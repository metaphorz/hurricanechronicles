"""Probe UFDC's fdnl_titles_list endpoint and map each archive city -> bibids
of newspapers that have coverage overlapping 1944.

Writes tests/auto/ufdc_titles_1944.json with:
  {
    "<archive-id>": [
       {"bibid": "...", "title": "...", "date_start": "...", "date_end": "...",
        "county": "...", "city": "..."}
    ],
    ...
  }

Also prints a short report.
"""
from __future__ import annotations

import json
import sys
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "tests" / "auto" / "ufdc_titles_1944.json"
RAW = ROOT / "tests" / "auto" / "ufdc_titles_raw.json"

BASE = "https://api.patron.uflib.ufl.edu"

# Archive id -> (city tokens we accept as a match against the UFDC title metadata)
# Tokens are substrings matched case-insensitively against title/city/county.
CITY_TOKENS = {
    "key-west":         ["key west", "monroe"],
    "dry-tortugas":     ["key west", "monroe"],
    "sarasota":         ["sarasota"],
    "fort-myers-beach": ["fort myers", "lee", "estero"],
    "tampa":            ["tampa", "st. petersburg", "saint petersburg",
                         "hillsborough", "pinellas"],
    "orlando":          ["orlando", "orange", "sanford", "seminole"],
    "jacksonville":     ["jacksonville", "duval"],
    "fernandina-beach": ["fernandina", "amelia", "nassau"],
}


def fetch(path, params=None):
    url = BASE + path
    if params:
        url += "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={
        "User-Agent": "HurricaneChronicles/0.1",
        "Accept": "application/json",
    })
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())


def year_range(rec):
    """Return (lo, hi) year ints from min_date/max_date, or (None, None)."""
    def yr(v):
        if not v: return None
        s = str(v)
        return int(s[:4]) if len(s) >= 4 and s[:4].isdigit() else None
    return (yr(rec.get("min_date")), yr(rec.get("max_date")))


def matches_city(rec, tokens):
    hay = " ".join(str(rec.get(k, "") or "") for k in
                   ("title", "city", "county", "place", "publisher"))
    hay = hay.lower()
    return any(tok in hay for tok in tokens)


def main():
    print("Fetching fdnl_titles_list ...")
    try:
        data = fetch("/fdnl_titles_list")
    except Exception as e:
        print(f"  error: {e}")
        sys.exit(1)

    # Shape is unknown — try common containers.
    if isinstance(data, dict):
        for key in ("titles", "results", "data", "items"):
            if key in data and isinstance(data[key], list):
                records = data[key]
                break
        else:
            print(f"  unexpected dict keys: {list(data.keys())[:20]}")
            RAW.write_text(json.dumps(data, indent=2)[:200000])
            print(f"  raw sample saved to {RAW}")
            sys.exit(1)
    elif isinstance(data, list):
        records = data
    else:
        print(f"  unexpected type: {type(data).__name__}")
        sys.exit(1)

    print(f"  got {len(records)} records")
    RAW.write_text(json.dumps(records[:5], indent=2))
    print(f"  first 5 records saved to {RAW}")

    # Filter to papers whose date range includes 1944
    covers_1944 = []
    for r in records:
        lo, hi = year_range(r)
        if lo is None or hi is None:
            continue
        if lo <= 1944 <= hi:
            covers_1944.append(r)
    print(f"  covers 1944: {len(covers_1944)}")

    # Group by archive city
    out = {}
    for cid, tokens in CITY_TOKENS.items():
        hits = [r for r in covers_1944 if matches_city(r, tokens)]
        slim = []
        for r in hits:
            lo, hi = year_range(r)
            slim.append({
                "bibid": r.get("bibid") or r.get("bibID") or r.get("id") or "",
                "vid":   r.get("vid") or "",
                "title": r.get("title") or "",
                "city":  r.get("city") or "",
                "county": r.get("county") or "",
                "date_start": lo,
                "date_end": hi,
            })
        out[cid] = slim
        print(f"  {cid}: {len(slim)} papers covering 1944")
        for s in slim[:10]:
            print(f"      [{s['bibid']}] {s['title']!r}  "
                  f"{s['date_start']}-{s['date_end']}  ({s['city']}/{s['county']})")

    OUT.write_text(json.dumps(out, indent=2))
    print(f"\nWrote {OUT}")


if __name__ == "__main__":
    main()
