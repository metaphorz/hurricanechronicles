"""Curate DPLA items (photos/documents) per archive circle using the DPLA API.

Uses the DPLA v2 API (https://api.dp.la/v2/items). Requires DPLA_API_KEY in
~/.env. Queries each archive city with its aliases plus 'hurricane 1944',
keeps only items that (a) have a thumbnail URL, (b) are image/document type,
(c) mention the city in title/description.

Writes results back to data/storms/1944-cuba-florida.json, preserving any
previously curated non-DPLA photo items.
"""
from __future__ import annotations

import json
import os
import time
import urllib.parse
import urllib.request
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
STORM_JSON = ROOT / "data" / "storms" / "1944-cuba-florida.json"
LOG = ROOT / "tests" / "auto" / "curate_dpla.log"

MAX_PER_CITY = 15
REQ_DELAY = 0.5  # DPLA rate limit: 10 req/sec burst, stay well under

CITY_TERMS = {
    "dry-tortugas":    ["Dry Tortugas", "Tortugas"],
    "key-west":        ["Key West"],
    "sarasota":        ["Sarasota"],
    "fort-myers-beach":["Fort Myers", "Estero Island"],
    "tampa":           ["Tampa", "St. Petersburg"],
    "orlando":         ["Orlando"],
    "jacksonville":    ["Jacksonville"],
    "fernandina-beach":["Fernandina", "Amelia Island"],
}


def log(logf, msg):
    line = f"[{time.strftime('%H:%M:%S')}] {msg}"
    print(line, flush=True)
    logf.write(line + "\n")


def first(v):
    if isinstance(v, list):
        return v[0] if v else ""
    return v or ""


def api_search(api_key, query, logf):
    qs = urllib.parse.urlencode({
        "q": query,
        "page_size": 50,
        "api_key": api_key,
    })
    url = f"https://api.dp.la/v2/items?{qs}"
    log(logf, f"  DPLA: q={query!r}")
    req = urllib.request.Request(url, headers={"User-Agent": "HurricaneChronicles/0.1"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            data = json.loads(r.read())
    except Exception as e:
        log(logf, f"    error: {e}")
        return []
    time.sleep(REQ_DELAY)
    return data.get("docs", []) or []


import re as _re

_YEAR_RE = _re.compile(r"(1[89]\d{2}|20\d{2})")


def _date_includes_1944(date_val):
    """Accept only items whose date evidence covers 1944. Reject when date is
    clearly outside (e.g. single year 1964), and also reject when no date is
    available (too risky — most modern DPLA hurricane hits have no date)."""
    if not date_val:
        return False
    # Normalize to a string we can search
    if isinstance(date_val, list):
        date_val = date_val[0] if date_val else ""
    if isinstance(date_val, dict):
        date_val = (date_val.get("displayDate") or date_val.get("begin")
                    or date_val.get("end") or "")
    s = str(date_val)
    # If it's a single 4-digit year, accept only 1944
    ys = _YEAR_RE.findall(s)
    if not ys:
        return False
    # If any year token is exactly 1944 → accept
    if "1944" in ys:
        return True
    # If it's a range (has two years), accept if 1944 falls inside
    if len(ys) >= 2:
        try:
            lo, hi = int(ys[0]), int(ys[1])
            if lo <= 1944 <= hi:
                return True
        except Exception:
            pass
    # Narrow window tolerance: a single year within 1944 ±2 is acceptable
    try:
        if any(1942 <= int(y) <= 1946 for y in ys):
            return True
    except Exception:
        pass
    return False


def extract_item(doc, terms):
    """Convert a DPLA doc → archive item, or None if not relevant/usable."""
    src = doc.get("sourceResource", {}) or {}
    title = first(src.get("title"))
    if not title:
        return None

    desc = first(src.get("description")) or ""
    # Date: DPLA gives structured or string
    date_raw = src.get("date")
    if not _date_includes_1944(date_raw):
        return None
    date = date_raw
    if isinstance(date, list): date = date[0] if date else ""
    if isinstance(date, dict): date = date.get("displayDate", "") or ""
    date = date or ""

    # Require city term in title OR description
    haystack = (title + " " + desc).lower()
    matched = next((t for t in terms if t.lower() in haystack), "")
    if not matched:
        return None

    # Type filter: image / text
    types = src.get("type")
    if isinstance(types, list): types = [t.lower() for t in types]
    else: types = [str(types).lower()] if types else []
    if types and not any(t in ("image", "text", "physicalobject") for t in types):
        return None

    url = doc.get("isShownAt") or (doc.get("@id") or "")
    if not url:
        return None

    # Thumb — DPLA 'object' field is the preview image URL
    thumb = doc.get("object") or None

    provider = (doc.get("provider") or {}).get("name", "") or ""
    dp = first(doc.get("dataProvider"))
    if isinstance(dp, dict):
        dp = dp.get("name", "") or ""
    data_provider = dp or ""
    source_label = data_provider or provider or "Digital Public Library of America"
    if "dpla" not in source_label.lower():
        source_label = f"{source_label} (via DPLA)"

    return {
        "kind": "item",
        "title": title[:160],
        "url": url,
        "thumb": thumb,
        "description": desc[:240],
        "date": str(date)[:30],
        "source": source_label,
        "_matched": matched,
    }


def curate_city(api_key, archive, logf):
    terms = CITY_TERMS[archive["id"]]
    log(logf, f"=== {archive['city']}  terms={terms}")

    queries = []
    for t in terms:
        queries.append(f"{t} hurricane 1944")
        queries.append(f"{t} hurricane")

    seen_urls = set()
    items = []
    for q in queries:
        for doc in api_search(api_key, q, logf):
            it = extract_item(doc, terms)
            if not it: continue
            if it["url"] in seen_urls: continue
            seen_urls.add(it["url"])
            items.append(it)
            log(logf, f"    KEEP [{it['_matched']}] {it['title'][:70]}")
            if len(items) >= MAX_PER_CITY: break
        if len(items) >= MAX_PER_CITY: break

    for it in items: it.pop("_matched", None)
    log(logf, f"  kept: {len(items)}")
    return items


def main():
    load_dotenv(os.path.expanduser("~/.env"))
    api_key = os.environ.get("DPLA_API_KEY")
    if not api_key:
        raise SystemExit("DPLA_API_KEY not set in ~/.env")

    with open(STORM_JSON) as f:
        storm = json.load(f)

    LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG, "w", buffering=1) as logf:
        log(logf, f"Archives: {[a['id'] for a in storm['archives']]}")
        for a in storm["archives"]:
            if a["id"] not in CITY_TERMS:
                continue
            new_items = curate_city(api_key, a, logf)

            # Preserve photos NOT previously added via DPLA
            preserved = [p for p in a.get("photos", [])
                         if "DPLA" not in (p.get("source") or "")
                         and "dp.la" not in (p.get("url") or "")]
            a["photos"] = preserved + new_items
            log(logf, f"  -> {a['city']}: photos={len(a['photos'])} "
                     f"(preserved {len(preserved)}, new {len(new_items)})")

    with open(STORM_JSON, "w") as f:
        json.dump(storm, f, indent=2)

    print(f"\nUpdated {STORM_JSON}")
    for a in storm["archives"]:
        print(f"  {a['city']}: {len(a.get('news',[]))} news, "
              f"{len(a.get('photos',[]))} photos")


if __name__ == "__main__":
    main()
