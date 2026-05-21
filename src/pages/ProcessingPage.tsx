import { useState, useMemo } from 'react';
import { Link } from 'react-router-dom';
import { useParseResult } from '../context/ParseResultContext';
import { filterTransactionGroups } from '../utils/filterTransactionGroups';
import { AssigneeDatabase } from '../utils/AssigneeDatabase';

function formatAmount(amount: number): string {
  return Math.abs(amount).toLocaleString('en-IN', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

export default function ProcessingPage() {
  const { parseResult } = useParseResult();
  const [personNameQuery, setPersonNameQuery] = useState('');
  const [assigneeNameQuery, setAssigneeNameQuery] = useState('');

  const assigneeDb = useMemo(() => new AssigneeDatabase(), []);
  const assignees = useMemo(() => assigneeDb.getAssignees(), [assigneeDb]);
  const localStorageAvailable = useMemo(() => assigneeDb.isLocalStorageAvailable(), [assigneeDb]);

  const filteredGroups = useMemo(() => {
    if (!parseResult) return [];
    return filterTransactionGroups(
      parseResult.transactionGroups,
      personNameQuery,
      assigneeNameQuery,
      assigneeDb
    );
  }, [parseResult, personNameQuery, assigneeNameQuery, assigneeDb]);

  const totalTransactions = filteredGroups.reduce((sum, g) => sum + g.transactions.length, 0);

  // Summary stats
  const stats = useMemo(() => {
    const allTxns = filteredGroups.flatMap(g => g.transactions);
    const credits = allTxns.filter(t => t.amount > 0).reduce((s, t) => s + t.amount, 0);
    const debits = allTxns.filter(t => t.amount < 0).reduce((s, t) => s + Math.abs(t.amount), 0);
    return { credits, debits, net: credits - debits, count: allTxns.length };
  }, [filteredGroups]);

  if (!parseResult) {
    return (
      <div className="no-data-page">
        <div className="no-data-icon">
          <svg width="64" height="64" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1" strokeLinecap="round" strokeLinejoin="round">
            <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
            <polyline points="14 2 14 8 20 8" />
          </svg>
        </div>
        <h1>No Statement Loaded</h1>
        <p>Upload a bank statement to see your transactions here.</p>
        <Link to="/" className="btn-primary">← Upload a statement</Link>
      </div>
    );
  }

  const { statementPeriod } = parseResult;
  const periodUnknown =
    statementPeriod.startDate === 'Unknown' || statementPeriod.endDate === 'Unknown';

  return (
    <div className="processed-page">
      <div className="page-header">
        <Link to="/" className="back-link">← Upload another statement</Link>
        <h1>Statement Processed</h1>
      </div>

      {periodUnknown ? (
        <div className="period-warning" role="alert">
          Could not determine statement date range.
        </div>
      ) : (
        <div className="period-card">
          <span className="label">Period:</span>
          <span className="dates">{statementPeriod.startDate} — {statementPeriod.endDate}</span>
        </div>
      )}

      {/* Summary cards */}
      <div className="summary-cards">
        <div className="summary-card credit">
          <div className="summary-label">Total Credits</div>
          <div className="summary-value">+ ₹{formatAmount(stats.credits)}</div>
        </div>
        <div className="summary-card debit">
          <div className="summary-label">Total Debits</div>
          <div className="summary-value">− ₹{formatAmount(stats.debits)}</div>
        </div>
        <div className="summary-card net">
          <div className="summary-label">Net</div>
          <div className={`summary-value ${stats.net >= 0 ? 'positive' : 'negative'}`}>
            {stats.net >= 0 ? '+' : '−'} ₹{formatAmount(stats.net)}
          </div>
        </div>
        <div className="summary-card count">
          <div className="summary-label">Transactions</div>
          <div className="summary-value">{stats.count}</div>
        </div>
      </div>

      {!localStorageAvailable && (
        <div className="storage-warning" role="status">
          Local storage unavailable — assignee mappings won't persist between sessions.
        </div>
      )}

      <div className="filters">
        <div className="filter-group">
          <label htmlFor="person-name-filter">Search transactions</label>
          <input
            id="person-name-filter"
            type="text"
            value={personNameQuery}
            onChange={(e) => setPersonNameQuery(e.target.value)}
            placeholder="Search by name or description..."
          />
        </div>
        <div className="filter-group">
          <label htmlFor="assignee-name-filter">Assignee</label>
          <select
            id="assignee-name-filter"
            value={assigneeNameQuery}
            onChange={(e) => setAssigneeNameQuery(e.target.value)}
          >
            <option value="">All assignees</option>
            {assignees.map((assignee) => (
              <option key={assignee.name} value={assignee.name}>
                {assignee.name}
              </option>
            ))}
          </select>
        </div>
      </div>

      {filteredGroups.length === 0 ? (
        <div className="empty-state">
          <p>No transactions match your filters.</p>
        </div>
      ) : (
        filteredGroups.map((group, groupIndex) => (
          <div key={groupIndex} className="tx-group">
            <div className="tx-group-header">
              <span className="acc-number">{group.account.accountNumber}</span>
              <span className="acc-name">{group.account.accountName}</span>
            </div>
            <table className="tx-table">
              <thead>
                <tr>
                  <th>Date</th>
                  <th>Description</th>
                  <th style={{ textAlign: 'right' }}>Amount (₹)</th>
                </tr>
              </thead>
              <tbody>
                {group.transactions.map((txn, txnIndex) => (
                  <tr key={txnIndex}>
                    <td className="date">{txn.date}</td>
                    <td className="description">{txn.description}</td>
                    <td className={`amount ${txn.amount >= 0 ? 'positive' : 'negative'}`}>
                      {txn.amount < 0 ? '−' : '+'} {formatAmount(txn.amount)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            <div className="tx-count">
              {group.transactions.length} transaction{group.transactions.length !== 1 ? 's' : ''}
            </div>
          </div>
        ))
      )}

      {totalTransactions > 0 && (
        <div className="results-footer">
          Showing {totalTransactions} transaction{totalTransactions !== 1 ? 's' : ''} across {filteredGroups.length} account{filteredGroups.length !== 1 ? 's' : ''}
        </div>
      )}
    </div>
  );
}
