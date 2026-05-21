import type { ParseResult } from '../types';

/**
 * Server-side parsing payload, including any non-fatal warnings from the
 * parser.
 */
export interface ParseApiResponse extends ParseResult {
  warnings?: string[];
}

/** Error thrown when the API rejects or fails to parse a PDF. */
export class ParseApiError extends Error {
  status: number;
  warnings?: string[];

  constructor(message: string, status: number, warnings?: string[]) {
    super(message);
    this.name = 'ParseApiError';
    this.status = status;
    this.warnings = warnings;
  }
}

/**
 * Upload a PDF to the backend `POST /api/parse` endpoint and return the
 * parsed statement.
 */
export async function parseStatementViaApi(file: File): Promise<ParseApiResponse> {
  const formData = new FormData();
  formData.append('file', file, file.name);

  // In production, use the Railway-deployed backend. In dev, the Vite proxy
  // forwards /api/* to localhost:8000.
  const baseUrl = import.meta.env.VITE_API_URL || '';
  const url = `${baseUrl}/api/parse`;

  let response: Response;
  try {
    response = await fetch(url, {
      method: 'POST',
      body: formData,
    });
  } catch (err) {
    // Network-level failure (server down, offline, CORS misconfig, etc.).
    throw new ParseApiError(
      'Could not reach the parsing service. Is the backend running on port 8000?',
      0,
    );
  }

  let body: unknown;
  try {
    body = await response.json();
  } catch {
    throw new ParseApiError(
      `Server returned ${response.status} with a non-JSON body.`,
      response.status,
    );
  }

  if (!response.ok) {
    const errBody = body as { error?: string; warnings?: string[] };
    throw new ParseApiError(
      errBody.error || `Server error (${response.status})`,
      response.status,
      errBody.warnings,
    );
  }

  return body as ParseApiResponse;
}
