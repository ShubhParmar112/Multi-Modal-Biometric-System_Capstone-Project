const LABELS = {
  equity: "Equity", debt: "Debt", gold: "Gold",
  fd: "FD", cash: "Cash", mutual_funds: "MF",
};
const ORDER = ["equity", "debt", "gold", "fd", "cash", "mutual_funds"];
const HIGH = 0.75;

// Continuous diverging heatmap tint: positive correlations shade red
// (move together / concentration), negative shade green (hedge), and the
// intensity scales with the magnitude so every cell is coloured.
function cellColor(v) {
  if (v == null) return "transparent";
  const mag = Math.min(Math.abs(v), 1);
  const alpha = 0.08 + 0.72 * mag;
  return v >= 0
    ? `rgba(233, 69, 96, ${alpha.toFixed(3)})`   // red
    : `rgba(0, 212, 170, ${alpha.toFixed(3)})`;  // green
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
        <table style={{
          minWidth: 480, borderCollapse: "separate", borderSpacing: 3,
          textAlign: "center", margin: "8px auto 4px",
        }}>
          <thead>
            <tr>
              <th></th>
              {ORDER.map(a => (
                <th key={a} style={{
                  padding: "6px 8px", fontSize: 12, fontWeight: 600,
                  color: "var(--muted)", textTransform: "uppercase", letterSpacing: 0.4,
                }}>{LABELS[a]}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {ORDER.map(a => (
              <tr key={a}>
                <td style={{
                  padding: "6px 10px", fontSize: 12, fontWeight: 600, textAlign: "right",
                  color: "var(--muted)", textTransform: "uppercase", letterSpacing: 0.4,
                }}>{LABELS[a]}</td>
                {ORDER.map(b => {
                  const v = corr[a]?.[b];
                  const diag = a === b;
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
  );
}
