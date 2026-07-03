import { useEffect, useState } from "react";
import {
  PieChart, Pie, Cell, Tooltip, Legend, ResponsiveContainer,
  LineChart, Line, XAxis, YAxis, CartesianGrid,
  BarChart, Bar,
} from "recharts";
import client from "../api/client";

const COLORS = [
  "#00D4AA", "#E94560", "#F5A623", "#4ECDC4", "#9B59B6",
  "#3498DB", "#FF6B6B", "#2ECC71", "#FFD93D", "#A8DADC",
];

export default function Analytics() {
  const [report, setReport] = useState(null);
  const [spendingTrend, setSpendingTrend] = useState([]);
  const [savingsTrend, setSavingsTrend] = useState([]);
  const [cashFlow, setCashFlow] = useState([]);

  useEffect(() => {
    async function load() {
      const [reportRes, spendRes, savingsRes, flowRes] = await Promise.all([
        client.get("/api/analytics/monthly-report"),
        client.get("/api/analytics/spending-trend?months=6"),
        client.get("/api/analytics/savings-trend?months=6"),
        client.get("/api/analytics/cash-flow?months=6"),
      ]);
      setReport(reportRes.data);
      setSpendingTrend(spendRes.data);
      setSavingsTrend(savingsRes.data);
      setCashFlow(flowRes.data);
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

      {report && (
        <div className="card summary-card">
          <div><span className="muted">Month</span><h2>{report.month}</h2></div>
          <div><span className="muted">Income</span><h2>₹{report.total_income.toLocaleString()}</h2></div>
          <div><span className="muted">Expense</span><h2>₹{report.total_expense.toLocaleString()}</h2></div>
          <div><span className="muted">Net Savings</span><h2>₹{report.net_savings.toLocaleString()}</h2></div>
        </div>
      )}

      <div className="grid-2">
        <div className="card chart-card">
          <h2>Category Breakdown</h2>
          {pieData.length === 0 ? (
            <p className="muted">No expenses this month.</p>
          ) : (
            <ResponsiveContainer width="100%" height={280}>
              <PieChart>
                <Pie data={pieData} dataKey="value" nameKey="name" outerRadius={100} label>
                  {pieData.map((_, i) => (
                    <Cell key={i} fill={COLORS[i % COLORS.length]} />
                  ))}
                </Pie>
                <Tooltip />
                <Legend />
              </PieChart>
            </ResponsiveContainer>
          )}
        </div>

        <div className="card chart-card">
          <h2>Spending &amp; Savings Trend</h2>
          <ResponsiveContainer width="100%" height={280}>
            <LineChart data={trendData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#2A3A5C" />
              <XAxis dataKey="month" stroke="#7B8794" />
              <YAxis stroke="#7B8794" />
              <Tooltip />
              <Legend />
              <Line type="monotone" dataKey="spending" stroke="#E94560" name="Spending" />
              <Line type="monotone" dataKey="netSavings" stroke="#00D4AA" name="Net Savings" />
            </LineChart>
          </ResponsiveContainer>
        </div>

        <div className="card chart-card">
          <h2>Cash Flow</h2>
          <ResponsiveContainer width="100%" height={280}>
            <BarChart data={cashFlow}>
              <CartesianGrid strokeDasharray="3 3" stroke="#2A3A5C" />
              <XAxis dataKey="month" stroke="#7B8794" />
              <YAxis stroke="#7B8794" />
              <Tooltip />
              <Legend />
              <Bar dataKey="inflow" fill="#00D4AA" name="Inflow" />
              <Bar dataKey="outflow" fill="#E94560" name="Outflow" />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>
    </div>
  );
}
