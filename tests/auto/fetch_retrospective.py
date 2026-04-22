"""Add one 'retrospective' news item to a storm archive.

Fair-use approach for modern (in-copyright) articles: we do NOT republish
the article body. Instead, Perplexity Sonar fetches the page, then Claude
Opus 4.7 writes a 2-3 sentence summary in our own words. The card shows
the summary + prominent link back to the source.

Currently wired for the St. Augustine Record's 2010 '1944: a dangerous year'
piece → data/storms/1944-cuba-florida.json, saint-augustine archive.
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
LOG = Path(__file__).parent / "fetch_retrospective.log"

KEY = os.environ.get("OPENROUTER_API_KEY")
if not KEY:
    sys.exit("OPENROUTER_API_KEY not set in ~/.env")

TARGET = {
    "archive_id": "saint-augustine",
    "url": "https://www.staugustine.com/story/news/local/2010/11/01/1944-dangerous-year/16219491007/",
    "source": "The St. Augustine Record",
    "expected_date": "2010-11-01",
}

SONAR_MODEL = "perplexity/sonar-pro"
OPUS_MODEL = "anthropic/claude-opus-4.7"

FETCH_PROMPT = f"""Fetch and read the full article at:

  {TARGET["url"]}

This is a 2010 retrospective article from The St. Augustine Record. It discusses
the 1944 hurricane season's impact on northeast Florida (specifically the
October 1944 Cuba-Florida hurricane, which lashed Saint Augustine on Oct 19-20).

Return the article body text so it can be summarized. Include the headline,
byline (author), and publication date. Exclude navigation, ads, related-link
teasers, and comments.

Respond with STRICT JSON only, no commentary, no markdown fence:
{{
  "headline": "...",
  "byline": "... (empty string if none)",
  "published_date": "YYYY-MM-DD",
  "body": "the article body text as published"
}}
"""

SUMMARY_SYSTEM = """You write fair-use factual summaries of in-copyright news articles.

Hard rules:
- Write in your OWN words, 2 to 3 sentences total.
- Do NOT quote any span longer than ~10 consecutive words from the source.
- Focus only on what the source says about the October 1944 Cuba-Florida
  hurricane and its effect on Saint Augustine / northeast Florida.
- Neutral, factual tone; no editorializing.
- Do not invent facts not in the source.

Respond with STRICT JSON, no fence, no commentary:
{
  "summary": "your 2-3 sentence summary"
}
"""


def log_open():
    LOG.parent.mkdir(parents=True, exist_ok=True)
    return open(LOG, "w", buffering=1)


def log(lf, msg):
    line = f"[{time.strftime('%H:%M:%S')}] {msg}"
    print(line, flush=True)
    lf.write(line + "\n")


def call_openrouter(model, messages, temperature=0.2, timeout=180):
    r = requests.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {KEY}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://metaphorz.github.io/hurricanechronicles/",
            "X-Title": "Hurricane Chronicles",
        },
        json={"model": model, "messages": messages, "temperature": temperature},
        timeout=timeout,
    )
    r.raise_for_status()
    data = r.json()
    content = data["choices"][0]["message"]["content"].strip()
    content = re.sub(r"^```(?:json)?\s*|\s*```$", "", content, flags=re.DOTALL)
    return content, data


def fetch_article_via_sonar(lf):
    log(lf, f"Fetching via {SONAR_MODEL}: {TARGET['url']}")
    content, _ = call_openrouter(
        SONAR_MODEL,
        [{"role": "user", "content": FETCH_PROMPT}],
        temperature=0.1,
    )
    return json.loads(content)


def summarize_via_opus(body, lf):
    log(lf, f"Summarizing via {OPUS_MODEL} (len={len(body)} chars)...")
    content, _ = call_openrouter(
        OPUS_MODEL,
        [
            {"role": "system", "content": SUMMARY_SYSTEM},
            {"role": "user", "content": f"ARTICLE BODY:\n\n{body}"},
        ],
        temperature=0.2,
    )
    return json.loads(content)


def main():
    lf = log_open()
    try:
        fetched = fetch_article_via_sonar(lf)
    except Exception as e:
        log(lf, f"FAIL fetch: {e}")
        sys.exit(1)
    log(lf, f"headline={fetched.get('headline','?')!r}")
    log(lf, f"byline={fetched.get('byline','')!r}  date={fetched.get('published_date','?')}")
    body = fetched.get("body", "")
    log(lf, f"body length: {len(body)} chars")
    if len(body) < 400:
        log(lf, "WARN: body suspiciously short — Sonar may not have fetched full article")

    try:
        summary_obj = summarize_via_opus(body, lf)
    except Exception as e:
        log(lf, f"FAIL summarize: {e}")
        sys.exit(1)

    summary = summary_obj.get("summary", "").strip()
    log(lf, f"summary ({len(summary)} chars):")
    log(lf, f"  {summary}")

    item = {
        "kind": "retrospective",
        "title": f"The St. Augustine Record — {fetched.get('headline', '1944: a dangerous year')}",
        "url": TARGET["url"],
        "source": TARGET["source"],
        "date": fetched.get("published_date") or TARGET["expected_date"],
        "byline": fetched.get("byline", ""),
        "summary": summary,
    }

    with open(STORM) as f:
        storm = json.load(f)
    archive = next(a for a in storm["archives"] if a["id"] == TARGET["archive_id"])
    news = archive.setdefault("news", [])
    # Replace any existing retrospective for this URL; otherwise append.
    news = [n for n in news if n.get("url") != TARGET["url"]]
    news.append(item)
    archive["news"] = news

    with open(STORM, "w") as f:
        json.dump(storm, f, ensure_ascii=False, indent=2)
    log(lf, f"Appended retrospective to {TARGET['archive_id']}. Wrote {STORM}")
    lf.close()


if __name__ == "__main__":
    main()
