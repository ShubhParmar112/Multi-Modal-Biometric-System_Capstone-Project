import { useEffect, useState } from "react";
import client from "../../api/client";

const fmtINR = (n) => `₹${Number(n).toLocaleString("en-IN")}`;

const BUCKET_ICONS = {
  equity: "📈", mutual_funds: "🏦", gold: "🥇",
  debt: "📋", fd: "🏛️", cash: "💵",
};

// Smart Investment Plan: converts the recommended percentages into exact
// whole-unit purchases from the live picks. Re-fetches on `refreshKey`.
export default function InvestmentPlanCard({ refreshKey }) {
  const [plan, setPlan] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    client.get("/api/portfolio/investment-plan")
      .then(res => { if (!cancelled) { setPlan(res.data); setError(""); } })
      .catch(e => {
        if (!cancelled) {
          setPlan(null);
          setError(e.response?.data?.detail || "");
        }
      });
    return () => { cancelled = true; };
  }, [refreshKey]);

  if (!plan) {
    return error ? (
      <div className="card">
        <h2>Smart Investment Plan</h2>
        <p className="muted" style={{ marginBottom: 0 }}>{error}</p>
      </div>
    ) : null;
  }

  return (
    <div className="card">
      <h2>Smart Investment Plan</h2>
      <p className="muted" style={{ fontSize: 12, marginTop: -8 }}>
        Your {fmtINR(plan.total_amount)} converted into exact units of the live picks —
        whole shares for exchange-traded instruments, fractional units for funds.
      </p>

      {plan.buckets.map(bucket => (
        <div key={bucket.asset} style={{ marginBottom: 18 }}>
          <div style={{ display: "flex", alignItems: "baseline", gap: 8, marginBottom: 6 }}>
            <span>{BUCKET_ICONS[bucket.asset]}</span>
            <strong>{bucket.label}</strong>
            <span className="muted" style={{ fontSize: 12 }}>
              {bucket.pct}% → {fmtINR(bucket.amount)}
            </span>
          </div>
          <table className="table">
            <tbody>
              {bucket.items.map((item, i) => (
                <tr key={i}>
                  <td>{item.name}</td>
                  <td className="muted">
                    {item.units != null
                      ? `${item.units} × ${fmtINR(item.price)}`
                      : ""}
                  </td>
                  <td style={{ textAlign: "right", fontWeight: 600 }}>
                    {fmtINR(item.cost)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ))}

      <div style={{
        display: "flex", justifyContent: "space-between", flexWrap: "wrap",
        gap: 8, borderTop: "1px solid var(--card-border)", paddingTop: 12,
      }}>
        <span>Deployed: <strong style={{ color: "var(--primary)" }}>
          {fmtINR(plan.total_invested)}</strong></span>
        <span className="muted">
          Rounding leftover to cash: {fmtINR(plan.total_uninvested)}
        </span>
      </div>
    </div>
  );
}
