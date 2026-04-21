"""One-shot test: LLM-driven article extraction + translation.

Fetches the UFDC pagetext for the first La Gaceta hit
(UF00028296/10101 — "Un Ciclón Cerca de la Costa Sur de Cuba", 1944-10-14),
finds the page that contains a trigger term, and sends the full page OCR
to Claude Opus 4.7 via OpenRouter. Asks the model to (a) extract ONLY
the article that discusses the storm, (b) return the original-language
text, and (c) return an English translation. Response is requested as
JSON so parsing is deterministic.

Does NOT touch data/storms/. Pure test.
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv(Path.home() / ".env")

OPENROUTER_KEY = os.environ.get("OPENROUTER_API_KEY")
if not OPENROUTER_KEY:
    sys.exit("OPENROUTER_API_KEY not set in ~/.env")

UFDC_BASE = "https://api.patron.uflib.ufl.edu"
BIBID = "UF00028296"  # La Gaceta
VID = "10101"         # 1944-10-14
TRIGGER_TERMS = ["ciclón", "huracán", "tormenta", "hurricane", "storm"]

MODEL = "anthropic/claude-opus-4.7"  # most recent Claude flagship


def fetch_pagetext():
    url = f"{UFDC_BASE}/pagetext"
    r = requests.get(url, params={"bibid": BIBID, "vid": VID}, timeout=30)
    r.raise_for_status()
    return r.json()


def pick_matching_page(pagetext_response):
    hits = pagetext_response.get("hits", []) or []
    for h in hits:
        text = h.get("pagetext", "") or ""
        low = text.lower()
        for term in TRIGGER_TERMS:
            if term.lower() in low:
                return h, term
    return None, None


SYSTEM_PROMPT = """You process 1944 Florida newspaper OCR to help readers find storm coverage.

Given OCR of one newspaper page and a triggering term (a Spanish or English storm-related word found on that page), your job is:

1. Identify the ONE article on the page that actually discusses the storm — not neighboring columns about unrelated topics, even if they appear next to the storm article in the OCR blob.
2. Extract ONLY that article's text. OCR is imperfect — silently normalize obvious artifacts (duplicated syllables from column-wrapping, broken words, stray punctuation). Preserve proper nouns, dates, place names, and numeric facts exactly.
3. If the article is in Spanish, also produce an English translation preserving journalistic tone.
4. If the article is already in English, return the same text under both keys.

Respond with STRICT JSON only, no commentary, no markdown fence. Shape:
{
  "article_title": "short article title or headline as it appears",
  "language": "es" or "en",
  "article_text": "cleaned original-language article text",
  "article_text_en": "English translation (same as article_text if language == en)"
}
"""


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
    r = requests.post(url, headers=headers, json=payload, timeout=120)
    r.raise_for_status()
    data = r.json()
    content = data["choices"][0]["message"]["content"].strip()
    # Strip any accidental ```json fencing.
    content = re.sub(r"^```(?:json)?\s*|\s*```$", "", content, flags=re.DOTALL)
    return json.loads(content)


def main():
    print(f"Model: {MODEL}")
    print(f"Fetching UFDC pagetext for {BIBID}/{VID}...")
    resp = fetch_pagetext()
    page, term = pick_matching_page(resp)
    if not page:
        sys.exit("No trigger term found in this issue.")
    page_text = page["pagetext"]
    print(f"Matched term: {term!r} on pageorder={page.get('pageorder')}")
    print(f"Page OCR length: {len(page_text)} chars")

    print(f"\n--- Calling {MODEL} ---")
    result = extract_and_translate(page_text, term)

    print(f"\nArticle title: {result.get('article_title','?')}")
    print(f"Language: {result.get('language','?')}")
    print(f"Original length: {len(result.get('article_text',''))} chars")
    print(f"English length:  {len(result.get('article_text_en',''))} chars")
    print("\n--- ORIGINAL (cleaned) ---\n")
    print(result.get("article_text", ""))
    print("\n--- ENGLISH ---\n")
    print(result.get("article_text_en", ""))

    out = Path(__file__).parent / "test_widen_translate_one.json"
    with open(out, "w") as f:
        json.dump({
            "bibid": BIBID,
            "vid": VID,
            "date": "1944-10-14",
            "matched_term": term,
            "model": MODEL,
            **result,
        }, f, ensure_ascii=False, indent=2)
    print(f"\nSaved: {out}")


if __name__ == "__main__":
    main()
