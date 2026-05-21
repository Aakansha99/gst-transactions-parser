import { useState, useRef, type ChangeEvent } from 'react';
import { useNavigate } from 'react-router-dom';
import { validateExtension } from '../utils/validateExtension';
import { useParseResult } from '../context/ParseResultContext';
import { parseStatementViaApi, ParseApiError } from '../utils/parseStatementApi';

export default function UploadPage() {
  const [error, setError] = useState<string | null>(null);
  const [warnings, setWarnings] = useState<string[]>([]);
  const [isProcessing, setIsProcessing] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const navigate = useNavigate();
  const { setParseResult } = useParseResult();

  function resetFileInput() {
    if (fileInputRef.current) fileInputRef.current.value = '';
  }

  async function handleFileChange(event: ChangeEvent<HTMLInputElement>) {
    setError(null);
    setWarnings([]);
    const file = event.target.files?.[0];
    if (!file) return;

    if (!validateExtension(file.name)) {
      setError('Only PDF files are accepted. Please select a .pdf file.');
      resetFileInput();
      return;
    }

    setIsProcessing(true);

    try {
      const result = await parseStatementViaApi(file);
      setParseResult(result);
      if (result.warnings && result.warnings.length > 0) {
        setWarnings(result.warnings);
      }
      navigate('/processing');
    } catch (err) {
      const apiErr = err as ParseApiError;
      setError(apiErr.message || 'An unexpected error occurred while processing the PDF.');
      if (apiErr.warnings && apiErr.warnings.length > 0) {
        setWarnings(apiErr.warnings);
      }
      resetFileInput();
    } finally {
      setIsProcessing(false);
    }
  }

  return (
    <div className="upload-page">
      <h1>GST Statement Processor</h1>
      <p>Upload a bank statement PDF to extract and view transactions.</p>
      <p style={{ fontSize: '0.85rem', color: '#888' }}>
        PDFs are sent to the parsing service. Files are processed in memory and not stored.
      </p>

      <div className="upload-dropzone">
        <input
          ref={fileInputRef}
          type="file"
          accept=".pdf"
          onChange={handleFileChange}
          disabled={isProcessing}
          aria-label="Upload bank statement PDF"
        />
      </div>

      {isProcessing && <p className="processing-indicator">Processing PDF...</p>}

      {error && (
        <div className="error-message" role="alert">
          {error}
        </div>
      )}

      {warnings.length > 0 && (
        <div className="warning-message" role="status" style={{ color: '#a06000' }}>
          <strong>Notes from the parser:</strong>
          <ul style={{ margin: '0.25rem 0 0 1rem' }}>
            {warnings.map((w, i) => (
              <li key={i}>{w}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
