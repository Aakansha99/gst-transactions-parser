"""Generate a sample bank statement PDF (test fixture).

Modeled on a generic Indian bank statement layout:
  - Header: bank name, branch, customer name, account number, period
  - Bordered transactions table with columns:
      Date | Description | Debit | Credit | Balance

Usage:
    python scripts/make_sample_pdf.py
    python scripts/make_sample_pdf.py /path/to/output.pdf
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    PageBreak,
)


# ---- Sample data --------------------------------------------------------

ACCOUNT = {
    "bank": "Sample Bank Ltd.",
    "branch": "MG Road, Bengaluru",
    "ifsc": "SAMP0001234",
    "name": "MR. SAMPLE CUSTOMER",
    "address": "12, Sample Street, Bengaluru 560001",
    "account_number": "987654321012",
    "account_type": "SAVINGS",
    "period_from": "01/04/2025",
    "period_to": "30/06/2025",
}

# (date, description, debit, credit, balance)
# Balances are internally consistent so the parser can be checked easily.
TRANSACTIONS = [
    ("01/04/2025", "Opening Balance",                                 None,    None,    25000.00),
    ("02/04/2025", "UPI/AMAZON/9876543210/PAYMENT",                  1499.00, None,    23501.00),
    ("03/04/2025", "NEFT-CR/HDFC0001234/SALARY APRIL 2025",           None,   75000.00, 98501.00),
    ("05/04/2025", "ATM-WDL/SAMP0001234/BENGALURU",                  5000.00, None,    93501.00),
    ("07/04/2025", "UPI/SWIGGY/abcd@upi/ORDER REFUND",                None,    240.00,  93741.00),
    ("10/04/2025", "IMPS/PARENTS/SBIN0000001/MONTHLY",               20000.00, None,    73741.00),
    ("12/04/2025", "BIL/ELECTRICITY/BESCOM/MAR-25",                   2150.00, None,    71591.00),
    ("15/04/2025", "POS/DMART/CARD ENDING 1234",                      3275.50, None,    68315.50),
    ("18/04/2025", "UPI/UBER/uber@axis/RIDE",                          340.00, None,    67975.50),
    ("20/04/2025", "NEFT-CR/AXIS0009999/REFUND-INSURANCE",             None,   1850.00, 69825.50),
    ("22/04/2025", "UPI/ZOMATO/zomato@ybl/ORDER",                      612.00, None,    69213.50),
    ("25/04/2025", "BIL/CREDIT-CARD/HDFC/APR STMT",                  15000.00, None,    54213.50),
    ("28/04/2025", "INT-CR/QUARTERLY INTEREST",                         None,    187.45, 54400.95),
    ("30/04/2025", "CHQ-DEPOSIT/123456/SELF",                           None, 10000.00, 64400.95),
    ("02/05/2025", "UPI/RENT/landlord@okicici",                       18000.00, None,    46400.95),
    ("05/05/2025", "NEFT-CR/HDFC0001234/SALARY MAY 2025",               None, 75000.00, 121400.95),
    ("08/05/2025", "POS/AIRTEL/POSTPAID BILL",                         799.00, None,   120601.95),
    ("11/05/2025", "UPI/NETFLIX/netflix@hdfc",                         649.00, None,   119952.95),
    ("14/05/2025", "ATM-WDL/SAMP0001234/BENGALURU",                  10000.00, None,   109952.95),
    ("18/05/2025", "IMPS-CR/ICIC0000123/REFUND",                        None,  2400.00, 112352.95),
    ("22/05/2025", "BIL/MOBILE-RECHARGE/JIO",                          299.00, None,   112053.95),
    ("25/05/2025", "POS/BIG BAZAAR/CARD 1234",                        4280.75, None,   107773.20),
    ("28/05/2025", "UPI/PARENTS/MONTHLY",                            20000.00, None,    87773.20),
    ("30/05/2025", "INT-CR/MAY INTEREST",                                None,   210.55,  87983.75),
    ("02/06/2025", "BIL/BROADBAND/ACT FIBERNET",                      1199.00, None,    86784.75),
    ("05/06/2025", "NEFT-CR/HDFC0001234/SALARY JUNE 2025",               None, 75000.00, 161784.75),
    ("08/06/2025", "UPI/AMAZON/refund@axis",                             None,  1499.00, 163283.75),
    ("12/06/2025", "POS/RELIANCE-DIGITAL/CARD 1234",                 32999.00, None,   130284.75),
    ("16/06/2025", "BIL/CREDIT-CARD/HDFC/JUN STMT",                  18500.00, None,   111784.75),
    ("20/06/2025", "ATM-WDL/SAMP0001234/BENGALURU",                  15000.00, None,    96784.75),
    ("25/06/2025", "UPI/PARENTS/MONTHLY",                            20000.00, None,    76784.75),
    ("28/06/2025", "INT-CR/QUARTERLY INTEREST",                          None,   295.30,  77080.05),
    ("30/06/2025", "Closing Balance",                                    None,    None, 77080.05),
]


def _fmt_amount(value, *, zero_for_empty: bool = False):
    if value is None:
        return "0.00" if zero_for_empty else ""
    return f"{value:,.2f}"


def build(output_path: Path, *, zero_for_empty: bool = False) -> None:
    styles = getSampleStyleSheet()
    title = ParagraphStyle("title", parent=styles["Heading1"], fontSize=16, spaceAfter=4)
    sub = ParagraphStyle("sub", parent=styles["Heading2"], fontSize=11, spaceAfter=2)
    label = ParagraphStyle("label", parent=styles["Normal"], fontSize=9)

    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=A4,
        leftMargin=15 * mm,
        rightMargin=15 * mm,
        topMargin=15 * mm,
        bottomMargin=15 * mm,
        title="Sample Bank Statement",
    )

    story = []

    story.append(Paragraph(ACCOUNT["bank"], title))
    story.append(Paragraph(f"Branch: {ACCOUNT['branch']} &nbsp;&nbsp;|&nbsp;&nbsp; IFSC: {ACCOUNT['ifsc']}", sub))
    story.append(Spacer(1, 6 * mm))

    info = [
        ["Account Holder:", ACCOUNT["name"]],
        ["Address:",        ACCOUNT["address"]],
        ["Account Number:", ACCOUNT["account_number"]],
        ["Account Type:",   ACCOUNT["account_type"]],
        ["Statement Period:", f"{ACCOUNT['period_from']} to {ACCOUNT['period_to']}"],
    ]
    info_table = Table(info, colWidths=[40 * mm, 110 * mm])
    info_table.setStyle(TableStyle([
        ("FONT", (0, 0), (-1, -1), "Helvetica", 10),
        ("FONT", (0, 0), (0, -1), "Helvetica-Bold", 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
    ]))
    story.append(info_table)
    story.append(Spacer(1, 8 * mm))

    story.append(Paragraph("Statement of Account", sub))
    story.append(Spacer(1, 2 * mm))

    header = ["Date", "Description", "Debit", "Credit", "Balance"]
    body = [
        [
            d,
            desc,
            _fmt_amount(dr, zero_for_empty=zero_for_empty),
            _fmt_amount(cr, zero_for_empty=zero_for_empty),
            _fmt_amount(bal),
        ]
        for (d, desc, dr, cr, bal) in TRANSACTIONS
    ]
    table_data = [header] + body

    txn_table = Table(
        table_data,
        colWidths=[24 * mm, 75 * mm, 22 * mm, 22 * mm, 27 * mm],
        repeatRows=1,
    )
    txn_table.setStyle(TableStyle([
        ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 10),
        ("FONT", (0, 1), (-1, -1), "Helvetica", 9),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e8eef7")),
        ("ALIGN", (2, 0), (4, -1), "RIGHT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    story.append(txn_table)

    story.append(Spacer(1, 6 * mm))
    story.append(Paragraph(
        "This is a system-generated statement. Please report any discrepancies within 30 days.",
        ParagraphStyle("footer", parent=styles["Italic"], fontSize=8),
    ))

    doc.build(story)


def main(argv: list[str]) -> int:
    repo_root = Path(__file__).resolve().parent.parent
    fixtures = repo_root / "tests" / "fixtures"
    fixtures.mkdir(parents=True, exist_ok=True)

    if len(argv) > 1:
        out = Path(os.path.expanduser(argv[1])).resolve()
        out.parent.mkdir(parents=True, exist_ok=True)
        build(out)
        print(f"Wrote: {out}")
        return 0

    # Default: build both variants so we can test the parser against
    #   1. blank empty-side cells (clean layout)
    #   2. "0.00"-filled empty-side cells (mirrors the YES Bank failure mode)
    clean = fixtures / "sample_bank_statement.pdf"
    zero_filled = fixtures / "sample_bank_statement_zero_filled.pdf"
    build(clean, zero_for_empty=False)
    build(zero_filled, zero_for_empty=True)
    print(f"Wrote: {clean}")
    print(f"Wrote: {zero_filled}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
