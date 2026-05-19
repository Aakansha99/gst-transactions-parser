"""Generate a coverage matrix of synthetic bank statement fixtures.

Each fixture varies one or more axes that real banks vary on:
  - date format
  - number format (Indian vs US grouping)
  - amount column shape (single, debit+credit, with/without 0.00 filler)
  - balance shape (plain, CR/DR suffix, none)
  - column order
  - header style (honorific, labelled name, branch-only)
  - filler placeholders (~, --, 0.00)

The same canonical transaction set is reused so each fixture has a known
ground truth (closing balance, count, sum). Use `verify_synthetic.py` to
parse all fixtures and report pass/fail.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
)


# ---------- Canonical data (shared by all fixtures) ----------

ACCOUNT = {
    "bank": "Sample Bank Ltd.",
    "branch": "MG Road, Bengaluru",
    "ifsc": "SAMP0001234",
    "name": "MR. SAMPLE CUSTOMER",
    "address": "12, Sample Street, Bengaluru 560001",
    "account_number": "987654321012",
    "period_iso_from": (2025, 4, 1),
    "period_iso_to":   (2025, 6, 30),
}

# (iso_date_tuple, description, debit, credit, balance)
TRANSACTIONS: list[tuple[tuple[int, int, int], str, float | None, float | None, float]] = [
    ((2025, 4, 1),  "Opening Balance",                                None,    None,    25000.00),
    ((2025, 4, 2),  "UPI/AMAZON/9876543210/PAYMENT",                  1499.00, None,    23501.00),
    ((2025, 4, 3),  "NEFT-CR/HDFC0001234/SALARY APRIL 2025",          None,   75000.00,  98501.00),
    ((2025, 4, 5),  "ATM-WDL/SAMP0001234/BENGALURU",                  5000.00, None,    93501.00),
    ((2025, 4, 7),  "UPI/SWIGGY/abcd@upi/ORDER REFUND",               None,    240.00,  93741.00),
    ((2025, 4, 10), "IMPS/PARENTS/SBIN0000001/MONTHLY",              20000.00, None,    73741.00),
    ((2025, 4, 12), "BIL/ELECTRICITY/BESCOM/MAR-25",                  2150.00, None,    71591.00),
    ((2025, 4, 15), "POS/DMART/CARD ENDING 1234",                     3275.50, None,    68315.50),
    ((2025, 4, 18), "UPI/UBER/uber@axis/RIDE",                         340.00, None,    67975.50),
    ((2025, 4, 20), "NEFT-CR/AXIS0009999/REFUND-INSURANCE",           None,   1850.00,  69825.50),
    ((2025, 4, 22), "UPI/ZOMATO/zomato@ybl/ORDER",                     612.00, None,    69213.50),
    ((2025, 4, 25), "BIL/CREDIT-CARD/HDFC/APR STMT",                 15000.00, None,    54213.50),
    ((2025, 4, 28), "INT-CR/QUARTERLY INTEREST",                       None,    187.45, 54400.95),
    ((2025, 4, 30), "CHQ-DEPOSIT/123456/SELF",                         None,  10000.00, 64400.95),
    ((2025, 5, 2),  "UPI/RENT/landlord@okicici",                     18000.00, None,    46400.95),
    ((2025, 5, 5),  "NEFT-CR/HDFC0001234/SALARY MAY 2025",             None,  75000.00,121400.95),
    ((2025, 5, 8),  "POS/AIRTEL/POSTPAID BILL",                        799.00, None,   120601.95),
    ((2025, 5, 11), "UPI/NETFLIX/netflix@hdfc",                        649.00, None,   119952.95),
    ((2025, 5, 14), "ATM-WDL/SAMP0001234/BENGALURU",                 10000.00, None,   109952.95),
    ((2025, 5, 18), "IMPS-CR/ICIC0000123/REFUND",                      None,   2400.00,112352.95),
    ((2025, 5, 22), "BIL/MOBILE-RECHARGE/JIO",                         299.00, None,   112053.95),
    ((2025, 5, 25), "POS/BIG BAZAAR/CARD 1234",                       4280.75, None,   107773.20),
    ((2025, 5, 28), "UPI/PARENTS/MONTHLY",                           20000.00, None,    87773.20),
    ((2025, 5, 30), "INT-CR/MAY INTEREST",                             None,    210.55, 87983.75),
    ((2025, 6, 2),  "BIL/BROADBAND/ACT FIBERNET",                     1199.00, None,    86784.75),
    ((2025, 6, 5),  "NEFT-CR/HDFC0001234/SALARY JUNE 2025",            None,  75000.00,161784.75),
    ((2025, 6, 8),  "UPI/AMAZON/refund@axis",                          None,   1499.00,163283.75),
    ((2025, 6, 12), "POS/RELIANCE-DIGITAL/CARD 1234",                32999.00, None,   130284.75),
    ((2025, 6, 16), "BIL/CREDIT-CARD/HDFC/JUN STMT",                 18500.00, None,   111784.75),
    ((2025, 6, 20), "ATM-WDL/SAMP0001234/BENGALURU",                 15000.00, None,    96784.75),
    ((2025, 6, 25), "UPI/PARENTS/MONTHLY",                           20000.00, None,    76784.75),
    ((2025, 6, 28), "INT-CR/QUARTERLY INTEREST",                       None,    295.30, 77080.05),
    ((2025, 6, 30), "Closing Balance",                                 None,    None,   77080.05),
]

MONTH_ABBR = ["", "Jan", "Feb", "Mar", "Apr", "May", "Jun",
              "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


# ---------- Layout configuration ----------

@dataclass
class LayoutSpec:
    """Describes one fixture's layout. Each axis is independent."""
    name: str
    date_format: str = "DD/MM/YYYY"          # DD/MM/YYYY, DD-MM-YYYY, DD/MMM/YYYY, DD-MMM-YY, YYYY-MM-DD, MM/DD/YYYY
    number_format: str = "indian"            # 'indian' (1,82,196.96) or 'us' (1,182,196.96)
    amount_shape: str = "debit_credit_blank" # 'single_signed', 'single_with_suffix', 'debit_credit_blank', 'debit_credit_zero', 'withdrawal_deposit'
    balance_shape: str = "plain"             # 'plain', 'with_cr_suffix', 'none'
    column_order: str = "date_first"         # 'date_first', 'date_last', 'with_value_date'
    header_style: str = "honorific"          # 'honorific', 'labelled', 'branch_only'
    filler_char: str | None = None           # None or '~' or '--'
    add_legends: bool = False                # True → add an ICICI-style legends section after the table
    page_total: bool = False                 # True → emit a 'Page Total' row that should be detected/skipped

    # Computed expected values (added by post_init)
    expected_count: int = 0
    expected_closing_balance: float = 0.0

    def __post_init__(self):
        # Counted as transactions: rows with a non-None debit or credit.
        self.expected_count = sum(
            1 for (_, _, dr, cr, _) in TRANSACTIONS if dr is not None or cr is not None
        )
        self.expected_closing_balance = TRANSACTIONS[-1][4]


# ---------- Formatters ----------

def fmt_date(d: tuple[int, int, int], fmt: str) -> str:
    y, m, day = d
    if fmt == "DD/MM/YYYY":
        return f"{day:02d}/{m:02d}/{y}"
    if fmt == "DD-MM-YYYY":
        return f"{day:02d}-{m:02d}-{y}"
    if fmt == "DD/MMM/YYYY":
        return f"{day:02d}/{MONTH_ABBR[m]}/{y}"
    if fmt == "DD-MMM-YY":
        return f"{day:02d}-{MONTH_ABBR[m]}-{y % 100:02d}"
    if fmt == "YYYY-MM-DD":
        return f"{y}-{m:02d}-{day:02d}"
    if fmt == "MM/DD/YYYY":
        return f"{m:02d}/{day:02d}/{y}"
    if fmt == "DD/MM/YY":
        return f"{day:02d}/{m:02d}/{y % 100:02d}"
    if fmt == "MMM_DD_YYYY":
        # "Apr 30, 2025" — comma-separated month+day+year, not in the strict
        # regex list. Used to exercise the fuzzy date fallback.
        return f"{MONTH_ABBR[m]} {day:02d}, {y}"
    if fmt == "DD_DOT_MM_DOT_YYYY":
        # "30.04.2025" — European dotted format, also not in the strict list.
        return f"{day:02d}.{m:02d}.{y}"
    raise ValueError(f"Unknown date format: {fmt}")


def fmt_indian(value: float) -> str:
    """Indian comma grouping: 1,82,196.96."""
    integer, dec = f"{value:.2f}".split(".")
    sign = ""
    if integer.startswith("-"):
        sign = "-"
        integer = integer[1:]
    if len(integer) <= 3:
        return f"{sign}{integer}.{dec}"
    last3 = integer[-3:]
    rest = integer[:-3]
    parts = []
    while len(rest) > 2:
        parts.insert(0, rest[-2:])
        rest = rest[:-2]
    if rest:
        parts.insert(0, rest)
    return f"{sign}{','.join(parts)},{last3}.{dec}"


def fmt_us(value: float) -> str:
    return f"{value:,.2f}"


def fmt_amount(value: float | None, *, fmt: str, fill: str = "") -> str:
    if value is None:
        return fill
    if fmt == "indian":
        return fmt_indian(value)
    return fmt_us(value)


def fmt_period(spec: LayoutSpec) -> tuple[str, str]:
    return (
        fmt_date(ACCOUNT["period_iso_from"], spec.date_format),
        fmt_date(ACCOUNT["period_iso_to"], spec.date_format),
    )


# ---------- Build a single fixture ----------

def _build_header_block(spec: LayoutSpec) -> list:
    """Account info block above the transactions table."""
    styles = getSampleStyleSheet()
    title = ParagraphStyle("title", parent=styles["Heading1"], fontSize=15, spaceAfter=4)
    sub = ParagraphStyle("sub", parent=styles["Heading2"], fontSize=10, spaceAfter=2)

    story = []
    story.append(Paragraph(ACCOUNT["bank"], title))
    story.append(Paragraph(
        f"Branch: {ACCOUNT['branch']} &nbsp;&nbsp;|&nbsp;&nbsp; IFSC: {ACCOUNT['ifsc']}", sub
    ))
    story.append(Spacer(1, 4 * mm))

    pf, pt = fmt_period(spec)

    if spec.header_style == "honorific":
        rows = [
            [ACCOUNT["name"], ""],
            ["Address:", ACCOUNT["address"]],
            ["A/C No:", ACCOUNT["account_number"]],
            ["Statement Period:", f"{pf} to {pt}"],
        ]
    elif spec.header_style == "labelled":
        rows = [
            ["Customer Name:", ACCOUNT["name"]],
            ["Address:", ACCOUNT["address"]],
            ["Account Number:", ACCOUNT["account_number"]],
            ["Statement Period:", f"From {pf} To {pt}"],
        ]
    elif spec.header_style == "branch_only":
        rows = [
            ["Account Number:", ACCOUNT["account_number"]],
            ["Statement of Account from:", f"{pf} to {pt}"],
        ]
    else:
        raise ValueError(f"Unknown header_style: {spec.header_style}")

    info = Table(rows, colWidths=[40 * mm, 110 * mm])
    info.setStyle(TableStyle([
        ("FONT", (0, 0), (-1, -1), "Helvetica", 9),
        ("FONT", (0, 0), (0, -1), "Helvetica-Bold", 9),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
        ("TOPPADDING", (0, 0), (-1, -1), 1),
    ]))
    story.append(info)
    story.append(Spacer(1, 6 * mm))
    return story


def _txn_rows(spec: LayoutSpec) -> tuple[list[str], list[list[str]], list[float]]:
    """Build header + body rows and the canonical column-widths."""
    nf = spec.number_format
    fill = spec.filler_char or ""

    def amt(v: float | None) -> str:
        if v is None:
            if spec.amount_shape == "debit_credit_zero":
                return "0.00"
            return fill
        return fmt_amount(v, fmt=nf)

    def signed_amt(dr: float | None, cr: float | None) -> str:
        # Single column carrying signed amount; debit is negative.
        if dr is not None:
            return fmt_amount(-dr, fmt=nf)
        if cr is not None:
            return fmt_amount(cr, fmt=nf)
        return ""

    def signed_amt_with_suffix(dr: float | None, cr: float | None) -> str:
        # "Single amount + Dr/Cr suffix" style.
        if dr is not None:
            return f"{fmt_amount(dr, fmt=nf)} Dr"
        if cr is not None:
            return f"{fmt_amount(cr, fmt=nf)} Cr"
        return ""

    def bal(v: float) -> str:
        if spec.balance_shape == "plain":
            return fmt_amount(v, fmt=nf)
        if spec.balance_shape == "with_cr_suffix":
            return f"{fmt_amount(v, fmt=nf)} CR"
        if spec.balance_shape == "none":
            return ""  # caller drops the column
        raise ValueError(f"Unknown balance_shape: {spec.balance_shape}")

    # Build the per-row cells based on amount_shape.
    body_cells = []
    for (d, desc, dr, cr, balance) in TRANSACTIONS:
        date_s = fmt_date(d, spec.date_format)
        if spec.amount_shape == "single_signed":
            cells = [date_s, desc, signed_amt(dr, cr), bal(balance)]
        elif spec.amount_shape == "single_with_suffix":
            cells = [date_s, desc, signed_amt_with_suffix(dr, cr), bal(balance)]
        elif spec.amount_shape in ("debit_credit_blank", "debit_credit_zero"):
            cells = [date_s, desc, amt(dr), amt(cr), bal(balance)]
        elif spec.amount_shape == "withdrawal_deposit":
            cells = [date_s, desc, amt(dr), amt(cr), bal(balance)]
        else:
            raise ValueError(f"Unknown amount_shape: {spec.amount_shape}")
        body_cells.append(cells)

    # Column header row.
    if spec.amount_shape == "single_signed":
        header = ["Date", "Description", "Amount", "Balance"]
        widths = [25 * mm, 90 * mm, 28 * mm, 28 * mm]
    elif spec.amount_shape == "single_with_suffix":
        header = ["Date", "Description", "Amount", "Balance"]
        widths = [25 * mm, 90 * mm, 30 * mm, 30 * mm]
    elif spec.amount_shape == "debit_credit_blank" or spec.amount_shape == "debit_credit_zero":
        header = ["Date", "Description", "Debit", "Credit", "Balance"]
        widths = [25 * mm, 75 * mm, 22 * mm, 22 * mm, 27 * mm]
    elif spec.amount_shape == "withdrawal_deposit":
        header = ["Date", "Description", "Withdrawal", "Deposit", "Balance"]
        widths = [25 * mm, 70 * mm, 25 * mm, 25 * mm, 27 * mm]
    else:
        raise ValueError(spec.amount_shape)

    # Drop balance column if balance_shape == none.
    if spec.balance_shape == "none":
        header = header[:-1]
        widths = widths[:-1]
        body_cells = [row[:-1] for row in body_cells]

    # Apply column order transformations.
    if spec.column_order == "date_last":
        header = header[1:] + [header[0]]
        body_cells = [row[1:] + [row[0]] for row in body_cells]
        widths = widths[1:] + [widths[0]]
    elif spec.column_order == "with_value_date":
        # Insert a Value Date column right after Date with the same date.
        header = [header[0], "Value Date"] + header[1:]
        body_cells = [[row[0], row[0]] + row[1:] for row in body_cells]
        widths = [widths[0], widths[0]] + widths[1:]
    elif spec.column_order != "date_first":
        raise ValueError(spec.column_order)

    return header, body_cells, widths


def build_fixture(spec: LayoutSpec, output_path: Path) -> None:
    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=A4,
        leftMargin=15 * mm, rightMargin=15 * mm,
        topMargin=15 * mm, bottomMargin=15 * mm,
        title=f"Synthetic fixture: {spec.name}",
    )
    story = _build_header_block(spec)

    header, body, widths = _txn_rows(spec)
    rows = [header] + body
    n_cols = len(header)

    # Optional Page Total row.
    if spec.page_total:
        total_dr = sum(
            (-row[2 if spec.amount_shape == "single_signed" else 2]) if False else 0
            for row in body
        )
        # Simple page total with totals only in amount columns; we don't put
        # a date here, so the parser should *not* count it as a transaction.
        pt_row = ["" for _ in range(n_cols)]
        # Find an amount column (it's the second-to-last when balance present)
        if spec.amount_shape in ("debit_credit_blank", "debit_credit_zero", "withdrawal_deposit"):
            # Sum of debits, sum of credits.
            dr_sum = sum(t[2] for t in TRANSACTIONS if t[2] is not None)
            cr_sum = sum(t[3] for t in TRANSACTIONS if t[3] is not None)
            # Find debit/credit columns by position in header.
            # When date_first, debit is index 2, credit index 3.
            if spec.column_order == "date_first":
                pt_row[1] = "Page Total"
                pt_row[2] = fmt_amount(dr_sum, fmt=spec.number_format)
                pt_row[3] = fmt_amount(cr_sum, fmt=spec.number_format)
        else:
            if spec.column_order == "date_first":
                pt_row[1] = "Page Total"
        rows.append(pt_row)

    txn_table = Table(rows, colWidths=widths, repeatRows=1)
    txn_table.setStyle(TableStyle([
        ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 9),
        ("FONT", (0, 1), (-1, -1), "Helvetica", 8),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e8eef7")),
        ("ALIGN", (-3, 0), (-1, -1), "RIGHT"),  # right-align rightmost few
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
        ("LEFTPADDING", (0, 0), (-1, -1), 3),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]))
    story.append(txn_table)

    if spec.add_legends:
        story.append(Spacer(1, 4 * mm))
        legends = [
            "Legends Used in Account Statement",
            "1. UPI - Unified Payments Interface",
            "2. NEFT - National Electronic Funds Transfer",
            "3. IMPS - Immediate Payment Service",
            "4. ATM-WDL - ATM Withdrawal",
        ]
        styles = getSampleStyleSheet()
        for line in legends:
            story.append(Paragraph(line, styles["Normal"]))

    doc.build(story)


# ---------- Coverage matrix ----------

def coverage_matrix() -> list[LayoutSpec]:
    """A curated list of layouts covering the variation axes."""
    specs: list[LayoutSpec] = [
        # 1. Baseline
        LayoutSpec(name="01_baseline_indian"),
        # 2. Empty cells filled with 0.00 (YES Bank style)
        LayoutSpec(name="02_zero_filled_empties", amount_shape="debit_credit_zero"),
        # 3. CR/DR suffix on balance (Allahabad style)
        LayoutSpec(name="03_cr_suffix_balance", balance_shape="with_cr_suffix"),
        # 4. Filler chars between columns (Allahabad style)
        LayoutSpec(name="04_filler_tilde", filler_char="~", balance_shape="with_cr_suffix"),
        # 5. Single signed amount column
        LayoutSpec(name="05_single_signed_amount", amount_shape="single_signed"),
        # 6. Single amount + Dr/Cr suffix
        LayoutSpec(name="06_single_with_dr_cr_suffix", amount_shape="single_with_suffix"),
        # 7. Withdrawal/Deposit naming
        LayoutSpec(name="07_withdrawal_deposit_label", amount_shape="withdrawal_deposit"),
        # 8. Date last
        LayoutSpec(name="08_date_last", column_order="date_last"),
        # 9. With Value Date column
        LayoutSpec(name="09_with_value_date", column_order="with_value_date"),
        # 10. Different date formats
        LayoutSpec(name="10_date_dash_short_year", date_format="DD-MMM-YY"),
        LayoutSpec(name="11_date_iso", date_format="YYYY-MM-DD"),
        LayoutSpec(name="12_date_us_mdy", date_format="MM/DD/YYYY"),
        LayoutSpec(name="13_date_dd_mmm_yyyy", date_format="DD/MMM/YYYY"),
        # 14. US number format
        LayoutSpec(name="14_us_number_format", number_format="us"),
        # 15. No balance column
        LayoutSpec(name="15_no_balance_column", balance_shape="none"),
        # 16. Header is labelled (no honorific)
        LayoutSpec(name="16_labelled_header", header_style="labelled"),
        # 17. Header has only branch + account
        LayoutSpec(name="17_branch_only_header", header_style="branch_only"),
        # 18. Page total row at end (footer chrome)
        LayoutSpec(name="18_page_total_row", page_total=True),
        # 19. Legends after table (ICICI style)
        LayoutSpec(name="19_with_legends", add_legends=True),
        # 20. Combined hard case: zero-filled + value date + page total
        LayoutSpec(
            name="20_combined_hard",
            amount_shape="debit_credit_zero",
            column_order="with_value_date",
            page_total=True,
        ),
        # 21–22. Date formats not in the strict regex list — exercise the
        # dateutil fuzzy fallback. If the parser passes these, the fallback
        # is genuinely working; if it fails them, the fallback is broken.
        LayoutSpec(name="21_fuzzy_date_word_comma", date_format="MMM_DD_YYYY"),
        LayoutSpec(name="22_fuzzy_date_dotted", date_format="DD_DOT_MM_DOT_YYYY"),
    ]
    return specs


def main(argv: list[str]) -> int:
    repo_root = Path(__file__).resolve().parent.parent
    out_dir = repo_root / "tests" / "fixtures" / "synthetic"
    out_dir.mkdir(parents=True, exist_ok=True)

    specs = coverage_matrix()
    for spec in specs:
        path = out_dir / f"{spec.name}.pdf"
        try:
            build_fixture(spec, path)
            print(f"  wrote {spec.name}")
        except Exception as e:
            print(f"  FAILED to build {spec.name}: {e}")

    print(f"\nGenerated {len(specs)} fixtures in {out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
