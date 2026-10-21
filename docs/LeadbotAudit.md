# LeadBot Unified Audit — Trust, Lead Quality, Sales Workflow & Measurable Growth

## Your role

Act as a senior Python backend engineer, email deliverability specialist, AI systems engineer, sales operations strategist, data analyst, and UI/UX auditor.

Conduct a comprehensive, READ-ONLY audit of my existing LeadBot project. Your task is to understand the actual implementation, identify what works, uncover weaknesses, and produce one prioritized plan to help me achieve my business goals.

**This is an audit, not an implementation task. Do not modify files or make changes.**

Do not assume previous audit findings are still accurate. Verify them against the current code wherever possible. Do not report a feature as implemented merely because documentation claims it exists.

---

## 1. Business context

LeadBot is a local Python application used by TalkSasa, a Kenyan Bulk SMS provider.

It helps me discover organizations that could benefit from Bulk SMS or SMS API integration, contact them by email, process replies, classify prospects, manage follow-ups, and analyze sales outcomes.

Potential customers include:

- Schools and education management platforms.
- SACCOs and financial cooperatives.
- Microfinance organizations.
- Healthcare providers.
- Churches and other membership organizations.
- Businesses with multiple branches or large customer bases.
- Software companies and developers building systems that need SMS notifications, OTPs, reminders, alerts, or transactional messages.

The system currently uses a modular Python/FastAPI architecture, SQLite, a local web dashboard, SMTP for sending emails, IMAP for receiving replies, Telegram notifications, and AI-assisted reply classification. Verify this architecture from the source code rather than assuming every component remains unchanged.

### My four business goals

**Goal 1: Trustworthiness and operational safety**

The system must send the right emails to appropriate recipients, respect opt-outs, avoid duplicates, preserve records, handle failures safely, and alert me when intervention is required.

**Goal 2: Better prospect quality**

I want to prioritize organizations that have a plausible need for TalkSasa's services. I am particularly interested in newer or growing organizations, but I do not want the system to mistake weak evidence of a recent launch for proof that an organization is a good prospect.

**Goal 3: A practical sales workflow**

I need to know who is interested, who needs a response, who should receive a follow-up, which conversations could become meetings, and which leads have converted into customers.

**Goal 4: Evidence-based improvement**

I want reliable data to measure whether my prospecting and outreach strategies are improving. The dashboard should help me understand which industries, lead sources, qualification signals, and messaging approaches generate meaningful business results.

---

## 2. Operating constraints and safety rules

Treat the following as requirements:

- Maximum of **10 outbound emails per day**, unless the actual current configuration and code reveal a discrepancy. Report discrepancies; do not change anything.
- The inbox watcher/automatic reply processing must remain paused until critical safeguards have been verified. Inspect how it can be enabled and whether its current state matches this requirement. Do not start it.
- Groq is the current AI provider for now. The `.env` configuration previously used `AI_PROVIDER=groq` and the model `openai/gpt-oss-20b`.
- Ollama is a possible future local-AI option, but it is not currently installed. Do not assume it is available or require me to install it to complete this audit.
- AI-generated outreach openers were disabled using `USE_AI_OPENER=false`. Verify whether that remains true.
- Preserve the existing architecture unless you can identify a specific, evidence-backed reason that a future change is necessary.
- Prioritize affordable solutions suitable for an individual operator running the system on a Windows laptop/WSL environment.
- Do not send emails, read a live mailbox, contact external services, call Groq or other AI APIs, perform network scans, or trigger any production workflows.
- Do not expose, print, copy, or include secrets in your report.
- Do not modify files, environment variables, databases, Git history, running processes, scheduled tasks, or application settings.
- Do not commit, push, deploy, install packages, run migrations, or execute destructive commands.
- You may inspect source files, configuration templates, tests, Git history available locally, and existing documentation.
- Run only safe, offline tests if they do not modify project data or trigger external services. Explain any uncertainty about their side effects before running them.
- Treat previous audit documents as historical evidence, not proof of the current implementation.
- Distinguish verified findings, reported-but-unverified findings, inferences, and unknowns.

If a necessary file or piece of evidence is missing, state that limitation instead of guessing.

---

## 3. Audit the existing code in detail

### A. Architecture and execution flow

Map the actual path through the application:

1. Lead discovery and collection.
2. Organization and contact verification.
3. Lead scoring and prioritization.
4. Outreach message generation.
5. Daily send scheduling and limits.
6. Email sending and delivery error handling.
7. Inbox polling and message retrieval.
8. Reply-to-lead and thread matching.
9. AI classification and confidence handling.
10. Follow-up scheduling.
11. Telegram notifications and review queues.
12. Dashboard updates and analytics.

Identify the relevant modules, functions, database tables, scheduled jobs, and dependencies for each stage.

Explain how data moves between stages, where state is stored, and which operations are automatic versus manual.

Identify duplicate logic, hidden dependencies, unclear ownership of state, or unnecessary complexity. Do not recommend a rewrite just because the code could be organized differently.

### B. Trustworthiness and email safety

Inspect the implementation for:

- Duplicate sends, overlapping scheduler runs, race conditions, and concurrent processing.
- Whether the 10-email daily cap is enforced centrally, atomically, and across all send paths.
- Whether the cap counts successful sends, attempted sends, follow-ups, retries, and different message categories correctly.
- Whether opt-outs are checked immediately before sending, not only when leads are initially selected.
- Whether suppression survives lead re-imports, database restarts, and duplicate records.
- Whether both contact-level and appropriate domain-level suppression are supported.
- Whether opt-out detection distinguishes explicit requests from ordinary questions, quoted text, signatures, disclaimers, and discussion of unsubscribe mechanisms.
- Whether bounce detection covers relevant permanent and temporary SMTP failures.
- Whether permanent bounces and transient failures receive different treatment.
- Whether uncertain AI classifications are safely held for human review.
- Whether an AI failure or low-confidence classification creates a visible alert or review item.
- Whether an SMTP error for one lead incorrectly interrupts processing of other leads or creates misleading status records.
- Whether failed leads are retried indefinitely.
- Whether a failed or interrupted run can send the same message twice.
- Whether the system has a safe recovery path after a crash or laptop shutdown.
- Whether automatic follow-ups stop after a reply, opt-out, bounce, or other disqualifying event.
- Whether unsubscribe instructions, sender identity, and appropriate business contact details are included in outbound messages.
- Whether the code has safeguards against accidental bulk sends during testing.

Identify which failures could result in unwanted emails, missed prospects, misleading analytics, or reputational damage.

### C. Reply processing and AI classification

Inspect the actual classifier, reply-cleaning logic, sender matching, inbox polling, and status-transition code.

Check:

- Interested replies versus general questions.
- Explicit opt-outs versus ordinary questions containing phrases such as “unsubscribe.”
- Out-of-office responses, including automated messages with unusual subjects.
- Bounces and delivery-status notifications.
- Replies that contain quoted emails, forwarded content, signatures, or legal disclaimers.
- Replies in English, Swahili, and Sheng where supported.
- Replies from an alternate email address or a colleague at the same organization.
- Messages that cannot confidently be matched to a known lead.
- Repeated processing of the same message.
- Inbox read/unread handling and message UID tracking.
- IMAP UIDVALIDITY changes, mailbox rebuilds, reconnects, and missing messages.
- Whether Junk/Spam or other relevant folders are intentionally excluded or silently ignored.
- Whether received timestamps reflect the actual message time or only the time it was processed.
- Whether status transitions can overwrite newer or more important information.
- Whether the classifier's confidence score is calibrated or merely an arbitrary model output.
- Whether malformed AI output, timeouts, rate limits, or unavailable providers lead to safe, visible outcomes.
- Whether excessive email content is sent to the external AI provider.
- Whether unnecessary personal information is included in prompts or logs.

Inspect the current Groq integration and the potential future Ollama integration. Explain the actual data flow and external dependencies.

Do not assume that switching to local AI is automatically the best next step. Assess its privacy benefits, operational cost, laptop resource requirements, reliability, and maintenance burden relative to the current setup.

### D. Prospect discovery and qualification

Evaluate the actual methods used to discover organizations and assess their suitability for TalkSasa.

Inspect:

- Industry and organization-type classification.
- Lead source tracking.
- Email validity and contact-role relevance.
- Website and domain verification.
- Duplicate organization detection.
- Evidence of business activity and growth.
- Detection of recently established organizations.
- Scoring formulas, weights, thresholds, and tie-breaking.
- Handling of missing, stale, conflicting, or weak evidence.
- Whether scores can be explained to a human operator.
- Whether the system confuses an organization being newly discovered online with it being newly established.
- Whether it prioritizes relevant buyers over organizations that simply have a valid email address.
- Whether it can identify plausible SMS use cases, such as OTPs, payment reminders, member notifications, appointment reminders, and automated system alerts.
- Whether it wastes time and resources on low-quality leads.

Design a conceptual qualification framework that prioritizes evidence-backed potential customers.

Consider separate scores for:

1. **Service fit:** How plausibly the organization needs Bulk SMS or an SMS API.
2. **Growth/newness evidence:** How credible the signs of recent establishment or growth are.
3. **Contact quality:** Whether the contact appears relevant and reachable.
4. **Evidence confidence:** How complete, reliable, and recent the supporting information is.

Do not assume these dimensions must be combined into one score. Explain how to avoid over-ranking a new but irrelevant organization.

Identify which signals the existing code actually collects, which are missing, and which would require new data sources. Do not scrape additional websites or contact any services during the audit.

### E. Sales workflow and follow-ups

Determine whether the existing application supports a usable sales process.

Inspect whether it can distinguish and track:

- New leads.
- Qualified leads.
- Ready-to-contact leads.
- Emails sent.
- Delivery failures and bounces.
- Replies awaiting classification.
- Interested prospects.
- Questions requiring a human answer.
- Explicit opt-outs.
- Not-interested replies.
- Follow-ups due.
- Meetings proposed.
- Meetings booked.
- Negotiations or active opportunities.
- Converted customers.
- Closed or disqualified leads.

Do not require all these to be separate statuses if a better data model already exists. Assess the current model and recommend a clear, maintainable alternative only if necessary.

Verify:

- Follow-up timing and limits.
- Whether follow-ups stop when appropriate.
- Whether messages remain attached to the correct conversation.
- Whether I can see what action is required next for each lead.
- Whether human review items are prioritized.
- Whether meeting and customer outcomes can be recorded.
- Whether an operator can correct an AI classification without losing the original result or audit trail.
- Whether status changes are recorded with timestamps and reasons.
- Whether the system supports an effective daily sales routine.

### F. Data integrity, privacy, and security

Inspect the database schema, queries, migrations, logging, exports, backups, configuration, and Git practices.

Check for:

- Missing or incomplete sent-email history.
- Missing subject/body snapshots or message identifiers.
- Incorrect or inconsistent timestamps.
- Inadequate audit trails for status changes.
- Missing source URLs or evidence for leads.
- Duplicate or inconsistent organization records.
- Database locking, concurrency, migration, backup, and recovery risks.
- Unsafe SQLite usage across multiple processes.
- Sensitive data written to logs, CSV exports, tests, or sample data.
- API keys or credentials accidentally committed or exposed.
- `.env` handling and whether example configuration files contain real credentials.
- Unnecessary retention of email content or personal data.
- Inadequate access control for a dashboard that may expose lead and email information.
- Data deletion, retention, and export capabilities.
- Whether dry-run mode has side effects, including database updates, score changes, network requests, or external API calls.
- Whether test runs can accidentally modify production records.

Identify the actual evidence for each concern. Do not claim a credential is exposed without checking available evidence. Do not reproduce credentials even if found.

Flag privacy and Kenyan direct-marketing compliance questions that require confirmation by the business or qualified legal advice. Do not make unsupported legal conclusions.

### G. Monitoring, scheduling, and operational reliability

Inspect the background scheduler, inbox watcher, process lifecycle, logs, Telegram alerts, and retry mechanisms.

Determine:

- What starts automatically and what must be launched manually.
- Whether jobs survive restarts.
- Whether overlapping runs are prevented.
- Whether there is a heartbeat or last-success timestamp.
- Whether stale jobs, failed inbox checks, and repeated errors trigger alerts.
- Whether alerts are persisted and retried after Telegram failures.
- Whether alerts can be duplicated or lost.
- Whether logs contain enough diagnostic context without exposing sensitive data.
- Whether the system reports the last successful send, inbox poll, classification, and database backup.
- Whether an operator can distinguish “nothing happened because there was no work” from “nothing happened because the process failed.”

Do not start, stop, or restart services during this audit.

### H. Dashboard and user experience

Inspect the current dashboard implementation, not just its screenshots or documentation.

Evaluate whether it helps an individual sales operator answer these questions quickly:

1. What needs my attention now?
2. How many emails have been sent today against the 10-email limit?
3. Which leads are the best prospects and why?
4. Which replies need a human response?
5. Which follow-ups are due?
6. Which meetings or opportunities are progressing?
7. Which leads converted into clients?
8. Which outreach efforts are producing results?
9. Is the system running properly, and what has failed?
10. What should I do next?

Assess:

- Information hierarchy and visual clutter.
- Navigation and discoverability.
- Typography, spacing, color, contrast, and consistency.
- Table usability, filtering, searching, and sorting.
- Clear status labels and meaningful error messages.
- Empty states, loading states, and failure states.
- Whether important warnings are distinguishable from routine information.
- Whether charts display actionable information rather than vanity metrics.
- Whether dashboard actions are safe and clearly explained.

Do not redesign or modify the interface. Identify the highest-value improvements and justify them by their impact on daily work.

### I. Analytics and continuous improvement

Determine whether the current schema and dashboard can measure the entire journey from lead discovery to customer conversion.

Assess the availability and reliability of:

- Leads discovered by date, industry, source, and organization type.
- Leads meeting qualification criteria.
- Verified contact rate.
- Emails sent and delivery failures.
- Reply rate.
- Positive-reply rate.
- Qualified-opportunity rate.
- Meeting-booking rate.
- Customer-conversion rate.
- Opt-out and bounce rates.
- Follow-up effectiveness.
- Performance by industry, lead source, prospect score, and outreach template.
- Time from first contact to reply, meeting, and conversion.
- Manual corrections to AI classifications.
- Reasons for disqualification and lost opportunities.

Recommend a small set of primary metrics and supporting diagnostic metrics.

For every proposed metric, specify its numerator, denominator, required source data, and relevant time window. Do not define ambiguous metrics such as “success rate” without explaining what success means.

Explain how to avoid misleading comparisons caused by small sample sizes, missing outcomes, changes in sending volume, or differences in lead quality.

Recommend a baseline measurement period and a simple way to compare improvements over time. Account for the low daily email cap and the possibility that results will take time to accumulate.

Do not invent historical performance figures. If the data is insufficient, explain what must be recorded going forward.

---

## 4. Compare findings with previous audit documents

If previous audit reports or project documentation are available in the repository or supplied files, use them to create a reconciliation table.

For every significant previous finding, classify it as:

- Verified and still present.
- Verified as fixed.
- Partially fixed.
- Reported as fixed but not verifiable.
- No longer applicable.
- Unable to determine.

Pay particular attention to previously reported issues involving:

- Broad unsubscribe matching.
- Missing alerts for AI failures or low-confidence replies.
- Concurrent sending and daily-cap enforcement.
- Suppression checks immediately before sending.
- Inbox watcher supervision and heartbeat alerts.
- Incomplete sent-email history and timestamps.
- Dry-run side effects.
- Public-repository privacy and secret handling.
- IMAP UIDVALIDITY and mailbox folder handling.
- Domain-level suppression and bounce detection.
- SQLite concurrency and backup safety.
- Email footer, privacy notices, and compliance questions.
- Endless retries and follow-ups crowding out new prospects.
- Existing fixes to quoted-text cleaning, thread matching, out-of-office detection, SMTP error handling, Telegram retries, and status regression.

These are historical leads for investigation, not assumptions about the current code.

---

## 5. Evidence requirements

For each significant finding, provide:

- Finding ID.
- Goal affected.
- Severity: Critical, High, Medium, or Low.
- Confidence: High, Medium, or Low.
- Relevant file path and function, class, query, or configuration key.
- Exact code behavior or test evidence supporting the finding.
- Reproduction steps or a safe offline test where practical.
- Likely business impact.
- Recommended correction.
- Dependencies and implementation risks.
- A suggested regression test.

Clearly distinguish a confirmed defect from a design concern or a recommendation.

Do not provide fabricated line numbers, pretend tests were executed, or claim that a feature is missing without inspecting the relevant implementation.

If a test cannot be safely executed, explain why and describe the test that should be performed later.

---

## 6. Required final report

Produce one consolidated report with these sections.

### Section 1: Executive summary

Explain the current state of LeadBot, the biggest risks, the strongest existing capabilities, and the highest-value opportunities for improvement.

State what was actually inspected and what remains unverified.

### Section 2: Current architecture and workflow

Include a concise architecture diagram using Mermaid if useful, followed by the end-to-end data flow and important dependencies.

### Section 3: Goal scorecard

Assess each of the four goals:

- Trustworthiness and safety.
- Prospect quality.
- Sales workflow.
- Measurable improvement.

Use evidence-based ratings and explain the basis for each. Do not use arbitrary numerical scores without a defined rubric.

### Section 4: Verified findings register

Create a prioritized table containing ID, severity, goal, finding, evidence, business impact, and recommended action.

Separate verified defects from unverified concerns.

### Section 5: Previous-audit reconciliation

Show which previous issues remain, have been fixed, are partially fixed, or cannot be verified.

### Section 6: Lead quality and scoring recommendations

Explain the proposed qualification dimensions, available evidence, missing signals, and how to avoid favoring organizations simply because they appear new.

### Section 7: Sales workflow and dashboard recommendations

Describe the minimum useful daily sales workflow and the dashboard information needed to support it.

### Section 8: Analytics and measurement plan

Define the baseline, primary metrics, formulas, required data, and method for measuring improvement.

### Section 9: Prioritized implementation roadmap

Organize work into phases:

**Phase 0 — Immediate safeguards:** prevent accidental or duplicate sends, protect opt-outs, enforce the daily cap, and surface critical failures.

**Phase 1 — Data integrity and reliability:** improve reply processing, history, timestamps, scheduler recovery, database safety, and operational monitoring.

**Phase 2 — Prospect quality:** improve qualification, evidence collection, scoring transparency, and lead prioritization.

**Phase 3 — Sales workflow:** improve review queues, follow-ups, conversation tracking, meeting outcomes, and customer conversion tracking.

**Phase 4 — Analytics and optimization:** establish reliable metrics, compare lead sources and outreach performance, and use evidence to refine the process.

**Phase 5 — Optional improvements:** assess local AI with Ollama, advanced dashboard changes, and other enhancements only if the evidence supports them.

For each task include priority, expected benefit, dependencies, estimated effort (Small/Medium/Large), test requirements, and measurable completion criteria.

Avoid duplicate work and unnecessary architecture changes. Identify tasks that can be done independently and tasks that must be completed first.

### Section 10: Owner decisions

List only decisions that genuinely require my input, such as data retention, approved outreach policy, review rules, and whether to adopt a local AI model.

Give a recommended default for each decision when reasonable.

### Section 11: Readiness checklist

Provide a checklist that must be satisfied before automatic inbox processing is resumed or outbound automation is expanded.

---

## 7. Final instructions

Start by inspecting the project structure and identifying the relevant source files. Then trace the actual implementation before reaching conclusions.

Do not edit anything.

Do not stop after identifying technical bugs. Connect each important finding to one or more of my four business goals.

Do not recommend building more features before confirming that the current system is reliable and its data is trustworthy.

Do not treat the number of emails sent or leads scraped as the main measure of success. The goal is to generate qualified opportunities and customers safely, with evidence showing what works.

Do not over-engineer the solution. Prefer the smallest reliable change that solves a demonstrated problem.

At the end, give me:

1. The **five highest-priority actions**.
2. The **three most important things I should not build yet**.
3. The **single best next implementation task** and why.
4. The exact files and functions that should be examined or changed in the next phase.
5. The tests and measurable criteria needed to verify that the next phase succeeds.

**Stop after delivering the audit and roadmap. Wait for my approval before implementing anything.**