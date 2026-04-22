/* HurricaneChronicles — interactive Florida hurricane map */
(() => {
  const MAP_CENTER = [27.8, -83.5];
  const MAP_ZOOM = 6;

  const map = L.map('map', {
    zoomControl: true,
    preferCanvas: true,
  }).setView(MAP_CENTER, MAP_ZOOM);
  window.__map = map;

  L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
    attribution: '&copy; OpenStreetMap contributors',
    maxZoom: 18,
  }).addTo(map);

  const stormLayer = L.layerGroup().addTo(map);
  const archiveLayer = L.layerGroup().addTo(map);

  const panel = document.getElementById('panel');
  const panelTitle = document.getElementById('panel-title');
  const panelSubtitle = document.getElementById('panel-subtitle');
  const panelBody = document.getElementById('panel-body');
  document.getElementById('panel-close').addEventListener('click', () => {
    panel.hidden = true;
  });

  const summaryEl = document.getElementById('summary');
  const summaryTitle = document.getElementById('summary-title');
  const summaryText = document.getElementById('summary-text');
  const summarySource = document.getElementById('summary-source');

  const select = document.getElementById('storm-select');
  select.addEventListener('change', () => loadStorm(select.value));

  fetch('data/storms.json')
    .then(r => r.json())
    .then(storms => {
      storms.forEach(s => {
        const opt = document.createElement('option');
        opt.value = s.file;
        opt.textContent = `${s.year} — ${s.name}`;
        select.appendChild(opt);
      });
      if (storms.length) loadStorm(storms[0].file);
    });

  function loadStorm(file) {
    stormLayer.clearLayers();
    archiveLayer.clearLayers();
    panel.hidden = true;

    fetch('data/' + file)
      .then(r => r.json())
      .then(storm => {
        document.getElementById('storm-meta').textContent =
          `${storm.date_range}  •  HURDAT2 ${storm.hurdat_id}`;
        renderSummary(storm);
        renderTrack(storm.track);
        renderArchives(storm.archives);
        renderMisc(storm);
      });
  }

  function renderMisc(storm) {
    const btn = document.getElementById('misc-btn');
    const misc = storm.misc || { photos: [], news: [] };
    const total = (misc.photos?.length || 0) + (misc.news?.length || 0);
    if (!total) {
      btn.hidden = true;
      btn.onclick = null;
      return;
    }
    btn.textContent = `MISC (${total})`;
    btn.title = 'Storm-wide references — not tied to a single city';
    btn.hidden = false;
    btn.onclick = () => {
      const virtualArchive = {
        city: 'Miscellaneous',
        region: `${storm.name} — storm-wide references`,
        photos: misc.photos || [],
        news: misc.news || [],
      };
      const kind = (misc.news?.length || 0) >= (misc.photos?.length || 0) ? 'news' : 'photos';
      openPanel(virtualArchive, kind);
    };
  }

  function renderSummary(storm) {
    summaryTitle.textContent = storm.name;
    summaryText.textContent = storm.summary;
    summarySource.textContent = `Track: ${storm.source_track}`;
    summaryEl.hidden = false;
  }

  const BASE_RADIUS = 3.5;
  const BASE_LANDFALL_RADIUS = 7;
  const BASE_ZOOM = 6;
  const trackMarkers = [];

  function zoomScale() {
    const z = map.getZoom();
    return Math.max(0.85, 1 + (z - BASE_ZOOM) * 0.18);
  }

  function applyZoomRadius() {
    const s = zoomScale();
    trackMarkers.forEach(({ marker, isLandfall }) => {
      marker.setRadius((isLandfall ? BASE_LANDFALL_RADIUS : BASE_RADIUS) * s);
    });
  }

  map.on('zoomend', applyZoomRadius);

  function renderTrack(track) {
    trackMarkers.length = 0;

    const coords = track.map(p => [p.lat, p.lng]);
    L.polyline(coords, {
      color: '#1f4cc4',
      weight: 3,
      opacity: 0.85,
    }).addTo(stormLayer);

    const s = zoomScale();
    track.forEach(p => {
      const color = catColor(p.saffir_simpson, p.status);
      const isLandfall = p.landfall;
      const marker = L.circleMarker([p.lat, p.lng], {
        radius: (isLandfall ? BASE_LANDFALL_RADIUS : BASE_RADIUS) * s,
        color: isLandfall ? '#fff' : color,
        weight: isLandfall ? 2 : 1,
        fillColor: isLandfall ? '#d64500' : color,
        fillOpacity: 0.9,
      }).addTo(stormLayer);
      trackMarkers.push({ marker, isLandfall: !!isLandfall });

      const when = formatWhen(p.date, p.time_utc);
      const cat = p.status === 'HU' ? `Cat ${p.saffir_simpson}` : p.status;
      const press = p.pressure_mb ? `, ${p.pressure_mb} mb` : '';
      const content = document.createElement('div');
      content.textContent = `${when} UTC — ${cat} · ${p.wind_kt} kt${press}${isLandfall ? ' · LANDFALL' : ''}`;
      marker.bindPopup(content, { closeButton: true, autoClose: true, closeOnClick: true });
    });
  }

  function catColor(cat, status) {
    if (status === 'EX') return '#888';
    if (status === 'TD') return '#4aa3df';
    if (status === 'TS') return '#3aaf5f';
    if (cat <= 1) return '#f4c430';
    if (cat === 2) return '#f39c12';
    if (cat === 3) return '#e67e22';
    if (cat === 4) return '#d64500';
    return '#9b1818';
  }

  function formatWhen(date, time) {
    const y = date.slice(0, 4), m = date.slice(4, 6), d = date.slice(6, 8);
    const hh = time.slice(0, 2), mm = time.slice(2, 4);
    return `${y}-${m}-${d} ${hh}:${mm}`;
  }

  function renderArchives(archives) {
    const nonEmpty = archives.filter(a =>
      (a.photos?.length || 0) + (a.news?.length || 0) > 0
    );
    nonEmpty.forEach(a => {
      const marker = L.circleMarker([a.lat, a.lng], {
        radius: 9,
        color: '#003147',
        weight: 2,
        fillColor: '#ffffff',
        fillOpacity: 0.95,
      }).addTo(archiveLayer);

      marker.bindTooltip(a.city, { direction: 'top', permanent: false });

      marker.on('click', () => {
        const popupContent = buildPopup(a);
        L.popup({ closeButton: true, autoPan: true })
          .setLatLng([a.lat, a.lng])
          .setContent(popupContent)
          .openOn(map);
      });
    });
  }

  function buildPopup(archive) {
    const div = document.createElement('div');
    div.className = 'popup-choice';

    const h3 = document.createElement('h3');
    h3.textContent = archive.city;
    div.appendChild(h3);

    if (archive.note) {
      const p = document.createElement('p');
      p.className = 'popup-note';
      p.textContent = archive.note;
      div.appendChild(p);
    }

    const btnRow = document.createElement('div');
    btnRow.className = 'buttons';

    const photoCount = archive.photos?.length || 0;
    const newsCount = archive.news?.length || 0;

    const photoBtn = document.createElement('button');
    photoBtn.textContent = photoCount ? `Photos (${photoCount})` : 'Photos';
    photoBtn.disabled = !photoCount;
    photoBtn.addEventListener('click', () => {
      map.closePopup();
      openPanel(archive, 'photos');
    });

    const newsBtn = document.createElement('button');
    newsBtn.textContent = newsCount ? `News (${newsCount})` : 'News';
    newsBtn.disabled = !newsCount;
    newsBtn.addEventListener('click', () => {
      map.closePopup();
      openPanel(archive, 'news');
    });

    btnRow.append(photoBtn, newsBtn);
    div.appendChild(btnRow);
    return div;
  }

  function openPanel(archive, kind) {
    panelTitle.textContent = `${archive.city} — ${kind === 'photos' ? 'Photos' : 'News'}`;
    panelSubtitle.textContent = archive.region || '';

    // Clear
    while (panelBody.firstChild) panelBody.removeChild(panelBody.firstChild);

    const items = kind === 'photos' ? archive.photos : archive.news;
    if (!items || items.length === 0) {
      const p = document.createElement('p');
      p.style.color = '#888';
      p.style.padding = '20px 0';
      p.textContent = 'No items available.';
      panelBody.appendChild(p);
      panel.hidden = false;
      return;
    }

    items.forEach(it => panelBody.appendChild(buildItem(it)));
    panel.hidden = false;
  }

  function buildItem(it) {
    const el = document.createElement('div');
    el.className = 'item';

    if (it.thumb) {
      const thumbLink = document.createElement('a');
      thumbLink.className = 'item-thumb';
      thumbLink.href = it.url;
      thumbLink.target = '_blank';
      thumbLink.rel = 'noopener';
      const img = document.createElement('img');
      img.src = it.thumb;
      img.alt = it.title || '';
      img.loading = 'lazy';
      thumbLink.appendChild(img);
      el.appendChild(thumbLink);
    }

    const body = document.createElement('div');
    body.className = 'item-body';

    const titleLink = document.createElement('a');
    titleLink.className = 'item-title';
    titleLink.href = it.url;
    titleLink.target = '_blank';
    titleLink.rel = 'noopener';

    const badge = buildBadge(it.kind, it.count);
    if (badge) titleLink.appendChild(badge);
    titleLink.appendChild(document.createTextNode(it.title || ''));
    body.appendChild(titleLink);

    if (it.description) {
      const desc = document.createElement('p');
      desc.className = 'item-desc';
      desc.textContent = it.description;
      body.appendChild(desc);
    }

    const terms = it.highlight_terms || DEFAULT_HIGHLIGHT_TERMS;

    if (it.snippet) {
      const snip = document.createElement('p');
      snip.className = 'item-snippet';
      appendHighlighted(snip, it.snippet, terms);
      body.appendChild(snip);
    }

    if (it.article_text) {
      const isSpanish = it.article_language === 'es' && it.article_text_en;
      if (isSpanish) {
        body.appendChild(makeLabel('Original (Spanish)'));
        body.appendChild(makeHighlightedBlock(it.article_text, terms, 'item-article'));
        body.appendChild(makeLabel('English translation'));
        body.appendChild(makeHighlightedBlock(it.article_text_en, terms, 'item-article-en'));
      } else {
        body.appendChild(makeHighlightedBlock(it.article_text, terms, 'item-article'));
      }
      const viewLink = document.createElement('a');
      viewLink.className = 'item-view-original';
      viewLink.href = it.url;
      viewLink.target = '_blank';
      viewLink.rel = 'noopener';
      viewLink.textContent = 'View original page →';
      body.appendChild(viewLink);
    }

    if (it.kind === 'retrospective' && it.summary) {
      if (it.byline) {
        const by = document.createElement('div');
        by.className = 'item-byline';
        by.textContent = it.byline;
        body.appendChild(by);
      }
      const label = document.createElement('div');
      label.className = 'item-summary-label';
      label.textContent = 'Summary (our words)';
      body.appendChild(label);
      const summary = document.createElement('div');
      summary.className = 'item-summary';
      summary.textContent = it.summary;
      body.appendChild(summary);
      const readLink = document.createElement('a');
      readLink.className = 'item-view-original';
      readLink.href = it.url;
      readLink.target = '_blank';
      readLink.rel = 'noopener';
      readLink.textContent = `Read the full story at ${it.source || 'the source'} →`;
      body.appendChild(readLink);
    }

    if (it.date && !it.snippet) {
      // show date badge only when no snippet provides context
      const d = document.createElement('div');
      d.className = 'item-date';
      d.textContent = it.date;
      body.appendChild(d);
    } else if (it.date && it.snippet) {
      const d = document.createElement('div');
      d.className = 'item-date';
      d.textContent = it.date;
      body.insertBefore(d, body.firstChild.nextSibling); // after title
    }

    if (it.source) {
      const src = document.createElement('div');
      src.className = 'item-source';
      src.textContent = it.source;
      body.appendChild(src);
    }

    el.appendChild(body);
    return el;
  }

  function escapeHtml(s) {
    return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
  }

  function highlightStorm(text) {
    const escaped = escapeHtml(text);
    const pattern = /(hurricane|huracanes?|hurac\u00e1n|huracanes|ciclones?|cicl\u00f3n|cyclone|tropical|storm|tormenta|gale|flood|flooded|damage|damaged|destroyed|destruction)/gi;
    return escaped.replace(pattern, '<mark>$1</mark>');
  }

  const DEFAULT_HIGHLIGHT_TERMS = [
    'hurricane', 'hurricanes', 'cyclone', 'cyclones',
    'tropical', 'storm', 'storms', 'tormenta', 'tempestad', 'gale',
    'flood', 'flooded', 'damage', 'damaged', 'destroyed', 'destruction',
    'huracán',
    'huracánes',
    'ciclón',
    'ciclones',
  ];

  function escapeRegex(s) {
    return s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  }

  function appendHighlighted(parent, text, terms) {
    if (!text) return;
    if (!terms || terms.length === 0) {
      parent.appendChild(document.createTextNode(text));
      return;
    }
    const pattern = new RegExp('(' + terms.map(escapeRegex).join('|') + ')', 'gi');
    const parts = text.split(pattern);
    for (let i = 0; i < parts.length; i++) {
      if (!parts[i]) continue;
      if (i % 2 === 1) {
        const mark = document.createElement('mark');
        mark.textContent = parts[i];
        parent.appendChild(mark);
      } else {
        parent.appendChild(document.createTextNode(parts[i]));
      }
    }
  }

  function makeLabel(text) {
    const el = document.createElement('div');
    el.className = 'item-article-label';
    el.textContent = text;
    return el;
  }

  function makeHighlightedBlock(text, terms, className) {
    const el = document.createElement('div');
    el.className = className;
    appendHighlighted(el, text, terms);
    return el;
  }

  function buildBadge(kind, count) {
    if (!kind) return null;
    const labels = {
      collection: `Collection${count ? ` · ${count}` : ''}`,
      portal: 'Portal',
      search: 'Search',
      retrospective: 'Retrospective',
      encyclopedia: 'Encyclopedia',
      'primary-document': 'Primary document',
    };
    if (!(kind in labels)) return null;
    const span = document.createElement('span');
    span.className = `badge ${kind}`;
    span.textContent = labels[kind];
    return span;
  }
})();
