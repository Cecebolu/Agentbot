"""inbox.check_once(catch_up=True): mail an earlier check skipped is read again, and what now
matches a lead is held for a person (needs_review + alert), never sent to the AI."""
import db
import inbox
from fakemail import SENT_ID, FakeMailbox, message, status


def check(monkeypatch, mails, catch_up):
    """One check over these messages (uid -> raw message)."""
    box = FakeMailbox(mails)
    monkeypatch.setattr(inbox.imaplib, "IMAP4_SSL", box)
    inbox.check_once(catch_up=catch_up)
    return box


def stored():
    with db.conn() as c:
        return c.execute("SELECT from_email, label FROM replies ORDER BY id").fetchall()


def colleague_reply():
    # answers our email to info@nyerihigh.com (SENT_ID) from another address
    return message("bursar@nyerihigh.com", "Re: Fee reminders", "Yes, please call me on Monday.", in_reply_to=SENT_ID)


def test_skipped_thread_reply_is_caught_up_and_held_for_you(leads, ai, alerts, monkeypatch):
    db.add_skipped(["7"])  # an older check passed over it
    check(monkeypatch, {b"7": colleague_reply()}, catch_up=True)
    assert [tuple(r) for r in stored()] == [("bursar@nyerihigh.com", "needs_review")]
    assert not ai  # never sent to the AI
    assert len(alerts) == 1 and "NEEDS_REVIEW" in alerts[0]
    assert status("info@nyerihigh.com") == "replied"  # no follow-up any more
    assert "7" not in db.skipped_uids()


def test_normal_check_still_ignores_skipped_mail(leads, ai, alerts, monkeypatch):
    db.add_skipped(["7"])
    check(monkeypatch, {b"7": colleague_reply()}, catch_up=False)
    assert stored() == [] and not alerts


def test_catch_up_reads_only_skipped_mail(leads, ai, alerts, monkeypatch):
    new = message("info@dazzcode.com", "Re: Quick chat", "Call me.")
    check(monkeypatch, {b"8": new}, catch_up=True)  # never skipped: left to the normal check
    assert stored() == []


def test_still_unmatched_mail_stays_skipped(leads, ai, alerts, monkeypatch):
    db.add_skipped(["9"])
    check(monkeypatch, {b"9": message("someone@example.org", "Hello", "Newsletter")}, catch_up=True)
    assert stored() == [] and "9" in db.skipped_uids()


def test_colleague_opt_out_is_held_not_acted_on(leads, ai, alerts, monkeypatch):
    db.add_skipped(["10"])
    check(monkeypatch, {b"10": message("bursar@nyerihigh.com", "unsubscribe", "Please unsubscribe me")},
          catch_up=True)
    assert [tuple(r) for r in stored()] == [("bursar@nyerihigh.com", "needs_review")]
    assert len(alerts) == 1
    assert not db.is_suppressed("bursar@nyerihigh.com")  # you decide


def test_caught_up_auto_reply_is_out_of_office_without_alert(leads, ai, alerts, monkeypatch):
    db.add_skipped(["11"])
    auto = message("bursar@nyerihigh.com", "Ticket Received - Fee reminders", "We got your message.",
                   in_reply_to=SENT_ID, headers={"Auto-Submitted": "auto-replied"})
    check(monkeypatch, {b"11": auto}, catch_up=True)
    assert [tuple(r) for r in stored()] == [("bursar@nyerihigh.com", "out_of_office")]
    assert not alerts and status("info@nyerihigh.com") == "sent"


def test_catching_up_twice_changes_nothing(leads, ai, alerts, monkeypatch):
    db.add_skipped(["7"])
    check(monkeypatch, {b"7": colleague_reply()}, catch_up=True)
    check(monkeypatch, {b"7": colleague_reply()}, catch_up=True)
    assert len(stored()) == 1 and len(alerts) == 1
