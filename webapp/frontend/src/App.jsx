import { useEffect } from "react";
import { Routes, Route, Navigate } from "react-router-dom";
import client from "./api/client";
import Navbar from "./components/Navbar";
import ProtectedRoute from "./components/ProtectedRoute";
import { useAuth } from "./context/AuthContext";
import { useTheme } from "./context/ThemeContext";
import Login from "./pages/Login";
import Dashboard from "./pages/Dashboard";
import Transactions from "./pages/Transactions";
import Analytics from "./pages/Analytics";
import Portfolio from "./pages/Portfolio";
import Advisor from "./pages/Advisor";
import Settings from "./pages/Settings";

// Apply the signed-in user's persisted theme preference (per user on the
// server) on top of the device-level localStorage default.
function UserThemeSync() {
  const { user } = useAuth();
  const { applyServerTheme } = useTheme();

  useEffect(() => {
    if (!user) return;
    let cancelled = false;
    client.get("/api/settings/profile")
      .then((res) => {
        if (!cancelled && res.data.theme) applyServerTheme(res.data.theme);
      })
      .catch(() => {});
    return () => { cancelled = true; };
    // applyServerTheme is stable enough for this once-per-login sync.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user]);

  return null;
}

export default function App() {
  return (
    <>
      <UserThemeSync />
      <Navbar />
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route
          path="/dashboard"
          element={<ProtectedRoute><Dashboard /></ProtectedRoute>}
        />
        <Route
          path="/transactions"
          element={<ProtectedRoute><Transactions /></ProtectedRoute>}
        />
        <Route
          path="/analytics"
          element={<ProtectedRoute><Analytics /></ProtectedRoute>}
        />
        <Route
          path="/portfolio"
          element={<ProtectedRoute><Portfolio /></ProtectedRoute>}
        />
        <Route
          path="/advisor"
          element={<ProtectedRoute><Advisor /></ProtectedRoute>}
        />
        <Route
          path="/settings"
          element={<ProtectedRoute><Settings /></ProtectedRoute>}
        />
        <Route path="*" element={<Navigate to="/dashboard" replace />} />
      </Routes>
    </>
  );
}
