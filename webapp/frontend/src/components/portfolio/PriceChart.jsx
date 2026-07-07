import { useEffect, useState } from "react";
import {
  Area, AreaChart, CartesianGrid, ReferenceLine, ResponsiveContainer,
  Tooltip, XAxis, YAxis,
} from "recharts";
import client from "../../api/client";

const RANGES = [
  { label: "1M", days: 22 },
  { label: "3M", days: 66 },
  { label: "6M", days: 132 },
  { label: "1Y", days: 260 },
  { label: "All", days: null },
];

// Stored daily closes for one holding with range buttons and an
// average-buy-price reference line.
export default function PriceChart({ ticker, avgBuyPrice }) {
  const [history, setHistory] = useState([]);
  const [range, setRange] = useState("6M");

  useEffect(() => {
    if (!ticker) return;
    let cancelled = false;
    client.get(`/api/portfolio/holdings/prices/${encodeURIComponent(ticker)}`)
      .then(res => { if (!cancelled) setHistory(res.data); })
      .catch(() => { if (!cancelled) setHistory([]); });
    return () => { cancelled = true; };
  }, [ticker]);

  if (!ticker) return null;

  const days = RANGES.find(r => r.label === range)?.days;
  const data = (days ? history.slice(-days) : history).map(row => ({
    date: row.price_date,
    close: row.close_price,
  }));

  return (
    <div className="card chart-card">
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 8 }}>
        <h2 style={{ margin: 0 }}>{ticker.replace(".NS", "")} — Price History</h2>
        <div style={{ display: "flex", gap: 4 }}>
          {RANGES.map(r => (
            <button key={r.label}
              className={r.label === range ? "btn btn-primary" : "btn"}
              style={{ padding: "3px 10px", fontSize: 12 }}
              onClick={() => setRange(r.label)}>
              {r.label}
            </button>
          ))}
        </div>
      </div>
      {data.length === 0 ? (
        <p className="muted">No stored prices yet — hit “Refresh Prices”.</p>
      ) : (
        <ResponsiveContainer width="100%" height={280}>
          <AreaChart data={data} margin={{ top: 10, right: 12, left: 0, bottom: 0 }}>
            <defs>
              <linearGradient id="priceFill" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="#00D4AA" stopOpacity={0.35} />
                <stop offset="100%" stopColor="#00D4AA" stopOpacity={0.02} />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke="#2A3A5C" />
            <XAxis dataKey="date" stroke="#7B8794" minTickGap={40} fontSize={11} />
            <YAxis stroke="#7B8794" fontSize={11} width={70}
              domain={["auto", "auto"]}
              tickFormatter={v => `₹${Number(v).toLocaleString("en-IN")}`} />
            <Tooltip formatter={v => [`₹${Number(v).toLocaleString("en-IN")}`, "Close"]} />
            {avgBuyPrice > 0 && (
              <ReferenceLine y={avgBuyPrice} stroke="#F5A623" strokeDasharray="6 4"
                label={{ value: "avg buy", fill: "#F5A623", fontSize: 11, position: "insideTopRight" }} />
            )}
            <Area type="monotone" dataKey="close" stroke="#00D4AA"
              strokeWidth={2} fill="url(#priceFill)" />
          </AreaChart>
        </ResponsiveContainer>
      )}
    </div>
  );
}
