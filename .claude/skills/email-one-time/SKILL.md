---
name: email-one-time
description: Send a batch of pre-written, personalised emails one time from a spreadsheet (one row = one email with To/CC/Subject/Body), safely, from the user's Gmail. Use when the user shares a Google Sheet/Excel/CSV of emails to send ("manda queste mail", "invia a tutte le startup del file", outcome/selection emails, invitations, announcements). Not for recurring automations — those live on the company n8n.
---

# Email one time

The user's standard is **"non possiamo sbagliare nulla"**: every email that leaves goes to real founders/partners
from the user's own account and cannot be recalled. Follow every step in order. Never skip the test or the explicit go.

Tool: `scripts/send_one_off.py` (generic; config-driven). Signature comes from `email_signature.py` at repo root.
Credentials: `GMAIL_USER` / `GMAIL_APP_PASSWORD` in `.env` (Gmail App Password).

## Hard rules

- **Nothing is sent before the user writes an explicit go in chat** for the real send ("invia", "vai invia"). Approval of the plan or of the test is not approval to send.
- **Data never goes to git.** The repo is public. Snapshot, config, preview and send log live in `one-off-sends/<job-name>/` (gitignored). Never put addresses in committed files.
- **Never `source .env` in a shell.** A malformed line (e.g. a space after `=`) makes zsh print the secret. Read it in Python only (the script does). Never print secret values.
- **Before fixing or rotating a shared credential** (expired App Password, etc.), find every consumer of it and what is queued: anything that was failing on it will fire the moment it works again. The local n8n must stay off permanently; the company n8n (agentflow.pnptc.com) uses Gmail OAuth, not the App Password.
- The send runs **only from the frozen snapshot**: if the hash differs from the reviewed one, the script refuses. If the user edits the sheet, re-download, re-review, re-hash.

## Steps

### 1. Read the sheet
- Google Sheet/Drive files are private: open it in the user's Chrome (claude-in-chrome), then fetch the tab as CSV from the page context:
  `fetch('/spreadsheets/d/<ID>/gviz/tq?tqx=out:csv&gid=<GID>', {credentials:'include'})` (the `/export` URL fails cross-origin).
- Confirm with the user it's the right version/tab (they often re-upload: the gid can change). Read the Summary/notes tab if any — it states intent (who gets what, deliberate exceptions).
- Tool output is truncated around ~1000 chars and some output gets blocked (looks like cookies/query strings: avoid `key=value` formats in results). Keep results small and summarised.

### 2. Consistency analysis (report it to the user before anything else)
Check at least, per row and across rows:
- To parses into valid addresses; To equals the source email columns if To is a formula; no duplicate address in a row; no two rows with the same To; CC/BCC valid and as expected.
- **No cross-contamination**: a body/subject never mentions another row's company name. The company name used in the body is the right one for the row.
- Greeting names match the recipients (every greeted first name appears in Full name or in a To local part; "team" greetings are deliberate only if multiple recipients).
- Within each category the bodies are the same template: diff each body against the category's first one and show what varies (should be only name, date, tech area, etc.).
- Subjects consistent per category; no leftover placeholders (`{{`, `[NAME]`, TBD, XXX); no hidden characters; status column all "Ready".
- Flag for confirmation (don't decide alone): email domain ≠ website domain, unexpected CC domain, dates/facts you can't verify, rows with extra contacts.
Ask the user about every flag with AskUserQuestion, then proceed.

### 3. Freeze the snapshot
- Download the exact CSV through Chrome (ask permission for the download: filename, source, size), compute its SHA-256 in the page (`crypto.subtle.digest`) and compare with `shasum -a 256` of the downloaded file.
- Move it to `one-off-sends/<job-name>/snapshot.csv`. Write `config.json` there (see the script docstring): columns, `ready_status`, `expected_rows`, `expected_counts`, `body_must_start_with` / `body_must_end_with` as they apply, `sender_name`, and `sha256` from `--hash`.
- Re-run the step-2 analysis on the local file (Python) so the frozen copy is the reviewed one.

### 4. Dry run + preview
`python3 .claude/skills/email-one-time/scripts/send_one_off.py --config one-off-sends/<job>/config.json`
- Fix any validation failure in the sheet (not in the snapshot by hand), re-freeze.
- Also build every message offline (import the script, call `Job.build_message`) and assert: envelope recipients == To + CC (+BCC) of the row, subject/plain text unchanged, signature present, bullets rendered as `<ul>` where the body has "- " lines.
- `open` the preview.html for the user.

### 5. Test send
`... --test`: one email per category plus the row with most recipients, every real recipient replaced by a plus-alias of the sender (`user+to1@`, `user+cc1@`), real recipients printed at the top of the body.
- Verify via IMAP (always with `SINCE <today>`) that they arrived and in Sent, with the right To/Cc headers.
- Explain to the user: Gmail shows one message even with several aliases (same mailbox dedup); commas between recipients are the standard separator; the compact "to a, b" line includes CC — expand ▾ to see To/Cc separately.
- Let the user check rendering, signature and recipients in Gmail. Answer their doubts before asking for the go.

### 6. Real send — only after explicit go
`... --send` (3s pause, per-row fsync'd log, stops on first SMTP error; a rerun skips rows already logged as sent).

### 7. Verify and report
- Log has N "sent" rows; every logged Message-ID is in `[Gmail]/Sent Mail`; check INBOX for mailer-daemon/postmaster bounces since today (re-check later in the day if asked).
- If the user wants the sheet updated (e.g. Status column): first re-hash the live sheet to make sure row order is unchanged, then write `Sent YYYY-MM-DD HH:MM` per row from the log, then re-read the sheet and compare every row.
- Close the Chrome tabs you opened. Report counts per category, recipients, bounces.

## Troubleshooting
- `SMTPServerDisconnected: Connection unexpectedly closed` at login, or IMAP `[AUTHENTICATIONFAILED] Invalid credentials`: the App Password was revoked — a company password change revokes all App Passwords. The user creates a new one at myaccount.google.com/apppasswords and writes it into `.env` themselves (`! open -e .env`, value right after `=`, no spaces) — never pasted in chat. Before this, apply the shared-credential rule above.
