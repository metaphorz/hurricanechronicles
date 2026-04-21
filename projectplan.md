# History Hurricanes — Interactive Florida Map

## Goal
Build a Leaflet-based web map of Florida with a dropdown menu of historical hurricanes. Each storm displays its track as a polyline with small clickable circles at regions/cities along the path. Clicking a circle lets the user choose **News** or **Photos** to browse how the hurricane affected that area. Archives linked include museums, universities, and digital collections.

First storm: **1944 Cuba–Florida Hurricane** (Oct 12–23, 1944).

## Architecture (kept intentionally simple)
- **Stack**: Static HTML + vanilla JS + Leaflet (via CDN). No build step.
- **Data**: One JSON file per storm under `data/storms/`. Storm list in `data/storms.json`.
- **Serving**: `start` script using Python's built-in `http.server` (so `fetch()` works for JSON).
- **Tests**: Playwright screenshots under `tests/auto/` to verify UI.

### File layout
```
historyhurricanes/
├── index.html               # Map, dropdown, side panel
├── css/style.css            # Layout + panel styling
├── js/app.js                # Map init, storm loading, interactions
├── data/
│   ├── storms.json          # [{id, name, year, file}]
│   └── storms/
│       └── 1944-cuba-florida.json
├── start                    # Launch local server on :8000
├── stop                     # Stop local server
├── tests/auto/              # Playwright scripts + screenshots
└── projectplan.md
```

### Storm data schema
```json
{
  "id": "1944-cuba-florida",
  "name": "1944 Cuba–Florida Hurricane",
  "year": 1944,
  "summary": "Category 4 over Cuba; landfall near Sarasota Oct 19 as Category 2.",
  "track": [
    {"lat": 21.5, "lng": -83.0, "time": "1944-10-18 00Z", "category": 4}
  ],
  "archives": [
    {
      "id": "key-west",
      "city": "Key West",
      "region": "Florida Keys",
      "lat": 24.5551,
      "lng": -81.7800,
      "news": [
        {"title": "...", "source": "Chronicling America", "url": "..."}
      ],
      "photos": [
        {"title": "...", "source": "Monroe County Public Library (Flickr)", "url": "..."}
      ]
    }
  ]
}
```

### UI flow
1. Load → Florida basemap + dropdown in top-right corner.
2. Select storm → draw polyline track + circle markers at each archive point.
3. Click circle → popup with two buttons: **News** / **Photos**.
4. Click News/Photos → side panel slides in with a list of linked archive items (title, source, URL). Each link opens in a new tab.

## 1944 archive points (from earlier research)
- **Key West** — Monroe County Public Library (Wikimedia Commons, Flickr photostream)
- **Dry Tortugas** — NOAA/NPS references
- **Sarasota** — landfall zone; Sarasota County Historical Resources
- **Venice** — Venice Museum & Archives (PastPerfect)
- **Fort Myers / Estero Island** — Southwest Florida Historical Society
- **Fernandina Beach / Amelia Island** — Amelia Island Museum of History (PastPerfect)
- Statewide fallback: Florida Memory, USF digital collection

News sources: **Chronicling America** (Library of Congress) has free-text search of historical Florida newspapers — generates a permalink per query.

## Todo list

### Phase 1 — MVP (this session)
- [ ] Create directory structure
- [ ] Write `index.html` with Leaflet CDN, dropdown, side panel
- [ ] Write `css/style.css` (map fills viewport, panel slides from right)
- [ ] Write `js/app.js` (load storm list, draw track, circles, popups, panel)
- [ ] Create `data/storms.json` (just 1944 for now)
- [ ] Create `data/storms/1944-cuba-florida.json` with:
  - Approximate track coordinates (Cuba → Dry Tortugas → Sarasota → NE Florida exit)
  - ~6 archive points with real archive/search URLs
- [ ] Create `start` and `stop` scripts
- [ ] Test in browser — verify dropdown, track renders, circles clickable, panel shows links
- [ ] Capture screenshots to `tests/auto/` at each UI state

### Phase 2 — deferred (not this session)
- Replace approximate track with real HURDAT2 coordinates
- Add additional storms (1898 hurricane the user mentioned)
- Embed thumbnail previews for Wikimedia Commons photos via MediaWiki API
- Add storm intensity coloring along track

## Questions before I start
1. **Archive data depth**: For Phase 1, is it OK if each archive point has 2–4 real external links (search URLs into existing archives) rather than individual curated items? Curating individual items = large manual effort; search links are honest about "here's where to look."
2. **Track accuracy**: OK to use ~10 approximate track points for MVP, then refine with HURDAT2 data in Phase 2? Or do you want HURDAT2 from the start?
3. **News source**: Default to Chronicling America search links (free, permalinkable). Or do you have a preferred newspaper archive?

## Review
_To be filled in after implementation._

---

## Phase 3 — UFDC news curator (next up)

### Context
LoC Chronicling America has only thin 1944 FL coverage (La Gaceta, Southern Jewish Weekly, Nassau County Leader, Key West Citizen, Ocala Banner, etc.). Missing from LoC: Tampa Tribune, St. Petersburg Times, Sarasota Herald-Tribune, Orlando Sentinel, Jacksonville Florida Times-Union, Fort Myers News-Press — these live in UFDC (Florida Digital Newspaper Library).

UFDC exposes a JSON API at `api.patron.uflib.ufl.edu` with endpoints including `pagetext`, `exactsearch`, `fdnl_titles_list`. This plan builds a UFDC curator analogous to `curate_news.py` but against that API.

### Todo
- [ ] Probe `fdnl_titles_list` to map each archive city → bibids of 1944-era papers (Tampa Tribune, Sarasota Herald-Tribune, etc.). Save to `tests/auto/ufdc_titles_1944.json` for reuse.
- [ ] Probe `pagetext` with a single known-good query (e.g. phrase=hurricane, datelo=1944-10-12, datehi=1944-10-26, bibid=<Tampa Tribune>) to learn the response shape.
- [ ] Write `tests/auto/curate_ufdc.py`:
  - Per archive city, iterate its mapped bibids.
  - For each bibid, call `pagetext` with `phrase=hurricane`, `datelo=1944-10-12`, `datehi=1944-10-26`.
  - For each hit, keep only items whose page text also mentions the city (proximity check, same as `curate_news.py`).
  - Build item: title (paper + date), url (UFDC viewer with match highlight), thumb (UFDC page thumbnail), snippet, source = "Florida Digital Newspaper Library (UF)".
  - Merge into `data/storms/1944-cuba-florida.json` preserving non-UFDC news.
- [ ] Run it; spot-check one archive in the browser; run `verify_app.py`.

### Pending (after UFDC lands)
- [ ] Retry `curate_news.py` (LoC) when LoC servers recover — same Oct 12–26 window.
- [ ] Final dedupe pass across LoC + UFDC + DPLA so the side panel shows a coherent list per city.
