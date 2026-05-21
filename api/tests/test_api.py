"""End-to-end tests for the API.

Run with: pytest api/tests/  (from the api/ directory)
"""

from __future__ import annotations

import io
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app


REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_PATH = REPO_ROOT / "tests" / "fixtures" / "sample_bank_statement.pdf"


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def test_health(client: TestClient) -> None:
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_parse_rejects_empty_upload(client: TestClient) -> None:
    response = client.post(
        "/api/parse",
        files={"file": ("empty.pdf", b"", "application/pdf")},
    )
    assert response.status_code == 400
    assert "empty" in response.json()["error"].lower()


def test_parse_rejects_non_pdf(client: TestClient) -> None:
    response = client.post(
        "/api/parse",
        files={"file": ("data.txt", b"hello", "text/plain")},
    )
    assert response.status_code == 400
    assert "pdf" in response.json()["error"].lower()


def test_parse_returns_ui_shape(client: TestClient) -> None:
    if not FIXTURE_PATH.exists():
        pytest.skip(f"Fixture {FIXTURE_PATH} not available")

    with FIXTURE_PATH.open("rb") as fh:
        response = client.post(
            "/api/parse",
            files={"file": (FIXTURE_PATH.name, fh, "application/pdf")},
        )
    assert response.status_code == 200, response.text
    payload = response.json()

    # Schema check.
    assert "statementPeriod" in payload
    assert "transactionGroups" in payload
    assert isinstance(payload["transactionGroups"], list) and payload["transactionGroups"]
    group = payload["transactionGroups"][0]
    assert {"accountNumber", "accountName"} <= set(group["account"].keys())
    assert isinstance(group["transactions"], list)
    assert all(
        {"date", "description", "amount"} <= set(t.keys()) for t in group["transactions"]
    )

    # Spot-check the known fixture: it has 33 transactions with closing
    # balance 77080.05.
    txns = group["transactions"]
    assert len(txns) == 33
    last_with_balance = next(
        (t for t in reversed(txns) if t.get("balance") is not None), None
    )
    assert last_with_balance is not None
    assert abs(last_with_balance["balance"] - 77080.05) < 0.01
