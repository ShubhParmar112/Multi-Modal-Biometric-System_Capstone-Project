import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
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

  useEffect(() => {
    client.get("/api/settings/profile").then((res) => {
      setProfile(res.data);
      setEmail(res.data.email || "");
    }).catch(() => {});
  }, []);

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
  );
}

/* ── Analysis (login & security activity) ─────────────────── */

function AnalysisSection() {
  const [activity, setActivity] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    client.get("/api/settings/activity")
      .then((res) => setActivity(res.data))
      .catch(() => setError("Could not load activity."));
  }, []);

  if (error) return <div className="card"><p className="error-text">{error}</p></div>;
  if (!activity) return <div className="spinner" />;

  const { summary, logs } = activity;
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

      <div className="card">
        <h2>Login &amp; Security Activity</h2>
        <p className="muted" style={{ fontSize: 12, marginTop: -8 }}>
          Every authentication event on your account — web and ATM.
        </p>
        {logs.length === 0 ? (
          <p className="muted">No activity recorded yet.</p>
        ) : (
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
        Choose how SmartBank looks on this device. Saved automatically.
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

  async function refresh() {
    try {
      const res = await client.get("/api/settings/beneficiaries");
      setBeneficiaries(res.data);
    } catch {
      setStatus({ ok: false, msg: "Could not load beneficiaries." });
    }
  }

  useEffect(() => { refresh(); }, []);

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
    </>
  );
}
