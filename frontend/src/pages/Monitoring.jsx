import React, { useEffect, useState } from "react";
import { api } from "../lib/api";
import Locked from "./Locked.jsx";
import { isLockedError, lockedMessage } from "../lib/errors";

export default function Monitoring(){
  const [outcomes,setOutcomes]=useState(null);
  const [drift,setDrift]=useState(null);
  const [sim,setSim]=useState(null);
  const [err,setErr]=useState("");
  const [locked,setLocked]=useState(null);

  async function loadAll(){
    setErr("");
    try{
      const o = await api.get("/api/monitor/outcomes?days=30");
      setOutcomes(o.data);
    }catch(e){
      if (isLockedError(e)) return setLocked(lockedMessage(e));
      setErr("Failed outcomes monitoring");
    }

    try{
      const d = await api.get("/api/monitor/drift/latest");
      setDrift(d.data);
    }catch{
      // ok
    }

    try{
      const s = await api.get("/api/monitor/simulation/flagged?threshold=0.5&days=30");
      setSim(s.data);
    }catch{
      // ok
    }
  }

  async function computeDrift(){
    setErr("");
    try{
      const d = await api.post("/api/monitor/drift/snapshot?window_days=30");
      setDrift({ ...d.data, created_at: new Date().toISOString() });
    }catch(e){
      if (isLockedError(e)) return setLocked(lockedMessage(e));
      setErr(e?.response?.data?.detail || "Failed drift snapshot");
    }
  }

  useEffect(()=>{ loadAll(); },[]);

  if (locked) return <Locked message={locked} />;

  return (
    <div className="container">
      <div className="card">
        <h2>Monitoring</h2>
        <p className="small">Outcome-based monitoring + drift (PSI/KS) + deployment simulation.</p>
        {err && <p style={{ color:"#ff8080" }}>{err}</p>}

        <div className="row" style={{ alignItems:"start" }}>
          <div className="card">
            <h3 style={{ marginTop:0 }}>Outcome Monitoring (last 30 days)</h3>
            <pre className="small" style={{ whiteSpace:"pre-wrap" }}>{JSON.stringify(outcomes, null, 2)}</pre>
          </div>

          <div className="card">
            <h3 style={{ marginTop:0 }}>Simulation</h3>
            <pre className="small" style={{ whiteSpace:"pre-wrap" }}>{JSON.stringify(sim, null, 2)}</pre>
          </div>
        </div>

        <div className="card" style={{ marginTop: 12 }}>
          <div style={{ display:"flex", justifyContent:"space-between", gap:10, flexWrap:"wrap" }}>
            <h3 style={{ margin:0 }}>Drift Monitoring</h3>
            <button className="btn secondary" onClick={computeDrift}>Compute drift snapshot</button>
          </div>
          <pre className="small" style={{ whiteSpace:"pre-wrap", marginTop: 10 }}>
{JSON.stringify(drift, null, 2)}
          </pre>
        </div>
      </div>
    </div>
  );
}
