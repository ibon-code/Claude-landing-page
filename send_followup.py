"""
Follow-up step — two-stage sequence on the SAME thread as the original
outreach email (via In-Reply-To/References, threaded off its stored
Message-ID), max 2 follow-ups total (3 automated emails per startup,
matching MAX_OUTREACH_PER_STARTUP):

  Stage 1 (>=7 days after Date Contacted, no reply): the "bumping this"
  nudge. Marks Followed Up = TRUE, Date Followed Up = today.

  Stage 2 (>=7 days after Date Followed Up, still no reply): the final
  attempt — invites a reply if there's interest, says we won't reach out
  again otherwise. Marks Final Followup Sent = TRUE.

After stage 2, the automation stops for that startup permanently — no
further automated email is ever sent (enforced here via Final Followup Sent
and, as a backstop, via the Outreach Count cap in all four send scripts).

Any reply that check_replies.py classifies (booked, interested, or declined)
sets the Meeting column, which halts the sequence immediately regardless of
stage.

Same safety pattern as send_outreach.py: DRY_RUN by default, pass --send
to actually send. Saves the workbook immediately after every send.
"""

import datetime
import os
import sys
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import smtplib

import openpyxl

from email_signature import SIGNATURE_HTML

FILE_PATH = "/Users/iacopobon/Desktop/Claude code experiment/Apollo enrich/Nuove liste/Sourcing Summer challange.xlsx"
PIPELINE_SHEET = "Pipeline"
FOLLOWUP_AFTER_DAYS = 7
CALENDLY_LINK = "https://calendly.com/i-bon"
MAX_OUTREACH_PER_STARTUP = 3  # hard cap on total automated touches (outreach + follow-up + playbook invite + playbook follow-up)

DRY_RUN = "--send" not in sys.argv

GMAIL_USER = os.environ.get("GMAIL_USER")
GMAIL_APP_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD")
if not DRY_RUN and (not GMAIL_USER or not GMAIL_APP_PASSWORD):
    sys.exit("Set GMAIL_USER / GMAIL_APP_PASSWORD before sending for real.")

# Stage 1 — the nudge
FOLLOWUP_TEMPLATE = """Hi {greeting},

Bumping this in case it got buried. Still keen to grab 10 minutes, hear what you're building at {startup_name}, and see if there's potential alignment with our corporate network at Plug and Play.

Open to a quick chat? Feel free to reply directly or grab a slot here: {calendly_link}

Best,

Iacopo"""

FOLLOWUP_HTML_TEMPLATE = """\
<p>Hi {greeting},</p>
<p>Bumping this in case it got buried. Still keen to grab 10 minutes, hear what you're building at {startup_name}, and see if there's potential alignment with our corporate network at Plug and Play.</p>
<p>Open to a quick chat? Feel free to reply directly or grab a slot here: <a href="{calendly_link}">{calendly_link}</a></p>
<p>Best,</p>
{signature}
"""

# Stage 2 — final attempt, then we stop for good
FINAL_FOLLOWUP_TEMPLATE = """Hi {greeting},

Last note from me on this one. I don't want to keep cluttering your inbox, so if there's any interest in connecting with our corporate network at Plug and Play, now or down the line, just let me know: {calendly_link}

Otherwise, no worries at all, and I won't reach out again.

Best,

Iacopo"""

FINAL_FOLLOWUP_HTML_TEMPLATE = """\
<p>Hi {greeting},</p>
<p>Last note from me on this one. I don't want to keep cluttering your inbox, so if there's any interest in connecting with our corporate network at Plug and Play, now or down the line, just let me know: <a href="{calendly_link}">{calendly_link}</a></p>
<p>Otherwise, no worries at all, and I won't reach out again.</p>
<p>Best,</p>
{signature}
"""


def is_checked(value) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().upper() == "TRUE"
    return False


def send_email(to_addr, subject, text_body, html_body, in_reply_to=None):
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = GMAIL_USER
    msg["To"] = to_addr
    if in_reply_to:
        msg["In-Reply-To"] = in_reply_to
        msg["References"] = in_reply_to
    msg.attach(MIMEText(text_body, "plain"))
    msg.attach(MIMEText(html_body, "html"))
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=15) as s:
        s.login(GMAIL_USER, GMAIL_APP_PASSWORD)
        s.send_message(msg)


def main():
    wb = openpyxl.load_workbook(FILE_PATH)
    ws = wb[PIPELINE_SHEET]
    headers = [c.value for c in ws[1]]
    col = {h: i + 1 for i, h in enumerate(headers) if h}

    today = datetime.date.today()
    sent = 0

    print(f"Mode: {'DRY RUN (no emails sent)' if DRY_RUN else 'LIVE SEND'}")
    print("-" * 55)

    for row in range(2, ws.max_row + 1):
        name = ws.cell(row, col["Startup name "]).value
        email_addr = ws.cell(row, col.get("Email", 0)).value if "Email" in col else None
        contacted = ws.cell(row, col.get("Contacted ", 0)).value if "Contacted " in col else None
        date_contacted = ws.cell(row, col.get("Date Contacted", 0)).value if "Date Contacted" in col else None
        followed_up = ws.cell(row, col.get("Followed Up", 0)).value if "Followed Up" in col else None
        date_followed_up = ws.cell(row, col.get("Date Followed Up", 0)).value if "Date Followed Up" in col else None
        final_followup_sent = ws.cell(row, col.get("Final Followup Sent", 0)).value if "Final Followup Sent" in col else None
        meeting = ws.cell(row, col.get("Meeting", 0)).value if "Meeting" in col else None
        founder_name = ws.cell(row, col.get("Full Name", 0)).value if "Full Name" in col else None
        outreach_count = ws.cell(row, col.get("Outreach Count", 0)).value if "Outreach Count" in col else 0
        message_id = ws.cell(row, col.get("Message ID", 0)).value if "Message ID" in col else None
        playbook_flag = ws.cell(row, col.get("Playbook", 0)).value if "Playbook" in col else None

        if not name or not email_addr or not contacted or not date_contacted:
            continue
        if meeting:  # any reply already classified — booked, interested, or declined — stop the sequence
            continue
        if is_checked(playbook_flag):
            print(f"{name} <{email_addr}> — Playbook = TRUE, stopping the outreach follow-up sequence")
            continue
        if "Outreach Count" in col and int(outreach_count or 0) >= MAX_OUTREACH_PER_STARTUP:
            continue

        if not is_checked(followed_up):
            stage = 1
            try:
                anchor_date = datetime.date.fromisoformat(str(date_contacted))
            except ValueError:
                continue
        elif not is_checked(final_followup_sent):
            stage = 2
            if not date_followed_up:
                continue
            try:
                anchor_date = datetime.date.fromisoformat(str(date_followed_up))
            except ValueError:
                continue
        else:
            continue  # both follow-ups already sent — automation stops here for good

        days_since = (today - anchor_date).days
        if days_since < FOLLOWUP_AFTER_DAYS:
            continue

        greeting = founder_name.split()[0] if founder_name else f"{name}'s team"
        if stage == 1:
            body = FOLLOWUP_TEMPLATE.format(greeting=greeting, startup_name=name, calendly_link=CALENDLY_LINK)
            html_body = FOLLOWUP_HTML_TEMPLATE.format(
                greeting=greeting, startup_name=name, calendly_link=CALENDLY_LINK, signature=SIGNATURE_HTML
            )
        else:
            body = FINAL_FOLLOWUP_TEMPLATE.format(greeting=greeting, calendly_link=CALENDLY_LINK)
            html_body = FINAL_FOLLOWUP_HTML_TEMPLATE.format(
                greeting=greeting, calendly_link=CALENDLY_LINK, signature=SIGNATURE_HTML
            )
        subject = f"Re: Plug and Play <> {name}"

        print(f"\n=== {name} <{email_addr}> — stage {stage} follow-up, {days_since} days since anchor ===")
        print(f"Subject: {subject}")
        print(body)
        print("-" * 55)

        if not DRY_RUN:
            try:
                send_email(email_addr, subject, body, html_body, in_reply_to=message_id)
            except Exception as e:
                print(f"  !! send failed for {name} <{email_addr}>: {e}")
                continue
            if stage == 1:
                ws.cell(row, col["Followed Up"]).value = True
                if "Date Followed Up" in col:
                    ws.cell(row, col["Date Followed Up"]).value = today.isoformat()
            else:
                ws.cell(row, col["Final Followup Sent"]).value = True
            if "Outreach Count" in col:
                ws.cell(row, col["Outreach Count"]).value = int(outreach_count or 0) + 1
            wb.save(FILE_PATH)  # save immediately so a later crash (e.g. SMTP disconnect) can't lose this send's flag and cause a resend
            print("  -> sent")

        sent += 1

    print(f"\n{'Would follow up' if DRY_RUN else 'Followed up'}: {sent}")


if __name__ == "__main__":
    main()
