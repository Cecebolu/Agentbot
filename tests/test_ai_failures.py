"""G-02: an AI failure or an unsure answer is kept for a person (needs_review) and alerted
once; transient failures are retried a few times; no other provider is ever asked; and a
failed classification never leads to a follow-up. The AI's HTTP calls are faked."""
from datetime import date, timedelta

import pytest
import requests

import classifier
import config
import db
import sender
from fakemail import message, run, status


class FakeResponse:
    def __init__(self, code, body=None):
        self.status_code, self._body = code, body

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code} error", response=self)

    def json(self):
        return self._body


def groq_answer(label="interested", confidence=0.9):
    content = f'{{"label": "{label}", "summary": "s", "confidence": {confidence}}}'
    return FakeResponse(200, {"choices": [{"message": {"content": content}}]})


@pytest.fixture
def http(monkeypatch):
    """Every AI HTTP call: replies[i] answers the i-th (a response, or an exception to raise)."""
    world = {"urls": [], "replies": [], "sleeps": []}

    def post(url, **kw):
        world["urls"].append(url)
        reply = world["replies"].pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply

    monkeypatch.setattr(classifier.requests, "post", post)
    monkeypatch.setattr(classifier.time, "sleep", world["sleeps"].append)
    monkeypatch.setattr(config, "AI_PROVIDER", "groq")
    monkeypatch.setattr(config, "GROQ_API_KEY", "test-key")
    return world


def test_transient_failure_is_retried_then_succeeds(http):
    http["replies"] = [requests.ConnectionError("reset"), FakeResponse(503), groq_answer()]
    assert classifier.classify("Can we meet Thursday?")["label"] == "interested"
    assert len(http["urls"]) == 3 and http["sleeps"] == [5, 10]


def test_retries_are_limited_then_held_for_review(http):
    http["replies"] = [requests.Timeout("slow")] * 5
    result = classifier.classify("Can we meet Thursday?")
    assert result["label"] == "needs_review" and result["hold"]
    assert len(http["urls"]) == classifier.AI_TRIES


def test_a_bad_key_is_not_retried(http):
    http["replies"] = [FakeResponse(401)]
    assert classifier.classify("Can we meet Thursday?")["label"] == "needs_review"
    assert len(http["urls"]) == 1


def test_an_unreadable_answer_is_held(http):
    http["replies"] = [FakeResponse(200, {"choices": [{"message": {"content": "no json here"}}]})]
    assert classifier.classify("Can we meet Thursday?")["label"] == "needs_review"


def test_low_confidence_is_held(http):
    http["replies"] = [groq_answer("interested", 0.3)]
    result = classifier.classify("Hmm, maybe.")
    assert result["label"] == "needs_review" and result["hold"]


def test_only_groq_is_asked_when_groq_is_down(http, monkeypatch):
    http["replies"] = [requests.ConnectionError("down")] * 5
    monkeypatch.setattr(classifier, "_ask_ollama", lambda p: pytest.fail("another provider was asked"))
    classifier.classify("Can we meet Thursday?")
    assert http["urls"] and all(u.startswith("https://api.groq.com/") for u in http["urls"])


# --- through the inbox check ---

@pytest.fixture
def ai_down(monkeypatch):
    calls = []

    def fail(prompt, groq_model=None):
        calls.append(prompt)
        raise requests.ConnectionError("groq unreachable")

    monkeypatch.setattr(classifier, "ask", fail)
    monkeypatch.setattr(classifier.time, "sleep", lambda s: None)
    return calls


def replies():
    with db.conn() as c:
        return c.execute("SELECT label, summary FROM replies").fetchall()


def test_failed_classification_is_kept_and_alerted_once(leads, ai_down, alerts, monkeypatch):
    mail = message("info@dazzcode.com", "Re: Hi", "Can you send pricing for 20,000 SMS?")
    run(monkeypatch, mail)
    run(monkeypatch, mail)  # the next poll sees the same message
    run(monkeypatch, mail)
    stored = replies()
    assert len(stored) == 1 and stored[0]["label"] == "needs_review"
    assert "could not read" in stored[0]["summary"]
    assert len(alerts) == 1 and "NEEDS_REVIEW" in alerts[0]
    assert len(ai_down) == classifier.AI_TRIES  # retried within the first check only


def test_alert_that_fails_is_retried_not_duplicated(leads, ai_down, monkeypatch):
    sent, attempts = [], []

    def flaky(text):
        attempts.append(text)
        if len(attempts) == 1:
            raise requests.ConnectionError("telegram down")
        sent.append(text)

    import notify
    monkeypatch.setattr(notify, "send", flaky)
    mail = message("info@dazzcode.com", "Re: Hi", "Can you send pricing?")
    run(monkeypatch, mail)
    run(monkeypatch, mail)
    run(monkeypatch, mail)
    assert len(sent) == 1


def test_no_follow_up_after_a_failed_classification(leads, ai_down, alerts, monkeypatch):
    run(monkeypatch, message("info@dazzcode.com", "Re: Hi", "Can you send pricing?"))
    assert status("info@dazzcode.com") == "replied"
    monkeypatch.setattr(config, "FOLLOWUPS_APPROVED", True)
    with db.conn() as c:  # long past the follow-up day
        c.execute("UPDATE sent SET sent_on=?", ((date.today() - timedelta(days=30)).isoformat(),))
    assert "info@dazzcode.com" not in [l["email"] for l, _ in sender.followups_due()]
