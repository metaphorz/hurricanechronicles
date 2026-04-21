"""For each candidate bibid in ufdc_titles_1944.json, use /all_vids_in_bibid
to find the actual 1944-10-12..26 issues (min_date/max_date had gaps).
"""
import json
import re
import urllib.parse
import urllib.request
from pathlib import Path

BASE = "https://api.patron.uflib.ufl.edu"
HERE = Path(__file__).resolve().parent
TITLES = json.loads((HERE / "ufdc_titles_1944.json").read_text())
OUT = HERE / "ufdc_real1944.json"

MONTHS = {"January":1,"February":2,"March":3,"April":4,"May":5,"June":6,
          "July":7,"August":8,"September":9,"October":10,"November":11,"December":12}

def parse_iso(pd):
    if not pd: return None
    first = pd[0] if isinstance(pd, list) else pd
    if not isinstance(first, str): return None
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", first)
    if m: return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    m = re.match(r"(\w+)\s+(\d{1,2}),?\s+(\d{4})", first)
    if m and m.group(1) in MONTHS:
        return f"{m.group(3)}-{MONTHS[m.group(1)]:02d}-{int(m.group(2)):02d}"
    return None


def fetch_vids(bibid):
    url = BASE + "/all_vids_in_bibid?" + urllib.parse.urlencode(
        {"bibid": bibid, "size": 10000, "start": 0})
    req = urllib.request.Request(url, headers={"User-Agent": "hc/0.1"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read())


# Collect unique bibids + label them by archive city
bibid_to_cities = {}
bibid_to_title = {}
for city, records in TITLES.items():
    for rec in records:
        b = rec["bibid"]
        bibid_to_cities.setdefault(b, set()).add(city)
        bibid_to_title[b] = rec["title"]

# Also probe a wider pool — scan ALL bibids in fdnl that cover 1944 period
# by min/max, regardless of city filter (in case city filter was too narrow)
print(f"Scanning {len(bibid_to_cities)} bibids from ufdc_titles_1944.json\n")
results = {}
for bibid, cities in sorted(bibid_to_cities.items()):
    try:
        vids = fetch_vids(bibid)
    except Exception as e:
        print(f"  {bibid:15s} ERROR {e}")
        continue
    oct44 = []
    year_counter = {}
    for rec in vids:
        iso = parse_iso(rec.get("PublicationDate"))
        if iso:
            year_counter[iso[:4]] = year_counter.get(iso[:4], 0) + 1
            if "1944-10-12" <= iso <= "1944-10-26":
                oct44.append({"vid": rec.get("vid"), "date": iso})
    has1944 = year_counter.get("1944", 0)
    print(f"  {bibid:15s} cities={sorted(cities)!s:40s}  "
          f"title='{bibid_to_title[bibid][:40]}'  "
          f"total={len(vids):<5} 1944={has1944:<4} oct44_window={len(oct44)}")
    results[bibid] = {
        "title": bibid_to_title[bibid],
        "cities": sorted(cities),
        "total_vids": len(vids),
        "year_counts": year_counter,
        "oct44_vids": oct44,
    }

OUT.write_text(json.dumps(results, indent=2))
print(f"\nsaved to {OUT}")

# Summary
wins = {b: v for b, v in results.items() if v["oct44_vids"]}
print(f"\nbibids with 1944-10-12..26 vids: {len(wins)}")
for b, v in wins.items():
    print(f"  {b} ({v['title']}): {len(v['oct44_vids'])} issues")
