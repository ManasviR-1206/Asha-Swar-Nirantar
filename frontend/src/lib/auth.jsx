import React, { createContext, useContext, useEffect, useState } from "react";
import { api } from "./api.js";

const AuthCtx = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(() => {
    try {
      const saved = JSON.parse(localStorage.getItem("asn_auth") || "null");
      return saved?.worker ? saved.worker : null;
    } catch {
      return null;
    }
  });
  const [health, setHealth] = useState(null);

  useEffect(() => {
    // Fetch runtime status so UI can label explicit demo setup and integration state honestly.
    api.get("/health").then((d) => setHealth(d || null)).catch(() => {});
  }, []);

  const login = async (workerId, password, language, remember) => {
    const data = await api.post(
      "/auth/login",
      {
        worker_id: workerId,
        password,
        language,
      },
      { redirectOnUnauthorized: false }
    );
    localStorage.setItem(
      "asn_auth",
      JSON.stringify({ token: data.token, worker: data.worker, remember })
    );
    setUser(data.worker);
    return data.worker;
  };

  const demoLogin = async () => {
    const data = await api.post("/auth/demo-session", {}, { redirectOnUnauthorized: false });
    localStorage.setItem(
      "asn_auth",
      JSON.stringify({ token: data.token, worker: data.worker, remember: true, demo_session: true })
    );
    setUser(data.worker);
    return data.worker;
  };

  const logout = () => {
    // Best-effort server-side token revocation; never block local sign-out.
    api.post("/auth/logout", {}, { redirectOnUnauthorized: false }).catch(() => {});
    try { sessionStorage.removeItem("geopulse_cache_v1_redacted"); } catch {}
    localStorage.removeItem("asn_auth");
    setUser(null);
  };

  const isAdmin = (user?.role || "asha") === "admin";
  const demoSetup = !!(health?.app?.demo_setup || health?.mode === "demo");
  // Backward-compatible alias used by older UI code paths.
  const mode = demoSetup ? "demo" : "normal";
  const gnani = health?.gnani || null;

  return (
    <AuthCtx.Provider value={{ user, login, demoLogin, logout, mode, demoSetup, gnani, health, isAdmin }}>{children}</AuthCtx.Provider>
  );
}

export const useAuth = () => useContext(AuthCtx);
