"""
Outreach step — for each Pipeline row with an email and not yet contacted,
personalizes the template (founder name, industry, 1-2 relevant PNP partners)
via Claude and sends it through Gmail SMTP.

Safety: DRY_RUN defaults to True — prints the generated email instead of
sending. Flip to False (or pass --send) only once you've reviewed sample
output and are happy with it. This runs automatically every 15 minutes via
the n8n "Every 15min - Check Pipeline" trigger — approving a row (Salesforce
= TRUE) is enough to fire a live send on the next cycle.
"""

import datetime
import json
import os
import re
import smtplib
import sys
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import openpyxl
import requests

from email_signature import SIGNATURE_HTML

FILE_PATH = "/Users/iacopobon/Desktop/Claude code experiment/Apollo enrich/Nuove liste/Sourcing Summer challange.xlsx"
PIPELINE_SHEET = "Pipeline"
PARTNERS_PATH = os.path.join(os.path.dirname(__file__), "pnp_partners_reference.json")

DRY_RUN = "--send" not in sys.argv
MAX_EMAILS_PER_RUN = 20  # safety cap even once sending is live
MAX_OUTREACH_PER_STARTUP = 3  # hard cap on total automated touches (outreach + follow-up + playbook invite + playbook follow-up)

ANTHROPIC_KEY = os.environ.get("ANTHROPIC_API_KEY")
GMAIL_USER = os.environ.get("GMAIL_USER")
GMAIL_APP_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD")
CALENDLY_LINK = "https://calendly.com/i-bon"

if not ANTHROPIC_KEY:
    sys.exit("Set ANTHROPIC_API_KEY before running.")
if not DRY_RUN and (not GMAIL_USER or not GMAIL_APP_PASSWORD):
    sys.exit("Set GMAIL_USER / GMAIL_APP_PASSWORD before sending for real.")

CLAUDE_MODEL = "claude-haiku-4-5-20251001"

TEMPLATE = """Hi {greeting},
I came across {startup_name} while mapping out startups in the {industry} space.
I'm on the Ventures team at Plug and Play Tech Center. We invest at the early stage (early backers of Dropbox, PayPal and Honey), but the bigger part of our model is commercial: we run innovation programs for corporate partners and introduce startups to the ones actively looking. In {industry} that includes {partners}.
Even if you aren't currently fundraising, I'd love to learn more about what you're building and see if there might be potential alignment with our ecosystem down the line.
Are you open to a quick 30 minute intro chat this week? Feel free to reply directly, or grab a slot on my calendar here: {calendly_link}

Best,

Iacopo Bon"""

HTML_TEMPLATE = """\
<p>Hi {greeting},</p>
<p>I came across {startup_name} while mapping out startups in the {industry} space.</p>
<p>I'm on the Ventures team at Plug and Play Tech Center. We invest at the early stage (early backers of Dropbox, PayPal and Honey), but the bigger part of our model is commercial: we run innovation programs for corporate partners and introduce startups to the ones actively looking. In {industry} that includes {partners}.</p>
<p>Even if you aren't currently fundraising, I'd love to learn more about what you're building and see if there might be potential alignment with our ecosystem down the line.</p>
<p>Are you open to a quick 30 minute intro chat this week? Feel free to reply directly, or grab a slot on my calendar here: <a href="{calendly_link}">{calendly_link}</a></p>
<p>Best,</p>
{signature}
"""


def is_checked(value) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().upper() == "TRUE"
    return False


def load_partners():
    with open(PARTNERS_PATH) as f:
        return json.load(f)


def strip_html(raw: str) -> str:
    text = re.sub(r"<[^>]+>", " ", raw or "")
    text = re.sub(r"\s+", " ", text).strip()
    return text


def fetch_homepage_summary(url: str) -> str:
    if not url:
        return ""
    try:
        r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
        title = re.search(r"<title[^>]*>(.*?)</title>", r.text, re.IGNORECASE | re.DOTALL)
        desc = re.search(
            r'<meta[^>]+name=["\']description["\'][^>]+content=["\'](.*?)["\']',
            r.text, re.IGNORECASE,
        )
        parts = []
        if title:
            parts.append(strip_html(title.group(1)))
        if desc:
            parts.append(strip_html(desc.group(1)))
        return " — ".join(parts)[:400]
    except requests.RequestException:
        return ""


def personalize(name, website, job_title, founder_name, partners_by_industry):
    site_summary = fetch_homepage_summary(website)
    prompt = (
        "You are helping personalize a VC outreach email. Given a startup, pick the single best-fitting "
        "industry category from this list of Plug and Play corporate-partner verticals, and 1-2 of the "
        "most plausibly relevant partner names from that category's list:\n\n"
        + json.dumps(partners_by_industry, ensure_ascii=False)
        + f"\n\nStartup: {name}\nWebsite: {website}\n"
        + f"What the startup's own homepage says about itself: {site_summary or 'not available'}\n"
        + f"Founder/contact title: {job_title or 'unknown'}\n"
        + f"Founder/contact name on file: {founder_name or 'unknown'}\n\n"
        + "Base the industry classification primarily on what the homepage says, not on the company name alone.\n"
        + "Return ONLY JSON (no prose, no markdown fences): "
        + '{"greeting": "...", "industry": "...", "partners": "..."}\n'
        + "greeting: the founder's first name if founder_name looks like a real person's name, "
        + f"otherwise \"{name}'s team\".\n"
        + "industry: a natural, human-readable phrase for the vertical (e.g. \"mobility and physical AI\"), "
        + "not the all-caps category label.\n"
        + 'partners: 1-2 partner names joined naturally, e.g. "BMW Group and Bosch" or "PepsiCo".'
    )

    resp = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key": ANTHROPIC_KEY,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        json={"model": CLAUDE_MODEL, "max_tokens": 300, "messages": [{"role": "user", "content": prompt}]},
        timeout=30,
    )
    resp.raise_for_status()
    text = resp.json()["content"][0]["text"].strip()
    text = re.sub(r"^```(json)?", "", text).strip()
    text = re.sub(r"```$", "", text).strip()
    return json.loads(text)


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
    partners_by_industry = load_partners()

    wb = openpyxl.load_workbook(FILE_PATH)
    ws = wb[PIPELINE_SHEET]
    headers = [c.value for c in ws[1]]
    col = {h: i + 1 for i, h in enumerate(headers) if h}

    sent = 0
    print(f"Mode: {'DRY RUN (no emails sent)' if DRY_RUN else 'LIVE SEND'}")
    print("-" * 55)

    for row in range(2, ws.max_row + 1):
        if sent >= MAX_EMAILS_PER_RUN:
            break

        name = ws.cell(row, col["Startup name "]).value
        website = ws.cell(row, col["Website"]).value
        email = ws.cell(row, col.get("Email", 0)).value if "Email" in col else None
        job_title = ws.cell(row, col.get("Job title", 0)).value if "Job title" in col else None
        founder_name = ws.cell(row, col.get("Full Name", 0)).value if "Full Name" in col else None
        contacted = ws.cell(row, col.get("Contacted ", 0)).value if "Contacted " in col else None
        salesforce_approved = ws.cell(row, col.get("Salesforce", 0)).value if "Salesforce" in col else None
        outreach_count = ws.cell(row, col.get("Outreach Count", 0)).value if "Outreach Count" in col else 0

        if not name or not email or contacted or not is_checked(salesforce_approved):
            continue
        if "Outreach Count" in col and int(outreach_count or 0) >= MAX_OUTREACH_PER_STARTUP:
            print(f"{name} <{email}> — outreach cap ({MAX_OUTREACH_PER_STARTUP}) already reached, skipping")
            continue

        try:
            info = personalize(name, website, job_title, founder_name, partners_by_industry)
        except Exception as e:
            print(f"  !! personalize failed for {name}: {e}")
            continue
        format_args = dict(
            greeting=info["greeting"],
            startup_name=name,
            industry=info["industry"],
            partners=info["partners"],
            calendly_link=CALENDLY_LINK,
        )
        body = TEMPLATE.format(**format_args)
        html_body = HTML_TEMPLATE.format(**format_args, signature=SIGNATURE_HTML)
        subject = f"Plug and Play <> {name}"

        print(f"\n=== {name} <{email}> ===")
        print(f"Subject: {subject}")
        print(body)
        print("-" * 55)

        if not DRY_RUN:
            try:
                send_email(email, subject, body, html_body)
            except Exception as e:
                print(f"  !! send failed for {name} <{email}>: {e}")
                continue
            ws.cell(row, col["Contacted "]).value = True
            if "Date Contacted" in col:
                ws.cell(row, col["Date Contacted"]).value = datetime.date.today().isoformat()
            if "Followed Up" in col:
                ws.cell(row, col["Followed Up"]).value = False
            if "Outreach Count" in col:
                ws.cell(row, col["Outreach Count"]).value = int(outreach_count or 0) + 1
            wb.save(FILE_PATH)  # save immediately so a later crash (e.g. SMTP disconnect) can't lose this send's flag and cause a resend
            print("  -> sent")

        sent += 1

    print(f"\n{'Would process' if DRY_RUN else 'Processed'}: {sent}")


if __name__ == "__main__":
    main()
