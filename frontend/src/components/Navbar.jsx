import React from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { clearAuth, getAuth } from "../lib/authStore";

export default function Navbar(){
  const nav = useNavigate();
  const loc = useLocation();
  const auth = getAuth();

  if (!auth?.access_token) return null;
  if (loc.pathname === "/login" || loc.pathname.startsWith("/register")) return null;

  function logout(){
    clearAuth();
    nav("/login");
  }

  return (
    <div className="topbar">
      <div className="topbar-inner">
        <div className="topbar-left">
          <button className="btn secondary" onClick={()=>nav(-1)}>Back</button>
          <Link className="brand" to="/dashboard">GlucoLens</Link>
        </div>
        <div className="topbar-links">
          <Link to="/dashboard">Dashboard</Link>
          <Link to="/screening/tabular">Screening</Link>
          <Link to="/models/tabular">Tabular Card</Link>
          <Link to="/models/fusion">Fusion Card</Link>
          <Link to="/models/skin">Skin Card</Link>
          <Link to="/referrals">Referrals</Link>
          <Link to="/outcomes">Outcomes</Link>
          <Link to="/monitoring">Monitoring</Link>
        </div> 
        <div className="topbar-right">
          <Link className="btn secondary" to="/billing">Billing</Link>
          <button className="btn secondary" onClick={logout}>Logout</button>
        </div>
      </div>
    </div>
  );
}
