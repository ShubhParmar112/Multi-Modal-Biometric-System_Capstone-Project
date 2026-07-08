import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer,
  Tooltip, XAxis, YAxis,
} from "recharts";
import client from "../api/client";
import { useAuth } from "../context/AuthContext";
import { useTheme } from "../context/ThemeContext";

const TABS = [
  { id: "security", label: "🔐 Security" },
  { id: "analysis", label: "📊 Analysis" },
  { id: "theme", label: "🎨 Theme" },
  { id: "beneficiaries", label: "👥 Beneficiaries" },
];

export default function Settings() {
  const [tab, setTab] = useState("security");
  const { logout } = useAuth();
  const navigate = useNavigate();

  function handleLogout() {
    logout();
    navigate("/login");
  }

  return (
    <div className="page">
      <h1>Settings</h1>

      <div className="settings-tabs">
        {TABS.map((t) => (
          <button
            key={t.id}
            className={`settings-tab ${tab === t.id ? "active" : ""}`}
            onClick={() => setTab(t.id)}
          >
            {t.label}
          </button>
        ))}
      </div>

      {tab === "security" && <SecuritySection />}
      {tab === "analysis" && <AnalysisSection />}
      {tab === "theme" && <ThemeSection />}
      {tab === "beneficiaries" && <BeneficiariesSection />}

      <div className="card logout-card">
        <div>
          <h2 style={{ marginBottom: 4 }}>Log out</h2>
          <p className="muted" style={{ margin: 0, fontSize: 13 }}>
            End this session on this device.
          </p>
        </div>
        <button className="btn btn-danger" onClick={handleLogout}>
          ⏻ Logout
        </button>
      </div>
    </div>
  );
}

/* ── Security ─────────────────────────────────────────────── */

function SecuritySection() {
  const [profile, setProfile] = useState(null);
  const [oldPin, setOldPin] = useState("");
  const [newPin, setNewPin] = useState("");
  const [email, setEmail] = useState("");
  const [pinStatus, setPinStatus] = useState(null);
  const [emailStatus, setEmailStatus] = useState(null);
  const [twoFactor, setTwoFactor] = useState(false);
  const [twoFaStatus, setTwoFaStatus] = useState(null);
  const [twoFaBusy, setTwoFaBusy] = useState(false);

  useEffect(() => {
    client.get("/api/settings/profile").then((res) => {
      setProfile(res.data);
      setEmail(res.data.email || "");
      setTwoFactor(!!res.data.two_factor_enabled);
    }).catch(() => {});
  }, []);

  async function handleToggleTwoFactor() {
    setTwoFaStatus(null);
    setTwoFaBusy(true);
    try {
      const res = await client.post("/api/settings/two-factor", {
        enabled: !twoFactor,
      });
      setTwoFactor(res.data.two_factor_enabled);
      setTwoFaStatus({ ok: true, msg: res.data.message });
    } catch (err) {
      setTwoFaStatus({
        ok: false,
        msg: err.response?.data?.detail || "Could not update 2FA.",
      });
    } finally {
      setTwoFaBusy(false);
    }
  }

  async function handleChangePin(e) {
    e.preventDefault();
    setPinStatus(null);
    try {
      const res = await client.post("/api/settings/change-pin", {
        old_pin: oldPin, new_pin: newPin,
      });
      setPinStatus({ ok: true, msg: res.data.message });
      setOldPin(""); setNewPin("");
    } catch (err) {
      setPinStatus({ ok: false, msg: err.response?.data?.detail || "PIN change failed." });
    }
  }

  async function handleUpdateEmail(e) {
    e.preventDefault();
    setEmailStatus(null);
    try {
      const res = await client.post("/api/settings/email", { email });
      setEmailStatus({ ok: true, msg: res.data.message });
    } catch (err) {
      setEmailStatus({ ok: false, msg: err.response?.data?.detail || "Update failed." });
    }
  }

  return (
    <>
    <div className="card toggle-card">
      <label className="switch">
        <input type="checkbox" checked={twoFactor}
               disabled={twoFaBusy} onChange={handleToggleTwoFactor} />
        <span className="slider" />
      </label>
      <div>
        <strong>Two-factor authentication {twoFactor ? "(ON)" : "(OFF)"}</strong>
        <p className="muted" style={{ margin: "2px 0 0", fontSize: 13 }}>
          When on, signing in with your PIN also requires a Face ID check —
          the same face you enrolled at the ATM. When off, the PIN alone
          signs you in.
        </p>
        {twoFaStatus && (
          <p className={twoFaStatus.ok ? "success-text" : "error-text"}
             style={{ margin: "6px 0 0", fontSize: 13 }}>
            {twoFaStatus.msg}
          </p>
        )}
      </div>
    </div>
    <div className="grid-2">
      <form className="card" onSubmit={handleChangePin}>
        <h2>Change PIN</h2>
        <p className="muted" style={{ fontSize: 13 }}>
          The new PIN applies to both the web portal and the ATM.
        </p>
        <label className="field-label">Current PIN</label>
        <input className="input" type="password" inputMode="numeric" maxLength={4}
               value={oldPin} onChange={(e) => setOldPin(e.target.value)}
               placeholder="••••" required />
        <label className="field-label">New PIN</label>
        <input className="input" type="password" inputMode="numeric" maxLength={4}
               value={newPin} onChange={(e) => setNewPin(e.target.value)}
               placeholder="••••" required />
        {pinStatus && (
          <p className={pinStatus.ok ? "success-text" : "error-text"}>{pinStatus.msg}</p>
        )}
        <button className="btn btn-primary" type="submit">Update PIN</button>
      </form>

      <form className="card" onSubmit={handleUpdateEmail}>
        <h2>Alert Email</h2>
        <p className="muted" style={{ fontSize: 13 }}>
          Debit and credit alerts are mailed to this address.
        </p>
        <label className="field-label">Email address</label>
        <input className="input" type="email" value={email}
               onChange={(e) => setEmail(e.target.value)}
               placeholder="you@example.com" required />
        {emailStatus && (
          <p className={emailStatus.ok ? "success-text" : "error-text"}>{emailStatus.msg}</p>
        )}
        <button className="btn btn-primary" type="submit">Save Email</button>
        {profile && (
          <p className="muted" style={{ fontSize: 12, marginTop: 12 }}>
            Account {profile.user_id} · created {profile.created_at || "—"}
          </p>
        )}
      </form>
    </div>
    </>
  );
}

/* ── Analysis (login & security activity) ─────────────────── */

const ACTIVITY_INITIAL = 10;   // latest 10 events by default
const ACTIVITY_PER_CLICK = 20; // each "Show more" loads 20 more

function AnalysisSection() {
  const [activity, setActivity] = useState(null);
  const [limit, setLimit] = useState(ACTIVITY_INITIAL);
  const [allLoaded, setAllLoaded] = useState(false);
  const [error, setError] = useState("");

  async function load(nextLimit) {
    try {
      const res = await client.get(`/api/settings/activity?limit=${nextLimit}`);
      setActivity(res.data);
      setAllLoaded(res.data.logs.length < nextLimit);
    } catch {
      setError("Could not load activity.");
    }
  }

  useEffect(() => { load(ACTIVITY_INITIAL); }, []);

  function showMore() {
    const next = limit + ACTIVITY_PER_CLICK;
    setLimit(next);
    load(next);
  }

  if (error) return <div className="card"><p className="error-text">{error}</p></div>;
  if (!activity) return <div className="spinner" />;

  const { summary, logs } = activity;

  // Chart built from the SAME logs shown below — extends with "Show more".
  const byDay = new Map();
  for (const l of [...logs].reverse()) {
    const day = (l.timestamp || "").slice(0, 10);
    if (!byDay.has(day)) byDay.set(day, { day, success: 0, failure: 0 });
    byDay.get(day)[l.result === "success" ? "success" : "failure"] += 1;
  }
  const chartData = [...byDay.values()];

  return (
    <>
      <div className="card summary-card">
        <div>
          <p className="muted">Recent events</p>
          <h2>{summary.events}</h2>
        </div>
        <div>
          <p className="muted">Failed attempts</p>
          <h2 style={{ color: summary.failures ? "var(--accent)" : "inherit" }}>
            {summary.failures}
          </h2>
        </div>
        <div>
          <p className="muted">Face ID logins</p>
          <h2>{summary.face_logins}</h2>
        </div>
        <div>
          <p className="muted">Last login</p>
          <h2 style={{ fontSize: 14 }}>{summary.last_login || "—"}</h2>
        </div>
      </div>

      {chartData.length > 0 && (
        <div className="card chart-card">
          <h2>Activity Over Time</h2>
          <p className="muted" style={{ fontSize: 12, marginTop: -8 }}>
            Successful vs failed authentication events from the rows shown below.
          </p>
          <ResponsiveContainer width="100%" height={220}>
            <BarChart data={chartData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#2A3A5C" />
              <XAxis dataKey="day" stroke="#7B8794" fontSize={11} />
              <YAxis stroke="#7B8794" fontSize={11} allowDecimals={false} />
              <Tooltip />
              <Legend />
              <Bar dataKey="success" fill="#00D4AA" name="Success" />
              <Bar dataKey="failure" fill="#E94560" name="Failure" />
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}

      <div className="card">
        <h2>Login &amp; Security Activity</h2>
        <p className="muted" style={{ fontSize: 12, marginTop: -8 }}>
          Latest {logs.length} authentication events on your account — web and ATM.
        </p>
        {logs.length === 0 ? (
          <p className="muted">No activity recorded yet.</p>
        ) : (
          <>
            <table className="table">
              <thead>
                <tr><th>Event</th><th>Result</th><th>Details</th><th>When</th></tr>
              </thead>
              <tbody>
                {logs.map((l) => (
                  <tr key={l.id}>
                    <td>{l.event_type.replaceAll("_", " ")}</td>
                    <td className={l.result === "success" ? "success-text" : "error-text"}>
                      {l.result}
                    </td>
                    <td className="muted">{l.details}</td>
                    <td className="muted">{l.timestamp}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {!allLoaded && (
              <button className="btn btn-secondary" style={{ marginTop: 12 }}
                onClick={showMore}>
                Show more ({ACTIVITY_PER_CLICK} older events)
              </button>
            )}
            {allLoaded && logs.length > ACTIVITY_INITIAL && (
              <p className="muted" style={{ marginTop: 12, marginBottom: 0, fontSize: 12 }}>
                Full history shown.
              </p>
            )}
          </>
        )}
      </div>
    </>
  );
}

/* ── Theme ────────────────────────────────────────────────── */

function ThemeSection() {
  const { theme, setTheme } = useTheme();

  return (
    <div className="card">
      <h2>Appearance</h2>
      <p className="muted" style={{ fontSize: 13 }}>
        Saved automatically — to your profile, so it follows you on any device.
        "System" tracks your OS/browser light-dark setting live.
      </p>
      <div className="theme-options">
        <button
          className={`theme-option ${theme === "dark" ? "selected" : ""}`}
          onClick={() => setTheme("dark")}
        >
          <div className="theme-swatch theme-swatch-dark">🌙</div>
          <strong>Dark</strong>
          <span className="muted" style={{ fontSize: 12 }}>Default</span>
        </button>
        <button
          className={`theme-option ${theme === "light" ? "selected" : ""}`}
          onClick={() => setTheme("light")}
        >
          <div className="theme-swatch theme-swatch-light">☀️</div>
          <strong>Light</strong>
          <span className="muted" style={{ fontSize: 12 }}>Bright &amp; clean</span>
        </button>
        <button
          className={`theme-option ${theme === "system" ? "selected" : ""}`}
          onClick={() => setTheme("system")}
        >
          <div className="theme-swatch theme-swatch-dark">🖥️</div>
          <strong>System</strong>
          <span className="muted" style={{ fontSize: 12 }}>Follows your OS</span>
        </button>
      </div>
    </div>
  );
}

/* ── Beneficiaries ────────────────────────────────────────── */

function BeneficiariesSection() {
  const [beneficiaries, setBeneficiaries] = useState([]);
  const [name, setName] = useState("");
  const [accountNumber, setAccountNumber] = useState("");
  const [status, setStatus] = useState(null);
  const [grants, setGrants] = useState([]);
  const [grantAccount, setGrantAccount] = useState("");
  const [grantStatus, setGrantStatus] = useState(null);

  async function refresh() {
    try {
      const [benRes, grantRes] = await Promise.all([
        client.get("/api/settings/beneficiaries"),
        client.get("/api/settings/access-grants"),
      ]);
      setBeneficiaries(benRes.data);
      setGrants(grantRes.data);
    } catch {
      setStatus({ ok: false, msg: "Could not load beneficiaries." });
    }
  }

  useEffect(() => { refresh(); }, []);

  async function handleAddGrant(e) {
    e.preventDefault();
    setGrantStatus(null);
    try {
      const res = await client.post("/api/settings/access-grants", {
        account_number: grantAccount,
      });
      setGrantStatus({ ok: true, msg: res.data.message });
      setGrantAccount("");
      refresh();
    } catch (err) {
      setGrantStatus({
        ok: false,
        msg: err.response?.data?.detail || "Could not grant access.",
      });
    }
  }

  async function handleRevokeGrant(id) {
    try {
      await client.delete(`/api/settings/access-grants/${id}`);
      refresh();
    } catch {
      setGrantStatus({ ok: false, msg: "Could not revoke access." });
    }
  }

  async function handleAdd(e) {
    e.preventDefault();
    setStatus(null);
    try {
      const res = await client.post("/api/settings/beneficiaries", {
        name, account_number: accountNumber,
      });
      setStatus({ ok: true, msg: res.data.message });
      setName(""); setAccountNumber("");
      refresh();
    } catch (err) {
      setStatus({ ok: false, msg: err.response?.data?.detail || "Could not add beneficiary." });
    }
  }

  async function handleDelete(id) {
    try {
      await client.delete(`/api/settings/beneficiaries/${id}`);
      refresh();
    } catch {
      setStatus({ ok: false, msg: "Could not remove beneficiary." });
    }
  }

  return (
    <>
      <form className="card" onSubmit={handleAdd}>
        <h2>Add Beneficiary</h2>
        <p className="muted" style={{ fontSize: 13 }}>
          Saved beneficiaries appear as one-click choices on the Transfer form.
        </p>
        <div className="grid-2">
          <div>
            <label className="field-label">Name</label>
            <input className="input" value={name}
                   onChange={(e) => setName(e.target.value)}
                   placeholder="e.g. Mom" required />
          </div>
          <div>
            <label className="field-label">SmartBank Account Number</label>
            <input className="input" value={accountNumber}
                   onChange={(e) => setAccountNumber(e.target.value)}
                   placeholder="12-digit account number" required />
          </div>
        </div>
        {status && (
          <p className={status.ok ? "success-text" : "error-text"}>{status.msg}</p>
        )}
        <button className="btn btn-primary" type="submit">+ Add Beneficiary</button>
      </form>

      <div className="card">
        <h2>Saved Beneficiaries</h2>
        {beneficiaries.length === 0 ? (
          <p className="muted">No beneficiaries saved yet.</p>
        ) : (
          <table className="table">
            <thead>
              <tr><th>Name</th><th>Account Number</th><th>Added</th><th /></tr>
            </thead>
            <tbody>
              {beneficiaries.map((b) => (
                <tr key={b.beneficiary_id}>
                  <td><strong>{b.name}</strong></td>
                  <td style={{ fontFamily: "var(--mono)" }}>{b.account_number}</td>
                  <td className="muted">{b.added_at}</td>
                  <td style={{ textAlign: "right" }}>
                    <button className="btn btn-secondary btn-small"
                            onClick={() => handleDelete(b.beneficiary_id)}>
                      Remove
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <form className="card" onSubmit={handleAddGrant}>
        <h2>Data Access</h2>
        <p className="muted" style={{ fontSize: 13 }}>
          Give the holder of another SmartBank account <strong>read-only</strong>{" "}
          access to your data — holdings, transactions, analytics and
          portfolio. They'll get a "View account" switcher after their next
          sign-in. You can revoke at any time.
        </p>
        <div className="inline-form">
          <input className="input" value={grantAccount}
                 onChange={(e) => setGrantAccount(e.target.value)}
                 placeholder="Their 12-digit account number" required />
          <button className="btn btn-primary" type="submit">Grant access</button>
        </div>
        {grantStatus && (
          <p className={grantStatus.ok ? "success-text" : "error-text"}>
            {grantStatus.msg}
          </p>
        )}

        {grants.length > 0 && (
          <table className="table" style={{ marginTop: 12 }}>
            <thead>
              <tr><th>User</th><th>Since</th><th /></tr>
            </thead>
            <tbody>
              {grants.map((g) => (
                <tr key={g.grant_id}>
                  <td>
                    <strong>{g.name}</strong>
                    <span className="muted" style={{ marginLeft: 8, fontSize: 12 }}>
                      {g.grantee_user_id}
                    </span>
                  </td>
                  <td className="muted">{g.created_at}</td>
                  <td style={{ textAlign: "right" }}>
                    <button type="button" className="btn btn-secondary btn-small"
                            onClick={() => handleRevokeGrant(g.grant_id)}>
                      Revoke
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </form>
    </>
  );
}
