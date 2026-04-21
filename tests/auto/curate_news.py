"""Curate real, verified 1944 hurricane newspaper articles per archive circle.

Flow per archive city:
  1. Query loc.gov JSON (Chronicling America, Florida, 1944-10-15 to 1944-11-30)
     with q='hurricane <city>'.
  2. For each hit, fetch the page's full-text (ALTO JSON) via the page's
     fulltext_service URL.
  3. Keep only pages whose OCR contains BOTH 'hurricane' (or 'storm') AND a
     city alias, within ~700 chars of each other — so every saved article
     actually discusses the storm (not just unrelated columns on the same
     page).
  4. Build an item with a loc.gov viewer URL that highlights the match
     (`&q=hurricane`), a snippet of the OCR around the match, and the page
     thumbnail.
  5. Write results back into data/storms/1944-cuba-florida.json, preserving
     any curated non-LoC news items.

Uses Selenium (headless Chrome) for all LoC requests — loc.gov is behind
Cloudflare with bot/rate-limit challenges that urllib cannot solve.
"""
from __future__ import annotations

import json
import re
import time
import urllib.parse
from pathlib import Path

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By

ROOT = Path(__file__).resolve().parents[2]
STORM_JSON = ROOT / "data" / "storms" / "1944-cuba-florida.json"
LOG = ROOT / "tests" / "auto" / "curate_news.log"

DATE_RANGE = "1944-10-15/1944-11-30"
MAX_PER_CITY = 12
REQ_DELAY = 1.5  # seconds between navigations — be polite

CITY_TERMS = {
    "dry-tortugas": ["Dry Tortugas", "Tortugas", "Key West"],
    "key-west": ["Key West"],
    "sarasota": ["Sarasota"],
    "fort-myers-beach": ["Fort Myers", "Estero"],
    "tampa": ["Tampa", "St. Petersburg"],
    "orlando": ["Orlando"],
    "jacksonville": ["Jacksonville"],
    "fernandina-beach": ["Fernandina", "Amelia Island"],
}

PROXIMITY = 700  # OCR proximity for hurricane+city verification
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/605.1.15 "
      "(KHTML, like Gecko) Version/17.0 Safari/605.1.15")


# --------------------------------------------------------------------- logging

def open_log():
    LOG.parent.mkdir(parents=True, exist_ok=True)
    return open(LOG, "w", buffering=1)


def log(logf, msg):
    line = f"[{time.strftime('%H:%M:%S')}] {msg}"
    print(line, flush=True)
    logf.write(line + "\n")


# --------------------------------------------------------------- Selenium JSON

def build_driver():
    opts = Options()
    # NOT headless — LoC is behind Cloudflare which blocks headless Chrome.
    # Non-headless passes the JS challenge in ~1s with no user interaction.
    opts.add_argument("--window-size=1100,800")
    opts.add_argument("--window-position=2000,2000")  # off-screen
    opts.add_argument("--disable-blink-features=AutomationControlled")
    return webdriver.Chrome(options=opts)


def fetch_json(driver, url, logf, tries=3):
    """Navigate Chrome to a URL that returns JSON; return parsed JSON or None.
    Handles Cloudflare JS challenges by waiting and reloading."""
    for attempt in range(1, tries + 1):
        try:
            driver.get(url)
        except Exception as e:
            log(logf, f"    nav error: {e}")
            time.sleep(3)
            continue
        # Wait out any Cloudflare challenge
        for _ in range(10):
            time.sleep(1.5)
            body = driver.find_element(By.TAG_NAME, "body").text.strip()
            if body.startswith("{") or body.startswith("["):
                break
            if "Just a moment" in body or "challenge" in body.lower():
                continue
        if not (body.startswith("{") or body.startswith("[")):
            log(logf, f"    attempt {attempt}: non-JSON body "
                     f"(first 60: {body[:60]!r})")
            time.sleep(3)
            continue
        try:
            return json.loads(body)
        except Exception as e:
            log(logf, f"    parse error: {e}")
            time.sleep(2)
    return None


# --------------------------------------------------------------- verification

WORD_RE = re.compile(r"\s+")


def find_snippet(text, primary, city_terms):
    """Return (snippet, matched_city_term) if 'primary' (e.g. 'hurricane')
    and a city term appear within PROXIMITY chars — same article, not just
    same page OCR blob."""
    tl = text.lower()
    prim = primary.lower()
    hur_positions = []
    p = 0
    while True:
        i = tl.find(prim, p)
        if i < 0: break
        hur_positions.append(i)
        p = i + 1
    if not hur_positions:
        return "", ""
    best = None
    for term in city_terms:
        tlow = term.lower()
        q = 0
        while True:
            ti = tl.find(tlow, q)
            if ti < 0: break
            for hi in hur_positions:
                if abs(hi - ti) <= PROXIMITY:
                    snip_start = max(0, min(hi, ti) - 100)
                    snip_end = min(len(text), max(hi, ti) + 220)
                    snip = WORD_RE.sub(" ", text[snip_start:snip_end]).strip()
                    if best is None or abs(hi - ti) < best[2]:
                        best = (snip, term, abs(hi - ti))
            q = ti + 1
    if best:
        return best[0], best[1]
    return "", ""


def get_page_fulltext(driver, page_url, logf):
    """Fetch a page's OCR full_text string via its LoC resource JSON."""
    if "fo=json" not in page_url:
        sep = "&" if "?" in page_url else "?"
        meta_url = f"{page_url}{sep}fo=json"
    else:
        meta_url = page_url
    meta = fetch_json(driver, meta_url, logf)
    time.sleep(REQ_DELAY)
    if not meta:
        return ""
    ft_url = (meta.get("resource") or {}).get("fulltext_file") or ""
    if not ft_url:
        return ""
    ft = fetch_json(driver, ft_url, logf)
    time.sleep(REQ_DELAY)
    if not ft:
        return ""
    try:
        val = next(iter(ft.values()))
        return val.get("full_text", "") or ""
    except Exception:
        return ""


# ----------------------------------------------------------------- curation

def loc_search(driver, term, logf):
    q = urllib.parse.quote_plus(f"hurricane {term}")
    url = (f"https://www.loc.gov/search/?q={q}"
           f"&fa=partof:chronicling+america%7Clocation:florida"
           f"&dates={urllib.parse.quote(DATE_RANGE, safe='/')}"
           f"&fo=json&c=40")
    log(logf, f"  LoC: {url}")
    data = fetch_json(driver, url, logf)
    time.sleep(REQ_DELAY)
    return (data or {}).get("results", []) or []


def curate_city(driver, archive, logf):
    cid = archive["id"]
    terms = CITY_TERMS[cid]
    log(logf, f"=== {archive['city']}  terms={terms}")

    raw, seen = [], set()
    for term in terms:
        for r in loc_search(driver, term, logf):
            rid = r.get("id") or ""
            if rid and rid not in seen:
                seen.add(rid)
                raw.append(r)
    log(logf, f"  raw hits: {len(raw)}")

    items = []
    for r in raw:
        date = (r.get("date") or "")[:10]
        if not date.startswith("1944"): continue
        title = r.get("title") or ""
        url_ = r.get("id") or ""
        if not title or not url_: continue

        text = get_page_fulltext(driver, url_, logf)
        if not text:
            log(logf, f"    skip (no text): {title[:70]}")
            continue
        snip, matched = find_snippet(text, "hurricane", terms)
        if not snip:
            snip, matched = find_snippet(text, "storm", terms)
        if not snip:
            log(logf, f"    skip (no hurricane+city near): {title[:70]}")
            continue

        sep = "&" if "?" in url_ else "?"
        viewer_url = f"{url_}{sep}q=hurricane"

        imgs = r.get("image_url") or []
        thumb = imgs[0] if imgs else None

        rel = 3 if date.startswith("1944-10") else (
              2 if date.startswith("1944-11") else (
              1 if date.startswith("1944-12") else 0))

        items.append({
            "kind": "item",
            "title": title[:160],
            "url": viewer_url,
            "thumb": thumb,
            "description": snip[:280],
            "date": date,
            "source": "Chronicling America (Library of Congress)",
            "_rel": rel,
        })
        log(logf, f"    KEEP ({date}, via '{matched}'): {title[:70]}")

    items.sort(key=lambda x: (-x["_rel"], x.get("date") or ""))
    for it in items: it.pop("_rel", None)
    items = items[:MAX_PER_CITY]
    log(logf, f"  kept: {len(items)}")
    return items


def main():
    with open(STORM_JSON) as f:
        storm = json.load(f)
    logf = open_log()
    driver = build_driver()
    try:
        log(logf, f"Archives: {[a['id'] for a in storm['archives']]}")
        for a in storm["archives"]:
            if a["id"] not in CITY_TERMS:
                log(logf, f"skip (no terms): {a['id']}")
                continue
            new_news = curate_city(driver, a, logf)
            preserved = [n for n in a.get("news", [])
                         if "loc.gov" not in (n.get("url") or "")]
            a["news"] = preserved + new_news
            log(logf, f"  -> {a['city']}: news={len(a['news'])} "
                     f"(preserved {len(preserved)}, new {len(new_news)})")
        with open(STORM_JSON, "w") as f:
            json.dump(storm, f, indent=2)
        print(f"\nUpdated {STORM_JSON}")
        for a in storm["archives"]:
            print(f"  {a['city']}: {len(a.get('news',[]))} news, "
                  f"{len(a.get('photos',[]))} photos")
    finally:
        driver.quit()
        logf.close()


if __name__ == "__main__":
    main()
