"""Back-fill article_text / article_text_en / highlight_terms for Tampa only.

For each La Gaceta news item currently listed under the Tampa archive in
data/storms/1944-cuba-florida.json:
  1. Re-fetch the UFDC pagetext for the referenced vid.
  2. Locate the page that contains a Spanish/English storm trigger term.
  3. Send the full-page OCR to Claude Opus 4.7 via OpenRouter; ask it to
     extract ONLY the storm article and translate to English.
  4. Merge the result back into the item, preserving all existing fields.

Only the Tampa archive is modified. All other archives are left alone.
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv(Path.home() / ".env")

ROOT = Path(__file__).resolve().parents[2]
STORM = ROOT / "data" / "storms" / "1944-cuba-florida.json"
LOG = ROOT / "tests" / "auto" / "widen_translate_tampa.log"

OPENROUTER_KEY = os.environ.get("OPENROUTER_API_KEY")
if not OPENROUTER_KEY:
    sys.exit("OPENROUTER_API_KEY not set in ~/.env")

UFDC_BASE = "https://api.patron.uflib.ufl.edu"
TRIGGER_TERMS = ["ciclón", "huracán", "tormenta", "hurricane", "storm",
                 "tropical", "tempestad"]
HIGHLIGHT_TERMS = ["ciclón", "ciclones", "huracán", "huracanes",
                   "tormenta", "tempestad", "tropical",
                   "hurricane", "storm", "cyclone", "gale", "tropical"]

MODEL = "anthropic/claude-opus-4.7"

SYSTEM_PROMPT = """You process 1944 Florida newspaper OCR to help readers find storm coverage.

Given OCR of one newspaper page and a triggering term (a Spanish or English storm-related word found on that page), your job is:

1. Identify the ONE article on the page that actually discusses the storm (the 1944 Cuba-Florida Hurricane, October 12-23) — not neighboring columns about unrelated topics, even if they appear next to the storm article in the OCR blob.
2. Extract ONLY that article's text. OCR is imperfect — silently normalize obvious artifacts (duplicated syllables from column-wrapping, broken words, stray punctuation). Preserve proper nouns, dates, place names, and numeric facts exactly.
3. If the article is in Spanish, also produce an English translation preserving journalistic tone.
4. If the article is already in English, return the same text under both keys.
5. If no page content is actually about the storm (the triggering term was a false positive like "hurricane lamp" or "Hawker Hurricane"), set both text fields to an empty string and article_title to "".

Respond with STRICT JSON only, no commentary, no markdown fence. Shape:
{
  "article_title": "short headline as it appears, or empty string if none",
  "language": "es" or "en",
  "article_text": "cleaned original-language article text",
  "article_text_en": "English translation (same as article_text if language == en)"
}
"""


def log_open():
    LOG.parent.mkdir(parents=True, exist_ok=True)
    return open(LOG, "w", buffering=1)


def log(lf, msg):
    line = f"[{time.strftime('%H:%M:%S')}] {msg}"
    print(line, flush=True)
    lf.write(line + "\n")


def parse_ufdc_url(url: str):
    """Parse https://ufdc.ufl.edu/UF00028296/10101 → (bibid, vid)."""
    m = re.match(r"https?://ufdc\.ufl\.edu/(UF\d+)/(\d+)", url or "")
    if not m:
        return None, None
    return m.group(1), m.group(2)


def fetch_pagetext(bibid: str, vid: str):
    r = requests.get(f"{UFDC_BASE}/pagetext",
                     params={"bibid": bibid, "vid": vid}, timeout=30)
    r.raise_for_status()
    return r.json()


def pick_matching_page(resp):
    hits = resp.get("hits", []) or []
    for h in hits:
        text = h.get("pagetext", "") or ""
        low = text.lower()
        for term in TRIGGER_TERMS:
            if term.lower() in low:
                return h, term
    return None, None


def extract_and_translate(page_text: str, matched_term: str) -> dict:
    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {OPENROUTER_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://metaphorz.github.io/hurricanechronicles/",
        "X-Title": "Hurricane Chronicles",
    }
    user_msg = (
        f"Triggering term found on this page: {matched_term!r}\n\n"
        f"OCR of the full page:\n\n{page_text}"
    )
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_msg},
        ],
        "temperature": 0.2,
    }
    r = requests.post(url, headers=headers, json=payload, timeout=180)
    r.raise_for_status()
    data = r.json()
    content = data["choices"][0]["message"]["content"].strip()
    content = re.sub(r"^```(?:json)?\s*|\s*```$", "", content, flags=re.DOTALL)
    return json.loads(content)


def process_item(item: dict, lf) -> dict:
    bibid, vid = parse_ufdc_url(item.get("url", ""))
    if not bibid:
        log(lf, f"  SKIP (non-UFDC url): {item.get('title','?')[:70]}")
        return item
    try:
        resp = fetch_pagetext(bibid, vid)
    except Exception as e:
        log(lf, f"  FETCH FAIL {bibid}/{vid}: {e}")
        return item
    page, term = pick_matching_page(resp)
    if not page:
        log(lf, f"  NO TRIGGER on page ({bibid}/{vid})")
        return item
    try:
        result = extract_and_translate(page["pagetext"], term)
    except Exception as e:
        log(lf, f"  LLM FAIL {bibid}/{vid}: {e}")
        return item
    if not result.get("article_text"):
        log(lf, f"  EMPTY extract (possible false-positive): {item.get('title')[:70]}")
        return item
    item["article_title"] = result.get("article_title") or ""
    item["article_language"] = result.get("language") or "es"
    item["article_text"] = result["article_text"]
    item["article_text_en"] = result.get("article_text_en", "")
    item["highlight_terms"] = HIGHLIGHT_TERMS
    log(lf, f"  OK lang={item['article_language']} "
            f"len_es={len(item['article_text'])} "
            f"len_en={len(item['article_text_en'])}  "
            f"title={result.get('article_title','')[:60]!r}")
    return item


def main():
    with open(STORM) as f:
        storm = json.load(f)

    tampa = next((a for a in storm["archives"]
                  if a.get("id") == "tampa" or a.get("city", "").startswith("Tampa")),
                 None)
    if not tampa:
        sys.exit("Tampa archive not found.")

    lf = log_open()
    log(lf, f"Tampa: {len(tampa.get('news', []))} news items")
    for i, it in enumerate(tampa.get("news", [])):
        log(lf, f"[{i+1}/{len(tampa['news'])}] {it.get('title','?')[:70]}")
        process_item(it, lf)

    with open(STORM, "w") as f:
        json.dump(storm, f, ensure_ascii=False, indent=2)
    log(lf, f"Wrote {STORM}")
    lf.close()


if __name__ == "__main__":
    main()
