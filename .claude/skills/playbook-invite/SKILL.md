---
name: playbook-invite
description: After a first meeting with a founder, invite their startup to Playbook (app.playbook.vc) - create the startup profile, add the founder in the profile's Team (Playbook then emails them its invitation), send Iacopo's standard "Playbook invite" email, and log it in the Pipeline sheet. Use when the user says "invita X su Playbook", "manda il Playbook invite a ...", or rows have 'Playbook Invite' = YES in the Pipeline tab of "Sourcing - N8N Cloud".
---

# Playbook invite (done by Claude in Chrome, on request)

**Normally n8n does this** (workflow `Pipeline - Playbook Invite`, from 2026-11-03): it creates the profile, emails the
user the Team link, and sends our email once the user sets `Team Added` = YES. Use this skill only as a fallback:
rows n8n marked `Needs review`, or when the user explicitly asks Claude to do it in Chrome. Never run it on a row
whose `Playbook Invite Status` is not empty without the user's OK (n8n may be handling it).

n8n cannot do this: the Playbook MCP can create a startup, but none of its 45 tools has a team / founder /
email field (`update_startup` only edits company data). The web app adds a team member with a
`PATCH /v1/startups/<id>/` on its own session cookie. So Claude does it in the user's Chrome, where they are
logged in to Playbook (route tested 2026-11-02 on test startup 119064: card showed "Invitation sent").

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
3. **Create the profile**: sidebar **Create** > **Startup** > **From Website URL** > paste the website >
   **Analyze Website**.
   - If Playbook shows "This company may already exist in Playbook", stop: no duplicate. Tell the user and
     use that profile only if they say so.
   - The AI pre-fills a review form. Check every field against the startup's own website and fix it: factual,
     no hype, and the right logo (a wrong logo can appear).
   - Required fields: Website, Startup name, Logo, One liner, Description, Vertical(s), Tags, HQ country, HQ city.
   - Press **CREATE STARTUP** and note the profile URL (`https://app.playbook.vc/discover/startups/<id>/overview`).
   - If the analysis finds nothing, fill the same fields by hand ("Create Manually" also needs a logo file).
4. **Add the founder to the Team**: open `https://app.playbook.vc/discover/startups/<id>/team` and press
   **+** next to "Startup Team".
   - In the form, User type = **Member Profile** (the default, the one tested; External Contact was not tested).
   - Fill First name, Last name, Email = the recipient, Job role (e.g. CEO), then **SUBMIT**.
   - Playbook sends its invitation at this moment.
   - The email must belong to one of the profile's **valid domains** (by default the website's domain).
     Otherwise the form says "Email doesn't match the following domains".
     - If the founder's company email domain differs: **ACTIONS > Manage domains > Add domain**, then retry.
     - Some domains are refused ("This domain is not allowed", e.g. pnptc.com, probably also gmail.com etc.).
       If so, stop and tell the user: no email.
   - Reload the Team tab. The card must show the name, the role and **"Invitation sent"**. If not, stop and
     tell the user (no email).
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
- Never delete a Playbook profile yourself (ACTIONS > Delete startup exists): ask the user to do it.
