"""SQLite storage for leads, sent emails, replies and the history of each lead."""
import csv
import json
import sqlite3
from datetime import date
from pathlib import Path

import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS leads (
    id INTEGER PRIMARY KEY,
    company TEXT,
    website TEXT,
    industry TEXT,
    email TEXT UNIQUE,
    status TEXT DEFAULT 'new',
    -- new -> verified / invalid -> sent -> replied / bounced / unsubscribed
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    -- the AI's two slots in the email (see personalise.py): opener is its sentence about
    -- the lead's website, uses is a JSON list picked from uses.yaml. confidence is NULL
    -- until that has been tried, then 1 if the opener is usable and 0 if the fallback is used.
    -- use_case and subject_topic are from the older way of writing emails and no longer used.
    opener TEXT,
    use_case TEXT,
    subject_topic TEXT,
    uses TEXT,
    confidence REAL,
    -- year the company started, estimated for ranking (see ranking.py);
    -- est_year_source is 'site', 'whois' or 'unknown', NULL until it has been tried
    est_year INTEGER,
    est_year_source TEXT,
    -- where the lead came from: source is 'search', 'csv' or 'manual'
    source TEXT,
    source_query TEXT,
    source_url TEXT,
    discovered_at TEXT,
    -- when the status first became meeting / client
    meeting_at TEXT,
    client_at TEXT,
    -- ranking score as last calculated (see ranking.py); score_reasons is JSON
    score INTEGER,
    score_reasons TEXT,
    score_version INTEGER
);
CREATE TABLE IF NOT EXISTS sent (
    id INTEGER PRIMARY KEY,
    lead_id INTEGER REFERENCES leads(id),
    message_id TEXT,
    template TEXT,
    sent_on TEXT DEFAULT (date('now')),
    -- exactly what went out: the subject and the plain-text body
    sent_subject TEXT,
    sent_body TEXT
);
CREATE TABLE IF NOT EXISTS replies (
    id INTEGER PRIMARY KEY,
    lead_id INTEGER REFERENCES leads(id),
    from_email TEXT,
    subject TEXT,
    body TEXT,
    label TEXT,
    summary TEXT,
    imap_uid TEXT UNIQUE,
    received_at TEXT DEFAULT CURRENT_TIMESTAMP
);
-- mail that isn't from a lead, so the inbox check doesn't look at it again
CREATE TABLE IF NOT EXISTS skipped (
    imap_uid TEXT PRIMARY KEY
);
-- everything that happens to a lead, one row each; detail is JSON
CREATE TABLE IF NOT EXISTS lead_events (
    id INTEGER PRIMARY KEY,
    lead_id INTEGER REFERENCES leads(id),
    event_type TEXT,
    -- discovered, verified, invalid, email_sent, bounced, replied, unsubscribed, status_changed
    detail TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS lead_events_lead ON lead_events (lead_id);
-- addresses that must never be emailed or added again (unsubscribes and bounces)
CREATE TABLE IF NOT EXISTS suppression (
    email TEXT PRIMARY KEY,
    domain TEXT,
    reason TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
-- Telegram alerts waiting to go out; sent_at stays NULL until Telegram accepts one,
-- so an alert that fails is sent at a later inbox check instead of being lost
CREATE TABLE IF NOT EXISTS alert_outbox (
    id INTEGER PRIMARY KEY,
    reply_id INTEGER UNIQUE REFERENCES replies(id),
    text TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    sent_at TEXT,
    attempts INTEGER DEFAULT 0,
    last_error TEXT
);
"""

def conn():
    c = sqlite3.connect(config.DB_PATH)
    c.row_factory = sqlite3.Row
    return c

def init():
    with conn() as c:
        c.executescript(SCHEMA)
        # Databases made before these columns existed: add them, leave the rows alone
        for table, col, kind in (("sent", "sent_subject", "TEXT"), ("sent", "sent_body", "TEXT"),
                                 ("leads", "opener", "TEXT"), ("leads", "use_case", "TEXT"), ("leads", "subject_topic", "TEXT"),
                                 ("leads", "uses", "TEXT"),
                                 ("leads", "confidence", "REAL"), ("leads", "est_year", "INTEGER"),
                                 ("leads", "est_year_source", "TEXT"),
                                 ("leads", "source", "TEXT"), ("leads", "source_query", "TEXT"),
                                 ("leads", "source_url", "TEXT"), ("leads", "discovered_at", "TEXT"),
                                 ("leads", "meeting_at", "TEXT"), ("leads", "client_at", "TEXT"),
                                 ("leads", "score", "INTEGER"), ("leads", "score_reasons", "TEXT"),
                                 ("leads", "score_version", "INTEGER")):
            if col not in {r["name"] for r in c.execute(f"PRAGMA table_info({table})")}:
                c.execute(f"ALTER TABLE {table} ADD COLUMN {col} {kind}")
        # Leads from before these existed
        c.execute("UPDATE leads SET discovered_at=created_at WHERE discovered_at IS NULL")
        for lead in c.execute("SELECT email, status FROM leads WHERE status IN ('bounced','unsubscribed')").fetchall():
            _suppress(c, lead["email"], lead["status"])

def log_event(c, lead_id, event_type, **detail):
    """Add a row to lead_events on connection c. Empty details are left out."""
    detail = {k: v for k, v in detail.items() if v is not None}
    c.execute("INSERT INTO lead_events (lead_id, event_type, detail) VALUES (?,?,?)",
              (lead_id, event_type, json.dumps(detail, ensure_ascii=False) if detail else None))

def _suppress(c, email, reason):
    email = email.lower().strip()
    c.execute("INSERT OR IGNORE INTO suppression (email, domain, reason) VALUES (?,?,?)",
              (email, email.rsplit("@", 1)[-1], reason))

def is_suppressed(email):
    with conn() as c:
        return c.execute("SELECT 1 FROM suppression WHERE email=?",
                         (email.lower().strip(),)).fetchone() is not None

def suppressed_emails():
    with conn() as c:
        return {r[0] for r in c.execute("SELECT email FROM suppression")}

def unsubscribe(email):
    """Opt an address out for good, whether or not it is a lead."""
    lead = find_lead_by_email(email.strip())
    if lead:
        set_status(lead["id"], "unsubscribed", "manual")
    with conn() as c:
        _suppress(c, email, "unsubscribed")

def add_lead(company, website, industry, email, source=None, source_query=None, source_url=None):
    """Returns True if the lead is new. An address on the suppression list is never added."""
    email = email.lower().strip()
    with conn() as c:
        if c.execute("SELECT 1 FROM suppression WHERE email=?", (email,)).fetchone():
            return False
        cur = c.execute(
            "INSERT OR IGNORE INTO leads (company, website, industry, email, source, source_query,"
            " source_url, discovered_at) VALUES (?,?,?,?,?,?,?,CURRENT_TIMESTAMP)",
            (company, website, industry, email, source, source_query, source_url),
        )
        if cur.rowcount != 1:
            return False
        log_event(c, cur.lastrowid, "discovered", source=source, query=source_query, url=source_url)
        return True

def leads_by_status(status, limit=None):
    sql = "SELECT * FROM leads WHERE status=? ORDER BY id"
    if limit:
        sql += f" LIMIT {int(limit)}"
    with conn() as c:
        return c.execute(sql, (status,)).fetchall()

def leads_to_personalise(limit=None):
    sql = "SELECT * FROM leads WHERE status='verified' AND confidence IS NULL ORDER BY id"
    if limit:
        sql += f" LIMIT {int(limit)}"
    with conn() as c:
        return c.execute(sql).fetchall()

def save_personalisation(lead_id, opener, uses, confidence):
    with conn() as c:
        c.execute("UPDATE leads SET opener=?, uses=?, confidence=? WHERE id=?",
                  (opener, uses, confidence, lead_id))

def save_est_year(lead_id, year, source):
    with conn() as c:
        c.execute("UPDATE leads SET est_year=?, est_year_source=? WHERE id=?", (year, source, lead_id))

def set_status(lead_id, status, by=None):
    """Change a lead's status and log it. `by` says what did it (verify, send, inbox,
    dashboard, manual). Returns False if there is no such lead."""
    with conn() as c:
        lead = c.execute("SELECT email, status FROM leads WHERE id=?", (lead_id,)).fetchone()
        if not lead:
            return False
        old = lead["status"]
        if old == status:
            return True
        c.execute("UPDATE leads SET status=? WHERE id=?", (status, lead_id))
        if status in ("meeting", "client"):
            c.execute(f"UPDATE leads SET {status}_at=COALESCE({status}_at, CURRENT_TIMESTAMP) WHERE id=?",
                      (lead_id,))
        if status in ("verified", "invalid", "bounced", "unsubscribed"):
            log_event(c, lead_id, status, by=by)
        log_event(c, lead_id, "status_changed", old=old, new=status, by=by)
        if status in ("bounced", "unsubscribed"):
            _suppress(c, lead["email"], status)
    return True

def find_lead_by_email(email):
    with conn() as c:
        return c.execute("SELECT * FROM leads WHERE email=?", (email.lower(),)).fetchone()

def record_sent(lead_id, message_id, template, subject=None, body=None, subject_variant=None):
    with conn() as c:
        cur = c.execute("INSERT INTO sent (lead_id, message_id, template, sent_subject, sent_body)"
                        " VALUES (?,?,?,?,?)",
                        (lead_id, message_id, template, subject, body))
        step = c.execute("SELECT COUNT(*) FROM sent WHERE lead_id=?", (lead_id,)).fetchone()[0]
        # the campaign is the niche template the email was built from
        log_event(c, lead_id, "email_sent", sent_id=cur.lastrowid, step=step, subject=subject,
                  subject_variant=subject_variant, campaign=template)

# step = 1 for the first email to a lead, 2 for the first follow-up, and so on
SENT_LOG = """
SELECT s.id, s.sent_on, s.message_id, s.template, s.sent_subject, s.sent_body,
       l.company, l.email,
       ROW_NUMBER() OVER (PARTITION BY s.lead_id ORDER BY s.id) AS step
FROM sent s LEFT JOIN leads l ON l.id = s.lead_id
"""

def sent_log(days=None):
    sql, args = f"SELECT * FROM ({SENT_LOG})", ()
    if days:
        sql += " WHERE sent_on >= date('now', ?)"
        args = (f"-{int(days) - 1} days",)
    with conn() as c:
        return c.execute(sql + " ORDER BY id", args).fetchall()

def sent_to(email):
    with conn() as c:
        return c.execute(f"SELECT * FROM ({SENT_LOG}) WHERE email=? ORDER BY id",
                         (email.lower().strip(),)).fetchall()

def lead_by_message_ids(ids):
    """The lead one of our emails went to, by that email's Message-ID, or None."""
    if not ids:
        return None
    with conn() as c:
        return c.execute("SELECT l.* FROM sent s JOIN leads l ON l.id = s.lead_id"
                         f" WHERE s.message_id IN ({','.join('?' * len(ids))}) ORDER BY s.id DESC LIMIT 1",
                         ids).fetchone()

def leads_on_domain(domain):
    with conn() as c:
        return c.execute("SELECT * FROM leads WHERE lower(substr(email, instr(email, '@') + 1)) = ?"
                         " ORDER BY id", (domain.lower(),)).fetchall()

def bounce_stats(days):
    """(companies emailed, how many of them bounced), for the companies first emailed in the
    last `days` days. A lead counts once, whether its email went out or its address was
    refused at sending; a bounce counts whenever it arrived. Leads added by hand (test
    leads) are left out."""
    with conn() as c:
        rows = c.execute(f"""
            SELECT e.lead_id,
                   EXISTS (SELECT 1 FROM lead_events b WHERE b.lead_id = e.lead_id AND b.event_type = 'bounced')
                       OR l.status = 'bounced' AS bounced
            FROM lead_events e JOIN leads l ON l.id = e.lead_id
            WHERE (e.event_type = 'email_sent'
                   OR (e.event_type = 'bounced' AND json_extract(e.detail, '$.by') = 'send'))
              AND {real('l')}
            GROUP BY e.lead_id HAVING MIN(e.created_at) >= datetime('now', ?)""",
                         (f"-{int(days)} days",)).fetchall()
    return len(rows), sum(r["bounced"] for r in rows)

def first_sent_date():
    with conn() as c:
        return c.execute("SELECT MIN(sent_on) FROM sent").fetchone()[0]

def sent_count(lead_id):
    with conn() as c:
        return c.execute("SELECT COUNT(*) FROM sent WHERE lead_id=?", (lead_id,)).fetchone()[0]

def awaiting_followup():
    """Leads still at 'sent' that have had exactly one email, oldest send first. Each row is
    the lead plus that email's sent_id, message_id, sent_subject and sent_on."""
    with conn() as c:
        return c.execute("""
            SELECT l.*, s.id AS sent_id, s.message_id, s.sent_subject, s.sent_on
            FROM leads l JOIN sent s ON s.lead_id = l.id
            WHERE l.status = 'sent' AND (SELECT COUNT(*) FROM sent s2 WHERE s2.lead_id = l.id) = 1
            ORDER BY s.id""").fetchall()

def recent_out_of_office(lead_id, days):
    """Whether an out-of-office reply from this lead arrived in the last `days` days."""
    with conn() as c:
        return c.execute("SELECT 1 FROM replies WHERE lead_id=? AND label='out_of_office'"
                         " AND received_at >= datetime('now', ?)", (lead_id, f"-{int(days)} days")).fetchone() is not None

def emailed_lead_ids():
    with conn() as c:
        return {r[0] for r in c.execute("SELECT DISTINCT lead_id FROM sent")}

def sent_today():
    with conn() as c:
        return c.execute("SELECT COUNT(*) FROM sent WHERE sent_on=?",
                         (date.today().isoformat(),)).fetchone()[0]

def reply_seen(uid):
    with conn() as c:
        return c.execute("SELECT 1 FROM replies WHERE imap_uid=?", (uid,)).fetchone() is not None

def queue_alert(reply_id, text):
    with conn() as c:
        c.execute("INSERT OR IGNORE INTO alert_outbox (reply_id, text) VALUES (?,?)", (reply_id, text))

def pending_alerts():
    with conn() as c:
        return c.execute("SELECT * FROM alert_outbox WHERE sent_at IS NULL ORDER BY id").fetchall()

def alert_sent(alert_id):
    with conn() as c:
        c.execute("UPDATE alert_outbox SET sent_at=CURRENT_TIMESTAMP, attempts=attempts+1 WHERE id=?",
                  (alert_id,))

def alert_failed(alert_id, error):
    with conn() as c:
        c.execute("UPDATE alert_outbox SET attempts=attempts+1, last_error=? WHERE id=?", (error, alert_id))

def add_reply(lead_id, from_email, subject, body, label, summary, uid):
    """Returns the new reply's id, or None if it is already stored (same imap_uid): that
    one is left alone and logs nothing, so checking the inbox again never repeats it."""
    with conn() as c:
        cur = c.execute(
            "INSERT OR IGNORE INTO replies (lead_id, from_email, subject, body, label, summary, imap_uid)"
            " VALUES (?,?,?,?,?,?,?)",
            (lead_id, from_email, subject, body, label, summary, uid),
        )
        if cur.rowcount != 1:
            return None
        log_event(c, lead_id, "replied", reply_id=cur.lastrowid, label=label)
        return cur.lastrowid

def skipped_uids():
    with conn() as c:
        return {r[0] for r in c.execute("SELECT imap_uid FROM skipped")}

def add_skipped(uids):
    with conn() as c:
        c.executemany("INSERT OR IGNORE INTO skipped (imap_uid) VALUES (?)", [(u,) for u in uids])

def real(alias=""):
    """SQL condition that leaves out leads added by hand (source 'manual': test leads).
    Used by stats and the dashboards only; sending and the daily limit still count them."""
    return f"COALESCE({alias + '.' if alias else ''}source, '') != 'manual'"

def stats():
    with conn() as c:
        rows = c.execute(f"SELECT status, COUNT(*) n FROM leads WHERE {real()} GROUP BY status").fetchall()
        labels = c.execute("SELECT r.label, COUNT(*) n FROM replies r LEFT JOIN leads l ON l.id = r.lead_id"
                           f" WHERE {real('l')} GROUP BY r.label").fetchall()
    return {r["status"]: r["n"] for r in rows}, {r["label"]: r["n"] for r in labels}

# file -> (table, what its id column is called in the file). Every file has lead_id to join on.
EXPORTS = {"leads.csv": ("leads", "lead_id"), "events.csv": ("lead_events", "event_id"),
           "replies.csv": ("replies", "reply_id")}

def export(folder="."):
    """Write leads.csv, events.csv and replies.csv. Returns {file: number of rows}."""
    counts = {}
    with conn() as c:
        for name, (table, id_name) in EXPORTS.items():
            cur = c.execute(f"SELECT * FROM {table} ORDER BY id")
            header = [id_name if d[0] == "id" else d[0] for d in cur.description]
            rows = cur.fetchall()
            with open(Path(folder) / name, "w", newline="", encoding="utf-8-sig") as f:
                w = csv.writer(f)
                w.writerow(header)
                w.writerows(tuple(r) for r in rows)
            counts[name] = len(rows)
    return counts
