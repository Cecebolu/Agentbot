"""Shared fixtures. Every test gets its own temporary database; the AI and Telegram are
replaced by fakes, so nothing real is called, read or sent."""
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))

import classifier  # noqa: E402
import config  # noqa: E402
import db  # noqa: E402
import inbox  # noqa: E402
import notify  # noqa: E402
from fakemail import SENT_ID  # noqa: E402


@pytest.fixture
def leads(tmp_path, monkeypatch):
    """A fresh database with three emailed leads, one of them on gmail.com."""
    monkeypatch.setattr(config, "DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setattr(inbox, "Path", lambda *_: tmp_path / "inbox.py")  # heartbeat file
    db.init()
    ids = {}
    for email in ("info@nyerihigh.com", "info@dazzcode.com", "school@gmail.com"):
        db.add_lead("Test", email.split("@")[1], "school", email, "manual")
        lead = db.find_lead_by_email(email)
        db.record_sent(lead["id"], SENT_ID if email == "info@nyerihigh.com" else f"<{email}>", "school")
        db.set_status(lead["id"], "sent", "send")
        ids[email] = lead["id"]
    return ids


@pytest.fixture
def ai(monkeypatch):
    """Every message the AI is asked about; it always answers "interested"."""
    asked = []

    def fake_ask(prompt, groq_model=None):
        asked.append(prompt)
        return '{"label": "interested", "summary": "wants a call", "confidence": 0.9}'

    monkeypatch.setattr(classifier, "ask", fake_ask)
    return asked


@pytest.fixture
def alerts(monkeypatch):
    """Every Telegram message sent."""
    sent = []
    monkeypatch.setattr(notify, "send", sent.append)
    return sent
