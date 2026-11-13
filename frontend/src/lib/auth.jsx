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
  const [mode, setMode] = useState("demo");

  useEffect(() => {
    // Fetch integration mode so the UI can label live vs demo honestly.
    api.get("/health").then((d) => setMode(d.mode || "demo")).catch(() => {});
  }, []);

  const login = async (workerId, password, language, remember) => {
    const data = await api.post("/auth/login", {
      worker_id: workerId,
      password,
      language,
    });
    localStorage.setItem(
      "asn_auth",
      JSON.stringify({ token: data.token, worker: data.worker, remember })
    );
    setUser(data.worker);
    return data.worker;
  };

  const logout = () => {
    localStorage.removeItem("asn_auth");
    setUser(null);
  };

  return (
    <AuthCtx.Provider value={{ user, login, logout, mode }}>{children}</AuthCtx.Provider>
  );
}

export const useAuth = () => useContext(AuthCtx);
