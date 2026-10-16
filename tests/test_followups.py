"""One follow-up per lead, in the same thread, 5 business days after the first email.
Temporary database and fake mail server: nothing is sent."""
from datetime import date

import pytest

import config
import db
import ranking
import sender

FIRST_ID = "<first@talksasa.co.ke>"


@pytest.fixture
def world(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setattr(config, "FOLLOWUPS_APPROVED", True)
    monkeypatch.setattr(config, "FOLLOWUP_AFTER_DAYS", 5)
    monkeypatch.setattr(config, "DAILY_LIMIT", 10)
    monkeypatch.setattr(config, "SEND_DELAY_SECONDS", 0)
    monkeypatch.setattr(config, "USE_AI_OPENER", False)
    monkeypatch.setattr(config, "FROM_EMAIL", "florence@talksasa.co.ke")
    monkeypatch.setattr(ranking, "fill_years", lambda *a, **k: 0)
    monkeypatch.setattr(sender, "save_to_sent", lambda *a: True)
    monkeypatch.setattr(sender.notify, "send", lambda text: None)
    db.init()


def emailed(address, days_ago, industry="sacco", subject="Loan reminders by SMS", message_id=FIRST_ID):
    """A lead whose first email went out `days_ago` days ago and who hasn't answered."""
    db.add_lead("Hurima Sacco", address.split("@")[1], industry, address, "search")
    lead_id = db.find_lead_by_email(address)["id"]
    db.record_sent(lead_id, message_id, industry, subject, "first email")
    db.set_status(lead_id, "sent", "send")
    with db.conn() as c:
        c.execute("UPDATE sent SET sent_on = date('now', ?) WHERE lead_id = ?", (f"-{days_ago} days", lead_id))
    return lead_id


def sent_to(smtp_world, address):
    return [m for m in smtp_world["messages"] if m["To"] == address]


@pytest.fixture
def mail(smtp, monkeypatch):
    """The fake mail server, also keeping each whole message."""
    smtp["messages"] = []
    real = sender.deliver

    def deliver(s, lead, msg, tname, followup=False):
        real(s, lead, msg, tname, followup)
        smtp["messages"].append(msg)

    monkeypatch.setattr(sender, "deliver", deliver)
    return smtp


def test_follow_up_goes_in_the_same_thread(world, mail):
    emailed("info@hurimasacco.co.ke", days_ago=10)
    sender.run()
    [msg] = sent_to(mail, "info@hurimasacco.co.ke")
    assert msg["Subject"] == "Re: Loan reminders by SMS"
    assert msg["In-Reply-To"] == FIRST_ID and msg["References"] == FIRST_ID
    text = msg.get_body(("plain",)).get_content()
    assert "Hello Hurima Sacco team" in text and "Following up on my earlier note" in text
    assert "loan reminders, deposit confirmations and AGM notices" in text
    assert 'just reply "unsubscribe"' in text  # footer, as on every email
    assert not list(msg.iter_attachments())  # no PDF the second time
    assert db.find_lead_by_email("info@hurimasacco.co.ke")["status"] == "sent"  # still waiting
    assert db.sent_count(db.find_lead_by_email("info@hurimasacco.co.ke")["id"]) == 2


def test_not_due_before_five_business_days(world, mail):
    emailed("info@hurimasacco.co.ke", days_ago=1)
    sender.run()
    assert mail["delivered"] == []


def test_only_one_follow_up_ever(world, mail):
    emailed("info@hurimasacco.co.ke", days_ago=20)
    sender.run()
    sender.run()
    assert mail["delivered"] == ["info@hurimasacco.co.ke"]


@pytest.mark.parametrize("new_status", ["replied", "meeting", "client", "bounced", "unsubscribed", "invalid"])
def test_no_follow_up_once_the_lead_has_moved_on(world, mail, new_status):
    lead_id = emailed("info@hurimasacco.co.ke", days_ago=10)
    db.set_status(lead_id, new_status, "inbox")
    sender.run()
    assert mail["delivered"] == []


def test_recent_out_of_office_holds_the_follow_up(world, mail):
    lead_id = emailed("info@hurimasacco.co.ke", days_ago=10)
    db.add_reply(lead_id, "info@hurimasacco.co.ke", "Automatic reply", "Away", "out_of_office", "away", "1")
    sender.run()
    assert mail["delivered"] == []
    with db.conn() as c:  # a week later they are probably back
        c.execute("UPDATE replies SET received_at = datetime('now', '-8 days')")
    sender.run()
    assert mail["delivered"] == ["info@hurimasacco.co.ke"]


def test_nothing_when_follow_ups_are_not_approved(world, mail, monkeypatch):
    monkeypatch.setattr(config, "FOLLOWUPS_APPROVED", False)
    emailed("info@hurimasacco.co.ke", days_ago=10)
    sender.run()
    assert mail["delivered"] == []


def test_no_follow_up_without_a_template(world, mail, monkeypatch, tmp_path):
    monkeypatch.setattr(sender, "FOLLOWUP_DIR", tmp_path / "none")
    emailed("info@hurimasacco.co.ke", days_ago=10)
    sender.run()
    assert mail["delivered"] == []


def test_unapproved_industry_gets_no_follow_up(world, mail):
    emailed("info@clinic.co.ke", days_ago=10, industry="health")
    sender.run()
    assert mail["delivered"] == []


def test_first_email_is_never_sent_twice(world, mail):
    lead_id = emailed("info@hurimasacco.co.ke", days_ago=1)
    db.set_status(lead_id, "verified", "dashboard")  # set back by hand
    sender.run()
    assert mail["delivered"] == []


def test_follow_ups_go_first_within_the_daily_limit(world, mail, monkeypatch):
    monkeypatch.setattr(config, "DAILY_LIMIT", 1)
    emailed("info@hurimasacco.co.ke", days_ago=10)
    db.add_lead("New Sacco", "newsacco.co.ke", "sacco", "info@newsacco.co.ke", "search")
    db.set_status(db.find_lead_by_email("info@newsacco.co.ke")["id"], "verified", "verify")
    sender.run()
    assert mail["delivered"] == ["info@hurimasacco.co.ke"]


def test_first_subject_from_the_template_when_not_recorded(world, mail):
    emailed("info@hurimasacco.co.ke", days_ago=10, subject=None)
    sender.run()
    [msg] = sent_to(mail, "info@hurimasacco.co.ke")
    assert msg["Subject"] == "Re: Loan reminders by SMS"  # sacco template's own subject


def test_every_approved_industry_has_a_follow_up():
    import personalise
    approved = [k for k, v in personalise.USES.items() if v.get("approved")]
    missing = [k for k in approved if not (sender.FOLLOWUP_DIR / f"{k}.txt").exists()]
    assert missing == []


@pytest.mark.parametrize("start, expected", [
    ("2026-10-16", "2026-10-23"),  # Friday + 5 working days = next Friday
    ("2026-10-12", "2026-10-19"),  # Monday -> next Monday
    ("2026-10-17", "2026-10-23"),  # Saturday -> Friday
])
def test_business_days(start, expected):
    assert sender.business_days_after(date.fromisoformat(start), 5) == date.fromisoformat(expected)
