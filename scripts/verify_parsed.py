"""Quick verification — checks the parsed JSON for arithmetic consistency.

Reports:
  - total transactions
  - rows with missing balance / amount
  - row-to-row arithmetic mismatches (balance[i] - balance[i-1] == amount[i])
"""
import json
import os
import sys

paths = sys.argv[1:] or [
    os.path.expanduser("~/Downloads/sample_statements/bank1_azf99.parsed.json"),
    os.path.expanduser("~/Downloads/sample_statements/bank2_azf99.parsed.json"),
    os.path.expanduser("~/Downloads/sample_statements/yes1_azf99.parsed.json"),
]

for path in paths:
    print(f"\n=== {os.path.basename(path)} ===")
    data = json.load(open(path))
    txns = data["transactions"]
    print(f"  total: {len(txns)}")
    print(f"  account: {data['account_number']}, name: {data['account_name']}")
    print(f"  period: {data['statement_period']}")
    if data.get("warnings"):
        print(f"  warnings: {data['warnings']}")

    none_amt = sum(1 for t in txns if t["amount"] is None)
    zero_amt = sum(1 for t in txns if t["amount"] == 0)
    none_bal = sum(1 for t in txns if t["balance"] is None)
    print(f"  zero amount rows: {zero_amt}")
    print(f"  null amount rows: {none_amt}")
    print(f"  null balance rows: {none_bal}")

    # Internal arithmetic check: skip rows with missing amount or balance.
    mismatches = 0
    comparisons = 0
    last = None
    for t in txns:
        cur = t["balance"]
        amt = t["amount"]
        if last is not None and cur is not None and amt is not None:
            comparisons += 1
            if abs((last + amt) - cur) > 0.01:
                mismatches += 1
        if cur is not None:
            last = cur
    print(f"  arithmetic comparisons: {comparisons}, mismatches: {mismatches}")

    if txns:
        print(f"  first 2:")
        for t in txns[:2]:
            print(f"    {t['date']}  amt={t['amount']}  bal={t['balance']}  desc={t['description'][:60]}")
        print(f"  last 2:")
        for t in txns[-2:]:
            print(f"    {t['date']}  amt={t['amount']}  bal={t['balance']}  desc={t['description'][:60]}")
