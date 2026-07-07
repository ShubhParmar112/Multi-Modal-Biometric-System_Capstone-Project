import { useEffect, useState } from "react";
import client from "../../api/client";

// Search the local pick universes, then enter quantity + average buy price.
export default function AddHoldingModal({ onClose, onSaved }) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState([]);
  const [selected, setSelected] = useState(null);
  const [quantity, setQuantity] = useState("");
  const [price, setPrice] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!query.trim() || selected) { setResults([]); return; }
    const t = setTimeout(() => {
      client.get(`/api/portfolio/ticker-search?q=${encodeURIComponent(query)}`)
        .then(res => setResults(res.data))
        .catch(() => setResults([]));
    }, 250);
    return () => clearTimeout(t);
  }, [query, selected]);

  async function save() {
    setError("");
    if (!selected || !quantity || !price) {
      setError("Pick a security and fill in quantity and price.");
      return;
    }
    setSaving(true);
    try {
      await client.post("/api/portfolio/holdings", {
        ticker: selected.ticker,
        name: selected.name,
        quantity: Number(quantity),
        avg_buy_price: Number(price),
      });
      onSaved();
    } catch (e) {
      setError(e.response?.data?.detail || "Failed to save holding.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div style={{
      position: "fixed", inset: 0, background: "rgba(5, 8, 18, 0.65)",
      display: "flex", alignItems: "center", justifyContent: "center", zIndex: 50,
    }} onClick={onClose}>
      <div className="card" style={{ width: "min(440px, 92vw)", margin: 0 }}
        onClick={e => e.stopPropagation()}>
        <h2 style={{ marginTop: 0 }}>Add Holding</h2>

        <label className="field-label">Search NSE stocks / ETFs</label>
        <input className="input" autoFocus placeholder="e.g. Reliance, GOLDBEES, gilt…"
          value={selected ? `${selected.name} (${selected.ticker})` : query}
          onChange={e => { setSelected(null); setQuery(e.target.value); }} />

        {results.length > 0 && !selected && (
          <div style={{
            border: "1px solid var(--card-border)", borderRadius: 8,
            marginTop: 4, maxHeight: 180, overflowY: "auto",
          }}>
            {results.map(r => (
              <div key={r.ticker}
                style={{ padding: "8px 12px", cursor: "pointer", fontSize: 14 }}
                onClick={() => { setSelected(r); setResults([]); }}>
                <strong>{r.name}</strong>
                <span className="muted" style={{ marginLeft: 8, fontSize: 12 }}>
                  {r.ticker} · {r.sector}
                </span>
              </div>
            ))}
          </div>
        )}

        <div className="grid-2" style={{ gap: 12, marginTop: 8 }}>
          <div>
            <label className="field-label">Quantity</label>
            <input className="input" type="number" min="0" step="any"
              value={quantity} onChange={e => setQuantity(e.target.value)} />
          </div>
          <div>
            <label className="field-label">Avg Buy Price (₹)</label>
            <input className="input" type="number" min="0" step="any"
              value={price} onChange={e => setPrice(e.target.value)} />
          </div>
        </div>

        {error && <p className="error-text" style={{ marginBottom: 0 }}>{error}</p>}

        <div style={{ display: "flex", gap: 10, marginTop: 16, justifyContent: "flex-end" }}>
          <button className="btn" onClick={onClose}>Cancel</button>
          <button className="btn btn-primary" onClick={save} disabled={saving}>
            {saving ? "Saving…" : "Add Holding"}
          </button>
        </div>
      </div>
    </div>
  );
}
