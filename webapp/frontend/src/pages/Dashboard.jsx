import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import client from "../api/client";
import { useAuth } from "../context/AuthContext";
import BankCardCarousel from "../components/BankCardCarousel";

export default function Dashboard() {
  const { user } = useAuth();
  const [account, setAccount] = useState(null);
  const [invest, setInvest] = useState(null);
  const [transactions, setTransactions] = useState([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function load() {
      try {
        const [accRes, txnRes, investRes] = await Promise.all([
          client.get("/api/accounts/me"),
          client.get("/api/transactions/mini-statement?limit=5"),
          // The invest card is optional — never fail the dashboard for it.
          client.get("/api/portfolio/summary").catch(() => null),
        ]);
        setAccount(accRes.data);
        setTransactions(txnRes.data);
        setInvest(investRes?.data || null);
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
        <BankCardCarousel account={account} invest={invest} holder={user?.name} />
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
