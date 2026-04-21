"""Probe UFDC /pagetext endpoint to learn its response shape and date/phrase filters."""
import json
import urllib.parse
import urllib.request

BASE = "https://api.patron.uflib.ufl.edu"


def fetch(path, params):
    url = BASE + path + "?" + urllib.parse.urlencode(params)
    print(f"GET {url}")
    req = urllib.request.Request(url, headers={
        "User-Agent": "HurricaneChronicles/0.1",
        "Accept": "application/json",
    })
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        print(f"  HTTP {e.code}: {e.read()[:500]!r}")
        return None
    except Exception as e:
        print(f"  error: {e}")
        return None


# Try several shapes. We don't know which param-names the API wants.
attempts = [
    ("variant 1 (match_phrase)", "/pagetext", {
        "match_phrase": "hurricane",
        "datelo": "1944-10-12",
        "datehi": "1944-10-26",
        "bibid": "UF00079944",   # Orlando Morning Sentinel
    }),
    ("variant 2 (match_term_exact)", "/pagetext", {
        "match_term_exact": "hurricane",
        "datelo": "1944-10-12",
        "datehi": "1944-10-26",
        "bibid": "UF00079944",
    }),
    ("variant 3 (exactsearch)", "/exactsearch", {
        "phrase": "hurricane",
        "datelo": "1944-10-12",
        "datehi": "1944-10-26",
        "bibid": "UF00079944",
    }),
    ("variant 4 (pagetext global)", "/pagetext", {
        "match_phrase": "hurricane",
        "datelo": "1944-10-12",
        "datehi": "1944-10-26",
    }),
    ("variant 5 (exactsearch global)", "/exactsearch", {
        "phrase": "hurricane",
        "datelo": "1944-10-12",
        "datehi": "1944-10-26",
    }),
]

for label, path, params in attempts:
    print(f"\n=== {label} ===")
    data = fetch(path, params)
    if data is None:
        continue
    if isinstance(data, dict):
        print(f"  keys: {list(data.keys())[:15]}")
        # Print first element of list-valued keys
        for k, v in list(data.items())[:20]:
            if isinstance(v, list):
                print(f"  {k}: list of {len(v)}")
                if v:
                    print(f"    [0] = {json.dumps(v[0], indent=2)[:800]}")
            else:
                print(f"  {k}: {str(v)[:120]}")
    elif isinstance(data, list):
        print(f"  list of {len(data)}")
        if data:
            print(f"    [0] = {json.dumps(data[0], indent=2)[:800]}")
