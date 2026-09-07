"""
Daily harvest step — Apollo company search as a second sourcing channel,
targeted at hardware/deep-tech/industrial companies (BetaList skews consumer/
SMB software, this fills the physical-product gap).

Apollo has no real-time company database — its newest indexed founding years
lag reality by months, so unlike BetaList (true "founded this year" launches),
here we accept founded_year within the last ~18 months as the early-stage proxy.

Adds candidates into the same leads_cache.json used by harvest_leads.py, tagged
with source="Apollo", so select_leads.py scores everything together.
"""

import html
import json
import os
import re
import sys

import requests

APOLLO_KEY = os.environ.get("APOLLO_KEY")
if not APOLLO_KEY:
    sys.exit("Set the APOLLO_KEY environment variable before running this script.")

CACHE_PATH = os.path.join(os.path.dirname(__file__), "leads_cache.json")
SEARCH_URL = "https://api.apollo.io/api/v1/mixed_companies/search"

KEYWORD_TAGS = [
    "robotics", "hardware", "industrial automation", "iot", "sensors",
    "deep tech", "medical devices", "energy hardware", "manufacturing automation",
    "aerospace", "materials science", "logistics automation",
]
LOCATIONS = ["Europe", "United States", "United Kingdom", "Middle East"]
EMPLOYEE_RANGE = "1,50"
MIN_FOUNDED_YEAR = 2025  # ~last 18 months, given Apollo's indexing lag (see module docstring)
MAX_PAGES = 6
MAX_NEW_PER_RUN = 30


def strip_html(raw: str) -> str:
    text = re.sub(r"<[^>]+>", " ", raw or "")
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


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
        return " — ".join(parts)[:500]
    except requests.RequestException:
        return ""


def load_cache():
    if os.path.exists(CACHE_PATH):
        with open(CACHE_PATH) as f:
            return json.load(f)
    return []


def save_cache(cache):
    with open(CACHE_PATH, "w") as f:
        json.dump(cache, f, indent=2, ensure_ascii=False)


def main():
    cache = load_cache()
    known_domains = {c["slug"] for c in cache if c.get("source") == "Apollo"}

    new_count = 0
    for page in range(1, MAX_PAGES + 1):
        if new_count >= MAX_NEW_PER_RUN:
            break

        resp = requests.post(
            SEARCH_URL,
            headers={"x-api-key": APOLLO_KEY, "Content-Type": "application/json"},
            json={
                "q_organization_keyword_tags": KEYWORD_TAGS,
                "organization_locations": LOCATIONS,
                "organization_num_employees_ranges": [EMPLOYEE_RANGE],
                "sort_by_field": "organization_founded_year",
                "sort_ascending": False,
                "page": page,
                "per_page": 50,
            },
            timeout=30,
        )
        if resp.status_code != 200:
            print(f"  ⚠ Apollo {resp.status_code}: {resp.text[:150]}")
            break

        orgs = resp.json().get("organizations") or resp.json().get("accounts") or []
        if not orgs:
            break

        print(f"Page {page}: {len(orgs)} orgs returned")

        for o in orgs:
            if new_count >= MAX_NEW_PER_RUN:
                break

            founded = o.get("founded_year")
            domain = o.get("primary_domain") or ""
            if not founded or founded < MIN_FOUNDED_YEAR or not domain:
                continue
            if domain in known_domains:
                continue

            website = o.get("website_url") or f"https://{domain}"
            summary = fetch_homepage_summary(website)

            entry = {
                "slug": domain,
                "name": o.get("name", "").strip(),
                "tagline": "",
                "description": summary,
                "published": "",
                "betalist_url": "",
                "website": website.split("?")[0].rstrip("/"),
                "source": "Apollo",
                "founded_year": founded,
                "scored": False,
                "added_to_sheet": False,
            }
            cache.append(entry)
            known_domains.add(domain)
            new_count += 1
            print(f"  + cached: {entry['name']} ({entry['website']}) — founded {founded}")

    save_cache(cache)
    print(f"\nNew Apollo candidates this run: {new_count}")
    print(f"Cache total: {len(cache)} entries -> {CACHE_PATH}")


if __name__ == "__main__":
    main()
