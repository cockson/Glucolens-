import React, { useState } from "react";
import { api } from "../lib/api";
import { useNavigate, Link } from "react-router-dom";

export default function RegisterBusiness() {
  const nav = useNavigate();
  const [form, setForm] = useState({
    email:"", password:"",
    org_name:"", country_code:"NG",
    facility_name:"", facility_type:"pharmacy", site_code:"SITE001"
  });
  const [err, setErr] = useState("");

  function set(k,v){ setForm(prev=>({ ...prev, [k]: v })); }

  async function submit(e){
    e.preventDefault(); setErr("");
    const payload = {
      ...form,
      email: form.email.trim().toLowerCase(),
      country_code: form.country_code.trim().toUpperCase(),
      site_code: form.site_code.trim().toUpperCase(),
      org_name: form.org_name.trim(),
      facility_name: form.facility_name.trim(),
    };
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(payload.email)) return setErr("Enter a valid business email.");
    if (!payload.password || payload.password.length < 8) return setErr("Password must be at least 8 characters.");
    if (!/^[A-Z]{2}$/.test(payload.country_code)) return setErr("Country code must be 2 letters (e.g., NG).");
    if (!/^[A-Z0-9_-]{3,30}$/.test(payload.site_code)) return setErr("Site code must be 3-30 chars: A-Z, 0-9, _ or -.");
    if (!payload.org_name) return setErr("Organization name is required.");
    if (!payload.facility_name) return setErr("Facility name is required.");
    try {
      await api.post("/api/auth/register-business", payload);
      nav("/login");
    } catch (e2) {
      const detail = e2?.response?.data?.detail;
      if (Array.isArray(detail)) {
        setErr(detail.map((x) => x?.msg || "Invalid input").join(", "));
      } else {
        setErr(detail || "Registration failed");
      }
    }
  }

  return (
    <div className="container">
      <div className="card auth-card" style={{ maxWidth: 820, margin: "40px auto" }}>
        <h2>Register Business</h2>
        <p className="small">Hospitals, clinics, and pharmacies.</p>
        <form onSubmit={submit} className="row">
          <div>
            <label className="small">Business Email</label>
            <input className="input" type="email" required value={form.email} onChange={e=>set("email", e.target.value)} />
          </div>
          <div>
            <label className="small">Password</label>
            <input className="input" type="password" required minLength={8} value={form.password} onChange={e=>set("password", e.target.value)} />
          </div>
          <div>
            <label className="small">Organization Name</label>
            <input className="input" required value={form.org_name} onChange={e=>set("org_name", e.target.value)} />
          </div>
          <div>
            <label className="small">Country Code</label>
            <input className="input" required maxLength={2} value={form.country_code} onChange={e=>set("country_code", e.target.value.toUpperCase())} placeholder="NG" />
          </div>
          <div>
            <label className="small">Facility Name</label>
            <input className="input" required value={form.facility_name} onChange={e=>set("facility_name", e.target.value)} />
          </div>
          <div>
            <label className="small">Facility Type</label>
            <select className="input" value={form.facility_type} onChange={e=>set("facility_type", e.target.value)}>
              <option value="pharmacy">Pharmacy</option>
              <option value="clinic">Clinic</option>
              <option value="hospital">Hospital</option>
            </select>
          </div>
          <div>
            <label className="small">Site Code</label>
            <input className="input" required minLength={3} maxLength={30} value={form.site_code} onChange={e=>set("site_code", e.target.value.toUpperCase())} />
          </div>
          <div className="auth-actions">
            <button className="btn" type="submit">Create account</button>
          </div>
        </form>
        {err && <p style={{ color:"#ff8080" }}>{err}</p>}
        <div className="small auth-links">
          <Link className="system-link" to="/login">Back to login</Link>
          <span className="auth-links-divider">|</span>
          <Link className="system-link" to="/register-public">Public quick-check</Link>
        </div>
      </div>
    </div>
  );
}

