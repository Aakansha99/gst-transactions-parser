"""Adapter that converts the parser's ParseResult into the JSON shape the
React UI expects (camelCase, matching `src/types.ts`).

The parser groups all transactions under a single account today (its
internal data model is one ParseResult per PDF). The UI expects an array of
`transactionGroups`, each keyed by `{ accountNumber, accountName }`. We map
the parser's account_number/account_name to a single group.

If the parser fails to extract an account name, we fall back to a
placeholder so the UI still renders something readable.
"""

from __future__ import annotations

from typing import Any

from .parser import ParseResult, Transaction


def _to_account_identifier(result: ParseResult) -> dict[str, str]:
    return {
        "accountNumber": result.account_number or "Unknown",
        "accountName": result.account_name or "Unknown account",
    }


def _to_ui_transaction(t: Transaction) -> dict[str, Any]:
    # The UI's Transaction interface is { date, description, amount } —
    # balance is preserved as an additional field for clients that want it,
    # but the existing UI ignores it.
    payload: dict[str, Any] = {
        "date": t.date,
        "description": t.description,
        "amount": t.amount,
    }
    if t.balance is not None:
        payload["balance"] = t.balance
    return payload


def _to_statement_period(result: ParseResult) -> dict[str, str]:
    return {
        "startDate": result.statement_period_start or "Unknown",
        "endDate": result.statement_period_end or "Unknown",
    }


def to_ui_payload(result: ParseResult) -> dict[str, Any]:
    """Convert a parser ParseResult into the JSON the React UI expects."""
    account = _to_account_identifier(result)
    transactions = [_to_ui_transaction(t) for t in result.transactions]
    return {
        "statementPeriod": _to_statement_period(result),
        "transactionGroups": [
            {
                "account": account,
                "transactions": transactions,
            }
        ],
        "warnings": list(result.warnings or []),
    }
