import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import client from "../api/client";
import { useAuth } from "../context/AuthContext";

export default function Dashboard() {
  const { user } = useAuth();
  const [account, setAccount] = useState(null);
  const [transactions, setTransactions] = useState([]);
  const [error, setError] = useState("");

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
        setError("Could not load account data.");
      }
    }
    load();
  }, []);

  return (
    <div className="page">
      <h1>Welcome, {user?.name}</h1>

      {error && <p className="error-text">{error}</p>}

      {account && (
        <div className="card balance-card">
          <p className="balance-label">Available Balance</p>
          <p className="balance-amount">
            ₹{account.balance.toLocaleString(undefined, { minimumFractionDigits: 2 })}
          </p>
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
