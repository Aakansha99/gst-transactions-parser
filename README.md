# GST Statement Processor

A browser-based tool for extracting and viewing transactions from bank statement PDFs. Upload a statement, the FastAPI backend in `api/` parses it, and the React frontend shows the transactions grouped by account with search and assignee filtering.

Built with [React 18](https://react.dev/), [TypeScript](https://www.typescriptlang.org/), [Vite](https://vite.dev/), and a [FastAPI](https://fastapi.tiangolo.com/) parsing service backed by [pdfplumber](https://github.com/jsvine/pdfplumber).

## Features

- Server-side PDF parsing with pdfplumber — handles multi-bank layouts (ICICI, HDFC, Allahabad, YES Bank, etc.)
- Files are uploaded to the parser, processed in memory, and not stored on disk
- Extracts statement period and transactions grouped by account
- Search transactions by name or description
- Assignee mappings stored in `localStorage`
- Routing between upload and processing views via `react-router-dom`

> Privacy note: previous versions parsed PDFs entirely client-side. The current version uploads the PDF to a parsing service. If client-side parsing is a hard requirement for your deployment, run the API locally and proxy through the Vite dev server (the default).

## Prerequisites

- [Node.js](https://nodejs.org/) 18 or later
- npm 9+ (bundled with Node.js)

Check your versions:

```bash
node --version
npm --version
```

## Getting Started

You need to run **two processes** during development: the FastAPI backend (port 8000) and the Vite dev server (port 5173). The Vite server proxies `/api/*` to the backend.

1. Install frontend dependencies:

   ```bash
   npm install
   ```

2. Set up the backend (one-time):

   ```bash
   cd api
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   cd ..
   ```

3. Start the backend in one terminal:

   ```bash
   cd api
   source .venv/bin/activate
   uvicorn app.main:app --reload --port 8000
   ```

4. Start the frontend in another terminal:

   ```bash
   npm run dev
   ```

5. Open the URL printed by Vite (usually http://localhost:5173).

## Available Scripts

| Command | Description |
|---|---|
| `npm run dev` | Start the Vite dev server with HMR. |
| `npm run build` | Type-check with `tsc -b` and build for production into `dist/`. |
| `npm run preview` | Preview the production build locally. |
| `npm run lint` | Run ESLint across the project. |
| `npm test` | Run the Vitest test suite once (non-watch). |

## Project Structure

```
.
├── api/                          # FastAPI parsing service
│   ├── app/
│   │   ├── main.py               # FastAPI app, CORS, routes
│   │   ├── parser_adapter.py     # ParseResult → UI JSON shape
│   │   └── parser/               # vendored copy of scripts/parse_statement.py
│   ├── tests/
│   ├── requirements.txt
│   └── README.md
├── scripts/                      # Python parser & coverage matrix
│   ├── parse_statement.py        # the parser (also vendored under api/)
│   ├── make_synthetic_fixtures.py
│   ├── verify_synthetic.py
│   ├── regression_run.py
│   └── verify_parsed.py
├── tests/fixtures/               # PDFs used by both parser and API tests
└── src/                          # React frontend
    ├── App.tsx                   # Router + context provider
    ├── main.tsx                  # React entry point
    ├── context/
    │   └── ParseResultContext.tsx
    ├── pages/
    │   ├── UploadPage.tsx        # POSTs PDF to /api/parse
    │   └── ProcessingPage.tsx    # Transaction view with filters
    ├── utils/
    │   ├── parseStatementApi.ts  # client for the FastAPI backend
    │   ├── filterTransactionGroups.ts
    │   ├── AssigneeDatabase.ts
    │   └── validateExtension.ts
    └── types.ts                  # Shared TypeScript types
```

## Usage

1. From the upload page, select a `.pdf` bank statement.
2. The app validates the file, extracts text with PDF.js, and parses transactions.
3. You're redirected to the processing page where you can search transactions and filter by assignee.
4. Use the back link to upload another statement.

## Testing

Tests use [Vitest](https://vitest.dev/) with [@testing-library/react](https://testing-library.com/docs/react-testing-library/intro/) and a `jsdom` environment. Setup lives in `src/setupTests.ts`.

Run the full suite:

```bash
npm test
```

## Deployment

The project builds to static assets in `dist/`, so any static host works. Build and preview locally:

```bash
npm run build
npm run preview
```

### Deploying to Vercel

This project is deployed on Vercel with a GitHub integration — every push to the connected branch triggers an automatic deploy.

**How it was set up:**

1. Logged into [Vercel](https://vercel.com/) and created a new project from the dashboard.
2. Connected the GitHub repository. Vercel auto-detected Vite and used the default build settings (`npm run build` → `dist/`).
3. Added `vercel.json` to the repo so client-side routing works correctly:

   ```json
   {
     "rewrites": [
       { "source": "/(.*)", "destination": "/" }
     ]
   }
   ```

   This rewrites every path to `/` so `react-router-dom` handles the route on the client. Without it, refreshing on `/processing` or sharing a deep link would return a 404 from Vercel's static host.

That's the only project-side change needed — no other config, no env vars. Push to the connected branch and Vercel takes over the build and deploy.

## Tech Stack

- React 18 + React Router 7
- TypeScript 5.6
- Vite 5
- pdfjs-dist 5
- Vitest + Testing Library + fast-check
- ESLint 9 with `typescript-eslint` and React hooks plugins
