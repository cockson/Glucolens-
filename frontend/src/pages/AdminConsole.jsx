import React, { useEffect, useState } from "react";
import { api } from "../lib/api";

export default function AdminConsole() {
  const [summary, setSummary] = useState(null);
  const [audit, setAudit] = useState(null);
  const [users, setUsers] = useState([]);
  const [err, setErr] = useState("");

  useEffect(() => {
    let alive = true;

    async function load() {
      try {
        const [summaryRes, auditRes, usersRes] = await Promise.all([
          api.get("/api/admin/summary"),
          api.get("/api/admin/model-audit"),
          api.get("/api/admin/users"),
        ]);
        if (!alive) return;
        setSummary(summaryRes.data);
        setAudit(auditRes.data);
        setUsers(usersRes.data || []);
      } catch (e) {
        if (!alive) return;
        setErr(e?.response?.data?.detail || "Failed to load admin console");
      }
    }

    load();
    return () => { alive = false; };
  }, []);

  return (
    <div className="container">
      <div className="card">
        <h2 style={{ marginTop: 0 }}>Admin Console</h2>
        <p className="small">Operational summary, user oversight, and model retention audit for screening governance.</p>
        {err && <p style={{ color: "#ff8080" }}>{err}</p>}
      </div>

      <div style={{ height: 16 }} />

      <div className="row" style={{ alignItems: "start", marginTop: 0 }}>
        <div className="card">
          <h3 style={{ marginTop: 0 }}>Operational Snapshot</h3>
          {!summary ? <p className="small">Loading summary...</p> : (
            <>
              <p className="small">Scope: <b>{summary.scope}</b></p>
              <div className="row" style={{ marginTop: 8 }}>
                {Object.entries(summary.counts || {}).map(([key, value]) => (
                  <div key={key} className="card" style={{ margin: 0 }}>
                    <div className="small" style={{ textTransform: "capitalize" }}>{key.replaceAll("_", " ")}</div>
                    <div style={{ fontSize: 28, fontWeight: 700 }}>{value}</div>
                  </div>
                ))}
              </div>
            </>
          )}
        </div>

        <div className="card">
          <h3 style={{ marginTop: 0 }}>Prediction Mix</h3>
          {!summary ? <p className="small">Loading predictions...</p> : (
            <>
              <p className="small"><b>By modality</b></p>
              {(Object.entries(summary.predictions_by_modality || {}).length === 0) ? (
                <p className="small">No prediction records yet.</p>
              ) : (
                Object.entries(summary.predictions_by_modality || {}).map(([key, value]) => (
                  <p key={key} className="small" style={{ margin: "6px 0" }}>{key}: <b>{value}</b></p>
                ))
              )}
              <div style={{ height: 12 }} />
              <p className="small"><b>By label</b></p>
              {(Object.entries(summary.predictions_by_label || {}).length === 0) ? (
                <p className="small">No labels yet.</p>
              ) : (
                Object.entries(summary.predictions_by_label || {}).map(([key, value]) => (
                  <p key={key} className="small" style={{ margin: "6px 0" }}>{key}: <b>{value}</b></p>
                ))
              )}
            </>
          )}
        </div>
      </div>

      <div style={{ height: 16 }} />

      <div className="card">
        <h3 style={{ marginTop: 0 }}>Screening Model Audit</h3>
        {!audit ? <p className="small">Loading audit...</p> : (
          <>
            <p className="small">
              As of <b>{audit.as_of}</b>, retain <b>{audit.recommended_retention?.primary_screening_model}</b> as the
              primary screening model and <b>{audit.recommended_retention?.core_fallback_model}</b> as the core fallback.
            </p>
            {(audit.models || []).map((model) => (
              <div key={model.modality} className="card" style={{ marginTop: 12 }}>
                <div style={{ display: "flex", justifyContent: "space-between", gap: 12, flexWrap: "wrap" }}>
                  <div>
                    <h4 style={{ margin: 0, textTransform: "capitalize" }}>{model.modality}</h4>
                    <p className="small" style={{ marginTop: 6 }}>
                      {model.model_name} {model.model_version ? `(${model.model_version})` : ""}
                    </p>
                  </div>
                  <div className="small"><b>{model.decision}</b></div>
                </div>
                <p className="small" style={{ marginTop: 8 }}>{model.screening_role}</p>
                <p className="small" style={{ marginTop: 8 }}>
                  Metrics: {Object.entries(model.metrics || {}).map(([k, v]) => `${k}=${v ?? "n/a"}`).join(" | ")}
                </p>
                <p className="small" style={{ marginTop: 8 }}>
                  Rationale: {(model.rationale || []).join(" ")}
                </p>
                <p className="small" style={{ marginTop: 8 }}>
                  Risks: {(model.risks || []).join(" ")}
                </p>
              </div>
            ))}
          </>
        )}
      </div>

      <div style={{ height: 16 }} />

      <div className="card">
        <h3 style={{ marginTop: 0 }}>Recent Users</h3>
        {!users.length ? <p className="small">No users available.</p> : users.map((user) => (
          <div key={user.id} style={{ padding: "10px 0", borderBottom: "1px solid rgba(255,255,255,0.08)" }}>
            <div>{user.email}</div>
            <div className="small">
              {user.role} | active: {String(user.is_active)} | created: {user.created_at || "n/a"}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
