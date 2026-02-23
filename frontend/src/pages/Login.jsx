import React, { useState } from "react";
import { api } from "../lib/api";
import { setAuth } from "../lib/authStore";
import { useNavigate, Link } from "react-router-dom";

export default function Login() {
  const nav = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [err, setErr] = useState("");

  async function submit(e) {
    e.preventDefault();
    setErr("");
    try {
      const res = await api.post("/api/auth/login", { email, password });
      setAuth(res.data);
      nav("/dashboard");
    } catch (e2) {
      setErr(e2?.response?.data?.detail || "Login failed");
    }
  }

  return (
    <div className="container">
      <div className="card" style={{ maxWidth: 520, margin: "40px auto" }}>
        <h2>Login</h2>
        <p className="small">Access hospital/clinic/pharmacy tools (subscription required).</p>
        <form onSubmit={submit}>
          <input className="input" placeholder="Email" value={email} onChange={e=>setEmail(e.target.value)} />
          <div style={{ height: 10 }} />
          <input className="input" type="password" placeholder="Password" value={password} onChange={e=>setPassword(e.target.value)} />
          <div style={{ height: 14 }} />
          <button className="btn" type="submit">Login</button>
        </form>
        {err && <p style={{ color: "#ff8080" }}>{err}</p>}
        <div style={{ marginTop: 12 }} className="small">
          <Link to="/register-business">Register business</Link> •{" "}
          <Link to="/register-public">Public quick-check</Link>
        </div>
      </div>
    </div>
  );
}