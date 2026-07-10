import { useEffect, useState } from "react";
import {
  PieChart, Pie, Cell, Tooltip, Legend, ResponsiveContainer,
  LineChart, Line, XAxis, YAxis, CartesianGrid,
} from "recharts";
import client from "../api/client";
import MiniAdvisor from "../components/MiniAdvisor";
import CorrelationMatrixCard from "../components/portfolio/CorrelationMatrixCard";
import HoldingsOptimizerCard from "../components/portfolio/HoldingsOptimizerCard";
import HoldingsTab from "../components/portfolio/HoldingsTab";
import InvestmentPlanCard from "../components/portfolio/InvestmentPlanCard";
import VarCard from "../components/portfolio/VarCard";
import { useViewAs } from "../context/ViewAsContext";

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

// Each pick section is tinted with a very soft pastel of the same colour that
// asset gets in the allocation pie chart, so the section and its pie slice
// read as the same asset at a glance.
const ASSET_SECTION_COLORS = {
  equity: ASSET_COLORS.Equity,
  mutual_funds: ASSET_COLORS["Mutual Funds"],
  gold: ASSET_COLORS.Gold,
  debt: ASSET_COLORS.Debt,
  fd: ASSET_COLORS.FD,
};

// ── Small helpers ─────────────────────────────────────────────────────────────

function fmt(n) { return n != null ? `₹${Number(n).toLocaleString("en-IN")}` : "—"; }

// Soft pastel card background + matching subtle border from an asset colour
// (8-bit hex alpha suffixes: 1A ≈ 10%, 33 ≈ 20%).
function softCard(color) {
  return { background: `${color}1A`, borderColor: `${color}33` };
}

// Average FD rate across all banks for one column. Each bank publishes a
// "lo% – hi%" range, so we take each bank's midpoint and average those.
function avgFdRate(fdRows, key) {
  const mids = [];
  for (const r of fdRows || []) {
    const nums = String(r[key] || "").match(/\d+(?:\.\d+)?/g);
    if (!nums || !nums.length) continue;
    mids.push(nums.map(Number).reduce((a, b) => a + b, 0) / nums.length);
  }
  if (!mids.length) return null;
  return mids.reduce((a, b) => a + b, 0) / mids.length;
}

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

function RiskBadge({ risk }) {
  const color =
    risk?.toLowerCase().includes("very high") ? "#E94560" :
    risk?.toLowerCase().includes("high")      ? "#F5A623" :
    risk?.toLowerCase().includes("moderate")  ? "#4ECDC4" : "#00D4AA";
  return <Badge text={risk} color={color} />;
}

// ── Main component ────────────────────────────────────────────────────────────

function TabSwitcher({ view, setView }) {
  const tabs = [
    { id: "optimizer", label: "Optimizer" },
    { id: "holdings", label: "My Holdings" },
  ];
  return (
    <div style={{
      display: "flex", gap: 30, marginBottom: 24,
      borderBottom: "1px solid var(--card-border)",
    }}>
      {tabs.map(t => {
        const active = view === t.id;
        return (
          <button key={t.id}
            onClick={() => setView(t.id)}
            style={{
              background: "none", border: "none", cursor: "pointer",
              padding: "10px 2px", fontSize: 17, fontWeight: 600,
              color: active ? "var(--primary)" : "var(--text)",
              borderBottom: active
                ? "3px solid var(--primary)"
                : "3px solid transparent",
              marginBottom: -1, transition: "color .15s",
            }}>
            {t.label}
          </button>
        );
      })}
    </div>
  );
}

// Prev / Next pager for the two sub-pages of the Optimizer tab: PREV on the
// far left, the page label centred, NEXT on the far right. Buttons turn theme
// cyan on hover (see `.pager-btn` in index.css). Rendered both above and below
// the page content for easier reach. `edge` ("top" | "bottom") only tweaks
// spacing.
function OptimizerPager({ page, setPage, edge = "top" }) {
  const PAGES = ["Optimizer & Analytics", "Specific Investment Picks"];
  const last = PAGES.length - 1;
  return (
    <div className="pager" style={
      edge === "top" ? { marginBottom: 20 } : { marginTop: 24 }
    }>
      <button className="pager-btn" disabled={page === 0}
        onClick={() => setPage(p => Math.max(0, p - 1))}>
        ‹ PREV
      </button>
      <span className="pager-label">
        Page {page + 1} of {PAGES.length} · {PAGES[page]}
      </span>
      <button className="pager-btn" disabled={page === last}
        onClick={() => setPage(p => Math.min(last, p + 1))}>
        NEXT ›
      </button>
    </div>
  );
}

export default function Portfolio() {
  const { isViewing } = useViewAs();
  const [view, setView] = useState("optimizer");
  const [optimizerPage, setOptimizerPage] = useState(0);
  const [profile, setProfile] = useState({
    risk_appetite: "medium", investment_horizon_years: 5,
    monthly_savings: "", available_balance: "",
  });
  const [recommendation, setRecommendation] = useState(null);
  const [previewAlloc, setPreviewAlloc] = useState(null);
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

  // Live-preview the optimal allocation for the selected risk appetite so the
  // pie chart / KPIs / picks reflect the dropdown without needing to re-save
  // and re-generate. Only relevant once a recommendation exists (section shown).
  useEffect(() => {
    if (!recommendation) return;
    let cancelled = false;
    client.get(`/api/portfolio/allocation-preview?risk_appetite=${profile.risk_appetite}`)
      .then(res => { if (!cancelled) setPreviewAlloc(res.data); })
      .catch(() => { if (!cancelled) setPreviewAlloc(null); });
    return () => { cancelled = true; };
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

  // The live allocation driving the pie / KPIs / picks: the preview for the
  // currently-selected risk appetite, falling back to the saved recommendation.
  const alloc = previewAlloc || recommendation;

  const pieData = alloc
    ? Object.entries(ASSET_LABELS).map(([key, label]) => ({
        name: label, value: alloc[`${key}_pct`],
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
    <div className="page has-advisor" style={{ maxWidth: 1100 }}>
      <h1>Investment Portfolio</h1>
      <TabSwitcher view={view} setView={setView} />

      {view === "holdings" && (
        <div className="tab-pane"><HoldingsTab /></div>
      )}

      {view === "optimizer" && (
      <div className="tab-pane">
      {/* ── Prev / Next pager for the two optimizer sub-pages (top) ─────── */}
      <OptimizerPager page={optimizerPage} setPage={setOptimizerPage} edge="top" />

      {/* ═══ PAGE 1 — Optimizer & Analytics ═════════════════════════════ */}
      {optimizerPage === 0 && (
      <div className="tab-pane">
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
        {!isViewing && (
          <button className="btn btn-primary" onClick={saveProfile}>Save Profile</button>
        )}
        {profileMsg === "success" && <p className="success-text" style={{ marginTop: 8 }}>Profile saved.</p>}
        {profileMsg === "error"   && <p className="error-text"   style={{ marginTop: 8 }}>Failed to save.</p>}
      </div>

      {/* ── Holdings-driven optimizer (dynamic, from real data) ─────────── */}
      <HoldingsOptimizerCard defaultAmount={profile.available_balance} />

      {/* ── Generate Button ─────────────────────────────────────────────── */}
      {!isViewing && (
        <button className="btn btn-primary" onClick={generateRecommendation}
          disabled={generating} style={{ marginBottom: 24 }}>
          {generating ? "Optimizing portfolio…" : "Generate Recommendation"}
        </button>
      )}

      {/* ── Recommendation Output ───────────────────────────────────────── */}
      {alloc && (
        <>
          {/* Summary KPI cards — reflect the selected risk appetite live */}
          <div className="grid-3">
            <div className="card" style={{ textAlign: "center" }}>
              <p className="muted" style={{ margin: "0 0 4px" }}>Expected Annual Return</p>
              <div style={{ fontSize: 32, fontWeight: 700, color: "var(--primary)" }}>
                {alloc.expected_return}%
              </div>
            </div>
            <div className="card" style={{ textAlign: "center" }}>
              <p className="muted" style={{ margin: "0 0 4px" }}>Expected Risk (Volatility)</p>
              <div style={{ fontSize: 32, fontWeight: 700, color: "var(--accent)" }}>
                {alloc.expected_risk}%
              </div>
            </div>
            <div className="card" style={{ textAlign: "center" }}>
              <p className="muted" style={{ margin: "0 0 4px" }}>Sharpe Ratio</p>
              <div style={{ fontSize: 32, fontWeight: 700, color: "var(--warning)" }}>
                {alloc.sharpe_ratio}
              </div>
            </div>
          </div>

          {/* Monte-Carlo Value-at-Risk on this allocation */}
          <VarCard refreshKey={recommendation} />

          {/* Pie chart — extra margin + labelLine so outer labels (e.g. Gold
              at the top) never overlap the slices or the card title. */}
          <div className="card chart-card">
            <h2>Optimal Asset Allocation</h2>
            <ResponsiveContainer width="100%" height={360}>
              <PieChart margin={{ top: 36, bottom: 24, left: 24, right: 24 }}>
                <Pie data={pieData} dataKey="value" nameKey="name" outerRadius={100}
                  labelLine={{ stroke: "var(--muted)" }} minAngle={4}
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

          {/* Exact units to buy from the live picks */}
          <InvestmentPlanCard refreshKey={recommendation} />
        </>
      )}
      </div>
      )}

      {/* ═══ PAGE 2 — Specific Investment Picks ═════════════════════════ */}
      {optimizerPage === 1 && (
        <div className="tab-pane">
          {/* ── Specific Investment Picks ────────────────────────────────── */}
          <h2 style={{ marginTop: 4 }}>
            Specific Investment Picks
            {picksLoading && <span className="muted" style={{ fontSize: 13, marginLeft: 10 }}>fetching live data…</span>}
          </h2>
          <p className="muted" style={{ fontSize: 13, marginTop: -6 }}>
            Concrete instruments for your{" "}
            <strong>{profile.risk_appetite}</strong>-risk allocation. Generate a
            recommendation on the previous page first.
          </p>

          {alloc && picks && (
            <>
              {/* ── EQUITY ─────────────────────────────────────────────── */}
              {alloc.equity_pct > 0 && picks.equity.length > 0 && (
                <div className="card" style={softCard(ASSET_SECTION_COLORS.equity)}>
                  <SectionHeader icon={SECTION_ICONS.equity}
                    title={`Equity — Top NSE Picks for ${profile.risk_appetite.charAt(0).toUpperCase() + profile.risk_appetite.slice(1)} Risk (Live)`}
                    pct={alloc.equity_pct} />
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
              {alloc.mutual_funds_pct > 0 && picks.mutual_funds.length > 0 && (
                <div className="card" style={softCard(ASSET_SECTION_COLORS.mutual_funds)}>
                  <SectionHeader icon={SECTION_ICONS.mutual_funds}
                    title={`Mutual Funds — ${profile.risk_appetite.charAt(0).toUpperCase() + profile.risk_appetite.slice(1)}-Risk Picks`}
                    pct={alloc.mutual_funds_pct} />
                  <p className="muted" style={{ fontSize: 12, marginTop: -8 }}>
                    Live NAVs and trailing returns from AMFI data — past performance is not a guarantee.
                  </p>
                  <div style={{ overflowX: "auto" }}>
                    <table className="table" style={{ minWidth: 750 }}>
                      <thead>
                        <tr>
                          <th>Fund Name</th>
                          <th>Category</th>
                          <th>Risk</th>
                          <th>NAV</th>
                          <th>1Y Returns</th>
                          <th>3Y Returns (CAGR)</th>
                          <th>Volatility</th>
                        </tr>
                      </thead>
                      <tbody>
                        {picks.mutual_funds.map(f => (
                          <tr key={f.name}>
                            <td>
                              <strong style={{ color: "var(--text)" }}>{f.name}</strong>
                              <div style={{ fontSize: 11, color: "var(--muted)" }}>
                                {f.fund_house} · NAV as of {f.nav_date}
                              </div>
                            </td>
                            <td><Badge text={f.category} color="#9B59B6" /></td>
                            <td><RiskBadge risk={f.risk} /></td>
                            <td style={{ fontWeight: 700 }}>₹{f.nav?.toLocaleString("en-IN")}</td>
                            <td><ChangeChip value={f.returns_1y} /></td>
                            <td><ChangeChip value={f.returns_3y} /></td>
                            <td className="muted">
                              {f.volatility_pct != null ? `${f.volatility_pct.toFixed(1)}%` : "—"}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}

              {/* ── GOLD ────────────────────────────────────────────────── */}
              {alloc.gold_pct > 0 && picks.gold.length > 0 && (
                <div className="card" style={softCard(ASSET_SECTION_COLORS.gold)}>
                  <SectionHeader icon={SECTION_ICONS.gold}
                    title="Gold — ETFs &amp; Sovereign Gold Bonds (Live)"
                    pct={alloc.gold_pct} />
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
              {alloc.debt_pct > 0 && (
                <div className="card" style={softCard(ASSET_SECTION_COLORS.debt)}>
                  <SectionHeader icon={SECTION_ICONS.debt}
                    title="Debt — Exchange-Traded Fixed Income (Live)"
                    pct={alloc.debt_pct} />
                  <p className="muted" style={{ fontSize: 12, marginTop: -8 }}>
                    Gilt, PSU bond and liquid ETFs traded on the NSE — live prices and 1-year returns.
                  </p>
                  <div style={{ overflowX: "auto" }}>
                    <table className="table" style={{ minWidth: 640 }}>
                      <thead>
                        <tr>
                          <th>Type</th>
                          <th>Instrument</th>
                          <th>Price (₹)</th>
                          <th>Day Change</th>
                          <th>1Y Return</th>
                          <th>Volatility</th>
                        </tr>
                      </thead>
                      <tbody>
                        {picks.debt.map(d => (
                          <tr key={d.ticker || d.name}>
                            <td><Badge text={d.type} color="#4ECDC4" /></td>
                            <td>
                              <strong style={{ color: "var(--text)" }}>{d.name}</strong>
                              <div style={{ fontSize: 11, color: "var(--muted)" }}>{d.ticker}</div>
                            </td>
                            <td style={{ fontWeight: 700 }}>₹{d.price?.toLocaleString("en-IN")}</td>
                            <td><ChangeChip value={d.change_pct} /></td>
                            <td><ChangeChip value={d.returns_1y_pct} /></td>
                            <td className="muted">
                              {d.volatility_pct != null ? `${d.volatility_pct.toFixed(1)}%` : "—"}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}

              {/* ── FIXED DEPOSITS ───────────────────────────────────────── */}
              {alloc.fd_pct > 0 && (
                <div className="card" style={softCard(ASSET_SECTION_COLORS.fd)}>
                  <SectionHeader icon={SECTION_ICONS.fd}
                    title="Fixed Deposits — Our FD Rates (Live)"
                    pct={alloc.fd_pct} />
                  <p className="muted" style={{ fontSize: 12, marginTop: -8 }}>
                    As an independent bank, our indicative FD rate is benchmarked to
                    the market average across {picks.fd.length} leading banks' live
                    published rates. DICGC insured up to ₹5L.
                  </p>
                  {(() => {
                    const reg = avgFdRate(picks.fd, "rate_regular");
                    const sen = avgFdRate(picks.fd, "rate_senior");
                    return (
                      <div className="grid-2" style={{ gap: 16 }}>
                        <div className="card" style={{ textAlign: "center", margin: 0 }}>
                          <p className="muted" style={{ margin: "0 0 4px" }}>
                            Regular Rate (all tenures)
                          </p>
                          <div style={{ fontSize: 32, fontWeight: 700, color: "var(--primary)" }}>
                            {reg != null ? `${reg.toFixed(2)}%` : "—"}
                          </div>
                          <span className="muted" style={{ fontSize: 12 }}>p.a. (average)</span>
                        </div>
                        <div className="card" style={{ textAlign: "center", margin: 0 }}>
                          <p className="muted" style={{ margin: "0 0 4px" }}>
                            Senior Citizen Rate
                          </p>
                          <div style={{ fontSize: 32, fontWeight: 700, color: "var(--primary)" }}>
                            {sen != null ? `${sen.toFixed(2)}%` : "—"}
                          </div>
                          <span className="muted" style={{ fontSize: 12 }}>p.a. (average)</span>
                        </div>
                      </div>
                    );
                  })()}
                </div>
              )}
            </>
          )}

          {/* ── Analytics (moved here): Efficient Frontier, Asset Class
                 Statistics & Asset Correlation Matrix — shown after the
                 Specific Investment Picks ─────────────────────────────── */}
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

      {/* ── Correlation heat map (same data source as the optimizer) ─────── */}
      <CorrelationMatrixCard assetStats={assetStats} />
      </div>
      )}

      {/* ── Prev / Next pager (bottom) — same controls for easier reach ── */}
      <OptimizerPager page={optimizerPage} setPage={setOptimizerPage} edge="bottom" />
      </div>
      )}

      {/* Docked mini AI Advisor — same conversation as the /advisor tab */}
      <MiniAdvisor />
    </div>
  );
}
