import {
  CartesianGrid, Legend, Line, LineChart, ResponsiveContainer,
  Tooltip, XAxis, YAxis,
} from "recharts";

// Base-100 growth of the current holdings vs the NIFTY 50 benchmark.
export default function EquityCurveChart({ data, benchmarkName }) {
  if (!data || data.length < 2) return null;

  const hasBenchmark = data.some(p => p.benchmark != null);

  return (
    <div className="card chart-card">
      <h2>Portfolio vs {benchmarkName}</h2>
      <p className="muted" style={{ fontSize: 12, marginTop: -8 }}>
        Both series rebased to 100 at the start of the stored history —
        above the benchmark line means your picks beat the index.
      </p>
      <ResponsiveContainer width="100%" height={280}>
        <LineChart data={data} margin={{ top: 10, right: 12, left: 0, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#2A3A5C" />
          <XAxis dataKey="date" stroke="#7B8794" minTickGap={40} fontSize={11} />
          <YAxis stroke="#7B8794" fontSize={11} domain={["auto", "auto"]} />
          <Tooltip />
          <Legend />
          <Line type="monotone" dataKey="portfolio" stroke="#00D4AA"
            strokeWidth={2} dot={false} name="Your Portfolio" />
          {hasBenchmark && (
            <Line type="monotone" dataKey="benchmark" stroke="#F5A623"
              strokeWidth={2} dot={false} name={benchmarkName} />
          )}
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
