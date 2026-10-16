"""F7: one failed email never stops the rest of the day's batch. Runs sender.run against a
temporary database and a fake SMTP server: no real email is sent."""
import smtplib
import sqlite3

import pytest

import config
import db
import ranking
import sender

LEADS = ["one@one.co.ke", "two@two.co.ke", "three@three.co.ke", "four@four.co.ke"]


@pytest.fixture
def waiting(tmp_path, monkeypatch):
    """Four verified SACCO leads (an approved industry), in this sending order."""
    monkeypatch.setattr(config, "DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setattr(config, "DAILY_LIMIT", 10)
    monkeypatch.setattr(config, "SEND_DELAY_SECONDS", 0)
    monkeypatch.setattr(config, "USE_AI_OPENER", False)
    monkeypatch.setattr(config, "FOLLOWUPS_APPROVED", False)
    monkeypatch.setattr(config, "FROM_EMAIL", "florence@talksasa.co.ke")
    monkeypatch.setattr(ranking, "fill_years", lambda *a, **k: 0)  # no WHOIS or website lookups
    monkeypatch.setattr(sender, "save_to_sent", lambda *a: True)  # no IMAP
    db.init()
    for email in LEADS:
        db.add_lead("Test Sacco", email.split("@")[1], "sacco", email, "manual")
        db.set_status(db.find_lead_by_email(email)["id"], "verified", "verify")


@pytest.fixture
def smtp(monkeypatch):
    """A fake mail server. errors[address] = exceptions to raise on its next attempts
    (None = accept); connect_ok = how many connections succeed (None = all)."""
    world = {"connects": 0, "delivered": [], "errors": {}, "connect_ok": None}

    class FakeSMTP:
        def __init__(self, host, port, timeout=None):
            world["connects"] += 1
            if world["connect_ok"] is not None and world["connects"] > world["connect_ok"]:
                raise ConnectionRefusedError("mail server down")

        def starttls(self):
            pass

        def login(self, *a):
            pass

        def quit(self):
            pass

        def send_message(self, msg):
            planned = world["errors"].get(msg["To"])
            error = planned.pop(0) if planned else None
            if error:
                raise error
            world["delivered"].append(msg["To"])

    monkeypatch.setattr(sender.smtplib, "SMTP", FakeSMTP)
    return world


def status(email):
    return db.find_lead_by_email(email)["status"]


def failed_events(email):
    with db.conn() as c:
        return c.execute("SELECT detail FROM lead_events WHERE event_type='send_failed' AND lead_id=?",
                         (db.find_lead_by_email(email)["id"],)).fetchall()


def test_all_sent(waiting, smtp):
    sender.run()
    assert smtp["delivered"] == LEADS
    assert all(status(e) == "sent" for e in LEADS)


def test_rejected_email_does_not_stop_the_batch(waiting, smtp):
    smtp["errors"]["two@two.co.ke"] = [smtplib.SMTPDataError(550, b"Message rejected")]
    sender.run()
    assert smtp["delivered"] == ["one@one.co.ke", "three@three.co.ke", "four@four.co.ke"]
    assert status("two@two.co.ke") == "verified"  # waiting: tried again next time
    assert "550" in failed_events("two@two.co.ke")[0][0]


def test_temporary_error_does_not_stop_the_batch(waiting, smtp):
    smtp["errors"]["two@two.co.ke"] = [smtplib.SMTPDataError(451, b"Try again later")]
    sender.run()
    assert len(smtp["delivered"]) == 3 and status("two@two.co.ke") == "verified"


def test_dropped_connection_reconnects_and_retries_the_lead(waiting, smtp):
    smtp["errors"]["two@two.co.ke"] = [smtplib.SMTPServerDisconnected("Connection unexpectedly closed")]
    sender.run()
    assert smtp["delivered"] == LEADS
    assert smtp["connects"] == 2


def test_server_closing_421_reconnects(waiting, smtp):
    smtp["errors"]["two@two.co.ke"] = [smtplib.SMTPDataError(421, b"Service closing")]
    sender.run()
    assert smtp["delivered"] == LEADS and smtp["connects"] == 2


def test_cannot_reconnect_stops_cleanly_and_leaves_the_rest_waiting(waiting, smtp):
    smtp["connect_ok"] = 1
    smtp["errors"]["two@two.co.ke"] = [ConnectionResetError("reset by peer")]
    sender.run()  # no exception
    assert smtp["delivered"] == ["one@one.co.ke"]
    assert [status(e) for e in LEADS[1:]] == ["verified"] * 3


def test_refused_recipient_is_bounced_and_the_rest_go_out(waiting, smtp):
    smtp["errors"]["two@two.co.ke"] = [smtplib.SMTPRecipientsRefused({"two@two.co.ke": (550, b"No such user")})]
    sender.run()
    assert status("two@two.co.ke") == "bounced"
    assert db.is_suppressed("two@two.co.ke")
    assert len(smtp["delivered"]) == 3


def test_three_failures_in_a_row_stop_the_batch(waiting, smtp):
    for email in LEADS[:3]:
        smtp["errors"][email] = [smtplib.SMTPDataError(554, b"Spam detected")]
    sender.run()
    assert smtp["delivered"] == []
    assert not failed_events("four@four.co.ke")  # never tried
    assert status("four@four.co.ke") == "verified"


def test_sender_refused_stops_at_once(waiting, smtp):
    smtp["errors"]["one@one.co.ke"] = [smtplib.SMTPSenderRefused(553, b"Sender not allowed", "florence@talksasa.co.ke")]
    sender.run()
    assert smtp["delivered"] == []
    assert not failed_events("two@two.co.ke")


def test_broken_template_skips_only_that_lead(waiting, smtp, monkeypatch):
    real_build = sender.build

    def build(lead):
        if lead["email"] == "two@two.co.ke":
            raise KeyError("phone_number")
        return real_build(lead)

    monkeypatch.setattr(sender, "build", build)
    sender.run()
    assert smtp["delivered"] == ["one@one.co.ke", "three@three.co.ke", "four@four.co.ke"]
    assert status("two@two.co.ke") == "verified"


def test_error_after_the_email_went_out_stops_without_sending_twice(waiting, smtp, monkeypatch):
    def broken_record(*a, **k):
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(db, "record_sent", broken_record)
    with pytest.raises(sqlite3.OperationalError):
        sender.run()
    assert smtp["delivered"] == ["one@one.co.ke"]  # gone once, never retried
