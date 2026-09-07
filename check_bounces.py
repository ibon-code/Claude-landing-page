"""
Bounce handler — scans for "couldn't be delivered" / non-existent-recipient
bounce notifications, matches the failed address back to its Pipeline row,
clears the Email cell, resets Contacted so it re-enters the outreach flow,
and records the dead address in "Bounced Emails" so enrich_apollo_pipeline.py
knows to skip that contact and try the next-best one at the company instead.

Tracks processed bounce UIDs in a local cache so the same bounce is never
handled twice.
"""

import datetime
import email as email_lib
import imaplib
import json
import os
import re
import sys

import openpyxl

FILE_PATH = "/Users/iacopobon/Desktop/Claude code experiment/Apollo enrich/Nuove liste/Sourcing Summer challange.xlsx"
PIPELINE_SHEET = "Pipeline"
SEEN_BOUNCES_PATH = os.path.join(os.path.dirname(__file__), "seen_bounces.json")

GMAIL_USER = os.environ.get("GMAIL_USER")
GMAIL_APP_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD")
if not GMAIL_USER or not GMAIL_APP_PASSWORD:
    sys.exit("Set GMAIL_USER / GMAIL_APP_PASSWORD before running.")

LOOKBACK_DAYS = 7
_since = (datetime.date.today() - datetime.timedelta(days=LOOKBACK_DAYS)).strftime("%d-%b-%Y")

BOUNCE_SEARCHES = [
    f'(SINCE {_since} SUBJECT "couldn\'t be delivered")',
    f'(SINCE {_since} SUBJECT "Delivery Status Notification (Failure)")',
    f'(SINCE {_since} SUBJECT "Undelivered Mail")',
    f'(SINCE {_since} SUBJECT "Returned mail")',
    f'(SINCE {_since} FROM "mailer-daemon")',
    f'(SINCE {_since} FROM "postmaster")',
]

FAILED_ADDR_PATTERNS = [
    re.compile(r"sent to (\S+@\S+?) couldn", re.IGNORECASE),
    re.compile(r"delivered to (\S+@\S+?) because", re.IGNORECASE),
    re.compile(r"message to[: ]+<?(\S+@\S+?)>?\s+(couldn|failed|could not)", re.IGNORECASE),
    re.compile(r"Final-Recipient:\s*rfc822;\s*(\S+@\S+)", re.IGNORECASE),
]

NONEXISTENT_MARKERS = [
    "does not exist", "no such user", "recipient email address is possibly incorrect",
    "5.1.1", "user unknown", "invalid recipient", "address not found",
    "couldn't be found", "unable to receive mail",
]


def get_plain_body(msg):
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain":
                return part.get_payload(decode=True).decode(errors="ignore")
        return ""
    return msg.get_payload(decode=True).decode(errors="ignore")


def extract_failed_address(body):
    for pattern in FAILED_ADDR_PATTERNS:
        m = pattern.search(body)
        if m:
            return m.group(1).strip().rstrip(".,;:").lower()
    return None


def is_nonexistent_bounce(body):
    lowered = body.lower()
    return any(marker in lowered for marker in NONEXISTENT_MARKERS)


def load_seen():
    if os.path.exists(SEEN_BOUNCES_PATH):
        with open(SEEN_BOUNCES_PATH) as f:
            return set(json.load(f))
    return set()


def save_seen(seen):
    with open(SEEN_BOUNCES_PATH, "w") as f:
        json.dump(sorted(seen), f, indent=2)


def main():
    seen = load_seen()

    m = imaplib.IMAP4_SSL("imap.gmail.com")
    m.login(GMAIL_USER, GMAIL_APP_PASSWORD)
    m.select('"[Gmail]/All Mail"')

    ids = set()
    for query in BOUNCE_SEARCHES:
        status, data = m.search(None, query)
        ids.update(data[0].split())
    print(f"Bounce-like messages found: {len(ids)}")

    bounced_addresses = set()
    for uid in ids:
        key = uid.decode()
        if key in seen:
            continue

        status, msg_data = m.fetch(uid, "(RFC822)")
        msg = email_lib.message_from_bytes(msg_data[0][1])
        body = get_plain_body(msg)

        if not is_nonexistent_bounce(body):
            seen.add(key)
            continue

        addr = extract_failed_address(body)
        if addr:
            bounced_addresses.add(addr)
            print(f"  bounce: {addr}")
        seen.add(key)

    m.logout()
    save_seen(seen)

    if not bounced_addresses:
        print("No new nonexistent-recipient bounces to process.")
        return

    wb = openpyxl.load_workbook(FILE_PATH)
    ws = wb[PIPELINE_SHEET]
    headers = [c.value for c in ws[1]]
    col = {h: i + 1 for i, h in enumerate(headers) if h}

    required = ["Email", "Contacted ", "Bounced Emails"]
    for label in required:
        if label not in col:
            sys.exit(f'Pipeline sheet is missing column "{label}".')

    updated = 0
    for row in range(2, ws.max_row + 1):
        current_email = ws.cell(row, col["Email"]).value
        if not current_email or str(current_email).strip().lower() not in bounced_addresses:
            continue

        dead_email = str(current_email).strip().lower()
        name = ws.cell(row, col["Startup name "]).value

        existing_bounced = ws.cell(row, col["Bounced Emails"]).value or ""
        bounced_list = [e.strip() for e in existing_bounced.split(",") if e.strip()]
        if dead_email not in bounced_list:
            bounced_list.append(dead_email)
        ws.cell(row, col["Bounced Emails"]).value = ", ".join(bounced_list)

        ws.cell(row, col["Email"]).value = None
        ws.cell(row, col["Contacted "]).value = False

        updated += 1
        print(f"  reset: {name} — cleared {dead_email}, will retry via Apollo")

    if updated:
        wb.save(FILE_PATH)
    print(f"\nDone. Rows reset for retry: {updated}")


if __name__ == "__main__":
    main()
