/* GeoTech Satellite — front-end logic (Leaflet map + assessment UI). */
"use strict";

// ---- Map with live satellite imagery + zoom ------------------------------
const map = L.map("map", { center: [20, 10], zoom: 3, worldCopyJump: true,
  maxZoom: 21, zoomControl: true });

const satellite = L.tileLayer(
  "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
  { maxZoom: 21, maxNativeZoom: 19, detectRetina: true, crossOrigin: true,
    attribution: "Imagery © Esri, Maxar, Earthstar Geographics" }
).addTo(map);

const labels = L.tileLayer(
  "https://server.arcgisonline.com/ArcGIS/rest/services/Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}",
  { maxZoom: 19, opacity: 0.9 }
).addTo(map);

const streets = L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
  maxZoom: 19, attribution: "© OpenStreetMap contributors",
});

const topo = L.tileLayer("https://{s}.tile.opentopomap.org/{z}/{x}/{y}.png", {
  maxZoom: 17, attribution: "© OpenTopoMap (CC-BY-SA)",
});

// Sentinel-2 cloudless annual mosaic (EOX) — real Sentinel-2, no API key.
const sentinel = L.tileLayer(
  "https://tiles.maps.eox.at/wmts/1.0.0/s2cloudless-2021_3857/default/g/{z}/{y}/{x}.jpg",
  { maxNativeZoom: 15, maxZoom: 19,
    attribution: "Sentinel-2 cloudless 2021 © EOX IT Services (contains modified Copernicus Sentinel data)" }
);

// Hydro reference overlay (rivers, lakes, coastline) — transparent, keyless.
const hydro = L.tileLayer(
  "https://services.arcgisonline.com/arcgis/rest/services/Reference/World_Hydro_Reference_Overlay/MapServer/tile/{z}/{y}/{x}",
  { maxZoom: 19, opacity: 0.9, attribution: "Hydro reference © Esri" });

L.control.layers(
  { "Satellite (Esri)": satellite, "Sentinel-2 (cloudless)": sentinel,
    "Street map": streets, "Topographic": topo },
  { "Place labels": labels, "Water / hydrology": hydro },
  { position: "topright", collapsed: true }
).addTo(map);

// Layer group for the nearest-water marker + connector line (per assessment).
const waterGroup = L.layerGroup().addTo(map);
L.control.scale({ imperial: false }).addTo(map);

let marker = null;
const $ = (id) => document.getElementById(id);

function setSite(lat, lon, fly) {
  lat = +(+lat).toFixed(6);
  lon = +(+lon).toFixed(6);
  $("lat").value = lat;
  $("lon").value = lon;
  const cr = $("coordReadout");
  cr.dataset.base = `Site: ${lat}, ${lon}`;
  cr.textContent = cr.dataset.base;
  if (marker) marker.setLatLng([lat, lon]);
  else marker = L.marker([lat, lon], { draggable: true }).addTo(map)
          .on("dragend", (e) => { const p = e.target.getLatLng(); setSite(p.lat, p.lng, false); });
  if (fly) map.flyTo([lat, lon], Math.max(map.getZoom(), 14), { duration: 0.8 });
}

map.on("click", (e) => setSite(e.latlng.lat, e.latlng.lng, false));

// ---- Map tools: fullscreen, zoom-to-site, screenshot, video recorder -----
$("fsBtn").onclick = () => {
  const pane = document.querySelector(".map-pane");
  if (!document.fullscreenElement) {
    (pane.requestFullscreen ? pane.requestFullscreen() : Promise.reject())
      .then(() => setTimeout(() => map.invalidateSize(), 200)).catch(() => {});
  } else {
    document.exitFullscreen().then(() => setTimeout(() => map.invalidateSize(), 200));
  }
};
document.addEventListener("fullscreenchange", () => setTimeout(() => map.invalidateSize(), 200));

$("zoomSiteBtn").onclick = () => {
  const lat = parseFloat($("lat").value), lon = parseFloat($("lon").value);
  if (Number.isNaN(lat) || Number.isNaN(lon)) {
    flash("Pick a site first (click the map or search)."); return;
  }
  map.flyTo([lat, lon], 19, { duration: 0.9 });
};

$("shotBtn").onclick = () => {
  const c = map.getCenter();
  const z = Math.min(Math.round(map.getZoom()), 19);
  flash("Capturing live satellite image…");
  const url = `/api/sitemap.png?lat=${c.lat.toFixed(6)}&lon=${c.lng.toFixed(6)}&zoom=${z}&grid=3`;
  // Fetch then download (so errors are visible instead of a broken file).
  fetch(url).then(async (r) => {
    if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || r.statusText);
    const blob = await r.blob();
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `satellite_${c.lat.toFixed(4)}_${c.lng.toFixed(4)}_z${z}.png`;
    a.click(); URL.revokeObjectURL(a.href);
    flash("Screenshot downloaded.");
  }).catch((e) => flash("Screenshot failed: " + e.message));
};

// Screen/tab video recorder via getDisplayMedia + MediaRecorder.
let mediaRecorder = null, recChunks = [], recStream = null;
$("recBtn").onclick = async () => {
  if (mediaRecorder && mediaRecorder.state !== "inactive") {
    mediaRecorder.stop();
    return;
  }
  if (!navigator.mediaDevices || !navigator.mediaDevices.getDisplayMedia) {
    flash("Recording not supported in this browser."); return;
  }
  try {
    recStream = await navigator.mediaDevices.getDisplayMedia({
      video: { frameRate: 30 }, audio: false });
    const mime = MediaRecorder.isTypeSupported("video/webm;codecs=vp9")
      ? "video/webm;codecs=vp9" : "video/webm";
    mediaRecorder = new MediaRecorder(recStream, { mimeType: mime });
    recChunks = [];
    mediaRecorder.ondataavailable = (e) => { if (e.data.size) recChunks.push(e.data); };
    mediaRecorder.onstop = () => {
      recStream.getTracks().forEach((t) => t.stop());
      const blob = new Blob(recChunks, { type: "video/webm" });
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = `geotech_recording_${Date.now()}.webm`;
      a.click(); URL.revokeObjectURL(a.href);
      $("recBtn").textContent = "⏺ Rec";
      $("recBtn").classList.remove("recording");
      flash("Recording saved.");
    };
    // Stop automatically if the user ends the screen share.
    recStream.getVideoTracks()[0].addEventListener("ended", () => {
      if (mediaRecorder && mediaRecorder.state !== "inactive") mediaRecorder.stop();
    });
    mediaRecorder.start();
    $("recBtn").textContent = "⏹ Stop";
    $("recBtn").classList.add("recording");
    flash("Recording… click ⏹ Stop (or end sharing) to save.");
  } catch (e) {
    flash("Recording cancelled.");
  }
};

let _flashT = null;
function flash(msg) {
  const el = $("coordReadout");
  if (!el) return;
  el.textContent = msg;
  clearTimeout(_flashT);
  _flashT = setTimeout(() => {
    el.textContent = el.dataset.base || "Click the map or search to drop a site pin";
  }, 3500);
}

// ---- Place search (browser-side Nominatim) -------------------------------
async function searchPlace() {
  const q = $("placeInput").value.trim();
  if (!q) return;
  $("status").textContent = "Searching…";
  try {
    const r = await fetch(
      `https://nominatim.openstreetmap.org/search?format=json&limit=1&q=${encodeURIComponent(q)}`,
      { headers: { "Accept": "application/json" } }
    );
    const data = await r.json();
    if (!data.length) { $("status").textContent = "Place not found."; return; }
    setSite(data[0].lat, data[0].lon, true);
    if (!$("projectName").value) $("projectName").value = (data[0].display_name || q).split(",")[0];
    $("status").textContent = "";
  } catch (err) {
    $("status").textContent = "Search failed (offline?). Click the map instead.";
  }
}
$("searchBtn").onclick = searchPlace;
$("placeInput").addEventListener("keydown", (e) => { if (e.key === "Enter") searchPlace(); });

// ---- Borehole / measured ground data -------------------------------------
function addBhRow(v = {}) {
  const row = document.createElement("div");
  row.className = "bh-row";
  row.innerHTML = `
    <input class="bh-top" type="number" step="0.1" value="${v.top ?? ""}" />
    <input class="bh-bot" type="number" step="0.1" value="${v.bot ?? ""}" />
    <input class="bh-desc" type="text" placeholder="stiff CLAY" value="${v.desc ?? ""}" />
    <input class="bh-uscs" type="text" placeholder="CL" value="${v.uscs ?? ""}" />
    <input class="bh-n" type="number" step="1" placeholder="N" value="${v.n ?? ""}" />
    <button type="button" class="bh-del" title="Remove">✕</button>`;
  row.querySelector(".bh-del").onclick = () => row.remove();
  $("bhRows").appendChild(row);
}
$("bhAdd").onclick = () => addBhRow();

// Parse pasted/uploaded CSV (or TSV) into borehole rows. Flexible headers.
function parseBhCsv(text) {
  const lines = text.split(/\r?\n/).map((l) => l.trim()).filter(Boolean);
  if (!lines.length) return { rows: [], err: "No data found." };
  const delim = lines[0].includes("\t") ? "\t" : (lines[0].includes(";") ? ";" : ",");
  const split = (l) => l.split(delim).map((c) => c.trim().replace(/^"|"$/g, ""));
  let start = 0, idx = { top: 0, bot: 1, desc: 2, uscs: 3, n: 4 };
  const first = split(lines[0]).map((c) => c.toLowerCase());
  const looksHeader = first.some((c) => /top|base|bottom|depth|desc|uscs|spt|^n$/.test(c));
  if (looksHeader) {
    start = 1;
    const find = (re, d) => { const i = first.findIndex((c) => re.test(c)); return i < 0 ? d : i; };
    idx = {
      top: find(/top|from|depth.*top|^depth$/, 0),
      bot: find(/base|bottom|to\b|depth.*base/, 1),
      desc: find(/desc|soil|strata|material/, 2),
      uscs: find(/uscs|class|symbol/, 3),
      n: find(/spt|blows|^n$|n.?value/, 4),
    };
  }
  const rows = [];
  for (let i = start; i < lines.length; i++) {
    const c = split(lines[i]);
    const top = parseFloat(c[idx.top]), bot = parseFloat(c[idx.bot]);
    if (Number.isNaN(top) || Number.isNaN(bot) || bot <= top) continue;
    const nv = c[idx.n] != null ? parseInt(c[idx.n], 10) : NaN;
    rows.push({ top, bot, desc: c[idx.desc] || "", uscs: c[idx.uscs] || "",
      n: Number.isNaN(nv) ? "" : nv });
  }
  return { rows, err: rows.length ? null : "No valid layer rows (need numeric top<base)." };
}

function loadBhCsv(text) {
  const { rows, err } = parseBhCsv(text);
  const msg = $("bhCsvMsg");
  if (err) { msg.textContent = "⚠ " + err; return; }
  if ([...document.querySelectorAll(".bh-row")].length &&
      !confirm(`Replace current layers with ${rows.length} imported row(s)?`)) return;
  $("bhRows").innerHTML = "";
  rows.forEach(addBhRow);
  msg.textContent = `✔ Imported ${rows.length} layer(s).`;
  document.querySelector("details.borehole").open = true;
}

$("bhLoadCsv").onclick = () => loadBhCsv($("bhCsv").value);
$("bhFile").onchange = (e) => {
  const f = e.target.files[0];
  if (!f) return;
  const rd = new FileReader();
  rd.onload = () => { $("bhCsv").value = rd.result; loadBhCsv(rd.result); };
  rd.readAsText(f);
};

function readBorehole() {
  const rows = [...document.querySelectorAll(".bh-row")];
  const layers = [];
  for (const r of rows) {
    const top = parseFloat(r.querySelector(".bh-top").value);
    const bot = parseFloat(r.querySelector(".bh-bot").value);
    if (Number.isNaN(top) || Number.isNaN(bot) || bot <= top) continue;
    const nRaw = r.querySelector(".bh-n").value;
    layers.push({
      top_m: top, bottom_m: bot,
      description: r.querySelector(".bh-desc").value || null,
      uscs: r.querySelector(".bh-uscs").value || null,
      spt_n: nRaw === "" ? null : parseInt(nRaw, 10),
    });
  }
  const gwRaw = $("bhGw").value;
  const gw = gwRaw === "" ? null : parseFloat(gwRaw);
  if (!layers.length && gw == null) return null;
  return { layers, groundwater_depth_m: gw };
}

// ---- Run assessment ------------------------------------------------------
function payload() {
  const lat = parseFloat($("lat").value), lon = parseFloat($("lon").value);
  if (Number.isNaN(lat) || Number.isNaN(lon)) return null;
  const body = {
    lat, lon,
    project_name: $("projectName").value || null,
    foundation_width_m: parseFloat($("fw").value) || 2.0,
    foundation_depth_m: parseFloat($("fd").value) || 1.5,
  };
  const fl = parseFloat($("fl").value);
  if (!Number.isNaN(fl) && fl > 0) body.foundation_length_m = fl;
  const iv = parseFloat($("insar").value);
  if (!Number.isNaN(iv)) body.insar_velocity_mm_yr = iv;
  const ba = parseFloat($("bldgArea").value);
  if (!Number.isNaN(ba) && ba > 0) body.building_floor_area_m2 = ba;
  if ($("bldgType").value) body.building_type = $("bldgType").value;
  const bh = readBorehole();
  if (bh) body.borehole = bh;
  return body;
}

$("runBtn").onclick = async () => {
  const body = payload();
  if (!body) { setErr("Pick a location first (click the map or search)."); return; }
  const ai = $("ai").checked;
  $("runBtn").disabled = true;
  $("status").className = "status";
  $("status").textContent = ai ? "Fetching live data & writing AI commentary…"
    : "Fetching live satellite & geospatial data…";
  try {
    const r = await fetch(`/api/assess?ai=${ai}`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!r.ok) throw new Error((await r.json()).detail || r.statusText);
    const a = await r.json();
    render(a);
    $("status").textContent = "";
    lastPayload = { body, ai };
    $("actions").hidden = false;
  } catch (err) {
    setErr("Assessment failed: " + err.message);
  } finally {
    $("runBtn").disabled = false;
  }
};

function setErr(msg) { const s = $("status"); s.className = "status err"; s.textContent = msg; }

// ---- PDF download --------------------------------------------------------
let lastPayload = null;
$("pdfBtn").onclick = async () => {
  if (!lastPayload) return;
  $("pdfBtn").textContent = "Building PDF…";
  try {
    const r = await fetch(`/api/report.pdf?ai=${lastPayload.ai}`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(lastPayload.body),
    });
    if (!r.ok) throw new Error(r.statusText);
    const blob = await r.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url; a.download = "geotech_report.pdf"; a.click();
    URL.revokeObjectURL(url);
  } catch (err) { setErr("PDF failed: " + err.message); }
  $("pdfBtn").textContent = "⬇ Download PDF report";
};

// ---- Rendering -----------------------------------------------------------
const esc = (s) => String(s ?? "—").replace(/[&<>"]/g, (c) =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const cls = (lvl) => "badge " + String(lvl || "").replace(/\s+/g, "");
const sev = (lvl) => ({ Low: 20, "Low to Moderate": 35, Moderate: 50,
  "Moderate to high": 60, High: 75, "Very High": 92 }[lvl] ?? 40);

// Texture → fill colour for the soil-profile column.
const TEXCOLOR = {
  Sand: "#e3c884", "Loamy sand": "#d9b86a", "Sandy loam": "#c9a24f",
  Loam: "#a8894a", "Silt loam": "#b9a06a", Silt: "#cdbb8a",
  "Sandy clay loam": "#9a7b53", "Clay loam": "#8a6b4a", "Silty clay loam": "#7d6150",
  "Sandy clay": "#8f6b55", "Silty clay": "#6f5648", Clay: "#5e4a3f",
};

function kv(pairs) {
  return `<div class="kv">` + pairs.map(([k, v]) =>
    `<div class="k">${esc(k)}</div><div class="v">${esc(v)}</div>`).join("") + `</div>`;
}

const sevColor = (p) => p < 30 ? "#2e7d32" : p < 50 ? "#f9a825" : p < 70 ? "#ef6c00" : "#c62828";

function suitabilityGauge(su) {
  const score = su.score;
  const color = score >= 75 ? "#2e7d32" : score >= 55 ? "#f9a825"
    : score >= 35 ? "#ef6c00" : "#c62828";
  const drivers = (su.drivers || []).map((d) => `<li>${esc(d)}</li>`).join("");
  return `<div class="suit">
    <div class="gauge" style="--pct:${score};--col:${color}">
      <div class="gauge-inner"><span class="gscore">${score}</span><span class="gmax">/100</span></div>
    </div>
    <div class="suit-text">
      <div class="suit-rating" style="color:${color}">${esc(su.rating)}</div>
      <div class="suit-sum">${esc(su.summary)}</div>
      <ul class="suit-drivers">${drivers}</ul>
    </div></div>`;
}

function hazardMeters(hazards) {
  return hazards.map((h) => {
    const insuff = /insufficient/i.test(h.level || "");
    const p = insuff ? 0 : sev(h.level);
    const badge = insuff ? "badge insuff" : cls(h.level);
    const bar = insuff ? "" :
      `<div class="meter"><div class="meter-fill" style="width:${p}%;background:${sevColor(p)}"></div></div>`;
    return `<div class="meter-row">
      <div class="meter-head"><span>${esc(h.name)}</span>
        <span class="${badge}">${esc(h.level)}</span></div>
      ${bar}<div class="meter-why">${esc(h.rationale)}</div></div>`;
  }).join("");
}

// Format a possibly-null value with an optional unit suffix.
const u = (v, suffix = "") => (v == null || v === "" ? "—" : v + suffix);

function soilColumn(soil) {
  const layers = soil.layers || [];
  if (!layers.length) return "";
  const maxD = layers[layers.length - 1].bottom_cm || 200;
  const bars = layers.map((l) => {
    const h = ((l.bottom_cm - l.top_cm) / maxD) * 100;
    const col = TEXCOLOR[l.usda_texture] || "#8a7a63";
    return `<div class="soil-seg" style="height:${h}%;background:${col}"
      title="${esc(l.depth_label)}: ${esc(l.usda_texture)}">
      <span class="soil-lab">${esc(l.usda_texture || "")} · ${esc(l.clay_pct)}% clay</span></div>`;
  }).join("");
  return `<div class="soil-viz"><div class="soil-col">${bars}</div>
    <div class="soil-axis"><span>0</span><span>${maxD} cm</span></div></div>`;
}

function bearingChart(curve) {
  if (!curve || !curve.length) return "";
  const W = 320, H = 150, pad = 34;
  const xs = curve.map((p) => p.width_m), ys = curve.map((p) => p.allowable_kpa);
  const xmax = Math.max(...xs), ymax = Math.max(...ys, 10);
  const px = (x) => pad + (x / xmax) * (W - pad - 8);
  const py = (y) => H - pad - (y / ymax) * (H - pad - 10);
  const pts = curve.map((p) => `${px(p.width_m)},${py(p.allowable_kpa)}`).join(" ");
  const dots = curve.map((p) => `<circle cx="${px(p.width_m)}" cy="${py(p.allowable_kpa)}" r="2.5" fill="#2a7f62"/>`).join("");
  return `<svg class="chart" viewBox="0 0 ${W} ${H}" width="100%">
    <line x1="${pad}" y1="${H - pad}" x2="${W - 6}" y2="${H - pad}" stroke="#2a3a47"/>
    <line x1="${pad}" y1="10" x2="${pad}" y2="${H - pad}" stroke="#2a3a47"/>
    <polyline points="${pts}" fill="none" stroke="#2a7f62" stroke-width="2"/>${dots}
    <text x="${W / 2}" y="${H - 6}" fill="#9fb3c0" font-size="10" text-anchor="middle">Footing width B (m)</text>
    <text x="10" y="${H / 2}" fill="#9fb3c0" font-size="10" transform="rotate(-90 10 ${H / 2})" text-anchor="middle">q_allow (kPa)</text>
    <text x="${pad}" y="10" fill="#6f8497" font-size="9">${ymax.toFixed(0)}</text>
  </svg>`;
}

// Section heading with a data-provenance badge + source link.
// kind: measured | modelled | estimated
function head(emoji, title, kind, name, url) {
  const label = { measured: "Measured", modelled: "Modelled",
    estimated: "Estimated" }[kind] || kind;
  const src = url
    ? `<a class="src-link" href="${url}" target="_blank" rel="noopener">${esc(name)} ↗</a>`
    : `<span class="src-link">${esc(name)}</span>`;
  return `<div class="sec-head"><h3>${emoji} ${title}</h3>
    <span class="src-badge ${kind}" title="${label} data">${label}</span>${src}</div>`;
}

function render(a) {
  const badge = $("modeBadge");
  badge.textContent = "LIVE DATA";
  badge.className = "mode-badge live";

  const t = a.terrain, p = a.parameters, s = a.seismic, cl = a.climate || {},
    vg = a.vegetation || {}, hy = a.hydrology || {};

  // Draw nearest-water marker + dashed connector line.
  waterGroup.clearLayers();
  if (hy.nearest_water_lat != null && hy.nearest_water_lon != null) {
    const wll = [hy.nearest_water_lat, hy.nearest_water_lon];
    L.circleMarker(wll, { radius: 6, color: "#39a0ff", fillColor: "#39a0ff", fillOpacity: 0.9 })
      .bindTooltip(`Nearest water (${hy.nearest_water_type || "water"}) · ${hy.nearest_water_m} m`)
      .addTo(waterGroup);
    L.polyline([[a.location.lat, a.location.lon], wll],
      { color: "#39a0ff", weight: 2, dashArray: "5,6", opacity: 0.8 }).addTo(waterGroup);
  }
  let html = "";

  if (a.warnings && a.warnings.length)
    html += `<div class="warn">⚠ ${a.warnings.map(esc).join(" ")}</div>`;

  html += `<h3>📍 ${esc(a.location.display_name || a.project_name)}</h3>`;
  html += `<div class="sub">${a.location.lat.toFixed(5)}, ${a.location.lon.toFixed(5)}`
    + (a.location.country ? ` · ${esc(a.location.country)}` : "") + ` · ${esc(a.generated_utc)}</div>`;

  if (a.suitability) html += suitabilityGauge(a.suitability);

  if (a.commentary) {
    html += `<div class="commentary"><div class="commentary-head">🧠 AI engineering commentary</div>
      <p>${esc(a.commentary).replace(/\n+/g, "</p><p>")}</p>
      <div class="commentary-foot">Generated by ${esc(a.commentary_model || "LLM")} —
      interprets the data above; not a professional sign-off.</div></div>`;
  }

  html += head("⚠️", "Geohazard screening", "estimated", "derived from data below", null)
    + hazardMeters(a.hazards);

  html += head("🪨", "Soil profile (to 2 m)", "modelled", "ISRIC SoilGrids", "https://soilgrids.org/");
  const l0 = a.soil.layers[0];
  const clayStr = l0
    ? (l0.clay_low_pct != null
        ? `${l0.clay_pct}% (${l0.clay_low_pct}–${l0.clay_high_pct}%)` : l0.clay_pct + "%")
    : "—";
  html += `<div class="split"><div>${soilColumn(a.soil)}</div><div>` + kv([
    ["Dominant", `${esc(a.soil.dominant_usda_texture)} (${esc(a.soil.dominant_uscs_group)})`],
    ["Topsoil clay (5–95%)", clayStr],
    ["Model confidence", a.soil.texture_confidence || "—"],
    ["Source", a.soil.source || "SoilGrids"],
  ]) + `</div></div>`;

  const measured = p.data_basis === "borehole";
  html += head("🏗️", "Foundation &amp; parameters",
    measured ? "measured" : "estimated",
    measured ? "your borehole data (SPT/Meyerhof)" : "derived (Terzaghi/Vesic + ref. values)",
    null);
  if (measured)
    html += `<div class="bh-note">✔ Computed from your measured borehole log, overriding the satellite soil estimate.</div>`;
  const paramRows = [
    ["Recommended", p.recommended_foundation],
    ["Net allowable bearing", p.allowable_bearing_kpa == null ? "—" : p.allowable_bearing_kpa + " kPa (FS 3)"],
    ["Ultimate bearing", u(p.ultimate_bearing_kpa, " kPa")],
    ["Est. settlement", u(p.settlement_mm, " mm")],
    ["Min. founding depth", u(p.min_founding_depth_m, " m")],
    ["Friction φ' / cohesion c", (u(p.friction_angle_deg, "°")) + " / " + u(p.cohesion_kpa, " kPa")],
    ["Unit weight / Es", u(p.unit_weight_kn_m3, " kN/m³") + " / " + u(p.elastic_modulus_mpa, " MPa")],
    ["Typical SPT N", p.typical_spt_n],
    ["Seismic site class", p.vs30_proxy_mps == null ? u(p.seismic_site_class)
      : p.seismic_site_class + " (Vs30~" + p.vs30_proxy_mps + ")"],
  ];
  html += kv(paramRows);
  html += `<div class="chart-wrap"><div class="chart-title">Allowable bearing vs footing width</div>`
    + bearingChart(p.bearing_curve) + `</div>`;

  if (a.borehole && a.borehole.layers && a.borehole.layers.length) {
    html += head("🧪", "Borehole log (measured)", "measured", "user-supplied", null);
    html += `<table class="soil"><tr><th>Top m</th><th>Base m</th><th>Description</th><th>USCS</th><th>SPT N</th></tr>`;
    for (const l of a.borehole.layers)
      html += `<tr><td>${esc(l.top_m)}</td><td>${esc(l.bottom_m)}</td>
        <td style="text-align:left">${esc(l.description)}</td><td>${esc(l.uscs)}</td><td>${esc(l.spt_n)}</td></tr>`;
    html += `</table>`;
    if (a.borehole.groundwater_depth_m != null)
      html += `<div class="kv"><div class="k">Groundwater depth</div><div class="v">${a.borehole.groundwater_depth_m} m</div></div>`;
  }

  html += head("🏔️", "Terrain", "measured", "NASA SRTM / OpenTopoData", "https://www.opentopodata.org/");
  html += kv([
    ["Elevation", t.elevation_m != null ? t.elevation_m + " m" : "—"],
    ["Slope / aspect", (t.slope_deg != null ? t.slope_deg + "°" : "—") + " / " + (t.aspect_deg != null ? t.aspect_deg + "°" : "—")],
    ["Terrain class", t.terrain_class],
  ]);

  html += head("🌧️", "Climate &amp; frost", "modelled", "Open-Meteo ERA5", "https://open-meteo.com/");
  html += kv([
    ["Annual rainfall", cl.annual_precip_mm != null ? cl.annual_precip_mm + " mm (" + esc(cl.wetness_class) + ")" : "—"],
    ["Mean / min temp", (cl.mean_temp_c ?? "—") + " / " + (cl.min_temp_c ?? "—") + " °C"],
    ["Frost penetration", cl.frost_depth_m != null ? cl.frost_depth_m + " m" : "—"],
  ]);

  const gm = a.ground_motion;
  if (gm && (gm.velocity_mm_yr != null || gm.egms_viewer_url)) {
    const link = gm.egms_viewer_url
      ? ` · <a class="src-link" href="${gm.egms_viewer_url}" target="_blank" rel="noopener">EGMS viewer ↗</a>` : "";
    html += head("📡", "Ground motion (InSAR)", gm.velocity_mm_yr != null ? "measured" : "estimated",
      "InSAR / EGMS", null);
    if (gm.velocity_mm_yr != null)
      html += kv([["Velocity", `${gm.velocity_mm_yr} mm/yr (${esc(gm.direction)})`]]);
    html += `<div class="meter-why">${esc(gm.note)}${link}</div>`;
  }

  const sh = a.sentinel;
  if (sh && sh.ndvi != null) {
    html += head("🛰️", "Sentinel-2 high-res (10 m)", "measured",
      "Sentinel Hub / Copernicus", "https://dataspace.copernicus.eu/");
    html += kv([
      ["NDVI (vegetation)", sh.ndvi],
      ["NDWI (surface water)", sh.ndwi != null ? sh.ndwi + (sh.ndwi > 0 ? " — open water likely" : "") : "—"],
      ["NDMI (moisture)", sh.ndmi != null ? sh.ndmi : "—"],
      ["Scene date", sh.observation_date || "—"],
    ]);
  }

  if (vg.ndvi != null) {
    const np = Math.max(0, Math.min(1, vg.ndvi)) * 100;
    const ncol = vg.ndvi < 0.1 ? "#b08968" : vg.ndvi < 0.3 ? "#c9b458"
      : vg.ndvi < 0.6 ? "#7cb342" : "#2e7d32";
    html += head("🌱", "Vegetation / NDVI", "measured", "NASA MODIS", "https://modis.ornl.gov/");
    html += `<div class="meter-row"><div class="meter-head">
      <span>NDVI ${vg.ndvi.toFixed(2)} · ${esc(vg.cover_class)}</span>
      <span class="sub" style="margin:0">${esc(vg.observation_date)}</span></div>
      <div class="meter"><div class="meter-fill" style="width:${np}%;background:${ncol}"></div></div>
      <div class="meter-why">${esc(vg.ground_description)}</div></div>`;
  }

  if (hy.nearest_water_m != null || hy.river_discharge_m3s != null) {
    html += head("💧", "Hydrology &amp; water proximity", "measured",
      "OpenStreetMap + GloFAS", "https://overpass-turbo.eu/");
    html += kv([
      ["Nearest water", hy.nearest_water_m != null
        ? `${hy.nearest_water_m} m (${esc(hy.nearest_water_type)})` : "none within 5 km"],
      ["River discharge", hy.river_discharge_m3s != null ? hy.river_discharge_m3s + " m³/s" : "—"],
      ["Ground elevation", t.elevation_m != null ? t.elevation_m + " m" : "—"],
    ]);
  }

  html += head("🌍", "Seismic context", "measured", "USGS catalogue", "https://earthquake.usgs.gov/");
  html += kv([
    ["M≥4 events (300 km)", s.event_count],
    ["Max magnitude", s.max_magnitude ? "M" + s.max_magnitude : "—"],
    ["Nearest significant", s.nearest_significant_km != null ? s.nearest_significant_km + " km" : "—"],
    ["Indicative PGA", s.estimated_pga_g != null ? s.estimated_pga_g + " g" : "—"],
  ]);

  const hv = a.hvac;
  if (hv) {
    html += head("❄️", "HVAC study", "estimated", "derived from ERA5 climate", null);
    const rows = [
      ["Climate zone", hv.climate_zone],
      ["Heating / cooling degree-days", u(hv.hdd18) + " / " + u(hv.cdd18) + " (base 18°C)"],
      ["Design temps (heat / cool)", u(hv.heating_design_temp_c, "°C") + " / " + u(hv.cooling_design_temp_c, "°C")],
    ];
    if (hv.peak_heating_kw != null) {
      rows.push(["Peak heating load", u(hv.peak_heating_kw, " kW")]);
      rows.push(["Peak cooling load", u(hv.peak_cooling_kw, " kW") + (hv.cooling_tons ? " (" + hv.cooling_tons + " tons)" : "")]);
      rows.push(["Annual heating / cooling", u(hv.annual_heating_kwh, " kWh") + " / " + u(hv.annual_cooling_kwh, " kWh")]);
    }
    html += kv(rows);
    html += `<div class="rec"><b>System.</b> ${esc(hv.recommended_system)}</div>`;
    if (hv.note) html += `<div class="meter-why">${esc(hv.note)}</div>`;
  }

  const ug = a.underground;
  if (ug) {
    html += head("🔧", "Underground networks &amp; excavation", "estimated",
      "derived from soil / groundwater / frost", null);
    html += kv([
      ["Infiltration / SuDS", u(ug.infiltration_class) + (ug.soakaway_feasibility ? " — " + ug.soakaway_feasibility : "")],
      ["Soil corrosivity", u(ug.soil_corrosivity)],
      ["Min. pipe burial depth", u(ug.min_burial_depth_m, " m")],
      ["Dewatering", u(ug.dewatering)],
      ["Trench support", u(ug.trench_support)],
      ["Stormwater", u(ug.stormwater_note)],
    ]);
    if (ug.pipe_material_guidance) html += `<div class="rec"><b>Pipe material.</b> ${esc(ug.pipe_material_guidance)}</div>`;
    if (ug.bedding_backfill) html += `<div class="rec"><b>Bedding/backfill.</b> ${esc(ug.bedding_backfill)}</div>`;
    for (const n of (ug.notes || [])) html += `<div class="meter-why">${esc(n)}</div>`;
  }

  html += `<h3>✅ Recommendations</h3>`;
  for (const r of a.recommendations)
    html += `<div class="rec"><b>${esc(r.category)}.</b> ${esc(r.text)}</div>`;

  const res = $("results");
  res.innerHTML = html;
  res.hidden = false;
  lastAssessment = a;
  if ($("saveBtn")) $("saveBtn").disabled = false;
}

// ---- Save & compare multiple sites (localStorage) ------------------------
const SAVE_KEY = "geotech_sites_v1";
let lastAssessment = null;
const savedGroup = L.layerGroup().addTo(map);

function loadSaved() {
  try { return JSON.parse(localStorage.getItem(SAVE_KEY) || "[]"); }
  catch (e) { return []; }
}
function storeSaved(arr) {
  try { localStorage.setItem(SAVE_KEY, JSON.stringify(arr)); } catch (e) {}
}
const suitColor = (s) => s == null ? "#789" : s >= 75 ? "#2e7d32"
  : s >= 55 ? "#f9a825" : s >= 35 ? "#ef6c00" : "#c62828";

function saveCurrent() {
  if (!lastAssessment) return;
  const a = lastAssessment;
  const arr = loadSaved();
  const name = (a.project_name && a.project_name !== "Untitled Site")
    ? a.project_name : `${a.location.lat.toFixed(3)}, ${a.location.lon.toFixed(3)}`;
  arr.push({
    id: "s" + Date.now(), name,
    lat: a.location.lat, lon: a.location.lon,
    saved: new Date().toISOString().slice(0, 16).replace("T", " "),
    a,
  });
  storeSaved(arr);
  renderSaved();
}

function removeSaved(id) {
  storeSaved(loadSaved().filter((s) => s.id !== id));
  renderSaved();
  $("compareWrap").hidden = true;
}

function recenterSaved(s) {
  setSite(s.lat, s.lon, true);
  if (s.a.project_name) $("projectName").value = s.a.project_name;
}

function renderSaved() {
  const arr = loadSaved();
  $("savedCard").hidden = arr.length === 0;
  $("savedCount").textContent = arr.length;
  savedGroup.clearLayers();
  const rows = arr.map((s) => {
    const sc = s.a.suitability ? s.a.suitability.score : null;
    L.circleMarker([s.lat, s.lon], { radius: 6, color: "#fff", weight: 1,
      fillColor: suitColor(sc), fillOpacity: 0.95 })
      .bindTooltip(`${s.name}${sc != null ? " · " + sc + "/100" : ""}`).addTo(savedGroup);
    return `<label class="saved-row">
      <input type="checkbox" class="saved-chk" value="${s.id}" />
      <span class="saved-dot" style="background:${suitColor(sc)}"></span>
      <span class="saved-name" data-id="${s.id}">${esc(s.name)}</span>
      <span class="saved-score">${sc != null ? sc : "—"}</span>
      <button class="saved-del" data-id="${s.id}" title="Remove">✕</button>
    </label>`;
  }).join("");
  $("savedList").innerHTML = rows;
  $("savedList").querySelectorAll(".saved-name").forEach((el) =>
    el.onclick = () => recenterSaved(loadSaved().find((s) => s.id === el.dataset.id)));
  $("savedList").querySelectorAll(".saved-del").forEach((el) =>
    el.onclick = () => removeSaved(el.dataset.id));
}

function selectedSites() {
  const ids = [...document.querySelectorAll(".saved-chk:checked")].map((c) => c.value);
  const arr = loadSaved();
  return arr.filter((s) => ids.includes(s.id));
}

function hz(a, name) {
  const h = (a.hazards || []).find((x) => x.name === name);
  return h ? h.level : "—";
}

function compareSites() {
  let sites = selectedSites();
  if (sites.length < 1) sites = loadSaved();          // default: compare all
  if (sites.length < 2) {
    $("compareWrap").innerHTML = `<div class="warn">Select at least two saved sites (tick the boxes) to compare.</div>`;
    $("compareWrap").hidden = false;
    return;
  }
  const hazNames = [...new Set(sites.flatMap((s) => (s.a.hazards || []).map((h) => h.name)))];
  const num = (s, f) => { const p = s.a.parameters || {}; return p[f] != null ? p[f] : "—"; };
  const rowDefs = [
    ["Suitability", (s) => s.a.suitability ? `${s.a.suitability.score}/100 ${s.a.suitability.rating}` : "—"],
    ["Net allowable bearing (kPa)", (s) => num(s, "allowable_bearing_kpa")],
    ["Settlement (mm)", (s) => num(s, "settlement_mm")],
    ["Min founding depth (m)", (s) => num(s, "min_founding_depth_m")],
    ["Seismic site class", (s) => num(s, "seismic_site_class")],
    ["Basis", (s) => (s.a.parameters && s.a.parameters.data_basis === "borehole") ? "Measured" : "Model"],
    ["Recommended foundation", (s) => num(s, "recommended_foundation")],
  ];
  let h = `<h3>⚖️ Site comparison (${sites.length})</h3><div class="cmp-scroll"><table class="cmp">`;
  h += `<tr><th>Metric</th>${sites.map((s) => `<th>${esc(s.name)}</th>`).join("")}</tr>`;
  for (const [label, fn] of rowDefs)
    h += `<tr><td class="cmp-m">${label}</td>${sites.map((s) => `<td>${esc(fn(s))}</td>`).join("")}</tr>`;
  for (const name of hazNames)
    h += `<tr><td class="cmp-m">${esc(name)}</td>${sites.map((s) =>
      `<td><span class="${cls(hz(s.a, name))}">${esc(hz(s.a, name))}</span></td>`).join("")}</tr>`;
  h += `</table></div>`;
  // Highlight the most suitable site.
  const best = sites.reduce((b, s) => (s.a.suitability && (!b.a.suitability || s.a.suitability.score > b.a.suitability.score)) ? s : b, sites[0]);
  if (best.a.suitability)
    h += `<div class="bh-note">🏆 Highest suitability: <b>${esc(best.name)}</b> (${best.a.suitability.score}/100, ${esc(best.a.suitability.rating)}).</div>`;
  $("compareWrap").innerHTML = h;
  $("compareWrap").hidden = false;
}

function exportCsv() {
  const arr = loadSaved();
  if (!arr.length) return;
  const cols = ["name", "lat", "lon", "suitability", "rating", "bearing_kpa",
    "settlement_mm", "min_depth_m", "basis"];
  const lines = [cols.join(",")];
  for (const s of arr) {
    const p = s.a.parameters || {}, su = s.a.suitability || {};
    const row = [s.name, s.lat, s.lon, su.score ?? "", su.rating ?? "",
      p.allowable_bearing_kpa ?? "", p.settlement_mm ?? "", p.min_founding_depth_m ?? "",
      p.data_basis === "borehole" ? "measured" : "model"];
    lines.push(row.map((v) => `"${String(v).replace(/"/g, '""')}"`).join(","));
  }
  const blob = new Blob([lines.join("\n")], { type: "text/csv" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url; link.download = "geotech_sites.csv"; link.click();
  URL.revokeObjectURL(url);
}

function exportJson() {
  if (!lastAssessment) return;
  const blob = new Blob([JSON.stringify(lastAssessment, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  const nm = (lastAssessment.project_name || "site").replace(/[^a-z0-9]+/gi, "_").slice(0, 40);
  link.href = url; link.download = `geotech_${nm}.json`; link.click();
  URL.revokeObjectURL(url);
}

async function comparePdf() {
  let sites = selectedSites();
  if (sites.length < 2) sites = loadSaved();
  if (sites.length < 2) { alert("Save at least two sites to produce a comparison PDF."); return; }
  const btn = $("comparePdfBtn");
  btn.textContent = "Building…"; btn.disabled = true;
  try {
    const r = await fetch("/api/compare.pdf", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ sites: sites.map((s) => s.a) }),
    });
    if (!r.ok) throw new Error((await r.json()).detail || r.statusText);
    const blob = await r.blob();
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url; link.download = "geotech_comparison.pdf"; link.click();
    URL.revokeObjectURL(url);
  } catch (e) { alert("Comparison PDF failed: " + e.message); }
  btn.textContent = "⬇ Comparison PDF"; btn.disabled = false;
}

$("saveBtn").onclick = saveCurrent;
$("jsonBtn").onclick = exportJson;
$("compareBtn").onclick = compareSites;
$("comparePdfBtn").onclick = comparePdf;
$("exportCsvBtn").onclick = exportCsv;
$("clearSaved").onclick = () => { if (confirm("Remove all saved sites?")) { storeSaved([]); renderSaved(); $("compareWrap").hidden = true; } };
renderSaved();
