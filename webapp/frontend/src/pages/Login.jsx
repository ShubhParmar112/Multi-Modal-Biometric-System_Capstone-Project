import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";

export default function Login() {
  const [userId, setUserId] = useState("");
  const [pin, setPin] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const { login } = useAuth();
  const navigate = useNavigate();

  async function handleSubmit(e) {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      await login(userId, pin);
      navigate("/dashboard");
    } catch (err) {
      if (err.response?.status === 401) {
        setError("Invalid user ID or PIN.");
      } else {
        setError("Cannot reach the server. Is the backend running on port 8000?");
      }
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="centered-page">
      <form className="card login-card" onSubmit={handleSubmit}>
        <div className="login-logo">🏦</div>
        <h1 className="login-title">SmartBank</h1>
        <p className="login-subtitle">Secure Online Banking Portal</p>

        <label className="field-label">User ID</label>
        <input
          className="input"
          value={userId}
          onChange={(e) => setUserId(e.target.value)}
          placeholder="USR001"
          required
        />

        <label className="field-label">PIN</label>
        <input
          className="input"
          type="password"
          inputMode="numeric"
          maxLength={4}
          value={pin}
          onChange={(e) => setPin(e.target.value)}
          placeholder="••••"
          required
        />

        {error && <p className="error-text">{error}</p>}

        <button className="btn btn-primary" type="submit" disabled={loading}>
          {loading ? "Signing in..." : "Sign In"}
        </button>

        <p className="login-hint">
          Use the User ID and PIN created during ATM enrollment.
        </p>
      </form>
    </div>
  );
}
