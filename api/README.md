# gst-statement-api

FastAPI backend that wraps the `parse_statement.py` parser as an HTTP API
for the React UI to consume.

This lives under `api/` inside the same repository as the frontend, but it's
a self-contained Python project with its own `requirements.txt` and venv.

## Why this exists

The UI used to parse PDFs entirely client-side with `pdfjs-dist`. The Python
parser (in `../scripts/parse_statement.py`) is more robust — it handles
dual debit/credit columns, `CR`/`DR` suffixes, fuzzy date formats, and is
tested against a 22-fixture coverage matrix. This service exposes that
parser to the React frontend.

> Privacy note: PDFs are uploaded to this server for parsing. Files are
> processed in memory and not persisted to disk.

## Endpoints

### `POST /api/parse`

Accept: `multipart/form-data` with one field `file` containing a PDF.

Response: JSON in the shape the React UI consumes
(`ParseResult` from `../src/types.ts`):

```json
{
  "statementPeriod": { "startDate": "01/04/2025", "endDate": "30/06/2025" },
  "transactionGroups": [
    {
      "account": { "accountNumber": "987654321012", "accountName": "MR. SAMPLE CUSTOMER" },
      "transactions": [
        { "date": "02/04/2025", "description": "UPI/AMAZON/...", "amount": -1499 }
      ]
    }
  ],
  "warnings": []
}
```

Error response (HTTP 400/422/500):

```json
{ "error": "human-readable message" }
```

### `GET /api/health`

Returns `{ "status": "ok" }`. Used for readiness checks.

## Running locally

```bash
cd api
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

The Vite dev server is configured to proxy `/api/*` to
`http://localhost:8000` so the frontend can call the API on a relative URL.

## Project structure

```
api/
├── app/
│   ├── __init__.py
│   ├── main.py              # FastAPI app + CORS + routes
│   ├── parser_adapter.py    # converts ParseResult → UI schema
│   └── parser/              # copy of parse_statement.py for reuse
│       ├── __init__.py
│       └── parse_statement.py
├── tests/
│   └── test_api.py
├── requirements.txt
└── README.md
```
