import { useCallback, useEffect, useState } from "react";
import client from "../../api/client";
import { useViewAs } from "../../context/ViewAsContext";
import AddHoldingModal from "./AddHoldingModal";
import EquityCurveChart from "./EquityCurveChart";
import PriceChart from "./PriceChart";

const SECTOR_COLORS = [
  "#00D4AA", "#E94560", "#F5A623", "#4ECDC4", "#9B59B6",
  "#3498DB", "#FF6B6B", "#2ECC71", "#FFD93D", "#A8DADC",
];

const fmtINR = (n) => `₹${Number(n).toLocaleString("en-IN")}`;

function PnL({ value, pct }) {
  const pos = value >= 0;
  return (
    <span style={{ color: pos ? "var(--primary)" : "var(--accent)", fontWeight: 600 }}>
      {pos ? "+" : "−"}{fmtINR(Math.abs(value))}
      {pct != null && <span style={{ fontSize: 11, marginLeft: 4 }}>({pct}%)</span>}
    </span>
  );
}

function SummaryTiles({ summary }) {
  const tiles = [
    { label: "Portfolio Value", value: fmtINR(summary.total_value), color: "var(--text)" },
    {
      label: "Total P&L",
      value: `${summary.total_pnl >= 0 ? "+" : "−"}${fmtINR(Math.abs(summary.total_pnl))}`,
      sub: `${summary.total_pnl_pct}%`,
      color: summary.total_pnl >= 0 ? "var(--primary)" : "var(--accent)",
    },
    {
      label: "Annualized Volatility",
      value: summary.volatility_pct != null ? `${summary.volatility_pct}%` : "—",
      color: "var(--warning)",
    },
    {
      label: "30-Day VaR (95%)",
      value: summary.var ? fmtINR(summary.var.var_95_amount) : "—",
      sub: summary.var ? `${summary.var.var_95_pct}%` : "refresh prices",
      color: "var(--accent)",
    },
    { label: "Positions", value: summary.positions, color: "var(--text)" },
  ];
  return (
    <div style={{
      display: "grid", gap: 14, marginBottom: 20,
      gridTemplateColumns: "repeat(auto-fit, minmax(170px, 1fr))",
    }}>
      {tiles.map(t => (
        <div key={t.label} className="card" style={{ textAlign: "center", margin: 0 }}>
          <p className="muted" style={{ margin: "0 0 4px", fontSize: 12 }}>{t.label}</p>
          <div style={{ fontSize: 22, fontWeight: 700, color: t.color }}>{t.value}</div>
          {t.sub && <span className="muted" style={{ fontSize: 11 }}>{t.sub}</span>}
        </div>
      ))}
    </div>
  );
}

function TradeForm({ holding, onDone, onCancel }) {
  const [action, setAction] = useState("BUY");
  const [quantity, setQuantity] = useState("");
  const [price, setPrice] = useState(holding.latest_price || "");
  const [error, setError] = useState("");

  async function submit() {
    setError("");
    try {
      await client.post("/api/portfolio/trades", {
        ticker: holding.ticker, action,
        price: Number(price), quantity: Number(quantity),
      });
      onDone();
    } catch (e) {
      setError(e.response?.data?.detail || "Trade failed.");
    }
  }

  return (
    <tr>
      <td colSpan={8} style={{ background: "var(--primary-dim)" }}>
        <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap", padding: "4px 0" }}>
          <select className="input" style={{ width: 90, margin: 0 }}
            value={action} onChange={e => setAction(e.target.value)}>
            <option value="BUY">BUY</option>
            <option value="SELL">SELL</option>
          </select>
          <input className="input" style={{ width: 110, margin: 0 }} type="number"
            placeholder="Qty" min="0" step="any"
            value={quantity} onChange={e => setQuantity(e.target.value)} />
          <input className="input" style={{ width: 130, margin: 0 }} type="number"
            placeholder="Price ₹" min="0" step="any"
            value={price} onChange={e => setPrice(e.target.value)} />
          <button className="btn btn-primary" style={{ padding: "6px 14px" }} onClick={submit}>
            Record {action}
          </button>
          <button className="btn" style={{ padding: "6px 14px" }} onClick={onCancel}>Cancel</button>
          {error && <span className="error-text" style={{ fontSize: 12 }}>{error}</span>}
        </div>
      </td>
    </tr>
  );
}

export default function HoldingsTab() {
  const { isViewing } = useViewAs();
  const [analytics, setAnalytics] = useState(null);
  const [trades, setTrades] = useState([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [showModal, setShowModal] = useState(false);
  const [selectedTicker, setSelectedTicker] = useState(null);
  const [tradingTicker, setTradingTicker] = useState(null);
  const [editing, setEditing] = useState(null); // {ticker, quantity, avg_buy_price}

  const load = useCallback(async () => {
    try {
      const [aRes, tRes] = await Promise.all([
        client.get("/api/portfolio/holdings/analytics"),
        client.get("/api/portfolio/trades?limit=15"),
      ]);
      setAnalytics(aRes.data);
      setTrades(tRes.data);
      setSelectedTicker(prev =>
        prev && aRes.data.holdings.some(h => h.ticker === prev)
          ? prev
          : aRes.data.holdings[0]?.ticker ?? null);
    } catch {}
    finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  async function refreshPrices() {
    setRefreshing(true);
    try {
      await client.post("/api/portfolio/holdings/prices/refresh", null,
        { timeout: 120000 });
      await load();
    } catch {}
    finally { setRefreshing(false); }
  }

  async function saveEdit() {
    try {
      await client.patch(`/api/portfolio/holdings/${encodeURIComponent(editing.ticker)}`, {
        quantity: Number(editing.quantity),
        avg_buy_price: Number(editing.avg_buy_price),
      });
      setEditing(null);
      await load();
    } catch (e) {
      alert(e.response?.data?.detail || "Update failed.");
    }
  }

  async function deleteHolding(ticker) {
    if (!confirm(`Remove ${ticker.replace(".NS", "")} from your holdings?`)) return;
    try {
      await client.delete(`/api/portfolio/holdings/${encodeURIComponent(ticker)}`);
      await load();
    } catch {}
  }

  if (loading) return <div className="spinner" />;

  const holdings = analytics?.holdings ?? [];
  const summary = analytics?.summary;
  const selected = holdings.find(h => h.ticker === selectedTicker);

  return (
    <>
      {/* Header actions */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 10, marginBottom: 16 }}>
        <p className="muted" style={{ margin: 0, fontSize: 13 }}>
          Track the securities you actually own — P&L and risk update from stored NSE closes.
        </p>
        {!isViewing && (
          <div style={{ display: "flex", gap: 8 }}>
            <button className="btn" onClick={refreshPrices} disabled={refreshing || holdings.length === 0}>
              {refreshing ? "Fetching prices…" : "⟳ Refresh Prices"}
            </button>
            <button className="btn btn-primary" onClick={() => setShowModal(true)}>
              + Add Holding
            </button>
          </div>
        )}
      </div>

      {analytics?.warnings?.map((w, i) => (
        <p key={i} style={{
          background: "rgba(245, 166, 35, 0.12)", border: "1px solid rgba(245, 166, 35, 0.4)",
          borderRadius: 8, padding: "8px 12px", fontSize: 13,
        }}>⚠️ {w}</p>
      ))}

      {holdings.length === 0 ? (
        <div className="card" style={{ textAlign: "center", padding: 40 }}>
          <p style={{ fontSize: 15 }}>No holdings yet.</p>
          <p className="muted">Add the stocks, ETFs or funds you own to see live P&L,
            risk analytics and a benchmark comparison.</p>
        </div>
      ) : (
        <>
          {summary && <SummaryTiles summary={summary} />}

          {/* Holdings table */}
          <div className="card">
            <h2>My Holdings</h2>
            <div style={{ overflowX: "auto" }}>
              <table className="table" style={{ minWidth: 820 }}>
                <thead>
                  <tr>
                    <th>Security</th><th>Qty</th><th>Avg Buy</th><th>Latest</th>
                    <th>Value</th><th>P&L</th><th>Weight</th><th style={{ textAlign: "right" }}>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {holdings.map(h => (
                    <HoldingRows key={h.ticker} h={h} readOnly={isViewing}
                      editing={editing} setEditing={setEditing} saveEdit={saveEdit}
                      tradingTicker={tradingTicker} setTradingTicker={setTradingTicker}
                      selectedTicker={selectedTicker} setSelectedTicker={setSelectedTicker}
                      deleteHolding={deleteHolding} load={load} />
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          {/* Price chart of the selected holding */}
          {selected && (
            <PriceChart ticker={selected.ticker} avgBuyPrice={selected.avg_buy_price} />
          )}

          {/* Equity curve vs benchmark */}
          <EquityCurveChart data={analytics.equity_curve}
            benchmarkName={analytics.benchmark_name} />

          {/* Sector allocation (text) + diversification verdict */}
          <div className="grid-2">
            {analytics.sector_allocation.length > 0 && (
              <div className="card">
                <h2>Sector Allocation</h2>
                <p className="muted" style={{ fontSize: 12, marginTop: -8 }}>
                  Portfolio weight per sector, from your holdings' sector metadata.
                </p>
                {analytics.sector_allocation.map((s, i) => (
                  <div key={s.sector} style={{ marginBottom: 10 }}>
                    <div style={{
                      display: "flex", justifyContent: "space-between",
                      alignItems: "baseline", marginBottom: 4, fontSize: 14,
                    }}>
                      <span>
                        <span style={{
                          display: "inline-block", width: 10, height: 10,
                          borderRadius: 3, marginRight: 8,
                          background: SECTOR_COLORS[i % SECTOR_COLORS.length],
                        }} />
                        <strong>{s.sector}</strong>
                        <span className="muted" style={{ fontSize: 12, marginLeft: 8 }}>
                          {fmtINR(s.value)}
                        </span>
                      </span>
                      <strong>{s.pct}%</strong>
                    </div>
                    <div style={{
                      height: 6, borderRadius: 3,
                      background: "var(--card-border)", overflow: "hidden",
                    }}>
                      <div style={{
                        width: `${Math.min(s.pct, 100)}%`, height: "100%",
                        background: SECTOR_COLORS[i % SECTOR_COLORS.length],
                      }} />
                    </div>
                  </div>
                ))}
              </div>
            )}

            <div className="card">
              <h2>Diversification Check</h2>
              {analytics.diversification && (
                <div style={{
                  display: "inline-flex", alignItems: "center", gap: 8,
                  padding: "6px 14px", borderRadius: 8, marginBottom: 12,
                  fontWeight: 700, fontSize: 14,
                  background: analytics.diversification.status === "pass"
                    ? "rgba(0, 212, 170, 0.14)" : "rgba(245, 166, 35, 0.14)",
                  border: analytics.diversification.status === "pass"
                    ? "1px solid rgba(0, 212, 170, 0.4)"
                    : "1px solid rgba(245, 166, 35, 0.4)",
                  color: analytics.diversification.status === "pass"
                    ? "var(--primary)" : "var(--warning)",
                }}>
                  {analytics.diversification.status === "pass"
                    ? "✓ Well diversified" : "⚠ Concentration risk"}
                </div>
              )}
              {analytics.diversification?.checks.map((c, i) => (
                <div key={i} style={{ display: "flex", gap: 8, marginBottom: 8, fontSize: 13 }}>
                  <span style={{
                    color: c.status === "pass" ? "var(--primary)" : "var(--warning)",
                    flexShrink: 0,
                  }}>
                    {c.status === "pass" ? "✓" : "⚠"}
                  </span>
                  <span>
                    <strong>{c.label}:</strong>{" "}
                    <span className="muted">{c.detail}</span>
                  </span>
                </div>
              ))}

              {analytics.correlation_pairs.length > 0 && (
                <>
                  <p className="muted" style={{ fontSize: 12, margin: "14px 0 6px" }}>
                    Pairwise correlations (above 0.75 move together):
                  </p>
                  <table className="table">
                    <thead>
                      <tr><th>Pair</th><th style={{ textAlign: "right" }}>Correlation</th></tr>
                    </thead>
                    <tbody>
                      {analytics.correlation_pairs.slice(0, 8).map((p, i) => (
                        <tr key={i}>
                          <td>
                            {p.ticker_a.replace(".NS", "")} × {p.ticker_b.replace(".NS", "")}
                            {p.high && <span style={{ marginLeft: 6 }}>⚠️</span>}
                          </td>
                          <td style={{
                            textAlign: "right", fontFamily: "var(--mono)",
                            color: p.high ? "var(--accent)" : "var(--text)",
                          }}>
                            {p.correlation.toFixed(2)}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </>
              )}
            </div>
          </div>

          {/* Trade log */}
          {trades.length > 0 && (
            <div className="card">
              <h2>Recent Trades</h2>
              <table className="table">
                <thead>
                  <tr><th>Date</th><th>Security</th><th>Action</th><th>Qty</th><th>Price</th></tr>
                </thead>
                <tbody>
                  {trades.map(t => (
                    <tr key={t.trade_id}>
                      <td className="muted">{(t.traded_at || "").slice(0, 10)}</td>
                      <td>{t.ticker.replace(".NS", "")}</td>
                      <td style={{
                        color: t.action === "BUY" ? "var(--primary)" : "var(--accent)",
                        fontWeight: 600,
                      }}>{t.action}</td>
                      <td>{t.quantity}</td>
                      <td>{fmtINR(t.price)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}

      {showModal && (
        <AddHoldingModal onClose={() => setShowModal(false)}
          onSaved={() => { setShowModal(false); load(); }} />
      )}
    </>
  );
}

function HoldingRows({ h, readOnly, editing, setEditing, saveEdit, tradingTicker,
                       setTradingTicker, selectedTicker, setSelectedTicker,
                       deleteHolding, load }) {
  const isEditing = editing?.ticker === h.ticker;
  return (
    <>
      <tr style={{
        cursor: "pointer",
        background: selectedTicker === h.ticker ? "var(--primary-dim)" : "transparent",
      }} onClick={() => setSelectedTicker(h.ticker)}>
        <td>
          <strong style={{ color: "var(--text)" }}>{h.name}</strong>
          <div style={{ fontSize: 11, color: "var(--muted)" }}>
            {h.ticker.replace(".NS", "")} · {h.sector}
          </div>
        </td>
        <td>
          {isEditing ? (
            <input className="input" style={{ width: 80, margin: 0 }} type="number" step="any"
              value={editing.quantity}
              onClick={e => e.stopPropagation()}
              onChange={e => setEditing({ ...editing, quantity: e.target.value })} />
          ) : h.quantity}
        </td>
        <td>
          {isEditing ? (
            <input className="input" style={{ width: 100, margin: 0 }} type="number" step="any"
              value={editing.avg_buy_price}
              onClick={e => e.stopPropagation()}
              onChange={e => setEditing({ ...editing, avg_buy_price: e.target.value })} />
          ) : fmtINR(h.avg_buy_price)}
        </td>
        <td>
          {fmtINR(h.latest_price)}
          {h.is_estimated && (
            <span title="No stored price — using buy price"
              style={{ color: "var(--warning)", marginLeft: 4 }}>≈</span>
          )}
        </td>
        <td style={{ fontWeight: 600 }}>{fmtINR(h.market_value)}</td>
        <td><PnL value={h.pnl} pct={h.pnl_pct} /></td>
        <td className="muted">{h.weight_pct}%</td>
        <td style={{ textAlign: "right", whiteSpace: "nowrap" }}
          onClick={e => e.stopPropagation()}>
          {readOnly ? (
            <span className="muted" style={{ fontSize: 11 }}>read-only</span>
          ) : isEditing ? (
            <>
              <button className="btn btn-primary" style={{ padding: "4px 10px", fontSize: 12 }}
                onClick={saveEdit}>Save</button>{" "}
              <button className="btn" style={{ padding: "4px 10px", fontSize: 12 }}
                onClick={() => setEditing(null)}>Cancel</button>
            </>
          ) : (
            <>
              <button className="btn" style={{ padding: "4px 10px", fontSize: 12 }}
                title="Record a BUY or SELL"
                onClick={() => setTradingTicker(
                  tradingTicker === h.ticker ? null : h.ticker)}>Trade</button>{" "}
              <button className="btn" style={{ padding: "4px 10px", fontSize: 12 }}
                title="Edit quantity / avg price"
                onClick={() => setEditing({
                  ticker: h.ticker, quantity: h.quantity,
                  avg_buy_price: h.avg_buy_price,
                })}>✎</button>{" "}
              <button className="btn" style={{ padding: "4px 10px", fontSize: 12, color: "var(--accent)" }}
                title="Remove holding"
                onClick={() => deleteHolding(h.ticker)}>✕</button>
            </>
          )}
        </td>
      </tr>
      {tradingTicker === h.ticker && (
        <TradeForm holding={h}
          onDone={() => { setTradingTicker(null); load(); }}
          onCancel={() => setTradingTicker(null)} />
      )}
    </>
  );
}
