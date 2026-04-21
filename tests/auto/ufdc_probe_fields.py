"""Dump the full 'choices_are' list for /pagetext and /exactsearch."""
import json
import urllib.parse
import urllib.request
from pathlib import Path

OUT = Path(__file__).resolve().parent / "ufdc_valid_fields.json"
BASE = "https://api.patron.uflib.ufl.edu"


def get(path, params):
    url = BASE + path + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": "hc/0.1"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())


out = {}
out["pagetext"] = get("/pagetext", {"bogus": "x"}).get("choices_are", [])
out["exactsearch"] = get("/exactsearch", {"bogus": "x"}).get("choices_are", [])
OUT.write_text(json.dumps(out, indent=2))
print(f"pagetext ({len(out['pagetext'])} fields): {out['pagetext']}")
print(f"\nexactsearch ({len(out['exactsearch'])} fields) — first 40:")
for f in out["exactsearch"][:40]:
    print(f"  {f}")
print(f"\nsaved to {OUT}")
