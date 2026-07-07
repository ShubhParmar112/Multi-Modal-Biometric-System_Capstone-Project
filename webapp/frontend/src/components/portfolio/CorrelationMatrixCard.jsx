const LABELS = {
  equity: "Equity", debt: "Debt", gold: "Gold",
  fd: "FD", cash: "Cash", mutual_funds: "MF",
};
const ORDER = ["equity", "debt", "gold", "fd", "cash", "mutual_funds"];
const HIGH = 0.75;

// Green (diversifying) → red (concentrated) cell tint.
function cellColor(v) {
  if (v >= HIGH) return "rgba(255, 84, 112, 0.35)";
  if (v >= 0.4) return "rgba(245, 166, 35, 0.25)";
  if (v <= -0.2) return "rgba(0, 212, 170, 0.30)";
  return "transparent";
}

// Renders the 6×6 correlation matrix already returned by /asset-stats.
export default function CorrelationMatrixCard({ assetStats }) {
  const corr = assetStats?.correlation;
  if (!corr) return null;

  const highPairs = [];
  for (let i = 0; i < ORDER.length; i++) {
    for (let j = i + 1; j < ORDER.length; j++) {
      const v = corr[ORDER[i]]?.[ORDER[j]];
      if (v != null && v >= HIGH) {
        highPairs.push({ a: LABELS[ORDER[i]], b: LABELS[ORDER[j]], v });
      }
    }
  }

  return (
    <div className="card">
      <h2>Asset Correlation Matrix</h2>
      <p className="muted" style={{ fontSize: 12, marginTop: -8 }}>
        Highly correlated assets (red) move together and dilute diversification;
        negative pairs (green) hedge each other.
      </p>
      <div style={{ overflowX: "auto" }}>
        <table className="table" style={{ minWidth: 480, textAlign: "center" }}>
          <thead>
            <tr>
              <th></th>
              {ORDER.map(a => <th key={a} style={{ textAlign: "center" }}>{LABELS[a]}</th>)}
            </tr>
          </thead>
          <tbody>
            {ORDER.map(a => (
              <tr key={a}>
                <td><strong>{LABELS[a]}</strong></td>
                {ORDER.map(b => {
                  const v = corr[a]?.[b];
                  return (
                    <td key={b} style={{
                      background: a === b ? "transparent" : cellColor(v),
                      color: a === b ? "var(--muted)" : "var(--text)",
                      fontFamily: "var(--mono)", fontSize: 13,
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
  );
}
