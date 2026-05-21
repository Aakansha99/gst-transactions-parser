import { useState, useRef, useCallback, type ChangeEvent, type DragEvent } from 'react';
import { useNavigate } from 'react-router-dom';
import { validateExtension } from '../utils/validateExtension';
import { useParseResult } from '../context/ParseResultContext';
import { parseStatementViaApi, ParseApiError } from '../utils/parseStatementApi';

export default function UploadPage() {
  const [error, setError] = useState<string | null>(null);
  const [warnings, setWarnings] = useState<string[]>([]);
  const [isProcessing, setIsProcessing] = useState(false);
  const [isDragging, setIsDragging] = useState(false);
  const [fileName, setFileName] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const navigate = useNavigate();
  const { setParseResult } = useParseResult();

  function resetState() {
    if (fileInputRef.current) fileInputRef.current.value = '';
    setFileName(null);
  }

  async function processFile(file: File) {
    setError(null);
    setWarnings([]);

    if (!validateExtension(file.name)) {
      setError('Only PDF files are accepted. Please select a .pdf file.');
      resetState();
      return;
    }

    setFileName(file.name);
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
      resetState();
    } finally {
      setIsProcessing(false);
    }
  }

  function handleFileChange(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (file) processFile(file);
  }

  const handleDragOver = useCallback((e: DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  }, []);

  const handleDragLeave = useCallback((e: DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
  }, []);

  const handleDrop = useCallback((e: DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    const file = e.dataTransfer.files?.[0];
    if (file) processFile(file);
  }, []);

  return (
    <div className="upload-page">
      <div className="upload-hero">
        <div className="upload-icon">
          <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
            <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
            <polyline points="14 2 14 8 20 8" />
            <line x1="12" y1="18" x2="12" y2="12" />
            <polyline points="9 15 12 12 15 15" />
          </svg>
        </div>
        <h1>GST Statement Processor</h1>
        <p className="subtitle">Upload a bank statement PDF to extract and view transactions</p>
      </div>

      <div
        className={`upload-dropzone ${isDragging ? 'dragging' : ''} ${isProcessing ? 'processing' : ''}`}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
        onClick={() => !isProcessing && fileInputRef.current?.click()}
      >
        <input
          ref={fileInputRef}
          type="file"
          accept=".pdf"
          onChange={handleFileChange}
          disabled={isProcessing}
          aria-label="Upload bank statement PDF"
          style={{ display: 'none' }}
        />

        {isProcessing ? (
          <div className="upload-processing">
            <div className="spinner" />
            <p>Parsing <strong>{fileName}</strong>...</p>
            <p className="hint">Extracting transactions from your statement</p>
          </div>
        ) : (
          <div className="upload-prompt">
            <div className="upload-prompt-icon">
              <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
                <polyline points="17 8 12 3 7 8" />
                <line x1="12" y1="3" x2="12" y2="15" />
              </svg>
            </div>
            <p><strong>Drop your PDF here</strong> or click to browse</p>
            <p className="hint">Supports ICICI, HDFC, SBI, Axis, Kotak, and most Indian bank statements</p>
          </div>
        )}
      </div>

      <p className="privacy-note">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ verticalAlign: '-2px', marginRight: '4px' }}>
          <rect x="3" y="11" width="18" height="11" rx="2" ry="2" />
          <path d="M7 11V7a5 5 0 0 1 10 0v4" />
        </svg>
        Files are processed in memory and not stored on any server
      </p>

      {error && (
        <div className="error-message" role="alert">
          <strong>Error:</strong> {error}
        </div>
      )}

      {warnings.length > 0 && (
        <div className="warning-message" role="status">
          <strong>Notes:</strong>
          <ul>
            {warnings.map((w, i) => (
              <li key={i}>{w}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
