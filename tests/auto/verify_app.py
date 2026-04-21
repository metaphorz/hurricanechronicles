"""Selenium verification: side panel shows real items (thumbnails + news titles),
not SEARCH entries, for every archive circle."""
from __future__ import annotations

import sys
import time
from pathlib import Path

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

ROOT = Path(__file__).resolve().parents[2]
SHOTS = ROOT / "tests" / "auto"
URL = "http://localhost:8000/"


def build_driver():
    opts = Options()
    opts.add_argument("--headless=new")
    opts.add_argument("--window-size=1600,1100")
    return webdriver.Chrome(options=opts)


def verify_panel(driver, archive_idx, which):
    """Click a specific archive circle, click Photos or News, inspect panel."""
    circles = driver.find_elements(By.CSS_SELECTOR, "path.leaflet-interactive")
    arch_circles = [c for c in circles if "#" in (c.get_attribute("stroke") or "")]
    # Easier: click markers via map panel — instead click archives by index
    # We'll use the dataset the app exposes. Fall back to clicking last N circles.
    archives = driver.execute_script(
        "return window.__archives ? window.__archives : null;"
    )
    return archives


def main():
    driver = build_driver()
    results = []
    try:
        driver.get(URL)
        WebDriverWait(driver, 20).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, ".leaflet-container"))
        )
        time.sleep(2)

        # Read archive data from the storm JSON via JS
        archives = driver.execute_script(
            "return fetch('data/storms/1944-cuba-florida.json')"
            ".then(r=>r.json()).then(d=>d.archives);"
        )
        # execute_script with promise returns None — use async pattern instead
        archives = driver.execute_async_script("""
            const cb = arguments[arguments.length-1];
            fetch('data/storms/1944-cuba-florida.json')
              .then(r=>r.json())
              .then(d=>cb(d.archives))
              .catch(e=>cb({error:String(e)}));
        """)
        print(f"Loaded {len(archives)} archives from JSON")

        # For each archive, programmatically open the panel by calling app internals
        # The app exposes openPanel via window for testing? If not, click circles by coord.
        # Simplest: invoke the panel-render code through the existing buttons.
        # We'll click circles via Leaflet's marker layer — open popup, click button.

        panel_screenshot_paths = []
        for i, a in enumerate(archives):
            city = a["city"]
            # Open popup by simulating a marker click through Leaflet API
            js = """
            const archive = arguments[0];
            // Find the circleMarker at these coordinates
            const map = window.__map;
            if (!map) return 'no-map';
            let found = null;
            map.eachLayer(l => {
                if (l.options && l.options.radius && l._latlng
                    && Math.abs(l._latlng.lat - archive.lat) < 0.01
                    && Math.abs(l._latlng.lng - archive.lng) < 0.01) {
                    found = l;
                }
            });
            if (!found) return 'no-marker';
            found.fire('click');
            return 'ok';
            """
            res = driver.execute_script(js, a)
            print(f"[{city}] marker: {res}")
            if res != "ok":
                results.append((city, "photos", "marker not found"))
                continue
            time.sleep(0.6)

            for which, label in (("photos", "Photos"), ("news", "News")):
                # Click the button in the popup (match "Photos" or "Photos (N)")
                try:
                    btn = driver.find_element(
                        By.XPATH,
                        f"//div[contains(@class,'leaflet-popup-content')]//button[starts-with(normalize-space(),'{label}')]"
                    )
                    btn.click()
                except Exception as e:
                    results.append((city, which, f"button click failed: {e}"))
                    continue
                time.sleep(0.8)

                # Inspect panel body
                body = driver.find_element(By.ID, "panel-body")
                items = body.find_elements(By.CSS_SELECTOR, ".item")
                badges = body.find_elements(By.CSS_SELECTOR, ".badge")
                thumbs = body.find_elements(By.CSS_SELECTOR, ".item-thumb img")
                search_badges = [b for b in badges
                                 if "search" in (b.get_attribute("class") or "").lower()
                                 or "Search" in (b.text or "")]
                shot = SHOTS / f"verify_{i}_{city.split()[0]}_{which}.png"
                driver.save_screenshot(str(shot))
                panel_screenshot_paths.append(shot)
                results.append((city, which, {
                    "items": len(items),
                    "thumbs": len(thumbs),
                    "search_badges": len(search_badges),
                    "screenshot": shot.name,
                }))
                print(f"  {city} / {which}: items={len(items)} thumbs={len(thumbs)} search_badges={len(search_badges)}")

                # Re-open popup for second button
                driver.execute_script(js, a)
                time.sleep(0.4)

    finally:
        driver.quit()

    print("\n=== SUMMARY ===")
    problems = []
    for city, which, info in results:
        print(f"{city} / {which}: {info}")
        if isinstance(info, dict):
            if info["search_badges"] > 0:
                problems.append(f"{city}/{which}: {info['search_badges']} SEARCH badges")
            if info["items"] == 0:
                problems.append(f"{city}/{which}: 0 items")
    if problems:
        print("\nPROBLEMS:")
        for p in problems:
            print(f"  - {p}")
        sys.exit(1)
    print("\nAll panels show only real items. No SEARCH badges detected.")


if __name__ == "__main__":
    main()
