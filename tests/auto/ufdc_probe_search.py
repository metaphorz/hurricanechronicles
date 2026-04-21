"""Probe: can /exactsearch return 1944 hurricane pages from UFDC newspaper bibids?

Uses bibids we verified have 1944 coverage:
  UF00079944 — Orlando morning sentinel (3228 issues, 1918-1947)
  UF00048666 — Key West Citizen (5812 issues, 1879-1954)
"""
import json
import urllib.parse
import urllib.request

BASE = "https://api.patron.uflib.ufl.edu"


def get(path, params):
    url = BASE + path + "?" + urllib.parse.urlencode(params)
    print(f"\nGET {url}")
    req = urllib.request.Request(url, headers={"User-Agent": "hc/0.1"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        body = e.read()[:400]
        print(f"  HTTP {e.code}: {body!r}")
        try: return json.loads(body)
        except: return None


def dump(label, data, nrows=3):
    if not isinstance(data, dict):
        print(f"  {label}: not a dict → {type(data).__name__}")
        return
    if data.get("error"):
        print(f"  {label} ERROR: {data.get('error')} / {data.get('error_field')}")
        return
    # Find the results container
    for key in ("results", "docs", "items", "hits", "rows"):
        if key in data and isinstance(data[key], list):
            rows = data[key]
            print(f"  {label}: {len(rows)} {key}")
            for row in rows[:nrows]:
                print(f"    {json.dumps(row, indent=2)[:800]}")
            return
    # No common container — print top-level keys
    print(f"  {label} keys: {list(data.keys())[:20]}")
    # And a shallow dump of first value lists
    for k, v in list(data.items())[:6]:
        if isinstance(v, list):
            print(f"    {k}: list of {len(v)}")
            if v and nrows > 0:
                print(f"      [0] = {json.dumps(v[0], indent=2)[:600]}")
        else:
            print(f"    {k}: {str(v)[:120]}")


# Orlando Sentinel, narrow window
dump("orlando_narrow",
     get("/exactsearch", {
         "fulltext": "hurricane",
         "publication_date": "1944-10-12 TO 1944-10-26",
         "bibid": "UF00079944",
     }))

# Key West Citizen, narrow window
dump("keywest_narrow",
     get("/exactsearch", {
         "fulltext": "hurricane",
         "publication_date": "1944-10-12 TO 1944-10-26",
         "bibid": "UF00048666",
     }))

# Try alternate date-range syntax
dump("orlando_altdate",
     get("/exactsearch", {
         "fulltext": "hurricane",
         "publication_date": "[1944-10-12 TO 1944-10-26]",
         "bibid": "UF00079944",
     }))

# Try simpler: just year 1944 (no range)
dump("orlando_justyear",
     get("/exactsearch", {
         "fulltext": "hurricane",
         "publication_date": "1944",
         "bibid": "UF00079944",
     }))

# Baseline — no filter
dump("orlando_nofilter",
     get("/exactsearch", {
         "fulltext": "hurricane",
         "bibid": "UF00079944",
     }), nrows=1)
