"""Find a publication_date query syntax that actually filters to 1944."""
import json
import urllib.parse
import urllib.request

BASE = "https://api.patron.uflib.ufl.edu"


def q(params, label):
    url = BASE + "/exactsearch?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": "hc/0.1"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            data = json.loads(r.read())
    except Exception as e:
        print(f"{label:40s} ERROR: {e}")
        return
    hc = data.get("hit_count", "?")
    results = data.get("results") or []
    # Count how many results actually fall in 1944-10-12..26
    ok = 0
    for rr in results:
        pd = rr.get("publication_date")
        if isinstance(pd, list): pd = pd[0] if pd else ""
        if not pd: continue
        if "1944" in pd and ("Oct" in pd or "-10-" in pd):
            ok += 1
    print(f"{label:40s} hit_count={hc:<5} shown={len(results):<3} oct44_actual={ok}")


# Baseline
q({"bibid": "UF00079944"}, "bibid only")
q({"bibid": "UF00079944", "fulltext": "hurricane"}, "bibid + fulltext:hurricane")

# Date variants
q({"bibid": "UF00079944", "fulltext": "hurricane",
   "publication_date": "1944-10-12 TO 1944-10-26"}, "plain TO (no brackets)")
q({"bibid": "UF00079944", "fulltext": "hurricane",
   "publication_date": "[1944-10-12 TO 1944-10-26]"}, "[brackets]")
q({"bibid": "UF00079944", "fulltext": "hurricane",
   "publication_date": "{1944-10-12 TO 1944-10-26}"}, "{braces}")

# With conv_date, which is mentioned in the field list and may be an ISO-normalized form
q({"bibid": "UF00079944", "fulltext": "hurricane",
   "conv_date": "[1944-10-12 TO 1944-10-26]"}, "conv_date [brackets]")
q({"bibid": "UF00079944", "fulltext": "hurricane",
   "conv_date": "1944-10-12 TO 1944-10-26"}, "conv_date plain")
q({"bibid": "UF00079944", "fulltext": "hurricane",
   "conv_date": "1944-10-*"}, "conv_date wildcard")

# Date as single token (exact year)
q({"bibid": "UF00079944", "fulltext": "hurricane",
   "publication_date": "October 19, 1944"}, "exact date")
q({"bibid": "UF00079944", "fulltext": "hurricane",
   "publication_date": "1944"}, "just 1944")

# Default query field with date inside
q({"bibid": "UF00079944", "fulltext": "hurricane",
   "default": "publication_date:[1944-10-12 TO 1944-10-26]"}, "default=pd:[...]")
