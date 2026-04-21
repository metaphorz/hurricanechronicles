"""Probe: does non-headless Chrome bypass the LoC Cloudflare challenge?"""
import json
import sys
import time
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By

URL = ("https://www.loc.gov/search/?q=hurricane+Jacksonville"
       "&fa=partof:chronicling+america%7Clocation:florida"
       "&dates=1944-10-15/1944-11-30&fo=json&c=3")

opts = Options()
opts.add_argument("--window-size=1200,900")
opts.add_argument("--disable-blink-features=AutomationControlled")
driver = webdriver.Chrome(options=opts)
try:
    driver.get(URL)
    for i in range(20):
        time.sleep(1.5)
        body = driver.find_element(By.TAG_NAME, "body").text.strip()
        first = body[:60].replace("\n", " ")
        print(f"[{i*1.5:.1f}s] len={len(body)}  first: {first!r}", flush=True)
        if body.startswith("{") or body.startswith("["):
            print("--- GOT JSON ---")
            try:
                d = json.loads(body)
                print("  results:", len(d.get("results", [])))
                for r in d.get("results", [])[:3]:
                    print("   ", (r.get("date") or "")[:10], "|",
                          (r.get("title") or "")[:80])
            except Exception as e:
                print("  parse error:", e)
            sys.exit(0)
    print("--- TIMEOUT, never got JSON ---")
finally:
    driver.quit()
