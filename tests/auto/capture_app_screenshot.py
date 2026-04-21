"""Capture a Selenium screenshot of the running app for docs/figures/.

Loads http://localhost:8000/index.html, waits for the map + storm track to
render (so all archive circles are visible), then writes PNGs to
docs/figures/.
"""
from __future__ import annotations

import time
from pathlib import Path

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

ROOT = Path(__file__).resolve().parents[2]
FIG = ROOT / "docs" / "figures"
FIG.mkdir(parents=True, exist_ok=True)

URL = "http://localhost:8000/index.html"


def build_driver():
    opts = Options()
    opts.add_argument("--window-size=1400,900")
    opts.add_argument("--window-position=200,120")
    opts.add_argument("--disable-blink-features=AutomationControlled")
    return webdriver.Chrome(options=opts)


def main():
    driver = build_driver()
    try:
        driver.get(URL)
        WebDriverWait(driver, 20).until(
            EC.presence_of_element_located((By.ID, "storm-select"))
        )
        for _ in range(20):
            time.sleep(0.5)
            opts = driver.find_elements(By.CSS_SELECTOR, "#storm-select option")
            if opts:
                break
        time.sleep(2.5)

        out1 = FIG / "app_overview.png"
        driver.save_screenshot(str(out1))
        print(f"wrote {out1}")

        circles = driver.find_elements(By.CSS_SELECTOR, ".leaflet-interactive")
        if circles:
            circles[len(circles) // 2].click()
            time.sleep(1.2)
            out2 = FIG / "app_popup.png"
            driver.save_screenshot(str(out2))
            print(f"wrote {out2}")
    finally:
        driver.quit()


if __name__ == "__main__":
    main()
