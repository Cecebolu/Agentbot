"""G-01: only a plain request to stop is an opt-out. Questions and talk about unsubscribing
are held for a person (needs_review, alerted), and the AI never opts anyone out nor
overrides a plain opt-out. Temporary database and fake mailbox; the AI is a fake."""
import pytest

import classifier
import db
from fakemail import SENT_ID, message, run, status

DIRECT = [
    "Please unsubscribe me.",
    "Unsubscribe",
    "Please remove me from your mailing list.",
    "Remove us from your list.",
    "Not interested, please remove us.",
    "Can you please remove us from your list?",
    "Could you unsubscribe me?",
    "Stop emailing us.",
    "Please stop sending us emails.",
    "Do not contact us again.",
    "Take me off your list, thanks.",
    "We would like to opt out.",
    "I'd like to unsubscribe.",
    "Thanks but no more emails please.",
    # Swahili / Sheng
    "Tafadhali niondoe kwenye orodha yenu.",
    "Acha kunitumia hizi email.",
    "Usinitumie tena barua pepe.",
    "Msitutumie ujumbe tena.",
    "Sitaki tena email zenu.",
    "Hatutaki barua zenu, asanteni.",
    "Stop kunitumia hizi messages bana.",
]

NOT_A_REQUEST = [
    # questions about unsubscribing
    "Do your messages let members unsubscribe?",
    "How can someone unsubscribe from your service?",
    "Can you tell me how to unsubscribe?",
    "What happens if a member wants to opt out?",
    "Je, wateja wanaweza kujiondoa?",
    "Mtu anawezaje kujiondoa kwenye SMS zenu?",
    # talk about the process
    "We need to understand your unsubscribe process before integrating.",
    "Our members can opt out by replying STOP.",
    # negation
    "Please don't remove us, we are interested.",
    "We do not want to unsubscribe, send pricing.",
    "Never unsubscribe us, we like these updates.",
]


@pytest.mark.parametrize("text", DIRECT)
def test_direct_request_is_an_opt_out(text):
    assert classifier.quick_rules(f"Subject: Re: Loan reminders\n\n{text}") == "unsubscribe"


@pytest.mark.parametrize("text", NOT_A_REQUEST)
def test_mention_without_a_request_goes_to_review(text):
    assert classifier.quick_rules(f"Subject: Re: Loan reminders\n\n{text}") == "needs_review"


@pytest.mark.parametrize("text", ["Yes, call me Thursday.", "Tupigie simu kesho.", "What's your price per SMS?"])
def test_ordinary_replies_are_left_to_the_ai(text):
    assert classifier.quick_rules(f"Subject: Re: Loan reminders\n\n{text}") is None


def test_unsubscribe_link_and_mail_app_button():
    assert classifier.quick_rules("Subject: unsubscribe\n\nPlease unsubscribe me") == "unsubscribe"
    assert classifier.quick_rules("Subject: unsubscribe\n\n") == "unsubscribe"
    # the link's subject, but the person wrote a question instead
    assert classifier.quick_rules("Subject: unsubscribe\n\nHow do your members unsubscribe?") == "needs_review"


def test_quoted_lines_are_not_read_as_a_request():
    assert classifier.quick_rules("Subject: Re: Hi\n\nInterested.\n> Please remove me from your list") is None


def test_request_after_a_question_still_counts():
    text = "Subject: Re: Hi\n\nWhy did you email us? Remove us from your list."
    assert classifier.quick_rules(text) == "unsubscribe"


def test_the_ai_never_overrides_a_plain_opt_out(monkeypatch):
    asked = []
    monkeypatch.setattr(classifier, "ask", lambda p, groq_model=None: asked.append(p) or
                        '{"label": "interested", "summary": "x", "confidence": 0.99}')
    assert classifier.classify("Subject: Re: Hi\n\nPlease remove us from your list.")["label"] == "unsubscribe"
    assert not asked


def test_the_ai_alone_never_opts_anyone_out(monkeypatch):
    monkeypatch.setattr(classifier, "ask", lambda p, groq_model=None:
                        '{"label": "unsubscribe", "summary": "wants out", "confidence": 0.95}')
    result = classifier.classify("Subject: Re: Hi\n\nHii haitusaidii kwa sasa.")
    assert result["label"] == "needs_review" and result["hold"]


# --- through the inbox check ---

def test_question_about_unsubscribing_is_held_and_alerted(leads, ai, alerts, monkeypatch):
    run(monkeypatch, message("info@dazzcode.com", "Re: Hi", "How can our members unsubscribe from your SMS?"))
    assert not db.is_suppressed("info@dazzcode.com")
    assert status("info@dazzcode.com") == "replied"  # no follow-up: a person reads it first
    with db.conn() as c:
        assert c.execute("SELECT label FROM replies").fetchone()[0] == "needs_review"
    assert len(alerts) == 1 and not ai


def test_plain_opt_out_suppresses_at_once(leads, ai, alerts, monkeypatch):
    run(monkeypatch, message("info@dazzcode.com", "Re: Hi", "Tafadhali niondoe kwenye orodha yenu."))
    assert status("info@dazzcode.com") == "unsubscribed"
    assert db.is_suppressed("info@dazzcode.com") and not ai


def test_quoted_request_in_a_reply_is_not_an_opt_out(leads, ai, alerts, monkeypatch):
    body = ("Sounds good, send pricing.\r\n\r\nOn Mon, 13 Oct 2026 at 09:00, Florence wrote:\r\n"
            "> Please remove me from your list if this isn't relevant.")
    run(monkeypatch, message("info@dazzcode.com", "Re: Hi", body))
    assert status("info@dazzcode.com") == "replied" and not db.is_suppressed("info@dazzcode.com")
    assert len(ai) == 1  # an ordinary reply: the AI reads it


def test_negated_request_is_not_an_opt_out(leads, ai, alerts, monkeypatch):
    run(monkeypatch, message("info@dazzcode.com", "Re: Hi", "Please don't remove us, we want a demo."))
    assert not db.is_suppressed("info@dazzcode.com")
    assert len(alerts) == 1


def test_opt_out_from_an_address_linked_to_no_lead_is_kept(leads, ai, alerts, monkeypatch):
    run(monkeypatch, message("ceo@otherfirm.co.ke", "RE: FW: Fee reminders", "Please remove us from your list.",
                             in_reply_to=SENT_ID))
    assert db.is_suppressed("ceo@otherfirm.co.ke")
    assert status("info@nyerihigh.com") == "unsubscribed"  # its thread is that lead's email


def test_opt_out_matched_by_our_subject_alone_is_kept(leads, ai, alerts, monkeypatch):
    # forwarded and answered from an unrelated address, reply headers lost: linked to no lead
    run(monkeypatch, message("ceo@otherfirm.co.ke", "RE: FW: Fee reminders and parent alerts by SMS",
                             "Please remove us from your list."))
    assert db.is_suppressed("ceo@otherfirm.co.ke")
    with db.conn() as c:
        assert tuple(c.execute("SELECT lead_id, label FROM replies").fetchone()) == (None, "unsubscribe")
    assert not ai


def test_colleague_question_about_unsubscribing_is_held(leads, ai, alerts, monkeypatch):
    run(monkeypatch, message("bursar@nyerihigh.com", "Opt-outs", "How do parents unsubscribe from your SMS?"))
    assert status("info@nyerihigh.com") == "replied"  # someone there answered: no follow-up
    assert not db.is_suppressed("bursar@nyerihigh.com") and not db.is_suppressed("info@nyerihigh.com")
    assert len(alerts) == 1 and not ai
