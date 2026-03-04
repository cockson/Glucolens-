import React, { useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { clearAuth, getAuth } from "../lib/authStore";
import { getTheme, toggleTheme } from "../lib/theme";

const CLINICIAN_ROLES = new Set(["clinician", "facility_admin", "org_admin", "super_admin"]);

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
      { to: "/models/fusion", label: "Fusion Model Card" },
      { to: "/models/retina", label: "Retina Model Card" },
      { to: "/models/skin", label: "Skin Model Card" },
      { to: "/models/genomics", label: "Genomics Model Card" },
      { to: "/quick-check", label: "Public Quick-Check" },
    ],
  },
];

export default function Sidebar(){
  const nav = useNavigate();
  const loc = useLocation();
  const auth = getAuth();
  const isClinician = CLINICIAN_ROLES.has(auth?.role);
  const [theme, setTheme] = useState(getTheme());
  const [hidden, setHidden] = useState(false);

  if (!auth?.access_token) return null;
  if (loc.pathname === "/login" || loc.pathname.startsWith("/register")) return null;

  function logout(){
    clearAuth();
    nav("/login");
  }

  function isActive(path){
    return loc.pathname === path || loc.pathname.startsWith(path + "/");
  }

  function onToggleTheme() {
    setTheme(toggleTheme());
  }

  const publicNav = [
    {
      title: "Screening",
      items: [{ to: "/screening/fusion", label: "Fusion Screening" }],
    },
  ];

  const navSections = isClinician ? NAV : publicNav;

  return (
    <>
      {hidden && (
        <button className="sidebar-fab" onClick={()=>setHidden(false)} aria-label="Open menu">
          Menu
        </button>
      )}
      <aside className={`sidebar ${hidden ? "hidden" : ""}`}>
      <div className="sidebar-top">
        <div className="brand-stack">
          <div className="brand-mark" aria-hidden="true">
            <div className="brand-logo-track">
              <div className="brand-logo-sweep">
                <div className="brand-logo-lens">
                  <div className="brand-logo-handle" />
                </div>
              </div>
            </div>
          </div>
          {!hidden && (
            <div>
            <div className="brand">GlucoLens</div>
            <div className="sidebar-subtitle">Clinical ML Console</div>
            </div>
          )}
        </div>
        <button className="collapse-btn" onClick={()=>setHidden(true)} aria-label="Hide sidebar">x</button>
      </div>

      <div className="sidebar-quick">
        <button className="btn secondary" onClick={()=>nav(-1)}>Back</button>
        <Link className="btn" to="/dashboard">Dashboard</Link>
      </div>

      <nav className="sidebar-nav">
        {navSections.map(section => (
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
        {isClinician ? (
          <Link className="btn secondary" to="/billing">Billing</Link>
        ) : (
          <Link className="btn" to="/register-business">Upgrade</Link>
        )}
        <button className="btn secondary" onClick={onToggleTheme}>
          {theme === "dark" ? "Light mode" : "Dark mode"}
        </button>
        <button className="btn secondary" onClick={logout}>Logout</button>
      </div>
      </aside>
    </>
  );
}

