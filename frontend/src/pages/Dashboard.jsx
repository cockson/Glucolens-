import React from "react";
import { clearAuth, getAuth } from "../lib/authStore";
import { useNavigate, Link } from "react-router-dom";

export default function Dashboard(){
  const nav = useNavigate();
  const auth = getAuth();

  function logout(){
    clearAuth();
    nav("/login");
  }

  return (
    <div className="container">
      <div className="card">
        <h2>GlucoLens Dashboard</h2>
        <p className="small">Logged in. Subscription is required for business actions.</p>
        <div style={{ display:"flex", gap:10, flexWrap:"wrap" }}>
          <Link className="btn" to="/billing">Billing</Link>
          <Link className="btn secondary" to="/facilities">Facility Finder</Link>
          <button className="btn secondary" onClick={logout}>Logout</button>
        </div>
        <pre className="small" style={{ marginTop: 14, whiteSpace:"pre-wrap" }}>
{JSON.stringify(auth, null, 2)}
        </pre>
      </div>
    </div>
  );
}