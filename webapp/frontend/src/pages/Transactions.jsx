import { useEffect, useMemo, useState } from "react";
import {
  Area, AreaChart, Bar, BarChart, CartesianGrid, Legend,
  ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import client from "../api/client";
import { useCurrency } from "../context/CurrencyContext";
import { useViewAs } from "../context/ViewAsContext";

const INITIAL_ROWS = 10;   // mini statement starts with the latest 10
const ROWS_PER_CLICK = 20; // each "Show more" loads 20 additional rows

const INCOME_TYPES = new Set(["deposit", "transfer_in"]);
const EXPENSE_TYPES = new Set(["withdraw", "transfer_out"]);

// Charts built from the SAME rows the mini statement shows — they extend
// as "Show more" loads older rows.
function StatementCharts({ statement, fmt }) {
  const { daily, cumulative } = useMemo(() => {
    const rows = [...statement].reverse(); // oldest first
    const byDay = new Map();
    let running = 0;
    const cumulative = [];
    for (const t of rows) {
      const day = (t.timestamp || "").slice(0, 10);
      if (!byDay.has(day)) byDay.set(day, { day, credit: 0, debit: 0 });
      if (INCOME_TYPES.has(t.txn_type)) {
        byDay.get(day).credit += t.amount;
        running += t.amount;
      } else if (EXPENSE_TYPES.has(t.txn_type)) {
        byDay.get(day).debit += t.amount;
        running -= t.amount;
      }
      cumulative.push({ i: cumulative.length, day, net: Math.round(running * 100) / 100 });
    }
    return { daily: [...byDay.values()], cumulative };
  }, [statement]);

  if (statement.length === 0) return null;

  // Split the net-flow area at zero: green fill above the axis, red below.
  const nets = cumulative.map((c) => c.net);
  const maxNet = Math.max(...nets, 0);
  const minNet = Math.min(...nets, 0);
  const zeroOffset = maxNet <= 0 ? 0
    : minNet >= 0 ? 1
    : maxNet / (maxNet - minNet);

  return (
    <div className="grid-2">
      <div className="card chart-card">
        <h2>Credit vs Debit Volume</h2>
        <p className="muted" style={{ fontSize: 12, marginTop: -8 }}>
          From the {statement.length} statement rows shown below.
        </p>
        <ResponsiveContainer width="100%" height={240}>
          <BarChart data={daily}>
            <CartesianGrid strokeDasharray="3 3" stroke="#2A3A5C" />
            <XAxis dataKey="day" stroke="#7B8794" fontSize={11} />
            <YAxis stroke="#7B8794" fontSize={11} />
            <Tooltip formatter={(v) => fmt(v)} />
            <Legend />
            <Bar dataKey="credit" fill="#00D4AA" name="Credits" />
            <Bar dataKey="debit" fill="#E94560" name="Debits" />
          </BarChart>
        </ResponsiveContainer>
      </div>

      <div className="card chart-card">
        <h2>Cumulative Net Flow</h2>
        <p className="muted" style={{ fontSize: 12, marginTop: -8 }}>
          Running net of credits minus debits across the visible rows.
        </p>
        <ResponsiveContainer width="100%" height={240}>
          <AreaChart data={cumulative} margin={{ top: 5, right: 18, left: 0, bottom: 0 }}>
            <defs>
              <linearGradient id="netFlowFill" x1="0" y1="0" x2="0" y2="1">
                <stop offset={zeroOffset} stopColor="#00D4AA" stopOpacity={0.35} />
                <stop offset={zeroOffset} stopColor="#E94560" stopOpacity={0.35} />
              </linearGradient>
              <linearGradient id="netFlowStroke" x1="0" y1="0" x2="0" y2="1">
                <stop offset={zeroOffset} stopColor="#00D4AA" stopOpacity={1} />
                <stop offset={zeroOffset} stopColor="#E94560" stopOpacity={1} />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke="#2A3A5C" />
            {/* Unique integer index keeps every transaction a distinct point
                (dates repeat), so the hover dot tracks the cursor exactly. */}
            <XAxis dataKey="i" stroke="#7B8794" fontSize={11}
              tickFormatter={(i) => cumulative[i]?.day || ""} />
            <YAxis stroke="#7B8794" fontSize={11} />
            <Tooltip
              itemStyle={{ color: "#1B2333" }}
              labelFormatter={(i) => cumulative[i]?.day || ""}
              formatter={(v) => [
                <span style={{ color: v < 0 ? "#E94560" : "#00D4AA", fontWeight: 600 }}>{fmt(v)}</span>,
                "Net Flow",
              ]} />
            <Area type="monotone" dataKey="net" stroke="url(#netFlowStroke)"
              strokeWidth={2} fill="url(#netFlowFill)" dot={false} name="Net Flow" />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

export default function Transactions() {
  const { fmt } = useCurrency();
  const { isViewing } = useViewAs();
  const [categories, setCategories] = useState([]);
  const [newCategory, setNewCategory] = useState("");
  const [statement, setStatement] = useState([]);
  const [statementLimit, setStatementLimit] = useState(INITIAL_ROWS);
  const [allLoaded, setAllLoaded] = useState(false);
  const [status, setStatus] = useState(null);
  const [blockHighRisk, setBlockHighRisk] = useState(false);
  const [beneficiaries, setBeneficiaries] = useState([]);

  const [depositAmount, setDepositAmount] = useState("");
  const [withdrawAmount, setWithdrawAmount] = useState("");
  const [withdrawCategory, setWithdrawCategory] = useState("Other");
  const [transferAccount, setTransferAccount] = useState("");
  const [transferAmount, setTransferAmount] = useState("");
  const [transferCategory, setTransferCategory] = useState("Other");

  async function loadStatement(limit) {
    const res = await client.get(`/api/transactions/mini-statement?limit=${limit}`);
    setStatement(res.data);
    // Fewer rows than asked for means the history is fully loaded.
    setAllLoaded(res.data.length < limit);
  }

  async function refresh(limit = statementLimit) {
    try {
      const [catRes, fraudRes, benRes] = await Promise.all([
        client.get("/api/analytics/categories"),
        client.get("/api/fraud/blocking-status"),
        client.get("/api/settings/beneficiaries"),
        loadStatement(limit),
      ]);
      setCategories(catRes.data);
      setBlockHighRisk(fraudRes.data.enabled);
      setBeneficiaries(benRes.data);
    } catch {
      setStatus({ success: false, message: "Could not load data from the server." });
    }
  }

  useEffect(() => {
    refresh(INITIAL_ROWS);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function showMore() {
    const next = statementLimit + ROWS_PER_CLICK;
    setStatementLimit(next);
    try {
      await loadStatement(next);
    } catch {
      setStatus({ success: false, message: "Could not load more rows." });
    }
  }

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

      {/* Money movement acts on YOUR account — hidden while viewing a
          beneficiary's account read-only. */}
      {!isViewing && (
        <>
          <div className="grid-3">
            <form className="card" onSubmit={handleDeposit}>
              <h2>Deposit</h2>
              <label className="field-label">Amount</label>
              <input
                className="input" type="number" min="0.01" step="0.01" required
                value={depositAmount} onChange={(e) => setDepositAmount(e.target.value)}
              />
              <button className="btn btn-primary" type="submit">Deposit</button>
            </form>

            <form className="card" onSubmit={handleWithdraw}>
              <h2>Withdraw</h2>
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
              <h2>Transfer</h2>
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
        </>
      )}

      <StatementCharts statement={statement} fmt={fmt} />

      <div className="card">
        <h2>Mini Statement</h2>
        <p className="muted" style={{ fontSize: 12, marginTop: -8 }}>
          Latest {statement.length} transactions, newest first.
        </p>
        {statement.length === 0 ? (
          <p className="muted">No transactions yet.</p>
        ) : (
          <>
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
                    <td>{fmt(t.amount, { minimumFractionDigits: 2 })}</td>
                    <td>{fmt(t.balance_after, { minimumFractionDigits: 2 })}</td>
                    <td>{t.status}</td>
                    <td>{t.timestamp}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {!allLoaded && (
              <button className="btn btn-secondary" style={{ marginTop: 12 }}
                onClick={showMore}>
                Show more ({ROWS_PER_CLICK} older transactions)
              </button>
            )}
            {allLoaded && statement.length > INITIAL_ROWS && (
              <p className="muted" style={{ marginTop: 12, marginBottom: 0, fontSize: 12 }}>
                Full history shown.
              </p>
            )}
          </>
        )}
      </div>
    </div>
  );
}
