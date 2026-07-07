import { useEffect, useState } from "react";
import client from "../api/client";

export default function Transactions() {
  const [categories, setCategories] = useState([]);
  const [newCategory, setNewCategory] = useState("");
  const [statement, setStatement] = useState([]);
  const [status, setStatus] = useState(null);
  const [blockHighRisk, setBlockHighRisk] = useState(false);
  const [beneficiaries, setBeneficiaries] = useState([]);

  const [depositAmount, setDepositAmount] = useState("");
  const [withdrawAmount, setWithdrawAmount] = useState("");
  const [withdrawCategory, setWithdrawCategory] = useState("Other");
  const [transferAccount, setTransferAccount] = useState("");
  const [transferAmount, setTransferAmount] = useState("");
  const [transferCategory, setTransferCategory] = useState("Other");

  async function refresh() {
    try {
      const [catRes, stmtRes, fraudRes, benRes] = await Promise.all([
        client.get("/api/analytics/categories"),
        client.get("/api/transactions/mini-statement?limit=20"),
        client.get("/api/fraud/blocking-status"),
        client.get("/api/settings/beneficiaries"),
      ]);
      setCategories(catRes.data);
      setStatement(stmtRes.data);
      setBlockHighRisk(fraudRes.data.enabled);
      setBeneficiaries(benRes.data);
    } catch {
      setStatus({ success: false, message: "Could not load data from the server." });
    }
  }

  useEffect(() => {
    refresh();
  }, []);

  function showStatus(res) {
    setStatus({
      success: res.data.success,
      message: res.data.message,
    });
    refresh();
  }

  function showError() {
    setStatus({ success: false, message: "The request failed. Please try again." });
  }

  async function handleDeposit(e) {
    e.preventDefault();
    try {
      const res = await client.post("/api/transactions/deposit", {
        amount: parseFloat(depositAmount),
      });
      setDepositAmount("");
      showStatus(res);
    } catch { showError(); }
  }

  async function handleWithdraw(e) {
    e.preventDefault();
    try {
      const res = await client.post("/api/transactions/withdraw", {
        amount: parseFloat(withdrawAmount),
        category: withdrawCategory,
      });
      setWithdrawAmount("");
      showStatus(res);
    } catch { showError(); }
  }

  async function handleTransfer(e) {
    e.preventDefault();
    try {
      const res = await client.post("/api/transactions/transfer", {
        to_account_number: transferAccount,
        amount: parseFloat(transferAmount),
        category: transferCategory,
      });
      setTransferAccount("");
      setTransferAmount("");
      showStatus(res);
    } catch { showError(); }
  }

  async function handleAddCategory(e) {
    e.preventDefault();
    if (!newCategory.trim()) return;
    await client.post("/api/analytics/categories", { name: newCategory.trim() });
    setNewCategory("");
    refresh();
  }

  async function handleToggleBlocking() {
    const res = await client.post("/api/fraud/toggle-blocking", {
      enabled: !blockHighRisk,
    });
    setBlockHighRisk(res.data.enabled);
  }

  return (
    <div className="page">
      <h1>Transactions</h1>

      {status && (
        <p className={status.success ? "success-text" : "error-text"}>
          {status.message}
        </p>
      )}

      <div className="grid-3">
        <form className="card" onSubmit={handleDeposit}>
          <h2>💰 Deposit</h2>
          <label className="field-label">Amount</label>
          <input
            className="input" type="number" min="0.01" step="0.01" required
            value={depositAmount} onChange={(e) => setDepositAmount(e.target.value)}
          />
          <button className="btn btn-primary" type="submit">Deposit</button>
        </form>

        <form className="card" onSubmit={handleWithdraw}>
          <h2>💸 Withdraw</h2>
          <label className="field-label">Amount</label>
          <input
            className="input" type="number" min="0.01" step="0.01" required
            value={withdrawAmount} onChange={(e) => setWithdrawAmount(e.target.value)}
          />
          <label className="field-label">Category</label>
          <select
            className="input" value={withdrawCategory}
            onChange={(e) => setWithdrawCategory(e.target.value)}
          >
            {categories.map((c) => <option key={c} value={c}>{c}</option>)}
          </select>
          <button className="btn btn-primary" type="submit">Withdraw</button>
        </form>

        <form className="card" onSubmit={handleTransfer}>
          <h2>🔁 Transfer</h2>
          {beneficiaries.length > 0 && (
            <>
              <label className="field-label">Beneficiary</label>
              <select
                className="input" value=""
                onChange={(e) => e.target.value && setTransferAccount(e.target.value)}
              >
                <option value="">Pick a saved beneficiary…</option>
                {beneficiaries.map((b) => (
                  <option key={b.beneficiary_id} value={b.account_number}>
                    {b.name} — {b.account_number}
                  </option>
                ))}
              </select>
            </>
          )}
          <label className="field-label">Destination Account Number</label>
          <input
            className="input" required
            value={transferAccount} onChange={(e) => setTransferAccount(e.target.value)}
          />
          <label className="field-label">Amount</label>
          <input
            className="input" type="number" min="0.01" step="0.01" required
            value={transferAmount} onChange={(e) => setTransferAmount(e.target.value)}
          />
          <label className="field-label">Category</label>
          <select
            className="input" value={transferCategory}
            onChange={(e) => setTransferCategory(e.target.value)}
          >
            {categories.map((c) => <option key={c} value={c}>{c}</option>)}
          </select>
          <button className="btn btn-primary" type="submit">Transfer</button>
        </form>
      </div>

      <div className="card">
        <h2>Manage Categories</h2>
        <form className="inline-form" onSubmit={handleAddCategory}>
          <input
            className="input" placeholder="New category name"
            value={newCategory} onChange={(e) => setNewCategory(e.target.value)}
          />
          <button className="btn btn-secondary" type="submit">+ Add</button>
        </form>
        <div className="tag-list">
          {categories.map((c) => <span className="tag" key={c}>{c}</span>)}
        </div>
      </div>

      <div className="card toggle-card">
        <label className="switch">
          <input type="checkbox" checked={blockHighRisk} onChange={handleToggleBlocking} />
          <span className="slider" />
        </label>
        <span>Block high-risk transactions {blockHighRisk ? "(ON)" : "(OFF)"}</span>
      </div>

      <div className="card">
        <h2>Mini Statement</h2>
        {statement.length === 0 ? (
          <p className="muted">No transactions yet.</p>
        ) : (
          <table className="table">
            <thead>
              <tr>
                <th>Type</th><th>Category</th><th>Amount</th><th>Balance</th>
                <th>Status</th><th>Date</th>
              </tr>
            </thead>
            <tbody>
              {statement.map((t) => (
                <tr key={t.transaction_id}>
                  <td>{t.txn_type}</td>
                  <td>{t.category}</td>
                  <td>{t.amount.toFixed(2)}</td>
                  <td>{t.balance_after.toFixed(2)}</td>
                  <td>{t.status}</td>
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
