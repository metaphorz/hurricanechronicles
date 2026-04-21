# Archive Search Algorithm — 1944 Cuba-Florida Hurricane

Running notes on what worked / didn't work for sourcing photos and news for each archive circle. Goal: reusable recipe for future storms.

## Sources — summary

| Source | What it has | How to query | Auth / quirks |
|---|---|---|---|
| **Florida Memory** (State Archives of FL) | Photos, postcards, audio | `/find?keywords=...&page=N` | **Cloudflare-protected** — must use non-headless Selenium with stealth opts |
| **UFDC / Florida Digital Newspaper Library** | Newspaper full text | `/pagetext?bibid=X&vid=Y` via `api.patron.uflib.ufl.edu` | Free, JSON, no auth |
| **PastPerfect Online** (museum CMS) | Small museum catalogs | `{museum}.pastperfectonline.com/search?...` | Many museums disable search (admin-locked); try fulltext on specific sites |
| **DPLA** | Aggregator of US archives | `api.dp.la/v2/items?...` | Misses FL Memory; many bad matches, high noise |
| **LOC Chronicling America** | Historic newspapers (small FL papers, Jewish weeklies, county gazettes) | `www.loc.gov/collections/chronicling-america/?q=X&dates=YYYY-MM&fa=location:florida&fo=json&c=100` | **Legacy `chroniclingamerica.loc.gov/...ocr.txt` is dead (403)**; use new loc.gov endpoints. Browser UA header required. |

## What worked (for this storm)

### Florida Memory — 13 photos
- Non-headless Selenium (headless → Cloudflare 403)
- Warmup: visit a known-good item page first to clear CF cookies
- Search URL: `/find?keywords=1944+hurricane` paginated
- City-specific queries (`hurricane+Tampa+1944`, etc.) added **zero** new items — the generic "1944 hurricane" keyword captures everything
- Extract via regex on `/items/show/\d+`, `og:image`, `og:description`, Dublin Core h3/div pairs

### UFDC Newspaper Library — Tampa (La gaceta) 11/13 issues
- `/fdnl_titles_list?size=10000` → list all FL newspapers with min/max date spanning 1944
- `/all_vids_in_bibid?bibid=X&size=50000` → real issue dates (min/max has gaps)
- `/pagetext?bibid=X&vid=Y` → full OCR text. Response shape: `{hits:[{pagetext,pageorder,thumbnail,...}]}`
- **Language matters**: La gaceta is bilingual Tampa Spanish/English. English "hurricane" = 0 hits; Spanish "huracán" / "ciclón" = 11/13 issues.
- Always search both English and Spanish keywords for Tampa/Miami papers.

### PastPerfect Online — Amelia Island Museum (18 photos)
- Only site where search was left fully open by the admin
- `/search?keywords=1944+hurricane` returns rich 1944 hurricane collections

### LOC Chronicling America — Jacksonville (2), Miami (1), Brooksville (2)
**Recipe** (verified for this storm):

1. **Search API** — JSON collection endpoint (legacy `chroniclingamerica.loc.gov/search/pages/results/` now 404s after CF redirect):
   ```
   GET https://www.loc.gov/collections/chronicling-america/
       ?q=<keyword>&dates=YYYY-MM&fa=location:florida&fo=json&c=100
   ```
   Response: `{results:[{id, title, date, extract, ...}, ...], pagination:{of:<total>}}`. Headers: browser User-Agent required (plain Python UA → 403).

2. **Broaden the keyword set** — one keyword is never enough. For this storm, "hurricane" returned 8 hits but only 5 real; "storm" + "tropical" + "damage" + "gale" found another 3 real ones that hurricane-only missed. Run them all, dedupe by result ID.
   - English: `hurricane, storm, tropical, gale, damage, flood, destroyed`
   - Spanish (Tampa/Miami bilingual papers): `huracán, ciclón, tormenta`

3. **Fetch OCR** (needed for noise filtering — the search `extract` field is useless):
   ```
   GET <result.id>&fo=json               # resource JSON
     → response.fulltext_service         # URL to text-services
   GET <fulltext_service>                # RETURNS JSON, not XML!
     → body[<segment_path>].full_text    # ~10-25 KB of OCR per page
   ```
   Critical gotcha: the `fulltext_service` URL contains `format=alto_xml` in the query string and looks like it returns XML, but it actually returns a JSON envelope with a `full_text` field. Don't rewrite the URL, just parse the response as JSON.

4. **Noise filter** — LOC keyword search matches literally; half of 1944 "hurricane" hits are non-storm. Catalog of known false positives:
   - "Hurricane Pie" — a WWII recipe using apple windfalls
   - "Wyoming Hurricane" — Russell Hayden cowboy movie
   - "Summer Storm" — 1944 Linda Darnell film
   - "Hawker Hurricane" / "Spitfire and Hurricane" — RAF WWII fighter planes
   - "Hurricane lamp" — classified ad
   - "storm troops" — political metaphor for Nazi brownshirts
   - "storm sash" — building-supplies ad
   - "storm in Connecticut" — another state's agriculture news
   Always grep OCR for storm terms, then manually read ±200 chars of context before including.

5. **Date the real coverage** — this storm hit Oct 19, 1944. Substantive coverage appears in Oct 19 issues (bulletins, wind speed, track) and Oct 26 follow-ups (damage totals, OPA price-ceiling requests, power company notes). Oct 12 issues = pre-storm Cuba reports. Oct 5 or earlier = noise.

6. **Which FL papers are in LOC's free collection** — for this storm: *Brooksville Journal, Gadsden County Times (Quincy), Miami Citizen, Southern Jewish Weekly (Jax), Community Council Commentator (Jax), La Gaceta (Tampa, also in UFDC).* **NOT in LOC**: Orlando Sentinel, Jacksonville Times-Union, Miami Herald, Sarasota Herald-Tribune, Fort Myers News-Press, Daytona News-Journal, Key West Citizen. Those are on Newspapers.com (paid).

## What did NOT work

### UFDC `publication_date` filter
- `publication_date=1944-10-12 TO 1944-10-26` does **token matching** not range filtering. Returns 1920s garbage mixed in.
- **Workaround**: fetch all vids in a bibid, filter dates client-side.

### UFDC `size` parameter truncation
- Default `size=1000` on `/all_vids_in_bibid`; La gaceta has 12000+ vids → early date filter missed 1944 entirely.
- **Fix**: always `size=50000`.

### PastPerfect Online on most FL museums
- Jacksonville Historical Society, FL Historical Society (Cocoa): `/search` redirects to `/Home/ContactAdmin` — search disabled by admin.
- Sarasota County gov: search works but only 1 weak match (non-hurricane).
- **Lesson**: PastPerfect is museum-by-museum; can't assume it will work.

### DPLA for Florida Memory content
- FL State Archives is **not a DPLA data provider**. DPLA has ~13 total "hurricane 1944 florida" items, mostly irrelevant.
- Occasional false positives: "Arlington Historical Society" (Arlington, MA) → mistakenly grouped under sarasota before manual audit.
- **Lesson**: DPLA hits need location sanity-check against the archive circle.

### Florida Memory headless Selenium
- Cloudflare returns 403 Forbidden.
- **Fix**: non-headless Chrome + `--disable-blink-features=AutomationControlled` + remove `webdriver` navigator property via CDP.

## Algorithm for next storm (generalized)

1. **Figure out the track** — list candidate archive circles (landfall, track cities, exit point). Put coords + region note in each.
2. **Florida Memory sweep** — one generic `YYYY+hurricane` keyword via `/find?keywords=...&page=N`, non-headless Selenium with anti-detection options. Warmup by visiting a known-good `/items/show/<id>` page first to clear Cloudflare cookies. Harvest all items across pagination, then sort by Dublin Core `Subject` (e.g. `Hurricanes--Florida--<County>--<City>`) into circles. City-specific keywords are unnecessary — they added zero new items for this storm.
3. **UFDC sweep** —
   - `GET /fdnl_titles_list?size=10000` → all FL newspapers
   - Filter to bibids where `min_date <= YYYY <= max_date`
   - `GET /all_vids_in_bibid?bibid=X&size=50000` (NOT the default 1000!) → real issue dates; filter client-side for the Oct window
   - `GET /pagetext?bibid=X&vid=Y` → `{hits:[{pagetext, pageorder, thumbnail, ...}]}`
   - Grep each `pagetext` for bilingual keywords: `hurricane, huracán, ciclón, tormenta, storm, tropical, damage`. Spanish-language hits dominate in Tampa/Miami papers (La Gaceta: 11/13 issues matched Spanish, 0 matched English).
4. **PastPerfect by town** — guess `{museum}.pastperfectonline.com`; abort immediately if `/search` redirects to `/Home/ContactAdmin` (admin-locked). Amelia Island Museum is the reliable open one.
5. **LOC Chronicling America** — follow the recipe in the "What worked" section above. Run the full keyword set, fetch `fulltext_service` JSON, apply the noise-filter catalog before including anything.
6. **DPLA as last resort only** — high noise, missing FL State Archives. Every hit must be location-checked (Arlington MA vs. Arlington County, etc.).
7. **Newspapers.com** — paid, but the only source for major FL dailies (Orlando Sentinel, Jax Times-Union, Miami Herald, Sarasota Herald-Tribune). Not attempted here.
8. **Curate each candidate** — skip marginal items (humor columns, one-line mentions, off-topic keyword collisions). Better a small circle with strong content than a large circle padded with noise.
9. **Audit provenance** — every entry needs a `source` field that names the archive; readers should be able to identify MA-based mismatches on sight.
10. **Hide empty circles** — in `js/app.js renderArchives()`, filter `a => a.photos.length + a.news.length > 0` before rendering. Keeps the track implicit in the populated circles.
11. **Highlight matched terms in the UI** — the news snippet box should `<mark>` the terms that triggered inclusion (hurricane, huracán, ciclón, storm, tormenta, damage, tropical, flood, gale, destroyed). Users shouldn't have to skim walls of OCR text.
