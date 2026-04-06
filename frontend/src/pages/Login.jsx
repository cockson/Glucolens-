import React, { useState } from "react";
import { api, setAuthHeader } from "../lib/api";
import { clearAuth, setAuth } from "../lib/authStore";
import { useNavigate, Link } from "react-router-dom";

export default function Login() {
  const nav = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [err, setErr] = useState("");

  async function submit(e) {
    e.preventDefault();
    setErr("");
    const normalizedEmail = email.trim().toLowerCase();
    if (!normalizedEmail || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(normalizedEmail)) {
      setErr("Enter a valid email address.");
      return;
    }
    if (!password || password.length < 8) {
      setErr("Password must be at least 8 characters.");
      return;
    }

    clearAuth();
    try {
      const tokenRes = await api.post("/api/auth/login", {
        email: normalizedEmail,
        password,
      });
      setAuthHeader(tokenRes.data.access_token);
      const me = await api.get("/api/auth/me");
      setAuth({ ...tokenRes.data, ...me.data });
      nav("/dashboard");
    } catch (e2) {
      clearAuth();
      const status = e2?.response?.status;
      const detail = e2?.response?.data?.detail || e2?.message || "Login failed";
      setErr(`${status ? `${status} ` : ""}${detail}`);
    }
  }

  return (
    <div className="container">
      <div className="card auth-card" style={{ maxWidth: 520, margin: "40px auto" }}>
        <h2>Sign in</h2>
        <p className="small">Access hospital, clinic, and pharmacy tools.</p>
        <form onSubmit={submit}>
          <label className="small" htmlFor="login-email">Email</label>
          <input
            id="login-email"
            className="input"
            type="email"
            required
            placeholder="you@organization.com"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
          <div style={{ height: 10 }} />
          <label className="small" htmlFor="login-password">Password</label>
          <input
            id="login-password"
            className="input"
            type="password"
            required
            minLength={8}
            placeholder="Your password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
          <div style={{ height: 14 }} />
          <button className="btn" type="submit">Sign in</button>
        </form>
        {err && <p style={{ color: "#ff8080" }}>{err}</p>}
        <div className="small auth-links">
          <Link className="system-link" to="/register-business">Register business</Link>
          <span className="auth-links-divider">|</span>
          <Link className="system-link" to="/register-public">Public quick-check</Link>
        </div>
      </div>
    </div>
  );
}

