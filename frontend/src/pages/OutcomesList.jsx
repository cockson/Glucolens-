import React, { useEffect, useState } from "react";
import { api } from "../lib/api.js";
import Locked from "./Locked.jsx";
import { isLockedError, lockedMessage } from "../lib/errors.js";
import { Link } from "react-router-dom";

export default function OutcomesList(){
  const [rows,setRows]=useState([]);
  const [err,setErr]=useState("");
  const [locked,setLocked]=useState(null);

  useEffect(()=>{
    api.get("/api/outcomes/")
      .then(r=>setRows(r.data))
      .catch(e=>{
        if (isLockedError(e)) setLocked(lockedMessage(e));
        else setErr(e?.response?.data?.detail || "Failed to load outcomes");
      });
  },[]);

  if (locked) return <Locked message={locked} />;

  return (
    <div className="container">
      <div className="card">
        <div style={{display:"flex", justifyContent:"space-between", gap:10, flexWrap:"wrap"}}>
          <h2 style={{margin:0}}>Outcomes</h2>
          <Link className="btn" to="/outcomes/new">Record Outcome</Link>
        </div>
        {err && <p style={{ color:"#ff8080" }}>{err}</p>}
        <div style={{ marginTop: 12 }}>
          {rows.map(o=>(
            <div key={o.id} className="card" style={{ marginBottom: 10 }}>
              <div style={{display:"flex", justifyContent:"space-between", gap:10, flexWrap:"wrap"}}>
                <b>{o.patient_key}</b>
                <span className="small">{o.outcome_label}</span>
              </div>
              <div className="small">{new Date(o.recorded_at).toLocaleString()}</div>
              {o.referral_id && <div className="small">Referral: {o.referral_id}</div>}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}