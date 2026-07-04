import { useEffect, useState } from "react";
import {
  PieChart, Pie, Cell, Tooltip, Legend, ResponsiveContainer,
  LineChart, Line, XAxis, YAxis, CartesianGrid,
} from "recharts";
import client from "../api/client";

// ── Constants ─────────────────────────────────────────────────────────────────

const ASSET_COLORS = {
  Equity: "#00D4AA", Debt: "#4ECDC4", Gold: "#F5A623",
  FD: "#9B59B6", Cash: "#7B8794", "Mutual Funds": "#E94560",
};

const ASSET_LABELS = {
  equity: "Equity", debt: "Debt", gold: "Gold",
  fd: "FD", cash: "Cash", mutual_funds: "Mutual Funds",
};

const SECTION_ICONS = {
  equity: "📈", mutual_funds: "🏦", gold: "🥇", debt: "📋", fd: "🏛️",
};

// ── Small helpers ─────────────────────────────────────────────────────────────

function fmt(n) { return n != null ? `₹${Number(n).toLocaleString("en-IN")}` : "—"; }

function ChangeChip({ value }) {
  if (value == null) return <span className="muted">—</span>;
  const pos = value >= 0;
  return (
    <span style={{ color: pos ? "var(--primary)" : "var(--accent)", fontWeight: 600 }}>
      {pos ? "▲" : "▼"} {Math.abs(value).toFixed(2)}%
    </span>
  );
}

function SectionHeader({ icon, title, pct }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 14 }}>
      <span style={{ fontSize: 22 }}>{icon}</span>
      <div>
        <h2 style={{ margin: 0, fontSize: 17 }}>{title}</h2>
        <span className="muted" style={{ fontSize: 12 }}>
          {pct}% of your portfolio
        </span>
      </div>
    </div>
  );
}

function Badge({ text, color }) {
  return (
    <span style={{
      background: color + "22", color, border: `1px solid ${color}55`,
      borderRadius: 4, padding: "1px 7px", fontSize: 11, fontWeight: 600,
    }}>
      {text}
    </span>
  );
}

function RatingStars({ r }) {
  return <span style={{ color: "var(--warning)", fontSize: 13 }}>{r}</span>;
}

function RiskBadge({ risk }) {
  const color =
    risk?.toLowerCase().includes("very high") ? "#E94560" :
    risk?.toLowerCase().includes("high")      ? "#F5A623" :
    risk?.toLowerCase().includes("moderate")  ? "#4ECDC4" : "#00D4AA";
  return <Badge text={risk} color={color} />;
}

// ── Main component ────────────────────────────────────────────────────────────

export default function Portfolio() {
  const [profile, setProfile] = useState({
    risk_appetite: "medium", investment_horizon_years: 5,
    monthly_savings: "", available_balance: "",
  });
  const [recommendation, setRecommendation] = useState(null);
  const [frontier, setFrontier] = useState([]);
  const [assetStats, setAssetStats] = useState(null);
  const [picks, setPicks] = useState(null);
  const [picksLoading, setPicksLoading] = useState(false);
  const [profileMsg, setProfileMsg] = useState("");
  const [generating, setGenerating] = useState(false);

  // Load everything on mount
  useEffect(() => {
    async function load() {
      try {
        const res = await client.get("/api/portfolio/profile");
        const p = res.data;
        setProfile({
          risk_appetite: p.risk_appetite,
          investment_horizon_years: p.investment_horizon_years,
          monthly_savings: p.monthly_savings,
          available_balance: p.available_balance,
        });
      } catch {}

      try {
        const res = await client.get("/api/portfolio/recommendation");
        setRecommendation(res.data);
      } catch {}

      try {
        const res = await client.get("/api/portfolio/efficient-frontier");
        setFrontier(res.data);
      } catch {}

      try {
        const res = await client.get("/api/portfolio/asset-stats");
        setAssetStats(res.data);
      } catch {}
    }
    load();
  }, []);

  // Load picks whenever profile risk appetite changes and we have a recommendation
  useEffect(() => {
    if (!recommendation) return;
    loadPicks(profile.risk_appetite);
  }, [recommendation, profile.risk_appetite]);

  async function loadPicks(risk) {
    setPicksLoading(true);
    try {
      const res = await client.get(`/api/portfolio/picks?risk_appetite=${risk}`);
      setPicks(res.data);
    } catch {}
    finally { setPicksLoading(false); }
  }

  async function saveProfile() {
    setProfileMsg("");
    try {
      await client.post("/api/portfolio/profile", {
        risk_appetite: profile.risk_appetite,
        investment_horizon_years: Number(profile.investment_horizon_years),
        monthly_savings: Number(profile.monthly_savings),
        available_balance: Number(profile.available_balance),
      });
      setProfileMsg("success");
    } catch { setProfileMsg("error"); }
  }

  async function generateRecommendation() {
    setGenerating(true);
    try {
      const res = await client.post("/api/portfolio/recommendation");
      setRecommendation(res.data);
    } catch (e) {
      alert(e.response?.data?.detail || "Save a profile first.");
    } finally { setGenerating(false); }
  }

  const pieData = recommendation
    ? Object.entries(ASSET_LABELS).map(([key, label]) => ({
        name: label, value: recommendation[`${key}_pct`],
      })).filter(d => d.value > 0)
    : [];

  const assetRows = assetStats
    ? Object.keys(ASSET_LABELS).map(key => ({
        label: ASSET_LABELS[key],
        ret: (assetStats.returns[key] * 100).toFixed(2),
        vol: (assetStats.volatility[key] * 100).toFixed(2),
      }))
    : [];

  return (
    <div className="page" style={{ maxWidth: 1100 }}>
      <h1>Investment Portfolio</h1>

      {/* ── Investment Profile ──────────────────────────────────────────── */}
      <div className="card">
        <h2>Investment Profile</h2>
        <div className="grid-2" style={{ gap: 16 }}>
          <div>
            <label className="field-label">Risk Appetite</label>
            <select
              className="input"
              value={profile.risk_appetite}
              onChange={e => setProfile(p => ({ ...p, risk_appetite: e.target.value }))}
            >
              <option value="low">Low — Capital preservation</option>
              <option value="medium">Medium — Balanced growth</option>
              <option value="high">High — Aggressive growth</option>
            </select>

            <label className="field-label">Investment Horizon (Years)</label>
            <input className="input" type="number" min="1"
              value={profile.investment_horizon_years}
              onChange={e => setProfile(p => ({ ...p, investment_horizon_years: e.target.value }))} />
          </div>
          <div>
            <label className="field-label">Monthly Savings (₹)</label>
            <input className="input" type="number" min="0"
              value={profile.monthly_savings}
              onChange={e => setProfile(p => ({ ...p, monthly_savings: e.target.value }))} />

            <label className="field-label">Available Balance to Invest (₹)</label>
            <input className="input" type="number" min="0"
              value={profile.available_balance}
              onChange={e => setProfile(p => ({ ...p, available_balance: e.target.value }))} />
          </div>
        </div>
        <button className="btn btn-primary" onClick={saveProfile}>Save Profile</button>
        {profileMsg === "success" && <p className="success-text" style={{ marginTop: 8 }}>Profile saved.</p>}
        {profileMsg === "error"   && <p className="error-text"   style={{ marginTop: 8 }}>Failed to save.</p>}
      </div>

      {/* ── Generate Button ─────────────────────────────────────────────── */}
      <button className="btn btn-primary" onClick={generateRecommendation}
        disabled={generating} style={{ marginBottom: 24 }}>
        {generating ? "Optimizing portfolio…" : "Generate Recommendation"}
      </button>

      {/* ── Recommendation Output ───────────────────────────────────────── */}
      {recommendation && (
        <>
          {/* Summary KPI cards */}
          <div className="grid-3">
            <div className="card" style={{ textAlign: "center" }}>
              <p className="muted" style={{ margin: "0 0 4px" }}>Expected Annual Return</p>
              <div style={{ fontSize: 32, fontWeight: 700, color: "var(--primary)" }}>
                {recommendation.expected_return}%
              </div>
            </div>
            <div className="card" style={{ textAlign: "center" }}>
              <p className="muted" style={{ margin: "0 0 4px" }}>Expected Risk (Volatility)</p>
              <div style={{ fontSize: 32, fontWeight: 700, color: "var(--accent)" }}>
                {recommendation.expected_risk}%
              </div>
            </div>
            <div className="card" style={{ textAlign: "center" }}>
              <p className="muted" style={{ margin: "0 0 4px" }}>Sharpe Ratio</p>
              <div style={{ fontSize: 32, fontWeight: 700, color: "var(--warning)" }}>
                {recommendation.sharpe_ratio}
              </div>
            </div>
          </div>

          {/* Pie chart */}
          <div className="card chart-card">
            <h2>Optimal Asset Allocation</h2>
            <ResponsiveContainer width="100%" height={320}>
              <PieChart>
                <Pie data={pieData} dataKey="value" nameKey="name" outerRadius={120}
                  label={({ name, value }) => `${name}: ${value}%`}>
                  {pieData.map((entry, i) => (
                    <Cell key={i} fill={ASSET_COLORS[entry.name] || "#7B8794"} />
                  ))}
                </Pie>
                <Tooltip formatter={v => `${v}%`} />
                <Legend />
              </PieChart>
            </ResponsiveContainer>
          </div>

          {/* ── Specific Investment Picks ────────────────────────────────── */}
          <h2 style={{ marginTop: 4 }}>
            Specific Investment Picks
            {picksLoading && <span className="muted" style={{ fontSize: 13, marginLeft: 10 }}>fetching live data…</span>}
          </h2>

          {picks && (
            <>
              {/* ── EQUITY ─────────────────────────────────────────────── */}
              {recommendation.equity_pct > 0 && picks.equity.length > 0 && (
                <div className="card">
                  <SectionHeader icon={SECTION_ICONS.equity}
                    title={`Equity — Top NSE Picks for ${profile.risk_appetite.charAt(0).toUpperCase() + profile.risk_appetite.slice(1)} Risk (Live)`}
                    pct={recommendation.equity_pct} />
                  <p className="muted" style={{ fontSize: 12, marginTop: -8 }}>
                    Selected dynamically from live NSE data for your risk profile — low risk favours
                    stability, high risk favours momentum. Prices refresh every hour.
                  </p>
                  <div style={{ overflowX: "auto" }}>
                    <table className="table" style={{ minWidth: 760 }}>
                      <thead>
                        <tr>
                          <th>Company</th>
                          <th>Sector</th>
                          <th>Price (₹)</th>
                          <th>Day Change</th>
                          <th>1Y Return</th>
                          <th>Volatility</th>
                          <th>52W High</th>
                          <th>52W Low</th>
                        </tr>
                      </thead>
                      <tbody>
                        {picks.equity.map(s => (
                          <tr key={s.ticker}>
                            <td>
                              <strong style={{ color: "var(--text)" }}>{s.name}</strong>
                              <div style={{ fontSize: 11, color: "var(--muted)" }}>{s.ticker}</div>
                            </td>
                            <td><Badge text={s.sector} color="#4ECDC4" /></td>
                            <td style={{ fontWeight: 700 }}>₹{s.price?.toLocaleString("en-IN")}</td>
                            <td><ChangeChip value={s.change_pct} /></td>
                            <td><ChangeChip value={s.returns_1y_pct} /></td>
                            <td className="muted">
                              {s.volatility_pct != null ? `${s.volatility_pct.toFixed(1)}%` : "—"}
                            </td>
                            <td style={{ color: "var(--primary)" }}>₹{s.week52_high?.toLocaleString("en-IN")}</td>
                            <td style={{ color: "var(--accent)" }}>₹{s.week52_low?.toLocaleString("en-IN")}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}

              {/* ── MUTUAL FUNDS ────────────────────────────────────────── */}
              {recommendation.mutual_funds_pct > 0 && picks.mutual_funds.length > 0 && (
                <div className="card">
                  <SectionHeader icon={SECTION_ICONS.mutual_funds}
                    title={`Mutual Funds — ${profile.risk_appetite.charAt(0).toUpperCase() + profile.risk_appetite.slice(1)}-Risk Picks`}
                    pct={recommendation.mutual_funds_pct} />
                  <p className="muted" style={{ fontSize: 12, marginTop: -8 }}>
                    Start a SIP to invest monthly. Returns are trailing figures — past performance is not a guarantee.
                  </p>
                  <div style={{ overflowX: "auto" }}>
                    <table className="table" style={{ minWidth: 750 }}>
                      <thead>
                        <tr>
                          <th>Fund Name</th>
                          <th>Category</th>
                          <th>Rating</th>
                          <th>Risk</th>
                          <th>1Y Returns</th>
                          <th>3Y Returns</th>
                          <th>Min SIP</th>
                          <th>AUM</th>
                        </tr>
                      </thead>
                      <tbody>
                        {picks.mutual_funds.map(f => (
                          <tr key={f.name}>
                            <td><strong style={{ color: "var(--text)" }}>{f.name}</strong></td>
                            <td><Badge text={f.category} color="#9B59B6" /></td>
                            <td><RatingStars r={f.rating} /></td>
                            <td><RiskBadge risk={f.risk} /></td>
                            <td style={{ color: "var(--primary)", fontWeight: 600 }}>{f.returns_1y}%</td>
                            <td style={{ color: "var(--primary)", fontWeight: 600 }}>{f.returns_3y}%</td>
                            <td>₹{f.min_sip.toLocaleString("en-IN")}</td>
                            <td className="muted">{f.aum}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}

              {/* ── GOLD ────────────────────────────────────────────────── */}
              {recommendation.gold_pct > 0 && picks.gold.length > 0 && (
                <div className="card">
                  <SectionHeader icon={SECTION_ICONS.gold}
                    title="Gold — ETFs &amp; Sovereign Gold Bonds (Live)"
                    pct={recommendation.gold_pct} />
                  <div style={{ overflowX: "auto" }}>
                    <table className="table" style={{ minWidth: 640 }}>
                      <thead>
                        <tr>
                          <th>Instrument</th>
                          <th>Type</th>
                          <th>Price (₹/unit)</th>
                          <th>Day Change</th>
                          <th>52W High</th>
                          <th>52W Low</th>
                        </tr>
                      </thead>
                      <tbody>
                        {picks.gold.map(g => (
                          <tr key={g.ticker}>
                            <td>
                              <strong style={{ color: "var(--text)" }}>{g.name}</strong>
                              {g.note && (
                                <div style={{ fontSize: 11, color: "var(--muted)", marginTop: 3, maxWidth: 300 }}>
                                  {g.note}
                                </div>
                              )}
                            </td>
                            <td><Badge text={g.sector} color="#F5A623" /></td>
                            <td style={{ fontWeight: g.price ? 700 : 400 }}>
                              {g.price ? `₹${g.price.toLocaleString("en-IN")}` : "—"}
                            </td>
                            <td><ChangeChip value={g.change_pct} /></td>
                            <td style={{ color: "var(--primary)" }}>
                              {g.week52_high ? `₹${g.week52_high.toLocaleString("en-IN")}` : "—"}
                            </td>
                            <td style={{ color: "var(--accent)" }}>
                              {g.week52_low ? `₹${g.week52_low.toLocaleString("en-IN")}` : "—"}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}

              {/* ── DEBT ────────────────────────────────────────────────── */}
              {recommendation.debt_pct > 0 && (
                <div className="card">
                  <SectionHeader icon={SECTION_ICONS.debt}
                    title="Debt — Fixed Income Instruments"
                    pct={recommendation.debt_pct} />
                  <div style={{ overflowX: "auto" }}>
                    <table className="table" style={{ minWidth: 640 }}>
                      <thead>
                        <tr>
                          <th>Type</th>
                          <th>Instrument</th>
                          <th>Rate</th>
                          <th>Tenure</th>
                          <th>Risk</th>
                          <th>Min. Investment</th>
                        </tr>
                      </thead>
                      <tbody>
                        {picks.debt.map(d => (
                          <tr key={d.name}>
                            <td><Badge text={d.type} color="#4ECDC4" /></td>
                            <td><strong style={{ color: "var(--text)" }}>{d.name}</strong></td>
                            <td style={{ color: "var(--primary)", fontWeight: 600 }}>{d.rate}</td>
                            <td className="muted">{d.tenure}</td>
                            <td><RiskBadge risk={d.risk} /></td>
                            <td className="muted">{d.min_invest}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}

              {/* ── FIXED DEPOSITS ───────────────────────────────────────── */}
              {recommendation.fd_pct > 0 && (
                <div className="card">
                  <SectionHeader icon={SECTION_ICONS.fd}
                    title="Fixed Deposits — Best Bank Rates"
                    pct={recommendation.fd_pct} />
                  <p className="muted" style={{ fontSize: 12, marginTop: -8 }}>
                    Rates are indicative. Verify with bank before investing. DICGC insured up to ₹5L per bank.
                  </p>
                  <div style={{ overflowX: "auto" }}>
                    <table className="table" style={{ minWidth: 560 }}>
                      <thead>
                        <tr>
                          <th>Bank</th>
                          <th>1-Year Rate</th>
                          <th>3-Year Rate</th>
                          <th>5-Year Rate</th>
                          <th>Special</th>
                        </tr>
                      </thead>
                      <tbody>
                        {picks.fd.map(fd => (
                          <tr key={fd.bank}>
                            <td><strong style={{ color: "var(--text)" }}>{fd.bank}</strong></td>
                            <td style={{ color: "var(--primary)", fontWeight: 600 }}>{fd.rate_1y}%</td>
                            <td style={{ color: "var(--primary)", fontWeight: 600 }}>{fd.rate_3y}%</td>
                            <td style={{ color: "var(--primary)", fontWeight: 600 }}>{fd.rate_5y}%</td>
                            <td className="muted">{fd.special || "—"}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}
            </>
          )}
        </>
      )}

      {/* ── Efficient Frontier ────────────────────────────────────────────── */}
      {frontier.length > 0 && (
        <div className="card chart-card">
          <h2>Efficient Frontier (Markowitz)</h2>
          <p className="muted" style={{ fontSize: 12, marginTop: -8 }}>
            Each point is an optimal portfolio for its risk level. Points to the left are more conservative.
          </p>
          <ResponsiveContainer width="100%" height={300}>
            <LineChart data={frontier} margin={{ bottom: 20, left: 10, right: 20, top: 10 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#2A3A5C" />
              <XAxis dataKey="risk" stroke="#7B8794"
                label={{ value: "Risk (%)", position: "insideBottom", offset: -12, fill: "#7B8794" }} />
              <YAxis dataKey="return" stroke="#7B8794"
                label={{ value: "Return (%)", angle: -90, position: "insideLeft", fill: "#7B8794" }} />
              <Tooltip formatter={v => `${v}%`} />
              <Line type="monotone" dataKey="return" stroke="#00D4AA" dot={false}
                strokeWidth={2} name="Expected Return" />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* ── Asset Statistics ──────────────────────────────────────────────── */}
      {assetStats && (
        <div className="card">
          <h2>Asset Class Statistics</h2>
          <p className="muted" style={{ fontSize: 12, marginTop: -8 }}>
            Source: {assetStats.source} — annualised figures used by the optimizer
          </p>
          <table className="table">
            <thead>
              <tr>
                <th>Asset Class</th>
                <th>Annual Return (%)</th>
                <th>Volatility (%)</th>
                <th>Risk/Return</th>
              </tr>
            </thead>
            <tbody>
              {assetRows.map(row => {
                const ratio = row.vol > 0 ? (row.ret / row.vol).toFixed(2) : "—";
                return (
                  <tr key={row.label}>
                    <td><strong>{row.label}</strong></td>
                    <td style={{ color: "var(--primary)" }}>{row.ret}%</td>
                    <td style={{ color: "var(--accent)" }}>{row.vol}%</td>
                    <td className="muted">{ratio}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
