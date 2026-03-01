import React, { useState } from "react";
import { api } from "../lib/api";

const COUNTRY_RE = /^[A-Z]{2}$/;

export default function Facilities(){
  const [country,setCountry]=useState(import.meta.env.VITE_DEFAULT_COUNTRY || "NG");
  const [type,setType]=useState("hospital");
  const [q,setQ]=useState("");
  const [rows,setRows]=useState([]);
  const [err,setErr]=useState("");

  async function search(){
    setErr("");
    try{
      const cc = country.trim().toUpperCase();
      if (!COUNTRY_RE.test(cc)) throw new Error("Country must be a 2-letter code (for example, NG).");
      const res = await api.get("/api/tenancy/public/facilities", { params: { country_code: cc, facility_type: type, q: q.trim() }});
      setRows(res.data);
    }catch(e){
      setErr(e?.message || "Search failed");
    }
  }

  return (
    <div className="container">
      <div className="card">
        <h2>Facility Finder</h2>
        <div className="row">
          <div>
            <label className="small">Country</label>
            <input className="input" value={country} maxLength={2} onChange={e=>setCountry(e.target.value.toUpperCase())} placeholder="NG"/>
            <div className="small">Expected format: 2-letter ISO code</div>
          </div>
          <div>
            <label className="small">Type</label>
            <select className="input" value={type} onChange={e=>setType(e.target.value)}>
              <option value="hospital">Hospital</option>
              <option value="clinic">Clinic</option>
              <option value="pharmacy">Pharmacy</option>
            </select>
          </div>
          <div>
            <label className="small">Search</label>
            <input className="input" value={q} maxLength={80} onChange={e=>setQ(e.target.value)} placeholder="e.g., Ikeja"/>
          </div>
          <div style={{ display:"flex", alignItems:"end" }}>
            <button className="btn" onClick={search}>Search</button>
          </div>
        </div>

        {err && <p style={{ color:"#ff8080" }}>{err}</p>}
        <div style={{ marginTop: 14 }}>
          {rows.map(r=>(
            <div key={r.id} className="card" style={{ marginBottom: 10 }}>
              <div style={{ display:"flex", justifyContent:"space-between", gap:10, flexWrap:"wrap" }}>
                <b>{r.name}</b>
                <span className="small">{r.facility_type} • {r.city || ""} {r.state || ""}</span>
              </div>
              <div className="small">{r.address || ""}</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
