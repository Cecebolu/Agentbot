"""Unsubscribe handling in inbox.check_once, run against a temporary database and a fake
mailbox. Nothing is sent, no real mailbox is read and the AI is never called for real."""
import db
from fakemail import SENT_ID, message, run, status

FOOTER = 'If you\'d rather not hear from us, just reply "unsubscribe" and we won\'t email you again.'
HTML_FOOTER = ('<p>--<br>If you\'d rather not hear from us, <a href="mailto:x@talksasa.co.ke?subject=unsubscribe">'
               'click here to unsubscribe</a>.</p>')


def test_footer_link_unsubscribes(leads, ai, alerts, monkeypatch):
    run(monkeypatch, message("info@dazzcode.com", "unsubscribe", "Please unsubscribe me"))
    assert status("info@dazzcode.com") == "unsubscribed"
    assert db.is_suppressed("info@dazzcode.com")
    assert not ai and not alerts


def test_mail_app_unsubscribe_button_with_empty_body(leads, ai, alerts, monkeypatch):
    run(monkeypatch, message("info@dazzcode.com", "unsubscribe", ""))
    assert status("info@dazzcode.com") == "unsubscribed"


def test_typed_unsubscribe_reply_quoting_our_email(leads, ai, alerts, monkeypatch):
    body = f"Please unsubscribe me.\r\n\r\nFrom: Florence\r\nSent: Friday\r\nSubject: Hi\r\n\r\n{FOOTER}"
    run(monkeypatch, message("info@dazzcode.com", "RE: Hi", body))
    assert status("info@dazzcode.com") == "unsubscribed"


def test_outlook_reply_quoting_footer_is_not_an_unsubscribe(leads, ai, alerts, monkeypatch):
    body = (f"Yes please, call me on Thursday.\r\n\r\nFrom: Florence <f@talksasa.co.ke>\r\n"
            f"Sent: Monday, October 13, 2026 9:02 AM\r\nSubject: Quick chat\r\n\r\nHello\r\n--\r\n{FOOTER}")
    run(monkeypatch, message("info@dazzcode.com", "RE: Quick chat", body))
    assert status("info@dazzcode.com") == "replied"
    assert not db.is_suppressed("info@dazzcode.com")
    assert len(alerts) == 1


def test_outlook_reply_with_underscore_separator(leads, ai, alerts, monkeypatch):
    body = f"Sounds good, send pricing.\r\n\r\n________________________________\r\nFrom: Florence\r\n{FOOTER}"
    run(monkeypatch, message("info@dazzcode.com", "RE: Quick chat", body))
    assert status("info@dazzcode.com") == "replied"


def test_html_only_reply_quoting_footer_is_not_an_unsubscribe(leads, ai, alerts, monkeypatch):
    body = f"<html><body><p>Interested, send pricing.</p><blockquote>{HTML_FOOTER}</blockquote></body></html>"
    run(monkeypatch, message("info@dazzcode.com", "Re: Quick chat", body, html=True))
    assert status("info@dazzcode.com") == "replied"
    assert "<" not in ai[0].split("Reply:")[-1]  # the AI gets text, not HTML tags


def test_reply_with_footer_unquoted_is_not_an_unsubscribe(leads, ai, alerts, monkeypatch):
    # Some mail apps paste the original below with no marker at all
    run(monkeypatch, message("info@dazzcode.com", "Re: Quick chat", f"Call me tomorrow.\r\n\r\n--\r\n{FOOTER}"))
    assert status("info@dazzcode.com") == "replied"


def test_colleague_answering_our_email_unsubscribes_the_lead(leads, ai, alerts, monkeypatch):
    run(monkeypatch, message("bursar@nyerihigh.com", "Re: Fees", "Please remove us from your list.",
                             in_reply_to=SENT_ID))
    assert status("info@nyerihigh.com") == "unsubscribed"
    assert db.is_suppressed("bursar@nyerihigh.com")


def test_colleague_writing_fresh_unsubscribes_the_lead_without_ai(leads, ai, alerts, monkeypatch):
    run(monkeypatch, message("bursar@nyerihigh.com", "unsubscribe", "Please unsubscribe me"))
    assert status("info@nyerihigh.com") == "unsubscribed"
    assert db.is_suppressed("bursar@nyerihigh.com")
    assert not ai


def test_colleague_other_mail_is_left_alone(leads, ai, alerts, monkeypatch):
    run(monkeypatch, message("bursar@nyerihigh.com", "Term dates", "School opens on Monday."))
    assert status("info@nyerihigh.com") == "sent"
    assert not ai


def test_free_mail_stranger_does_not_unsubscribe_a_gmail_lead(leads, ai, alerts, monkeypatch):
    run(monkeypatch, message("someone@gmail.com", "unsubscribe", "Please unsubscribe me"))
    assert status("school@gmail.com") == "sent"
    assert not db.is_suppressed("someone@gmail.com")


def test_read_mail_is_checked_and_nothing_is_handled_twice(leads, ai, alerts, monkeypatch):
    mail = message("info@dazzcode.com", "unsubscribe", "Please unsubscribe me")
    box = run(monkeypatch, mail)
    assert box.searches[0][1] == "SINCE"  # every message since the first send, read or unread
    events = len(db.sent_log())
    run(monkeypatch, mail)
    with db.conn() as c:
        assert c.execute("SELECT COUNT(*) FROM replies").fetchone()[0] == 1
    assert len(db.sent_log()) == events
