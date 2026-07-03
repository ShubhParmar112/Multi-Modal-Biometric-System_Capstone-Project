import { NavLink, useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";

export default function Navbar() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  function handleLogout() {
    logout();
    navigate("/login");
  }

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
        <button className="btn btn-secondary" onClick={handleLogout}>Logout</button>
      </div>
    </nav>
  );
}
