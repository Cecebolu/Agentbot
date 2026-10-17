"""A fake IMAP mailbox and message builder for the inbox tests."""
import db
import inbox

SENT_ID = "<abc123@talksasa.co.ke>"


class FakeMailbox:
    """Just enough of imaplib.IMAP4_SSL for check_once. `mails` is INBOX (uid bytes -> raw
    message); `folders` adds other folders. A Sent and a Drafts folder always exist."""

    def __init__(self, mails, folders=None):
        self.mails = mails
        self.folders = {"INBOX": mails, "Sent": {}, "Drafts": {}, **(folders or {})}
        self.current = "INBOX"
        self.searches = []
        self.seen = []

    def __call__(self, host):
        return self

    def login(self, *a):
        pass

    def list(self):
        flags = {"Sent": "\\Sent", "Drafts": "\\Drafts"}
        return ("OK", [f'(\\HasNoChildren {flags.get(name, "")}) "/" "{name}"'.encode() for name in self.folders])

    def select(self, name="INBOX", readonly=False):
        name = name.strip('"')
        if name not in self.folders:
            return ("NO", [b"no such folder"])
        self.current = name
        return ("OK", [str(len(self.folders[name])).encode()])

    def logout(self):
        pass

    def uid(self, cmd, *args):
        box = self.folders[self.current]
        if cmd == "search":
            self.searches.append(args)
            return ("OK", [b" ".join(box)])
        if cmd == "fetch":
            if args[0] not in box:
                return ("OK", [None])
            return ("OK", [(b"1", box[args[0]])])
        if cmd == "store":
            self.seen.append((self.current, args[0]))
        return ("OK", [b""])


def message(sender, subject, body, html=False, in_reply_to=None, headers=None, message_id=None):
    head = f"From: {sender}\r\nTo: florence@talksasa.co.ke\r\nSubject: {subject}\r\n"
    if message_id:
        head += f"Message-ID: {message_id}\r\n"
    if in_reply_to:
        head += f"In-Reply-To: {in_reply_to}\r\n"
    for name, value in (headers or {}).items():
        head += f"{name}: {value}\r\n"
    kind = "text/html" if html else "text/plain"
    return (head + f"Content-Type: {kind}; charset=utf-8\r\n\r\n{body}\r\n").encode()


def run(monkeypatch, *mails, folders=None):
    """One inbox check over these INBOX messages (uids 1, 2, ...) and any other folders."""
    box = FakeMailbox({str(i).encode(): m for i, m in enumerate(mails, 1)}, folders)
    monkeypatch.setattr(inbox.imaplib, "IMAP4_SSL", box)
    inbox.check_once()
    return box


def status(email):
    return db.find_lead_by_email(email)["status"]
