"""
Watchdog — independent of n8n itself, so it can catch n8n being down entirely,
not just a broken trigger inside it. Checks that the most recent n8n workflow
execution happened within the expected window; if not, emails an alert.

Meant to run on its own launchd schedule (every 30 min), separate from n8n's
own scheduler, precisely so a failure in n8n doesn't also silence the alarm.
"""

import datetime
import os
import sys
from email.mime.text import MIMEText
import smtplib

import requests

N8N_API_KEY = os.environ.get("N8N_API_KEY")
GMAIL_USER = os.environ.get("GMAIL_USER")
GMAIL_APP_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD")
WORKFLOW_ID = "9z1m7OFAGBMEVFgb"
MAX_SILENCE_MINUTES = 30  # tightest cadence in the workflow is every 15 min

ALERT_EMAIL = "i.bon@pnptc.com"


def send_alert(subject, body):
    if not GMAIL_USER or not GMAIL_APP_PASSWORD:
        print("Cannot send alert — Gmail credentials not set.")
        return
    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = GMAIL_USER
    msg["To"] = ALERT_EMAIL
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=15) as s:
        s.login(GMAIL_USER, GMAIL_APP_PASSWORD)
        s.send_message(msg)


def main():
    if not N8N_API_KEY:
        sys.exit("Set N8N_API_KEY before running.")

    try:
        resp = requests.get(
            f"http://localhost:5678/api/v1/executions?limit=1&workflowId={WORKFLOW_ID}",
            headers={"X-N8N-API-KEY": N8N_API_KEY},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()["data"]
    except requests.RequestException as e:
        send_alert(
            "ALERT: n8n unreachable — automation may be down",
            f"Could not reach n8n's API at all: {e}\n\nThe automation pipeline (sourcing, outreach, follow-ups) is likely not running. Check the Mac / n8n process.",
        )
        print("n8n unreachable, alert sent.")
        return

    if not data:
        send_alert(
            "ALERT: n8n has no execution history",
            "n8n is reachable but reports zero executions for the pipeline workflow. Something is wrong with the workflow itself.",
        )
        print("No executions found, alert sent.")
        return

    last_started = data[0]["startedAt"]
    last_dt = datetime.datetime.fromisoformat(last_started.replace("Z", "+00:00"))
    now = datetime.datetime.now(datetime.timezone.utc)
    minutes_since = (now - last_dt).total_seconds() / 60

    print(f"Last execution: {last_started} ({minutes_since:.1f} minutes ago)")

    if minutes_since > MAX_SILENCE_MINUTES:
        send_alert(
            "ALERT: pipeline automation appears stuck",
            f"The last n8n execution for the startup pipeline workflow was {minutes_since:.0f} minutes ago "
            f"(expected at least every {MAX_SILENCE_MINUTES} minutes). The automation may have silently stopped — "
            f"check n8n on the Mac.",
        )
        print("Silence threshold exceeded, alert sent.")
    else:
        print("Healthy — within expected window.")


if __name__ == "__main__":
    main()
