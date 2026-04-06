import React, { useEffect, useState } from "react";
import { clearAuth, getAuth } from "../lib/authStore";
import { useNavigate, Link } from "react-router-dom";
import { api } from "../lib/api";

export default function Dashboard(){
  const nav = useNavigate();
  const auth = getAuth();
  const isAdmin = ["facility_admin", "org_admin", "super_admin"].includes(auth?.role);
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
      <div className="card" style={{ padding: 24 }}>
        <div style={{ display: "flex", justifyContent: "space-between", gap: 16, flexWrap: "wrap", alignItems: "baseline" }}>
          <div>
            <h2 style={{ margin: 0 }}>GlucoLens Dashboard</h2>
            <p className="small" style={{ marginTop: 8 }}>
              {sub?.required
                ? `Subscription status: ${sub?.status || "unknown"}`
                : "Logged in."}
            </p>
          </div>
          <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
            <Link className="btn" to="/billing">Billing</Link>
            <button className="btn secondary" onClick={logout}>Logout</button>
          </div>
        </div>

        {me && (
          <div className="small" style={{ marginTop: 12 }}>
            <span><strong>Email:</strong> {me.email}</span>
            <span style={{ marginLeft: 16 }}><strong>Role:</strong> {me.role}</span>
          </div>
        )}
        {profileErr && <p className="small" style={{ marginTop: 12, color: "#ff8080" }}>{profileErr}</p>}
        {!me && !profileErr && auth?.access_token && <p className="small" style={{ marginTop: 12 }}>Loading profile...</p>}
      </div>

      <div style={{ height: 16 }} />

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(260px, 1fr))", gap: 16 }}>
        <div className="card">
          <h3 style={{ marginTop: 0 }}>Screening</h3>
          <p className="small">Run clinical screening workflows.</p>
          <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
            <Link className="btn" to="/screening/tabular">Tabular Mode</Link>
            <Link className="btn" to="/screening/fusion">Multi-Mode </Link>
            <Link className="btn secondary" to="/screening/retina">Retina Mode</Link>
            <Link className="btn secondary" to="/screening/skin">Skin Mode</Link>
          </div>
        </div>

        <div className="card">
          <h3 style={{ marginTop: 0 }}>Referrals & Outcomes</h3>
          <p className="small">Track patient flow and confirmed outcomes.</p>
          <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
            <Link className="btn" to="/referrals/new">Create Referral</Link>
            <Link className="btn secondary" to="/referrals">Referrals List</Link>
            <Link className="btn secondary" to="/outcomes/new">Record Outcome</Link>
            <Link className="btn secondary" to="/outcomes">Outcomes List</Link>
          </div>
        </div>

        <div className="card">
          <h3 style={{ marginTop: 0 }}>Monitoring & Validation</h3>
          <p className="small">Quality, drift, and external validation tools.</p>
          <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
            <Link className="btn secondary" to="/monitoring">Monitoring</Link>
            <Link className="btn secondary" to="/validation">External Validation</Link>
            <Link className="btn secondary" to="/governance/thresholds">Threshold Governance</Link>
          </div>
        </div>

        <div className="card">
          <h3 style={{ marginTop: 0 }}>Models & Tools</h3>
          <p className="small">Model cards and supporting tools.</p>
          <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
            <Link className="btn secondary" to="/models/tabular">Tabular Model Card</Link>
            <Link className="btn secondary" to="/models/fusion">Fusion Model Card</Link>
            <Link className="btn secondary" to="/models/retina">Retina Model Card</Link>
            <Link className="btn secondary" to="/models/skin">Skin Model Card</Link>
            <Link className="btn secondary" to="/models/genomics">Genomics Model Card</Link>
            <Link className="btn secondary" to="/quick-check">Public Quick-Check</Link>
            <Link className="btn secondary" to="/facilities">Facility Finder</Link>
          </div>
        </div>

        {isAdmin && (
          <div className="card">
            <h3 style={{ marginTop: 0 }}>Admin</h3>
            <p className="small">Organization-level oversight and model retention audit.</p>
            <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
              <Link className="btn" to="/admin">Admin Console</Link>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
