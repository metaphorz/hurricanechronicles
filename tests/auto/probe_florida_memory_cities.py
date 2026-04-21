"""City-specific Florida Memory probes for 1944 hurricane coverage.

Targets archive circles that were empty after the generic "1944 hurricane" search:
Tampa, Orlando, Jacksonville, Fort Myers, Sarasota. Also re-queries Naples for more.
Cloudflare-protected: non-headless Selenium required.
"""
import json
import re
import time
from pathlib import Path

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By

HERE = Path(__file__).resolve().parent
OUT_JSON = HERE / "florida_memory_cities_1944.json"
LOG = HERE / "florida_memory_cities.log"

CITY_QUERIES = [
    ("tampa",         "hurricane+Tampa+1944"),
    ("orlando",       "hurricane+Orlando+1944"),
    ("jacksonville",  "hurricane+Jacksonville+1944"),
    ("fort-myers",    "hurricane+Fort+Myers+1944"),
    ("sarasota",      "hurricane+Sarasota+1944"),
    ("naples",        "hurricane+Naples+1944"),
    ("key-west",      "hurricane+Key+West+1944"),
    ("daytona",       "hurricane+Daytona+1944"),
    ("miami",         "hurricane+Miami+1944"),
]

WARMUP = "https://www.floridamemory.com/items/show/153868"


def main():
    opts = Options()
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

    results = {}
    try:
        log(f"WARMUP {WARMUP}")
        driver.get(WARMUP)
        for attempt in range(30):
            time.sleep(2)
            t = driver.title or ""
            if "just a moment" not in t.lower() and t.strip():
                log(f"  cleared: {t!r}"); break

        for tag, kw in CITY_QUERIES:
            page_items = []
            for page in (1, 2):
                url = f"https://www.floridamemory.com/find?keywords={kw}"
                if page > 1: url += f"&page={page}"
                log(f"\nGET [{tag}] p{page}: {url}")
                driver.get(url)
                for attempt in range(30):
                    time.sleep(2)
                    title = driver.title or ""
                    if ("just a moment" not in title.lower()
                            and "cloudflare" not in title.lower()
                            and title.strip()):
                        break
                html = driver.page_source
                log(f"  title={driver.title!r}  size={len(html)}")
                hrefs = set(re.findall(r'href="(/items/show/\d+)"', html))
                log(f"  links: {len(hrefs)}")
                for h in hrefs:
                    u = "https://www.floridamemory.com" + h
                    if any(x["url"] == u for x in page_items): continue
                    page_items.append({"url": u, "page": page})

            # Harvest each item
            for i, it in enumerate(page_items, 1):
                log(f"  [{tag} {i}/{len(page_items)}] {it['url']}")
                driver.get(it["url"])
                for attempt in range(8):
                    time.sleep(2)
                    t = driver.title or ""
                    if "just a moment" not in t.lower(): break
                html = driver.page_source
                it["title"] = (driver.title or "").replace(" \u00b7 Florida Memory", "").strip()
                try:
                    h1 = driver.find_element(By.CSS_SELECTOR, "h1").text.strip()
                    if h1: it["h1"] = h1
                except Exception: pass
                m = re.search(r'<meta property="og:image" content="([^"]+)"', html)
                if m: it["thumb"] = m.group(1)
                m = re.search(r'<meta property="og:description" content="([^"]+)"', html)
                if m: it["description"] = m.group(1)[:300]
                for label in ("Date", "Subject", "Spatial Coverage", "Coverage", "Description"):
                    m = re.search(
                        rf'<h3[^>]*>{label}</h3>\s*<div[^>]*>(.*?)</div>',
                        html, re.S | re.I)
                    if m:
                        txt = re.sub(r"<[^>]+>", " ", m.group(1))
                        txt = re.sub(r"\s+", " ", txt).strip()
                        it[label.lower().replace(" ", "_")] = txt[:300]
                log(f"    date={it.get('date','?')}  subj={it.get('subject','?')[:60]}")

            results[tag] = {"keyword": kw, "items": page_items}

        OUT_JSON.write_text(json.dumps(results, indent=2))
        log(f"\nSaved {OUT_JSON}")
        log("\n=== 1944 items by city ===")
        for tag, r in results.items():
            good = [i for i in r["items"]
                    if str(i.get("date","")).startswith("1944")]
            log(f"  {tag:15s} query-matches={len(r['items'])}  1944={len(good)}")
    finally:
        driver.quit()
        logf.close()


if __name__ == "__main__":
    main()
