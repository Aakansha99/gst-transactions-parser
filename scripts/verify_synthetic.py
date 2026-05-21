"""Verify each synthetic fixture parses correctly.

For each fixture:
  - Read the canonical LayoutSpec to know expected count and closing balance
  - Run the parser
  - Compare against expectations and run the row-to-row arithmetic check
  - Print a one-line PASS/FAIL row plus the failure reason

Exits 0 if all pass, 1 if any fail.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import parse_statement as ps
from make_synthetic_fixtures import coverage_matrix


REPO = Path(__file__).resolve().parent.parent
FIXTURE_DIR = REPO / "tests" / "fixtures" / "synthetic"

# Tolerances
BAL_TOL = 0.05  # closing balance match (paise tolerance)


def _arithmetic_mismatches(transactions) -> tuple[int, int]:
    mismatches = 0
    comparisons = 0
    last = None
    for t in transactions:
        if last is not None and t.balance is not None and t.amount is not None:
            comparisons += 1
            if abs(last + t.amount - t.balance) > 0.01:
                mismatches += 1
        if t.balance is not None:
            last = t.balance
    return mismatches, comparisons


def verify_one(spec) -> dict:
    pdf_path = FIXTURE_DIR / f"{spec.name}.pdf"
    if not pdf_path.exists():
        return {"name": spec.name, "status": "MISSING", "reason": "fixture not found"}

    result = ps.parse(pdf_path)
    txns = result.transactions

    failures = []

    # Count check — only when balance column exists; with no balance column,
    # the first row (Opening Balance) and last row (Closing Balance) might
    # not be detectable as transactions because they have no amount value.
    expected_count_min = spec.expected_count - 2  # tolerate sentinel rows
    expected_count_max = spec.expected_count + 2
    if not (expected_count_min <= len(txns) <= expected_count_max):
        failures.append(f"count={len(txns)} (expected ~{spec.expected_count})")

    # Closing balance check — only when fixture has a balance column.
    if spec.balance_shape != "none":
        closing = next(
            (t.balance for t in reversed(txns) if t.balance is not None),
            None,
        )
        if closing is None:
            failures.append("no balance values parsed")
        elif abs(closing - spec.expected_closing_balance) > BAL_TOL:
            failures.append(
                f"closing={closing:.2f} (expected {spec.expected_closing_balance:.2f})"
            )

    # Arithmetic consistency. Only meaningful when the fixture has a
    # balance column to track.
    mism, comp = _arithmetic_mismatches(txns)
    if spec.balance_shape != "none":
        if comp == 0:
            failures.append("no arithmetic comparisons made")
        elif mism > 0:
            failures.append(f"{mism}/{comp} arithmetic mismatches")

    # Sum of signed amounts should equal closing - opening (within tolerance).
    if spec.balance_shape != "none" and txns:
        total_signed = sum(t.amount for t in txns if t.amount is not None)
        first_bal = next((t.balance for t in txns if t.balance is not None), None)
        last_bal = next(
            (t.balance for t in reversed(txns) if t.balance is not None), None
        )
        if first_bal is not None and last_bal is not None:
            expected_delta = last_bal - first_bal
            if abs(total_signed - expected_delta) > 1.0:
                failures.append(
                    f"sum of signed amounts={total_signed:.2f} "
                    f"(expected ~{expected_delta:.2f})"
                )

    return {
        "name": spec.name,
        "status": "PASS" if not failures else "FAIL",
        "txns": len(txns),
        "mismatches": mism,
        "comparisons": comp,
        "account_name": result.account_name or "-",
        "account_number": result.account_number or "-",
        "period_start": result.statement_period_start or "-",
        "period_end": result.statement_period_end or "-",
        "warnings": result.warnings,
        "reason": "; ".join(failures) if failures else "",
    }


def main() -> int:
    rows = [verify_one(s) for s in coverage_matrix()]
    print(f"{'fixture':35s}  {'status':6s}  {'txns':>5}  {'mis':>3}  {'cmp':>3}  reason")
    print("-" * 110)
    n_pass = 0
    for r in rows:
        status_str = r["status"]
        line = (
            f"{r['name']:35s}  {status_str:6s}  "
            f"{r.get('txns', 0):>5}  {r.get('mismatches', 0):>3}  "
            f"{r.get('comparisons', 0):>3}  {r['reason']}"
        )
        print(line)
        if status_str == "PASS":
            n_pass += 1

    print()
    print(f"{n_pass}/{len(rows)} fixtures pass")

    print("\nMetadata:")
    for r in rows:
        print(
            f"  {r['name']:35s} acct={r['account_number']}  "
            f"name={r['account_name'][:30]:30s}  "
            f"period={r['period_start']} → {r['period_end']}"
        )

    return 0 if n_pass == len(rows) else 1


if __name__ == "__main__":
    sys.exit(main())
