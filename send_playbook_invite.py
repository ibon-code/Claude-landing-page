"""
Playbook invite step — for Pipeline rows where you've set "Playbook" = TRUE
(meant to be done manually, after an actual meeting happened), sends the
Playbook.vc invitation email and marks "Playbook Invite Sent" so it's never
sent twice.

Same safety pattern as the other outreach scripts: DRY_RUN by default,
pass --send to actually send.
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
PARTNERS_URL = "https://www.plugandplaytechcenter.com/innovation-services/corporations/our-corporate-partners"
PLAYBOOK_URL = "https://app.playbook.vc"
MAX_OUTREACH_PER_STARTUP = 3  # hard cap on total automated touches (outreach + follow-up + playbook invite + playbook follow-up)

DRY_RUN = "--send" not in sys.argv

GMAIL_USER = os.environ.get("GMAIL_USER")
GMAIL_APP_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD")
if not DRY_RUN and (not GMAIL_USER or not GMAIL_APP_PASSWORD):
    sys.exit("Set GMAIL_USER / GMAIL_APP_PASSWORD before sending for real.")

TEXT_TEMPLATE = """Hi {greeting},

It was a pleasure speaking with you, I really enjoyed learning about {startup_name} and your team.

I sent you an invitation to complete the profile at {playbook_url}. Can you check to see if you can log in? Your profile there should serve as a starting point to apply your company to meet with our partners and network. The invitation expires after 48 hours.

Additionally, here is the list of our corporate partners for reference: {partners_url}

Please keep me posted on your project's progress, and I would love to receive your deck if you have one!

Best,

Iacopo"""

HTML_TEMPLATE = """\
<p>Hi {greeting},</p>
<p>It was a pleasure speaking with you, I really enjoyed learning about {startup_name} and your team.</p>
<p>I sent you an invitation to complete the profile at <a href="{playbook_url}">{playbook_url}</a>. Can you check to see if you can log in? Your profile there should serve as a starting point to apply your company to meet with our partners and network. <strong>The invitation expires after 48 hours.</strong></p>
<p>Additionally, <a href="{partners_url}">here is the list of our corporate partners</a> for reference.</p>
<p>Please keep me posted on your project's progress, and I would love to receive your deck if you have one!</p>
<p>Best,</p>
{signature}
"""


def is_checked(value) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().upper() == "TRUE"
    return False


def send_email(to_addr, subject, text_body, html_body):
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = GMAIL_USER
    msg["To"] = to_addr
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

    if "Playbook" not in col:
        sys.exit('Pipeline sheet has no "Playbook" column.')
    if "Playbook Invite Sent" not in col:
        sys.exit('Pipeline sheet has no "Playbook Invite Sent" column.')

    sent = 0
    print(f"Mode: {'DRY RUN (no emails sent)' if DRY_RUN else 'LIVE SEND'}")
    print("-" * 55)

    for row in range(2, ws.max_row + 1):
        name = ws.cell(row, col["Startup name "]).value
        email_addr = ws.cell(row, col.get("Email", 0)).value if "Email" in col else None
        founder_name = ws.cell(row, col.get("Full Name", 0)).value if "Full Name" in col else None
        playbook_flag = ws.cell(row, col["Playbook"]).value
        already_sent = ws.cell(row, col["Playbook Invite Sent"]).value
        outreach_count = ws.cell(row, col.get("Outreach Count", 0)).value if "Outreach Count" in col else 0

        if not name or not email_addr or not is_checked(playbook_flag) or is_checked(already_sent):
            continue
        if "Outreach Count" in col and int(outreach_count or 0) >= MAX_OUTREACH_PER_STARTUP:
            print(f"{name} <{email_addr}> — outreach cap ({MAX_OUTREACH_PER_STARTUP}) already reached, skipping")
            continue

        greeting = founder_name.split()[0] if founder_name else f"{name}'s team"
        text_body = TEXT_TEMPLATE.format(
            greeting=greeting, startup_name=name, playbook_url=PLAYBOOK_URL, partners_url=PARTNERS_URL
        )
        html_body = HTML_TEMPLATE.format(
            greeting=greeting, startup_name=name, playbook_url=PLAYBOOK_URL, partners_url=PARTNERS_URL,
            signature=SIGNATURE_HTML,
        )
        subject = f"Plug and Play - {name} Playbook invite"

        print(f"\n=== {name} <{email_addr}> ===")
        print(f"Subject: {subject}")
        print(text_body)
        print("-" * 55)

        if not DRY_RUN:
            try:
                send_email(email_addr, subject, text_body, html_body)
            except Exception as e:
                print(f"  !! send failed for {name} <{email_addr}>: {e}")
                continue
            ws.cell(row, col["Playbook Invite Sent"]).value = True
            if "Date Playbook Invite Sent" in col:
                ws.cell(row, col["Date Playbook Invite Sent"]).value = datetime.date.today().isoformat()
            if "Playbook Followup Sent" in col:
                ws.cell(row, col["Playbook Followup Sent"]).value = False
            if "Outreach Count" in col:
                ws.cell(row, col["Outreach Count"]).value = int(outreach_count or 0) + 1
            wb.save(FILE_PATH)  # save immediately so a later crash (e.g. SMTP disconnect) can't lose this send's flag and cause a resend
            print("  -> sent")

        sent += 1

    print(f"\n{'Would send' if DRY_RUN else 'Sent'}: {sent}")


if __name__ == "__main__":
    main()
