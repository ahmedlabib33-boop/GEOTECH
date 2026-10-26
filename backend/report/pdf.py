"""Render an Assessment to a professional-looking PDF using ReportLab."""
from __future__ import annotations

import io

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (Paragraph, SimpleDocTemplate, Spacer, Table,
                                TableStyle, HRFlowable)

from ..schemas import Assessment

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


def build_pdf(a: Assessment) -> bytes:
    ss = _styles()
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=18 * mm, bottomMargin=16 * mm,
                            leftMargin=16 * mm, rightMargin=16 * mm,
                            title=f"Geotechnical Desk Study - {a.project_name}")
    story = []

    story.append(Paragraph("Preliminary Geotechnical Desk Study", ss["TitleBig"]))
    story.append(Paragraph("Satellite &amp; open-data site assessment", ss["Sub"]))
    story.append(HRFlowable(width="100%", thickness=1.4, color=ACCENT, spaceAfter=8))

    mode = "LIVE remote-sensing data" if a.data_mode == "live" else "DEMO / sample data"
    story.append(_kv_table([
        ("Project", a.project_name),
        ("Location", a.location.display_name or f"{a.location.lat}, {a.location.lon}"),
        ("Coordinates", f"{a.location.lat:.5f}, {a.location.lon:.5f}"),
        ("Country", a.location.country or "-"),
        ("Generated", a.generated_utc),
        ("Data mode", mode),
    ], ss, [40 * mm, 138 * mm]))

    if a.warnings:
        story.append(Spacer(1, 6))
        story.append(Paragraph("<b>Data notes:</b> " + " ".join(a.warnings), ss["Disc"]))

    # Suitability banner
    if a.suitability:
        su = a.suitability
        col = {"Favourable": _LEVEL_COLORS["Low"], "Marginal": _LEVEL_COLORS["Moderate"],
               "Challenging": _LEVEL_COLORS["High"], "Severe": _LEVEL_COLORS["Very High"]}.get(
            su.rating, colors.grey)
        story.append(Spacer(1, 8))
        banner = Table([[
            Paragraph(f'<font color="white" size="20"><b>{su.score:.0f}</b></font>'
                      f'<font color="white" size="9">/100</font>', ss["Cell"]),
            Paragraph(f'<font color="white"><b>Site Suitability: {su.rating}</b><br/>'
                      f'{su.summary}</font>', ss["Cell"]),
        ]], colWidths=[28 * mm, 150 * mm])
        banner.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), col),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (-1, -1), 8), ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ("TOPPADDING", (0, 0), (-1, -1), 7), ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
        ]))
        story.append(banner)
        if su.drivers:
            story.append(Spacer(1, 3))
            story.append(Paragraph("Key drivers: " + "; ".join(su.drivers), ss["Disc"]))

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
    story.append(Paragraph(f"Dominant texture: <b>{a.soil.dominant_usda_texture or 'n/a'}</b> "
                           f"(approx. USCS {a.soil.dominant_uscs_group or 'n/a'}). "
                           f"Source: {a.soil.source}.", ss["Disc"]))

    # Parameters
    p = a.parameters
    story.append(Paragraph("3. Preliminary Geotechnical Parameters", ss["H2"]))
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

    # Bearing vs footing width
    if p.bearing_curve:
        pairs = ", ".join(f"B={bp.width_m} m → {bp.allowable_kpa:.0f} kPa"
                          for bp in p.bearing_curve)
        story.append(Spacer(1, 2))
        story.append(Paragraph(f"<b>Allowable bearing vs footing width:</b> {pairs}.", ss["Disc"]))

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
        story.append(_kv_table([
            ("NDVI", f"{vg.ndvi}"),
            ("Observation date", vg.observation_date or "-"),
            ("Cover class", vg.cover_class or "-"),
            ("Ground condition", vg.ground_description or "-"),
            ("Source", vg.source or "-"),
        ], ss, [48 * mm, 130 * mm]))

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


def _footer(canvas, doc):
    canvas.saveState()
    canvas.setFont("Helvetica", 7.5)
    canvas.setFillColor(colors.grey)
    canvas.drawString(16 * mm, 9 * mm, "GeoTech Satellite - automated preliminary desk study")
    canvas.drawRightString(A4[0] - 16 * mm, 9 * mm, f"Page {doc.page}")
    canvas.restoreState()
