import { createContext, useContext, useState } from "react";
import client from "../api/client";

const AuthContext = createContext(null);

// A stable id for this browser, minted once and kept in localStorage. Adaptive
// auth uses it to distinguish a returning device from a brand-new one. It is
// not a secret and not a credential — just a "have I seen this browser" tag.
function getDeviceId() {
  let id = localStorage.getItem("smartbank_device_id");
  if (!id) {
    id = (crypto?.randomUUID?.() ||
          `dev-${Date.now()}-${Math.random().toString(16).slice(2)}`);
    localStorage.setItem("smartbank_device_id", id);
  }
  return id;
}

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
    const res = await client.post("/api/auth/login", {
      user_id: userId,
      pin,
      // Stable per-browser id so adaptive auth can recognise a returning
      // device and wave it through without a step-up.
      device_id: getDeviceId(),
    });
    // Adaptive auth may decide the PIN alone isn't enough (new device, new
    // network, odd hour…). Then the PIN only earns a challenge and the caller
    // must complete verifyTwoFactor() before a session exists.
    if (res.data.requires_2fa) return res.data;
    storeSession(res.data);
    return res.data;
  }

  async function verifyTwoFactor(challengeToken, imageDataUrls) {
    // A burst of frames, not one snapshot: the server looks for a blink
    // across them before it will trust the face. Face matching runs a CPU
    // model server-side — allow it extra time.
    const res = await client.post(
      "/api/auth/face-verify",
      { challenge_token: challengeToken, images: imageDataUrls },
      { timeout: 45000 }
    );
    storeSession(res.data);
    return res.data;
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
    localStorage.removeItem("smartbank_view_as");
    setUser(null);
  }

  return (
    <AuthContext.Provider
      value={{ user, login, loginWithFace, verifyTwoFactor, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  return useContext(AuthContext);
}
