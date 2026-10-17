"""Every reply to our emails is stored and shown, even from an address linked to no lead:
held as needs_review, alerted once, never sent to the AI, never changing a lead."""
import db
from fakemail import SENT_ID, message, run, status

LEADBOT_ID = "<176061234567.4242.1234567890123456789@talksasa.co.ke>"  # how make_msgid looks


def stored():
    with db.conn() as c:
        return [tuple(r) for r in c.execute("SELECT lead_id, from_email, label FROM replies ORDER BY id")]


def test_reply_to_our_email_from_an_unknown_address_is_shown_and_alerted(leads, ai, alerts, monkeypatch):
    # e.g. a reply to a test email, which LeadBot sent but didn't record
    run(monkeypatch, message("ndemiflorence@gmail.com", "Re: [TEST] Fee reminders", "Looks good!",
                             in_reply_to=LEADBOT_ID))
    assert stored() == [(None, "ndemiflorence@gmail.com", "needs_review")]
    assert not ai and len(alerts) == 1 and "Not linked to a lead" in alerts[0]


def test_matched_by_our_subject_alone(leads, ai, alerts, monkeypatch):
    # forwarded inside a company, answered from an unrelated address, reply headers lost
    run(monkeypatch, message("ceo@otherfirm.co.ke", "RE: FW: Fee reminders and parent alerts by SMS",
                             "We'd like to talk."))
    assert stored() == [(None, "ceo@otherfirm.co.ke", "needs_review")]
    assert len(alerts) == 1


def test_unrelated_mail_stays_out(leads, ai, alerts, monkeypatch):
    run(monkeypatch,
        message("friend@gmail.com", "Re: lunch on Friday", "Sure", in_reply_to="<CAF123abc@mail.gmail.com>"),
        # a personal thread on our own domain, not an email LeadBot made
        message("colleague@partner.co.ke", "Re: invoice", "Paid", in_reply_to="<abc-def-123@talksasa.co.ke>"),
        message("news@shop.example", "Weekly deals", "50% off"))
    assert stored() == [] and not alerts


def test_unlinked_reply_changes_no_lead(leads, ai, alerts, monkeypatch):
    run(monkeypatch, message("someone@else.org", "Re: x", "Remove us please, we're not interested",
                             in_reply_to=LEADBOT_ID))
    assert stored() == [(None, "someone@else.org", "needs_review")]
    assert [status(e) for e in ("info@nyerihigh.com", "info@dazzcode.com", "school@gmail.com")] == ["sent"] * 3
    assert not db.is_suppressed("someone@else.org")  # held for you, not acted on


def test_unlinked_auto_reply_is_stored_without_alert(leads, ai, alerts, monkeypatch):
    run(monkeypatch, message("someone@else.org", "Automatic reply: Fee reminders", "Away this week",
                             in_reply_to=LEADBOT_ID))
    assert stored() == [(None, "someone@else.org", "out_of_office")]
    assert not alerts


def test_colleague_replying_outside_the_thread_is_held_against_the_lead(leads, ai, alerts, monkeypatch):
    lead_id = leads["info@nyerihigh.com"]
    run(monkeypatch, message("bursar@nyerihigh.com", "Re: Fee reminders and parent alerts by SMS",
                             "Please call the bursar's office."))
    assert stored() == [(lead_id, "bursar@nyerihigh.com", "needs_review")]
    assert not ai and len(alerts) == 1
    assert status("info@nyerihigh.com") == "replied"  # no follow-up


def test_linked_replies_still_go_to_the_ai(leads, ai, alerts, monkeypatch):
    run(monkeypatch, message("info@dazzcode.com", "Re: Quick chat", "Call me.", in_reply_to=SENT_ID))
    assert len(ai) == 1


def test_dashboard_lists_unlinked_replies(leads, ai, alerts, monkeypatch):
    run(monkeypatch, message("ndemiflorence@gmail.com", "Re: [TEST] Fee reminders", "Looks good!",
                             in_reply_to=LEADBOT_ID))
    import web
    web.ensure_schema()
    reply = web.all_data()["replies"][0]
    assert reply["from_email"] == "ndemiflorence@gmail.com" and reply["lead_id"] is None
    assert reply["handled"] is False  # waiting for you
