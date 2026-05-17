# Financial Analysis

Expert skill for cross-referencing financial documents and flagging discrepancies between spreadsheet data and PDF narrative claims.

## When to use this skill

Load this skill when asked to:
- Compare figures between a spreadsheet (Excel/CSV) and a PDF report
- Identify trends, anomalies, or inconsistencies in revenue/cost/margin data
- Validate whether written claims in a report match underlying numbers
- Summarise financial trajectory across periods

## Step-by-step approach

1. **Inventory the files** — call `list_files` on the target folder first.
2. **Read the spreadsheet** — call `read_file` on any .xlsx or .csv. Note:
   - Revenue and cost figures by period (month/quarter/year)
   - Year-over-year or period-over-period growth rates
   - Gross margin, net margin, or any derived metric in the sheet
3. **Read the PDF** — call `read_file` on the PDF. Extract:
   - Any numerical claims ("Q3 revenue was $4.2M")
   - Forward-looking statements ("we expect 15% growth next year")
   - Summary tables or charts described in text
4. **Cross-reference** — for each numerical claim in the PDF, find the
   matching row/column in the spreadsheet. Record exact values from both sources.
5. **Flag discrepancies** — report any mismatch. Thresholds:
   - > 1 % difference: flag as a finding
   - Rounding (e.g. $4,187,000 rounded to $4.2M): note but do not flag as error
   - Unit mismatch (thousands vs millions): flag loudly — this is a common trap
6. **Summarise** — produce a structured report (see output format below).

## Output format

```
## Analysis Summary

Files analysed: <list>
Period covered: <date range>

## Findings

1. [MISMATCH] Q3 revenue: PDF claims $4.2M, spreadsheet shows $3.9M (−7.1%)
2. [UNIT ERROR] Annual operating costs: PDF uses "thousands", sheet uses raw dollars
3. [OK] Full-year net revenue: both sources agree at $14.8M
4. [NOTE] PDF rounds Q1 figure ($2,134,500 → $2.1M) — within acceptable rounding

## Trajectory Assessment

<2–3 sentences on whether the overall trend described in the PDF matches
what the numbers actually show>

## Data Quality Notes

<Any caveats about parsing quality, missing pages, merged cells, etc.>
```

## Common pitfalls

- **Rounding**: PDFs almost always display rounded figures. Don't flag a
  $12,500 difference on a $2.1M number as an error — calculate the percentage.
- **Multiple sheets**: Excel files often have a summary sheet and detail sheets.
  Check all sheets before concluding a number is missing.
- **Fiscal vs calendar year**: A report labelled "FY2023" may cover Apr 2023–Mar 2024.
  Verify before comparing periods.
- **Cumulative vs period figures**: "Year-to-date revenue" is not the same as
  "Q3 revenue". Read column headers carefully.
- **Negative numbers**: Some spreadsheets show costs as positives, others as
  negatives. Check sign conventions before comparing totals.
- **Empty rows**: `read_file` skips blank rows in Excel — row numbers in the
  output may not match what you see in the actual file.
