"""Inspect UFDC records for titles we expect to have 1944 coverage but lost."""
import json
import urllib.parse
import urllib.request

BASE = "https://api.patron.uflib.ufl.edu"

WANTED = [
    "venice gondolier",
    "florida catholic",
    "jacksonville free press",
    "southern jewish",
    "la gaceta",
    "key west citizen",
    "sarasota",
    "estero",
    "fort myers",
]

req = urllib.request.Request(BASE + "/fdnl_titles_list",
    headers={"User-Agent": "HurricaneChronicles/0.1"})
with urllib.request.urlopen(req, timeout=60) as r:
    recs = json.loads(r.read())

print(f"Total: {len(recs)}")
for rec in recs:
    title = (rec.get("title") or "").lower()
    if any(w in title for w in WANTED):
        print(json.dumps({
            "bibid": rec.get("bibid"),
            "title": rec.get("title"),
            "county": rec.get("county"),
            "min_date": rec.get("min_date"),
            "max_date": rec.get("max_date"),
            "vids_per_bibid": rec.get("vids_per_bibid"),
        }, indent=2))
