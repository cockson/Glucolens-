import React from "react";
import { Link, Navigate } from "react-router-dom";
import { getAuth } from "../lib/authStore";

function LandingRedirect() {
  const auth = getAuth();
  if (!auth?.access_token) return null;
  if (auth?.role === "public") return <Navigate to="/screening/fusion" replace />;
  return <Navigate to="/dashboard" replace />;
}

export default function Landing() {
  return (
    <>
      <LandingRedirect />
      <main className="landing-page">
        <section className="landing-hero container">
          <p className="landing-kicker">GLUCOLENS</p>
          <h1>Clinical AI Screening, From First Check to Care Pathway</h1>
          <p className="landing-subtitle">
            Run multimodal diabetes risk screening, route referrals, and monitor outcomes in one platform.
          </p>
          <div className="landing-actions">
            <Link to="/login" className="btn">Login</Link>
            <Link to="/register-business" className="btn secondary">Register Organization</Link>
            <Link to="/register-public" className="system-link">Public Quick-Check Account</Link>
          </div>
        </section>

        <section className="landing-grid container">
          <article className="landing-panel">
            <h3>Hospitals and Clinics</h3>
            <p>Centralize screening and outcomes by organization and facility with role-based controls.</p>
          </article>
          <article className="landing-panel">
            <h3>Pharmacies</h3>
            <p>Capture fast walk-in assessments and escalate high-risk cases to referral partners.</p>
          </article>
          <article className="landing-panel">
            <h3>Public Users</h3>
            <p>Use guided quick-check mode for personal risk awareness before clinical confirmation.</p>
          </article>
        </section>
      </main>
    </>
  );
}

