"""A fake IMAP mailbox and message builder for the inbox tests."""
import db
import inbox

SENT_ID = "<abc123@talksasa.co.ke>"


class FakeMailbox:
    """Just enough of imaplib.IMAP4_SSL for check_once."""

    def __init__(self, mails):
        self.mails = mails  # uid (bytes) -> raw message (bytes)
        self.searches = []
        self.seen = []

    def __call__(self, host):
        return self

    def login(self, *a):
        pass

    def select(self, *a):
        return ("OK", [b"1"])

    def logout(self):
        pass

    def uid(self, cmd, *args):
        if cmd == "search":
            self.searches.append(args)
            return ("OK", [b" ".join(self.mails)])
        if cmd == "fetch":
            return ("OK", [(b"1", self.mails[args[0]])])
        if cmd == "store":
            self.seen.append(args[0])
        return ("OK", [b""])


def message(sender, subject, body, html=False, in_reply_to=None, headers=None):
    head = f"From: {sender}\r\nTo: florence@talksasa.co.ke\r\nSubject: {subject}\r\n"
    if in_reply_to:
        head += f"In-Reply-To: {in_reply_to}\r\n"
    for name, value in (headers or {}).items():
        head += f"{name}: {value}\r\n"
    kind = "text/html" if html else "text/plain"
    return (head + f"Content-Type: {kind}; charset=utf-8\r\n\r\n{body}\r\n").encode()


def run(monkeypatch, *mails):
    """One inbox check over these messages (uids 1, 2, ...)."""
    box = FakeMailbox({str(i).encode(): m for i, m in enumerate(mails, 1)})
    monkeypatch.setattr(inbox.imaplib, "IMAP4_SSL", box)
    inbox.check_once()
    return box


def status(email):
    return db.find_lead_by_email(email)["status"]
