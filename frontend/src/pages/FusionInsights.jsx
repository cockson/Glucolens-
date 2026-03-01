import React, { useEffect, useState } from "react";
import { api } from "../lib/api";
import CleanDataView from "../components/CleanDataView.jsx";

export default function FusionInsights() {
  const [card, setCard] = useState(null);
  const [perf, setPerf] = useState(null);
  const [err, setErr] = useState("");

  useEffect(() => {
    api.get("/api/fusion/model-card").then((r) => setCard(r.data)).catch(() => setErr("Failed model card"));
    api.get("/api/fusion/performance").then((r) => setPerf(r.data)).catch(() => setErr("Failed performance"));
  }, []);

  const perfSummary = perf?.performance?.metrics_summary ?? perf?.performance ?? null;

  return (
    <div className="container">
      <div className="card">
        <h2>Fusion - Model Card & Performance</h2>
        {err && <p style={{ color: "#ff8080" }}>{err}</p>}

        {card && (
          <div className="card">
            <h3 style={{ marginTop: 0 }}>Model Card</h3>
            <CleanDataView data={card} />
          </div>
        )}

        {perfSummary && (
          <div className="card" style={{ marginTop: 12 }}>
            <h3 style={{ marginTop: 0 }}>Performance</h3>
            <CleanDataView data={perfSummary} />
          </div>
        )}
      </div>
    </div>
  );
}
