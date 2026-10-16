"""Sends intro emails to verified leads, respecting the daily limit.
Every email that goes out is also filed in the mailbox's Sent folder."""
import html
import imaplib
import re
import smtplib
import time
from email.message import EmailMessage
from email.utils import formatdate, make_msgid, formataddr
from pathlib import Path

import config
import db
import personalise
import ranking

TEMPLATE_DIR = Path(__file__).parent / "templates"
MAX_PDF_BYTES = 1024 * 1024
ATTACHMENT_LINE = "I've attached a one-page overview of TalkSasa."
# Tried in this order when the server doesn't flag a folder as \Sent
SENT_NAMES = ("Sent", "Sent Items", "Sent Messages", "Sent Mail", "INBOX.Sent",
              "INBOX.Sent Items", "INBOX.Sent Messages", "INBOX/Sent", "[Gmail]/Sent Mail")
# What the website line reads as. In the HTML email it is a link to config.WEBSITE
WEBSITE_LABEL = "TalkSasa"
_warned = set()
_sent_folder = None  # found once per run


def _warn(text):
    if text not in _warned:  # once per run, not once per email
        _warned.add(text)
        print(f"WARNING: {text}")


def attachment():
    """The PDF to attach, or None. Warns if it is missing or over 1MB."""
    if not config.ATTACH_PDF:
        return None
    path = Path(config.ATTACH_PDF)
    if not path.is_absolute():
        path = Path(__file__).parent / path
    if not path.is_file():
        _warn(f"ATTACH_PDF file not found: {path}. Sending without an attachment.")
        return None
    size = path.stat().st_size
    if size > MAX_PDF_BYTES:
        _warn(f"{path.name} is {size / MAX_PDF_BYTES:.1f}MB (over 1MB). "
              "Large attachments are more likely to land in spam.")
    return path


def load_template(industry):
    """Use templates/<industry>.txt if it exists, otherwise templates/default.txt.
    First line is the subject, the rest is the body. The body is fixed text apart from
    {opener} and {uses}, which personalise.py fills for each lead."""
    name = (industry or "default").lower().replace(" ", "_")
    path = TEMPLATE_DIR / f"{name}.txt"
    if not path.exists():
        path, name = TEMPLATE_DIR / "default.txt", "default"
    subject, body = path.read_text(encoding="utf-8").split("\n", 1)
    return name, subject.replace("Subject:", "").strip(), body.strip()


def fill(text, lead, attached=False, for_html=False):
    return text.format(
        opener=personalise.opener(lead),
        uses=personalise.uses(lead),
        company=lead["company"] or "your organisation",
        industry=lead["industry"] or "",
        sender=config.SENDER_NAME,
        our_company=config.COMPANY,
        phone=config.SENDER_PHONE,
        # plain text shows the name only; the HTML version turns the address into a link
        website=config.WEBSITE if for_html else WEBSITE_LABEL,
        profile_url=config.PROFILE_URL,
        # own paragraph before the sign-off; empty when nothing is attached
        attachment_line=ATTACHMENT_LINE if attached else "",
        # whole signature line; empty when PROFILE_URL is not set
        profile_line=f"Company profile: {config.PROFILE_URL}" if config.PROFILE_URL else "",
    )


def _link(m):
    """Our own website reads as WEBSITE_LABEL; any other link shows its address."""
    url = m.group(0)
    ours = url.rstrip("/") == html.escape(config.WEBSITE, quote=False).rstrip("/")
    return f'<a href="{url}">{WEBSITE_LABEL if ours else url}</a>'


def to_html(text):
    """A plain copy of the text: paragraphs and clickable links, nothing else,
    so it reads like a normal personal email."""
    paras = []
    for block in re.split(r"\n\s*\n", text.strip()):
        block = html.escape(block, quote=False)
        block = re.sub(r"https?://[^\s<]+[^\s<.,;:!?)]", _link, block)
        paras.append("<p>" + block.replace("\n", "<br>\n") + "</p>")
    unsubscribe = (f"mailto:{config.FROM_EMAIL}?subject=unsubscribe"
                   "&amp;body=Please%20unsubscribe%20me")
    paras.append(f"<p>--<br>\nIf you'd rather not hear from us, "
                 f'<a href="{unsubscribe}">click here to unsubscribe</a>.</p>')
    return "<html><body>\n" + "\n".join(paras) + "\n</body></html>"


def build(lead):
    tname, subject, body = load_template(lead["industry"])
    pdf = attachment()
    def tidy(t):
        return re.sub(r"\n{3,}", "\n\n", t.rstrip())  # close the gap left by an empty placeholder line
    text = tidy(fill(body, lead, attached=bool(pdf)))
    html_body = to_html(tidy(fill(body, lead, attached=bool(pdf), for_html=True)))
    body = text + (
        "\n\n--\nIf you'd rather not hear from us, just reply \"unsubscribe\" "
        "and we won't email you again."
    )
    msg = EmailMessage()
    msg["From"] = formataddr((config.FROM_NAME, config.FROM_EMAIL))
    msg["To"] = lead["email"]
    msg["Subject"] = fill(subject, lead)
    msg["Date"] = formatdate(localtime=True)
    msg["Message-ID"] = make_msgid(domain=config.FROM_EMAIL.split("@")[1])
    msg["List-Unsubscribe"] = f"<mailto:{config.FROM_EMAIL}?subject=unsubscribe>"
    msg.set_content(body)
    msg.add_alternative(html_body, subtype="html")
    if pdf:  # turns the message into multipart/mixed: (plain + HTML) + PDF
        msg.add_attachment(pdf.read_bytes(), maintype="application", subtype="pdf", filename=pdf.name)
    return msg, tname


def _folders(box):
    """Every folder on the server as (flags, name)."""
    typ, data = box.list()
    if typ != "OK":
        raise imaplib.IMAP4.error(f"LIST failed: {data}")
    out = []
    for item in data:
        if isinstance(item, tuple):  # name sent as a literal
            head, name = item[0], item[1]
        elif item:
            m = re.match(rb'(\(.*?\)) (?:"[^"]*"|NIL) (.*)', item)
            if not m:
                continue
            head, name = m.group(1), m.group(2).strip()
            if name.startswith(b'"') and name.endswith(b'"'):
                name = name[1:-1].replace(b'\\"', b'"').replace(b"\\\\", b"\\")
        else:
            continue
        flags = re.search(rb"\((.*?)\)", head)
        out.append((flags.group(1).decode().lower().split() if flags else [],
                    name.decode("utf-8", "replace")))
    return out


def find_sent_folder(box):
    """The folder flagged \\Sent, otherwise the first of SENT_NAMES that exists."""
    global _sent_folder
    if _sent_folder:
        return _sent_folder
    folders = _folders(box)
    found = next((name for flags, name in folders if "\\sent" in flags), None)
    how = "flagged \\Sent by the server"
    if not found:
        by_lower = {name.lower(): name for _, name in folders}
        found = next((by_lower[n.lower()] for n in SENT_NAMES if n.lower() in by_lower), None)
        how = "matched by name"
    if not found:
        raise LookupError("no Sent folder found. Folders: " + ", ".join(n for _, n in folders))
    print(f"Sent folder: {found} ({how})")
    _sent_folder = found
    return found


def wire_bytes(msg):
    """The message exactly as SMTP sends it."""
    return msg.as_bytes(policy=msg.policy.clone(linesep="\r\n"))


def save_to_sent(msg, sent_at):
    """File a copy of a sent email in the Sent folder, marked read.
    A failure here is only a warning: the email has already gone out."""
    try:
        box = imaplib.IMAP4_SSL(config.IMAP_HOST)
        try:
            box.login(config.IMAP_USER, config.IMAP_PASS)
            folder = find_sent_folder(box)
            quoted = '"' + folder.replace("\\", "\\\\").replace('"', '\\"') + '"'
            typ, data = box.append(quoted, "\\Seen", imaplib.Time2Internaldate(sent_at),
                                   wire_bytes(msg))
            if typ != "OK":
                raise imaplib.IMAP4.error(f"APPEND refused: {data}")
        finally:
            try:
                box.logout()
            except Exception:
                pass
        return True
    except Exception as e:
        print(f"WARNING: email to {msg['To']} was sent, but could not be saved "
              f"to the Sent folder: {e}")
        return False


def deliver(smtp, lead, msg, tname):
    """Send one email, record exactly what went out, and file it in Sent.
    Every send (first email or follow-up) goes through here, so this is also where a
    second email to the same lead is refused until follow-ups are approved."""
    if not personalise.approved(lead):
        raise RuntimeError(f"{lead['email']}: industry {lead['industry'] or 'default'!r} is not approved in uses.yaml")
    if lead["id"] in db.emailed_lead_ids() and not config.FOLLOWUPS_APPROVED:
        raise RuntimeError(f"{lead['email']} has already been emailed and follow-ups are not approved "
                           "(FOLLOWUPS_APPROVED in .env)")
    smtp.send_message(msg)
    sent_at = time.time()
    variant = "personal" if personalise.picked_uses(lead) else "template"
    db.record_sent(lead["id"], msg["Message-ID"], tname, str(msg["Subject"]), plain_of(msg), variant)
    save_to_sent(msg, sent_at)


def plain_of(msg):
    return msg.get_body(("plain",)).get_content()


def html_of(msg):
    return msg.get_body(("html",)).get_content()


def personal_lines(lead):
    """What previews say about the opener and uses for one lead."""
    return personalise.notes(lead)


def preview(industry=None, limit=1):
    """Show the plain and HTML versions of an email for the next `limit` verified
    leads (or an example lead for one industry). Nothing is sent."""
    leads = ranking.waiting()[:limit]
    if industry or not leads:
        leads = [{"company": "Example Company", "industry": industry or "", "email": "info@example.co.ke"}]
    line = "=" * 60
    for lead in leads:
        msg, tname = build(lead)
        print(f"{line}\nTemplate: {tname}\nFrom: {msg['From']}\nTo: {msg['To']}\nSubject: {msg['Subject']}")
        print(personal_lines(lead))
        print(f"{line}\nPLAIN TEXT VERSION\n{line}\n{plain_of(msg)}")
        print(f"{line}\nHTML VERSION\n{line}\n{html_of(msg)}")
        files = [f"{p.get_filename()} ({p.get_content_type()}, {len(p.get_payload(decode=True)) // 1024} KB)"
                 for p in msg.iter_attachments()]
        print(f"{line}\nATTACHMENTS: {', '.join(files) or 'none'}")


def _cut(text, width):
    text = text or ""
    return text if len(text) <= width else text[:width - 1] + "…"


def sent_log(days=None):
    """List what was sent: date, company, email, step, subject."""
    rows = db.sent_log(days)
    if not rows:
        print("Nothing sent" + (f" in the last {days} days." if days else " yet."))
        return
    print(f"{'DATE':10}  {'COMPANY':28}  {'EMAIL':36}  STEP  SUBJECT")
    for r in rows:
        print(f"{r['sent_on']:10}  {_cut(r['company'], 28):28}  {_cut(r['email'], 36):36}  "
              f"{r['step']:>4}  {r['sent_subject'] or '(not recorded)'}")
    print(f"{len(rows)} emails.")


def show_sent(email):
    """Print the full text of every email sent to one address."""
    rows = db.sent_to(email)
    if not rows:
        print(f"Nothing has been sent to {email}.")
        return
    line = "=" * 60
    for r in rows:
        print(f"{line}\nDate: {r['sent_on']}\nTo: {r['company']} <{r['email']}>\n"
              f"Step: {r['step']}\nTemplate: {r['template']}\nMessage-ID: {r['message_id']}\n"
              f"Subject: {r['sent_subject'] or '(not recorded)'}\n{line}")
        print(r["sent_body"] or "(The text of this email was not recorded. "
                                "It was sent before LeadBot kept copies.)")


def approved_waiting(quiet=False):
    """Waiting leads whose industry is approved in uses.yaml, in sending order. The rest
    are skipped and left exactly as they are, so they go out once their industry is approved."""
    waiting = ranking.waiting()
    leads = [l for l in waiting if personalise.approved(l)]
    if len(leads) < len(waiting) and not quiet:
        skipped = sorted({personalise.industry_key(l) for l in waiting if not personalise.approved(l)})
        print(f"Skipped {len(waiting) - len(leads)} waiting leads in industries not approved "
              f"in uses.yaml: {', '.join(skipped)}")
    return leads


def run(dry_run=False):
    remaining = config.DAILY_LIMIT - db.sent_today()
    if remaining <= 0:
        print(f"Daily limit of {config.DAILY_LIMIT} reached. Try again tomorrow.")
        return
    # Highest-scoring leads first (younger companies, busy niches, own-domain email),
    # then oldest-found first. Start years are needed for every waiting lead to rank them.
    ranking.fill_years()
    leads = approved_waiting()[:remaining]
    if not leads:
        print("No verified leads waiting in an approved industry.")
        return
    # Write personal lines for any of today's leads that don't have them yet
    if personalise.run(leads) or any(l["confidence"] is None for l in leads):
        leads = approved_waiting(quiet=True)[:remaining]

    if dry_run:
        for lead in leads[:3]:
            msg, _ = build(lead)
            print("=" * 60, f"\nTo: {msg['To']}\nSubject: {msg['Subject']}\n{personal_lines(lead)}"
                  f"\n\n{plain_of(msg)}")
        print(f"\n(dry run) would send {len(leads)} emails.")
        return

    with smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT) as s:
        s.starttls()
        s.login(config.SMTP_USER, config.SMTP_PASS)
        for i, lead in enumerate(leads, 1):
            msg, tname = build(lead)
            try:
                deliver(s, lead, msg, tname)
            except smtplib.SMTPRecipientsRefused:
                db.set_status(lead["id"], "bounced", "send")
                continue
            db.set_status(lead["id"], "sent", "send")
            print(f"[{i}/{len(leads)}] sent to {lead['email']}")
            if i < len(leads):
                time.sleep(config.SEND_DELAY_SECONDS)
