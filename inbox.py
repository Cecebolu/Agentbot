"""Polls the inbox, matches replies to leads, classifies them and alerts you."""
import email
import html as html_lib
import imaplib
import re
import time
from datetime import date, datetime, timedelta
from email.header import decode_header, make_header
from email.utils import parseaddr
from pathlib import Path

import classifier
import config
import db
import notify
import ranking

ALERT_ON = {"interested", "question"}
BOUNCE_SENDERS = ("mailer-daemon@", "postmaster@")
MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
# Where the quoted copy of the email being answered starts in a plain-text reply
QUOTE_START = re.compile(
    r"\nOn [^\n]{5,200}\n?[^\n]{0,100}wrote:"         # Gmail, Apple Mail
    r"|\n-{2,} ?Original Message"                     # older Outlook
    r"|\n_{10,}"                                       # Outlook's line above the quote
    r"|\n\*?From:\*?[ \t][^\n]*\n\*?(?:Sent|Date):",  # Outlook's From:/Sent: block
    re.I)
# Where the quoted copy starts in an HTML reply
HTML_QUOTE_START = re.compile(r"<blockquote|<div[^>]+(?:gmail_quote|divRplyFwdMsg|appendonsend)", re.I)
# Subjects mail apps give automatic replies ("Automatic reply: ...", "Out of Office: ...")
AUTO_SUBJECT = re.compile(r"^\s*(automatic reply|auto[- ]?reply|autoreply|auto[- ]?response|"
                          r"out of (the )?office|away from (the )?office)\b", re.I)
# Our own footer, plain and HTML wording. It says "unsubscribe", so when a reply quotes it
# without the markers above it would read as an unsubscribe request; it is removed first.
OUR_FOOTER = re.compile(r"[^\n]*(?:rather not hear from us|click here to unsubscribe)[^\n]*", re.I)


def _decoded(part):
    return (part.get_payload(decode=True) or b"").decode(part.get_content_charset() or "utf-8", "ignore")


def html_text(html):
    """The readable text of an HTML email, without the quoted email it answers."""
    html = re.sub(r"(?is)<(style|script)\b.*?</\1>", " ", html)
    html = HTML_QUOTE_START.split(html, maxsplit=1)[0]
    html = re.sub(r"(?i)<br\s*/?>|</p>|</div>", "\n", html)
    return html_lib.unescape(re.sub(r"<[^>]+>", " ", html))


def text_of(msg):
    """Get the reply's own text: the plain-text part (or the HTML part as text), without the
    quoted original email and without our footer."""
    plain = html = None
    for part in msg.walk():
        if part.is_multipart() or "attachment" in str(part.get("Content-Disposition")):
            continue
        if part.get_content_type() == "text/plain" and plain is None:
            plain = _decoded(part)
        elif part.get_content_type() == "text/html" and html is None:
            html = _decoded(part)
    body = plain if plain is not None else html_text(html or "")
    body = QUOTE_START.split("\n" + body.replace("\r\n", "\n"), maxsplit=1)[0]
    body = OUR_FOOTER.sub("", body)
    return "\n".join(l for l in body.splitlines() if not l.startswith(">")).strip()


def is_auto_reply(msg, subject):
    """Whether a mail app sent this by itself (out of office, holiday, auto-response),
    going by the headers it marks such mail with and its subject. The words of the
    reply are not used: a person can write "on leave" in a real reply."""
    auto = (msg.get("Auto-Submitted") or "no").strip().lower()
    if auto != "no":
        return True
    if any(msg.get(h) for h in ("X-Autoreply", "X-Autorespond", "X-Autoresponse")):
        return True
    if (msg.get("Precedence") or "").strip().lower() == "auto_reply":
        return True
    return bool(AUTO_SUBJECT.search(subject))


def status_after(current, label):
    """A lead's status after a reply with this label, or None to leave it as it is. Only
    replies change status here; the dashboard can still set any status by hand.
      - unsubscribe: always unsubscribed, whatever the lead's status (an opt-out is absolute)
      - out_of_office: no change; nobody has answered yet, so the lead still counts as
        waiting for a reply (and for a follow-up)
      - bounce: bounced, except for a lead already at meeting or client, or unsubscribed
      - anything else: replied, but only from new, verified or sent, so a lead at meeting
        or client never drops back to replied when it writes again"""
    if label == "unsubscribe":
        return "unsubscribed"
    if label == "out_of_office":
        return None
    if label == "bounce":
        return None if current in ("meeting", "client", "unsubscribed") else "bounced"
    return "replied" if current in ("new", "verified", "sent") else None


def send_alerts():
    """Send the Telegram alerts waiting in the queue, oldest first. One that fails stays
    queued and is tried again at the next check, so an alert is never lost to a network
    error. Returns how many were sent."""
    sent = 0
    for alert in db.pending_alerts():
        try:
            notify.send(alert["text"])
        except Exception as e:
            db.alert_failed(alert["id"], str(e))
            print(f"  Telegram alert not sent ({e}); will try again next check.")
            break  # Telegram is down or unreachable: the rest wait too
        db.alert_sent(alert["id"])
        sent += 1
    return sent


def thread_lead(headers):
    """The lead one of our emails went to, if this message answers it (In-Reply-To / References)."""
    ids = re.findall(r"<[^>]+>", f"{headers.get('In-Reply-To', '')} {headers.get('References', '')}")
    return db.lead_by_message_ids(ids)


def colleague_leads(sender):
    """Leads at the sender's company: same email domain, never a free-mail one like gmail.com."""
    domain = sender.rsplit("@", 1)[-1]
    if not domain or domain in ranking.FREE_MAIL:
        return []
    return db.leads_on_domain(domain)


def since_first_send():
    """IMAP date the day before our first email, or None if nothing was sent yet."""
    first = db.first_sent_date()
    if not first:
        return None
    d = date.fromisoformat(first) - timedelta(days=1)
    return f"{d.day:02d}-{MONTHS[d.month - 1]}-{d.year}"


def find_original_recipient(msg):
    """For bounces, the failed address is inside the message body."""
    raw = msg.as_string()
    m = re.search(r"Final-Recipient:.*?;\s*([^\s]+@[^\s]+)", raw, re.I)
    return m.group(1).lower() if m else None


def check_once():
    """Reads mail from leads, replies to our emails from anyone (matched by In-Reply-To),
    bounces of our own emails, and unsubscribe requests from a lead's colleagues (same
    company domain). Read and unread mail alike, since our first send: each message is
    handled once, then remembered. Everything else is skipped: never downloaded in full,
    never sent to the AI, and left unread exactly as it was."""
    send_alerts()  # alerts left over from a check when Telegram was unreachable
    box = imaplib.IMAP4_SSL(config.IMAP_HOST)
    box.login(config.IMAP_USER, config.IMAP_PASS)
    box.select("INBOX")
    since = since_first_send()
    uids = box.uid("search", None, "SINCE", since)[1][0].split() if since else []
    handled = 0
    skipped, newly_skipped = db.skipped_uids(), []
    for uid in uids:
        uid_s = uid.decode()
        if uid_s in skipped or db.reply_seen(uid_s):
            continue
        # Look at the headers only. BODY.PEEK never marks the mail as read.
        _, head = box.uid("fetch", uid, "(BODY.PEEK[HEADER.FIELDS (FROM IN-REPLY-TO REFERENCES)])")
        if not head or not isinstance(head[0], tuple):
            continue
        headers = email.message_from_bytes(head[0][1])
        sender = parseaddr(headers.get("From", ""))[1].lower()
        is_bounce = sender.startswith(BOUNCE_SENDERS)
        lead = db.find_lead_by_email(sender) or (None if is_bounce else thread_lead(headers))
        colleagues = [] if lead or is_bounce else colleague_leads(sender)
        if not lead and not is_bounce and not colleagues:
            newly_skipped.append(uid_s)  # not a lead: leave it alone
            continue

        _, msg_data = box.uid("fetch", uid, "(BODY.PEEK[])")
        msg = email.message_from_bytes(msg_data[0][1])
        subject = str(make_header(decode_header(msg.get("Subject", ""))))
        body = text_of(msg)

        if colleagues:
            # Someone else at a lead's company, not answering one of our emails. Only an
            # unsubscribe request is acted on, by the rules alone: never sent to the AI.
            if classifier.quick_rules(f"Subject: {subject}\n\n{body}") != "unsubscribe":
                newly_skipped.append(uid_s)
                continue
            lead = colleagues[0]
            result = {"label": "unsubscribe",
                      "summary": f"{sender} asked to unsubscribe {sender.rsplit('@', 1)[-1]}"}
        elif is_bounce:
            failed = find_original_recipient(msg)
            lead = db.find_lead_by_email(failed) if failed else None
            if not lead:
                newly_skipped.append(uid_s)  # a bounce of some other email, not ours
                continue
            # "Delayed Mail" warnings mean the server is still retrying: not a bounce
            action = re.search(r"^Action:\s*(\w+)", msg.as_string(), re.I | re.M)
            if action and action.group(1).lower() != "failed":
                newly_skipped.append(uid_s)
                continue
            result = {"label": "bounce", "summary": f"delivery to {failed} failed"}
        elif is_auto_reply(msg, subject):
            result = {"label": "out_of_office", "summary": "automatic reply"}
        else:
            result = classifier.classify(f"Subject: {subject}\n\n{body}")
        label = result["label"]

        reply_id = db.add_reply(lead["id"], sender, subject, body, label, result["summary"], uid_s)
        if not reply_id:
            continue  # stored by an earlier check: nothing is logged or alerted twice
        for each in colleagues or [lead]:  # a colleague's opt-out covers every lead at that company
            new_status = status_after(each["status"], label)
            if new_status:
                db.set_status(each["id"], new_status, "inbox")
        if label == "unsubscribe" and sender != lead["email"]:
            db.unsubscribe(sender)  # the person who asked is never emailed or added either

        if label in ALERT_ON:
            # Queued, then sent after the loop: a Telegram error can't stop the check
            db.queue_alert(reply_id, notify.alert_text(lead, sender, subject, label, result["summary"], body))
            box.uid("store", uid, "+FLAGS", "(\\Seen)")  # the alert is on its way
        print(f"  {label:15} {sender}  {result['summary']}")
        handled += 1

    db.add_skipped(newly_skipped)
    box.logout()
    # Heartbeat for the dashboard: when the inbox was last checked
    (Path(__file__).parent / "last_check.txt").write_text(datetime.now().isoformat(timespec="seconds"))
    send_alerts()
    return handled


def watch():
    print(f"Watching inbox every {config.POLL_MINUTES} min. Ctrl+C to stop.")
    while True:
        try:
            n = check_once()
            if n:
                print(f"Handled {n} replies.")
        except Exception as e:
            print(f"Inbox check failed: {e}")
        time.sleep(config.POLL_MINUTES * 60)
