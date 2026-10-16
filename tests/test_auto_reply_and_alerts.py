"""F3: out-of-office is decided by auto-reply headers, not by words like "on leave".
F6: a Telegram failure never loses an alert or stops the inbox check."""
import pytest
import requests

import config
import db
import notify
from fakemail import message, run, status


# --- F3: out of office ---

def test_interested_reply_mentioning_leave_goes_to_the_ai_and_alerts(leads, ai, alerts, monkeypatch):
    run(monkeypatch, message("info@dazzcode.com", "Re: Quick chat",
                             "Our IT head is on leave, but we would like a demo next week."))
    assert len(ai) == 1
    assert status("info@dazzcode.com") == "replied"
    assert len(alerts) == 1 and "INTERESTED" in alerts[0]


@pytest.mark.parametrize("headers", [
    {"Auto-Submitted": "auto-replied"},
    {"Auto-Submitted": "auto-generated"},
    {"X-Autoreply": "yes"},
    {"X-Autorespond": "Out of office"},
    {"Precedence": "auto_reply"},
])
def test_auto_reply_headers_mean_out_of_office(leads, ai, alerts, monkeypatch, headers):
    run(monkeypatch, message("info@dazzcode.com", "Re: Quick chat",
                             "I am away until Monday with limited access to email.", headers=headers))
    with db.conn() as c:
        assert c.execute("SELECT label FROM replies").fetchone()[0] == "out_of_office"
    assert not ai and not alerts


@pytest.mark.parametrize("subject", ["Automatic reply: Quick chat", "Out of Office: Quick chat",
                                     "Auto-Reply: Quick chat", "Autoreply: Quick chat"])
def test_auto_reply_subjects_mean_out_of_office(leads, ai, alerts, monkeypatch, subject):
    run(monkeypatch, message("info@dazzcode.com", subject, "I am out of the office until 20 October."))
    with db.conn() as c:
        assert c.execute("SELECT label FROM replies").fetchone()[0] == "out_of_office"
    assert not ai and not alerts


def test_auto_submitted_no_is_a_person(leads, ai, alerts, monkeypatch):
    run(monkeypatch, message("info@dazzcode.com", "Re: Quick chat", "Yes, call me.",
                             headers={"Auto-Submitted": "no"}))
    assert len(ai) == 1 and len(alerts) == 1


# --- F6: alerts survive Telegram failures ---

@pytest.fixture
def telegram(monkeypatch):
    """A Telegram that can be switched off; records what it delivered."""
    state = {"up": True, "delivered": []}

    def send(text):
        if not state["up"]:
            raise requests.ConnectionError("telegram unreachable")
        state["delivered"].append(text)

    monkeypatch.setattr(notify, "send", send)
    return state


def test_telegram_down_does_not_stop_the_check_or_lose_the_alert(leads, ai, telegram, monkeypatch):
    telegram["up"] = False
    mails = (message("info@dazzcode.com", "Re: Quick chat", "Yes, call me Thursday."),
             message("info@nyerihigh.com", "Re: Fees", "Send pricing please."),
             message("stranger@example.org", "Hello", "Not a lead."))
    run(monkeypatch, *mails)  # must not raise
    with db.conn() as c:
        assert c.execute("SELECT COUNT(*) FROM replies").fetchone()[0] == 2  # both replies stored
        assert c.execute("SELECT COUNT(*) FROM skipped").fetchone()[0] == 1  # the stranger remembered
    assert len(db.pending_alerts()) == 2 and not telegram["delivered"]
    assert db.pending_alerts()[0]["attempts"] == 1

    telegram["up"] = True
    run(monkeypatch, *mails)  # next check: the queued alerts go out
    assert len(telegram["delivered"]) == 2 and not db.pending_alerts()

    run(monkeypatch, *mails)  # and never again
    assert len(telegram["delivered"]) == 2


def test_queued_alerts_go_out_even_if_the_mailbox_is_down(leads, ai, telegram, monkeypatch):
    telegram["up"] = False
    run(monkeypatch, message("info@dazzcode.com", "Re: Quick chat", "Yes, call me."))
    telegram["up"] = True

    def broken_mailbox(host):
        raise OSError("mail server unreachable")

    monkeypatch.setattr("inbox.imaplib.IMAP4_SSL", broken_mailbox)
    import inbox
    with pytest.raises(OSError):
        inbox.check_once()
    assert len(telegram["delivered"]) == 1


def test_send_raises_when_telegram_refuses(monkeypatch):
    class Refused:
        status_code = 401

        def raise_for_status(self):
            raise requests.HTTPError("401 Unauthorized")

    monkeypatch.setattr(config, "TELEGRAM_BOT_TOKEN", "test-token")
    monkeypatch.setattr(notify.requests, "post", lambda *a, **k: Refused())
    with pytest.raises(requests.HTTPError):
        notify.send("hello")
