"""Scrape real individual items (photos + news) for each archive city.

Sources:
  * News  — Library of Congress / Chronicling America JSON API
            (florida newspapers, hurricane coverage, Oct-Nov 1944)
  * Photos — DPLA via Selenium (JS-rendered site); also Wikimedia Commons
             and Amelia Island PastPerfect items are preserved from the
             existing JSON.

Produces only real individual items. Per user directive: no kind=search
entries in the output — retrieve real records, or leave empty.
"""
from __future__ import annotations

import json
import time
import urllib.parse
import urllib.request
from pathlib import Path

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

ROOT = Path(__file__).resolve().parents[2]
STORM_JSON = ROOT / "data" / "storms" / "1944-cuba-florida.json"
LOG = ROOT / "tests" / "auto" / "scrape_archives.log"

MAX_NEWS_PER_CITY = 12
MAX_PHOTOS_PER_CITY = 16
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/605.1.15 "
      "(KHTML, like Gecko) Version/17.0 Safari/605.1.15")

# For cities with sparse direct coverage, also query these alternate terms.
# Results are merged and deduped by URL.
ALT_QUERIES = {
    "Dry Tortugas": ["Tortugas", "Florida Keys"],
    "Fort Myers Beach": ["Fort Myers", "Estero"],
    "Fernandina Beach": ["Fernandina", "Amelia Island"],
}


# ---------------------------------------------------------------------------
# Logging

def open_log():
    LOG.parent.mkdir(parents=True, exist_ok=True)
    return open(LOG, "w", buffering=1)


def log(logf, msg):
    line = f"[{time.strftime('%H:%M:%S')}] {msg}"
    print(line, flush=True)
    logf.write(line + "\n")


# ---------------------------------------------------------------------------
# News: Library of Congress JSON API (Chronicling America)

def fetch_loc_once(query, logf):
    q = urllib.parse.quote_plus(f"{query} hurricane")
    url = (f"https://www.loc.gov/search/?q={q}"
           f"&fa=location:florida|partof:chronicling+america"
           f"&dates=1944&fo=json&c=40")
    log(logf, f"  LoC query '{query}' — {url}")
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    for attempt in (1, 2, 3):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.loads(r.read()).get("results", []) or []
        except Exception as e:
            log(logf, f"    attempt {attempt} error: {e}")
            time.sleep(2)
    return []


def fetch_loc_news(city, logf):
    """Return real Florida-newspaper issue records mentioning city + hurricane,
    biased toward October-November 1944."""
    queries = [city] + ALT_QUERIES.get(city, [])
    log(logf, f"LoC news: {city}  queries={queries}")
    results = []
    seen_ids = set()
    for q in queries:
        for r in fetch_loc_once(q, logf):
            rid = r.get("id") or ""
            if rid and rid not in seen_ids:
                seen_ids.add(rid)
                results.append(r)
    log(logf, f"  raw results merged: {len(results)}")

    items = []
    for r in results:
        date = r.get("date", "") or ""
        title = r.get("title", "") or ""
        url_ = r.get("id", "") or ""
        if not url_ or not title:
            continue
        # Prefer October and November 1944 issues (storm aftermath)
        relevance = 0
        if date.startswith("1944-10") or date.startswith("1944-11"):
            relevance = 2
        elif date.startswith("1944"):
            relevance = 1
        if relevance == 0:
            continue
        # Use first newspaper page image as a thumbnail when present
        thumb = None
        imgs = r.get("image_url") or []
        if imgs and isinstance(imgs, list):
            thumb = imgs[0]
        items.append({
            "kind": "item",
            "title": title[:160],
            "url": url_,
            "thumb": thumb,
            "description": (r.get("description") or [""])[0][:240]
                if isinstance(r.get("description"), list) else (r.get("description") or "")[:240],
            "date": date,
            "source": "Chronicling America (Library of Congress)",
            "_relevance": relevance,
        })
    items.sort(key=lambda x: (-x["_relevance"], x.get("date") or ""))
    for it in items:
        it.pop("_relevance", None)
    log(logf, f"  kept (1944 FL): {len(items)}")
    return items[:MAX_NEWS_PER_CITY]


# ---------------------------------------------------------------------------
# Photos: DPLA via Selenium

def build_driver(headless=True):
    opts = Options()
    if headless:
        opts.add_argument("--headless=new")
    opts.add_argument("--window-size=1400,1100")
    opts.add_argument("--disable-blink-features=AutomationControlled")
    opts.add_argument(f"--user-agent={UA}")
    return webdriver.Chrome(options=opts)


def scrape_dpla(driver, query, logf):
    url = f"https://dp.la/search?q={urllib.parse.quote_plus(query)}"
    log(logf, f"DPLA: {query} — {url}")
    driver.get(url)
    try:
        WebDriverWait(driver, 30).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "a[href*='/item/']"))
        )
    except Exception as e:
        log(logf, f"  dpla timeout: {e}")
        fail_path = ROOT / "tests" / "auto" / f"dpla_fail_{query.replace(' ', '_')[:40]}.html"
        try:
            fail_path.write_text(driver.page_source[:200000])
            log(logf, f"  wrote page source to {fail_path}")
        except Exception:
            pass
        return []
    time.sleep(2)

    anchors = driver.find_elements(By.CSS_SELECTOR, "a[href*='/item/']")
    log(logf, f"  item-link anchors: {len(anchors)}")

    seen = set()
    items = []
    for a in anchors:
        href = a.get_attribute("href") or ""
        if "/item/" not in href or href in seen:
            continue
        text = (a.text or "").strip()
        try:
            img = a.find_element(By.CSS_SELECTOR, "img")
            thumb = img.get_attribute("src") or None
        except Exception:
            thumb = None
        title = text if text and len(text) > 3 else ""
        if not title:
            continue
        # Try to find provider/source institution
        source = "Digital Public Library of America"
        try:
            container = a.find_element(By.XPATH, "./ancestor::*[self::article or self::li or contains(@class,'result')][1]")
            prov = container.find_elements(
                By.XPATH,
                ".//*[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'provided by')]"
            )
            if prov:
                t = prov[0].text.strip().replace("Provided by", "").strip()
                if t:
                    source = f"{t} (via DPLA)"
        except Exception:
            pass
        seen.add(href)
        items.append({
            "kind": "item",
            "title": title[:160],
            "url": href,
            "thumb": thumb,
            "source": source,
        })
        if len(items) >= MAX_PHOTOS_PER_CITY:
            break

    log(logf, f"  kept: {len(items)}")
    return items


# ---------------------------------------------------------------------------
# Main

def main():
    with open(STORM_JSON) as f:
        storm = json.load(f)

    logf = open_log()
    try:
        log(logf, f"Cities: {[a['city'] for a in storm['archives']]}")

        driver = build_driver(headless=True)
        try:
            for a in storm["archives"]:
                city_search = a["city"].split(" / ")[0]
                log(logf, f"\n=== {a['city']} ===")

                # Preserve only real curated items/collections, drop all search entries.
                curated_photos = [p for p in a.get("photos", [])
                                  if p.get("kind") in ("item", "collection")
                                  and "dp.la" not in (p.get("url") or "")]
                curated_news = [n for n in a.get("news", [])
                                if n.get("kind") in ("item", "collection")
                                and "loc.gov" not in (n.get("url") or "")]

                news_items = fetch_loc_news(city_search, logf)

                # DPLA: primary query + fallbacks if empty
                dpla_items = scrape_dpla(driver, f"{city_search} hurricane 1944", logf)
                if len(dpla_items) < 3:
                    for alt in ALT_QUERIES.get(city_search, []):
                        more = scrape_dpla(driver, f"{alt} hurricane 1944", logf)
                        seen = {p["url"] for p in dpla_items}
                        dpla_items.extend(p for p in more if p["url"] not in seen)
                        if len(dpla_items) >= MAX_PHOTOS_PER_CITY:
                            break

                a["photos"] = curated_photos + dpla_items
                a["news"] = curated_news + news_items

                log(logf, f"  -> photos {len(a['photos'])}, news {len(a['news'])}")
        finally:
            driver.quit()

        with open(STORM_JSON, "w") as f:
            json.dump(storm, f, indent=2)

        print(f"\nUpdated {STORM_JSON}")
        for a in storm["archives"]:
            print(f"  {a['city']}: {len(a['photos'])} photos, {len(a['news'])} news")
    finally:
        logf.close()


if __name__ == "__main__":
    main()
