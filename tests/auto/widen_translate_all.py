"""Back-fill article_text / article_text_en / highlight_terms for ALL news items.

Generalizes widen_translate_tampa.py to handle both UFDC and LOC (Chronicling
America) sources. Only touches items that don't already have article_text, so
Tampa (already processed) is preserved.

Source dispatch:
  ufdc.ufl.edu/UF.../vid            → UFDC pagetext API (multi-page hit list)
  www.loc.gov/resource/{lccn}/...   → loc.gov JSON → tile.loc.gov fulltext

For each item we:
  1. Fetch page OCR for the referenced page.
  2. Send the full-page OCR to Claude Opus 4.7 via OpenRouter; ask it to
     extract ONLY the storm article and translate to English if needed.
  3. Merge the result back into the item, preserving all existing fields.
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
from pathlib import Path
from urllib.parse import urlparse, parse_qs

import requests
from dotenv import load_dotenv

load_dotenv(Path.home() / ".env")

ROOT = Path(__file__).resolve().parents[2]
STORM = ROOT / "data" / "storms" / "1944-cuba-florida.json"
LOG = ROOT / "tests" / "auto" / "widen_translate_all.log"

OPENROUTER_KEY = os.environ.get("OPENROUTER_API_KEY")
if not OPENROUTER_KEY:
    sys.exit("OPENROUTER_API_KEY not set in ~/.env")

UFDC_BASE = "https://api.patron.uflib.ufl.edu"
TRIGGER_TERMS = ["ciclón", "huracán", "tormenta", "hurricane", "storm",
                 "tropical", "tempestad", "cyclone", "gale"]
HIGHLIGHT_TERMS = ["ciclón", "ciclones", "huracán", "huracanes",
                   "tormenta", "tempestad", "tropical",
                   "hurricane", "hurricanes", "storm", "storms",
                   "cyclone", "cyclones", "gale",
                   "flood", "flooded", "damage", "damaged",
                   "destroyed", "destruction"]

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


# ---------- Source detection ----------

def classify_source(url: str) -> str:
    if "ufdc.ufl.edu" in url:
        return "ufdc"
    if "loc.gov/resource/" in url or "loc.gov/item/" in url:
        return "loc"
    return "unknown"


# ---------- UFDC fetcher (multi-page; pick page w/ trigger) ----------

def ufdc_parse(url: str):
    m = re.match(r"https?://ufdc\.ufl\.edu/(UF\d+)/(\d+)", url or "")
    if not m:
        return None, None
    return m.group(1), m.group(2)


def ufdc_fetch_page_text(url: str):
    bibid, vid = ufdc_parse(url)
    if not bibid:
        return None, None
    r = requests.get(f"{UFDC_BASE}/pagetext",
                     params={"bibid": bibid, "vid": vid}, timeout=30)
    r.raise_for_status()
    resp = r.json()
    for h in resp.get("hits", []) or []:
        text = (h.get("pagetext") or "").lower()
        for term in TRIGGER_TERMS:
            if term.lower() in text:
                return h.get("pagetext", ""), term
    return None, None


# ---------- LOC fetcher (single-page by sp=N) ----------

def loc_parse(url: str):
    """Return (lccn, date, edition, seq) from a loc.gov resource URL."""
    # https://www.loc.gov/resource/{lccn}/{date}/ed-{n}/?sp=N&...
    m = re.match(
        r"https?://(?:www\.)?loc\.gov/resource/([^/]+)/(\d{4}-\d{2}-\d{2})/ed-(\d+)/",
        url or "",
    )
    if not m:
        return None
    lccn, date, edition = m.group(1), m.group(2), m.group(3)
    qs = parse_qs(urlparse(url).query)
    sp = qs.get("sp", ["1"])[0]
    return {"lccn": lccn, "date": date, "edition": edition, "seq": sp}


def loc_fetch_page_text(url: str):
    parts = loc_parse(url)
    if not parts:
        return None, None
    # Get the JSON for that page → resource.fulltext_file
    api = f"https://www.loc.gov/resource/{parts['lccn']}/{parts['date']}/ed-{parts['edition']}/"
    r = requests.get(api, params={"sp": parts["seq"], "fo": "json"}, timeout=30)
    r.raise_for_status()
    j = r.json()
    fulltext_url = (j.get("resource") or {}).get("fulltext_file")
    if not fulltext_url:
        return None, None
    r2 = requests.get(fulltext_url, timeout=30)
    r2.raise_for_status()
    # The tile.loc.gov service wraps text under a single XML-path key.
    try:
        payload = r2.json()
        # payload is {"<xml-path>": {"full_text": "..."}}
        text = ""
        for v in payload.values():
            if isinstance(v, dict) and v.get("full_text"):
                text = v["full_text"]
                break
        if not text:
            return None, None
    except json.JSONDecodeError:
        text = r2.text
    low = text.lower()
    for term in TRIGGER_TERMS:
        if term.lower() in low:
            return text, term
    # No exact trigger hit; still send to LLM with a generic term so it can decide.
    return text, "hurricane"


# ---------- LLM call ----------

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


# ---------- Per-item processing ----------

def process_item(item: dict, lf) -> bool:
    """Return True if item was modified, False otherwise."""
    if item.get("article_text"):
        return False  # already done (e.g., Tampa)

    url = item.get("url", "")
    source = classify_source(url)
    title = (item.get("title") or "?")[:70]

    if source == "ufdc":
        page_text, term = ufdc_fetch_page_text(url)
    elif source == "loc":
        try:
            page_text, term = loc_fetch_page_text(url)
        except Exception as e:
            log(lf, f"  FETCH FAIL (loc): {e}")
            return False
    else:
        log(lf, f"  SKIP (unknown source): {title}")
        return False

    if not page_text:
        log(lf, f"  NO OCR / NO TRIGGER: {title}")
        return False

    try:
        result = extract_and_translate(page_text, term)
    except Exception as e:
        log(lf, f"  LLM FAIL: {e}")
        return False

    if not result.get("article_text"):
        log(lf, f"  EMPTY extract (possible false-positive): {title}")
        return False

    item["article_title"] = result.get("article_title") or ""
    item["article_language"] = result.get("language") or "en"
    item["article_text"] = result["article_text"]
    item["article_text_en"] = result.get("article_text_en", "")
    item["highlight_terms"] = HIGHLIGHT_TERMS
    log(lf,
        f"  OK lang={item['article_language']} "
        f"len_src={len(item['article_text'])} "
        f"len_en={len(item['article_text_en'])}  "
        f"title={result.get('article_title','')[:60]!r}")
    return True


def main():
    with open(STORM) as f:
        storm = json.load(f)

    lf = log_open()
    modified = 0
    skipped = 0
    for archive in storm["archives"]:
        news = archive.get("news") or []
        if not news:
            continue
        log(lf, f"=== {archive.get('id','?')} ({archive.get('city','?')}) "
                f"— {len(news)} news ===")
        for i, it in enumerate(news):
            log(lf, f"[{i+1}/{len(news)}] {it.get('title','?')[:70]}")
            if process_item(it, lf):
                modified += 1
            else:
                skipped += 1

    with open(STORM, "w") as f:
        json.dump(storm, f, ensure_ascii=False, indent=2)
    log(lf, f"Wrote {STORM} — modified={modified} skipped={skipped}")
    lf.close()


if __name__ == "__main__":
    main()
