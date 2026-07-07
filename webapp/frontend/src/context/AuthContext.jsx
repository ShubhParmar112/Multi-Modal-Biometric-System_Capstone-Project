import { createContext, useContext, useState } from "react";
import client from "../api/client";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(() => {
    const stored = localStorage.getItem("smartbank_user");
    return stored ? JSON.parse(stored) : null;
  });

  function storeSession(data) {
    const { access_token, user_id, name } = data;
    localStorage.setItem("smartbank_token", access_token);
    localStorage.setItem("smartbank_user", JSON.stringify({ user_id, name }));
    setUser({ user_id, name });
  }

  async function login(userId, pin) {
    const res = await client.post("/api/auth/login", { user_id: userId, pin });
    storeSession(res.data);
  }

  async function loginWithFace(imageDataUrl) {
    // Face matching runs a CPU model server-side — allow it extra time.
    const res = await client.post(
      "/api/auth/face-login",
      { image: imageDataUrl },
      { timeout: 45000 }
    );
    storeSession(res.data);
    return res.data;
  }

  function logout() {
    localStorage.removeItem("smartbank_token");
    localStorage.removeItem("smartbank_user");
    setUser(null);
  }

  return (
    <AuthContext.Provider value={{ user, login, loginWithFace, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  return useContext(AuthContext);
}
