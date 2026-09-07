"""
Daily harvest step — pulls new entries from BetaList's Atom feed into a local
cache, resolving each startup's real website.

Why daily: BetaList's feed only keeps ~25 most-recent entries, and turns over
roughly every 1-2 days. Running the scoring/selection step just once a week
would silently miss most of the week's listings — so harvesting must run more
often than the feed rotates, independent of how often leads are scored/added
to the sheet (see select_leads.py, run weekly).
"""

import html
import json
import os
import re
import xml.etree.ElementTree as ET

import requests

FEED_URL = "https://feeds.feedburner.com/BetaList"
CACHE_PATH = os.path.join(os.path.dirname(__file__), "leads_cache.json")


def strip_html(raw: str) -> str:
    text = re.sub(r"<[^>]+>", " ", raw or "")
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def fetch_feed_entries():
    resp = requests.get(FEED_URL, headers={"User-Agent": "Mozilla/5.0"}, timeout=20)
    resp.raise_for_status()
    ns = {"atom": "http://www.w3.org/2005/Atom"}
    root = ET.fromstring(resp.content)

    entries = []
    for entry in root.findall("atom:entry", ns):
        entry_id = entry.findtext("atom:id", default="", namespaces=ns)
        title = entry.findtext("atom:title", default="", namespaces=ns)
        content = entry.findtext("atom:content", default="", namespaces=ns)
        published = entry.findtext("atom:published", default="", namespaces=ns)

        slug = entry_id.rstrip("/").split("/")[-1]
        if " – " in title:
            name, tagline = title.split(" – ", 1)
        elif " - " in title:
            name, tagline = title.split(" - ", 1)
        else:
            name, tagline = title, ""

        entries.append({
            "slug": slug,
            "name": name.strip(),
            "tagline": tagline.strip(),
            "description": strip_html(content),
            "published": published,
            "betalist_url": f"https://betalist.com/startups/{slug}",
            "source": "BetaList",
            "founded_year": None,
        })
    return entries


def resolve_website(slug: str) -> str:
    try:
        r = requests.get(
            f"https://betalist.com/startups/{slug}/visit",
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=15,
            allow_redirects=True,
        )
        return r.url.split("?")[0].rstrip("/")
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
    known_slugs = {c["slug"] for c in cache}

    entries = fetch_feed_entries()
    new_entries = [e for e in entries if e["slug"] not in known_slugs]

    print(f"Feed entries seen: {len(entries)}  |  New: {len(new_entries)}")

    for e in new_entries:
        e["website"] = resolve_website(e["slug"])
        e["scored"] = False
        e["added_to_sheet"] = False
        cache.append(e)
        print(f"  + cached: {e['name']} ({e['website']})")

    save_cache(cache)
    print(f"Cache total: {len(cache)} entries -> {CACHE_PATH}")


if __name__ == "__main__":
    main()
