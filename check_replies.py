"""
Checks the inbox for replies from contacted Pipeline startups, classifies
each reply with Claude (booked a meeting / interested but no meeting yet /
not interested / other), and updates the "Meeting" column accordingly.

Only updates "Meeting" to "Meeting booked" when the reply clearly confirms
that — a polite decline or a vague reply does not get marked as booked.
Tracks which message UIDs have already been processed (in a local cache) so
the same reply isn't re-classified/re-flagged on every run.
"""

import datetime
import email
import imaplib
import json
import os
import re
import sys
from email.header import decode_header

import openpyxl
import requests

FILE_PATH = "/Users/iacopobon/Desktop/Claude code experiment/Apollo enrich/Nuove liste/Sourcing Summer challange.xlsx"
PIPELINE_SHEET = "Pipeline"
SEEN_REPLIES_PATH = os.path.join(os.path.dirname(__file__), "seen_replies.json")

GMAIL_USER = os.environ.get("GMAIL_USER")
GMAIL_APP_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD")
ANTHROPIC_KEY = os.environ.get("ANTHROPIC_API_KEY")

if not GMAIL_USER or not GMAIL_APP_PASSWORD:
    sys.exit("Set GMAIL_USER / GMAIL_APP_PASSWORD before running.")
if not ANTHROPIC_KEY:
    sys.exit("Set ANTHROPIC_API_KEY before running.")

CLAUDE_MODEL = "claude-haiku-4-5-20251001"


def decode_subject(raw):
    parts = decode_header(raw or "")
    out = ""
    for text, enc in parts:
        out += text.decode(enc or "utf-8", errors="ignore") if isinstance(text, bytes) else text
    return out


def get_plain_body(msg):
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain":
                return part.get_payload(decode=True).decode(errors="ignore")
        return ""
    return msg.get_payload(decode=True).decode(errors="ignore")


def load_seen():
    if os.path.exists(SEEN_REPLIES_PATH):
        with open(SEEN_REPLIES_PATH) as f:
            return set(json.load(f))
    return set()


def save_seen(seen):
    with open(SEEN_REPLIES_PATH, "w") as f:
        json.dump(sorted(seen), f, indent=2)


def classify_reply(startup_name, body):
    prompt = (
        "Classify this email reply to a VC outreach message. Return ONLY JSON, no prose:\n"
        '{"category": "meeting_booked" | "interested_no_meeting" | "not_interested" | "other", '
        '"summary": "one short sentence"}\n\n'
        "meeting_booked: they clearly confirm booking/scheduling a call or meeting (e.g. booked a calendar slot, "
        "proposed a specific time and it's being confirmed).\n"
        "interested_no_meeting: positive/curious but no meeting confirmed yet.\n"
        "not_interested: declines, says no, not a fit, unsubscribe, etc.\n"
        "other: auto-reply, out-of-office, unrelated, unclear.\n\n"
        f"Startup: {startup_name}\nReply text:\n{body[:1500]}"
    )
    resp = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key": ANTHROPIC_KEY,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        json={"model": CLAUDE_MODEL, "max_tokens": 200, "messages": [{"role": "user", "content": prompt}]},
        timeout=30,
    )
    resp.raise_for_status()
    text = resp.json()["content"][0]["text"].strip()
    text = re.sub(r"^```(json)?", "", text).strip()
    text = re.sub(r"```$", "", text).strip()
    return json.loads(text)


def main():
    seen = load_seen()

    wb = openpyxl.load_workbook(FILE_PATH)
    ws = wb[PIPELINE_SHEET]
    headers = [c.value for c in ws[1]]
    col = {h: i + 1 for i, h in enumerate(headers) if h}

    if "Meeting" not in col:
        sys.exit('Pipeline sheet has no "Meeting" column.')

    contacted_rows = []
    for row in range(2, ws.max_row + 1):
        email_addr = ws.cell(row, col.get("Email", 0)).value if "Email" in col else None
        date_contacted = ws.cell(row, col.get("Date Contacted", 0)).value if "Date Contacted" in col else None
        if email_addr:
            contacted_rows.append(
                (row, str(email_addr).strip().lower(), ws.cell(row, col["Startup name "]).value, date_contacted)
            )

    if not contacted_rows:
        print("No contacted rows with an email — nothing to check.")
        return

    m = imaplib.IMAP4_SSL("imap.gmail.com")
    m.login(GMAIL_USER, GMAIL_APP_PASSWORD)
    m.select("inbox")

    updated = 0
    for row, addr, name, date_contacted in contacted_rows:
        # Scoped to the original outreach thread — a reply to the later
        # Playbook-invite email (different subject/conversation) must not
        # be picked up here. Date-scoped to SINCE the outreach was actually
        # sent (falls back to a 30-day window if the date is missing) so
        # this doesn't scan the entire mailbox history on every run.
        try:
            since_date = datetime.date.fromisoformat(str(date_contacted))
        except (ValueError, TypeError):
            since_date = datetime.date.today() - datetime.timedelta(days=30)
        since_str = since_date.strftime("%d-%b-%Y")

        status, data = m.search(None, f'(SINCE {since_str} FROM "{addr}" NOT SUBJECT "Playbook invite")')
        ids = data[0].split()
        for uid in ids:
            key = f"{addr}:{uid.decode()}"
            if key in seen:
                continue

            status, msg_data = m.fetch(uid, "(RFC822)")
            msg = email.message_from_bytes(msg_data[0][1])
            body = get_plain_body(msg)

            result = classify_reply(name, body)
            print(f"{name} <{addr}> — {result['category']}: {result['summary']}")

            if result["category"] == "meeting_booked":
                ws.cell(row, col["Meeting"]).value = "Meeting booked"
                updated += 1
            elif result["category"] == "not_interested":
                ws.cell(row, col["Meeting"]).value = "Not interested"
            elif result["category"] == "interested_no_meeting":
                ws.cell(row, col["Meeting"]).value = "Interested — following up"

            seen.add(key)

    m.logout()

    if updated or seen != load_seen():
        wb.save(FILE_PATH)
    save_seen(seen)
    print(f"\nDone. Meetings newly marked booked: {updated}")


if __name__ == "__main__":
    main()
