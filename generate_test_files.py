"""
Generates realistic test files for the Sapiex agent stress test.
Intentional discrepancies are baked in to test the agent's analytical ability.

Discrepancies to catch:
  1. PDF claims total revenue $5.2B — Excel monthly sum is $4.8B
  2. PDF says Asia-Pacific is 15% of revenue — Excel says 18%

Usage:
    pip install reportlab openpyxl
    python generate_test_files.py
"""

from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib import colors
import openpyxl
import csv
import os

OUT_DIR = "/tmp"

def make_pdf(path):
    doc = SimpleDocTemplate(path, pagesize=letter)
    styles = getSampleStyleSheet()
    story = []

    story.append(Paragraph("TechCorp Inc. — Annual Report 2023", styles["Title"]))
    story.append(Spacer(1, 12))

    story.append(Paragraph("CEO Letter", styles["Heading1"]))
    story.append(Paragraph(
        "2023 was a transformative year for TechCorp. We achieved record revenue of $5.2 billion, "
        "representing 18% year-over-year growth. Our cloud division grew 34% and now accounts for "
        "42% of total revenue. Net profit margin improved to 22%, up from 18% in 2022. "
        "We expanded into 12 new markets and grew our customer base by 28%.",
        styles["Normal"]))
    story.append(Spacer(1, 12))

    story.append(Paragraph("Financial Highlights", styles["Heading1"]))
    data = [
        ["Metric", "2023", "2022", "Change"],
        ["Total Revenue", "$5.2B", "$4.4B", "+18%"],
        ["Cloud Revenue", "$2.18B", "$1.63B", "+34%"],
        ["Net Profit Margin", "22%", "18%", "+4pp"],
        ["Customer Base", "2.56M", "2.0M", "+28%"],
    ]
    t = Table(data)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.grey),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
    ]))
    story.append(t)
    story.append(Spacer(1, 12))

    story.append(Paragraph("Regional Performance", styles["Heading1"]))
    story.append(Paragraph(
        "North America remains our largest market at 58% of revenue ($3.0B). "
        "Europe contributed 27% ($1.4B), showing 12% growth. "
        "Asia-Pacific grew fastest at 41%, contributing 15% ($0.78B).",  # <-- 15%
        styles["Normal"]))

    doc.build(story)
    print(f"✅ PDF created: {path}")


def make_excel(path):
    wb = openpyxl.Workbook()

    # Sheet 1: Monthly revenue — sums to $4,800M not $5,200M
    ws1 = wb.active
    ws1.title = "Monthly Revenue"
    ws1.append(["Month", "Revenue ($M)", "Cloud ($M)", "Other ($M)"])
    monthly = [
        ("Jan", 380, 140, 240), ("Feb", 370, 138, 232), ("Mar", 410, 152, 258),
        ("Apr", 395, 148, 247), ("May", 405, 155, 250), ("Jun", 420, 162, 258),
        ("Jul", 398, 153, 245), ("Aug", 410, 160, 250), ("Sep", 425, 168, 257),
        ("Oct", 415, 162, 253), ("Nov", 435, 172, 263), ("Dec", 337, 130, 207),
    ]
    for row in monthly:
        ws1.append(row)
    ws1.append([
        "TOTAL",
        sum(r[1] for r in monthly),
        sum(r[2] for r in monthly),
        sum(r[3] for r in monthly),
    ])

    # Sheet 2: Regional — Asia-Pacific shown as 18%, PDF says 15%
    ws2 = wb.create_sheet("Regional")
    ws2.append(["Region", "Revenue ($M)", "% of Total", "YoY Growth"])
    ws2.append(["North America", 3000, "58%", "14%"])
    ws2.append(["Europe", 1400, "27%", "12%"])
    ws2.append(["Asia-Pacific", 936, "18%", "41%"])  # <-- discrepancy: PDF says 15%
    ws2.append(["Other", 464, "9%", "8%"])

    wb.save(path)
    print(f"✅ Excel created: {path}")


def make_csv(path):
    rows = [
        ["product", "q1", "q2", "q3", "q4", "annual"],
        ["Cloud Storage", 52, 58, 63, 67, 240],
        ["Cloud Compute", 38, 42, 47, 51, 178],
        ["SaaS Platform", 28, 31, 34, 37, 130],
        ["Support", 22, 24, 24, 25, 95],
        ["TOTAL CLOUD", 140, 155, 168, 180, 643],
    ]
    with open(path, "w", newline="") as f:
        csv.writer(f).writerows(rows)
    print(f"✅ CSV created: {path}")


if __name__ == "__main__":
    make_pdf(os.path.join(OUT_DIR, "techcorp_annual_report.pdf"))
    make_excel(os.path.join(OUT_DIR, "techcorp_revenue.xlsx"))
    make_csv(os.path.join(OUT_DIR, "techcorp_products.csv"))
    print(f"\nAll files saved to {OUT_DIR}/")
    print("\nKnown discrepancies baked in:")
    print("  1. PDF claims $5.2B revenue — Excel monthly sum is $4.8B")
    print("  2. PDF says Asia-Pacific = 15% — Excel says 18%")