"""
Playbook follow-up step — for Pipeline rows where the Playbook invite was sent
>=7 days ago, checks the inbox for any reply from that contact since the
invite was sent; if none, sends one short bump email and marks
"Playbook Followup Sent" = TRUE. Never follows up more than once.

Same safety pattern as the other outreach scripts: DRY_RUN by default,
pass --send to actually send.
"""

import datetime
import email as email_lib
import imaplib
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
MAX_OUTREACH_PER_STARTUP = 3  # hard cap on total automated touches (outreach + follow-up + playbook invite + playbook follow-up)

DRY_RUN = "--send" not in sys.argv

GMAIL_USER = os.environ.get("GMAIL_USER")
GMAIL_APP_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD")
if not GMAIL_USER or not GMAIL_APP_PASSWORD:
    sys.exit("Set GMAIL_USER / GMAIL_APP_PASSWORD before running (needed to check for replies even in dry run).")

TEMPLATE = """Hi {greeting},

Just following up on my last email: were you able to log into the platform? The invitation expires after 48 hours, so if it lapsed or you ran into any issues, just let me know and I'll be happy to send you a new one.

Also, feel free to share your deck whenever it's ready. I'd love to take a look.

Best,
Iacopo"""

HTML_TEMPLATE = """\
<p>Hi {greeting},</p>
<p>Just following up on my last email: were you able to log into the platform? The invitation expires after 48 hours, so if it lapsed or you ran into any issues, just let me know and I'll be happy to send you a new one.</p>
<p>Also, feel free to share your deck whenever it's ready. I'd love to take a look.</p>
<p>Best,</p>
{signature}
"""


def is_checked(value) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().upper() == "TRUE"
    return False


def has_replied_to_playbook_invite(imap_conn, addr, since_date):
    # Scoped to the Playbook-invite thread specifically (subject contains
    # "Playbook invite") — a reply to the *original* outreach email from
    # the same address must NOT count here, they're different conversations.
    # Date-scoped to SINCE the invite was actually sent — a reply can't
    # predate the email it's replying to, and this keeps the IMAP search
    # fast instead of scanning the whole mailbox history.
    since_str = since_date.strftime("%d-%b-%Y")
    status, data = imap_conn.search(None, f'(SINCE {since_str} FROM "{addr}" SUBJECT "Playbook invite")')
    return bool(data[0].split())


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

    required = ["Playbook Invite Sent", "Date Playbook Invite Sent", "Playbook Followup Sent"]
    for label in required:
        if label not in col:
            sys.exit(f'Pipeline sheet is missing column "{label}".')

    imap_conn = imaplib.IMAP4_SSL("imap.gmail.com")
    imap_conn.login(GMAIL_USER, GMAIL_APP_PASSWORD)
    imap_conn.select("inbox")

    today = datetime.date.today()
    sent = 0

    print(f"Mode: {'DRY RUN (no emails sent)' if DRY_RUN else 'LIVE SEND'}")
    print("-" * 55)

    for row in range(2, ws.max_row + 1):
        name = ws.cell(row, col["Startup name "]).value
        email_addr = ws.cell(row, col.get("Email", 0)).value if "Email" in col else None
        founder_name = ws.cell(row, col.get("Full Name", 0)).value if "Full Name" in col else None
        invite_sent = ws.cell(row, col["Playbook Invite Sent"]).value
        date_sent = ws.cell(row, col["Date Playbook Invite Sent"]).value
        already_followed_up = ws.cell(row, col["Playbook Followup Sent"]).value
        outreach_count = ws.cell(row, col.get("Outreach Count", 0)).value if "Outreach Count" in col else 0

        if not name or not email_addr or not is_checked(invite_sent) or not date_sent:
            continue
        if is_checked(already_followed_up):
            continue
        if "Outreach Count" in col and int(outreach_count or 0) >= MAX_OUTREACH_PER_STARTUP:
            print(f"{name} <{email_addr}> — outreach cap ({MAX_OUTREACH_PER_STARTUP}) already reached, skipping")
            continue

        try:
            sent_date = datetime.date.fromisoformat(str(date_sent))
        except ValueError:
            continue

        days_since = (today - sent_date).days
        if days_since < FOLLOWUP_AFTER_DAYS:
            continue

        if has_replied_to_playbook_invite(imap_conn, email_addr.strip().lower(), sent_date):
            print(f"{name} <{email_addr}> — replied since invite, skipping follow-up")
            continue

        greeting = founder_name.split()[0] if founder_name else f"{name}'s team"
        body = TEMPLATE.format(greeting=greeting)
        html_body = HTML_TEMPLATE.format(greeting=greeting, signature=SIGNATURE_HTML)
        subject = f"Re: Plug and Play - {name} Playbook invite"

        print(f"\n=== {name} <{email_addr}> — {days_since} days since invite, no reply ===")
        print(f"Subject: {subject}")
        print(body)
        print("-" * 55)

        if not DRY_RUN:
            try:
                send_email(email_addr, subject, body, html_body)
            except Exception as e:
                print(f"  !! send failed for {name} <{email_addr}>: {e}")
                continue
            ws.cell(row, col["Playbook Followup Sent"]).value = True
            if "Outreach Count" in col:
                ws.cell(row, col["Outreach Count"]).value = int(outreach_count or 0) + 1
            wb.save(FILE_PATH)  # save immediately so a later crash can't lose this send's flag and cause a resend
            print("  -> sent")

        sent += 1

    imap_conn.logout()
    print(f"\n{'Would follow up' if DRY_RUN else 'Followed up'}: {sent}")


if __name__ == "__main__":
    main()
