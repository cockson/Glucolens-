import React, { useEffect, useState } from "react";
import { api } from "../lib/api";
import Locked from "./Locked.jsx";
import { isLockedError, lockedMessage } from "../lib/errors";
import CleanDataView from "../components/CleanDataView.jsx";

function fmt(v, d = 3) {
  const n = Number(v);
  return Number.isFinite(n) ? n.toFixed(d) : "N/A";
}

function TabularInsights() {
  const [card, setCard] = useState(null);
  const [perf, setPerf] = useState(null);
  const [err, setErr] = useState("");
  const [locked, setLocked] = useState(null);

  useEffect(() => {
    api.get("/api/predict/tabular/model-card")
      .then((r) => setCard(r.data))
      .catch(() => setErr("Failed to load model card"));

    api.get("/api/predict/tabular/performance")
      .then((r) => setPerf(r.data))
      .catch((e) => {
        if (isLockedError(e)) setLocked(lockedMessage(e));
        else setErr("Failed to load performance");
      });
  }, []);

  if (locked) return <Locked message={locked} />;

  const perfSummary = perf?.performance?.best ?? perf?.performance ?? null;

  return (
    <div className="container">
      <div className="card">
        <h2>Tabular Model - Card & Performance</h2>
        {err && <p style={{ color: "#ff8080" }}>{err}</p>}

        {card && (
          <div className="card" style={{ marginTop: 12 }}>
            <h3 style={{ marginTop: 0 }}>Model Card</h3>
            <CleanDataView data={card} />
          </div>
        )}

        {perfSummary && (
          <div className="card" style={{ marginTop: 12 }}>
            <h3 style={{ marginTop: 0 }}>Performance</h3>
            <CleanDataView data={perfSummary} />

            <h4>Top comparison rows (best to worst)</h4>
            <div className="small">
              {(perf?.comparison || []).slice(0, 8).map((r, i) => {
                const ece = r.ece_diabetic_vs_rest_oof ?? r.ece_oof;
                return (
                  <div key={i} className="card" style={{ marginBottom: 8 }}>
                    <b>{r.model}</b> | SMOTE: {String(r.smote)} | calib: {r.calibration}
                    <br />
                    AUROC: {fmt(r.auroc_oof)} (CI {fmt(r.auroc_ci_low)}-{fmt(r.auroc_ci_high)})
                    <br />
                    Brier: {fmt(r.brier_oof, 4)} | ECE: {fmt(ece, 4)} | F1: {fmt(r.f1_oof)}
                  </div>
                );
              })}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

export { TabularInsights };
export default TabularInsights;
