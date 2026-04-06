import React, { useState } from "react";
import { api } from "../lib/api";
import { useNavigate, Link } from "react-router-dom";

export default function RegisterPublic(){
  const nav = useNavigate();
  const [email,setEmail]=useState("");
  const [password,setPassword]=useState("");
  const [loading, setLoading] = useState(false);
  const [err,setErr]=useState("");

  async function submit(e){
    e.preventDefault();
    setErr("");
    setLoading(true);

    try{
      await api.post("/api/auth/register-public", {
        email: email.trim().toLowerCase(),
        password,
      });
      nav("/login");
    } catch (e2) {
      const status = e2?.response?.status;
      const detail = e2?.response?.data?.detail;

      let message = "Registration failed";
      if (Array.isArray(detail)) message = detail.map((x) => x?.msg || "Invalid input").join(", ");
      else if (typeof detail === "string") message = detail;
      else if (e2?.message) message = e2.message;

      setErr(`${status ? `${status} ` : ""}${message}`);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="container">
      <div className="card auth-card" style={{ maxWidth: 520, margin:"40px auto" }}>
        <h2>Create Public Quick-Check Account</h2>
        <p className="small">Rate-limited access for single users.</p>
        <form onSubmit={submit}>
          <label className="small" htmlFor="public-email">Email</label>
          <input
            id="public-email"
            className="input"
            type="email"
            placeholder="you@example.com"
            value={email}
            onChange={e=>setEmail(e.target.value)}
            required
          />
          <div style={{ height: 10 }} />
          <label className="small" htmlFor="public-password">Password</label>
          <input
            id="public-password"
            className="input"
            type="password"
            placeholder="Minimum 8 characters"
            value={password}
            onChange={e=>setPassword(e.target.value)}
            required
            minLength={8}
          />
          <div style={{ height: 14 }} />
          <button className="btn" type="submit" disabled={loading}>
            {loading ? "Creating..." : "Create account"}
          </button>
        </form>
        {err && <p style={{ color:"#ff8080" }}>{err}</p>}
        <div className="small auth-links">
          <Link className="system-link" to="/login">Back to login</Link>
          <span className="auth-links-divider">|</span>
          <Link className="system-link" to="/register-business">Register business</Link>
        </div>
      </div>
    </div>
  );
}

