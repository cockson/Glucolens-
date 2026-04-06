import React, { useState } from "react";
import { api, SCREENING_TIMEOUT_MS } from "../lib/api";
import { getAuth } from "../lib/authStore";
import ConsentCard from "../components/ConsentCard.jsx";
import Locked from "./Locked.jsx";
import { isLockedError, lockedMessage } from "../lib/errors";
import { pushQueue, loadQueue, clearQueue } from "../lib/offlineQueue";
import { Link } from "react-router-dom";

const COUNTRY_RE = /^[A-Z]{2}$/;
const PATIENT_KEY_RE = /^[A-Za-z0-9_-]{3,64}$/;

function screeningRequestError(err, fallback) {
  if (err?.code === "ECONNABORTED") {
    return "Prediction timed out. The server may be waking up or overloaded.";
  }
  if (!err?.response) {
    return "Prediction service is temporarily unavailable. Please retry in a moment.";
  }
  return err?.response?.data?.detail || fallback;
}

function formatProbability(value) {
  const n = Number(value);
  return Number.isFinite(n) ? n.toFixed(3) : "N/A";
}

export default function TabularScreening() {
  const auth = getAuth();
  const isPublic = auth?.role === "public";

  const [country, setCountry] = useState(import.meta.env.VITE_DEFAULT_COUNTRY || "NG");
  const [consent, setConsent] = useState({ ok: isPublic ? true : false });
  const [patientKey, setPatientKey] = useState("");
  const [form, setForm] = useState({
    age: "",
    sex: "",
    bmi: "",
    bmi_category: "",
    waist_circumference: "",
    systolic_bp: "",
    diastolic_bp: "",
    fasting_glucose_mgdl: "",
    hba1c_pct: "",
    family_history_diabetes: "",
    physical_activity: "",
    smoking_status: "",
  });

  const [result, setResult] = useState(null);
  const [predictionId, setPredictionId] = useState(null);
  const [err, setErr] = useState("");
  const [locked, setLocked] = useState(null);
  const [busy, setBusy] = useState(false);
  const tabularPredictPath = isPublic ? "/api/predict/tabular/public" : "/api/predict/tabular";

  const labelText = (label) => {
    if (label === "diabetic" || label === "t2d") return "Diabetic";
    if (label === "prediabetic") return "Prediabetic";
    if (label === "non_diabetic" || label === "not_diabetic") return "Non-diabetic";
    return label || "N/A";
  };

  function set(k, v) {
    setForm((prev) => ({ ...prev, [k]: v }));
  }

  function validate() {
    if (!isPublic && !consent?.ok) return "Consent is required.";
    if (!isPublic && patientKey.trim().length === 0) return "Patient key is required for clinical tracking.";
    if (!COUNTRY_RE.test(country.trim().toUpperCase())) return "Country must be a 2-letter code (for example, NG).";
    if (!isPublic && !PATIENT_KEY_RE.test(patientKey.trim())) return "Patient key must be 3-64 chars (letters, numbers, underscore, hyphen).";

    if (form.age && (Number(form.age) < 0 || Number(form.age) > 120)) return "Age must be 0-120";
    if (form.bmi && (Number(form.bmi) < 10 || Number(form.bmi) > 80)) return "BMI must be 10-80";
    if (form.waist_circumference && (Number(form.waist_circumference) < 40 || Number(form.waist_circumference) > 220)) return "Waist circumference must be 40-220 cm";
    if (form.systolic_bp && (Number(form.systolic_bp) < 70 || Number(form.systolic_bp) > 260)) return "SBP must be 70-260";
    if (form.diastolic_bp && (Number(form.diastolic_bp) < 40 || Number(form.diastolic_bp) > 160)) return "DBP must be 40-160";
    if (form.fasting_glucose_mgdl && (Number(form.fasting_glucose_mgdl) < 40 || Number(form.fasting_glucose_mgdl) > 500)) return "Fasting glucose must be 40-500 mg/dL";
    if (form.hba1c_pct && (Number(form.hba1c_pct) < 3 || Number(form.hba1c_pct) > 20)) return "HbA1c must be 3-20%";
    return null;
  }

  async function submit() {
    setErr("");
    setResult(null);
    setPredictionId(null);

    const v = validate();
    if (v) {
      setErr(v);
      return;
    }

    const payload = {
      country_code: country,
      patient_key: patientKey.trim() || null,
      ...Object.fromEntries(Object.entries(form).map(([k, val]) => [k, val === "" ? null : val])),
      consent: isPublic ? null : consent,
    };

    if (!navigator.onLine) {
      pushQueue({ kind: "tabular_predict", payload });
      setErr("Offline: saved to queue. Sync when internet returns.");
      return;
    }

    setBusy(true);
    try {
      const res = await api.post(tabularPredictPath, payload, { timeout: SCREENING_TIMEOUT_MS });
      setResult(res.data);
      setPredictionId(res.data.prediction_id);
    } catch (e) {
      if (isLockedError(e)) setLocked(lockedMessage(e));
      else setErr(screeningRequestError(e, "Prediction failed"));
    } finally {
      setBusy(false);
    }
  }

  async function downloadPdf() {
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

  async function syncQueue() {
    setErr("");
    if (!navigator.onLine) {
      setErr("Still offline.");
      return;
    }
    const q = loadQueue();
    if (!q.length) {
      setErr("No queued items.");
      return;
    }

    setBusy(true);
    try {
      let okCount = 0;
      for (const item of q) {
        if (item.kind !== "tabular_predict") continue;
        await api.post(tabularPredictPath, item.payload, { timeout: SCREENING_TIMEOUT_MS });
        okCount += 1;
      }
      clearQueue();
      setErr(`Synced ${okCount} queued screenings.`);
    } catch (e) {
      setErr(screeningRequestError(e, "Sync failed (partial)."));
    } finally {
      setBusy(false);
    }
  }

  if (locked) return <Locked message={locked} />;

  return (
    <div className="container">
      <div className="card">
        <div style={{ display: "flex", justifyContent: "space-between", gap: 10, flexWrap: "wrap" }}>
          <div>
            <h2 style={{ margin: 0 }}>{isPublic ? "Public Quick Check" : "Tabular Screening (Clinic)"}</h2>
            <p className="small" style={{ marginTop: 8 }}>
              Calibrated probabilities + SHAP. Screening support only - confirm with lab testing.
              {!isPublic && " Include a patient key to enable outcome linkage."}
            </p>
          </div>
          <div style={{ display: "flex", gap: 10, alignItems: "start", flexWrap: "wrap" }}>
            <button className="btn secondary" onClick={syncQueue} disabled={busy}>
              Sync queued ({loadQueue().length})
            </button>
          </div>
        </div>

        <div className="row" style={{ alignItems: "start" }}>
          <div className="card">
            <h3 style={{ marginTop: 0 }}>Inputs</h3>

            <label className="small">Country</label>
            <input className="input" value={country} maxLength={2} onChange={(e) => setCountry(e.target.value.toUpperCase())} placeholder="NG" />
            <div className="small">Expected format: 2-letter ISO code</div>

            <div style={{ height: 10 }} />
            {!isPublic && (
              <>
                <label className="small">Patient key</label>
                <input className="input" value={patientKey} maxLength={64} onChange={(e) => setPatientKey(e.target.value)} placeholder="PAT_001_ABC" />
                <div className="small">Expected format: 3-64 chars (A-Z, 0-9, _, -)</div>
                <div style={{ height: 10 }} />
              </>
            )}

            <div className="row">
              <div>
                <label className="small">Age</label>
                <input className="input" type="number" min="0" max="120" step="1" inputMode="numeric" value={form.age} onChange={(e) => set("age", e.target.value)} placeholder="45 (0-120)" />
              </div>
              <div>
                <label className="small">Sex</label>
                <select className="input" value={form.sex} onChange={(e) => set("sex", e.target.value)}>
                  <option value="">Unknown</option>
                  <option value="M">Male</option>
                  <option value="F">Female</option>
                </select>
              </div>
            </div>

            <div style={{ height: 10 }} />

            <div className="row">
              <div>
                <label className="small">BMI</label>
                <input className="input" type="number" min="10" max="80" step="0.1" inputMode="decimal" value={form.bmi} onChange={(e) => set("bmi", e.target.value)} placeholder="31.2 (10-80)" />
              </div>
              <div>
                <label className="small">BMI category</label>
                <select className="input" value={form.bmi_category} onChange={(e) => set("bmi_category", e.target.value)}>
                  <option value="">Unknown</option>
                  <option value="underweight">Underweight</option>
                  <option value="normal">Normal</option>
                  <option value="overweight">Overweight</option>
                  <option value="obese">Obese</option>
                </select>
              </div>
            </div>

            <div style={{ height: 10 }} />

            <div className="row">
              <div>
                <label className="small">Waist circumference</label>
                <input className="input" type="number" min="40" max="220" step="0.1" inputMode="decimal" value={form.waist_circumference} onChange={(e) => set("waist_circumference", e.target.value)} placeholder="98 (40-220)" />
              </div>
              <div>
                <label className="small">Family history of diabetes</label>
                <select className="input" value={form.family_history_diabetes} onChange={(e) => set("family_history_diabetes", e.target.value)}>
                  <option value="">Unknown</option>
                  <option value="1">Yes</option>
                  <option value="0">No</option>
                </select>
              </div>
            </div>

            <div style={{ height: 10 }} />

            <div className="row">
              <div>
                <label className="small">Systolic BP</label>
                <input className="input" type="number" min="70" max="260" step="1" inputMode="numeric" value={form.systolic_bp} onChange={(e) => set("systolic_bp", e.target.value)} placeholder="145 (70-260)" />
              </div>
              <div>
                <label className="small">Diastolic BP</label>
                <input className="input" type="number" min="40" max="160" step="1" inputMode="numeric" value={form.diastolic_bp} onChange={(e) => set("diastolic_bp", e.target.value)} placeholder="90 (40-160)" />
              </div>
            </div>

            <div style={{ height: 10 }} />

            <div className="row">
              <div>
                <label className="small">Fasting glucose (mg/dL)</label>
                <input className="input" type="number" min="40" max="500" step="0.1" inputMode="decimal" value={form.fasting_glucose_mgdl} onChange={(e) => set("fasting_glucose_mgdl", e.target.value)} placeholder="110 (40-500)" />
              </div>
              <div>
                <label className="small">HbA1c (%)</label>
                <input className="input" type="number" min="3" max="20" step="0.1" inputMode="decimal" value={form.hba1c_pct} onChange={(e) => set("hba1c_pct", e.target.value)} placeholder="6.2 (3-20)" />
              </div>
            </div>

            <div style={{ height: 10 }} />

            <div className="row">
              <div>
                <label className="small">Physical activity</label>
                <select className="input" value={form.physical_activity} onChange={(e) => set("physical_activity", e.target.value)}>
                  <option value="">Unknown</option>
                  <option value="inactive">Inactive</option>
                  <option value="moderate">Moderate</option>
                  <option value="active">Active</option>
                </select>
              </div>
              <div>
                <label className="small">Smoking status</label>
                <select className="input" value={form.smoking_status} onChange={(e) => set("smoking_status", e.target.value)}>
                  <option value="">Unknown</option>
                  <option value="never">Never</option>
                  <option value="former">Former</option>
                  <option value="current">Current</option>
                </select>
              </div>
            </div>

            <div style={{ height: 12 }} />

            {!isPublic && <ConsentCard country={country} lang={import.meta.env.VITE_DEFAULT_LANG || "en"} onChange={setConsent} />}

            <div style={{ height: 12 }} />
            <button className="btn" onClick={submit} disabled={busy}>
              {busy ? "Running..." : "Run screening"}
            </button>

            {err && <p style={{ color: "#ff8080" }}>{err}</p>}
          </div>

          <div className="card">
            <h3 style={{ marginTop: 0 }}>Result</h3>
            {!result ? (
              <p className="small">No result yet.</p>
            ) : (
              <>
                <p className="small">
                  Predicted: <b>{labelText(result.predicted_label)}</b>
                </p>
                <p className="small">
                  P(non-diabetic): <b>{formatProbability(result.probabilities?.non_diabetic ?? result.probabilities?.not_diabetic)}</b>
                  <br />
                  P(prediabetic): <b>{formatProbability(result.probabilities?.prediabetic)}</b>
                  <br />
                  P(diabetic): <b>{formatProbability(result.probabilities?.diabetic ?? result.probabilities?.t2d)}</b>
                </p>

                <div className="card" style={{ marginTop: 10 }}>
                  <b>Interpretation</b>
                  <p className="small" style={{ marginTop: 8 }}>
                    Patient: {(result.predicted_label === "diabetic" || result.predicted_label === "t2d")
                      ? "Your screening result suggests high diabetes risk. Please book confirmatory laboratory testing with a clinician."
                      : (result.predicted_label === "prediabetic"
                        ? "Your screening result suggests prediabetes risk. Please discuss early intervention and confirmatory testing with a clinician."
                        : "Your screening result suggests lower immediate diabetes risk. Continue healthy lifestyle and routine follow-up.")}
                  </p>
                  <p className="small" style={{ marginTop: 6 }}>
                    Clinician: {(result.predicted_label === "diabetic" || result.predicted_label === "t2d")
                      ? "High-risk case. Use top SHAP drivers for counseling and order confirmatory diagnostics (fasting plasma glucose, HbA1c, or OGTT)."
                      : (result.predicted_label === "prediabetic"
                        ? "Intermediate-risk case. Prioritize lifestyle intervention and near-term confirmatory testing."
                        : "Lower-risk case. Consider age, symptoms, and comorbid factors before deferring confirmatory testing.")}
                  </p>
                </div>

                <div className="card" style={{ marginTop: 10 }}>
                  <b>Top SHAP features</b>
                  <div className="small" style={{ marginTop: 8 }}>
                    {(result.explainability?.top_features || []).slice(0, 10).map((t, i) => (
                      <div key={i} style={{ marginBottom: 6 }}>
                        - {t.feature}: shap={Number(t.shap_value).toFixed(4)} | value={String(t.value)}
                      </div>
                    ))}
                  </div>
                </div>

                <div style={{ display: "flex", gap: 10, marginTop: 12, flexWrap: "wrap" }}>
                  <button className="btn secondary" onClick={downloadPdf} disabled={!predictionId}>
                    Download Tabular Screening Report - PDF
                  </button>
                  {!isPublic && patientKey.trim() && (
                    <Link className="btn secondary" to={`/outcomes/new?patient_key=${encodeURIComponent(patientKey.trim())}`}>
                      Record outcome
                    </Link>
                  )}
                </div>

                {predictionId && <p className="small" style={{ marginTop: 10 }}>prediction_id: {predictionId}</p>}
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
