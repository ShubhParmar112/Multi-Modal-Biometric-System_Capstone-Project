import { useEffect, useState } from "react";
import {
  PieChart, Pie, Cell, Tooltip, Legend, ResponsiveContainer,
  LineChart, Line, XAxis, YAxis, CartesianGrid,
  BarChart, Bar, AreaChart, Area,
} from "recharts";
import client from "../api/client";
import { useCurrency } from "../context/CurrencyContext";

const COLORS = [
  "#00D4AA", "#E94560", "#F5A623", "#4ECDC4", "#9B59B6",
  "#3498DB", "#FF6B6B", "#2ECC71", "#FFD93D", "#A8DADC",
];

export default function Analytics() {
  const { fmt } = useCurrency();
  const [report, setReport] = useState(null);
  const [spendingTrend, setSpendingTrend] = useState([]);
  const [savingsTrend, setSavingsTrend] = useState([]);
  const [cashFlow, setCashFlow] = useState([]);
  const [balanceHistory, setBalanceHistory] = useState([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function load() {
      try {
        const [reportRes, spendRes, savingsRes, flowRes, balanceRes] = await Promise.all([
          client.get("/api/analytics/monthly-report"),
          client.get("/api/analytics/spending-trend?months=6"),
          client.get("/api/analytics/savings-trend?months=6"),
          client.get("/api/analytics/cash-flow?months=6"),
          client.get("/api/analytics/balance-history"),
        ]);
        setReport(reportRes.data);
        setSpendingTrend(spendRes.data);
        setSavingsTrend(savingsRes.data);
        setCashFlow(flowRes.data);
        setBalanceHistory(balanceRes.data.map((p, i) => ({
          ...p,
          i,
          day: (p.timestamp || "").slice(0, 10),
        })));
      } catch {
        setError("Could not load analytics data. Make sure the backend is running.");
      } finally {
        setLoading(false);
      }
    }
    load();
  }, []);

  const pieData = report
    ? Object.entries(report.category_breakdown).map(([name, value]) => ({ name, value }))
    : [];

  const trendData = spendingTrend.map((row, i) => ({
    month: row.month,
    spending: row.total_spend,
    netSavings: savingsTrend[i]?.net_savings ?? 0,
  }));

  return (
    <div className="page">
      <h1>Personal Finance Analytics</h1>

      {error && <p className="error-text">{error}</p>}
      {loading && <div className="spinner" />}

      {report && (
        <div className="card summary-card">
          <div><span className="muted">Month</span><h2>{report.month}</h2></div>
          <div><span className="muted">Income</span><h2>{fmt(report.total_income)}</h2></div>
          <div><span className="muted">Expense</span><h2>{fmt(report.total_expense)}</h2></div>
          <div><span className="muted">Net Savings</span><h2>{fmt(report.net_savings)}</h2></div>
        </div>
      )}

      <div className="grid-2">
        <div className="card chart-card">
          <h2>Category Breakdown</h2>
          {pieData.length === 0 ? (
            <p className="muted">No expenses this month.</p>
          ) : (
            <ResponsiveContainer width="100%" height={330}>
              <PieChart margin={{ top: 24, bottom: 8, left: 8, right: 8 }}>
                <Pie data={pieData} dataKey="value" nameKey="name" outerRadius={88}
                  label={({ value }) => fmt(value)}>
                  {pieData.map((_, i) => (
                    <Cell key={i} fill={COLORS[i % COLORS.length]} />
                  ))}
                </Pie>
                <Tooltip formatter={(v) => fmt(v)} />
                <Legend wrapperStyle={{ paddingTop: 18 }} />
              </PieChart>
            </ResponsiveContainer>
          )}
        </div>

        <div className="card chart-card">
          <h2>Spending &amp; Savings Trend</h2>
          <ResponsiveContainer width="100%" height={280}>
            <LineChart data={trendData} margin={{ top: 5, right: 28, left: 0, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#2A3A5C" />
              <XAxis dataKey="month" stroke="#7B8794" interval={0} fontSize={11} />
              <YAxis stroke="#7B8794" fontSize={11} />
              <Tooltip formatter={(v) => fmt(v)} />
              <Legend wrapperStyle={{ paddingTop: 10 }} />
              <Line type="monotone" dataKey="spending" stroke="#E94560" name="Spending" />
              <Line type="monotone" dataKey="netSavings" stroke="#00D4AA" name="Net Savings" />
            </LineChart>
          </ResponsiveContainer>
        </div>

        <div className="card chart-card">
          <h2>Cash Flow</h2>
          <ResponsiveContainer width="100%" height={280}>
            <BarChart data={cashFlow} margin={{ top: 5, right: 28, left: 0, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#2A3A5C" />
              <XAxis dataKey="month" stroke="#7B8794" interval={0} fontSize={11} />
              <YAxis stroke="#7B8794" fontSize={11} />
              <Tooltip formatter={(v) => fmt(v)} />
              <Legend wrapperStyle={{ paddingTop: 10 }} />
              <Bar dataKey="inflow" fill="#00D4AA" name="Inflow" />
              <Bar dataKey="outflow" fill="#E94560" name="Outflow" />
            </BarChart>
          </ResponsiveContainer>
        </div>

        <div className="card chart-card">
          <h2>Account Balance Over Time</h2>
          <p className="muted" style={{ fontSize: 12, marginTop: -8 }}>
            Your running balance after every transaction.
          </p>
          {balanceHistory.length === 0 ? (
            <p className="muted">No transactions yet.</p>
          ) : (
            <ResponsiveContainer width="100%" height={280}>
              <AreaChart data={balanceHistory}
                margin={{ top: 5, right: 18, left: 0, bottom: 0 }}>
                <defs>
                  <linearGradient id="balanceFill" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#00D4AA" stopOpacity={0.35} />
                    <stop offset="100%" stopColor="#00D4AA" stopOpacity={0.02} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="#2A3A5C" />
                {/* Unique integer index → evenly spaced points that don't
                    collapse on repeated dates; label maps back to the date. */}
                <XAxis dataKey="i" stroke="#7B8794" fontSize={11}
                  tickFormatter={(i) => balanceHistory[i]?.day || ""} />
                <YAxis stroke="#7B8794" fontSize={11} />
                <Tooltip formatter={(v) => fmt(v)}
                  labelFormatter={(i) => balanceHistory[i]?.day || ""} />
                <Area type="monotone" dataKey="balance" stroke="#00D4AA"
                  strokeWidth={2} fill="url(#balanceFill)" name="Balance" />
              </AreaChart>
            </ResponsiveContainer>
          )}
        </div>
      </div>
    </div>
  );
}
