"""Scan every UFDC newspaper whose min_date<=1944<=max_date for real 1944-10-12..26 vids.
My city-filtered list was too narrow; walk the whole fdnl_titles_list instead.
"""
import json
import re
import time
import urllib.parse
import urllib.request
from pathlib import Path

BASE = "https://api.patron.uflib.ufl.edu"
HERE = Path(__file__).resolve().parent
OUT = HERE / "ufdc_all_1944_coverage.json"

MONTHS = {"January":1,"February":2,"March":3,"April":4,"May":5,"June":6,
          "July":7,"August":8,"September":9,"October":10,"November":11,"December":12}

def parse_iso(pd):
    first = pd[0] if isinstance(pd, list) and pd else pd
    if not isinstance(first, str): return None
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", first)
    if m: return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    m = re.match(r"(\w+)\s+(\d{1,2}),?\s+(\d{4})", first)
    if m and m.group(1) in MONTHS:
        return f"{m.group(3)}-{MONTHS[m.group(1)]:02d}-{int(m.group(2)):02d}"
    return None


def get(path, params):
    url = BASE + path + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": "hc/0.1"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read())


# Fetch complete fdnl titles list
titles = get("/fdnl_titles_list", {"size": 10000, "start": 0})
print(f"fdnl_titles_list: {len(titles)} records")

# Filter to those with min_date<=1944<=max_date
def year(s):
    if not s: return None
    m = re.search(r"(\d{4})", str(s))
    return int(m.group(1)) if m else None

candidates = []
for rec in titles:
    mn = year(rec.get("min_date") or rec.get("PublicationDateStart"))
    mx = year(rec.get("max_date") or rec.get("PublicationDateEnd"))
    if mn and mx and mn <= 1944 <= mx:
        candidates.append(rec)
print(f"candidates covering 1944 by min/max: {len(candidates)}")

# Unique bibids
seen = {}
for rec in candidates:
    b = rec.get("bibid")
    if b and b not in seen:
        seen[b] = rec
print(f"unique bibids: {len(seen)}\n")

results = {}
for i, (bibid, rec) in enumerate(sorted(seen.items()), 1):
    try:
        vids = get("/all_vids_in_bibid",
                   {"bibid": bibid, "size": 50000, "start": 0})
    except Exception as e:
        print(f"  [{i:3d}/{len(seen)}] {bibid} ERROR {e}")
        continue
    oct_win = []
    any_1944 = 0
    for v in vids:
        iso = parse_iso(v.get("PublicationDate"))
        if iso and iso.startswith("1944"):
            any_1944 += 1
            if "1944-10-12" <= iso <= "1944-10-26":
                oct_win.append({"vid": v.get("vid"), "date": iso,
                                "pagecount": v.get("pagecount")})
    title = rec.get("title") or rec.get("Title") or ""
    county = rec.get("county") or rec.get("County") or ""
    city = rec.get("city") or rec.get("City") or rec.get("PlaceOfPublication") or ""
    mark = "✅" if oct_win else ("·" if any_1944 else " ")
    print(f"  [{i:3d}/{len(seen)}] {mark} {bibid:15s} {title[:45]:45s} "
          f"city={city[:20]:20s} county={county[:15]:15s} 1944={any_1944:<4} oct44={len(oct_win)}")
    if oct_win or any_1944:
        results[bibid] = {
            "title": title,
            "city": city,
            "county": county,
            "total_vids": len(vids),
            "vids_in_1944": any_1944,
            "oct44_window": oct_win,
        }

OUT.write_text(json.dumps(results, indent=2))

wins = {b: v for b, v in results.items() if v["oct44_window"]}
print(f"\n=== bibids with 1944-10-12..26 vids: {len(wins)} ===")
for b, v in sorted(wins.items()):
    print(f"  {b}: {v['title']} ({v['city'] or v['county']}) "
          f"— {len(v['oct44_window'])} issues")
print(f"\nsaved to {OUT}")
