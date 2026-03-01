import React, { useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { clearAuth, getAuth } from "../lib/authStore";

const NAV = [
  {
    title: "Screening",
    items: [
      { to: "/screening/fusion", label: "Multi-Mode" },
      { to: "/screening/tabular", label: "Tabular Mode" },
      { to: "/screening/retina", label: "Retina Mode" },
      { to: "/screening/skin", label: "Skin Mode" },
      { to: "/screening/genomics", label: "Genomic Mode" },
    ],
  },
  {
    title: "Clinical Ops",
    items: [
      { to: "/referrals", label: "Referrals" },
      { to: "/outcomes", label: "Outcomes" },
      { to: "/facilities", label: "Facility Finder" },
    ],
  },
  {
    title: "Quality & Governance",
    items: [
      { to: "/monitoring", label: "Monitoring" },
      { to: "/validation", label: "External Validation" },
      { to: "/governance/thresholds", label: "Threshold Governance" },
    ],
  },
  {
    title: "Models",
    items: [
      { to: "/models/tabular", label: "Tabular Model Card" },
      { to: "/models/retina", label: "Retina Model Card" },
      { to: "/models/genomics", label: "Genomics Model Card" },
      { to: "/quick-check", label: "Public Quick-Check" },
    ],
  },
];

export default function Sidebar(){
  const nav = useNavigate();
  const loc = useLocation();
  const auth = getAuth();
  const [hidden, setHidden] = useState(true);

  if (!auth?.access_token) return null;
  if (loc.pathname === "/login" || loc.pathname.startsWith("/register")) return null;

  function logout(){
    clearAuth();
    nav("/login");
  }

  function isActive(path){
    return loc.pathname === path || loc.pathname.startsWith(path + "/");
  }

  return (
    <>
      {hidden && (
        <button className="sidebar-fab" onClick={()=>setHidden(false)} aria-label="Open menu">
          Menu
        </button>
      )}
      <aside className={`sidebar ${hidden ? "hidden" : ""}`}>
      <div className="sidebar-top">
        <div className="brand-badge">GL</div>
        {!hidden && (
          <div>
            <div className="brand">GlucoLens</div>
            <div className="sidebar-subtitle">Clinical ML Console</div>
          </div>
        )}
        <button className="collapse-btn" onClick={()=>setHidden(true)} aria-label="Hide sidebar">
          ×
        </button>
      </div>

      <div className="sidebar-quick">
        <button className="btn secondary" onClick={()=>nav(-1)}>Back</button>
        <Link className="btn" to="/dashboard">Dashboard</Link>
      </div>

      <nav className="sidebar-nav">
        {NAV.map(section => (
          <div className="sidebar-group" key={section.title}>
            {!hidden && <div className="sidebar-group-title">{section.title}</div>}
            <div className="sidebar-group-links">
              {section.items.map(item => (
                <Link
                  key={item.to}
                  to={item.to}
                  className={`sidebar-link ${isActive(item.to) ? "active" : ""}`}
                >
                  {item.label}
                </Link>
              ))}
            </div>
          </div>
        ))}
      </nav>

      <div className="sidebar-footer">
        <Link className="btn secondary" to="/billing">Billing</Link>
        <button className="btn secondary" onClick={logout}>Logout</button>
      </div>
      </aside>
    </>
  );
}
