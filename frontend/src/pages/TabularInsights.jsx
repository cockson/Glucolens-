import React, { useEffect, useState } from "react";
import { api } from "../lib/api";
import Locked from "./Locked.jsx";
import { isLockedError, lockedMessage } from "../lib/errors";

export default function TabularInsights(){
  const [card,setCard]=useState(null);
  const [perf,setPerf]=useState(null);
  const [err,setErr]=useState("");
  const [locked,setLocked]=useState(null);
  const perfSummary = perf?.performance?.best ?? perf?.performance ?? null;

  useEffect(()=>{
    api.get("/api/predict/tabular/model-card")
      .then(r=>setCard(r.data))
      .catch(()=>setErr("Failed to load model card"));

    api.get("/api/predict/tabular/performance")
      .then(r=>setPerf(r.data))
      .catch(e=>{
        if (isLockedError(e)) setLocked(lockedMessage(e));
        else setErr("Failed to load performance");
      });
  },[]);

  if (locked) return <Locked message={locked} />;

  return (
    <div className="container">
      <div className="card">
        <h2>Tabular Model — Card & Performance</h2>
        {err && <p style={{ color:"#ff8080" }}>{err}</p>}

        {card && (
          <div className="card" style={{ marginTop: 12 }}>
            <h3 style={{ marginTop: 0 }}>Model Card</h3>
            <pre className="small" style={{ whiteSpace:"pre-wrap" }}>{JSON.stringify(card, null, 2)}</pre>
          </div>
        )}

        {perf && (
          <div className="card" style={{ marginTop: 12 }}>
            <h3 style={{ marginTop: 0 }}>Performance</h3>
            <pre className="small" style={{ whiteSpace:"pre-wrap" }}>
{JSON.stringify(perfSummary, null, 2)}
            </pre>
            <h4>Top comparison rows (best → worst)</h4>
            <div className="small">
              {(perf.comparison || []).slice(0, 8).map((r, i)=>(
                <div key={i} className="card" style={{ marginBottom: 8 }}>
                  <b>{r.model}</b> | SMOTE: {String(r.smote)} | calib: {r.calibration} <br/>
                  AUROC: {Number(r.auroc_oof).toFixed(3)} (CI {Number(r.auroc_ci_low).toFixed(3)}–{Number(r.auroc_ci_high).toFixed(3)}) <br/>
                  Brier: {Number(r.brier_oof).toFixed(4)} | ECE: {Number(r.ece_oof).toFixed(4)} | F1: {Number(r.f1_oof).toFixed(3)}
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
