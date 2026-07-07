import { useEffect, useState } from "react";
import client from "../../api/client";

const fmtINR = (n) => `₹${Number(n).toLocaleString("en-IN")}`;

// 30-day Monte-Carlo Value-at-Risk on the latest recommendation.
// `refreshKey` re-fetches whenever a new recommendation is generated.
export default function VarCard({ refreshKey }) {
  const [varData, setVarData] = useState(null);

  useEffect(() => {
    let cancelled = false;
    client.get("/api/portfolio/var")
      .then(res => { if (!cancelled) setVarData(res.data); })
      .catch(() => { if (!cancelled) setVarData(null); });
    return () => { cancelled = true; };
  }, [refreshKey]);

  if (!varData) return null;

  return (
    <div className="card">
      <h2>Value at Risk — {varData.horizon_days}-Day Monte Carlo</h2>
      <p className="muted" style={{ fontSize: 12, marginTop: -8 }}>
        {varData.simulations.toLocaleString()} correlated simulations of your
        recommended allocation on {fmtINR(varData.amount)} invested.
      </p>
      <div className="grid-3">
        <div style={{ textAlign: "center" }}>
          <p className="muted" style={{ margin: "0 0 4px" }}>95% VaR</p>
          <div style={{ fontSize: 26, fontWeight: 700, color: "var(--accent)" }}>
            {fmtINR(varData.var_95_amount)}
          </div>
          <span className="muted" style={{ fontSize: 12 }}>
            {varData.var_95_pct}% — worst month in 20
          </span>
        </div>
        <div style={{ textAlign: "center" }}>
          <p className="muted" style={{ margin: "0 0 4px" }}>99% VaR</p>
          <div style={{ fontSize: 26, fontWeight: 700, color: "var(--accent)" }}>
            {fmtINR(varData.var_99_amount)}
          </div>
          <span className="muted" style={{ fontSize: 12 }}>
            {varData.var_99_pct}% — worst month in 100
          </span>
        </div>
        <div style={{ textAlign: "center" }}>
          <p className="muted" style={{ margin: "0 0 4px" }}>Expected 30-Day Return</p>
          <div style={{ fontSize: 26, fontWeight: 700, color: "var(--primary)" }}>
            {varData.expected_return_pct}%
          </div>
          <span className="muted" style={{ fontSize: 12 }}>simulation mean</span>
        </div>
      </div>
    </div>
  );
}
