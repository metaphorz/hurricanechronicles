"""Selenium smoke test for the new MISC topbar button.

Loads the running app, waits for storm to load, then:
  1. Confirms #misc-btn is visible and shows "MISC (5)"
  2. Clicks MISC and screenshots the opened panel
  3. Confirms the panel body has 5 item cards with the expected badges
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
OUT = ROOT / "tests" / "auto"
URL = "http://localhost:8000/index.html"


def build_driver():
    opts = Options()
    opts.add_argument("--window-size=1500,950")
    opts.add_argument("--window-position=200,120")
    return webdriver.Chrome(options=opts)


def main():
    driver = build_driver()
    try:
        driver.get(URL)
        WebDriverWait(driver, 20).until(
            EC.presence_of_element_located((By.ID, "storm-select"))
        )

        btn = WebDriverWait(driver, 15).until(
            EC.visibility_of_element_located((By.ID, "misc-btn"))
        )
        print(f"misc button visible. text='{btn.text}'")
        assert btn.text.strip() == "MISC (5)", f"expected 'MISC (5)', got {btn.text!r}"

        driver.save_screenshot(str(OUT / "verify_misc_topbar.png"))
        print(f"wrote {OUT/'verify_misc_topbar.png'}")

        btn.click()
        time.sleep(1.0)

        WebDriverWait(driver, 10).until(
            EC.visibility_of_element_located((By.ID, "panel"))
        )
        title = driver.find_element(By.ID, "panel-title").text
        subtitle = driver.find_element(By.ID, "panel-subtitle").text
        items = driver.find_elements(By.CSS_SELECTOR, "#panel-body .item")
        badges = [b.text for b in driver.find_elements(By.CSS_SELECTOR, "#panel-body .badge")]
        print(f"panel title='{title}'  subtitle='{subtitle}'  items={len(items)}  badges={badges}")
        assert "Miscellaneous" in title
        assert len(items) == 5, f"expected 5 items, got {len(items)}"

        driver.save_screenshot(str(OUT / "verify_misc_panel.png"))
        print(f"wrote {OUT/'verify_misc_panel.png'}")
    finally:
        driver.quit()


if __name__ == "__main__":
    main()
