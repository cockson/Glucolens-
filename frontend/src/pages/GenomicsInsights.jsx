import React, { useEffect, useState } from "react";
import { api } from "../lib/api";

export default function GenomicsInsights(){
  const [card, setCard] = useState(null);
  const [perf, setPerf] = useState(null);
  const [err, setErr] = useState("");

  useEffect(() => {
    api.get("/api/genomics/model-card").then(r => setCard(r.data)).catch(() => setErr("Failed model card"));
    api.get("/api/genomics/performance").then(r => setPerf(r.data)).catch(() => setErr("Failed performance"));
  }, []);

  return (
    <div className="container">
      <div className="card">
        <h2>Genomics - Model Card & Performance</h2>
        {err && <p style={{ color:"#ff8080" }}>{err}</p>}

        {card && (
          <div className="card">
            <h3 style={{ marginTop:0 }}>Model Card</h3>
            <pre className="small" style={{ whiteSpace:"pre-wrap" }}>{JSON.stringify(card, null, 2)}</pre>
          </div>
        )}

        {perf && (
          <div className="card" style={{ marginTop:12 }}>
            <h3 style={{ marginTop:0 }}>Performance</h3>
            <pre className="small" style={{ whiteSpace:"pre-wrap" }}>{JSON.stringify(perf.performance || perf, null, 2)}</pre>
          </div>
        )}
      </div>
    </div>
  );
}
