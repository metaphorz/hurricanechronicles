"""Probe Florida Memory for 1944 hurricane photos via Selenium (Cloudflare-protected).

Goals:
  1. Find a working search URL pattern for 1944 hurricane photos.
  2. List every 1944 hurricane item on the first 2 result pages with title, item URL,
     thumb URL, location, date.
  3. Save raw HTML + parsed results for later curator work.
"""
import json
import re
import time
from pathlib import Path

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

HERE = Path(__file__).resolve().parent
OUT_JSON = HERE / "florida_memory_1944.json"
OUT_HTML = HERE / "florida_memory_1944.html"
LOG = HERE / "florida_memory_probe.log"

SEARCH_URLS = [
    # Paginate through all "1944 hurricane" results (24 items, ~10 per page)
    "https://www.floridamemory.com/find?keywords=1944+hurricane",
    "https://www.floridamemory.com/find?keywords=1944+hurricane&page=2",
    "https://www.floridamemory.com/find?keywords=1944+hurricane&page=3",
    # Known-good item page (warm up Cloudflare cookies before searching)
    "https://www.floridamemory.com/items/show/153868",
]


def main():
    opts = Options()
    # Non-headless — Cloudflare blocks headless. A real Chrome window briefly appears.
    opts.add_argument("--window-size=1600,1200")
    opts.add_argument("--disable-blink-features=AutomationControlled")
    opts.add_experimental_option("excludeSwitches", ["enable-automation"])
    opts.add_experimental_option("useAutomationExtension", False)
    driver = webdriver.Chrome(options=opts)
    driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
        "source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
    })
    logf = open(LOG, "w", buffering=1)
    def log(m):
        line = f"[{time.strftime('%H:%M:%S')}] {m}"
        print(line, flush=True); logf.write(line + "\n")

    all_items = []
    try:
        # Visit known-good item first to clear Cloudflare cookies
        warmup = SEARCH_URLS[-1]
        log(f"WARMUP {warmup}")
        driver.get(warmup)
        for attempt in range(30):
            time.sleep(2)
            t = driver.title or ""
            if "just a moment" not in t.lower() and t.strip():
                log(f"  warmup cleared, title={t!r}"); break
            log(f"  warmup wait {attempt+1}, title={t!r}")

        for url in SEARCH_URLS[:-1]:
            log(f"GET {url}")
            driver.get(url)
            # Wait for Cloudflare + content (can take 20s+)
            for attempt in range(30):
                time.sleep(2)
                title = driver.title or ""
                if ("just a moment" not in title.lower()
                        and "cloudflare" not in title.lower()
                        and title.strip() != ""):
                    break
                log(f"  (waiting... attempt {attempt+1}, title={title!r})")
            log(f"  final title: {driver.title!r}")
            html = driver.page_source
            log(f"  page size: {len(html)}")
            if url == SEARCH_URLS[0]:
                OUT_HTML.write_text(html)
                log(f"  saved {OUT_HTML}")

            # Parse result items. Florida Memory uses Omeka-style markup.
            # Look for links to /items/show/NNNN
            item_hrefs = set(re.findall(r'href="(/items/show/\d+)"', html))
            log(f"  item links: {len(item_hrefs)}")

            for href in list(item_hrefs):
                iurl = "https://www.floridamemory.com" + href
                if any(i["url"] == iurl for i in all_items): continue
                all_items.append({"url": iurl, "found_via": url})


        log(f"\nTotal distinct item URLs: {len(all_items)}")

        # Visit all items to harvest details
        for i, it in enumerate(all_items, 1):
            log(f"\n[{i}/{min(15,len(all_items))}] visiting {it['url']}")
            driver.get(it["url"])
            for attempt in range(8):
                time.sleep(2)
                t = driver.title or ""
                if "just a moment" not in t.lower(): break
            html = driver.page_source
            it["title"] = (driver.title or "").replace(" · Florida Memory", "").strip()
            # Try to extract h1
            try:
                h1 = driver.find_element(By.CSS_SELECTOR, "h1").text.strip()
                if h1: it["h1"] = h1
            except Exception:
                pass
            # og:image meta for thumbnail
            m = re.search(r'<meta property="og:image" content="([^"]+)"', html)
            if m: it["thumb"] = m.group(1)
            m = re.search(r'<meta property="og:description" content="([^"]+)"', html)
            if m: it["description"] = m.group(1)[:300]
            # Date + location via Omeka dublin-core fields
            for label in ("Date", "Subject", "Spatial Coverage", "Coverage", "Description"):
                m = re.search(
                    rf'<h3[^>]*>{label}</h3>\s*<div[^>]*>(.*?)</div>',
                    html, re.S | re.I)
                if m:
                    txt = re.sub(r"<[^>]+>", " ", m.group(1))
                    txt = re.sub(r"\s+", " ", txt).strip()
                    it[label.lower().replace(" ", "_")] = txt[:300]
            log(f"  title={it.get('h1') or it.get('title')!r}")
            log(f"  date={it.get('date','?')}  loc={it.get('spatial_coverage') or it.get('coverage','?')}")

        OUT_JSON.write_text(json.dumps(all_items, indent=2))
        log(f"\nSaved {OUT_JSON}")

    finally:
        driver.quit()
        logf.close()


if __name__ == "__main__":
    main()
