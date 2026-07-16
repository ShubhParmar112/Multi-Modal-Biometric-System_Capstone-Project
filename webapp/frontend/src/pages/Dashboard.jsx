import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import client from "../api/client";
import { useAuth } from "../context/AuthContext";

export default function Dashboard() {
  const { user } = useAuth();
  const [account, setAccount] = useState(null);
  const [transactions, setTransactions] = useState([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function load() {
      try {
        const [accRes, txnRes] = await Promise.all([
          client.get("/api/accounts/me"),
          client.get("/api/transactions/mini-statement?limit=5"),
        ]);
        setAccount(accRes.data);
        setTransactions(txnRes.data);
      } catch {
        setError("Could not load account data. Make sure the backend is running.");
      } finally {
        setLoading(false);
      }
    }
    load();
  }, []);

  return (
    <div className="page">
      <h1>Welcome, {user?.name}</h1>

      {error && <p className="error-text">{error}</p>}
      {loading && <div className="spinner" />}

      {account && (
        <div className="bank-card-wrap">
          <div className="bank-card">
            <div className="bank-card-top">
              <div className="bank-card-chip" />
              <svg className="bank-card-contactless" viewBox="0 0 24 24"
                fill="none" stroke="currentColor" strokeWidth="2"
                strokeLinecap="round" aria-hidden="true">
                <path d="M6.5 8.5a9 9 0 0 1 0 7" />
                <path d="M10 6.5a13 13 0 0 1 0 11" />
                <path d="M13.5 4.5a17 17 0 0 1 0 15" />
              </svg>
            </div>

            <div>
              <p className="bank-card-number">
                {account.card_number_masked || "•••• •••• •••• ••••"}
              </p>
              <p className="bank-card-balance-label">Available Balance</p>
              <p className="bank-card-balance">
                ₹{account.balance.toLocaleString(undefined, { minimumFractionDigits: 2 })}
              </p>
            </div>

            <div className="bank-card-bottom">
              <div>
                <p className="bank-card-label">Card Holder</p>
                <p className="bank-card-holder">{user?.name}</p>
              </div>
              <div className="bank-card-brand" aria-hidden="true">
                <span /><span />
              </div>
            </div>
          </div>
          <p className="balance-meta">
            {account.account_type.toUpperCase()} · {account.account_number}
          </p>
        </div>
      )}

      <div className="quick-links">
        <Link className="btn btn-primary" to="/transactions">Deposit / Withdraw / Transfer</Link>
        <Link className="btn btn-secondary" to="/analytics">View Analytics</Link>
      </div>

      <div className="card">
        <h2>Recent Transactions</h2>
        {transactions.length === 0 ? (
          <p className="muted">No transactions yet.</p>
        ) : (
          <table className="table">
            <thead>
              <tr>
                <th>Type</th>
                <th>Category</th>
                <th>Amount</th>
                <th>Balance</th>
                <th>Date</th>
              </tr>
            </thead>
            <tbody>
              {transactions.map((t) => (
                <tr key={t.transaction_id}>
                  <td>{t.txn_type}</td>
                  <td>{t.category}</td>
                  <td>{t.amount.toFixed(2)}</td>
                  <td>{t.balance_after.toFixed(2)}</td>
                  <td>{t.timestamp}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
