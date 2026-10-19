"""A-01, A-02: only a delivery report from a mail server bounces a lead. A person's reply that
mentions a failed delivery, or one the AI calls a bounce, is held for you (needs_review, one
alert): the lead is not bounced or suppressed. Like any reply held for you, it moves the
lead to replied, so no automatic follow-up goes out before you have read it."""
import pytest

import classifier
import db
from fakemail import message, run, status

BOUNCE_PHRASES = [
    "Your first email to our old address was undeliverable, please use this one. We would like pricing.",
    "We tried your contact form but got address not found. Can you call us?",
    "Our mailbox unavailable error is fixed now. Send the brochure please.",
]


def stored():
    with db.conn() as c:
        return c.execute("SELECT label, lead_id FROM replies ORDER BY id").fetchall()


def suppressed():
    with db.conn() as c:
        return [tuple(r) for r in c.execute("SELECT email, reason FROM suppression ORDER BY email")]


def events(*types):
    with db.conn() as c:
        return [r[0] for r in c.execute(
            f"SELECT event_type FROM lead_events WHERE event_type IN ({','.join('?' * len(types))})", types)]


def check_twice(monkeypatch, mail):
    """Two inbox checks over the same message: the second must find nothing new."""
    run(monkeypatch, mail)
    run(monkeypatch, mail)


@pytest.mark.parametrize("text", BOUNCE_PHRASES)
def test_bounce_words_are_never_a_rule(text):
    assert classifier.quick_rules(f"Subject: Re: Loan reminders\n\n{text}") is None


@pytest.mark.parametrize("text", BOUNCE_PHRASES)
def test_person_mentioning_a_failed_delivery_is_held(text, ai):
    result = classifier.classify(f"Subject: Re: Loan reminders\n\n{text}")
    assert result["label"] == "needs_review" and result["hold"]
    assert not ai  # held by the rule, so the AI is not asked


def test_reply_mentioning_undeliverable_keeps_the_lead(leads, ai, alerts, monkeypatch):
    email = list(leads)[0]
    check_twice(monkeypatch, message(email, "Re: SMS for your school", BOUNCE_PHRASES[0]))
    assert [tuple(r) for r in stored()] == [("needs_review", leads[email])]
    assert status(email) == "replied"
    assert suppressed() == []
    assert events("bounced", "unsubscribed") == []
    assert len(alerts) == 1


def test_ai_saying_bounce_with_high_confidence_is_held(leads, alerts, monkeypatch):
    asked = []

    def fake_ask(prompt, groq_model=None):
        asked.append(prompt)
        return '{"label": "bounce", "summary": "mail failed", "confidence": 0.99}'

    monkeypatch.setattr(classifier, "ask", fake_ask)
    email = list(leads)[0]
    check_twice(monkeypatch, message(email, "Re: SMS for your school", "Hello, sorry for the late reply."))
    assert len(asked) == 1  # the second check does not ask the AI again
    assert [tuple(r) for r in stored()] == [("needs_review", leads[email])]
    assert status(email) == "replied"
    assert suppressed() == []
    assert events("bounced", "unsubscribed") == []
    assert len(alerts) == 1


def test_delivery_report_still_bounces(leads, ai, alerts, monkeypatch):
    email = list(leads)[0]
    dsn = message("mailer-daemon@googlemail.com", "Delivery Status Notification (Failure)",
                  f"Final-Recipient: rfc822; {email}\nAction: failed")
    check_twice(monkeypatch, dsn)
    assert [tuple(r) for r in stored()] == [("bounce", leads[email])]
    assert status(email) == "bounced"
    assert suppressed() == [(email, "bounced")]  # that address only, once
    assert events("bounced") == ["bounced"]
    assert not alerts and not ai
