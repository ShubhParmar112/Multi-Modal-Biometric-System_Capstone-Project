import { createContext, useContext, useState } from "react";
import client from "../api/client";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(() => {
    const stored = localStorage.getItem("smartbank_user");
    return stored ? JSON.parse(stored) : null;
  });

  async function login(userId, pin) {
    const res = await client.post("/api/auth/login", { user_id: userId, pin });
    const { access_token, user_id, name } = res.data;
    localStorage.setItem("smartbank_token", access_token);
    localStorage.setItem("smartbank_user", JSON.stringify({ user_id, name }));
    setUser({ user_id, name });
  }

  function logout() {
    localStorage.removeItem("smartbank_token");
    localStorage.removeItem("smartbank_user");
    setUser(null);
  }

  return (
    <AuthContext.Provider value={{ user, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  return useContext(AuthContext);
}
