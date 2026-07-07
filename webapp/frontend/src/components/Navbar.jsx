import { NavLink } from "react-router-dom";
import { useAuth } from "../context/AuthContext";

export default function Navbar() {
  const { user } = useAuth();

  if (!user) return null;

  return (
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
        <span>{user.name}</span>
        <NavLink to="/settings" className="navbar-link navbar-settings"
                 title="Settings">
          ⚙️ Settings
        </NavLink>
      </div>
    </nav>
  );
}
