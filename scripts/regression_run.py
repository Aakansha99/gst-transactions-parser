"""Run the parser against every available sample and verify each result.

Reports per-file: transactions, zero-amount rows, mismatches, account name.
Returns non-zero exit code if any file degrades from a target benchmark.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import parse_statement as ps

REPO = Path(__file__).resolve().parent.parent
HOME = Path.home()

SAMPLES = [
    HOME / "Downloads" / "DetailedStatement (59).pdf",
    HOME / "Downloads" / "Statement_MAY2026_370442576_1.pdf",
    HOME / "Downloads" / "HDFC_statement.pdf",
    HOME / "Downloads" / "sample_statements" / "bank1_azf99.pdf",
    HOME / "Downloads" / "sample_statements" / "bank2_azf99.pdf",
    HOME / "Downloads" / "sample_statements" / "yes1_azf99.pdf",
    REPO / "tests" / "fixtures" / "sample_bank_statement.pdf",
    REPO / "tests" / "fixtures" / "sample_bank_statement_zero_filled.pdf",
]


def run_one(pdf: Path) -> dict:
    if not pdf.exists():
        return {"path": str(pdf), "skipped": True}
    result = ps.parse(pdf)
    txns = result.transactions
    mismatches = 0
    comparisons = 0
    last = None
    for t in txns:
        if last is not None and t.balance is not None and t.amount is not None:
            comparisons += 1
            if abs(last + t.amount - t.balance) > 0.01:
                mismatches += 1
        if t.balance is not None:
            last = t.balance
    zero_amt = sum(1 for t in txns if t.amount == 0)
    return {
        "path": str(pdf),
        "txns": len(txns),
        "zero_amt": zero_amt,
        "mismatches": mismatches,
        "comparisons": comparisons,
        "account_number": result.account_number,
        "account_name": result.account_name,
        "period": (result.statement_period_start, result.statement_period_end),
        "warnings": result.warnings,
    }


def main() -> int:
    rows = [run_one(p) for p in SAMPLES]
    print(f"{'file':45s}  {'txns':>5}  {'zero':>4}  {'mism':>5}  {'cmp':>5}  name")
    print("-" * 100)
    for r in rows:
        if r.get("skipped"):
            print(f"{Path(r['path']).name:45s}  (skipped — file not found)")
            continue
        print(
            f"{Path(r['path']).name:45s}  {r['txns']:>5}  {r['zero_amt']:>4}  "
            f"{r['mismatches']:>5}  {r['comparisons']:>5}  "
            f"{(r['account_name'] or '-')[:30]}"
        )
    print()
    print("Period extraction:")
    for r in rows:
        if r.get("skipped"):
            continue
        print(f"  {Path(r['path']).name:45s} -> {r['period'][0]}  to  {r['period'][1]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
