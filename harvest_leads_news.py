"""
Daily harvest step — funding-news RSS feeds as sourcing channels.

Unlike BetaList (self-submitted launches) and Apollo (a lagging company index),
these are journalist-curated funding announcements — higher quality bar by
construction, and often state the actual amount raised in the headline, which
lets us finally enforce the investor's <=$1M pre-seed/seed requirement in code
instead of guessing.

Sources (both explicitly allow ClaudeBot / have no AI-crawler block in robots.txt):
  - tech.eu   — European tech/startup funding news
  - wamda.com — MENA (Middle East/North Africa) startup funding news
"""

import html
import json
import os
import re
import xml.etree.ElementTree as ET

import requests

CACHE_PATH = os.path.join(os.path.dirname(__file__), "leads_cache.json")

FEEDS = [
    {"source": "tech.eu", "url": "https://tech.eu/feed"},
    {"source": "Wamda", "url": "https://www.wamda.com/feed"},
]

MAX_FUNDING_USD = 1_500_000  # soft ceiling with a little slack over $1M for FX/estimation noise

FX_TO_USD = {"$": 1.0, "€": 1.08, "£": 1.27}

AMOUNT_RE = re.compile(
    r"([$€£])\s?(\d+(?:\.\d+)?)\s*([MmKkBb]|million|billion|thousand)?", re.IGNORECASE
)
SUFFIX_MULTIPLIER = {
    "k": 1_000, "thousand": 1_000,
    "m": 1_000_000, "million": 1_000_000,
    "b": 1_000_000_000, "billion": 1_000_000_000,
}


def strip_html(raw: str) -> str:
    text = re.sub(r"<[^>]+>", " ", raw or "")
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def parse_funding_usd(title: str):
    """Take the largest amount mentioned — conservative for a <=cap filter:
    if any figure in the headline implies a bigger raise, treat it as bigger
    rather than risk under-counting and letting an over-cap company through."""
    matches = AMOUNT_RE.findall(title)
    if not matches:
        return None

    best = None
    for symbol, number, suffix in matches:
        value = float(number) * SUFFIX_MULTIPLIER.get(suffix.lower(), 1_000_000)
        value_usd = value * FX_TO_USD.get(symbol, 1.0)
        if best is None or value_usd > best:
            best = value_usd
    return best


def fetch_feed(source: str, url: str):
    resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=20)
    resp.raise_for_status()
    root = ET.fromstring(resp.content)

    entries = []
    for item in root.findall(".//item"):
        title = item.findtext("title", default="")
        link = item.findtext("link", default="")
        desc = item.findtext("description", default="")
        categories = [c.text for c in item.findall("category") if c.text]
        pub_date = item.findtext("pubDate", default="")

        funding_usd = parse_funding_usd(title)

        entries.append({
            "slug": link.strip(),
            "name": title.split("–")[0].split("—")[0].split(":")[0].strip()[:80],
            "tagline": strip_html(title),
            "description": strip_html(desc) + (f" | Tags: {', '.join(categories)}" if categories else ""),
            "published": pub_date,
            "betalist_url": "",
            "website": link.strip(),
            "source": source,
            "founded_year": None,
            "funding_usd": funding_usd,
            "scored": False,
            "added_to_sheet": False,
        })
    return entries


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
    known_links = {c["slug"] for c in cache if c.get("source") in ("tech.eu", "Wamda")}

    total_new = 0
    for feed in FEEDS:
        entries = fetch_feed(feed["source"], feed["url"])
        new_entries = [e for e in entries if e["slug"] not in known_links]
        print(f"{feed['source']}: {len(entries)} items, {len(new_entries)} new")

        for e in new_entries:
            over_cap = e["funding_usd"] is not None and e["funding_usd"] > MAX_FUNDING_USD
            tag = " [OVER FUNDING CAP, will be filtered]" if over_cap else ""
            print(f"  + {e['name']} — funding: {e['funding_usd']}{tag}")
            cache.append(e)
            known_links.add(e["slug"])
            total_new += 1

    save_cache(cache)
    print(f"\nNew news-feed candidates: {total_new}")
    print(f"Cache total: {len(cache)} entries -> {CACHE_PATH}")


if __name__ == "__main__":
    main()
