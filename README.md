# GST Statement Processor

A browser-based tool for extracting and viewing transactions from bank statement PDFs. Upload a statement, the app parses it client-side with [pdfjs-dist](https://github.com/mozilla/pdf.js), and shows the transactions grouped by account with search and assignee filtering.

Built with [React 18](https://react.dev/), [TypeScript](https://www.typescriptlang.org/), and [Vite](https://vite.dev/).

## Features

- Client-side PDF parsing — no files leave your browser
- Extracts statement period and transactions grouped by account
- Search transactions by name or description
- Assignee mappings stored in `localStorage`
- Routing between upload and processing views via `react-router-dom`

## Prerequisites

- [Node.js](https://nodejs.org/) 18 or later
- npm 9+ (bundled with Node.js)

Check your versions:

```bash
node --version
npm --version
```

## Getting Started

1. Clone the repository and install dependencies:

   ```bash
   npm install
   ```

2. Start the dev server:

   ```bash
   npm run dev
   ```

3. Open the URL printed in the terminal (usually http://localhost:5173).

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
src/
├── App.tsx                  # Router + context provider
├── main.tsx                 # React entry point
├── context/
│   └── ParseResultContext.tsx   # Shares parse results between pages
├── pages/
│   ├── UploadPage.tsx       # PDF upload + client-side parsing
│   └── ProcessingPage.tsx   # Transaction view with filters
├── utils/
│   ├── parseBankStatement.ts
│   ├── validateBankStatement.ts
│   ├── validateExtension.ts
│   ├── filterTransactionGroups.ts
│   ├── AssigneeDatabase.ts
│   └── prettyPrintTransactions.ts
└── types.ts                 # Shared TypeScript types
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
