# LeadBot Implementation — Checkpoint 1: Safe Foundation

We have completed the LeadBot audit. Use the audit report as the source of truth for the current architecture, defects and implementation roadmap.

Implement only the first checkpoint: project protection, test infrastructure, and a safe database migration foundation.

## Objectives

1. Establish a safe, reproducible baseline.
2. Protect existing lead, email, reply and suppression data.
3. Create a test suite that will allow us to fix the reply-handling defects without regressions.
4. Establish a numbered migration mechanism compatible with the existing SQLite database.
5. Do not redesign the UI or add new sales features yet.

## Step 1: Inspect and protect

- Inspect the current Git status, branch, tracked files and `.gitignore`.
- Never overwrite or discard existing user changes.
- Check whether `.env`, `leads.db`, backups, generated exports and `previews.txt` are excluded from Git.
- Ensure credentials, personal contact data and live databases cannot accidentally be committed.
- If the project has no Git repository, initialize one without overwriting existing configuration.
- Before creating a baseline commit, show me the proposed changes and confirm that no secrets or live data will be included.
- Create a verified backup of the existing SQLite database before any schema changes.
- Do not print secrets or include personal contact information in logs.

## Step 2: Establish automated tests

- Inspect the existing dependencies and test conventions.
- Add `pytest` and only the minimum necessary development dependencies.
- Create a `tests/` directory.
- Ensure tests use isolated temporary databases and mocked external services.
- Do not send real email, contact real prospects, call live AI services or send Telegram messages during tests.
- Add anonymized fixtures for:
  - A normal Gmail reply.
  - An Outlook reply quoting our unsubscribe footer.
  - An HTML-only interested reply.
  - A genuine unsubscribe.
  - An out-of-office reply.
  - An interested reply that mentions someone being away.
  - A delivery-status notification or bounce.
  - An unrecognized sender.
- Add initial regression tests for the known reply-classification failures from the audit.
- Do not change production behavior merely to make the tests pass.

## Step 3: Database migration foundation

- Inspect `db.py`, `web.py`, `web_extra.py` and all current schema initialization logic.
- Consolidate schema upgrades behind a single, numbered migration mechanism using SQLite `PRAGMA user_version`.
- Make migrations safe to rerun or detect when they have already been applied.
- Preserve existing tables, IDs, data and suppression records.
- Ensure a fresh database and a copy of the existing database can reach the same schema version.
- Do not delete, rebuild or silently reset the live database.
- Test upgrades against a copy of the real schema and a temporary fresh database.
- Do not yet implement all the new audit tables or change all timestamp semantics; those belong to later approved tasks.

## Constraints

- Keep the existing Python modular monolith, FastAPI dashboard and SQLite architecture.
- Do not introduce PostgreSQL, Redis, Celery, a hosted CRM or other new infrastructure.
- Do not implement lead scoring, AI personalization, follow-ups, UI redesign or campaign analytics in this checkpoint.
- Do not modify live sending behavior.
- Do not silently make assumptions when a migration or repository action could risk data loss.

## Acceptance criteria

1. Existing user changes are preserved.
2. Secrets, databases, exports and preview files are correctly excluded from Git.
3. A safe baseline can be reviewed before committing.
4. Tests run without external network access or real side effects.
5. The new test fixtures reproduce the known classification bugs.
6. A fresh database and a copied existing database can be migrated safely.
7. Existing lead and suppression records remain intact after testing.
8. The application and dashboard still start successfully.

## Deliverables

Report:
- Files changed and why.
- Tests added and their results.
- Database backup location and verification status.
- Migration version before and after testing.
- Any risks or blockers.
- Exact commands I should run to verify the work.

Stop after this checkpoint. Show me the results and wait for my review before implementing the reply-pipeline fixes.