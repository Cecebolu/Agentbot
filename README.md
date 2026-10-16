# LeadBot — bulk SMS outreach

Finds company emails, sends intro emails in small daily batches, reads replies, labels them with AI, and pings you on Telegram when someone is interested.

```
companies.csv → scrape → verify → send → inbox (AI label) → Telegram alert
```

## Setup (30 min)

```bash
python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env              # then fill it in
python main.py init
```

**AI option A — Ollama (free, open source, local):** install from ollama.com, then `ollama pull qwen2.5:7b`. Set `AI_PROVIDER=ollama`.
**AI option B — Groq (free tier, no big PC needed):** get a key at console.groq.com. Set `AI_PROVIDER=groq` and `GROQ_API_KEY`.

**Telegram:** see the steps at the top of `notify.py`, then test with `python notify.py`.

**Test the AI:** `python classifier.py` runs 5 sample replies (including Swahili) and prints the labels.

## Daily use

```bash
python main.py scrape companies.csv   # add leads from your own list
python main.py discover sacco --max 5 # or find leads by web search (see discover.py)
python main.py verify                 # drop dead domains
python main.py send --dry-run         # read 3 sample emails first
python main.py preview                # one email, plain and HTML versions
python main.py send                   # send today's batch (DAILY_LIMIT)
python main.py watch                  # leave running; alerts you on replies
python main.py stats
python main.py export                 # leads.csv, events.csv, replies.csv (join on lead_id)
python main.py auto                   # or leave this running: does all of the above on weekdays at 9am
streamlit run dashboard.py            # optional dashboard
```

To run unattended on Linux, add to crontab:
```
0 9 * * 1-5  cd /path/to/leadbot && venv/bin/python main.py send
*/5 * * * *  cd /path/to/leadbot && venv/bin/python main.py inbox
```

## Templates

`templates/<industry>.txt` is used when a lead's `industry` matches (e.g. `sacco`, `school`). Otherwise `default.txt`. The subject is the template's own fixed `Subject:` line. Only industries marked `approved: true` in `uses.yaml` are emailed; leads in other industries are skipped and stay waiting. With `USE_AI_OPENER=false` in `.env` (the default) emails are templates only: no opener, and `{uses}` is the first three uses for the industry in `uses.yaml`. With `true`, the body has two AI slots: `{opener}` (one sentence, at most 20 words, saying what the lead does in our own words; left out when there is no good one, so the email starts with "I'm Florence from TalkSasa Communications in Nairobi.") and `{uses}` (picked from that industry's approved list in `uses.yaml`, never invented). Other placeholders: `{company} {sender} {our_company} {phone} {website} {profile_line} {attachment_line}` (`{profile_line}` is "Company profile: <PROFILE_URL>", or nothing if `PROFILE_URL` is empty).

## Getting leads (companies.csv)

Columns: `company,website,industry,email`. Leave `email` blank to have it scraped. Good public sources: SASRA licensed SACCO list, Ministry of Education school lists, Kenya Yellow Pages, chamber of commerce and trade association member lists. Skip LinkedIn and Google Maps scraping (against their terms).

## Before the first real send

- [ ] Separate outreach domain (not talksasa.co.ke), so spam flags can't hurt the main domain
- [ ] SPF, DKIM and DMARC records set on that domain (check at mail-tester.com, aim for 9/10+)
- [ ] Send a few test emails to your own Gmail and check they land in Inbox, not Spam
- [ ] Start at `DAILY_LIMIT=20–25`, raise by ~10/day each week if bounces stay under 3%
- [ ] Confirm with your boss whether TalkSasa needs ODPC registration for this

## What each label does

| Label | Lead status | Alert you? |
|---|---|---|
| interested | replied | 🔥 yes |
| question | replied | ❓ yes |
| needs_review | replied | no (stays unread in inbox) |
| not_interested | replied | no (stays unread in inbox) |
| out_of_office | replied | no |
| unsubscribe | unsubscribed, never emailed again | no |
| bounce | bounced | no |
