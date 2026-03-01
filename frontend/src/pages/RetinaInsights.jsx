import React, { useEffect, useState } from "react";
import { api } from "../lib/api";
import CleanDataView from "../components/CleanDataView.jsx";

export default function RetinaInsights(){
  const [card,setCard]=useState(null);
  const [perf,setPerf]=useState(null);
  const [err,setErr]=useState("");
  const perfSummary = perf?.performance?.val ?? perf?.performance ?? null;

  useEffect(()=>{
    api.get("/api/retina/model-card").then(r=>setCard(r.data)).catch(()=>setErr("Failed model card"));
    api.get("/api/retina/performance").then(r=>setPerf(r.data)).catch(()=>setErr("Failed performance"));
  },[]);

  return (
    <div className="container">
      <div className="card">
        <h2>Retina — Model Card & Performance</h2>
        {err && <p style={{ color:"#ff8080" }}>{err}</p>}

        {card && (
          <div className="card">
            <h3 style={{marginTop:0}}>Model Card</h3>
            <CleanDataView data={card} />
          </div>
        )}

        {perf && (
          <div className="card" style={{marginTop:12}}>
            <h3 style={{marginTop:0}}>Performance</h3>
            <CleanDataView data={perfSummary} />
          </div>
        )}
      </div>
    </div>
  );
}
