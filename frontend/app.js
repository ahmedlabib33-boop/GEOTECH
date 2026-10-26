/* GeoTech Satellite — front-end logic (Leaflet map + assessment UI). */
"use strict";

// ---- Map with live satellite imagery + zoom ------------------------------
const map = L.map("map", { center: [20, 10], zoom: 3, worldCopyJump: true });

const satellite = L.tileLayer(
  "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
  { maxZoom: 19, attribution: "Imagery © Esri, Maxar, Earthstar Geographics" }
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
  $("coordReadout").textContent = `Site: ${lat}, ${lon}`;
  if (marker) marker.setLatLng([lat, lon]);
  else marker = L.marker([lat, lon], { draggable: true }).addTo(map)
          .on("dragend", (e) => { const p = e.target.getLatLng(); setSite(p.lat, p.lng, false); });
  if (fly) map.flyTo([lat, lon], Math.max(map.getZoom(), 14), { duration: 0.8 });
}

map.on("click", (e) => setSite(e.latlng.lat, e.latlng.lng, false));

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
  const bh = readBorehole();
  if (bh) body.borehole = bh;
  return body;
}

$("runBtn").onclick = async () => {
  const body = payload();
  if (!body) { setErr("Pick a location first (click the map or search)."); return; }
  const demo = $("demo").checked, ai = $("ai").checked;
  $("runBtn").disabled = true;
  $("status").className = "status";
  $("status").textContent = ai ? "Fetching data & writing AI commentary…"
    : "Fetching satellite & geospatial data…";
  try {
    const r = await fetch(`/api/assess?demo=${demo}&ai=${ai}`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!r.ok) throw new Error((await r.json()).detail || r.statusText);
    const a = await r.json();
    render(a);
    $("status").textContent = "";
    lastPayload = { body, demo, ai };
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
    const r = await fetch(`/api/report.pdf?demo=${lastPayload.demo}&ai=${lastPayload.ai}`, {
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
    const p = sev(h.level);
    return `<div class="meter-row">
      <div class="meter-head"><span>${esc(h.name)}</span>
        <span class="${cls(h.level)}">${esc(h.level)}</span></div>
      <div class="meter"><div class="meter-fill" style="width:${p}%;background:${sevColor(p)}"></div></div>
      <div class="meter-why">${esc(h.rationale)}</div></div>`;
  }).join("");
}

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
let DEMO_MODE = false;
function head(emoji, title, kind, name, url) {
  if (DEMO_MODE) { kind = "sample"; name = "demo sample"; url = null; }
  const label = { measured: "Measured", modelled: "Modelled", estimated: "Estimated",
    sample: "Sample" }[kind] || kind;
  const src = url
    ? `<a class="src-link" href="${url}" target="_blank" rel="noopener">${esc(name)} ↗</a>`
    : `<span class="src-link">${esc(name)}</span>`;
  return `<div class="sec-head"><h3>${emoji} ${title}</h3>
    <span class="src-badge ${kind}" title="${label} data">${label}</span>${src}</div>`;
}

function render(a) {
  const badge = $("modeBadge");
  DEMO_MODE = a.data_mode === "demo";
  badge.textContent = a.data_mode === "live" ? "LIVE DATA" : "DEMO DATA";
  badge.className = "mode-badge " + a.data_mode;

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
    ["Source", a.soil.source && a.soil.source.includes("DEMO") ? "sample" : "SoilGrids"],
  ]) + `</div></div>`;

  const measured = p.data_basis === "borehole";
  html += head("🏗️", "Foundation &amp; parameters",
    measured ? "measured" : "estimated",
    measured ? "your borehole data (SPT/Meyerhof)" : "derived (Terzaghi/Vesic + ref. values)",
    null);
  if (measured)
    html += `<div class="bh-note">✔ Computed from your measured borehole log, overriding the satellite soil estimate.</div>`;
  html += kv([
    ["Recommended", p.recommended_foundation],
    ["Net allowable bearing", p.allowable_bearing_kpa + " kPa (FS 3)"],
    ["Ultimate bearing", p.ultimate_bearing_kpa + " kPa"],
    ["Est. settlement", p.settlement_mm + " mm"],
    ["Min. founding depth", p.min_founding_depth_m + " m"],
    ["Friction φ' / cohesion c", p.friction_angle_deg + "° / " + p.cohesion_kpa + " kPa"],
    ["Unit weight / Es", p.unit_weight_kn_m3 + " kN/m³ / " + p.elastic_modulus_mpa + " MPa"],
    ["Typical SPT N", p.typical_spt_n],
    ["Seismic site class", p.seismic_site_class + " (Vs30~" + p.vs30_proxy_mps + ")"],
  ]);
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

  html += `<h3>✅ Recommendations</h3>`;
  for (const r of a.recommendations)
    html += `<div class="rec"><b>${esc(r.category)}.</b> ${esc(r.text)}</div>`;

  const res = $("results");
  res.innerHTML = html;
  res.hidden = false;
}
