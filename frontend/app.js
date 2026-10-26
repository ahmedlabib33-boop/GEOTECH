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

L.control.layers(
  { "Satellite": satellite, "Street map": streets, "Topographic": topo },
  { "Place labels": labels },
  { position: "topright", collapsed: true }
).addTo(map);
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

// ---- Run assessment ------------------------------------------------------
function payload() {
  const lat = parseFloat($("lat").value), lon = parseFloat($("lon").value);
  if (Number.isNaN(lat) || Number.isNaN(lon)) return null;
  return {
    lat, lon,
    project_name: $("projectName").value || null,
    foundation_width_m: parseFloat($("fw").value) || 2.0,
    foundation_depth_m: parseFloat($("fd").value) || 1.5,
  };
}

$("runBtn").onclick = async () => {
  const body = payload();
  if (!body) { setErr("Pick a location first (click the map or search)."); return; }
  const demo = $("demo").checked;
  $("runBtn").disabled = true;
  $("status").className = "status";
  $("status").textContent = "Fetching satellite & geospatial data…";
  try {
    const r = await fetch(`/api/assess?demo=${demo}`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!r.ok) throw new Error((await r.json()).detail || r.statusText);
    const a = await r.json();
    render(a);
    $("status").textContent = "";
    lastPayload = { body, demo };
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
    const r = await fetch(`/api/report.pdf?demo=${lastPayload.demo}`, {
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
const esc = (s) => String(s ?? "—").replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c]));
const cls = (lvl) => "badge " + String(lvl || "").replace(/\s+/g, "");

function kv(pairs) {
  return `<div class="kv">` + pairs.map(([k, v]) =>
    `<div class="k">${esc(k)}</div><div class="v">${esc(v)}</div>`).join("") + `</div>`;
}

function render(a) {
  const badge = $("modeBadge");
  badge.textContent = a.data_mode === "live" ? "LIVE DATA" : "DEMO DATA";
  badge.className = "mode-badge " + a.data_mode;

  const t = a.terrain, p = a.parameters, s = a.seismic;
  let html = "";

  if (a.warnings && a.warnings.length)
    html += `<div class="warn">⚠ ${a.warnings.map(esc).join(" ")}</div>`;

  html += `<h3>📍 ${esc(a.location.display_name || a.project_name)}</h3>`;
  html += kv([
    ["Coordinates", `${a.location.lat.toFixed(5)}, ${a.location.lon.toFixed(5)}`],
    ["Country", a.location.country],
    ["Generated", a.generated_utc],
  ]);

  html += `<h3>🏔️ Terrain</h3>`;
  html += kv([
    ["Elevation", t.elevation_m != null ? t.elevation_m + " m" : "—"],
    ["Slope", t.slope_deg != null ? t.slope_deg + "°" : "—"],
    ["Aspect", t.aspect_deg != null ? t.aspect_deg + "°" : "—"],
    ["Terrain class", t.terrain_class],
  ]);

  html += `<h3>🪨 Soil profile</h3><table class="soil"><tr>
    <th>Depth</th><th>Clay%</th><th>Sand%</th><th>Silt%</th><th>USDA</th><th>USCS</th></tr>`;
  for (const l of a.soil.layers) {
    html += `<tr><td>${esc(l.depth_label)}</td><td>${esc(l.clay_pct)}</td>
      <td>${esc(l.sand_pct)}</td><td>${esc(l.silt_pct)}</td>
      <td>${esc(l.usda_texture)}</td><td>${esc(l.uscs_group)}</td></tr>`;
  }
  html += `</table><div class="kv"><div class="k">Dominant</div>
    <div class="v">${esc(a.soil.dominant_usda_texture)} (${esc(a.soil.dominant_uscs_group)})</div></div>`;

  html += `<h3>🏗️ Preliminary parameters</h3>`;
  html += kv([
    ["Description", p.soil_description],
    ["Friction angle φ'", p.friction_angle_deg + "°"],
    ["Cohesion c", p.cohesion_kpa + " kPa"],
    ["Unit weight γ", p.unit_weight_kn_m3 + " kN/m³"],
    ["Typical SPT N", p.typical_spt_n],
    ["Net allowable bearing", p.allowable_bearing_kpa + " kPa (FS 3)"],
    ["Ultimate bearing", p.ultimate_bearing_kpa + " kPa"],
    ["Settlement sensitivity", p.settlement_sensitivity],
  ]);

  html += `<h3>⚠️ Geohazard screening</h3>`;
  for (const h of a.hazards) {
    html += `<div class="hazard"><span class="${cls(h.level)}">${esc(h.level)}</span>
      <span><b>${esc(h.name)}</b><br><span class="hz-text">${esc(h.rationale)}</span></span></div>`;
  }

  html += `<h3>🌍 Seismic context</h3>`;
  html += kv([
    ["M≥4 events (300 km)", s.event_count],
    ["Max magnitude", s.max_magnitude ? "M" + s.max_magnitude : "—"],
    ["Nearest significant", s.nearest_significant_km != null ? s.nearest_significant_km + " km" : "—"],
    ["Hazard level", s.hazard_level],
    ["Indicative PGA", s.estimated_pga_g != null ? s.estimated_pga_g + " g" : "—"],
  ]);

  html += `<h3>✅ Recommendations</h3>`;
  for (const r of a.recommendations)
    html += `<div class="rec"><b>${esc(r.category)}.</b> ${esc(r.text)}</div>`;

  const res = $("results");
  res.innerHTML = html;
  res.hidden = false;
}
