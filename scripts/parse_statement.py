#!/usr/bin/env python3
"""
Generic bank statement PDF parser using pdfplumber.

Usage:
    python parse_statement.py <pdf_path>
    python parse_statement.py "~/Downloads/DetailedStatement (59).pdf"

The parser:
  1. Uses pdfplumber's built-in table detection (no hardcoded column names).
  2. Picks the largest table on each page as the transaction table.
  3. Identifies columns by data shape (dates, amounts, balances) instead of
     by header text.
  4. Reconciles wrapped cells across pages and outputs a normalised list of
     transactions plus account metadata.

Output: writes both JSON and CSV next to the input PDF, and prints a summary
to stdout.
"""

from __future__ import annotations

import csv
import json
import os
import re
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Iterable

import pdfplumber

try:
    from dateutil import parser as _dateutil_parser  # type: ignore
    _HAS_DATEUTIL = True
except ImportError:
    _HAS_DATEUTIL = False

# Fuzzy date detection is opt-in per call. The default is strict (regex
# only) because fuzzy matching is more permissive and can spuriously match
# truncated cells like "5/2025" that result from PDF text-strategy column
# splits. The pipeline retries a page with fuzzy enabled only if strict
# parsing fails to find any date column.
_FUZZY_DATES_ENABLED = False


# ---------- Patterns used for content fingerprinting ----------

DATE_PATTERNS = [
    re.compile(r"^\d{2}/\d{2}/\d{4}$"),                        # 07/05/2025
    re.compile(r"^\d{2}-\d{2}-\d{4}$"),                        # 07-05-2025
    re.compile(r"^\d{4}-\d{2}-\d{2}$"),                        # 2025-05-07
    re.compile(r"^\d{4}/\d{2}/\d{2}$"),                        # 2025/05/07
    re.compile(r"^\d{2}/[A-Za-z]{3}/\d{4}$"),                  # 07/May/2025
    re.compile(r"^\d{2}-[A-Za-z]{3}-\d{4}$"),                  # 07-May-2025
    re.compile(r"^\d{2}/\d{2}/\d{2}$"),                        # 07/05/25
    re.compile(r"^\d{2}-\d{2}-\d{2}$"),                        # 07-05-25
    re.compile(r"^\d{2}/[A-Za-z]{3}/\d{2}$"),                  # 07/May/25
    re.compile(r"^\d{2}-[A-Za-z]{3}-\d{2}$"),                  # 07-May-25
]

# Indian-formatted (1,82,196.96) or plain (123.45) decimals.
AMOUNT_PATTERN = re.compile(r"^-?(?:\d{1,3}(?:,\d{2,3})+|\d+)(?:\.\d{1,2})?$")

# Trailing Cr / Dr suffix used by some banks (Allahabad uses "1000.00 CR").
AMOUNT_SUFFIX_PATTERN = re.compile(r"\s*(CR|DR|Cr|Dr|cr|dr)\s*$")

# Filler placeholder cells some banks emit between columns ("~", "--", "..").
FILLER_CELL_PATTERN = re.compile(r"^[~\-\._]+(\s+[~\-\._]+)*$")

# Honorifics used to spot account holder lines when no "Name:" label exists.
# Honorifics are case-insensitive (Mr./MR./mr./M/s/M/S all valid). The captured
# name body must be in uppercase — that's how every bank PDF I've seen renders
# the customer name. Stopping at the first non-uppercase token prevents
# capturing trailing labels like "YourBranchDetails:".
HONORIFIC_PATTERN = re.compile(
    r"\b(?:[Mm][Rr]|[Mm][Rr][Ss]|[Mm][Ss]|[Mm][Ii][Ss][Ss]|[Dd][Rr]|[Mm]/[Ss])\.?\s*"
    r"([A-Z][A-Z]{1,60}"                                # first body token: 2+ letters
    r"(?:[.'\-][A-Z]{1,60})*"                           # internal joiners stay literal
    r"(?:\s+[A-Z][A-Z]{1,60}(?:[.'\-][A-Z]{1,60})*){0,5})"  # up to 5 more tokens, same shape
)

# Account number: a contiguous run of 8+ digits.
ACCOUNT_NUMBER_PATTERN = re.compile(r"\b\d{8,}\b")


@dataclass
class Transaction:
    date: str
    description: str
    amount: float                    # signed: positive = credit, negative = debit
    balance: float | None = None
    raw: dict = field(default_factory=dict)  # original cells, for debugging


@dataclass
class ParseResult:
    source_pdf: str
    account_number: str | None
    account_name: str | None
    statement_period_start: str | None
    statement_period_end: str | None
    transactions: list[Transaction]
    warnings: list[str] = field(default_factory=list)


# ---------- Helpers ----------

def _clean_cell(value) -> str:
    """Normalise whitespace inside a cell. Wrapped lines become single spaces.
    Filler-only cells (e.g. ``~``, ``--``) are normalised to empty strings so
    they don't create phantom columns."""
    if value is None:
        return ""
    s = re.sub(r"\s+", " ", str(value)).strip()
    if not s:
        return ""
    if FILLER_CELL_PATTERN.match(s):
        return ""
    return s


def _strip_amount_suffix(cell: str) -> tuple[str, str | None]:
    """Strip a trailing CR/DR suffix from a cell. Returns (number_str, suffix)."""
    m = AMOUNT_SUFFIX_PATTERN.search(cell)
    if not m:
        return cell, None
    return cell[: m.start()].strip(), m.group(1).upper()


def _is_date(cell: str, *, allow_fuzzy: bool = False) -> bool:
    if not cell:
        return False
    if any(p.match(cell) for p in DATE_PATTERNS):
        return True
    if allow_fuzzy or _FUZZY_DATES_ENABLED:
        return _is_date_fuzzy(cell)
    return False


def _is_date_fuzzy(cell: str) -> bool:
    """Fallback date detection using dateutil.

    Conservative — many money strings parse as dates if you let dateutil run
    free (e.g. "5,000.00" becomes year 5000). We require:
      - between 6 and 25 characters
      - at least one date-like separator (/, -, space)
      - not a number-with-comma-grouping (Indian or US amount format)
      - not a plain ".XX" decimal
      - no time-of-day delimiter (": followed by digits") so we don't accept
        "03:56:39 PM" as a date
      - dateutil parses to a year between 1900 and 2099
    """
    if not _HAS_DATEUTIL:
        return False
    s = cell.strip()
    if not (6 <= len(s) <= 25):
        return False
    if not re.search(r"[/\-.\s]", s):
        return False
    # Reject time-of-day strings.
    if re.search(r":\d{2}", s):
        return False
    # Reject anything that looks like an amount.
    if re.search(r"\d,\d{2,3}", s):
        return False
    if re.fullmatch(r"-?\d+(\.\d+)?", s):
        return False
    # The cell must contain enough structure to be a real date — at least
    # one of: a 4-digit year, a 3-letter English month abbreviation, or
    # two date-separators between digits.
    has_year = bool(re.search(r"\b(19|20)\d{2}\b", s))
    has_month = bool(re.search(
        r"\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec|"
        r"January|February|March|April|June|July|August|September|"
        r"October|November|December)\b",
        s, re.IGNORECASE,
    ))
    has_two_separators = bool(
        re.search(r"\d+[/\-.]\d+[/\-.]\d+", s)
    )
    # Reject single-digit-year truncations like "07/May/2" or "11/Aug/2 25"
    # that result from PDF text-strategy column splits mid-cell.
    if re.search(r"[/\-]\s*\d\s*$", s):
        return False
    if not (has_year or has_month or has_two_separators):
        return False
    try:
        dt = _dateutil_parser.parse(s, dayfirst=True, fuzzy=False)
    except (ValueError, OverflowError, TypeError):
        return False
    return 1900 <= dt.year <= 2099


def _is_amount(cell: str) -> bool:
    if not cell:
        return False
    body, _ = _strip_amount_suffix(cell)
    cleaned = body.replace(" ", "")
    return bool(AMOUNT_PATTERN.match(cleaned))


def _parse_amount(cell: str) -> float | None:
    """Parse a money-looking cell to float. Returns None if not parseable.

    Handles Indian/US comma grouping, optional sign, and trailing CR/DR
    indicators. The CR/DR suffix is *not* applied to the sign here — the
    caller decides that, since some banks report balance with CR/DR but
    transaction amounts without."""
    if not cell:
        return None
    body, _ = _strip_amount_suffix(cell)
    cleaned = body.replace(",", "").replace(" ", "")
    try:
        return float(cleaned)
    except ValueError:
        return None


def _is_decimal_amount(cell: str) -> bool:
    """Strict: must contain a decimal point (e.g. money amounts like 1,234.56)."""
    if not cell:
        return False
    body, _ = _strip_amount_suffix(cell)
    return _is_amount(body) and "." in body


def _column_profile(rows: list[list[str]]) -> list[dict]:
    """
    For each column index, count what fraction of non-empty cells look like
    dates, amounts (any number), decimal amounts (money), or other text.
    """
    if not rows:
        return []
    width = max(len(r) for r in rows)
    profile = []
    for col in range(width):
        cells = [_clean_cell(r[col]) if col < len(r) else "" for r in rows]
        non_empty = [c for c in cells if c]
        n = max(len(non_empty), 1)
        date_count = sum(1 for c in non_empty if _is_date(c))
        amount_count = sum(1 for c in non_empty if _is_amount(c))
        decimal_count = sum(1 for c in non_empty if _is_decimal_amount(c))
        avg_len = (
            sum(len(c) for c in non_empty) / len(non_empty) if non_empty else 0
        )
        distinct = len(set(non_empty))
        profile.append({
            "index": col,
            "non_empty_ratio": len(non_empty) / max(len(cells), 1),
            "date_ratio": date_count / n,
            "amount_ratio": amount_count / n,
            "decimal_ratio": decimal_count / n,
            "avg_len": avg_len,
            "distinct_values": distinct,
            "samples": non_empty[:3],
        })
    return profile


def _identify_columns(profile: list[dict]) -> dict:
    """
    Map column indices to semantic roles using only data shape.

    Money columns require a decimal point (X.XX) so that integer-only columns
    like row numbers / serial numbers are not mistaken for amounts.

    Description = the highest-distinctness, longest-text column that is *not*
    holding dates or money — this prevents value-date or amount columns from
    being misidentified as the description.

    Returns a dict like:
        {
            "date": <int>,
            "description": <int>,
            "amount_columns": [<int>, ...],   # any decimal-bearing columns
            "balance": <int|None>,
        }
    """
    date_cols = [p for p in profile if p["date_ratio"] >= 0.6]
    amount_cols = [p for p in profile if p["decimal_ratio"] >= 0.6]
    used = set(p["index"] for p in date_cols) | set(p["index"] for p in amount_cols)
    text_cols = [p for p in profile if p["index"] not in used]

    # Pick the date column with the highest date ratio (or earliest index on tie).
    date_col = None
    if date_cols:
        date_cols.sort(key=lambda p: (-p["date_ratio"], p["index"]))
        date_col = date_cols[0]["index"]

    # Description = text column with longest avg length and high distinctness,
    # and a meaningful fill ratio so we don't pick a sparse footer column.
    description_col = None
    candidate_text = [
        p for p in text_cols
        if p["non_empty_ratio"] >= 0.3 and p["avg_len"] >= 3
    ]
    if candidate_text:
        candidate_text.sort(key=lambda p: (-p["avg_len"], -p["distinct_values"]))
        description_col = candidate_text[0]["index"]
    elif text_cols:
        text_cols.sort(key=lambda p: (-p["avg_len"], -p["distinct_values"]))
        description_col = text_cols[0]["index"]

    return {
        "date": date_col,
        "description": description_col,
        "amount_columns": [p["index"] for p in amount_cols],
        "balance": None,  # filled in once we have actual values to compare
    }


def _trim_to_table_body(rows: list[list[str]]) -> list[list[str]]:
    """
    A page returned by pdfplumber's text strategy often begins with header
    chrome (account name, address, summary tables) before the actual
    transaction table. Drop everything before the first row that contains a
    date in any cell, and everything after the last such row, so column
    profiling sees only the transaction body.

    A "continuation" row (no date but immediately follows a transaction row)
    stays in the body — we keep rows up to the last dated row.
    """
    first = None
    last = None
    for i, row in enumerate(rows):
        if any(_is_date(_clean_cell(c)) for c in row):
            if first is None:
                first = i
            last = i
    if first is None:
        return []
    return rows[first : last + 1]


def _detect_balance_column(
    rows: list[list[str]], amount_columns: list[int]
) -> int | None:
    """
    Pick the running-balance column by checking which money column's values
    form a monotonic chain — i.e. for most rows, balance[n] ≈ balance[n-1] ± a
    transaction amount in the same row.

    This works regardless of magnitude, so a 17-day statement where the
    balance happens to be larger than typical transaction amounts still
    classifies correctly.
    """
    if not amount_columns or len(rows) < 3:
        return None

    def _column_values(col: int) -> list[float | None]:
        out = []
        for r in rows:
            cell = _clean_cell(r[col]) if col < len(r) else ""
            out.append(_parse_amount(cell) if _is_decimal_amount(cell) else None)
        return out

    best_col = None
    best_score = -1.0
    for col in amount_columns:
        col_values = _column_values(col)
        # Density: fraction of rows with a parseable value in this column.
        non_null = [v for v in col_values if v is not None]
        density = len(non_null) / max(len(col_values), 1)

        # Continuity check: walk through consecutive non-null pairs in this
        # column and see how often the delta equals (within 1%) some other
        # money cell on the same later row.
        matches = 0
        comparisons = 0
        last_idx = None
        last_val = None
        for i, v in enumerate(col_values):
            if v is None:
                continue
            if last_val is not None:
                comparisons += 1
                delta = abs(v - last_val)
                # Look at every other money column on row i for a match.
                for other in amount_columns:
                    if other == col or other >= len(rows[i]):
                        continue
                    cell = _clean_cell(rows[i][other])
                    if not _is_decimal_amount(cell):
                        continue
                    other_val = _parse_amount(cell) or 0.0
                    tol = max(0.01, abs(other_val) * 0.01)
                    if abs(delta - abs(other_val)) <= tol:
                        matches += 1
                        break
            last_idx = i
            last_val = v

        continuity = matches / comparisons if comparisons else 0.0
        # Score weights continuity above density — a column that's slightly
        # less dense but consistently moves by the other column's amount is
        # the balance column.
        score = continuity * 2.0 + density
        if score > best_score:
            best_score = score
            best_col = col
    return best_col


def _merge_continuation_rows(
    rows: list[list[str]], date_col: int
) -> list[list[str]]:
    """
    A row whose date column is empty is a continuation of the previous row's
    wrapped cells. Merge it into the previous row by appending each non-empty
    cell with a space.
    """
    if date_col is None:
        return rows

    merged: list[list[str]] = []
    for r in rows:
        normalised = [_clean_cell(c) for c in r]
        if not _is_date(normalised[date_col] if date_col < len(normalised) else ""):
            if not merged:
                # Continuation before any anchor row — drop it.
                continue
            for i, cell in enumerate(normalised):
                if not cell:
                    continue
                if i >= len(merged[-1]):
                    merged[-1].extend([""] * (i - len(merged[-1]) + 1))
                merged[-1][i] = (
                    f"{merged[-1][i]} {cell}".strip() if merged[-1][i] else cell
                )
        else:
            merged.append(normalised)
    return merged


# ---------- Metadata extraction ----------

def _extract_account_info(pages_text: list[str]) -> tuple[str | None, str | None]:
    text = "\n".join(pages_text[:2])  # first couple of pages usually have it.

    account_number = None
    label_match = re.search(
        r"(?:A/C\s*No|Account\s*Number|Account\s*No|Customer\s*A/C\s*No|"
        r"Account)\.?\s*[:\-]?\s*(\d{8,})",
        text, re.IGNORECASE,
    )
    if label_match:
        account_number = label_match.group(1)
    else:
        m = ACCOUNT_NUMBER_PATTERN.search(text)
        if m:
            account_number = m.group(0)

    # Account name: try, in order:
    #   1. Explicit "Name:" / "Account Holder:" / "Customer Name:" labels
    #   2. Honorific-prefixed line near the top (MR./MRS./M/S. ...)
    #   3. First ALL-CAPS line on page 1 that doesn't look like an address
    account_name = None
    label_match = re.search(
        r"(?:Account\s*Holder|Customer\s*Name|Name)\s*[:\-]?\s*"
        r"([A-Z][A-Z0-9 .&'\-/]+?)(?:\s{2,}|\n|A/C|Address|$)",
        text,
    )
    if label_match:
        account_name = label_match.group(1).strip().rstrip(":").strip()

    if not account_name:
        m = HONORIFIC_PATTERN.search(text)
        if m:
            full = m.group(0).strip()
            account_name = re.sub(r"\s+", " ", full).rstrip(":").strip()

    if account_name:
        # Trim trailing punctuation/whitespace artefacts and stray words that
        # got captured by greedy matching.
        account_name = re.sub(r"[\s:,.]+$", "", account_name).strip()
    return account_number, account_name


_DATE_TOKEN = (
    r"(?:"
    # 01/05/2025, 01-05-25, 2025-05-01, 01/May/2025, 01-May-2025
    r"\d{1,4}[/\-][A-Za-z0-9]+[/\-]\d{2,4}"
    # May 01, 2026 / May 1 2026
    r"|[A-Za-z]+\s+\d{1,2},?\s*\d{4}"
    # December01,2017 (no spaces)
    r"|[A-Za-z]+\d{1,2},?\d{4}"
    # 01 May 2025
    r"|\d{1,2}\s+[A-Za-z]+\s+\d{4}"
    r")"
)

# Period sentinels — banks use a wide variety of phrasings.
# Each pattern has two capture groups: start date and end date. We try them
# in order; the first that matches wins.
_PERIOD_LABEL_PATTERNS = [
    re.compile(
        r"(?:Transaction\s*Period|Statement\s*Period|"
        r"for\s*the\s*period|Period\s*From|Statement\s*of\s*Account\s*from|"
        r"\bPeriod\b)"
        r"\s*[:\-]?\s*(?:From\s+)?"
        + r"(" + _DATE_TOKEN + r")"
        + r"\s*(?:To|to|TO|–|—|-)\s*"
        + r"(" + _DATE_TOKEN + r")",
        re.IGNORECASE,
    ),
    # Bare "from <date> to <date>" — last fallback.
    re.compile(
        r"\bfrom\s+(" + _DATE_TOKEN + r")\s+to\s+(" + _DATE_TOKEN + r")",
        re.IGNORECASE,
    ),
]


def _extract_period(
    pages_text: list[str], transactions: list[Transaction]
) -> tuple[str | None, str | None]:
    text = "\n".join(pages_text[:2])
    for pattern in _PERIOD_LABEL_PATTERNS:
        m = pattern.search(text)
        if m:
            start = m.group(1).strip().rstrip(",")
            end = m.group(2).strip().rstrip(",")
            if start and end:
                return start, end

    if transactions:
        return transactions[0].date, transactions[-1].date
    return None, None


# ---------- Core pipeline ----------

def _score_table_set(tables: list[list[list[str]]]) -> int:
    """Score a list of tables by how many rows contain a date cell anywhere.
    Higher is better — used to pick the best extraction strategy per page."""
    score = 0
    for t in tables:
        for row in t:
            cells = [_clean_cell(c) for c in row]
            if any(_is_date(c) for c in cells):
                score += 1
    return score


def _extract_tables_per_page(pdf: pdfplumber.PDF) -> list[list[list[list[str]]]]:
    """
    Return one entry per page. Each entry is the list of tables found by
    whichever extraction strategy yielded the most date-bearing rows for
    that page.

    PDFs vary: some have ruling lines (best handled by the 'lines' strategy),
    some have only whitespace alignment (best handled by 'text'). We try all
    of them and keep the winner per page so column shapes stay consistent
    within each page.
    """
    strategies = [
        {},  # auto
        {"vertical_strategy": "lines", "horizontal_strategy": "lines"},
        {"vertical_strategy": "text",  "horizontal_strategy": "text"},
        {"vertical_strategy": "lines", "horizontal_strategy": "text"},
    ]

    per_page: list[list[list[list[str]]]] = []
    for page in pdf.pages:
        best_tables: list[list[list[str]]] = []
        best_score = -1
        for settings in strategies:
            try:
                tables = (
                    page.extract_tables(table_settings=settings)
                    if settings else page.extract_tables()
                )
            except Exception:
                continue
            score = _score_table_set(tables)
            if score > best_score:
                best_score = score
                best_tables = tables
        per_page.append(best_tables)
    return per_page


def _select_transaction_table_rows(
    tables: list[list[list[str]]],
) -> list[list[str]]:
    """
    Stitch together rows from every table that looks like a transaction table.
    A transaction table is one whose rows mostly contain a date in some column.

    Rows where every cell is empty are dropped — they're the gaps pdfplumber
    inserts between word rows when using the text strategy.
    """
    transaction_rows: list[list[str]] = []
    for table in tables:
        if not table:
            continue
        date_rows = 0
        for row in table:
            cells = [_clean_cell(c) for c in row]
            if any(_is_date(c) for c in cells):
                date_rows += 1
        if not table or date_rows / len(table) < 0.1:
            continue  # not a transaction table

        # Drop the header row if present (no dates, plenty of text).
        first = [_clean_cell(c) for c in table[0]]
        if not any(_is_date(c) for c in first) and any(first):
            data_rows = table[1:]
        else:
            data_rows = table

        for row in data_rows:
            cleaned = [_clean_cell(c) for c in row]
            if any(cleaned):
                transaction_rows.append(cleaned)
    return transaction_rows


def _classify_debit_credit(
    rows: list[list[str]],
    tx_amount_cols: list[int],
    balance_col: int | None,
) -> dict[int, str]:
    """
    For each transaction-amount column, decide whether it represents debit or
    credit by checking how its values correlate with the running balance:

      - A value in the **debit** column → balance goes DOWN
      - A value in the **credit** column → balance goes UP

    We use the absolute value of cell amounts so that pre-signed columns
    (where debits are written as negative numbers) don't confuse the math.

    Returns a dict mapping column index → "debit", "credit", or "signed"
    when both directions hit roughly equally (suggests a single signed
    column; the value's sign is the source of truth).

    When no balance column is available, falls back to:
      - one tx column → "signed" (preserve cell sign / suffix as source of truth)
      - two tx columns → leftmost = "debit", rightmost = "credit"
        (matches the dominant convention in Indian and US bank statements;
        emits a warning at the build layer when balance can't confirm).
    """
    classification: dict[int, str] = {}
    if len(tx_amount_cols) == 0:
        return {}

    if balance_col is None:
        if len(tx_amount_cols) == 1:
            classification[tx_amount_cols[0]] = "signed"
        elif len(tx_amount_cols) == 2:
            classification[tx_amount_cols[0]] = "debit"
            classification[tx_amount_cols[1]] = "credit"
        else:
            for c in tx_amount_cols:
                classification[c] = "unknown"
        return classification

    prev_balance: float | None = None
    debit_hits = {c: 0 for c in tx_amount_cols}
    credit_hits = {c: 0 for c in tx_amount_cols}
    samples = {c: 0 for c in tx_amount_cols}

    for r in rows:
        bal_cell = _clean_cell(r[balance_col]) if balance_col < len(r) else ""
        bal_val = _parse_amount(bal_cell) if _is_decimal_amount(bal_cell) else None
        if bal_val is None:
            continue
        if prev_balance is not None:
            delta = bal_val - prev_balance
            for c in tx_amount_cols:
                cell = _clean_cell(r[c]) if c < len(r) else ""
                if not _is_decimal_amount(cell):
                    continue
                v = _parse_amount(cell)
                if v is None or v == 0:
                    continue
                samples[c] += 1
                magnitude = abs(v)
                tol = max(0.01, magnitude * 0.01)
                if abs(delta + magnitude) <= tol:
                    debit_hits[c] += 1
                elif abs(delta - magnitude) <= tol:
                    credit_hits[c] += 1
        prev_balance = bal_val

    for c in tx_amount_cols:
        if samples[c] == 0:
            classification[c] = "unknown"
            continue
        # If a single column produces *both* debit and credit hits with
        # roughly comparable counts, it's a single signed column. The cell's
        # sign is then the source of truth (we'll preserve it in build).
        if (
            len(tx_amount_cols) == 1
            and debit_hits[c] > 0
            and credit_hits[c] > 0
        ):
            classification[c] = "signed"
        elif debit_hits[c] >= credit_hits[c] and debit_hits[c] > 0:
            classification[c] = "debit"
        elif credit_hits[c] > 0:
            classification[c] = "credit"
        else:
            classification[c] = "unknown"

    return classification


def _build_transactions(
    rows: list[list[str]], columns: dict, prev_balance: float | None = None
) -> list[Transaction]:
    transactions: list[Transaction] = []
    date_col = columns["date"]
    description_col = columns["description"]
    amount_columns = columns["amount_columns"]
    balance_col = columns.get("balance")
    tx_classification: dict[int, str] = columns.get("amount_classification", {})

    # Transaction-amount columns = amount columns excluding balance.
    tx_amount_cols = [c for c in amount_columns if c != balance_col]

    debit_cols = [c for c in tx_amount_cols if tx_classification.get(c) == "debit"]
    credit_cols = [c for c in tx_amount_cols if tx_classification.get(c) == "credit"]
    signed_cols = [c for c in tx_amount_cols if tx_classification.get(c) == "signed"]

    for r in rows:
        date = r[date_col] if date_col is not None and date_col < len(r) else ""
        if not _is_date(date):
            continue
        description = (
            r[description_col]
            if description_col is not None and description_col < len(r)
            else ""
        )

        # Read each transaction-amount column. We track the signed value so
        # that pre-signed columns (negative numbers in the cell) and
        # Dr/Cr-suffix columns are handled without losing the sign.
        signed_amount: float | None = None

        # 1) Signed single-column case — sign comes from the cell itself
        # (either a leading minus or a trailing Dr/Cr suffix).
        for c in signed_cols:
            cell = _clean_cell(r[c]) if c < len(r) else ""
            v = _parse_amount(cell) if _is_decimal_amount(cell) else None
            if v is None or v == 0:
                continue
            _, suffix = _strip_amount_suffix(cell)
            if suffix == "DR":
                contribution = -abs(v)
            elif suffix == "CR":
                contribution = abs(v)
            else:
                contribution = v  # already signed by the cell's sign
            signed_amount = (
                contribution if signed_amount is None else signed_amount + contribution
            )
        if signed_amount is not None:
            pass  # keep going to also check classified columns

        # 2) Debit + credit classified columns. Detect a Dr/Cr suffix per cell;
        # an explicit Cr beats classification, an explicit Dr beats it too.
        debit_value = 0.0
        credit_value = 0.0
        for c in debit_cols + credit_cols:
            cell = _clean_cell(r[c]) if c < len(r) else ""
            if not _is_decimal_amount(cell):
                continue
            v = _parse_amount(cell)
            if v is None or v == 0:
                continue
            magnitude = abs(v)
            _, suffix = _strip_amount_suffix(cell)
            if suffix == "CR":
                credit_value += magnitude
            elif suffix == "DR":
                debit_value += magnitude
            elif c in debit_cols:
                debit_value += magnitude
            elif c in credit_cols:
                credit_value += magnitude

        if debit_value > 0 or credit_value > 0:
            classified = credit_value - debit_value
            if signed_amount is None:
                signed_amount = classified
            else:
                signed_amount += classified

        balance_value: float | None = None
        if balance_col is not None and balance_col < len(r):
            balance_cell = _clean_cell(r[balance_col])
            if _is_decimal_amount(balance_cell):
                balance_value = _parse_amount(balance_cell)

        # 3) Fallback for unknown classification: pick first non-zero amount,
        # preserve its sign (from the cell or from a Dr/Cr suffix), or infer
        # from balance delta if neither is present.
        if signed_amount is None:
            for c in tx_amount_cols:
                cell = _clean_cell(r[c]) if c < len(r) else ""
                v = _parse_amount(cell) if _is_decimal_amount(cell) else None
                if v is None or v == 0:
                    continue
                _, suffix = _strip_amount_suffix(cell)
                if suffix == "CR":
                    signed_amount = abs(v)
                elif suffix == "DR":
                    signed_amount = -abs(v)
                elif v < 0:
                    signed_amount = v  # already signed
                elif (
                    balance_value is not None
                    and prev_balance is not None
                ):
                    delta = balance_value - prev_balance
                    signed_amount = -abs(v) if delta < 0 else abs(v)
                else:
                    signed_amount = abs(v)  # unsigned; warn elsewhere
                break

        if signed_amount is None:
            signed_amount = 0.0

        transactions.append(Transaction(
            date=date,
            description=description,
            amount=signed_amount,
            balance=balance_value,
            raw={"row": r},
        ))
        if balance_value is not None:
            prev_balance = balance_value
    return transactions


def _parse_page(rows: list[list[str]], prev_balance: float | None) -> tuple[list[Transaction], float | None, list[str]]:
    """
    Parse a single page's transaction rows. Each page is profiled independently
    because different pages of the same PDF can have different column counts
    (e.g., a page with an address header has more columns than a clean
    transactions-only page).

    Returns the transactions, the running balance after the last transaction,
    and any warnings emitted while processing this page.
    """
    warnings: list[str] = []
    if not rows:
        return [], prev_balance, warnings

    body = _trim_to_table_body(rows)
    if not body:
        return [], prev_balance, warnings

    profile = _column_profile(body)
    columns = _identify_columns(profile)

    if columns["date"] is None:
        warnings.append("Page has no identifiable date column; skipping")
        return [], prev_balance, warnings

    merged = _merge_continuation_rows(body, columns["date"])
    columns["balance"] = _detect_balance_column(merged, columns["amount_columns"])

    # Classify each transaction-amount column as debit or credit using how its
    # values correlate with the balance delta. This replaces "leftmost = debit".
    tx_amount_cols = [
        c for c in columns["amount_columns"] if c != columns["balance"]
    ]
    columns["amount_classification"] = _classify_debit_credit(
        merged, tx_amount_cols, columns["balance"]
    )

    transactions = _build_transactions(merged, columns, prev_balance)

    last_balance = prev_balance
    for t in transactions:
        if t.balance is not None:
            last_balance = t.balance
    return transactions, last_balance, warnings


def _parse_with_flag(pdf_path: Path) -> tuple[list[Transaction], list[str], list[str]]:
    """Run the table-extract + per-page parse pipeline with whatever
    `_FUZZY_DATES_ENABLED` is currently set to. Returns transactions,
    warnings, and a list of per-page text strings (for metadata extraction).
    """
    pages_text: list[str] = []
    with pdfplumber.open(pdf_path) as pdf:
        pages_text = [p.extract_text() or "" for p in pdf.pages]
        per_page_tables = _extract_tables_per_page(pdf)

    all_transactions: list[Transaction] = []
    all_warnings: list[str] = []
    running_balance: float | None = None

    for page_idx, page_tables in enumerate(per_page_tables):
        rows = _select_transaction_table_rows(page_tables)
        if not rows:
            continue
        page_txns, running_balance, page_warnings = _parse_page(rows, running_balance)
        all_transactions.extend(page_txns)
        for w in page_warnings:
            all_warnings.append(f"page {page_idx + 1}: {w}")

    return all_transactions, all_warnings, pages_text


def parse(pdf_path: Path) -> ParseResult:
    """Parse a bank statement PDF.

    Two-pass strategy:
      1. Try strict regex-only date detection. Most digital bank statements
         match this and we keep the strictest possible cell filtering.
      2. If pass 1 produces zero transactions, retry with the dateutil
         fuzzy fallback enabled. This catches statements with date formats
         outside the strict regex list (e.g. "Apr 30, 2025", "30.04.2025")
         without weakening detection on PDFs that already work.
    """
    global _FUZZY_DATES_ENABLED

    _FUZZY_DATES_ENABLED = False
    transactions, warnings, pages_text = _parse_with_flag(pdf_path)

    if not transactions and _HAS_DATEUTIL:
        _FUZZY_DATES_ENABLED = True
        try:
            transactions, warnings, pages_text = _parse_with_flag(pdf_path)
        finally:
            _FUZZY_DATES_ENABLED = False
        if transactions:
            warnings.insert(0, "date column detected via fuzzy fallback")

    if not transactions:
        warnings.append("No transactions parsed from any page")

    account_number, account_name = _extract_account_info(pages_text)
    period_start, period_end = _extract_period(pages_text, transactions)

    return ParseResult(
        source_pdf=str(pdf_path),
        account_number=account_number,
        account_name=account_name,
        statement_period_start=period_start,
        statement_period_end=period_end,
        transactions=transactions,
        warnings=warnings,
    )


# ---------- CLI ----------

def _write_outputs(result: ParseResult, pdf_path: Path) -> tuple[Path, Path]:
    base = pdf_path.with_suffix("")
    json_path = Path(f"{base}.parsed.json")
    csv_path = Path(f"{base}.parsed.csv")

    json_payload = {
        "source_pdf": result.source_pdf,
        "account_number": result.account_number,
        "account_name": result.account_name,
        "statement_period": {
            "start": result.statement_period_start,
            "end": result.statement_period_end,
        },
        "warnings": result.warnings,
        "transactions": [
            {
                "date": t.date,
                "description": t.description,
                "amount": t.amount,
                "balance": t.balance,
            }
            for t in result.transactions
        ],
    }
    json_path.write_text(json.dumps(json_payload, indent=2))

    with csv_path.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["date", "description", "amount", "balance"])
        for t in result.transactions:
            writer.writerow([t.date, t.description, t.amount, t.balance])

    return json_path, csv_path


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        default = os.path.expanduser("~/Downloads/sample_statements/yes1_azf99.pdf")
        print(f"No path given, using default: {default}")
        pdf_path = Path(default)
    else:
        pdf_path = Path(os.path.expanduser(argv[1]))

    if not pdf_path.exists():
        print(f"File not found: {pdf_path}", file=sys.stderr)
        return 1

    result = parse(pdf_path)

    print(f"\nSource: {result.source_pdf}")
    print(f"Account number : {result.account_number}")
    print(f"Account name   : {result.account_name}")
    print(
        f"Period         : {result.statement_period_start} -> "
        f"{result.statement_period_end}"
    )
    print(f"Transactions   : {len(result.transactions)}")
    if result.warnings:
        print("Warnings:")
        for w in result.warnings:
            print(f"  - {w}")

    if result.transactions:
        print("\nFirst 5 transactions:")
        for t in result.transactions[:5]:
            print(f"  {t.date}  {t.amount:>14,.2f}  bal={t.balance}  {t.description[:60]}")
        print("...")
        print("Last 5 transactions:")
        for t in result.transactions[-5:]:
            print(f"  {t.date}  {t.amount:>14,.2f}  bal={t.balance}  {t.description[:60]}")

    json_path, csv_path = _write_outputs(result, pdf_path)
    print(f"\nWrote: {json_path}")
    print(f"Wrote: {csv_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
