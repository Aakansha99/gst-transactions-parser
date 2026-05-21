"""FastAPI app exposing parse_statement as an HTTP API for the React UI.

Routes:
  GET  /api/health      → readiness probe
  POST /api/parse       → multipart upload of a PDF, returns parsed JSON

Runtime constraints:
  - 10 MB file size cap (bank statements are usually <2 MB)
  - PDF only — content-type and extension are both checked
  - In-memory processing; nothing is written to disk
"""

from __future__ import annotations

import logging
import tempfile
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .parser import parse
from .parser_adapter import to_ui_payload


MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10 MB
ALLOWED_CONTENT_TYPES = {"application/pdf", "application/x-pdf"}

logger = logging.getLogger("gst-statement-api")
logging.basicConfig(level=logging.INFO)

app = FastAPI(
    title="GST Statement API",
    description="Parses bank statement PDFs into structured JSON.",
    version="0.1.0",
)


@app.on_event("startup")
async def _log_startup() -> None:
    logger.info("gst-statement-api startup — exception handler active")

# Allow the Vite dev server (default 5173) to call the API directly during
# development. In production you'd typically front the API and the static
# site behind the same origin, in which case CORS becomes irrelevant.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:4173",  # vite preview
        "http://127.0.0.1:5173",
    ],
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
    allow_credentials=False,
)


# Always return errors as JSON so the frontend never gets an HTML
# traceback page (which would surface as the generic
# "Server returned 500 with a non-JSON body" message).
@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled error in %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={
            "error": f"Internal error: {type(exc).__name__}: {exc}",
        },
    )


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/parse")
async def parse_statement_endpoint(file: UploadFile = File(...)):
    logger.info(
        "POST /api/parse filename=%r content_type=%r",
        file.filename, file.content_type,
    )
    # 1. Validate content type and extension.
    content_type = (file.content_type or "").lower()
    filename = (file.filename or "").lower()
    if content_type not in ALLOWED_CONTENT_TYPES and not filename.endswith(".pdf"):
        return JSONResponse(
            status_code=400,
            content={"error": "Only PDF files are accepted."},
        )

    # 2. Read with a size cap. Stream the upload so we don't load
    #    arbitrarily-large bodies.
    body_chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await file.read(64 * 1024)
        if not chunk:
            break
        total += len(chunk)
        if total > MAX_UPLOAD_BYTES:
            return JSONResponse(
                status_code=413,
                content={
                    "error": (
                        f"File too large ({total} bytes). "
                        f"Limit is {MAX_UPLOAD_BYTES} bytes."
                    )
                },
            )
        body_chunks.append(chunk)
    body = b"".join(body_chunks)

    if not body:
        return JSONResponse(
            status_code=400,
            content={"error": "Uploaded file is empty."},
        )

    # 3. parse_statement.parse() takes a file path, so write the bytes to a
    #    NamedTemporaryFile. The file is deleted as soon as we exit the
    #    context manager, so nothing persists past the request.
    try:
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=True) as tmp:
            tmp.write(body)
            tmp.flush()
            result = parse(Path(tmp.name))
    except Exception as exc:
        logger.exception("Failed to parse uploaded PDF")
        return JSONResponse(
            status_code=500,
            content={"error": f"Failed to parse PDF: {exc}"},
        )

    payload = to_ui_payload(result)

    if not payload["transactionGroups"][0]["transactions"]:
        # Parser ran but extracted nothing. Tell the user explicitly so the
        # UI can surface a useful error instead of an empty table.
        return JSONResponse(
            status_code=422,
            content={
                "error": "No transactions found in the uploaded PDF.",
                "warnings": payload["warnings"],
            },
        )

    return payload
