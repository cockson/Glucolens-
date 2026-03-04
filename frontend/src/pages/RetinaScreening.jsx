import React, { useState } from "react";
import { api, SCREENING_TIMEOUT_MS } from "../lib/api";
import { getAuth } from "../lib/authStore";
import Locked from "./Locked.jsx";
import { isLockedError, lockedMessage } from "../lib/errors";

const PATIENT_KEY_RE = /^[A-Za-z0-9_-]{3,64}$/;
const MAX_IMAGE_BYTES = 10 * 1024 * 1024;

export default function RetinaScreening(){
  const auth = getAuth();
  const isPublic = auth?.role === "public";
  const [file,setFile]=useState(null);
  const [result,setResult]=useState(null);
  const [predId,setPredId]=useState(null);
  const [err,setErr]=useState("");
  const [busy,setBusy]=useState(false);
  const [locked,setLocked]=useState(null);
  const [patientKey, setPatientKey] = useState("");
  const labelText = (label) => {
    if (label === "t2d") return "Type 2 Diabetes";
    if (label === "not_diabetic") return "Not Diabetic";
    return label || "N/A";
  };

  async function run(){
    setErr(""); setResult(null); setPredId(null);
    if (!isPublic && patientKey.trim().length === 0) { setErr("Patient key is required for clinical tracking."); return; }
    if (!isPublic && !PATIENT_KEY_RE.test(patientKey.trim())) { setErr("Patient key must be 3-64 chars (letters, numbers, underscore, hyphen)."); return; }
    if(!file){ setErr("Choose an image."); return; }
    if (!String(file.type || "").startsWith("image/")) { setErr("Selected file must be an image."); return; }
    if (file.size > MAX_IMAGE_BYTES) { setErr("Image is too large (max 10MB)."); return; }
    setBusy(true);
    try{
      const fd = new FormData();
      fd.append("file", file);
      if (patientKey.trim()) fd.append("patient_key", patientKey.trim());
      const r = await api.post("/api/retina/predict", fd, {
        headers: { "Content-Type":"multipart/form-data" },
        timeout: SCREENING_TIMEOUT_MS,
      });
      setResult(r.data);
      setPredId(r.data.prediction_id);
    }catch(e){
      if (isLockedError(e)) setLocked(lockedMessage(e));
      else setErr(e?.response?.data?.detail || "Prediction failed");
    }finally{
      setBusy(false);
    }
  }

  async function downloadPdf(){
    if(!predId) return;
    setErr("");
    try {
      const res = await api.get(`/api/retina/report/${predId}`, {
        responseType: "blob",
      });
      const blob = new Blob([res.data], { type: "application/pdf" });
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `glucolens_retina_report_${predId}.pdf`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      window.URL.revokeObjectURL(url);
    } catch (e) {
      if (isLockedError(e)) setLocked(lockedMessage(e));
      else setErr(e?.response?.data?.detail || "Failed to download report");
    }
  }

  if (locked) return <Locked message={locked} />;

  const overlay = result?.explainability?.overlay_png_base64
    ? `data:image/png;base64,${result.explainability.overlay_png_base64}`
    : null;

  return (
    <div className="container">
      <div className="card">
        <h2>Retina Screening (Grad-CAM)</h2>
        <p className="small">Upload retina image for calibrated probability and Grad-CAM overlay.</p>
        {!isPublic && (
          <>
            <label className="small">Patient key</label>
            <input className="input" value={patientKey} maxLength={64} onChange={e=>setPatientKey(e.target.value)} placeholder="PAT_001_ABC" />
            <div className="small">Expected format: 3-64 chars (A-Z, 0-9, _, -)</div>
            <div style={{height:10}} />
          </>
        )}


        <input type="file" accept="image/*" onChange={e=>setFile(e.target.files?.[0] || null)} />
        <p className="small" style={{ marginTop:8 }}>
          Expected image quality: JPG or PNG, clear focus, no heavy blur/glare, evenly lit, minimum 512x512 pixels, recommended 1024x1024+, and file size up to 10MB.
        </p>
        <p className="small" style={{ marginTop:6 }}>
          Retina capture guidance: center the optic disc/macula in frame, keep camera steady, avoid flash reflections, capture both eyes separately, and retake if vessels are not clearly visible.
        </p>
        <div style={{height:10}} />
        <button className="btn" onClick={run} disabled={busy}>{busy ? "Running…" : "Run retina screening"}</button>
        {err && <p style={{ color:"#ff8080" }}>{err}</p>}

        <div className="row" style={{alignItems:"start", marginTop:12}}>
          <div className="card">
            <h3 style={{marginTop:0}}>Result</h3>
            {!result ? <p className="small">No result yet.</p> : (
              <>
                <p className="small">Predicted: <b>{labelText(result.predicted_label)}</b></p>
                <p className="small">
                  P(not diabetic): <b>{Number(result.probabilities?.not_diabetic).toFixed(3)}</b><br/>
                  P(Type 2 Diabetes / positive proxy): <b>{Number(result.probabilities?.t2d).toFixed(3)}</b>
                </p>
                <div className="card" style={{ marginTop: 10 }}>
                  <b>Interpretation</b>
                  <p className="small" style={{ marginTop: 8 }}>
                    Patient: {result.predicted_label === "t2d"
                      ? "The retina screen suggests retinal patterns associated with higher Type 2 Diabetes risk. Please see a clinician for confirmatory assessment."
                      : "The retina screen does not show strong high-risk retinal patterns at this time. Continue routine checks."}
                  </p>
                  <p className="small" style={{ marginTop: 6 }}>
                    Clinician: {result.predicted_label === "t2d"
                      ? "Positive proxy signal from retinal patterns. Correlate with systemic findings and confirm with standard glycemic diagnostics."
                      : "Negative proxy signal. Interpret with caution if image quality is marginal or clinical suspicion remains high."}
                  </p>
                </div>
                <button className="btn secondary" onClick={downloadPdf} disabled={!predId}>Download PDF</button>
              </>
            )}
          </div>

          <div className="card">
            <h3 style={{marginTop:0}}>Grad-CAM</h3>
            {!overlay ? <p className="small">No overlay yet.</p> : (
              <img src={overlay} alt="Grad-CAM overlay" style={{maxWidth:"100%", borderRadius:12}} />
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
