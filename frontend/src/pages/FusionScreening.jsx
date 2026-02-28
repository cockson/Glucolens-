import React, { useEffect, useState } from "react";
import { api } from "../lib/api";
import { getAuth } from "../lib/authStore";
import Locked from "./Locked.jsx";
import { isLockedError, lockedMessage } from "../lib/errors";

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
  const [form, setForm] = useState({ age:"", sex:"", bmi:"", waist_circumference:"", hip_circumference:"", systolic_bp:"", diastolic_bp:"" });
  const [result, setResult] = useState(null);
  const [predId, setPredId] = useState(null);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const [locked, setLocked] = useState(null);

  const fusionLabelText = (label) => {
    if (label === "screen_positive_refer") return "Screen Positive (Refer)";
    if (label === "screen_negative") return "Screen Negative";
    if (label === "retake_image") return "Retake Image Needed";
    if (label === "insufficient_data") return "Insufficient Data";
    return label || "N/A";
  };

  function set(k, v){ setForm((p) => ({ ...p, [k]: v })); }
  function setGeno(k, v){ setGenomicsForm((p) => ({ ...p, [k]: v })); }

  useEffect(() => {
    let alive = true;
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
  }, []);

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
    setBusy(true);

    if (!isPublic && patientKey.trim().length === 0) {
      setErr("Patient key is required for clinical tracking.");
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
          setErr(e?.message || "Invalid genomics CSV.");
          setBusy(false);
          return;
        }
      }

      genomicsFeatures.forEach((k) => {
        const raw = (genomicsForm[k] ?? "").toString().trim();
        if (!raw) return;
        const n = Number(raw);
        genomics[k] = Number.isNaN(n) ? raw : n;
      });
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

      const r = await api.post("/api/fusion/predict", fd, { headers: { "Content-Type": "multipart/form-data" } });
      setResult(r.data);
      setPredId(r.data.prediction_id);
    } catch (e) {
      if (isLockedError(e)) setLocked(lockedMessage(e));
      else setErr(e?.response?.data?.detail || "Fusion prediction failed");
    } finally {
      setBusy(false);
    }
  }

  function downloadPdf(){
    if (!predId) return;
    window.open(`${import.meta.env.VITE_API_URL}/api/fusion/report/${predId}`, "_blank");
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
        <p className="small">Each modality is in its own card, dashboard-style, with the same glassmorphic card design.</p>
      </div>

      <div style={{ height: 16 }} />

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(300px, 1fr))", gap: 16, alignItems: "start" }}>
        <div className="card">
          <h3 style={{ marginTop:0 }}>Tabular Mode</h3>
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
        </div>

        <div className="card">
          <h3 style={{ marginTop:0 }}>Retina Mode</h3>
          <label className="small">Optional retina image</label><br/>
          <input type="file" accept="image/*" onChange={e=>setRetinaFile(e.target.files?.[0]||null)} />
          <p className="small" style={{ marginTop:8 }}>
            JPG/PNG, clear focus, minimal blur/glare, evenly lit, min 512x512 (recommended 1024x1024+), up to 10MB.
          </p>
        </div>

        <div className="card">
          <h3 style={{ marginTop:0 }}>Skin Mode</h3>
          <label className="small">Optional skin image</label><br/>
          <input type="file" accept="image/*" onChange={e=>setSkinFile(e.target.files?.[0]||null)} />
          <p className="small" style={{ marginTop:8 }}>
            JPG/PNG, clear focus, minimal blur/glare, evenly lit, min 512x512 (recommended 1024x1024+), up to 10MB.
          </p>
        </div>

        <div className="card">
          <h3 style={{ marginTop:0 }}>Genomics Mode</h3>
          <label className="small">Enter genomic features</label>
          <div className="row" style={{marginTop:8}}>
            {genomicsFeatures.map((k)=>(
              <div key={k}>
                <label className="small">{k}</label>
                <input className="input" value={genomicsForm[k] ?? ""} onChange={e=>setGeno(k, e.target.value)} />
              </div>
            ))}
          </div>
          <div style={{height:10}} />
          <label className="small">Or upload one genomics CSV row</label><br/>
          <input type="file" accept=".csv,text/csv" onChange={e=>setGenomicsFile(e.target.files?.[0]||null)} />
          <p className="small" style={{ marginTop:6 }}>
            CSV format: first line headers, second line one patient row.
          </p>
        </div>

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
