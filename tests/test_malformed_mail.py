"""A-04: one email that can't be read never stops the inbox check. Headers and bodies in a
charset Python doesn't know are read anyway; any other error in one email sets that email
aside (left unread, skipped from then on, alerted once) and the check goes on. Errors about
the connection or the database still stop the check, so the next one tries again."""
import imaplib
import sqlite3

import pytest

import db
import inbox
from fakemail import FakeMailbox, message, run, status

BOGUS_SUBJECT = "=?x-bogus-charset?Q?Special_offer?="


def stored():
    with db.conn() as c:
        return [tuple(r) for r in c.execute("SELECT from_email, label FROM replies ORDER BY id")]


def heartbeat(tmp_path):
    return (tmp_path / "last_check.txt").exists()


def first(leads):
    return list(leads)[0]


def test_unknown_charset_header_from_a_stranger_is_skipped_normally(leads, ai, alerts, tmp_path, monkeypatch):
    junk = message("promo@spam.example", BOGUS_SUBJECT, "Buy now")
    reply = message(first(leads), "Re: SMS for your school", "Yes, call me tomorrow.")
    run(monkeypatch, folders={"Junk": {b"1": junk}, "Archive": {b"1": reply}})
    assert stored() == [(first(leads), "interested")]
    assert "Junk:1" in db.skipped_uids()
    assert len(alerts) == 1  # the interested reply only
    assert heartbeat(tmp_path)


def test_unknown_charset_header_and_body_from_a_lead_are_read(leads, ai, alerts, monkeypatch):
    raw = message(first(leads), BOGUS_SUBJECT, "Yes, call me tomorrow.").replace(
        b"charset=utf-8", b"charset=x-bogus-charset")
    run(monkeypatch, raw)
    assert stored() == [(first(leads), "interested")]
    assert "call me tomorrow" in ai[0]


def test_header_text_never_raises():
    assert inbox.header_text(BOGUS_SUBJECT) == "Special offer"
    assert inbox.header_text("=?utf-8?q?Habari_yako?=") == "Habari yako"
    assert inbox.header_text(None) == ""


@pytest.fixture
def breaks_on_uid_1(monkeypatch):
    """check_message fails, in a way nobody planned for, on INBOX uid 1 only."""
    real = inbox.check_message

    def check_message(box, uid, *args):
        if box.current == "INBOX" and uid == b"1":
            raise ValueError("something nobody planned for")
        return real(box, uid, *args)

    monkeypatch.setattr(inbox, "check_message", check_message)


def test_one_bad_email_is_set_aside_and_the_rest_are_read(leads, ai, alerts, tmp_path, monkeypatch, breaks_on_uid_1):
    bad = message("someone@odd.example", "Re: SMS", "?")
    good = message(first(leads), "Re: SMS for your school", "Yes, call me tomorrow.")
    box = run(monkeypatch, bad, good)
    assert stored() == [(first(leads), "interested")]
    assert "1" in db.skipped_uids()
    assert ("INBOX", b"1") not in box.seen  # left unread
    assert len(alerts) == 2
    set_aside_alert = next(a for a in alerts if "could not read" in a)
    assert "INBOX message 1" in set_aside_alert and "ValueError" in set_aside_alert
    assert heartbeat(tmp_path)


def test_a_set_aside_email_is_alerted_once(leads, ai, alerts, monkeypatch, breaks_on_uid_1):
    bad = message("someone@odd.example", "Re: SMS", "?")
    run(monkeypatch, bad)
    run(monkeypatch, bad)
    assert len(alerts) == 1


def test_catch_up_that_fails_again_does_not_alert_again(leads, ai, alerts, monkeypatch, breaks_on_uid_1):
    bad = message("someone@odd.example", "Re: SMS", "?")
    run(monkeypatch, bad)
    box = FakeMailbox({b"1": bad})
    monkeypatch.setattr(inbox.imaplib, "IMAP4_SSL", box)
    inbox.check_once(catch_up=True)
    assert len(alerts) == 1
    assert "1" in db.skipped_uids()


@pytest.mark.parametrize("error", [imaplib.IMAP4.abort("connection lost"), ConnectionResetError("reset"),
                                   sqlite3.OperationalError("database is locked")])
def test_connection_and_database_errors_still_stop_the_check(leads, ai, alerts, tmp_path, monkeypatch, error):
    def check_message(*args):
        raise error

    monkeypatch.setattr(inbox, "check_message", check_message)
    with pytest.raises(type(error)):
        run(monkeypatch, message(first(leads), "Re: SMS", "Yes, call me tomorrow."))
    assert "1" not in db.skipped_uids()  # tried again at the next check, not set aside
    assert not alerts
    assert not heartbeat(tmp_path)
    assert status(first(leads)) == "sent"
