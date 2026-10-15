"""
One-off send — Lleida-Alguaire Airport Startup Challenge 2026 outcome emails.

Sends the pre-written Subject/Body of each row of the reviewed CSV snapshot
(exported from the "Emails" tab of Lleida-Alguaire_Startup_Challenge_2026_emails.xlsx)
via Gmail SMTP, with the PnP HTML signature appended under "Best regards,".

The snapshot itself contains founder emails, so it lives in the gitignored
"FINAL REACH OUT LLEIDA/" folder, never in the repo.

Modes:
  (default)  dry run — validates everything and writes an HTML preview of all emails
  --test     sends one email per category to GMAIL_USER only (real To/CC shown in the body, no CC)
  --send     real send. Logs each send immediately; a rerun skips rows already sent.
"""

import csv
import hashlib
import html
import io
import os
import re
import smtplib
import sys
import time
from collections import Counter
from email.message import EmailMessage
from email.utils import formatdate, make_msgid

from email_signature import SIGNATURE_HTML

BASE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE, "FINAL REACH OUT LLEIDA", "Esiti challenge 2026")
SNAPSHOT = os.path.join(DATA_DIR, "lleida_snapshot.csv")
PREVIEW = os.path.join(DATA_DIR, "preview.html")
SEND_LOG = os.path.join(DATA_DIR, "send_log.csv")

# SHA-256 of the exact CSV content reviewed in the consistency analysis — any edit to the
# sheet after review changes this, and the script refuses to run until it is re-reviewed.
EXPECTED_SHA256 = "f693d72e1a1c15657c8b2b4406994d42c1e2bf9533382ed1d3f3689bad6099a7"

EXPECTED_COLUMNS = ["Startup name", "Website", "Full name", "Category", "Email 1", "Email 2",
                    "Email 3", "Email 4", "Email 5", "To", "CC", "Subject", "Body", "Status"]
EXPECTED_COUNTS = {
    "1. Selected": 7,
    "2. Next edition": 4,
    "3. Ecosystem fit": 2,
    "4. Deal flow, no fit": 4,
    "5. Not in deal flow": 32,
}
SENDER_NAME = "Iacopo Bon"
PAUSE_SECONDS = 3
EMAIL_RE = re.compile(r"^[^@\s,;]+@[^@\s,;]+\.[A-Za-z]{2,}$")

MODE = "send" if "--send" in sys.argv else "test" if "--test" in sys.argv else "dry"


def load_env():
    path = os.path.join(BASE, ".env")
    if os.path.exists(path):
        for line in open(path):
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.strip().split("=", 1)
                os.environ.setdefault(k, v.strip().strip('"').strip("'"))


def split_addrs(s):
    return [a.strip() for a in s.split(",") if a.strip()]


def load_and_validate():
    raw = open(SNAPSHOT, "rb").read()
    sha = hashlib.sha256(raw).hexdigest()
    if sha != EXPECTED_SHA256:
        sys.exit(f"Snapshot hash {sha} does not match the reviewed one ({EXPECTED_SHA256 or 'unset'}). Stop.")

    rows = list(csv.reader(io.StringIO(raw.decode("utf-8"), newline="")))
    header, data = rows[0], rows[1:]
    errors = []
    if header != EXPECTED_COLUMNS:
        errors.append(f"unexpected columns: {header}")
    records = [dict(zip(header, r)) for r in data]

    counts = Counter(r["Category"] for r in records)
    if dict(counts) != EXPECTED_COUNTS:
        errors.append(f"category counts {dict(counts)} != {EXPECTED_COUNTS}")
    if len(records) != sum(EXPECTED_COUNTS.values()):
        errors.append(f"{len(records)} rows, expected {sum(EXPECTED_COUNTS.values())}")

    ccs = {r["CC"].strip() for r in records}
    if len(ccs) != 1 or not EMAIL_RE.match(next(iter(ccs))):
        errors.append(f"expected one valid CC on every row, got {len(ccs)} distinct")

    seen_to = set()
    for i, r in enumerate(records, start=2):
        tag = f"row {i} ({r['Startup name']})"
        to = split_addrs(r["To"])
        emails = [r[f"Email {n}"].strip() for n in range(1, 6) if r[f"Email {n}"].strip()]
        if not to:
            errors.append(f"{tag}: empty To")
        if sorted(to) != sorted(emails):
            errors.append(f"{tag}: To differs from Email 1-5")
        if len(set(to)) != len(to):
            errors.append(f"{tag}: duplicate address in To")
        for a in to:
            if not EMAIL_RE.match(a):
                errors.append(f"{tag}: bad address {a!r}")
        if r["To"] in seen_to:
            errors.append(f"{tag}: same To as an earlier row")
        seen_to.add(r["To"])
        if r["Status"] != "Ready":
            errors.append(f"{tag}: Status {r['Status']!r}")
        if not r["Subject"].strip() or r["Subject"] != r["Subject"].strip():
            errors.append(f"{tag}: empty subject or stray whitespace")
        body = r["Body"]
        if not body.startswith("Dear ") or not re.search(r"Best regards,\s*$", body):
            errors.append(f"{tag}: body must start with 'Dear ' and end with 'Best regards,'")
        if re.search(r"\{\{|\}\}|\[[A-Z ]+\]|TBD|XXX", body + r["Subject"]):
            errors.append(f"{tag}: leftover placeholder")
        if re.search("[ ​-‍﻿  ]", body + r["Subject"] + r["To"] + r["CC"]):
            errors.append(f"{tag}: hidden character")
    if errors:
        sys.exit("VALIDATION FAILED:\n  " + "\n  ".join(errors))
    for i, r in enumerate(records, start=2):
        r["_row"] = i
    print(f"Validation OK: {len(records)} rows, hash {sha[:12]}…, counts {dict(counts)}")
    return records


def body_to_html(body):
    parts = []
    for para in re.split(r"\n\s*\n", body.strip()):
        # A paragraph can mix an intro line with "- " bullet lines; group consecutive runs of each.
        lines = [l.rstrip() for l in para.split("\n")]
        text, items = [], []
        for l in lines + [None]:
            if l is not None and l.startswith("- "):
                if text:
                    parts.append("<p>" + "<br>".join(html.escape(t) for t in text) + "</p>")
                    text = []
                items.append(f"<li>{html.escape(l[2:])}</li>")
            else:
                if items:
                    parts.append("<ul>" + "".join(items) + "</ul>")
                    items = []
                if l is not None:
                    text.append(l)
        if text:
            parts.append("<p>" + "<br>".join(html.escape(t) for t in text) + "</p>")
    return "\n".join(parts) + "\n" + SIGNATURE_HTML


def text_with_signature(body):
    return body.rstrip() + "\n\nIacopo Bon\nSenior Associate\nPlug and Play Tech Center\n"


def build_message(r, test_banner=False):
    sender = os.environ["GMAIL_USER"]
    body = r["Body"]
    subject = r["Subject"]
    to, cc = split_addrs(r["To"]), [r["CC"].strip()]
    if test_banner:
        banner = f"[TEST] Real recipients -> To: {', '.join(to)} | CC: {', '.join(cc)}\n\n"
        body = banner + body
        subject = "[TEST] " + subject
        # Each real recipient becomes a plus-alias of the sender, so multi-recipient To and the CC
        # are exercised for real while everything lands in the sender's own inbox.
        user, domain = sender.split("@")
        to = [f"{user}+to{n}@{domain}" for n in range(1, len(to) + 1)]
        cc = [f"{user}+cc@{domain}"]
    msg = EmailMessage()
    msg["From"] = f"{SENDER_NAME} <{sender}>"
    msg["To"] = ", ".join(to)
    if cc:
        msg["Cc"] = ", ".join(cc)
    msg["Subject"] = subject
    msg["Date"] = formatdate(localtime=True)
    msg["Message-ID"] = make_msgid(domain=sender.split("@")[1])
    msg.set_content(text_with_signature(body))
    msg.add_alternative(body_to_html(body), subtype="html")
    return msg


def write_preview(records):
    sender = os.environ.get("GMAIL_USER", "?")
    blocks = []
    for r in records:
        blocks.append(f"""
<section>
  <div class="meta"><b>#{r['_row']} · {html.escape(r['Category'])} · {html.escape(r['Startup name'])}</b><br>
  From: {html.escape(SENDER_NAME)} &lt;{html.escape(sender)}&gt;<br>
  To: {html.escape(', '.join(split_addrs(r['To'])))}<br>
  CC: {html.escape(r['CC'].strip())}<br>
  Subject: <b>{html.escape(r['Subject'])}</b></div>
  <div class="body">{body_to_html(r['Body'])}</div>
</section>""")
    page = f"""<!doctype html><meta charset="utf-8"><title>Lleida preview</title>
<style>body{{font-family:sans-serif;max-width:820px;margin:24px auto;color:#222}}
section{{border:1px solid #ccc;border-radius:8px;margin:18px 0;padding:14px}}
.meta{{background:#f4f4f4;padding:8px;border-radius:6px;font-size:13px;margin-bottom:10px}}</style>
<h1>{len(records)} emails</h1>{''.join(blocks)}"""
    open(PREVIEW, "w").write(page)
    print(f"Preview written: {PREVIEW}")


def smtp_send(msg):
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=30) as s:
        s.login(os.environ["GMAIL_USER"], os.environ["GMAIL_APP_PASSWORD"])
        s.send_message(msg)


def already_sent():
    if not os.path.exists(SEND_LOG):
        return set()
    with open(SEND_LOG) as f:
        return {(row["row"], row["to"]) for row in csv.DictReader(f) if row["status"] == "sent"}


def log_send(r, status, message_id):
    new = not os.path.exists(SEND_LOG)
    with open(SEND_LOG, "a", newline="") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["timestamp", "row", "startup", "category", "to", "cc", "status", "message_id"])
        w.writerow([time.strftime("%Y-%m-%d %H:%M:%S"), r["_row"], r["Startup name"], r["Category"],
                    r["To"], r["CC"], status, message_id])
        f.flush()
        os.fsync(f.fileno())


def main():
    load_env()
    records = load_and_validate()
    write_preview(records)
    if MODE == "dry":
        print("Dry run: nothing sent.")
        return
    if not os.environ.get("GMAIL_USER") or not os.environ.get("GMAIL_APP_PASSWORD"):
        sys.exit("GMAIL_USER / GMAIL_APP_PASSWORD missing.")

    if MODE == "test":
        firsts = {}
        for r in records:
            firsts.setdefault(r["Category"], r)
        # plus the row with the most recipients, to test a multi-recipient To end to end
        widest = max(records, key=lambda r: len(split_addrs(r["To"])))
        tests = list(firsts.values()) + ([widest] if widest not in firsts.values() else [])
        for r in tests:
            smtp_send(build_message(r, test_banner=True))
            print(f"TEST sent to self: #{r['_row']} {r['Startup name']} ({r['Category']})")
            time.sleep(PAUSE_SECONDS)
        return

    done = already_sent()
    sent = skipped = 0
    for r in records:
        if (str(r["_row"]), r["To"]) in done:
            skipped += 1
            continue
        msg = build_message(r)
        try:
            smtp_send(msg)
        except Exception as e:
            log_send(r, f"error: {e}", msg["Message-ID"])
            sys.exit(f"STOPPED at row {r['_row']} ({r['Startup name']}): {e}. Sent so far this run: {sent}.")
        log_send(r, "sent", msg["Message-ID"])
        sent += 1
        print(f"[{sent}] sent #{r['_row']} {r['Startup name']}")
        time.sleep(PAUSE_SECONDS)
    print(f"Done. Sent {sent}, skipped (already sent) {skipped}, total rows {len(records)}.")


if __name__ == "__main__":
    main()
