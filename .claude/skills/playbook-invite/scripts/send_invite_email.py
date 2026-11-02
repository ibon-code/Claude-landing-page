"""
Playbook invite email: the standard note sent to a founder AFTER their profile exists on Playbook and they
were added to its Team (Playbook sends its own invitation at that moment). Template from the old
send_playbook_invite.py.

  python3 send_invite_email.py --to EMAIL --name "First Last" --startup "Acme"            # preview only
  python3 send_invite_email.py --to EMAIL --name "First Last" --startup "Acme" --send     # real send

Safety:
- Preview by default; --send is required to send.
- Hard block: refuses to send if Gmail Sent already holds a "Playbook invite" email to this address
  (Gmail's own indexed search, from 2025 on), so the same founder can never get it twice.
- Prints the Message-ID and date to write into the Pipeline sheet.
Credentials: GMAIL_USER / GMAIL_APP_PASSWORD from the repo .env (read in Python, never printed).
"""
import argparse
import datetime
import imaplib
import os
import re
import smtplib
import sys
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formatdate, make_msgid

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
sys.path.insert(0, ROOT)
from email_signature import SIGNATURE_HTML  # noqa: E402

PLAYBOOK_URL = "https://app.playbook.vc"
PARTNERS_URL = "https://www.plugandplaytechcenter.com/innovation-services/corporations/our-corporate-partners"
EMAIL_RE = re.compile(r"^[^@\s,;<>]+@[^@\s,;<>]+\.[A-Za-z]{2,}$")

TEXT = """Hi {greeting},

It was a pleasure speaking with you, I really enjoyed learning about {startup} and your team.

I sent you an invitation to complete the profile at {playbook}. Can you check to see if you can log in? Your profile there should serve as a starting point to apply your company to meet with our partners and network. The invitation expires after 48 hours.

Additionally, here is the list of our corporate partners for reference: {partners}

Please keep me posted on your project's progress, and I would love to receive your deck if you have one!

Best,

Iacopo"""

HTML = """<p>Hi {greeting},</p>
<p>It was a pleasure speaking with you, I really enjoyed learning about {startup} and your team.</p>
<p>I sent you an invitation to complete the profile at <a href="{playbook}">{playbook}</a>. Can you check to see if you can log in? Your profile there should serve as a starting point to apply your company to meet with our partners and network. <strong>The invitation expires after 48 hours.</strong></p>
<p>Additionally, <a href="{partners}">here is the list of our corporate partners</a> for reference.</p>
<p>Please keep me posted on your project's progress, and I would love to receive your deck if you have one!</p>
<p>Best,</p>
{signature}"""


def load_env():
    for line in open(os.path.join(ROOT, ".env")):
        if "=" in line and not line.lstrip().startswith("#"):
            k, v = line.strip().split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def already_sent(user, password, to):
    m = imaplib.IMAP4_SSL("imap.gmail.com")
    m.login(user, password)
    m.select('"[Gmail]/Sent Mail"', readonly=True)
    q = f"in:sent to:{to} subject:(Playbook invite) after:2025/01/01"
    typ, data = m.search(None, "X-GM-RAW", f'"{q}"')
    m.logout()
    if typ != "OK":
        sys.exit("Gmail search failed - not sending (fail closed).")
    return len(data[0].split())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--to", required=True)
    ap.add_argument("--name", default="")
    ap.add_argument("--startup", required=True)
    ap.add_argument("--send", action="store_true")
    a = ap.parse_args()

    to = a.to.strip().lower()
    if not EMAIL_RE.match(to):
        sys.exit(f"Invalid email: {to!r}")
    first = (a.name.split() or [""])[0].strip(",.")
    greeting = first if re.match(r"^[^\W\d_][\w'’-]{1,24}$", first) else f"{a.startup} team"
    subject = f"Plug and Play - {a.startup} Playbook invite"
    fields = dict(greeting=greeting, startup=a.startup, playbook=PLAYBOOK_URL, partners=PARTNERS_URL)
    text = TEXT.format(**fields)
    html = HTML.format(**fields, signature=SIGNATURE_HTML)

    load_env()
    user, pwd = os.environ.get("GMAIL_USER"), os.environ.get("GMAIL_APP_PASSWORD")
    if not user or not pwd:
        sys.exit("GMAIL_USER / GMAIL_APP_PASSWORD missing from .env.")
    n = already_sent(user, pwd, to)

    print(f"To: {to}\nSubject: {subject}\n\n{text}\n")
    if n:
        sys.exit(f"BLOCKED: Gmail Sent already has {n} 'Playbook invite' email(s) to {to}. Nothing sent.")
    if not a.send:
        print("PREVIEW ONLY - nothing sent (add --send).")
        return

    msg = MIMEMultipart("alternative")
    msg["From"] = f"Iacopo Bon <{user}>"
    msg["To"] = to
    msg["Subject"] = subject
    msg["Date"] = formatdate(localtime=True)
    msg["Message-ID"] = make_msgid(domain=user.split("@")[1])
    msg.attach(MIMEText(text, "plain", "utf-8"))
    msg.attach(MIMEText(html, "html", "utf-8"))
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=30) as s:
        s.login(user, pwd)
        s.sendmail(user, [to], msg.as_string())
    print(f"SENT {datetime.datetime.now():%Y-%m-%d %H:%M} | Message-ID {msg['Message-ID']}")


if __name__ == "__main__":
    main()
