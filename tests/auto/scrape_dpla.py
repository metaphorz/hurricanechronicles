"""Scrape DPLA (Digital Public Library of America) for individual items per city.

Reads the storm JSON, for each archive city runs a DPLA search, extracts
up to N individual item records (title, URL, source institution, thumbnail),
and writes enriched items back into the JSON.

Uses Selenium + headless Chrome. Respects the project rule that every item
has a `source` field.
"""
from __future__ import annotations

import json
import sys
import time
import urllib.parse
from pathlib import Path

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

ROOT = Path(__file__).resolve().parents[2]
STORM_JSON = ROOT / "data" / "storms" / "1944-cuba-florida.json"
LOG = ROOT / "tests" / "auto" / "scrape_dpla.log"
MAX_ITEMS_PER_CITY = 12


def build_driver(headless=True):
    opts = Options()
    if headless:
        opts.add_argument("--headless=new")
    opts.add_argument("--window-size=1400,1000")
    opts.add_argument("--disable-blink-features=AutomationControlled")
    opts.add_argument("--user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15")
    return webdriver.Chrome(options=opts)


def log(msg, *, logf):
    line = f"[{time.strftime('%H:%M:%S')}] {msg}"
    print(line, flush=True)
    logf.write(line + "\n")
    logf.flush()


def scrape_dpla(driver, query, logf):
    """Run a DPLA search and extract result items."""
    url = f"https://dp.la/search?q={urllib.parse.quote_plus(query)}"
    log(f"DPLA search: {query}", logf=logf)
    log(f"  URL: {url}", logf=logf)
    driver.get(url)

    try:
        WebDriverWait(driver, 20).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "[data-testid='search-result'], article, .search-result, main a[href*='/item/']"))
        )
    except Exception as e:
        log(f"  timeout waiting for results: {e}", logf=logf)
        return []

    time.sleep(1.2)

    item_links = driver.find_elements(By.CSS_SELECTOR, "a[href*='/item/']")
    log(f"  raw item-link candidates: {len(item_links)}", logf=logf)

    seen = set()
    items = []
    for link in item_links:
        href = link.get_attribute("href") or ""
        if not href or "/item/" not in href:
            continue
        if href in seen:
            continue

        text = (link.text or "").strip()
        try:
            img = link.find_element(By.CSS_SELECTOR, "img")
            thumb = img.get_attribute("src") or ""
        except Exception:
            thumb = ""

        if text and len(text) > 3:
            title = text
        else:
            try:
                container = link.find_element(By.XPATH, "./ancestor::article | ./ancestor::*[contains(@class,'search-result')]")
                title_el = container.find_element(By.CSS_SELECTOR, "h2, h3, [class*='title']")
                title = (title_el.text or "").strip()
            except Exception:
                title = ""

        provider = ""
        try:
            container = link.find_element(By.XPATH, "./ancestor::article[1] | ./ancestor::*[contains(@class,'search-result')][1]")
            prov_el = container.find_element(
                By.XPATH,
                ".//*[contains(translate(text(),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'provider') or contains(@class,'provider') or contains(@class,'source')]"
            )
            provider = (prov_el.text or "").strip()
            provider = provider.replace("Provider:", "").strip().splitlines()[0]
        except Exception:
            provider = ""

        if not title:
            continue

        seen.add(href)
        items.append({
            "kind": "item",
            "title": title[:160],
            "url": href,
            "thumb": thumb or None,
            "source": provider or "Digital Public Library of America",
        })
        if len(items) >= MAX_ITEMS_PER_CITY:
            break

    log(f"  extracted {len(items)} items", logf=logf)
    return items


def main():
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(STORM_JSON) as f:
        storm = json.load(f)

    with open(LOG, "w") as logf:
        log(f"Loaded {STORM_JSON}", logf=logf)
        log(f"Archives: {[a['city'] for a in storm['archives']]}", logf=logf)

        driver = build_driver(headless=True)
        try:
            for a in storm["archives"]:
                city = a["city"].split(" / ")[0]
                query = f"{city} hurricane 1944"
                items = scrape_dpla(driver, query, logf)

                # Keep only curated individual items and collections — drop ALL search entries
                existing = [
                    p for p in a.get("photos", [])
                    if p.get("kind") in ("item", "collection")
                    and "dp.la" not in (p.get("url") or "")
                ]
                a["photos"] = existing + items

                # Also drop search entries from news — per user directive, retrieve only
                a["news"] = [
                    n for n in a.get("news", [])
                    if n.get("kind") in ("item", "collection")
                ]
                log(f"  -> {a['city']}: now {len(a['photos'])} photos total", logf=logf)

        finally:
            driver.quit()

    with open(STORM_JSON, "w") as f:
        json.dump(storm, f, indent=2)

    print(f"\nUpdated {STORM_JSON}")
    for a in storm["archives"]:
        print(f"  {a['city']}: {len(a['photos'])} photos, {len(a['news'])} news")


if __name__ == "__main__":
    main()
