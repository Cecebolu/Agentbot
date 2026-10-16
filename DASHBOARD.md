# LeadBot dashboard

A web dashboard for LeadBot. It reads the same `leads.db` as the bot.

## Install (inside the leadbot folder)

1. Copy `web.py` and the `static/` folder into your `leadbot` folder.
2. Install and run:

```bash
source venv/bin/activate
pip install fastapi uvicorn
uvicorn web:app --host 127.0.0.1 --port 8000
```

3. Open http://localhost:8000 in your browser.

`--host 127.0.0.1` keeps the dashboard reachable from this computer only. It has no password, so don't start it with `--host 0.0.0.0`.

If the page says "Example data", the API isn't running or the page was opened as a file. Open it through http://localhost:8000.

## What it shows

- **Overview**: replies waiting for you, emails sent, reply rate, interested rate, bounce rate (healthy under 2%), a 30-day chart, the lead pipeline and results by niche.
- **Replies**: every reply with its AI label and summary. Mark replies as handled, or record "Meeting set" or "Became a client".
- **Leads**: search and filter every lead by niche and status.

## Database changes

The first run adds one column, `replies.handled`, and leaves everything else alone.
"Meeting set" and "Became a client" set the lead status to `meeting` or `client`. Follow-ups only go to leads with status `sent`, so these leads stop getting follow-ups.

## Bot status in the sidebar

The sidebar shows when the bot last checked your inbox. For that, `inbox.check_once()` needs to write a timestamp file. Tell Claude Code:

> At the end of check_once() in inbox.py, write the current time to last_check.txt in the project folder (Path(__file__).parent / "last_check.txt").

## Run it alongside the bot

In tmux, open a second window (Ctrl+B then C) and run `uvicorn web:app --host 127.0.0.1 --port 8000` there, so the bot and the dashboard both keep running.
