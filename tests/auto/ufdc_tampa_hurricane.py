"""Search La gaceta (Tampa, UF00028296) Oct 1944 issues for hurricane coverage.
Bilingual paper — check both English 'hurricane' and Spanish 'huracan'.
"""
import json
import re
import urllib.parse
import urllib.request
from pathlib import Path

BASE = "https://api.patron.uflib.ufl.edu"
HERE = Path(__file__).resolve().parent
OUT = HERE / "ufdc_tampa_hurricane.json"

BIBID = "UF00028296"
# From ufdc_all_1944_coverage.json: vids 10099-10111 are Oct 12-26, 1944
VIDS = [
    ("10099", "1944-10-12"), ("10100", "1944-10-13"), ("10101", "1944-10-14"),
    ("10102", "1944-10-16"), ("10103", "1944-10-17"), ("10104", "1944-10-18"),
    ("10105", "1944-10-19"), ("10106", "1944-10-20"), ("10107", "1944-10-21"),
    ("10108", "1944-10-23"), ("10109", "1944-10-24"), ("10110", "1944-10-25"),
    ("10111", "1944-10-26"),
]


def get(path, params):
    url = BASE + path + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": "hc/0.1"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read()), url


def grab_pagetext(bibid, vid):
    """Fetch full-text of an issue via /pagetext."""
    data, url = get("/pagetext", {"bibid": bibid, "vid": vid})
    return data, url


results = []
for vid, date in VIDS:
    try:
        data, url = grab_pagetext(BIBID, vid)
    except Exception as e:
        print(f"  {vid} ({date}) ERROR {e}")
        continue
    # /pagetext returns {hits: [{pageorder, pagetext, ...}, ...]}
    pages = data.get("hits") or []
    hits = []
    for p in pages:
        text = p.get("pagetext") or ""
        if not isinstance(text, str): continue
        lo = text.lower()
        for kw in ("hurricane", "huracan", "huracán", "ciclon", "ciclón", "cyclone", "tormenta"):
            for m in re.finditer(kw, lo):
                ctx_start = max(0, m.start() - 120)
                ctx_end = min(len(text), m.end() + 220)
                snip = text[ctx_start:ctx_end]
                snip = re.sub(r"\s+", " ", snip).strip()
                hits.append({
                    "keyword": kw,
                    "pageorder": p.get("pageorder"),
                    "pageid": p.get("pageid"),
                    "thumbnail": p.get("thumbnail"),
                    "snippet": snip[:400],
                })
                break  # one hit per keyword per page is enough
    issue_url = f"https://ufdc.ufl.edu/{BIBID}/{vid}"
    print(f"  {vid} ({date})  pages={len(pages)}  hurricane-hits={len(hits)}")
    if hits:
        print(f"    first snip: {hits[0]['snippet'][:150]}")
    results.append({
        "vid": vid, "date": date, "url": issue_url,
        "pages": len(pages), "hits": hits,
    })

OUT.write_text(json.dumps(results, indent=2))
print(f"\nSaved {OUT}")
total = sum(1 for r in results if r["hits"])
print(f"Issues with hurricane hits: {total}/{len(results)}")
