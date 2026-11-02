---
name: playbook-invite
description: After a first meeting with a founder, invite their startup to Playbook (app.playbook.vc) - create the startup profile, add the founder in the profile's Team (Playbook then emails them its invitation), send Iacopo's standard "Playbook invite" email, and log it in the Pipeline sheet. Use when the user says "invita X su Playbook", "manda il Playbook invite a ...", or rows have 'Playbook Invite' = YES in the Pipeline tab of "Sourcing - N8N Cloud".
---

# Playbook invite (done by Claude in Chrome, on request)

n8n cannot do this: its Playbook login only works for the MCP connector, which can create a startup but has no
"add team member" function (tested 2026-11-02: the backend answers "Authentication credentials were not
provided"). So Claude does it in the user's Chrome, where they are logged in to Playbook.

Every email goes to a real founder and cannot be recalled. Follow the steps in order.

## Where things are
- Pipeline tab of Google Sheet "Sourcing - N8N Cloud":
  https://docs.google.com/spreadsheets/d/1LpPqSKXOvB2FdqNGNnlVBpPDvnfDrYml7npHJEZpKxc/edit?gid=114224284
  Columns used: `Startup name`, `Website`, `Email`, `Full Name`, `Playbook Invite` (YES = to do),
  `Meeting contact` + `Meeting contact name` (the person met; empty = use `Email` / `Full Name`),
  log: `Playbook Invite Status`, `Playbook Profile URL`, `Date Playbook Invite`, `Playbook Invite Message ID`.
  Read it with `fetch('/spreadsheets/d/<ID>/gviz/tq?tqx=out:csv&gid=114224284&headers=1')` from the sheet tab.
- Email script: `scripts/send_invite_email.py` (preview by default, `--send` to send; refuses if a
  "Playbook invite" email to that address is already in Gmail Sent).

## Steps (per startup)
1. **Pick the rows**: `Playbook Invite` = YES and `Playbook Invite Status` empty (or the startups the user named).
   Recipient = `Meeting contact` if filled, else `Email`; name = `Meeting contact name`, else `Full Name`.
   Show the user the list (startup, recipient, name) before touching Playbook.
2. **Already on Playbook?** Search the startup name and website domain in Playbook (Discover > Startups).
   If the same domain exists, do NOT create a duplicate: tell the user and use that profile only if they say so.
3. **Create the profile** in Playbook (sidebar "Create" > startup): name, website, one-liner, description
   (from the startup's own website, factual, no hype), country, vertical. Save, then note the profile URL
   (`https://app.playbook.vc/discover/startups/<id>/overview`).
4. **Add the founder to the Team**: profile > Team tab > **+** > name + email of the recipient > Submit.
   Playbook sends its invitation email automatically at this moment. Reload the Team tab and check the person
   is listed with the right email. If not, stop and tell the user (no email).
5. **Our email**: run the script without `--send`, show the user the preview, and send only after their
   explicit go ("invia"):
   `python3 .claude/skills/playbook-invite/scripts/send_invite_email.py --to EMAIL --name "First Last" --startup "Name" --send`
   If it prints BLOCKED, stop: that founder already got it.
6. **Log it in the sheet** on that row: `Playbook Invite Status` = `Sent YYYY-MM-DD HH:MM`, `Playbook Profile URL`,
   `Date Playbook Invite`, `Playbook Invite Message ID` (from the script output). Re-read the row to confirm.
7. Report: startups invited, profile links, emails sent, anything skipped and why. Close the tabs you opened.

## Rules
- Never send the email before step 4 is confirmed (otherwise the founder has no invitation to open).
- Never invite a startup twice: `Playbook Invite Status` filled or BLOCKED from the script = stop.
- No emoji, no edits to other rows or columns.
