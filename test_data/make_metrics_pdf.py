"""Generate a single test PDF containing a clearly-labelled metrics table.

Purpose: attach this PDF on the Generate page and verify whether the SLM-generated
proposal reproduces / reflects the table the user supplied. The figures are
deliberately distinctive (odd, memorable values) so they are easy to grep for in
the generated report.

Run:  backend\.venv\Scripts\python.exe test_data\make_metrics_pdf.py
"""

from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

OUT = Path(__file__).with_name("metrics_table_test.pdf")

styles = getSampleStyleSheet()

intro = (
    "Northwind Logistics PLC — FY2025 Key Performance Metrics. "
    "The figures below are supplied by the client for inclusion in the proposal. "
    "Please incorporate this Key Performance Metrics table in the generated report."
)

# Distinctive values so they're easy to verify in the generated output.
data = [
    ["Metric", "Q1", "Q2", "Q3", "Q4", "FY2025"],
    ["Revenue (GBP m)", "42.3", "47.8", "51.2", "58.6", "199.9"],
    ["Gross Margin (%)", "31.4", "32.1", "33.8", "35.0", "33.1"],
    ["EBITDA (GBP m)", "8.1", "9.4", "10.7", "12.9", "41.1"],
    ["Active Customers", "1,240", "1,389", "1,512", "1,704", "1,704"],
    ["Net Promoter Score", "48", "51", "55", "61", "54"],
    ["Headcount", "318", "342", "366", "401", "401"],
]

table = Table(data, hAlign="LEFT", colWidths=[55 * mm] + [22 * mm] * 5)
table.setStyle(
    TableStyle(
        [
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#7e2d2a")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#9c9482")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f4f2ea")]),
            ("ALIGN", (1, 0), (-1, -1), "CENTER"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]
    )
)

doc = SimpleDocTemplate(str(OUT), pagesize=A4, title="Northwind Logistics FY2025 Metrics")
story = [
    Paragraph("Northwind Logistics PLC", styles["Title"]),
    Paragraph("FY2025 Key Performance Metrics", styles["Heading2"]),
    Spacer(1, 6),
    Paragraph(intro, styles["BodyText"]),
    Spacer(1, 12),
    table,
    Spacer(1, 12),
    Paragraph(
        "Source: Client-supplied management accounts (illustrative test fixture).",
        styles["Italic"],
    ),
]
doc.build(story)
print(f"WROTE {OUT}  ({OUT.stat().st_size} bytes)")
