"""Render an Assessment to a professional-looking PDF using ReportLab."""
from __future__ import annotations

import io

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (Image as RLImage, PageBreak, Paragraph,
                                SimpleDocTemplate, Spacer, Table, TableStyle,
                                HRFlowable)
from reportlab.graphics.shapes import Circle, Drawing, Line, PolyLine, Rect, String
import io as _io

from ..schemas import Assessment

_RATING_COLORS = {"Favourable": "#2e7d32", "Marginal": "#f9a825",
                  "Challenging": "#ef6c00", "Severe": "#c62828"}


def hazard_chart(hazards) -> Drawing:
    """Horizontal bar chart of hazard scores (0-1)."""
    n = len(hazards)
    row, pad = 16, 6
    w, h = 470, n * row + pad
    d = Drawing(w, h)
    bx, bw = 150, 250
    for i, hz in enumerate(hazards):
        y = h - (i + 1) * row
        d.add(String(0, y + 4, (hz.name[:30]), fontSize=8, fillColor=NAVY))
        d.add(Rect(bx, y + 2, bw, 9, fillColor=LIGHT, strokeColor=None))
        col = _LEVEL_COLORS.get(hz.level, colors.grey)
        d.add(Rect(bx, y + 2, max(bw * float(hz.score), 1), 9, fillColor=col, strokeColor=None))
        d.add(String(bx + bw + 6, y + 4, hz.level, fontSize=7.5, fillColor=colors.grey))
    return d


def bearing_chart(points) -> Drawing:
    """Line plot of allowable bearing vs footing width."""
    W, H, padL, padB = 330, 150, 42, 26
    d = Drawing(W, H)
    xs = [p.width_m for p in points]
    ys = [p.allowable_kpa for p in points]
    xmax, ymax = max(xs), max(max(ys), 10)
    def px(x): return padL + x / xmax * (W - padL - 10)
    def py(y): return padB + y / ymax * (H - padB - 14)
    d.add(Line(padL, padB, W - 10, padB, strokeColor=colors.HexColor("#99a7b3")))
    d.add(Line(padL, padB, padL, H - 10, strokeColor=colors.HexColor("#99a7b3")))
    pts = []
    for p in points:
        pts += [px(p.width_m), py(p.allowable_kpa)]
    d.add(PolyLine(pts, strokeColor=ACCENT, strokeWidth=2))
    for p in points:
        d.add(Circle(px(p.width_m), py(p.allowable_kpa), 2.5, fillColor=ACCENT, strokeColor=None))
    d.add(String(padL, H - 9, f"{ymax:.0f} kPa", fontSize=7, fillColor=colors.grey))
    d.add(String(W / 2 - 30, 4, "footing width B (m)", fontSize=8, fillColor=colors.grey))
    for x in xs:
        d.add(String(px(x) - 4, padB - 10, f"{x:g}", fontSize=6.5, fillColor=colors.grey))
    return d


def spectrum_chart(points) -> Drawing:
    """Line plot of the elastic response spectrum Sa(T) in g."""
    W, H, padL, padB = 330, 150, 44, 26
    d = Drawing(W, H)
    xs = [p.period_s for p in points]
    ys = [p.sa_g for p in points]
    xmax = max(xs) or 4.0
    ymax = max(max(ys), 0.01)
    def px(x): return padL + x / xmax * (W - padL - 10)
    def py(y): return padB + y / ymax * (H - padB - 14)
    d.add(Line(padL, padB, W - 10, padB, strokeColor=colors.HexColor("#99a7b3")))
    d.add(Line(padL, padB, padL, H - 10, strokeColor=colors.HexColor("#99a7b3")))
    pts = []
    for p in points:
        pts += [px(p.period_s), py(p.sa_g)]
    d.add(PolyLine(pts, strokeColor=ACCENT, strokeWidth=2))
    d.add(String(padL - 2, H - 9, f"{ymax:.2f} g", fontSize=7, fillColor=colors.grey))
    d.add(String(W / 2 - 24, 4, "period T (s)", fontSize=8, fillColor=colors.grey))
    for x in (0, 1, 2, 3, 4):
        if x <= xmax:
            d.add(String(px(x) - 3, padB - 10, f"{x:g}", fontSize=6.5, fillColor=colors.grey))
    return d

NAVY = colors.HexColor("#1e3a5f")
ACCENT = colors.HexColor("#2a7f62")
LIGHT = colors.HexColor("#eef2f6")
_LEVEL_COLORS = {
    "Low": colors.HexColor("#2e7d32"),
    "Low to Moderate": colors.HexColor("#689f38"),
    "Moderate": colors.HexColor("#f9a825"),
    "Moderate to high": colors.HexColor("#f9a825"),
    "High": colors.HexColor("#ef6c00"),
    "Very High": colors.HexColor("#c62828"),
}


def _styles():
    ss = getSampleStyleSheet()
    ss.add(ParagraphStyle("TitleBig", parent=ss["Title"], textColor=NAVY, fontSize=22, spaceAfter=2))
    ss.add(ParagraphStyle("Sub", parent=ss["Normal"], textColor=colors.grey, fontSize=10, spaceAfter=10))
    ss.add(ParagraphStyle("H2", parent=ss["Heading2"], textColor=NAVY, fontSize=13, spaceBefore=12, spaceAfter=4))
    ss.add(ParagraphStyle("Body", parent=ss["Normal"], fontSize=9.5, leading=13))
    ss.add(ParagraphStyle("Cell", parent=ss["Normal"], fontSize=8.5, leading=11))
    ss.add(ParagraphStyle("CellB", parent=ss["Normal"], fontSize=8.5, leading=11, textColor=colors.white))
    ss.add(ParagraphStyle("Disc", parent=ss["Normal"], fontSize=8, leading=11, textColor=colors.HexColor("#555")))
    return ss


def _kv_table(rows, ss, col_widths):
    data = [[Paragraph(f"<b>{k}</b>", ss["Cell"]), Paragraph(str(v), ss["Cell"])] for k, v in rows]
    t = Table(data, colWidths=col_widths)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), LIGHT),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#c9d4de")),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    return t


def build_pdf(a: Assessment, site_image: bytes | None = None) -> bytes:
    ss = _styles()
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=18 * mm, bottomMargin=16 * mm,
                            leftMargin=16 * mm, rightMargin=16 * mm,
                            title=f"Geotechnical Desk Study - {a.project_name}")
    story = []

    # ---------------- COVER PAGE ----------------
    story.append(Paragraph("Preliminary Geotechnical Desk Study", ss["TitleBig"]))
    story.append(Paragraph("Satellite &amp; open-data site assessment", ss["Sub"]))
    story.append(HRFlowable(width="100%", thickness=1.4, color=ACCENT, spaceAfter=8))

    if site_image:
        try:
            img = RLImage(_io.BytesIO(site_image), width=120 * mm, height=120 * mm)
            img.hAlign = "CENTER"
            story.append(img)
            story.append(Paragraph(
                f"Satellite view centred on {a.location.lat:.5f}, {a.location.lon:.5f} "
                "(Esri World Imagery). Crosshair marks the assessed point.", ss["Disc"]))
            story.append(Spacer(1, 6))
        except Exception:
            pass

    if a.suitability:
        su = a.suitability
        col = colors.HexColor(_RATING_COLORS.get(su.rating, "#789"))
        banner = Table([[
            Paragraph(f'<font color="white" size="24"><b>{su.score:.0f}</b></font>'
                      f'<font color="white" size="9">/100</font>', ss["Cell"]),
            Paragraph(f'<font color="white" size="12"><b>Site Suitability: {su.rating}</b></font>'
                      f'<br/><font color="white">{su.summary}</font>', ss["Cell"]),
        ]], colWidths=[30 * mm, 148 * mm])
        banner.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), col),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (-1, -1), 10), ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ("TOPPADDING", (0, 0), (-1, -1), 9), ("BOTTOMPADDING", (0, 0), (-1, -1), 9),
        ]))
        story.append(banner)
        story.append(Spacer(1, 8))

    mode = "LIVE remote-sensing data" if a.data_mode == "live" else "DEMO / sample data"
    story.append(_kv_table([
        ("Project", a.project_name),
        ("Location", a.location.display_name or f"{a.location.lat}, {a.location.lon}"),
        ("Coordinates", f"{a.location.lat:.5f}, {a.location.lon:.5f}"),
        ("Country", a.location.country or "-"),
        ("Preliminary foundation", a.parameters.recommended_foundation or "-"),
        ("Net allowable bearing",
         "Not available (no real soil data)" if a.parameters.allowable_bearing_kpa is None
         else f"{a.parameters.allowable_bearing_kpa} kPa "
              f"({'measured' if a.parameters.data_basis == 'borehole' else 'model'})"),
        ("Generated", a.generated_utc),
        ("Data mode", mode),
    ], ss, [44 * mm, 134 * mm]))

    if a.suitability:
        top_hz = sorted(a.hazards, key=lambda h: -h.score)[:2]
        hz_txt = ", ".join(f"{h.name.split(' /')[0].split(' (')[0]} ({h.level})" for h in top_hz)
        story.append(Spacer(1, 8))
        story.append(Paragraph("Executive Summary", ss["H2"]))
        story.append(Paragraph(
            f"{a.suitability.summary} Leading constraints: {hz_txt}. "
            "This is an automated preliminary desk study from remote-sensing data; "
            "confirm all parameters by an intrusive ground investigation before design.",
            ss["Body"]))

    if a.warnings:
        story.append(Spacer(1, 6))
        story.append(Paragraph("<b>Data notes:</b> " + " ".join(a.warnings), ss["Disc"]))

    story.append(PageBreak())

    # Terrain
    story.append(Paragraph("1. Terrain &amp; Topography", ss["H2"]))
    t = a.terrain
    story.append(_kv_table([
        ("Elevation", f"{t.elevation_m} m" if t.elevation_m is not None else "-"),
        ("Slope", f"{t.slope_deg}°" if t.slope_deg is not None else "-"),
        ("Aspect", f"{t.aspect_deg}°" if t.aspect_deg is not None else "-"),
        ("Local relief", f"{t.relief_m} m" if t.relief_m is not None else "-"),
        ("Terrain class", t.terrain_class or "-"),
        ("Source", t.source or "-"),
    ], ss, [40 * mm, 138 * mm]))

    # Soil profile table
    story.append(Paragraph("2. Soil Profile (modelled)", ss["H2"]))
    header = ["Depth", "Clay %", "Sand %", "Silt %", "Bulk dens.\n(kg/m3)", "pH", "USDA texture", "USCS"]
    rows = [[Paragraph(f"<b>{h}</b>", ss["CellB"]) for h in header]]
    for l in a.soil.layers:
        rows.append([
            Paragraph(l.depth_label, ss["Cell"]),
            Paragraph(_s(l.clay_pct), ss["Cell"]),
            Paragraph(_s(l.sand_pct), ss["Cell"]),
            Paragraph(_s(l.silt_pct), ss["Cell"]),
            Paragraph(_s(l.bulk_density_kg_m3), ss["Cell"]),
            Paragraph(_s(l.ph), ss["Cell"]),
            Paragraph(l.usda_texture or "-", ss["Cell"]),
            Paragraph(l.uscs_group or "-", ss["Cell"]),
        ])
    st = Table(rows, colWidths=[20 * mm, 16 * mm, 16 * mm, 16 * mm, 22 * mm, 12 * mm, 46 * mm, 20 * mm], repeatRows=1)
    st.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT]),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#c9d4de")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    story.append(st)
    story.append(Spacer(1, 3))
    conf = f" Model confidence: <b>{a.soil.texture_confidence}</b>." if a.soil.texture_confidence else ""
    story.append(Paragraph(f"Dominant texture: <b>{a.soil.dominant_usda_texture or 'n/a'}</b> "
                           f"(approx. USCS {a.soil.dominant_uscs_group or 'n/a'})."
                           f"{conf} Source: {a.soil.source}.", ss["Disc"]))

    # Borehole log (measured) — if supplied
    if a.borehole and a.borehole.layers:
        story.append(Paragraph("Borehole Log (measured, user-supplied)", ss["H2"]))
        bhrows = [[Paragraph(f"<b>{h}</b>", ss["CellB"]) for h in
                   ("Top m", "Base m", "Description", "USCS", "SPT N")]]
        for l in a.borehole.layers:
            bhrows.append([Paragraph(_s(l.top_m), ss["Cell"]), Paragraph(_s(l.bottom_m), ss["Cell"]),
                           Paragraph(l.description or "-", ss["Cell"]),
                           Paragraph(l.uscs or "-", ss["Cell"]), Paragraph(_s(l.spt_n), ss["Cell"])])
        bt = Table(bhrows, colWidths=[20 * mm, 20 * mm, 90 * mm, 24 * mm, 24 * mm], repeatRows=1)
        bt.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), ACCENT),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT]),
            ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#c9d4de")),
            ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]))
        story.append(bt)
        if a.borehole.groundwater_depth_m is not None:
            story.append(Spacer(1, 2))
            story.append(Paragraph(
                f"Measured groundwater depth: <b>{a.borehole.groundwater_depth_m} m</b>.", ss["Disc"]))

    # Parameters
    p = a.parameters
    basis = ("<font color=\"#2e7d32\"><b>Measured — from borehole</b></font>"
             if p.data_basis == "borehole"
             else "<font color=\"#b8860b\">Estimated — from satellite soil model</font>")
    story.append(Paragraph("3. Preliminary Geotechnical Parameters", ss["H2"]))
    story.append(Paragraph(f"Basis: {basis}.", ss["Disc"]))
    story.append(_kv_table([
        ("Soil description", p.soil_description or "-"),
        ("Friction angle φ'", f"{p.friction_angle_deg}°"),
        ("Cohesion c", f"{p.cohesion_kpa} kPa"),
        ("Unit weight γ", f"{p.unit_weight_kn_m3} kN/m³"),
        ("Elastic modulus Es", f"{p.elastic_modulus_mpa} MPa"),
        ("Typical SPT N", p.typical_spt_n or "-"),
        ("Ultimate bearing q_ult", f"{p.ultimate_bearing_kpa} kPa"),
        ("Net allowable bearing", f"{p.allowable_bearing_kpa} kPa (FS 3.0)"),
        ("Est. settlement", f"{p.settlement_mm} mm — {p.settlement_sensitivity or '-'}"),
        ("Min. founding depth", f"{p.min_founding_depth_m} m"),
        ("Seismic site class", f"{p.seismic_site_class} (Vs30 proxy ~{p.vs30_proxy_mps} m/s)"),
        ("Recommended foundation", p.recommended_foundation or "-"),
    ], ss, [48 * mm, 130 * mm]))

    # Bearing vs footing width (chart)
    if p.bearing_curve:
        story.append(Spacer(1, 4))
        story.append(Paragraph("<b>Allowable bearing vs footing width</b>", ss["Disc"]))
        try:
            story.append(bearing_chart(p.bearing_curve))
        except Exception:
            pairs = ", ".join(f"B={bp.width_m} m -> {bp.allowable_kpa:.0f} kPa"
                              for bp in p.bearing_curve)
            story.append(Paragraph(pairs, ss["Disc"]))

    # Climate
    cl = a.climate
    if cl and (cl.annual_precip_mm is not None or cl.frost_depth_m is not None):
        story.append(Paragraph("4. Climate &amp; Frost", ss["H2"]))
        story.append(_kv_table([
            ("Reference year", str(cl.year or "-")),
            ("Annual rainfall", f"{cl.annual_precip_mm} mm ({cl.wetness_class or '-'})"),
            ("Mean / min temperature", f"{cl.mean_temp_c} °C / {cl.min_temp_c} °C"),
            ("Freezing index", f"{cl.freezing_degree_days} °C-days"),
            ("Est. frost penetration", f"{cl.frost_depth_m} m"),
            ("Source", cl.source or "-"),
        ], ss, [48 * mm, 130 * mm]))

    # Vegetation / NDVI
    vg = a.vegetation
    if vg and vg.ndvi is not None:
        story.append(Paragraph("5. Vegetation &amp; Surface Cover (NDVI)", ss["H2"]))
        rows = [
            ("NDVI", f"{vg.ndvi}"),
            ("Observation date", vg.observation_date or "-"),
            ("Cover class", vg.cover_class or "-"),
            ("Ground condition", vg.ground_description or "-"),
            ("Source", vg.source or "-"),
        ]
        sh = a.sentinel
        if sh and sh.ndvi is not None:
            rows.append(("Sentinel-2 10 m indices",
                         f"NDVI {sh.ndvi}, NDWI {sh.ndwi}, NDMI {sh.ndmi} "
                         f"(scene {sh.observation_date or '-'})"))
        story.append(_kv_table(rows, ss, [48 * mm, 130 * mm]))

    # Hydrology
    hy = a.hydrology
    if hy and (hy.nearest_water_m is not None or hy.river_discharge_m3s is not None):
        story.append(Paragraph("6. Hydrology &amp; Water Proximity", ss["H2"]))
        story.append(_kv_table([
            ("Nearest surface water", f"{hy.nearest_water_m} m ({hy.nearest_water_type})"
             if hy.nearest_water_m is not None else "none within 5 km"),
            ("River discharge (GloFAS)", f"{hy.river_discharge_m3s} m³/s"
             if hy.river_discharge_m3s is not None else "-"),
            ("Ground elevation", f"{a.terrain.elevation_m} m"
             if a.terrain.elevation_m is not None else "-"),
            ("Source", hy.source or "-"),
        ], ss, [48 * mm, 130 * mm]))

    # Hazards
    story.append(Paragraph("7. Geohazard Screening", ss["H2"]))
    if a.hazards:
        try:
            story.append(hazard_chart(a.hazards))
            story.append(Spacer(1, 4))
        except Exception:
            pass
    hrows = [[Paragraph("<b>Hazard</b>", ss["CellB"]),
              Paragraph("<b>Rating</b>", ss["CellB"]),
              Paragraph("<b>Basis</b>", ss["CellB"])]]
    for h in a.hazards:
        col = _LEVEL_COLORS.get(h.level, colors.grey)
        hrows.append([
            Paragraph(h.name, ss["Cell"]),
            Paragraph(f'<font color="#{col.hexval()[2:]}"><b>{h.level}</b></font>', ss["Cell"]),
            Paragraph(h.rationale, ss["Cell"]),
        ])
    ht = Table(hrows, colWidths=[46 * mm, 26 * mm, 106 * mm], repeatRows=1)
    ht.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT]),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#c9d4de")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    story.append(ht)

    # Seismic detail
    s = a.seismic
    story.append(Paragraph("8. Seismic Context", ss["H2"]))
    story.append(_kv_table([
        ("Search radius", f"{s.search_radius_km:.0f} km"),
        ("M≥4 events on record", str(s.event_count)),
        ("Max magnitude", f"M{s.max_magnitude}" if s.max_magnitude else "-"),
        ("Nearest significant", f"{s.nearest_significant_km} km" if s.nearest_significant_km else "-"),
        ("Hazard level", s.hazard_level or "-"),
        ("Indicative PGA", f"{s.estimated_pga_g} g" if s.estimated_pga_g else "-"),
        ("Source", s.source or "-"),
    ], ss, [48 * mm, 130 * mm]))

    # Recommendations
    story.append(Paragraph("9. Preliminary Recommendations", ss["H2"]))
    for r in a.recommendations:
        story.append(Paragraph(f"<b>{r.category}.</b> {r.text}", ss["Body"]))
        story.append(Spacer(1, 3))

    # Ground motion (InSAR)
    gm = a.ground_motion
    if gm and (gm.velocity_mm_yr is not None or gm.egms_viewer_url):
        story.append(Paragraph("Ground Motion (InSAR)", ss["H2"]))
        gmrows = []
        if gm.velocity_mm_yr is not None:
            gmrows.append(("Velocity", f"{gm.velocity_mm_yr:+.1f} mm/yr ({gm.direction})"))
        gmrows.append(("Assessment", gm.note or "-"))
        gmrows.append(("Source", gm.source or "-"))
        if gm.egms_viewer_url:
            gmrows.append(("EGMS viewer", gm.egms_viewer_url))
        story.append(_kv_table(gmrows, ss, [40 * mm, 138 * mm]))

    # HVAC study
    hv = a.hvac
    if hv:
        story.append(Paragraph("HVAC Study (screening)", ss["H2"]))
        rows = [
            ("Climate zone", hv.climate_zone or "-"),
            ("Degree-days (HDD/CDD, base 18C)", f"{_s(hv.hdd18)} / {_s(hv.cdd18)}"),
            ("Design temps (heat/cool)",
             f"{_s(hv.heating_design_temp_c)} C / {_s(hv.cooling_design_temp_c)} C"),
        ]
        if hv.peak_heating_kw is not None:
            rows += [
                ("Floor area / type", f"{_s(hv.floor_area_m2)} m² / {hv.building_type or '-'}"),
                ("Peak heating load", f"{_s(hv.peak_heating_kw)} kW"),
                ("Peak cooling load", f"{_s(hv.peak_cooling_kw)} kW "
                 f"({_s(hv.cooling_tons)} tons)"),
                ("Annual heating/cooling", f"{_s(hv.annual_heating_kwh)} / "
                 f"{_s(hv.annual_cooling_kwh)} kWh"),
            ]
        rows.append(("Recommended system", hv.recommended_system or "-"))
        story.append(_kv_table(rows, ss, [50 * mm, 128 * mm]))
        if hv.assumptions:
            story.append(Paragraph("Assumptions: " + " ".join(hv.assumptions), ss["Disc"]))

    # Underground networks / excavation
    ug = a.underground
    if ug:
        story.append(Paragraph("Underground Networks &amp; Excavation (screening)", ss["H2"]))
        story.append(_kv_table([
            ("Infiltration / SuDS", f"{_s(ug.infiltration_class)} "
             f"({ug.soakaway_feasibility or '-'})"),
            ("Soil corrosivity", _s(ug.soil_corrosivity)),
            ("Pipe material", ug.pipe_material_guidance or "-"),
            ("Min. burial depth", f"{_s(ug.min_burial_depth_m)} m (frost-protected cover)"),
            ("Trench support", ug.trench_support or "-"),
            ("Dewatering", ug.dewatering or "-"),
            ("Stormwater", ug.stormwater_note or "-"),
            ("Bedding / backfill", ug.bedding_backfill or "-"),
        ], ss, [40 * mm, 138 * mm]))

    # Wind & snow loads
    ws = a.wind_snow
    if ws:
        story.append(Paragraph("Wind &amp; Snow Loads (screening)", ss["H2"]))
        wsrows = []
        if ws.design_gust_ms is not None:
            wsrows += [
                (f"Design gust ({ws.return_period_years}-yr)",
                 f"{_s(ws.design_gust_ms)} m/s ({_s(ws.design_gust_kmh)} km/h)"),
                ("Basic velocity pressure", f"{_s(ws.basic_velocity_pressure_kpa)} kPa"),
                ("Indicative wall pressure", f"{_s(ws.indicative_wall_pressure_kpa)} kPa"),
                ("Dominant wind direction", ws.dominant_wind_dir or "-"),
                ("Wind exposure", ws.wind_class or "-"),
            ]
        if ws.snow_zone is not None:
            wsrows += [
                ("Snow zone", ws.snow_zone),
                (f"Ground snow load ({ws.return_period_years}-yr)", f"{_s(ws.ground_snow_load_kpa)} kPa"),
                ("Flat-roof snow load", f"{_s(ws.roof_snow_load_kpa)} kPa"),
                ("Design snow depth", f"{_s(ws.design_snow_depth_m)} m"),
            ]
        story.append(_kv_table(wsrows, ss, [50 * mm, 128 * mm]))
        if ws.assumptions:
            story.append(Paragraph("Assumptions: " + " ".join(ws.assumptions), ss["Disc"]))
        for n in (ws.notes or []):
            story.append(Paragraph(n, ss["Disc"]))

    # Seismic design (response spectrum)
    sd = a.seismic_design
    if sd:
        story.append(Paragraph("Seismic Design — Response Spectrum (screening)", ss["H2"]))
        sdrows = [
            ("Code basis", sd.code_basis),
            ("Ground type", (sd.ground_type or "-")
             + (f" (EC8 Type {sd.spectrum_type})" if sd.spectrum_type else "")),
        ]
        if sd.design_ground_accel_g is not None:
            sdrows += [
                ("Design ground accel. ag", f"{_s(sd.design_ground_accel_g)} g"),
                ("Soil factor S", _s(sd.soil_factor_s)),
                ("Plateau Sa (ag x S x 2.5)", f"{_s(sd.plateau_sa_g)} g"),
                ("Sa(0.2 s) / Sa(1.0 s)", f"{_s(sd.sa_short_g)} / {_s(sd.sa_1s_g)} g"),
                ("Corner periods TB/TC/TD", f"{_s(sd.t_b_s)} / {_s(sd.t_c_s)} / {_s(sd.t_d_s)} s"),
            ]
        story.append(_kv_table(sdrows, ss, [50 * mm, 128 * mm]))
        if sd.spectrum:
            story.append(Spacer(1, 3))
            story.append(Paragraph("<b>Elastic response spectrum</b> (horizontal, 5% damping)",
                                   ss["Disc"]))
            story.append(spectrum_chart(sd.spectrum))
        if sd.ag_basis:
            story.append(Paragraph("ag basis: " + sd.ag_basis, ss["Disc"]))
        if sd.importance_note:
            story.append(Paragraph(sd.importance_note, ss["Disc"]))
        for n in (sd.notes or []):
            story.append(Paragraph(n, ss["Disc"]))

    # Data sources & provenance
    story.append(Paragraph("Data Sources &amp; Provenance", ss["H2"]))
    prov = [
        ("Terrain / elevation", "Measured", "NASA SRTM 30 m (OpenTopoData)"),
        ("Soil properties", "Modelled", "ISRIC SoilGrids 250 m (median + 5-95%)"),
        ("Seismicity", "Measured", "USGS earthquake catalogue"),
        ("Climate / frost", "Modelled", "Open-Meteo ERA5 reanalysis (5-yr)"),
        ("Wind / snow loads", "Modelled", "Open-Meteo ERA5 extremes (Gumbel 50-yr)"),
        ("Vegetation / NDVI", "Measured", "NASA MODIS MOD13Q1 250 m"),
        ("Hydrology / flood", "Measured", "OpenStreetMap + Open-Meteo GloFAS"),
        ("Parameters / hazards", "Estimated", "Derived (Terzaghi/Vesic + references)"),
    ]
    prows = [[Paragraph("<b>Layer</b>", ss["CellB"]), Paragraph("<b>Type</b>", ss["CellB"]),
              Paragraph("<b>Source</b>", ss["CellB"])]]
    _pc = {"Measured": colors.HexColor("#2e7d32"), "Modelled": colors.HexColor("#b8860b"),
           "Estimated": colors.HexColor("#7b4b8a")}
    measured_params = a.parameters.data_basis == "borehole"
    for layer, kind, src in prov:
        if layer.startswith("Parameters") and measured_params:
            kind, src = "Measured", "User borehole log (SPT/Meyerhof)"
        col = _pc[kind]
        prows.append([
            Paragraph(layer, ss["Cell"]),
            Paragraph(f'<font color="#{col.hexval()[2:]}"><b>{kind}</b></font>', ss["Cell"]),
            Paragraph(src, ss["Cell"]),
        ])
    pt = Table(prows, colWidths=[46 * mm, 32 * mm, 100 * mm], repeatRows=1)
    pt.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT]),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#c9d4de")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    story.append(pt)
    story.append(Spacer(1, 3))
    story.append(Paragraph(
        "<b>Measured</b> = direct satellite/instrument reading. <b>Modelled</b> = global "
        "model prediction (real science, but an estimate — not a site measurement). "
        "<b>Estimated</b> = engineering calculation from the above. All values "
        "are live readings fetched at the site coordinates; any unavailable "
        "source is reported as such and never substituted.",
        ss["Disc"]))

    # AI commentary (optional)
    if a.commentary:
        story.append(Paragraph("10. Engineering Commentary (AI-assisted)", ss["H2"]))
        for para in a.commentary.split("\n"):
            if para.strip():
                story.append(Paragraph(para.strip(), ss["Body"]))
                story.append(Spacer(1, 3))
        story.append(Paragraph(
            f"Generated by {a.commentary_model or 'LLM'}; interprets the computed data "
            "only and is not a professional sign-off.", ss["Disc"]))

    # Disclaimer
    story.append(Spacer(1, 8))
    story.append(HRFlowable(width="100%", thickness=0.8, color=colors.HexColor("#c62828")))
    story.append(Spacer(1, 4))
    story.append(Paragraph("<b>Important limitations</b>", ss["Disc"]))
    story.append(Paragraph(a.disclaimer, ss["Disc"]))

    doc.build(story, onFirstPage=_footer, onLaterPages=_footer)
    return buf.getvalue()


def _s(v) -> str:
    return "-" if v is None else str(v)


def build_compare_pdf(items: list) -> bytes:
    """Build a multi-site comparison PDF. `items` is a list of (name, Assessment)."""
    from reportlab.lib.pagesizes import landscape
    ss = _styles()
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=landscape(A4), topMargin=16 * mm,
                            bottomMargin=14 * mm, leftMargin=14 * mm, rightMargin=14 * mm,
                            title="GeoTech Satellite - Site Comparison")
    story = [Paragraph("Site Comparison", ss["TitleBig"]),
             Paragraph("Preliminary geotechnical desk study - multiple sites", ss["Sub"]),
             HRFlowable(width="100%", thickness=1.2, color=ACCENT, spaceAfter=8)]

    items = items[:8]  # keep columns readable
    names = [n for n, _ in items]
    assessments = [a for _, a in items]

    def pv(a, f):
        v = getattr(a.parameters, f, None)
        return "-" if v is None else str(v)

    rows = [["Metric"] + names]
    rows.append(["Suitability"] + [f"{a.suitability.score:.0f} {a.suitability.rating}"
                                   if a.suitability else "-" for a in assessments])
    rows.append(["Coordinates"] + [f"{a.location.lat:.4f}, {a.location.lon:.4f}" for a in assessments])
    rows.append(["Net allowable bearing (kPa)"] + [pv(a, "allowable_bearing_kpa") for a in assessments])
    rows.append(["Settlement (mm)"] + [pv(a, "settlement_mm") for a in assessments])
    rows.append(["Min founding depth (m)"] + [pv(a, "min_founding_depth_m") for a in assessments])
    rows.append(["Seismic site class"] + [pv(a, "seismic_site_class") for a in assessments])
    rows.append(["Basis"] + ["Measured" if a.parameters.data_basis == "borehole" else "Model"
                             for a in assessments])
    rows.append(["Recommended foundation"] + [pv(a, "recommended_foundation") for a in assessments])

    hz_names = []
    for a in assessments:
        for h in a.hazards:
            if h.name not in hz_names:
                hz_names.append(h.name)
    for name in hz_names:
        line = [name]
        for a in assessments:
            match = next((h for h in a.hazards if h.name == name), None)
            line.append(match.level if match else "-")
        rows.append(line)

    # Wrap cells in Paragraphs for wrapping.
    data = [[Paragraph(f"<b>{c}</b>" if (i == 0 or j == 0) else c,
                       ss["CellB"] if i == 0 else ss["Cell"]) for j, c in enumerate(r)]
            for i, r in enumerate(rows)]
    first = 52 * mm
    rest = (landscape(A4)[0] - 28 * mm - first) / max(len(names), 1)
    t = Table(data, colWidths=[first] + [rest] * len(names), repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT]),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#c9d4de")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("BACKGROUND", (0, 1), (0, -1), colors.HexColor("#0b16200a")),
        ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    story.append(t)

    best = max([a for a in assessments if a.suitability],
               key=lambda a: a.suitability.score, default=None)
    if best is not None:
        bi = assessments.index(best)
        story.append(Spacer(1, 6))
        story.append(Paragraph(
            f"Highest suitability: <b>{names[bi]}</b> "
            f"({best.suitability.score:.0f}/100, {best.suitability.rating}).", ss["Body"]))
    story.append(Spacer(1, 6))
    story.append(Paragraph("Automated preliminary desk study. Confirm by intrusive ground "
                           "investigation before design.", ss["Disc"]))
    doc.build(story, onFirstPage=_footer, onLaterPages=_footer)
    return buf.getvalue()


def _footer(canvas, doc):
    canvas.saveState()
    canvas.setFont("Helvetica", 7.5)
    canvas.setFillColor(colors.grey)
    canvas.drawString(16 * mm, 9 * mm, "GeoTech Satellite - automated preliminary desk study")
    canvas.drawRightString(A4[0] - 16 * mm, 9 * mm, f"Page {doc.page}")
    canvas.restoreState()
