"""
One-off bulk send of pre-written emails from a frozen CSV snapshot (one row = one email).

Every run validates the snapshot against the config first; nothing is sent unless asked.

  python3 send_one_off.py --config CONFIG.json --hash   # print the snapshot's SHA-256 (put it in the config after review)
  python3 send_one_off.py --config CONFIG.json          # dry run: validate + write preview.html, sends nothing
  python3 send_one_off.py --config CONFIG.json --test   # one email per category (+ widest row) to plus-aliases of GMAIL_USER
  python3 send_one_off.py --config CONFIG.json --send   # real send, logged per row; a rerun skips rows already sent

Config (JSON) — only "snapshot" and "sha256" are required:
  {
    "snapshot": "path/to/snapshot.csv",           # relative to the config file
    "sha256": "<hash printed by --hash>",
    "columns": {"to": "To", "cc": "CC", "bcc": null, "subject": "Subject", "body": "Body",
                "name": "Startup name", "category": "Category", "status": "Status",
                "html": null},                    # html: optional column with a ready-made HTML body, sent
                                                  # as-is (+ signature) instead of the one built from "body";
                                                  # its visible text must match "body" (links may be written
                                                  # "text (url)" in the plain body). category may be a list
                                                  # of columns, joined with " / ".
    "ready_status": "Ready",                      # null = don't check
    "expected_rows": 49,
    "expected_counts": {"1. Selected": 7},        # per category, optional
    "body_must_start_with": "Dear ",
    "body_must_end_with": "Best regards,",
    "signature": true,                            # append SIGNATURE_HTML from email_signature.py
    "bold_lines": ["Please book your slot by ..."],  # optional: these exact lines are bold in the HTML part;
                                                  # each must appear exactly once in every body
    "sender_name": "Iacopo Bon",
    "pause_seconds": 3
  }
Preview and send log are written next to the config file. Keep that folder gitignored —
it holds recipient data.
"""

import argparse
import csv
import hashlib
import html
import io
import json
import os
import re
import smtplib
import sys
import time
from collections import Counter
from email.message import EmailMessage
from email.utils import formatdate, make_msgid

EMAIL_RE = re.compile(r"^[^@\s,;<>]+@[^@\s,;<>]+\.[A-Za-z]{2,}$")
HIDDEN_RE = re.compile("[ ​-‍﻿  ]")
PLACEHOLDER_RE = re.compile(r"\{\{|\}\}|\[[A-Z_ ]{2,}\]|\bTBD\b|\bXXX\b|\bLorem\b")
DEFAULT_COLUMNS = {"to": "To", "cc": "CC", "bcc": None, "subject": "Subject", "body": "Body",
                   "name": None, "category": None, "status": None, "html": None}


def find_repo_root():
    d = os.path.dirname(os.path.abspath(__file__))
    while d != os.path.dirname(d):
        if os.path.exists(os.path.join(d, "email_signature.py")) or os.path.exists(os.path.join(d, ".env")):
            return d
        d = os.path.dirname(d)
    sys.exit("Could not find the repo root (email_signature.py / .env).")


ROOT = find_repo_root()
sys.path.insert(0, ROOT)


def load_env():
    # Parsed in Python on purpose: `source .env` in a shell can print secrets if a line is malformed.
    path = os.path.join(ROOT, ".env")
    if os.path.exists(path):
        for line in open(path):
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.strip().split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def split_addrs(s):
    return [a.strip() for a in re.split(r"[,;\n]", s or "") if a.strip()]


class Job:
    def __init__(self, config_path):
        self.config_path = os.path.abspath(config_path)
        self.dir = os.path.dirname(self.config_path)
        self.cfg = json.load(open(self.config_path))
        self.snapshot = os.path.join(self.dir, self.cfg["snapshot"])
        self.cols = {**DEFAULT_COLUMNS, **self.cfg.get("columns", {})}
        self.preview = os.path.join(self.dir, "preview.html")
        self.send_log = os.path.join(self.dir, "send_log.csv")

    def col(self, r, key):
        name = self.cols.get(key)
        if isinstance(name, list):
            return " / ".join(r.get(n, "") for n in name)
        return r.get(name, "") if name else ""

    def html_part(self, r, body):
        """The HTML that is sent: the sheet's own HTML column if configured, else built from the body."""
        if not self.cols.get("html"):
            return self.body_to_html(body)
        out = self.col(r, "html")
        if self.cfg.get("signature", True):
            from email_signature import SIGNATURE_HTML
            out += "\n" + SIGNATURE_HTML
        return out

    @staticmethod
    def visible_text(html_text):
        t = re.sub(r"<[^>]+>", " ", html_text)
        return re.sub(r"\s+", "", html.unescape(t))

    def label(self, r):
        return self.col(r, "name") or split_addrs(self.col(r, "to"))[0]

    def sha(self):
        return hashlib.sha256(open(self.snapshot, "rb").read()).hexdigest()

    def load_and_validate(self):
        sha = self.sha()
        if sha != self.cfg.get("sha256"):
            sys.exit(f"Snapshot hash {sha} != reviewed hash {self.cfg.get('sha256') or '(unset)'}. "
                     "Re-review the data, then update sha256 in the config.")
        text = open(self.snapshot, "rb").read().decode("utf-8")
        rows = list(csv.DictReader(io.StringIO(text, newline="")))
        errors = []
        header = list(rows[0].keys()) if rows else []
        for key, name in self.cols.items():
            for n in (name if isinstance(name, list) else [name]):
                if n and n not in header:
                    errors.append(f"column {n!r} ({key}) not in CSV header {header}")
        if errors:
            sys.exit("VALIDATION FAILED:\n  " + "\n  ".join(errors))

        exp_rows = self.cfg.get("expected_rows")
        if exp_rows is not None and len(rows) != exp_rows:
            errors.append(f"{len(rows)} rows, expected {exp_rows}")
        exp_counts = self.cfg.get("expected_counts")
        if exp_counts:
            counts = dict(Counter(self.col(r, "category") for r in rows))
            if counts != exp_counts:
                errors.append(f"category counts {counts} != {exp_counts}")

        ready = self.cfg.get("ready_status")
        start, end = self.cfg.get("body_must_start_with"), self.cfg.get("body_must_end_with")
        seen_to = {}
        for i, r in enumerate(rows, start=2):
            r["_row"] = i
            tag = f"row {i} ({self.col(r, 'name') or '?'})"
            to = split_addrs(self.col(r, "to"))
            others = split_addrs(self.col(r, "cc")) + split_addrs(self.col(r, "bcc"))
            if not to:
                errors.append(f"{tag}: empty To")
            for a in to + others:
                if not EMAIL_RE.match(a):
                    errors.append(f"{tag}: bad address {a!r}")
            if len(set(to + others)) != len(to + others):
                errors.append(f"{tag}: duplicate address within the row")
            key = tuple(sorted(to))
            if key in seen_to:
                errors.append(f"{tag}: same To as row {seen_to[key]}")
            seen_to[key] = i
            subj, body = self.col(r, "subject"), self.col(r, "body")
            if not subj.strip() or subj != subj.strip() or "\n" in subj:
                errors.append(f"{tag}: empty subject, stray whitespace or newline")
            if not body.strip():
                errors.append(f"{tag}: empty body")
            if start and not body.startswith(start):
                errors.append(f"{tag}: body does not start with {start!r}")
            if end and not body.rstrip().endswith(end):
                errors.append(f"{tag}: body does not end with {end!r}")
            if PLACEHOLDER_RE.search(subj + " " + body):
                errors.append(f"{tag}: leftover placeholder")
            if HIDDEN_RE.search(subj + body + self.col(r, "to") + self.col(r, "cc")):
                errors.append(f"{tag}: hidden character")
            for b in self.cfg.get("bold_lines", []):
                n = sum(1 for l in body.split("\n") if l.strip() == b)
                if n != 1:
                    errors.append(f"{tag}: bold line {b!r} found {n} times, expected once")
            if self.cols.get("html"):
                h = self.col(r, "html")
                if not h.strip():
                    errors.append(f"{tag}: empty HTML body")
                elif PLACEHOLDER_RE.search(h):
                    errors.append(f"{tag}: leftover placeholder in HTML")
                else:
                    plain = re.sub(r"\s*\(https?://[^)\s]+\)", "", body)
                    plain = re.sub(r"\s+", "", plain.replace("\u2022", ""))
                    if self.visible_text(h).replace("\u2022", "") != plain:
                        errors.append(f"{tag}: HTML text differs from the plain body")
            if ready and self.col(r, "status") != ready:
                errors.append(f"{tag}: status {self.col(r, 'status')!r} != {ready!r}")
        if self.cols.get("name"):
            errors += self.cross_mentions(rows)
        if errors:
            sys.exit("VALIDATION FAILED:\n  " + "\n  ".join(errors))
        n_to = sum(len(split_addrs(self.col(r, "to"))) for r in rows)
        print(f"Validation OK: {len(rows)} emails, {n_to} To recipients, hash {sha[:12]}…")
        if self.cols.get("category"):
            print("  per category:", dict(Counter(self.col(r, "category") for r in rows)))
        return rows

    def cross_mentions(self, rows):
        """Worst possible mistake: an email naming another recipient's company."""
        suffix = re.compile(r"\b(B\.?V|GmbH|Ltd|Limited|srl|S\.?L\.?U?|S\.?A\.?S?|Inc|LLC|ApS|AG|Oy|AB|SE|Private)\b\.?", re.I)

        def short(n):
            return re.sub(r"\(.*?\)", "", suffix.sub("", n)).strip(" .-&")

        errors = []
        for r in rows:
            own = self.col(r, "name").lower()
            text = self.col(r, "subject") + " " + self.col(r, "body")
            for o in rows:
                s = short(self.col(o, "name"))
                if o is r or len(s) <= 3 or s.lower() in own:
                    continue
                # All-caps names (GAME, LVP) must match case too: "Madrid in Game" is not the company GAME.
                flags = 0 if s.isupper() else re.I
                if re.search(r"(?<!\w)" + re.escape(s) + r"(?!\w)", text, flags):
                    errors.append(f"row {r['_row']} ({self.col(r, 'name')}): mentions another row's company {s!r}")
        return errors

    # --- rendering -------------------------------------------------------------------------

    def line_html(self, line):
        esc = html.escape(line)
        return f"<strong>{esc}</strong>" if line.strip() in self.cfg.get("bold_lines", []) else esc

    def body_to_html(self, body):
        parts = []
        for para in re.split(r"\n\s*\n", body.strip()):
            # A paragraph can mix normal lines with "- " / "* " bullets; group consecutive runs.
            text, items = [], []
            for l in [l.rstrip() for l in para.split("\n")] + [None]:
                if l is not None and re.match(r"^[-*•] ", l):
                    if text:
                        parts.append("<p>" + "<br>".join(self.line_html(t) for t in text) + "</p>")
                        text = []
                    items.append(f"<li>{html.escape(l[2:])}</li>")
                else:
                    if items:
                        parts.append("<ul>" + "".join(items) + "</ul>")
                        items = []
                    if l is not None:
                        text.append(l)
            if text:
                parts.append("<p>" + "<br>".join(self.line_html(t) for t in text) + "</p>")
        out = "\n".join(parts)
        if self.cfg.get("signature", True):
            from email_signature import SIGNATURE_HTML
            out += "\n" + SIGNATURE_HTML
        return out

    def build_message(self, r, test=False):
        sender = os.environ["GMAIL_USER"]
        to, cc, bcc = (split_addrs(self.col(r, k)) for k in ("to", "cc", "bcc"))
        subject, body = self.col(r, "subject"), self.col(r, "body")
        if test:
            # Every real recipient becomes a plus-alias of the sender: multi-recipient To/CC is
            # exercised for real, but everything lands in the sender's own inbox.
            body = (f"[TEST] Real recipients -> To: {', '.join(to)} | CC: {', '.join(cc) or '-'}"
                    f" | BCC: {', '.join(bcc) or '-'}\n\n") + body
            subject = "[TEST] " + subject
            user, domain = sender.split("@")
            to = [f"{user}+to{n}@{domain}" for n in range(1, len(to) + 1)]
            cc = [f"{user}+cc{n}@{domain}" for n in range(1, len(cc) + 1)]
            bcc = [f"{user}+bcc{n}@{domain}" for n in range(1, len(bcc) + 1)]
        msg = EmailMessage()
        msg["From"] = f"{self.cfg.get('sender_name', '')} <{sender}>".strip()
        msg["To"] = ", ".join(to)
        if cc:
            msg["Cc"] = ", ".join(cc)
        msg["Subject"] = subject
        msg["Date"] = formatdate(localtime=True)
        msg["Message-ID"] = make_msgid(domain=sender.split("@")[1])
        plain = body.rstrip() + ("\n\n" + self.cfg.get("sender_name", "") if self.cfg.get("signature", True) else "")
        msg.set_content(plain + "\n")
        html_body = self.html_part(r, body)
        if test and self.cols.get("html"):  # the sheet's HTML doesn't contain the [TEST] recipients line
            html_body = f"<p><b>{html.escape(body.split(chr(10))[0])}</b></p>" + html_body
        msg.add_alternative(html_body, subtype="html")
        return msg, to + cc + bcc  # bcc goes only in the envelope, never in a header

    def write_preview(self, rows):
        sender = os.environ.get("GMAIL_USER", "?")
        blocks = []
        for r in rows:
            meta = [f"<b>#{r['_row']} · {html.escape(self.col(r, 'category'))} · {html.escape(self.label(r))}</b>",
                    f"From: {html.escape(self.cfg.get('sender_name', ''))} &lt;{html.escape(sender)}&gt;",
                    f"To: {html.escape(', '.join(split_addrs(self.col(r, 'to'))))}",
                    f"CC: {html.escape(', '.join(split_addrs(self.col(r, 'cc'))) or '-')}",
                    f"BCC: {html.escape(', '.join(split_addrs(self.col(r, 'bcc'))) or '-')}",
                    f"Subject: <b>{html.escape(self.col(r, 'subject'))}</b>"]
            blocks.append(f"<section><div class='meta'>{'<br>'.join(meta)}</div>"
                          f"<div>{self.html_part(r, self.col(r, 'body'))}</div></section>")
        page = ("<!doctype html><meta charset='utf-8'><title>Send preview</title><style>"
                "body{font-family:sans-serif;max-width:820px;margin:24px auto;color:#222}"
                "section{border:1px solid #ccc;border-radius:8px;margin:18px 0;padding:14px}"
                ".meta{background:#f4f4f4;padding:8px;border-radius:6px;font-size:13px;margin-bottom:10px}"
                f"</style><h1>{len(rows)} emails</h1>" + "".join(blocks))
        open(self.preview, "w").write(page)
        print(f"Preview written: {self.preview}")

    # --- sending ---------------------------------------------------------------------------

    def smtp_send(self, msg, rcpts):
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=30) as s:
            s.login(os.environ["GMAIL_USER"], os.environ["GMAIL_APP_PASSWORD"])
            s.send_message(msg, to_addrs=rcpts)

    def already_sent(self):
        if not os.path.exists(self.send_log):
            return set()
        with open(self.send_log) as f:
            return {(row["row"], row["to"]) for row in csv.DictReader(f) if row["status"] == "sent"}

    def log(self, r, status, message_id):
        new = not os.path.exists(self.send_log)
        with open(self.send_log, "a", newline="") as f:
            w = csv.writer(f)
            if new:
                w.writerow(["timestamp", "row", "name", "category", "to", "cc", "status", "message_id"])
            w.writerow([time.strftime("%Y-%m-%d %H:%M:%S"), r["_row"], self.label(r), self.col(r, "category"),
                        self.col(r, "to"), self.col(r, "cc"), status, message_id])
            f.flush()
            os.fsync(f.fileno())

    def run_test(self, rows):
        picks = {}
        for r in rows:
            picks.setdefault(self.col(r, "category"), r)
        widest = max(rows, key=lambda r: len(split_addrs(self.col(r, "to"))) + len(split_addrs(self.col(r, "cc"))))
        tests = list(picks.values()) + ([widest] if widest not in picks.values() else [])
        for r in tests:
            msg, rcpts = self.build_message(r, test=True)
            self.smtp_send(msg, rcpts)
            print(f"TEST sent to self: #{r['_row']} {self.label(r)} ({len(rcpts)} aliases)")
            time.sleep(self.cfg.get("pause_seconds", 3))

    def run_send(self, rows):
        done = self.already_sent()
        sent = skipped = 0
        for r in rows:
            if (str(r["_row"]), self.col(r, "to")) in done:
                skipped += 1
                continue
            msg, rcpts = self.build_message(r)
            try:
                self.smtp_send(msg, rcpts)
            except Exception as e:
                self.log(r, f"error: {e}", msg["Message-ID"])
                sys.exit(f"STOPPED at row {r['_row']} ({self.label(r)}): {e}. Sent this run: {sent}.")
            self.log(r, "sent", msg["Message-ID"])
            sent += 1
            print(f"[{sent}] sent #{r['_row']} {self.label(r)}")
            time.sleep(self.cfg.get("pause_seconds", 3))
        print(f"Done. Sent {sent}, skipped (already sent) {skipped}, total rows {len(rows)}.")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--hash", action="store_true")
    mode.add_argument("--test", action="store_true")
    mode.add_argument("--send", action="store_true")
    args = ap.parse_args()

    job = Job(args.config)
    if args.hash:
        print(job.sha())
        return
    load_env()
    rows = job.load_and_validate()
    job.write_preview(rows)
    if not (args.test or args.send):
        print("Dry run: nothing sent.")
        return
    if not os.environ.get("GMAIL_USER") or not os.environ.get("GMAIL_APP_PASSWORD"):
        sys.exit("GMAIL_USER / GMAIL_APP_PASSWORD missing from .env.")
    job.run_test(rows) if args.test else job.run_send(rows)


if __name__ == "__main__":
    main()
