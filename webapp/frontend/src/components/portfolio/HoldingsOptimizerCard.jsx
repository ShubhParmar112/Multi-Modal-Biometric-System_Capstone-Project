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

const HIGH_CORR = 0.75;

// Continuous diverging heatmap tint — identical to the Asset Correlation
// Matrix card: positive correlations shade red (move together /
// concentration), negative shade green (hedge), intensity scales with the
// magnitude so every cell is coloured.
function cellColor(v) {
  if (v == null) return "transparent";
  const mag = Math.min(Math.abs(v), 1);
  const alpha = 0.08 + 0.72 * mag;
  return v >= 0
    ? `rgba(233, 69, 96, ${alpha.toFixed(3)})`   // red
    : `rgba(0, 212, 170, ${alpha.toFixed(3)})`;  // green
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

  // One stable color per ticker so both pies (and the legend) stay in sync.
  const colorByName = {};
  data.allocation.forEach((a, i) => {
    colorByName[short(a.ticker)] = COLORS[i % COLORS.length];
  });
  const currentPieData = data.allocation
    .filter((a) => a.current_weight_pct > 0)
    .map((a) => ({ name: short(a.ticker), value: a.current_weight_pct }));
  const targetPieData = data.allocation
    .filter((a) => a.target_weight_pct > 0)
    .map((a) => ({ name: short(a.ticker), value: a.target_weight_pct }));
  const corr = data.correlation;

  // Highly correlated (non-diagonal) pairs, for the concentration-risk note.
  const highPairs = [];
  for (let i = 0; i < corr.tickers.length; i++) {
    for (let j = i + 1; j < corr.tickers.length; j++) {
      const v = corr.matrix[i][j];
      if (v != null && v >= HIGH_CORR) {
        highPairs.push({ a: short(corr.tickers[i]), b: short(corr.tickers[j]), v });
      }
    }
  }

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

        <div className="grid-2" style={{ alignItems: "stretch", marginBottom: 16 }}>
          <div className="card" style={{ margin: 0 }}>
            <p className="muted" style={{
              textAlign: "center", margin: "8px 0 0", fontSize: 12,
              textTransform: "uppercase", letterSpacing: 0.6,
            }}>Current Holdings</p>
            <ResponsiveContainer width="100%" height={300}>
              <PieChart margin={{ top: 24, bottom: 8, left: 8, right: 8 }}>
                <Pie data={currentPieData} dataKey="value" nameKey="name" outerRadius={90}
                  label={({ name, value }) => `${name}: ${value}%`}>
                  {currentPieData.map((d, i) => (
                    <Cell key={i} fill={colorByName[d.name]} />
                  ))}
                </Pie>
                <Tooltip formatter={(v) => `${v}%`} />
                <Legend />
              </PieChart>
            </ResponsiveContainer>
          </div>

          <div className="card" style={{ margin: 0 }}>
            <p className="muted" style={{
              textAlign: "center", margin: "8px 0 0", fontSize: 12,
              textTransform: "uppercase", letterSpacing: 0.6,
            }}>Optimized Target</p>
            <ResponsiveContainer width="100%" height={300}>
              <PieChart margin={{ top: 24, bottom: 8, left: 8, right: 8 }}>
                <Pie data={targetPieData} dataKey="value" nameKey="name" outerRadius={90}
                  label={({ name, value }) => `${name}: ${value}%`}>
                  {targetPieData.map((d, i) => (
                    <Cell key={i} fill={colorByName[d.name]} />
                  ))}
                </Pie>
                <Tooltip formatter={(v) => `${v}%`} />
                <Legend />
              </PieChart>
            </ResponsiveContainer>
          </div>
        </div>

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
          Highly correlated holdings (red) move together and dilute
          diversification; negative pairs (green) hedge each other. From the
          same stored price history the optimizer uses.
        </p>
        <div style={{ overflowX: "auto" }}>
          <table style={{
            minWidth: 420, borderCollapse: "separate", borderSpacing: 3,
            textAlign: "center", margin: "8px auto 4px",
          }}>
            <thead>
              <tr>
                <th></th>
                {corr.tickers.map((t) => (
                  <th key={t} style={{
                    padding: "6px 8px", fontSize: 12, fontWeight: 600,
                    color: "var(--muted)", textTransform: "uppercase",
                    letterSpacing: 0.4,
                  }}>{short(t)}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {corr.tickers.map((a, i) => (
                <tr key={a}>
                  <td style={{
                    padding: "6px 10px", fontSize: 12, fontWeight: 600,
                    textAlign: "right", color: "var(--muted)",
                    textTransform: "uppercase", letterSpacing: 0.4,
                  }}>{short(a)}</td>
                  {corr.tickers.map((b, j) => {
                    const v = corr.matrix[i][j];
                    const diag = i === j;
                    return (
                      <td key={b} style={{
                        width: 56, height: 44, borderRadius: 6,
                        background: diag ? "var(--card-border)" : cellColor(v),
                        color: diag ? "var(--muted)" : "var(--text)",
                        fontFamily: "var(--mono)", fontSize: 13,
                        fontWeight: diag ? 400 : 600, textAlign: "center",
                      }}>
                        {v != null ? v.toFixed(2) : "—"}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {highPairs.length > 0 && (
          <p style={{ fontSize: 13, marginBottom: 0 }}>
            ⚠️ <strong>Concentration risk:</strong>{" "}
            {highPairs.map(p => `${p.a} & ${p.b} (${p.v.toFixed(2)})`).join(", ")} move
            almost in lockstep — treat them as one risk bucket.
          </p>
        )}
      </div>
    </>
  );
}
