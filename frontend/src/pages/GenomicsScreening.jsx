import React, { useState } from "react";
import { api, SCREENING_TIMEOUT_MS } from "../lib/api";
import { getAuth } from "../lib/authStore";
import Locked from "./Locked.jsx";
import { isLockedError, lockedMessage } from "../lib/errors";

const PATIENT_KEY_RE = /^[A-Za-z0-9_-]{3,64}$/;

export default function GenomicsScreening(){
  const auth = getAuth();
  const isPublic = auth?.role === "public";
  const [patientKey, setPatientKey] = useState("");
  const [vectorText, setVectorText] = useState("");
  const [rowCsvFile, setRowCsvFile] = useState(null);
  const [result, setResult] = useState(null);
  const [predId, setPredId] = useState(null);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const [locked, setLocked] = useState(null);

  async function run(){
    setErr("");
    setBusy(true);
    setResult(null);
    setPredId(null);

    if (!isPublic && patientKey.trim().length === 0) {
      setErr("Patient key is required for clinical tracking.");
      setBusy(false);
      return;
    }
    if (!isPublic && !PATIENT_KEY_RE.test(patientKey.trim())) {
      setErr("Patient key must be 3-64 chars (letters, numbers, underscore, hyphen).");
      setBusy(false);
      return;
    }
    if (!vectorText.trim() && !rowCsvFile) {
      setErr("Paste feature vector JSON or upload one CSV row.");
      setBusy(false);
      return;
    }
    if (vectorText.trim()) {
      try {
        JSON.parse(vectorText.trim());
      } catch {
        setErr("Feature vector JSON is invalid.");
        setBusy(false);
        return;
      }
    }
    if (rowCsvFile && !String(rowCsvFile.name || "").toLowerCase().endsWith(".csv")) {
      setErr("Uploaded row file must be a .csv file.");
      setBusy(false);
      return;
    }

    try {
      const fd = new FormData();
      if (vectorText.trim()) {
        fd.append("payload", vectorText.trim());
      }
      if (rowCsvFile) {
        fd.append("row_csv", rowCsvFile);
      }
      if (patientKey.trim()) {
        fd.append("patient_key", patientKey.trim());
      }

      const r = await api.post("/api/genomics/predict", fd, {
        headers: { "Content-Type": "multipart/form-data" },
        timeout: SCREENING_TIMEOUT_MS,
      });
      setResult(r.data);
      setPredId(r.data.prediction_id);
    } catch (e) {
      if (isLockedError(e)) setLocked(lockedMessage(e));
      else setErr(e?.response?.data?.detail || "Genomics prediction failed");
    } finally {
      setBusy(false);
    }
  }

  function downloadPdf(){
    if (!predId) return;
    window.open(`${import.meta.env.VITE_API_URL}/api/genomics/report/${predId}`, "_blank");
  }

  if (locked) return <Locked message={locked} />;

  const top = result?.explainability?.top_coefficients || [];

  return (
    <div className="container">
      <div className="card">
        <h2>Genomics Screening</h2>
        <p className="small">Paste genomics feature JSON or upload one CSV row to get calibrated probability.</p>

        {!isPublic && (
          <>
            <label className="small">Patient key</label>
            <input className="input" value={patientKey} maxLength={64} onChange={e=>setPatientKey(e.target.value)} placeholder="PAT_001_ABC" />
            <div className="small">Expected format: 3-64 chars (A-Z, 0-9, _, -)</div>
            <div style={{height:10}} />
          </>
        )}

        <label className="small">Feature vector JSON (optional)</label>
        <textarea
          className="input"
          rows={8}
          value={vectorText}
          onChange={e=>setVectorText(e.target.value)}
          placeholder='{"TCF7L2_rs7903146": 1, "KCNQ1_rs2237892": 0, "Age": 52, "BMI": 31.2, "HbA1c": 6.1}'
        />

        <div style={{height:10}} />
        <label className="small">Upload one CSV row (optional)</label><br/>
        <input type="file" accept=".csv,text/csv" onChange={e=>setRowCsvFile(e.target.files?.[0] || null)} />

        <div style={{height:12}} />
        <button className="btn" onClick={run} disabled={busy}>{busy ? "Running..." : "Run genomics screening"}</button>
        {err && <p style={{ color:"#ff8080" }}>{err}</p>}

        <div className="row" style={{alignItems:"start", marginTop:12}}>
          <div className="card">
            <h3 style={{marginTop:0}}>Result</h3>
            {!result ? <p className="small">No result yet.</p> : (
              <>
                <p className="small">
                  Predicted: <b>{result.predicted_label || "N/A"}</b><br/>
                  P(positive): <b>{result.probability === null ? "N/A" : Number(result.probability).toFixed(3)}</b>
                </p>
                <button className="btn secondary" onClick={downloadPdf} disabled={!predId}>Download PDF</button>
              </>
            )}
          </div>

          <div className="card">
            <h3 style={{marginTop:0}}>Top Coefficients</h3>
            {!top.length ? <p className="small">No explainability yet.</p> : (
              <div className="small">
                {top.map((t, idx)=>(
                  <div key={`${t.feature}_${idx}`} style={{marginBottom:8}}>
                    <b>{t.feature}</b><br/>
                    coef={Number(t.coefficient).toFixed(4)} ({t.direction})
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
