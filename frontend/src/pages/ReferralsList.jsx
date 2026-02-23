import React, { useEffect, useState } from "react";
import { api } from "../lib/api";
import Locked from "./Locked.jsx";
import { isLockedError, lockedMessage } from "../lib/errors";
import { Link } from "react-router-dom";

export default function ReferralsList(){
  const [rows,setRows]=useState([]);
  const [err,setErr]=useState("");
  const [locked,setLocked]=useState(null);

  useEffect(()=>{
    api.get("/api/referrals/")
      .then(r=>setRows(r.data))
      .catch(e=>{
        if (isLockedError(e)) setLocked(lockedMessage(e));
        else setErr(e?.response?.data?.detail || "Failed to load referrals");
      });
  },[]);

  if (locked) return <Locked message={locked} />;

  return (
    <div className="container">
      <div className="card">
        <div style={{display:"flex", justifyContent:"space-between", gap:10, flexWrap:"wrap"}}>
          <h2 style={{margin:0}}>Referrals</h2>
          <Link className="btn" to="/referrals/new">Create Referral</Link>
        </div>
        {err && <p style={{ color:"#ff8080" }}>{err}</p>}
        <div style={{ marginTop: 12 }}>
          {rows.map(r=>(
            <div key={r.id} className="card" style={{ marginBottom: 10 }}>
              <div style={{display:"flex", justifyContent:"space-between", gap:10, flexWrap:"wrap"}}>
                <b>{r.patient_key}</b>
                <span className="small">{r.status} • {r.risk_score}/100</span>
              </div>
              <div className="small">{new Date(r.created_at).toLocaleString()}</div>
              <div style={{ marginTop: 10 }}>
                <Link className="btn secondary" to={`/referral/${r.id}`}>Open</Link>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}