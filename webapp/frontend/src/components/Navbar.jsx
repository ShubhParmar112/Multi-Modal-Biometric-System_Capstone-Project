import { NavLink } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import { useViewAs } from "../context/ViewAsContext";

export default function Navbar() {
  const { user } = useAuth();
  const { viewAs, granters, switchTo, exitViewAs, isViewing } = useViewAs();

  if (!user) return null;

  return (
    <>
      <nav className="navbar">
        <div className="navbar-brand">🏦 SmartBank</div>
        <div className="navbar-links">
          <NavLink to="/dashboard" className="navbar-link">Dashboard</NavLink>
          <NavLink to="/transactions" className="navbar-link">Transactions</NavLink>
          <NavLink to="/analytics" className="navbar-link">Analytics</NavLink>
          <NavLink to="/portfolio" className="navbar-link">Portfolio</NavLink>
          <NavLink to="/advisor" className="navbar-link">AI Advisor</NavLink>
        </div>
        <div className="navbar-user">
          {granters.length > 0 && !isViewing && (
            <select
              className="input"
              style={{ width: "auto", margin: 0, padding: "6px 10px", fontSize: 13 }}
              value=""
              onChange={(e) => {
                const g = granters.find((x) => x.user_id === e.target.value);
                if (g) switchTo(g);
              }}
              title="Accounts shared with you"
            >
              <option value="">👁 View account…</option>
              {granters.map((g) => (
                <option key={g.user_id} value={g.user_id}>
                  {g.name} ({g.user_id})
                </option>
              ))}
            </select>
          )}
          <span>{user.name}</span>
          <NavLink to="/settings" className="navbar-link navbar-settings"
                   title="Settings">
            ⚙️ Settings
          </NavLink>
        </div>
      </nav>
      {isViewing && (
        <div style={{
          background: "rgba(245, 166, 35, 0.15)",
          borderBottom: "1px solid rgba(245, 166, 35, 0.4)",
          padding: "8px 24px", fontSize: 13,
          display: "flex", justifyContent: "center", alignItems: "center", gap: 12,
        }}>
          <span>
            👁 Viewing <strong>{viewAs.name}</strong>'s account (read-only)
          </span>
          <button className="btn btn-secondary"
            style={{ padding: "3px 12px", fontSize: 12, margin: 0 }}
            onClick={exitViewAs}>
            Back to my account
          </button>
        </div>
      )}
    </>
  );
}
