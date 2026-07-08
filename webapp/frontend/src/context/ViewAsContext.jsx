import { createContext, useContext, useEffect, useState } from "react";
import client from "../api/client";
import { useAuth } from "./AuthContext";

// Beneficiary read access: when another user has granted me access
// (Settings → Beneficiaries → Data Access), I can switch the whole app
// into a read-only view of their data. The selection lives in
// localStorage so the axios interceptor can attach the X-View-As header,
// and switching reloads the app so every page refetches cleanly.

const STORAGE_KEY = "smartbank_view_as";
const ViewAsContext = createContext(null);

export function ViewAsProvider({ children }) {
  const { user } = useAuth();
  const [viewAs] = useState(() => {
    const stored = localStorage.getItem(STORAGE_KEY);
    try { return stored ? JSON.parse(stored) : null; } catch { return null; }
  });
  const [granters, setGranters] = useState([]);

  useEffect(() => {
    if (!user) return;
    let cancelled = false;
    client.get("/api/settings/access-grants/shared-with-me")
      .then((res) => { if (!cancelled) setGranters(res.data); })
      .catch(() => {});
    return () => { cancelled = true; };
  }, [user]);

  function switchTo(granter) {
    localStorage.setItem(STORAGE_KEY,
      JSON.stringify({ user_id: granter.user_id, name: granter.name }));
    window.location.reload();
  }

  function exitViewAs() {
    localStorage.removeItem(STORAGE_KEY);
    window.location.reload();
  }

  return (
    <ViewAsContext.Provider
      value={{ viewAs, granters, switchTo, exitViewAs, isViewing: !!viewAs }}>
      {children}
    </ViewAsContext.Provider>
  );
}

export function useViewAs() {
  return useContext(ViewAsContext);
}
