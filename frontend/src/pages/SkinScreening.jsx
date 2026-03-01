import React, { useState } from "react";
import { api } from "../lib/api";
import Locked from "./Locked.jsx";
import { isLockedError, lockedMessage } from "../lib/errors";

const MAX_IMAGE_BYTES = 10 * 1024 * 1024;

export default function SkinScreening(){
  const [file,setFile]=useState(null);
  const [result,setResult]=useState(null);
  const [predId,setPredId]=useState(null);
  const [err,setErr]=useState("");
  const [busy,setBusy]=useState(false);
  const [locked,setLocked]=useState(null);
  const skinLabelText = (label) => {
    if (label === "positive") return "Positive";
    if (label === "negative") return "Negative";
    return label || "N/A";
  };

  async function run(){
    setErr(""); setResult(null); setPredId(null);
    if(!file){ setErr("Choose an image."); return; }
    if (!String(file.type || "").startsWith("image/")) { setErr("Selected file must be an image."); return; }
    if (file.size > MAX_IMAGE_BYTES) { setErr("Image is too large (max 10MB)."); return; }
    setBusy(true);
    try{
      const fd = new FormData();
      fd.append("file", file);
      const r = await api.post("/api/skin/predict", fd, { headers:{ "Content-Type":"multipart/form-data" }});
      setResult(r.data);
      setPredId(r.data.prediction_id);
    }catch(e){
      if (isLockedError(e)) setLocked(lockedMessage(e));
      else setErr(e?.response?.data?.detail || "Prediction failed");
    }finally{
      setBusy(false);
    }
  }

  function downloadPdf(){
    if(!predId) return;
    window.open(`${import.meta.env.VITE_API_URL}/api/skin/report/${predId}`, "_blank");
  }

  if (locked) return <Locked message={locked} />;

  const overlay = result?.explainability?.overlay_png_base64
    ? `data:image/png;base64,${result.explainability.overlay_png_base64}` : null;

  return (
    <div className="container">
      <div className="card">
        <h2>Skin Screening (Grad-CAM)</h2>
        <p className="small">Upload skin image → calibrated probability + Grad-CAM overlay + quality gate.</p>

        <input type="file" accept="image/*" onChange={e=>setFile(e.target.files?.[0]||null)} />
        <p className="small" style={{ marginTop:8 }}>
          Expected image quality: JPG or PNG, clear focus, no heavy blur/glare, evenly lit, minimum 512x512 pixels, recommended 1024x1024+, and file size up to 10MB.
        </p>
        <div style={{height:10}} />
        <button className="btn" onClick={run} disabled={busy}>{busy?"Running…":"Run skin screening"}</button>
        {err && <p style={{color:"#ff8080"}}>{err}</p>}

        <div className="row" style={{alignItems:"start", marginTop:12}}>
          <div className="card">
            <h3 style={{marginTop:0}}>Result</h3>
            {!result ? <p className="small">No result yet.</p> : (
              <>
                <p className="small">
                  Predicted: <b>{skinLabelText(result.predicted_label)}</b><br/>
                  P(positive): <b>{result.probabilities?.positive===null ? "N/A" : Number(result.probabilities?.positive).toFixed(3)}</b><br/>
                  Quality: <b>{result.quality_gate?.passed ? "passed" : "failed"}</b> ({result.quality_gate?.reason})
                </p>
                <div className="card" style={{ marginTop: 10 }}>
                  <b>Interpretation</b>
                  <p className="small" style={{ marginTop: 8 }}>
                    Patient: {result.quality_gate?.passed
                      ? (result.predicted_label === "positive"
                        ? "This screening indicates a higher-risk skin finding. Please consult a clinician for diagnosis."
                        : "This screening did not detect a strong high-risk skin signal. Continue monitoring any changing lesions.")
                      : "Image quality was insufficient for a reliable interpretation. Please retake a clearer image."}
                  </p>
                  <p className="small" style={{ marginTop: 6 }}>
                    Clinician: {result.quality_gate?.passed
                      ? "Use as screening support only; correlate with history, examination, and definitive diagnostic pathway."
                      : "Quality gate failed. Do not use this output for decision-making until image quality criteria are met."}
                  </p>
                </div>
                <button className="btn secondary" onClick={downloadPdf} disabled={!predId}>Download PDF</button>
              </>
            )}
          </div>

          <div className="card">
            <h3 style={{marginTop:0}}>Grad-CAM</h3>
            {!overlay ? <p className="small">No overlay.</p> :
              <img src={overlay} alt="skin gradcam" style={{maxWidth:"100%", borderRadius:12}} />
            }
          </div>
        </div>
      </div>
    </div>
  );
}
