import { useEffect, useRef, useState } from "react";
import {
  Cell, Legend, Pie, PieChart, ResponsiveContainer, Tooltip,
} from "recharts";
import client from "../../api/client";
import { useCurrency } from "../../context/CurrencyContext";

const COLORS = [
  "#00D4AA", "#E94560", "#F5A623", "#4ECDC4", "#9B59B6",
  "#3498DB", "#FF6B6B", "#2ECC71", "#FFD93D", "#A8DADC",
];

// Same tinting rules as the asset-class correlation card.
function cellColor(v) {
  if (v >= 0.75) return "rgba(255, 84, 112, 0.35)";
  if (v >= 0.4) return "rgba(245, 166, 35, 0.25)";
  if (v <= -0.2) return "rgba(0, 212, 170, 0.30)";
  return "transparent";
}

function short(ticker) { return ticker.replace(".NS", ""); }

// Optimizer over the user's REAL holdings: target weights from stored
// price history (max-Sharpe, per-holding weight cap), a live investment
// plan for any amount, and the holdings correlation heatmap.
export default function HoldingsOptimizerCard({ defaultAmount }) {
  const { fmt } = useCurrency();
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [amount, setAmount] = useState(defaultAmount || "");
  const [plan, setPlan] = useState(null);
  const [planLoading, setPlanLoading] = useState(false);
  const debounceRef = useRef(null);

  useEffect(() => {
    let cancelled = false;
    client.get("/api/portfolio/holdings/optimizer")
      .then((res) => { if (!cancelled) setData(res.data); })
      .catch(() => { if (!cancelled) setError("Could not load the holdings optimizer."); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, []);

  useEffect(() => {
    if (defaultAmount && amount === "") setAmount(defaultAmount);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [defaultAmount]);

  // Recompute the plan live (debounced) as the amount changes.
  useEffect(() => {
    if (!data || data.status !== "ok") return;
    const value = Number(amount);
    if (!value || value <= 0) { setPlan(null); return; }
    clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(async () => {
      setPlanLoading(true);
      try {
        const res = await client.get(`/api/portfolio/holdings/plan?amount=${value}`);
        setPlan(res.data);
      } catch { setPlan(null); }
      finally { setPlanLoading(false); }
    }, 400);
    return () => clearTimeout(debounceRef.current);
  }, [amount, data]);

  if (loading) return <div className="card"><div className="spinner" /></div>;

  if (error || !data || data.status !== "ok") {
    return (
      <div className="card">
        <h2>🎯 Your Holdings — Optimized Allocation</h2>
        <p className="muted" style={{ marginBottom: 0 }}>
          {error || data?.message || "Not available."}
        </p>
      </div>
    );
  }

  const pieData = data.allocation
    .filter((a) => a.target_weight_pct > 0)
    .map((a) => ({ name: short(a.ticker), value: a.target_weight_pct }));
  const corr = data.correlation;

  return (
    <>
      <div className="card">
        <h2>🎯 Your Holdings — Optimized Allocation</h2>
        <p className="muted" style={{ fontSize: 12, marginTop: -8 }}>
          Max-Sharpe optimization over the securities you actually own, from
          their stored price history. No holding may exceed{" "}
          {data.max_weight_pct}% (enforced inside the optimizer).
          {data.excluded?.length > 0 &&
            ` Excluded for missing history: ${data.excluded.map(short).join(", ")}.`}
        </p>

        <div className="grid-3" style={{ marginBottom: 4 }}>
          <div className="card" style={{ textAlign: "center", margin: 0 }}>
            <p className="muted" style={{ margin: "0 0 4px" }}>Expected Annual Return</p>
            <div style={{ fontSize: 26, fontWeight: 700, color: "var(--primary)" }}>
              {data.expected_return}%
            </div>
          </div>
          <div className="card" style={{ textAlign: "center", margin: 0 }}>
            <p className="muted" style={{ margin: "0 0 4px" }}>Expected Risk</p>
            <div style={{ fontSize: 26, fontWeight: 700, color: "var(--accent)" }}>
              {data.expected_risk}%
            </div>
          </div>
          <div className="card" style={{ textAlign: "center", margin: 0 }}>
            <p className="muted" style={{ margin: "0 0 4px" }}>Sharpe Ratio</p>
            <div style={{ fontSize: 26, fontWeight: 700, color: "var(--warning)" }}>
              {data.sharpe_ratio}
            </div>
          </div>
        </div>

        <div className="grid-2" style={{ alignItems: "center" }}>
          <ResponsiveContainer width="100%" height={300}>
            <PieChart margin={{ top: 24, bottom: 8, left: 8, right: 8 }}>
              <Pie data={pieData} dataKey="value" nameKey="name" outerRadius={90}
                label={({ name, value }) => `${name}: ${value}%`}>
                {pieData.map((_, i) => (
                  <Cell key={i} fill={COLORS[i % COLORS.length]} />
                ))}
              </Pie>
              <Tooltip formatter={(v) => `${v}%`} />
              <Legend />
            </PieChart>
          </ResponsiveContainer>

          <div style={{ overflowX: "auto" }}>
            <table className="table">
              <thead>
                <tr>
                  <th>Holding</th>
                  <th style={{ textAlign: "right" }}>Current</th>
                  <th style={{ textAlign: "right" }}>Target</th>
                </tr>
              </thead>
              <tbody>
                {data.allocation.map((a) => (
                  <tr key={a.ticker}>
                    <td>
                      <strong style={{ color: "var(--text)" }}>{short(a.ticker)}</strong>
                      <div style={{ fontSize: 11, color: "var(--muted)" }}>{a.name}</div>
                    </td>
                    <td style={{ textAlign: "right" }} className="muted">
                      {a.current_weight_pct}%
                    </td>
                    <td style={{ textAlign: "right", fontWeight: 600 }}>
                      {a.target_weight_pct}%
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      {/* ── Smart Investment Plan (live from the optimized weights) ────── */}
      <div className="card">
        <h2>Smart Investment Plan — Your Holdings</h2>
        <p className="muted" style={{ fontSize: 12, marginTop: -8 }}>
          Enter an amount to invest and get exact whole-share counts that
          mirror the optimized target weights, at the latest stored prices.
        </p>
        <div className="inline-form" style={{ marginBottom: 12 }}>
          <input className="input" type="number" min="0" step="any"
            placeholder="Amount to invest"
            value={amount} onChange={(e) => setAmount(e.target.value)} />
          {planLoading && <span className="muted" style={{ fontSize: 12 }}>computing…</span>}
        </div>

        {plan?.status === "ok" && (
          <>
            <table className="table">
              <thead>
                <tr>
                  <th>Security</th><th>Weight</th><th>Shares × Price</th>
                  <th style={{ textAlign: "right" }}>Cost</th>
                </tr>
              </thead>
              <tbody>
                {plan.items.map((item) => (
                  <tr key={item.ticker}>
                    <td>
                      <strong style={{ color: "var(--text)" }}>{short(item.ticker)}</strong>
                      <div style={{ fontSize: 11, color: "var(--muted)" }}>{item.name}</div>
                    </td>
                    <td className="muted">{item.weight_pct}%</td>
                    <td className="muted">
                      {item.units} × {fmt(item.price)}
                      {item.is_estimated && (
                        <span title="No stored price — using buy price"
                          style={{ color: "var(--warning)", marginLeft: 4 }}>≈</span>
                      )}
                    </td>
                    <td style={{ textAlign: "right", fontWeight: 600 }}>{fmt(item.cost)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <div style={{
              display: "flex", justifyContent: "space-between", flexWrap: "wrap",
              gap: 8, borderTop: "1px solid var(--card-border)", paddingTop: 12,
            }}>
              <span>Deployed: <strong style={{ color: "var(--primary)" }}>
                {fmt(plan.total_invested)}</strong></span>
              <span className="muted">
                Rounding leftover to cash: {fmt(plan.total_uninvested)}
              </span>
            </div>
          </>
        )}
        {!plan && !planLoading && (
          <p className="muted" style={{ marginBottom: 0 }}>
            Enter an amount above to see the plan.
          </p>
        )}
      </div>

      {/* ── Correlation heatmap of the holdings ────────────────────────── */}
      <div className="card">
        <h2>Holdings Correlation Matrix</h2>
        <p className="muted" style={{ fontSize: 12, marginTop: -8 }}>
          From the same stored price history the optimizer uses. Red pairs
          move together (concentration); green pairs hedge each other.
        </p>
        <div style={{ overflowX: "auto" }}>
          <table className="table" style={{ minWidth: 420, textAlign: "center" }}>
            <thead>
              <tr>
                <th></th>
                {corr.tickers.map((t) => (
                  <th key={t} style={{ textAlign: "center" }}>{short(t)}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {corr.tickers.map((a, i) => (
                <tr key={a}>
                  <td><strong>{short(a)}</strong></td>
                  {corr.tickers.map((b, j) => {
                    const v = corr.matrix[i][j];
                    return (
                      <td key={b} style={{
                        background: i === j ? "transparent" : cellColor(v),
                        color: i === j ? "var(--muted)" : "var(--text)",
                        fontFamily: "var(--mono)", fontSize: 13,
                      }}>
                        {v.toFixed(2)}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </>
  );
}
