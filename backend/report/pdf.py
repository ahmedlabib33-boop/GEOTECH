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
        ("Typical SPT N", p.typical_spt_n or "-"),
        ("Ultimate bearing q_ult", f"{p.ultimate_bearing_kpa} kPa"),
        ("Net allowable bearing", f"{p.allowable_bearing_kpa} kPa (FS 3.0)"),
        ("Settlement sensitivity", p.settlement_sensitivity or "-"),
    ], ss, [48 * mm, 130 * mm]))

    # Hazards
    story.append(Paragraph("4. Geohazard Screening", ss["H2"]))
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
    story.append(Paragraph("5. Seismic Context", ss["H2"]))
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
    story.append(Paragraph("6. Preliminary Recommendations", ss["H2"]))
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
