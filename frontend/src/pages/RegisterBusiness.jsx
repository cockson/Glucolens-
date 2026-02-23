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
    try {
      await api.post("/api/auth/register-business", form);
      nav("/login");
    } catch (e2) {
      setErr(e2?.response?.data?.detail || "Registration failed");
    }
  }

  return (
    <div className="container">
      <div className="card" style={{ maxWidth: 820, margin: "40px auto" }}>
        <h2>Register Business</h2>
        <p className="small">Hospitals, clinics, pharmacies (multi-country).</p>
        <form onSubmit={submit} className="row">
          <div>
            <label className="small">Business Email</label>
            <input className="input" value={form.email} onChange={e=>set("email", e.target.value)} />
          </div>
          <div>
            <label className="small">Password</label>
            <input className="input" type="password" value={form.password} onChange={e=>set("password", e.target.value)} />
          </div>
          <div>
            <label className="small">Org Name</label>
            <input className="input" value={form.org_name} onChange={e=>set("org_name", e.target.value)} />
          </div>
          <div>
            <label className="small">Country Code</label>
            <input className="input" value={form.country_code} onChange={e=>set("country_code", e.target.value.toUpperCase())} />
          </div>
          <div>
            <label className="small">Facility Name</label>
            <input className="input" value={form.facility_name} onChange={e=>set("facility_name", e.target.value)} />
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
            <input className="input" value={form.site_code} onChange={e=>set("site_code", e.target.value)} />
          </div>
          <div style={{ display:"flex", alignItems:"end", gap:10 }}>
            <button className="btn" type="submit">Create</button>
            <Link className="btn secondary" to="/login">Back</Link>
          </div>
        </form>
        {err && <p style={{ color:"#ff8080" }}>{err}</p>}
      </div>
    </div>
  );
}