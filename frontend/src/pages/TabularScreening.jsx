import React, { useMemo, useState } from "react";
import { api } from "../lib/api";
import { getAuth } from "../lib/authStore";
import ConsentCard from "../components/ConsentCard.jsx";
import Locked from "./Locked.jsx";
import { isLockedError, lockedMessage } from "../lib/errors";
import { pushQueue, loadQueue, clearQueue } from "../lib/offlineQueue";
import { Link } from "react-router-dom";

export default function TabularScreening(){
  const auth = getAuth();
  const isPublic = auth?.role === "public";

  const [country, setCountry] = useState(import.meta.env.VITE_DEFAULT_COUNTRY || "NG");
  const [consent, setConsent] = useState({ ok: isPublic ? true : false });
  const [patientKey, setPatientKey] = useState("");
  const [form, setForm] = useState({
    age: "",
    sex: "",
    bmi: "",
    waist_circumference: "",
    hip_circumference: "",
    systolic_bp: "",
    diastolic_bp: "",
  });

  const [result, setResult] = useState(null);
  const [predictionId, setPredictionId] = useState(null);
  const [err, setErr] = useState("");
  const [locked, setLocked] = useState(null);
  const [busy, setBusy] = useState(false);

  const queuedCount = useMemo(()=>loadQueue().length, []);
  const labelText = (label) => {
    if (label === "t2d") return "Type 2 Diabetes";
    if (label === "not_diabetic") return "Not Diabetic";
    return label || "N/A";
  };

  function set(k,v){ setForm(prev=>({ ...prev, [k]: v })); }

  function validate(){
    // Minimal safety checks (backend still accepts missing features)
    if (!isPublic && !consent?.ok) return "Consent is required.";
    if (!isPublic && patientKey.trim().length === 0) return "Patient key is required for clinical tracking.";
    if (form.age && (Number(form.age) < 0 || Number(form.age) > 120)) return "Age must be 0–120";
    if (form.bmi && (Number(form.bmi) < 10 || Number(form.bmi) > 80)) return "BMI must be 10–80";
    if (form.systolic_bp && (Number(form.systolic_bp) < 70 || Number(form.systolic_bp) > 260)) return "SBP must be 70–260";
    if (form.diastolic_bp && (Number(form.diastolic_bp) < 40 || Number(form.diastolic_bp) > 160)) return "DBP must be 40–160";
    return null;
  }

  async function submit(){
    setErr(""); setResult(null); setPredictionId(null);

    const v = validate();
    if (v) { setErr(v); return; }

    const payload = {
      country_code: country,
      patient_key: patientKey.trim() || null,
      ...Object.fromEntries(Object.entries(form).map(([k,val]) => [k, val === "" ? null : val])),
      consent: isPublic ? null : consent,
      // never send PHI here
    };

    // Offline support
    if (!navigator.onLine) {
      pushQueue({ kind: "tabular_predict", payload });
      setErr("Offline: saved to queue. Sync when internet returns.");
      return;
    }

    setBusy(true);
    try{
      const res = await api.post("/api/predict/tabular", payload);
      setResult(res.data);
      setPredictionId(res.data.prediction_id);
    }catch(e){
      if (isLockedError(e)) setLocked(lockedMessage(e));
      else setErr(e?.response?.data?.detail || "Prediction failed");
    }finally{
      setBusy(false);
    }
  }

  async function downloadPdf(){
    if (!predictionId) return;
    setErr("");
    try {
      const res = await api.get(`/api/predict/tabular/report/${predictionId}`, {
        responseType: "blob",
      });
      const blob = new Blob([res.data], { type: "application/pdf" });
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `glucolens_tabular_report_${predictionId}.pdf`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      window.URL.revokeObjectURL(url);
    } catch (e) {
      if (isLockedError(e)) setLocked(lockedMessage(e));
      else setErr(e?.response?.data?.detail || "Failed to download report");
    }
  }

  async function syncQueue(){
    setErr("");
    if (!navigator.onLine) { setErr("Still offline."); return; }
    const q = loadQueue();
    if (!q.length) { setErr("No queued items."); return; }

    setBusy(true);
    try{
      let okCount = 0;
      for (const item of q) {
        if (item.kind !== "tabular_predict") continue;
        await api.post("/api/predict/tabular", item.payload);
        okCount += 1;
      }
      clearQueue();
      setErr(`✅ Synced ${okCount} queued screenings.`);
    } catch(e){
      setErr(e?.response?.data?.detail || "Sync failed (partial).");
    } finally {
      setBusy(false);
    }
  }

  if (locked) return <Locked message={locked} />;

  return (
    <div className="container">
      <div className="card">
        <div style={{display:"flex", justifyContent:"space-between", gap:10, flexWrap:"wrap"}}>
          <div>
            <h2 style={{margin:0}}>{isPublic ? "Public Quick Check" : "Tabular Screening (Clinic)"}</h2>
            <p className="small" style={{marginTop:8}}>
              Calibrated probabilities + SHAP. Screening support only — confirm with lab testing.
              {!isPublic && " Include a patient key to enable outcome linkage."}
            </p>
          </div>
          <div style={{display:"flex", gap:10, alignItems:"start", flexWrap:"wrap"}}>
            <button className="btn secondary" onClick={syncQueue} disabled={busy}>
              Sync queued ({loadQueue().length})
            </button>
          </div>
        </div>

        <div className="row" style={{ alignItems:"start" }}>
          <div className="card">
            <h3 style={{marginTop:0}}>Inputs</h3>

            <label className="small">Country</label>
            <input className="input" value={country} onChange={e=>setCountry(e.target.value.toUpperCase())} />

            <div style={{height:10}} />
            {!isPublic && (
              <>
                <label className="small">Patient key</label>
                <input className="input" value={patientKey} onChange={e=>setPatientKey(e.target.value)} placeholder="PAT_001_ABC" />
                <div style={{height:10}} />
              </>
            )}

            <div className="row">
              <div>
                <label className="small">Age</label>
                <input className="input" value={form.age} onChange={e=>set("age", e.target.value)} placeholder="45" />
              </div>
              <div>
                <label className="small">Sex</label>
                <select className="input" value={form.sex} onChange={e=>set("sex", e.target.value)}>
                  <option value="">Unknown</option>
                  <option value="M">Male</option>
                  <option value="F">Female</option>
                </select>
              </div>
            </div>

            <div style={{height:10}} />

            <div className="row">
              <div>
                <label className="small">BMI</label>
                <input className="input" value={form.bmi} onChange={e=>set("bmi", e.target.value)} placeholder="31.2" />
              </div>
              <div>
                <label className="small">Waist circumference</label>
                <input className="input" value={form.waist_circumference} onChange={e=>set("waist_circumference", e.target.value)} placeholder="98" />
              </div>
            </div>

            <div style={{height:10}} />

            <div className="row">
              <div>
                <label className="small">Hip circumference</label>
                <input className="input" value={form.hip_circumference} onChange={e=>set("hip_circumference", e.target.value)} placeholder="105" />
              </div>
              <div>
                <label className="small">Systolic BP</label>
                <input className="input" value={form.systolic_bp} onChange={e=>set("systolic_bp", e.target.value)} placeholder="145" />
              </div>
            </div>

            <div style={{height:10}} />

            <label className="small">Diastolic BP</label>
            <input className="input" value={form.diastolic_bp} onChange={e=>set("diastolic_bp", e.target.value)} placeholder="90" />

            <div style={{height:12}} />

            {!isPublic && (
              <ConsentCard
                country={country}
                lang={(import.meta.env.VITE_DEFAULT_LANG || "en")}
                onChange={setConsent}
              />
            )}

            <div style={{height:12}} />
            <button className="btn" onClick={submit} disabled={busy}>
              {busy ? "Running…" : "Run screening"}
            </button>

            {err && <p style={{ color:"#ff8080" }}>{err}</p>}
          </div>

          <div className="card">
            <h3 style={{marginTop:0}}>Result</h3>
            {!result ? (
              <p className="small">No result yet.</p>
            ) : (
              <>
                <p className="small">
                  Predicted: <b>{labelText(result.predicted_label)}</b>
                </p>
                <p className="small">
                  P(not diabetic): <b>{result.probabilities?.not_diabetic?.toFixed?.(3) ?? result.probabilities?.not_diabetic}</b>
                  <br/>
                  P(Type 2 Diabetes): <b>{result.probabilities?.t2d?.toFixed?.(3) ?? result.probabilities?.t2d}</b>
                </p>

                <div className="card" style={{ marginTop: 10 }}>
                  <b>Interpretation</b>
                  <p className="small" style={{ marginTop: 8 }}>
                    Patient: {result.predicted_label === "t2d"
                      ? "Your screening result suggests elevated risk for Type 2 Diabetes. Please book confirmatory laboratory testing with a clinician."
                      : "Your screening result suggests lower immediate risk for Type 2 Diabetes. Continue healthy lifestyle and routine follow-up."}
                  </p>
                  <p className="small" style={{ marginTop: 6 }}>
                    Clinician: {result.predicted_label === "t2d"
                      ? "Screen-positive case. Use probability and top SHAP drivers for counseling and order confirmatory diagnostics (for example, fasting plasma glucose, HbA1c, or OGTT)."
                      : "Screen-negative case. Consider age, symptoms, and comorbid risk factors before deferring confirmatory testing."}
                  </p>
                </div>

                <div className="card" style={{ marginTop: 10 }}>
                  <b>Top SHAP features</b>
                  <div className="small" style={{ marginTop: 8 }}>
                    {(result.explainability?.top_features || []).slice(0,10).map((t, i)=>(
                      <div key={i} style={{ marginBottom: 6 }}>
                        • {t.feature}: shap={Number(t.shap_value).toFixed(4)}    | value={String(t.value)}
                      </div>
                    ))}
                  </div>
                </div>

                <div style={{ display:"flex", gap:10, marginTop: 12, flexWrap:"wrap" }}>
                  <button className="btn secondary" onClick={downloadPdf} disabled={!predictionId}>
                    Download Tabular Screening Report - PDF
                  </button>
                  {!isPublic && patientKey.trim() && (
                    <Link className="btn secondary" to={`/outcomes/new?patient_key=${encodeURIComponent(patientKey.trim())}`}>
                      Record outcome
                    </Link>
                  )}
                </div>

                {predictionId && (
                  <p className="small" style={{ marginTop: 10 }}>
                    prediction_id: {predictionId}
                  </p>
                )}
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
