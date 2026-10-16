"""F8: a reply never moves a lead back from meeting or client to replied.
F9: an out-of-office reply leaves the lead's status alone."""
import pytest

import db
import inbox
from fakemail import message, run, status

STATUSES = ["new", "verified", "sent", "replied", "meeting", "client", "bounced", "unsubscribed"]
# What each reply label does to each status (None = left as it is)
EXPECTED = {
    "interested":     {"new": "replied", "verified": "replied", "sent": "replied"},
    "question":       {"new": "replied", "verified": "replied", "sent": "replied"},
    "not_interested": {"new": "replied", "verified": "replied", "sent": "replied"},
    "needs_review":   {"new": "replied", "verified": "replied", "sent": "replied"},
    "out_of_office":  {},
    "bounce":         {s: "bounced" for s in ("new", "verified", "sent", "replied", "bounced")},
    "unsubscribe":    {s: "unsubscribed" for s in STATUSES},
}


@pytest.mark.parametrize("label", EXPECTED)
@pytest.mark.parametrize("current", STATUSES)
def test_every_status_and_label(current, label):
    assert inbox.status_after(current, label) == EXPECTED[label].get(current)


def set_status(email, new):
    db.set_status(db.find_lead_by_email(email)["id"], new, "dashboard")


@pytest.mark.parametrize("stage", ["meeting", "client"])
def test_lead_at_meeting_or_client_keeps_its_status_and_still_alerts(leads, ai, alerts, monkeypatch, stage):
    set_status("info@dazzcode.com", stage)
    run(monkeypatch, message("info@dazzcode.com", "Re: Thursday", "See you Thursday at 10."))
    assert status("info@dazzcode.com") == stage
    assert len(alerts) == 1  # you still hear about it


def test_out_of_office_header_reply_leaves_the_lead_waiting(leads, ai, alerts, monkeypatch):
    run(monkeypatch, message("info@dazzcode.com", "Automatic reply: Quick chat", "I am away until Monday."))
    assert status("info@dazzcode.com") == "sent"
    with db.conn() as c:  # the reply is still stored and in the lead's history
        assert c.execute("SELECT label FROM replies").fetchone()[0] == "out_of_office"


def test_out_of_office_from_the_ai_leaves_the_lead_waiting(leads, alerts, monkeypatch):
    import classifier
    monkeypatch.setattr(classifier, "ask", lambda *a, **k:
                        '{"label": "out_of_office", "summary": "away", "confidence": 0.9}')
    run(monkeypatch, message("info@dazzcode.com", "Re: Quick chat", "I'm travelling, back next week."))
    assert status("info@dazzcode.com") == "sent"


def test_real_reply_after_an_out_of_office_counts(leads, ai, alerts, monkeypatch):
    run(monkeypatch,
        message("info@dazzcode.com", "Automatic reply: Quick chat", "I am away until Monday."),
        message("info@dazzcode.com", "Re: Quick chat", "Back now. Yes, call me."))
    assert status("info@dazzcode.com") == "replied"


def test_unsubscribe_from_a_client_still_opts_out(leads, ai, alerts, monkeypatch):
    set_status("info@dazzcode.com", "client")
    run(monkeypatch, message("info@dazzcode.com", "unsubscribe", "Please unsubscribe me"))
    assert status("info@dazzcode.com") == "unsubscribed"
    assert db.is_suppressed("info@dazzcode.com")


def test_dashboard_can_still_set_any_status(leads):
    set_status("info@dazzcode.com", "client")
    set_status("info@dazzcode.com", "replied")  # a correction by hand is allowed
    assert status("info@dazzcode.com") == "replied"
