import React, { useEffect, useState } from "react";
import { clearAuth, getAuth } from "../lib/authStore";
import { useNavigate, Link } from "react-router-dom";
import { api } from "../lib/api";

export default function Dashboard(){
  const nav = useNavigate();
  const auth = getAuth();
  const [me, setMe] = useState(null);
  const [sub, setSub] = useState(null);
  const [profileErr, setProfileErr] = useState("");

  useEffect(() => {
    let active = true;

    async function loadMe() {
      setProfileErr("");
      try {
        const res = await api.get("/api/auth/me");
        if (active) setMe(res.data);
        const subRes = await api.get("/api/billing/subscription/me");
        if (active) setSub(subRes.data);
      } catch (e2) {
        const detail = e2?.response?.data?.detail || "Could not load profile";
        if (active) setProfileErr(detail);
        if ((detail === "Invalid token" || detail === "Not authenticated") && active) {
          clearAuth();
          nav("/login");
        }
      }
    }

    loadMe();
    return () => { active = false; };
  }, [nav]);

  function logout(){
    clearAuth();
    nav("/login");
  }

  return (
    <div className="container">
      <div className="card">
        <h2>GlucoLens Dashboard</h2>
        <p className="small">
          {sub?.required
            ? `Subscription status: ${sub?.status || "unknown"}`
            : "Logged in."}
        </p>
        <div style={{ display:"flex", gap:10, flexWrap:"wrap" }}>
          <Link className="btn" to="/referrals/new">Create Referral</Link>
          <Link className="btn secondary" to="/outcomes/new">Record Outcome</Link>
          <Link className="btn" to="/billing">Billing</Link>
          <Link className="btn secondary" to="/facilities">Facility Finder</Link>
          <button className="btn secondary" onClick={logout}>Logout</button>
        </div>
        {me && (
          <div className="small" style={{ marginTop: 14 }}>
            <div><strong>Email:</strong> {me.email}</div>
            <div><strong>Role:</strong> {me.role}</div>
          </div>
        )}
        {profileErr && <p className="small" style={{ marginTop: 14, color: "#ff8080" }}>{profileErr}</p>}
        {!me && !profileErr && auth?.access_token && <p className="small" style={{ marginTop: 14 }}>Loading profile...</p>}
      </div>
    </div>
  );
}
