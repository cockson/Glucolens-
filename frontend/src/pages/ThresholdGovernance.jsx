import React, { useEffect, useState } from "react";
import { api } from "../lib/api";

export default function ThresholdGovernance(){
  const [facilityId,setFacilityId]=useState("");
  const [days,setDays]=useState(180);
  const [policies,setPolicies]=useState([]);
  const [err,setErr]=useState("");
  const [busy,setBusy]=useState(false);

  async function refresh(){
    const p = await api.get("/api/thresholds/policies");
    setPolicies(p.data);
  }
  useEffect(()=>{ refresh(); },[]);

  async function compute(){
    setErr(""); setBusy(true);
    try{
      const q = new URLSearchParams();
      if(facilityId.trim()) q.set("facility_id", facilityId.trim());
      q.set("days", String(days));
      await api.post(`/api/thresholds/compute?${q.toString()}`);
      await refresh();
    }catch(e){
      setErr(e?.response?.data?.detail || "Compute failed");
    }finally{
      setBusy(false);
    }
  }

  async function approve(id){
    setErr(""); setBusy(true);
    try{
      await api.post(`/api/thresholds/approve/${id}`);
      await refresh();
    }catch(e){
      setErr(e?.response?.data?.detail || "Approve failed");
    }finally{
      setBusy(false);
    }
  }

  return (
    <div className="container">
      <div className="card">
        <h2>Threshold Governance (Fusion)</h2>
        <p className="small">Compute thresholds from linked outcomes using DCA net benefit; approve to activate per facility/country.</p>
        {err && <p style={{color:"#ff8080"}}>{err}</p>}

        <div className="card">
          <h3 style={{marginTop:0}}>Compute new threshold</h3>
          <label className="small">Facility ID (optional)</label>
          <input className="input" value={facilityId} onChange={e=>setFacilityId(e.target.value)} />
          <div style={{height:8}} />
          <label className="small">Window days</label>
          <input className="input" value={days} onChange={e=>setDays(Number(e.target.value||180))} />
          <div style={{height:10}} />
          <button className="btn" onClick={compute} disabled={busy}>{busy?"Working…":"Compute threshold"}</button>
        </div>

        <div className="card" style={{marginTop:12}}>
          <h3 style={{marginTop:0}}>Policies</h3>
          <div className="small">
            {policies.map(p=>(
              <div key={p.id} className="card" style={{marginBottom:10}}>
                <b>{p.status.toUpperCase()}</b> • thr={Number(p.threshold).toFixed(2)} • scope={p.facility_id ? "facility" : "country/default"}<br/>
                id: {p.id.slice(0,8)}…<br/>
                n={p.evidence?.n} pos_rate={Number(p.evidence?.positive_rate||0).toFixed(3)} best_nb={Number(p.evidence?.best_net_benefit||0).toFixed(4)}<br/>
                {p.status === "proposed" && (
                  <button className="btn secondary" onClick={()=>approve(p.id)} disabled={busy}>Approve</button>
                )}
              </div>
            ))}
            {!policies.length && <p className="small">No policies yet.</p>}
          </div>
        </div>
      </div>
    </div>
  );
}