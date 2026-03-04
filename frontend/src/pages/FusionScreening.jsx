import React, { useEffect, useState } from "react";
import { api, SCREENING_TIMEOUT_MS } from "../lib/api";
import { getAuth } from "../lib/authStore";
import Locked from "./Locked.jsx";
import { isLockedError, lockedMessage } from "../lib/errors";
import { Link } from "react-router-dom";

const COUNTRY_RE = /^[A-Z]{2}$/;
const PATIENT_KEY_RE = /^[A-Za-z0-9_-]{3,64}$/;
const MAX_IMAGE_BYTES = 10 * 1024 * 1024;

export default function FusionScreening(){
  const DEFAULT_GENO_FEATURES = [
    "TCF7L2_rs7903146",
    "KCNQ1_rs2237892",
    "MTNR1B_rs10830963",
    "SLC30A8_rs13266634",
    "PPARG_rs1801282",
    "Age",
    "BMI",
    "HbA1c",
  ];

  const auth = getAuth();
  const isPublic = auth?.role === "public";

  const [retinaFile, setRetinaFile] = useState(null);
  const [skinFile, setSkinFile] = useState(null);
  const [genomicsFile, setGenomicsFile] = useState(null);
  const [genomicsFeatures, setGenomicsFeatures] = useState(DEFAULT_GENO_FEATURES);
  const [genomicsForm, setGenomicsForm] = useState(
    Object.fromEntries(DEFAULT_GENO_FEATURES.map((k) => [k, ""]))
  );

  const [country, setCountry] = useState("NG");
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
  const [predId, setPredId] = useState(null);
  const [err, setErr] = useState("");
  const [fieldErrors, setFieldErrors] = useState({});
  const [busy, setBusy] = useState(false);
  const [locked, setLocked] = useState(null);

  const fusionLabelText = (label) => {
    if (label === "screen_positive_refer") return "Screen Positive (Refer)";
    if (label === "screen_negative") return "Screen Negative";
    if (label === "retake_image") return "Retake Image Needed";
    if (label === "insufficient_data") return "Insufficient Data";
    return label || "N/A";
  };

  function genomicsSpec(feature){
    const f = String(feature || "").toLowerCase();
    if (f.includes("rs")) {
      return { min: 0, max: 2, step: 1, hint: "Expected range: 0-2 (genotype code)" };
    }
    if (f === "age") {
      return { min: 0, max: 120, step: 1, hint: "Expected range: 0-120 years" };
    }
    if (f === "bmi") {
      return { min: 10, max: 80, step: 0.1, hint: "Expected range: 10-80 kg/m2" };
    }
    if (f === "hba1c" || f.includes("hba1c")) {
      return { min: 3, max: 20, step: 0.1, hint: "Expected range: 3-20 %" };
    }
    return { min: undefined, max: undefined, step: 0.01, hint: "Expected range: numeric value" };
  }

  function clearFieldError(key){
    setFieldErrors((prev) => {
      if (!prev[key]) return prev;
      const next = { ...prev };
      delete next[key];
      return next;
    });
  }
  function set(k, v){
    setForm((p) => ({ ...p, [k]: v }));
    clearFieldError(k);
  }
  function setGeno(k, v){
    setGenomicsForm((p) => ({ ...p, [k]: v }));
    clearFieldError(`genomics.${k}`);
  }
  function checkRange(name, value, min, max){
    if (value === "" || value === null || value === undefined) return null;
    const n = Number(value);
    if (!Number.isFinite(n) || n < min || n > max) return `${name} must be between ${min} and ${max}.`;
    return null;
  }
  function extractErrorMessage(e){
    const detail = e?.response?.data?.detail;
    if (typeof detail === "string" && detail.trim()) return detail;
    if (Array.isArray(detail)) {
      return detail.map((d) => {
        if (typeof d === "string") return d;
        const loc = Array.isArray(d?.loc) ? d.loc.join(".") : "";
        const msg = d?.msg || JSON.stringify(d);
        return loc ? `${loc}: ${msg}` : msg;
      }).join(" | ");
    }
    if (detail && typeof detail === "object") return JSON.stringify(detail);
    if (typeof e?.response?.data === "string" && e.response.data.trim()) return e.response.data;
    if (e?.message) return e.message;
    return "Fusion prediction failed";
  }

  useEffect(() => {
    let alive = true;
    if (!auth?.access_token) return () => { alive = false; };
    api.get("/api/genomics/model-card")
      .then((r) => {
        if (!alive) return;
        const feats = Array.isArray(r?.data?.features) && r.data.features.length
          ? r.data.features
          : DEFAULT_GENO_FEATURES;
        setGenomicsFeatures(feats);
        setGenomicsForm((prev) => {
          const next = {};
          feats.forEach((f) => { next[f] = prev[f] ?? ""; });
          return next;
        });
      })
      .catch(() => {});
    return () => { alive = false; };
  }, [auth?.access_token]);

  function parseGenomicsCsv(text){
    const lines = text.split(/\r?\n/).map((l) => l.trim()).filter(Boolean);
    if (lines.length < 2) throw new Error("CSV must include header and one data row.");
    const headers = lines[0].split(",").map((h) => h.trim());
    const values = lines[1].split(",").map((v) => v.trim());
    const row = {};
    headers.forEach((h, idx) => {
      if (!h) return;
      const raw = values[idx] ?? "";
      if (raw === "") return;
      const n = Number(raw);
      row[h] = Number.isNaN(n) ? raw : n;
    });
    return row;
  }

  async function run(){
    setErr("");
    setFieldErrors({});
    setBusy(true);

    const nextErrors = {};

    if (!isPublic && patientKey.trim().length === 0) nextErrors.patientKey = "Patient key is required for clinical tracking.";
    if (!COUNTRY_RE.test(country.trim().toUpperCase())) {
      nextErrors.country = "Country must be a 2-letter code (for example, NG).";
    }
    if (!isPublic && !PATIENT_KEY_RE.test(patientKey.trim())) {
      nextErrors.patientKey = "Patient key must be 3-64 chars (letters, numbers, underscore, hyphen).";
    }
    const tabularChecks = [
      ["age", checkRange("Age", form.age, 0, 120)],
      ["bmi", checkRange("BMI", form.bmi, 10, 80)],
      ["waist_circumference", checkRange("Waist circumference", form.waist_circumference, 40, 220)],
      ["systolic_bp", checkRange("Systolic BP", form.systolic_bp, 70, 260)],
      ["diastolic_bp", checkRange("Diastolic BP", form.diastolic_bp, 40, 160)],
      ["fasting_glucose_mgdl", checkRange("Fasting glucose", form.fasting_glucose_mgdl, 40, 500)],
      ["hba1c_pct", checkRange("HbA1c", form.hba1c_pct, 3, 20)],
    ];
    tabularChecks.forEach(([k, msg]) => {
      if (msg) nextErrors[k] = msg;
    });
    if (retinaFile) {
      if (!String(retinaFile.type || "").startsWith("image/")) nextErrors.retina = "Retina file must be an image.";
      if (retinaFile.size > MAX_IMAGE_BYTES) nextErrors.retina = "Retina image is too large (max 10MB).";
    }
    if (skinFile) {
      if (!String(skinFile.type || "").startsWith("image/")) nextErrors.skin = "Skin file must be an image.";
      if (skinFile.size > MAX_IMAGE_BYTES) nextErrors.skin = "Skin image is too large (max 10MB).";
    }
    if (genomicsFile && !String(genomicsFile.name || "").toLowerCase().endsWith(".csv")) {
      nextErrors.genomicsFile = "Genomics upload must be a .csv file.";
    }
    if (Object.keys(nextErrors).length) {
      setFieldErrors(nextErrors);
      setBusy(false);
      return;
    }

    try {
      let genomics = {};
      if (genomicsFile) {
        try {
          const csvObj = parseGenomicsCsv(await genomicsFile.text());
          genomics = { ...genomics, ...csvObj };
        } catch (e) {
          setFieldErrors({ genomicsFile: e?.message || "Invalid genomics CSV." });
          setBusy(false);
          return;
        }
      }

      const genomicsErrors = {};
      genomicsFeatures.forEach((k) => {
        const raw = (genomicsForm[k] ?? "").toString().trim();
        if (!raw) return;
        const n = Number(raw);
        const spec = genomicsSpec(k);
        if (Number.isFinite(n) && spec.min !== undefined && n < spec.min) genomicsErrors[`genomics.${k}`] = `${k} must be >= ${spec.min}.`;
        if (Number.isFinite(n) && spec.max !== undefined && n > spec.max) genomicsErrors[`genomics.${k}`] = `${k} must be <= ${spec.max}.`;
        genomics[k] = Number.isNaN(n) ? raw : n;
      });
      if (Object.keys(genomicsErrors).length) {
        setFieldErrors(genomicsErrors);
        setBusy(false);
        return;
      }
      if (!Object.keys(genomics).length) genomics = null;

      const payloadObj = {
        country_code: country,
        patient_key: patientKey.trim() || null,
        ...Object.fromEntries(Object.entries(form).map(([k, v]) => [k, v === "" ? null : v])),
        genomics,
      };

      const fd = new FormData();
      fd.append("payload", JSON.stringify(payloadObj));
      if (retinaFile) fd.append("retina", retinaFile);
      if (skinFile) fd.append("skin", skinFile);

      const r = await api.post("/api/fusion/predict", fd, { timeout: SCREENING_TIMEOUT_MS });
      setResult(r.data);
      setPredId(r.data.prediction_id);
    } catch (e) {
      if (isLockedError(e)) setLocked(lockedMessage(e));
      else setErr(extractErrorMessage(e));
    } finally {
      setBusy(false);
    }
  }

  async function downloadPdf(){
    if (!predId) return;
    setErr("");
    try {
      const res = await api.get(`/api/fusion/report/${predId}`, {
        responseType: "blob",
      });
      const blob = new Blob([res.data], { type: "application/pdf" });
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `glucolens_fusion_report_${predId}.pdf`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      window.URL.revokeObjectURL(url);
    } catch (e) {
      if (isLockedError(e)) setLocked(lockedMessage(e));
      else setErr(extractErrorMessage(e) || "Failed to download report");
    }
  }

  if (locked) return <Locked message={locked} />;

  const retinaOverlay = result?.retina?.explainability?.overlay_png_base64
    ? `data:image/png;base64,${result.retina.explainability.overlay_png_base64}` : null;

  const skinOverlay = result?.skin?.explainability?.overlay_png_base64
    ? `data:image/png;base64,${result.skin.explainability.overlay_png_base64}` : null;

  return (
    <div className="container">
      <div className="card">
        <h2>Fusion Screening</h2>
        <p className="small">Complete tabular data and optionally add retina, skin, and genomics inputs for multimodal screening.</p>
        {isPublic && (
          <div style={{ marginTop: 10, display: "flex", gap: 10, flexWrap: "wrap", alignItems: "center" }}>
            <span className="small">Public access includes Fusion screening. Upgrade for full clinician workspace.</span>
            <Link className="btn secondary" to="/register-business">Upgrade</Link>
          </div>
        )}
      </div>

      <div style={{ height: 16 }} />

      <div className="row" style={{ alignItems: "start", marginTop: 0 }}>
        <div className="card">
          <h3 style={{ marginTop:0 }}>Tabular Mode</h3>
          <label className="small">Country</label>
          <input className={`input ${fieldErrors.country ? "input-error" : ""}`} value={country} maxLength={2} onChange={e=>{ setCountry(e.target.value.toUpperCase()); clearFieldError("country"); }} placeholder="2-letter country code (e.g., NG)" />
          {fieldErrors.country && <div className="field-error">{fieldErrors.country}</div>}

          {!isPublic && (
            <>
              <label className="small">Patient key</label>
              <input className={`input ${fieldErrors.patientKey ? "input-error" : ""}`} value={patientKey} maxLength={64} onChange={e=>{ setPatientKey(e.target.value); clearFieldError("patientKey"); }} placeholder="3-64 chars (letters, numbers, underscore, hyphen)" />
              {fieldErrors.patientKey && <div className="field-error">{fieldErrors.patientKey}</div>}
              <div style={{height:10}} />
            </>
          )}

          <div className="row" style={{marginTop:10}}>
            <div>
              <label className="small">Age</label>
              <input className={`input ${fieldErrors.age ? "input-error" : ""}`} type="number" min="0" max="120" step="1" inputMode="numeric" value={form.age} onChange={e=>set("age",e.target.value)} placeholder="Age in years (0-120)" />
              {fieldErrors.age && <div className="field-error">{fieldErrors.age}</div>}
            </div>
            <div>
              <label className="small">Sex</label>
              <select className="input" value={form.sex} onChange={e=>set("sex",e.target.value)}>
                <option value="">Unknown</option><option value="M">Male</option><option value="F">Female</option>
              </select>
            </div>
          </div>

          <div className="row" style={{marginTop:10}}>
            <div>
              <label className="small">BMI</label>
              <input className={`input ${fieldErrors.bmi ? "input-error" : ""}`} type="number" min="10" max="80" step="0.1" inputMode="decimal" value={form.bmi} onChange={e=>set("bmi",e.target.value)} placeholder="BMI in kg/m2 (10-80)" />
              {fieldErrors.bmi && <div className="field-error">{fieldErrors.bmi}</div>}
            </div>
            <div>
              <label className="small">BMI category</label>
              <select className="input" value={form.bmi_category} onChange={e=>set("bmi_category",e.target.value)}>
                <option value="">Unknown</option>
                <option value="underweight">Underweight</option>
                <option value="normal">Normal</option>
                <option value="overweight">Overweight</option>
                <option value="obese">Obese</option>
              </select>
            </div>
          </div>

          <div className="row" style={{marginTop:10}}>
            <div>
              <label className="small">Waist Circumference (cm)</label>
              <input className={`input ${fieldErrors.waist_circumference ? "input-error" : ""}`} type="number" min="40" max="220" step="0.1" inputMode="decimal" value={form.waist_circumference} onChange={e=>set("waist_circumference",e.target.value)} placeholder="40 - 220" />
              {fieldErrors.waist_circumference && <div className="field-error">{fieldErrors.waist_circumference}</div>}
            </div>
            <div>
              <label className="small">Family history of diabetes</label>
              <select className="input" value={form.family_history_diabetes} onChange={e=>set("family_history_diabetes",e.target.value)}>
                <option value="">Unknown</option>
                <option value="1">Yes</option>
                <option value="0">No</option>
              </select>
            </div>
          </div>

          <div className="row" style={{marginTop:10}}>
            <div>
              <label className="small">Systolic BP in mmHg</label>
              <input className={`input ${fieldErrors.systolic_bp ? "input-error" : ""}`} type="number" min="70" max="260" step="1" inputMode="numeric" value={form.systolic_bp} onChange={e=>set("systolic_bp",e.target.value)} placeholder=" 70 - 260" />
              {fieldErrors.systolic_bp && <div className="field-error">{fieldErrors.systolic_bp}</div>}
            </div>
            <div>
              <label className="small">Diastolic BP in mmHg</label>
              <input className={`input ${fieldErrors.diastolic_bp ? "input-error" : ""}`} type="number" min="40" max="160" step="1" inputMode="numeric" value={form.diastolic_bp} onChange={e=>set("diastolic_bp",e.target.value)} placeholder="40 - 160" />
              {fieldErrors.diastolic_bp && <div className="field-error">{fieldErrors.diastolic_bp}</div>}
            </div>
          </div>

          <div className="row" style={{marginTop:10}}>
            <div>
              <label className="small">Fasting glucose (mg/dL)</label>
              <input className={`input ${fieldErrors.fasting_glucose_mgdl ? "input-error" : ""}`} type="number" min="40" max="500" step="0.1" inputMode="decimal" value={form.fasting_glucose_mgdl} onChange={e=>set("fasting_glucose_mgdl",e.target.value)} placeholder=" 40 - 500" />
              {fieldErrors.fasting_glucose_mgdl && <div className="field-error">{fieldErrors.fasting_glucose_mgdl}</div>}
            </div>
            <div>
              <label className="small">HbA1c (%)</label>
              <input className={`input ${fieldErrors.hba1c_pct ? "input-error" : ""}`} type="number" min="3" max="20" step="0.1" inputMode="decimal" value={form.hba1c_pct} onChange={e=>set("hba1c_pct",e.target.value)} placeholder="3 - 20" />
              {fieldErrors.hba1c_pct && <div className="field-error">{fieldErrors.hba1c_pct}</div>}
            </div>
          </div>

          <div className="row" style={{marginTop:10}}>
            <div>
              <label className="small">Physical activity</label>
              <select className="input" value={form.physical_activity} onChange={e=>set("physical_activity",e.target.value)}>
                <option value="">Unknown</option>
                <option value="inactive">Inactive</option>
                <option value="moderate">Moderate</option>
                <option value="active">Active</option>
              </select>
            </div>
            <div>
              <label className="small">Smoking status</label>
              <select className="input" value={form.smoking_status} onChange={e=>set("smoking_status",e.target.value)}>
                <option value="">Unknown</option>
                <option value="never">Never</option>
                <option value="former">Former</option>
                <option value="current">Current</option>
              </select>
            </div>
          </div>
        </div>

        <div className="card">
          <h3 style={{ marginTop:0 }}>Genomics Mode</h3>
          <label className="small">Enter genomic features</label>
          <div className="row" style={{marginTop:8}}>
            {genomicsFeatures.map((k)=>(
              <div key={k}>
                <label className="small">{k}</label>
                <input
                  className={`input ${fieldErrors[`genomics.${k}`] ? "input-error" : ""}`}
                  type="number"
                  step={genomicsSpec(k).step}
                  min={genomicsSpec(k).min}
                  max={genomicsSpec(k).max}
                  inputMode="decimal"
                  value={genomicsForm[k] ?? ""}
                  onChange={e=>setGeno(k, e.target.value)}
                  placeholder={genomicsSpec(k).hint}
                />
                {fieldErrors[`genomics.${k}`] && <div className="field-error">{fieldErrors[`genomics.${k}`]}</div>}
              </div>
            ))}
          </div>
          <div style={{height:10}} />
          <label className="small">Or upload one genomics CSV row</label><br/>
          <input className={fieldErrors.genomicsFile ? "input-error" : ""} type="file" accept=".csv,text/csv" onChange={e=>{ setGenomicsFile(e.target.files?.[0]||null); clearFieldError("genomicsFile"); }} />
          {fieldErrors.genomicsFile && <div className="field-error">{fieldErrors.genomicsFile}</div>}
          <p className="small" style={{ marginTop:6 }}>
            CSV format: first line headers, second line one patient row.
          </p>
        </div>
      </div>

      <div className="row" style={{ alignItems: "start", marginTop: 16 }}>
        <div className="card">
          <h3 style={{ marginTop:0 }}>Retina Mode</h3>
          <label className="small">Optional retina image</label><br/>
          <input className={fieldErrors.retina ? "input-error" : ""} type="file" accept="image/*" onChange={e=>{ setRetinaFile(e.target.files?.[0]||null); clearFieldError("retina"); }} />
          {fieldErrors.retina && <div className="field-error">{fieldErrors.retina}</div>}
          <p className="small" style={{ marginTop:8 }}>
            JPG/PNG, clear focus, minimal blur/glare, evenly lit, min 512x512 (recommended 1024x1024+), up to 10MB.
          </p>
        </div>

        <div className="card">
          <h3 style={{ marginTop:0 }}>Skin Mode</h3>
          <label className="small">Optional skin image</label><br/>
          <input className={fieldErrors.skin ? "input-error" : ""} type="file" accept="image/*" onChange={e=>{ setSkinFile(e.target.files?.[0]||null); clearFieldError("skin"); }} />
          {fieldErrors.skin && <div className="field-error">{fieldErrors.skin}</div>}
          <p className="small" style={{ marginTop:8 }}>
            JPG/PNG, clear focus, minimal blur/glare, evenly lit, min 512x512 (recommended 1024x1024+), up to 10MB.
          </p>
        </div>
      </div>

      <div className="row" style={{ alignItems: "start", marginTop: 16 }}>
        <div className="card">
          <h3 style={{ marginTop:0 }}>Run Fusion</h3>
          <button className="btn" onClick={run} disabled={busy}>{busy ? "Running..." : "Run Fusion Screening"}</button>
          {err && <p style={{color:"#ff8080"}}>{err}</p>}
        </div>

        <div className="card">
          <h3 style={{marginTop:0}}>Fusion Result</h3>
          {!result ? <p className="small">No result yet.</p> : (
            <>
              <p className="small">
                Final: <b>{fusionLabelText(result.fusion?.final_label)}</b><br/>
                p: <b>{result.fusion?.final_proba === null ? "N/A" : Number(result.fusion?.final_proba).toFixed(3)}</b><br/>
                reason: {result.fusion?.reason}<br/>
                threshold: {result.threshold_used}<br/>
                genomics p: <b>{result.genomics?.probability === undefined || result.genomics?.probability === null ? "N/A" : Number(result.genomics?.probability).toFixed(3)}</b>
              </p>
              <div className="card" style={{ marginTop: 10 }}>
                <b>Interpretation</b>
                <p className="small" style={{ marginTop: 8 }}>
                  Patient: {result.fusion?.final_label === "screen_positive_refer"
                    ? "Your combined screening suggests higher risk. Please proceed for clinical review and confirmatory testing."
                    : result.fusion?.final_label === "screen_negative"
                      ? "Your combined screening suggests lower current risk. Keep routine health follow-up."
                      : result.fusion?.final_label === "retake_image"
                        ? "At least one modality failed quality gate. Please retake and repeat screening."
                        : "Screening could not be completed because required input data was insufficient."}
                </p>
                <p className="small" style={{ marginTop: 6 }}>
                  Clinician: {result.fusion?.final_label === "screen_positive_refer"
                    ? "Fusion output crossed operating threshold; referral pathway is recommended."
                    : result.fusion?.final_label === "screen_negative"
                      ? "Fusion output below threshold. Review context and risk factors before excluding further workup."
                      : result.fusion?.final_label === "retake_image"
                        ? "At least one modality quality gate failed. Repeat data capture before interpretation."
                        : "Missing required modality data; rely on complete clinical dataset."}
                </p>
              </div>
              <button className="btn secondary" onClick={downloadPdf} disabled={!predId}>Download PDF</button>
            </>
          )}
        </div>
      </div>

      <div className="row" style={{ alignItems: "start", marginTop: 16 }}>
        <div className="card">
          <h3 style={{marginTop:0}}>Retina Grad-CAM (if present)</h3>
          {!retinaOverlay ? <p className="small">No overlay.</p> : (
            <img src={retinaOverlay} alt="fusion retina overlay" style={{maxWidth:"100%", borderRadius:12}} />
          )}
        </div>

        <div className="card">
          <h3 style={{marginTop:0}}>Skin Overlay (if present)</h3>
          {!skinOverlay ? <p className="small">No overlay.</p> : (
            <img src={skinOverlay} alt="fusion skin overlay" style={{maxWidth:"100%", borderRadius:12}} />
          )}
        </div>
      </div>
    </div>
  );
}

