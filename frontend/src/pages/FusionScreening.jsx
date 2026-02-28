import React, { useState } from "react";
import { api } from "../lib/api";
import { getAuth } from "../lib/authStore";
import Locked from "./Locked.jsx";
import { isLockedError, lockedMessage } from "../lib/errors";

export default function FusionScreening(){
  const auth = getAuth();
  const isPublic = auth?.role === "public";
  const [file,setFile]=useState(null);
  const [country,setCountry]=useState("NG");
  const [patientKey, setPatientKey] = useState("");
  const [form,setForm]=useState({ age:"", sex:"", bmi:"", waist_circumference:"", hip_circumference:"", systolic_bp:"", diastolic_bp:"" });
  const [result,setResult]=useState(null);
  const [predId,setPredId]=useState(null);
  const [err,setErr]=useState("");
  const [busy,setBusy]=useState(false);
  const [locked,setLocked]=useState(null);
  const fusionLabelText = (label) => {
    if (label === "screen_positive_refer") return "Screen Positive (Refer)";
    if (label === "screen_negative") return "Screen Negative";
    if (label === "retake_image") return "Retake Image Needed";
    if (label === "insufficient_data") return "Insufficient Data";
    return label || "N/A";
  };

  function set(k,v){ setForm(p=>({ ...p, [k]: v })); }

  async function run(){
    setErr(""); setBusy(true);
    if (!isPublic && patientKey.trim().length === 0) { setErr("Patient key is required for clinical tracking."); setBusy(false); return; }
    try{
      const payloadObj = { country_code: country, patient_key: patientKey.trim() || null, ...Object.fromEntries(Object.entries(form).map(([k,v])=>[k, v===""?null:v])) };
      const fd = new FormData();
      fd.append("payload", JSON.stringify(payloadObj));
      if(file) fd.append("retina", file);

      const r = await api.post("/api/fusion/predict", fd, { headers: { "Content-Type":"multipart/form-data" }});
      setResult(r.data);
      setPredId(r.data.prediction_id);
    }catch(e){
      if (isLockedError(e)) setLocked(lockedMessage(e));
      else setErr(e?.response?.data?.detail || "Fusion prediction failed");
    }finally{
      setBusy(false);
    }
  }

  function downloadPdf(){
    if(!predId) return;
    window.open(`${import.meta.env.VITE_API_URL}/api/fusion/report/${predId}`, "_blank");
  }

  if (locked) return <Locked message={locked} />;

  const overlay = result?.retina?.explainability?.overlay_png_base64
    ? `data:image/png;base64,${result.retina.explainability.overlay_png_base64}`
    : null;

  return (
    <div className="container">
      <div className="card">
        <h2>Fusion Screening (Tabular + Retina)</h2>
        <p className="small">Upload optional retina image. Fusion uses calibrated probabilities with conservative abstain rules.</p>

        <label className="small">Country</label>
        <input className="input" value={country} onChange={e=>setCountry(e.target.value.toUpperCase())} />

        {!isPublic && (
          <>
            <label className="small">Patient key</label>
            <input className="input" value={patientKey} onChange={e=>setPatientKey(e.target.value)} placeholder="PAT_001_ABC" />
            <div style={{height:10}} />
          </>
        )}

        <div className="row" style={{marginTop:10}}>
          <div>
            <label className="small">Age</label>
            <input className="input" value={form.age} onChange={e=>set("age",e.target.value)} />
          </div>
          <div>
            <label className="small">Sex</label>
            <select className="input" value={form.sex} onChange={e=>set("sex",e.target.value)}>
              <option value="">Unknown</option><option value="M">Male</option><option value="F">Female</option>
            </select>
          </div>
        </div>

        <div className="row" style={{marginTop:10}}>
          <div><label className="small">BMI</label><input className="input" value={form.bmi} onChange={e=>set("bmi",e.target.value)} /></div>
          <div><label className="small">Waist</label><input className="input" value={form.waist_circumference} onChange={e=>set("waist_circumference",e.target.value)} /></div>
        </div>

        <div className="row" style={{marginTop:10}}>
          <div><label className="small">Hip</label><input className="input" value={form.hip_circumference} onChange={e=>set("hip_circumference",e.target.value)} /></div>
          <div><label className="small">SBP</label><input className="input" value={form.systolic_bp} onChange={e=>set("systolic_bp",e.target.value)} /></div>
        </div>

        <div style={{marginTop:10}}>
          <label className="small">DBP</label>
          <input className="input" value={form.diastolic_bp} onChange={e=>set("diastolic_bp",e.target.value)} />
        </div>

        <div style={{marginTop:12}}>
          <label className="small">Optional retina image</label><br/>
          <input type="file" accept="image/*" onChange={e=>setFile(e.target.files?.[0]||null)} />
          <p className="small" style={{ marginTop:8 }}>
            Expected image quality: JPG or PNG, clear focus, no heavy blur/glare, evenly lit, minimum 512x512 pixels, recommended 1024x1024+, and file size up to 10MB.
          </p>
          <p className="small" style={{ marginTop:6 }}>
            Retina capture guidance: center retina structures in frame, avoid reflections, hold device steady, and retake if vessel detail is not clear.
          </p>
        </div>

        <div style={{marginTop:12}}>
          <button className="btn" onClick={run} disabled={busy}>{busy?"Running…":"Run Fusion Screening"}</button>
          {err && <p style={{color:"#ff8080"}}>{err}</p>}
        </div>

        <div className="row" style={{alignItems:"start", marginTop:12}}>
          <div className="card">
            <h3 style={{marginTop:0}}>Fusion Result</h3>
            {!result ? <p className="small">No result yet.</p> : (
              <>
                <p className="small">
                  Final: <b>{fusionLabelText(result.fusion?.final_label)}</b><br/>
                  p: <b>{result.fusion?.final_proba === null ? "N/A" : Number(result.fusion?.final_proba).toFixed(3)}</b><br/>
                  reason: {result.fusion?.reason}<br/>
                  threshold: {result.threshold_used}
                </p>
                <div className="card" style={{ marginTop: 10 }}>
                  <b>Interpretation</b>
                  <p className="small" style={{ marginTop: 8 }}>
                    Patient: {result.fusion?.final_label === "screen_positive_refer"
                      ? "Your combined screening suggests higher risk. Please proceed for clinical review and confirmatory testing."
                      : result.fusion?.final_label === "screen_negative"
                        ? "Your combined screening suggests lower current risk. Keep routine health follow-up."
                        : result.fusion?.final_label === "retake_image"
                          ? "Your retina image quality was not sufficient. Please retake the image and repeat screening."
                          : "Screening could not be completed because required input data was insufficient."}
                  </p>
                  <p className="small" style={{ marginTop: 6 }}>
                    Clinician: {result.fusion?.final_label === "screen_positive_refer"
                      ? "Fusion output crossed operating threshold; referral pathway is recommended."
                      : result.fusion?.final_label === "screen_negative"
                        ? "Fusion output below threshold. Review context and risk factors before excluding further workup."
                        : result.fusion?.final_label === "retake_image"
                          ? "Retina quality gate failed. Acquire improved fundus image before interpreting retina contribution."
                          : "Missing required modality data; rely on complete clinical dataset."}
                  </p>
                </div>
                <button className="btn secondary" onClick={downloadPdf} disabled={!predId}>Download PDF</button>
              </>
            )}
          </div>

          <div className="card">
            <h3 style={{marginTop:0}}>Retina Grad-CAM (if present)</h3>
            {!overlay ? <p className="small">No overlay.</p> : (
              <img src={overlay} alt="fusion retina overlay" style={{maxWidth:"100%", borderRadius:12}} />
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
