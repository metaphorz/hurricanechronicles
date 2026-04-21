"""Check if the date filter actually narrows results, and find total-count + pagination."""
import json
import urllib.parse
import urllib.request

BASE = "https://api.patron.uflib.ufl.edu"


def get(params):
    url = BASE + "/exactsearch?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": "hc/0.1"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read()), url


def summarize(label, data, url):
    print(f"\n=== {label} ===\n  {url}")
    # Top-level keys (look for total, numFound, etc.)
    if isinstance(data, dict):
        non_list_keys = {k: v for k, v in data.items() if not isinstance(v, list)}
        print(f"  top-level non-list fields: {non_list_keys}")
        # results
        for key in ("results", "docs", "items", "hits", "rows"):
            if key in data and isinstance(data[key], list):
                rows = data[key]
                print(f"  {key}: {len(rows)}")
                for r in rows[:50]:
                    pd = r.get("publication_date")
                    if isinstance(pd, list): pd = pd[0] if pd else ""
                    vid = r.get("vid", "")
                    print(f"    vid={vid}  date={pd}")
                break


# Narrow — Oct 12-26 1944
data, url = get({
    "fulltext": "hurricane",
    "publication_date": "1944-10-12 TO 1944-10-26",
    "bibid": "UF00079944",
})
summarize("NARROW 1944-10-12..26", data, url)

# No filter — should return top-25 of all Orlando Sentinel hurricane mentions
data, url = get({
    "fulltext": "hurricane",
    "bibid": "UF00079944",
})
summarize("NO FILTER", data, url)

# Wider — all of 1944
data, url = get({
    "fulltext": "hurricane",
    "publication_date": "1944-01-01 TO 1944-12-31",
    "bibid": "UF00079944",
})
summarize("ALL 1944", data, url)

# Test ask for rows/pagination with a big number
data, url = get({
    "fulltext": "hurricane",
    "publication_date": "1944-10-12 TO 1944-10-26",
    "bibid": "UF00079944",
    "rows": 200,
})
summarize("NARROW rows=200", data, url)
