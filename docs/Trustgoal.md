# LeadBot Strategic Audit — Goal 1: Trustworthiness

You are auditing the existing LeadBot application for TalkSasa. This is the first step in a larger project with four strategic goals:

1. Make the current bot trustworthy.
2. Find better prospects.
3. Improve the sales workflow.
4. Make the system learn from evidence and outcomes.

## Current operating decisions

- Maximum 10 outbound emails per day.
- Windows laptop using WSL.
- SQLite database and local Ollama for AI reply processing.
- Target any organization with a plausible Bulk SMS or SMS API use case.
- Preserve the existing modular Python/FastAPI architecture.

## Your assignment

Review the current repository and compare its actual state against the uploaded LeadBot audit. Do not start implementing fixes yet.

### 1. Verify existing findings

Pay particular attention to:

- Interested replies incorrectly classified as unsubscribes.
- Interested replies incorrectly classified as out-of-office messages.
- Reply processing depending on unread status.
- Replies matched only by sender address.
- SMTP failures stopping an entire send batch.
- Lead statuses being overwritten or regressing.
- Missing email bodies, timestamps, sources and event history.
- Opt-outs and bounces being missed.
- Telegram alerts failing without retry.
- Scheduler runs being skipped when the laptop is asleep.
- Dry-run mode still causing side effects.
- Credentials, local databases and sensitive files being exposed or insufficiently ignored.
- Whether reply classification uses local Ollama or can transmit data to external AI services.

For each finding, report whether it is confirmed, partially confirmed, not reproduced, already fixed, or cannot be verified. Include file paths and function names, plus tests or reproducible evidence where possible.

Do not assume the earlier audit is still current.

### 2. Evaluate trustworthiness beyond the listed bugs

Assess five areas:

A. Data integrity: record accuracy, status transitions, event history, database safety and recovery.

B. Communication safety: duplicate-send prevention, daily cap enforcement, opt-out suppression, bounce handling and safe retries.

C. Reply processing: message retrieval, thread matching, HTML and quoted-text handling, classification accuracy and human review.

D. Operational reliability: scheduler recovery, logging, alert retries, startup checks and failure visibility.

E. Privacy and control: secrets handling, data retention, local AI configuration, access boundaries and direct-marketing safeguards.

Identify any critical risks missing from the earlier audit.

### 3. Produce a prioritized gap register

For every issue include:

- ID and description.
- Evidence and affected code.
- Status: confirmed, unverified, already fixed or not reproduced.
- Severity: critical, high, medium or low.
- Potential business impact.
- Recommended fix.
- Acceptance test that would prove the fix.
- Dependencies and implementation risks.
- Which of the four strategic goals it supports.

Prioritize issues that could lose a genuine opportunity, contact someone who opted out, send duplicate emails, corrupt records or silently stop processing.

### 4. Recommend implementation order

Group findings into:

1. Immediate safeguards.
2. Reply-processing and data-integrity fixes.
3. Sending and operational reliability.
4. Prospect-quality improvements.
5. Sales workflow improvements.
6. Analytics and learning capabilities.

Explain dependencies and why each phase should happen in that order.

### Constraints

- Do not edit, create, delete or migrate project files.
- Do not send emails or contact live SMTP/IMAP servers.
- Do not call external AI services.
- Do not alter the SQLite database.
- Do not expose secrets in the report.
- Do not redesign the dashboard or add features.
- Do not recommend a rewrite unless you demonstrate why the existing architecture cannot meet the goals.

## Final output

Deliver a concise executive summary, the evidence-backed gap register, the top five immediate priorities and a proposed implementation sequence with acceptance criteria.

End by identifying any decisions or evidence needed from the owner before changes can safely begin.
