"""
Apollo.io email enrichment script.
Two-step flow per company:
  1. api_search  → find people at the domain, pick best title with has_email=True
  2. people/match → reveal full name + verified email

Writes: email → col C, full name → col D, job title → col E
Saves every 50 rows. Skips rows already having an email.
"""

import re
import time
import requests
import openpyxl

# ── Config ────────────────────────────────────────────────────────────────────
FILE_PATH  = "/Users/iacopobon/Desktop/Claude code experiment/Blanks - Startup Aereoports.xlsx"
API_KEY    = "REDACTED-ROTATE-ME"
SEARCH_URL = "https://api.apollo.io/v1/mixed_people/api_search"
MATCH_URL  = "https://api.apollo.io/v1/people/match"
DELAY      = 1.5    # seconds between company lookups
SAVE_EVERY = 50     # checkpoint save frequency

HEADERS = {
    "x-api-key":    API_KEY,
    "Content-Type": "application/json",
    "Accept":       "application/json",
}

PRIORITY_TITLES = [
    ["CEO", "Chief Executive Officer", "Founder", "Co-Founder", "Cofounder",
     "Owner", "President", "Managing Director", "General Manager"],
    ["COO", "CTO", "CFO", "CPO", "VP", "Vice President",
     "Head of", "Director", "Partner", "Principal"],
]

# ── Helpers ───────────────────────────────────────────────────────────────────

def extract_domain(cell_value):
    if not cell_value:
        return None
    s = str(cell_value).strip()
    m = re.search(r'HYPERLINK\("([^"]+)"', s, re.IGNORECASE)
    if m:
        s = m.group(1)
    s = re.sub(r'^https?://', '', s)
    s = re.sub(r'^www\.', '', s)
    return s.split('/')[0].split('?')[0].strip() or None


def title_rank(title: str) -> int:
    if not title:
        return 99
    t = title.lower()
    for rank, group in enumerate(PRIORITY_TITLES):
        if any(kw.lower() in t for kw in group):
            return rank
    return 99


def apollo_request(url, payload, retries=2):
    """POST to Apollo, handling rate limits with one automatic retry."""
    for attempt in range(retries + 1):
        try:
            r = requests.post(url, json=payload, headers=HEADERS, timeout=20)
        except requests.RequestException as e:
            print(f"    ⚠ Network error: {e}")
            return {}

        if r.status_code == 429:
            wait = 60 if attempt == 0 else 120
            print(f"    ⚠ Rate limited — sleeping {wait}s …")
            time.sleep(wait)
            continue

        if r.status_code != 200:
            print(f"    ⚠ Apollo {r.status_code}: {r.text[:120]}")
            return {}

        return r.json()

    return {}


def enrich_company(company: str, domain: str) -> tuple[str, str, str]:
    """
    Returns (email, full_name, title) — all empty strings on failure.
    """
    # Step 1 — search for people at this domain
    data = apollo_request(SEARCH_URL, {
        "page":                   1,
        "per_page":               10,
        "q_organization_domains": domain,
    })
    people = data.get("people") or []

    # Prefer people Apollo already knows have an email
    candidates = [p for p in people if p.get("has_email")]
    if not candidates:
        candidates = people   # fall back to anyone

    if not candidates:
        return "", "", ""

    # Step 2 — pick best title, then reveal via match
    best = min(candidates, key=lambda p: title_rank(p.get("title", "")))

    data2 = apollo_request(MATCH_URL, {"id": best["id"]})
    person = data2.get("person") or {}

    email = person.get("email") or ""
    name  = person.get("name") or \
            f"{person.get('first_name','')} {person.get('last_name','')}".strip()
    title = person.get("title") or person.get("headline") or ""

    return email, name, title


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    wb = openpyxl.load_workbook(FILE_PATH)
    ws = wb.active

    # Ensure column headers
    if not ws["D1"].value:
        ws["D1"] = "Full Name"
    if not ws["E1"].value:
        ws["E1"] = "Job Title"

    total   = ws.max_row - 1
    found   = 0
    skipped = 0
    no_result = 0

    for row_idx in range(2, ws.max_row + 1):
        company        = str(ws.cell(row_idx, 1).value or "").strip()
        domain         = extract_domain(ws.cell(row_idx, 2).value)
        existing_email = ws.cell(row_idx, 3).value
        progress       = f"Row {row_idx - 1}/{total}"

        if existing_email and str(existing_email).strip():
            print(f"{progress} — {company} — already enriched, skipping")
            skipped += 1
            continue

        if not company and not domain:
            print(f"{progress} — empty row, skipping")
            continue

        email, name, title = enrich_company(company, domain or "")

        if email:
            ws.cell(row_idx, 3).value = email
            ws.cell(row_idx, 4).value = name
            ws.cell(row_idx, 5).value = title
            found += 1
            print(f"{progress} — {company} — ✓ {email} ({name}, {title})")
        else:
            no_result += 1
            print(f"{progress} — {company} — no email found")

        # Checkpoint save every N rows
        if (row_idx - 1) % SAVE_EVERY == 0:
            wb.save(FILE_PATH)
            print(f"  ── checkpoint saved ({row_idx - 1}/{total} rows) ──")

        time.sleep(DELAY)

    wb.save(FILE_PATH)
    print(f"\n{'─'*55}")
    print(f"Done.  Found: {found}  |  No result: {no_result}  |  Skipped: {skipped}")
    print(f"File saved: {FILE_PATH}")


if __name__ == "__main__":
    main()
