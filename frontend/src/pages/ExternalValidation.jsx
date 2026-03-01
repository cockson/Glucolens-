import React, { useEffect, useState } from "react";
import { api } from "../lib/api";
import Locked from "./Locked.jsx";
import { isLockedError, lockedMessage } from "../lib/errors";

const COUNTRY_RE = /^[A-Z]{2}$/;
const MAX_CSV_BYTES = 10 * 1024 * 1024;

export default function ExternalValidation(){
  const [datasets,setDatasets]=useState([]);
  const [runs,setRuns]=useState([]);
  const [siteName,setSiteName]=useState("");
  const [country,setCountry]=useState("NG");
  const [desc,setDesc]=useState("");
  const [file,setFile]=useState(null);
  const [err,setErr]=useState("");
  const [locked,setLocked]=useState(null);
  const [busy,setBusy]=useState(false);

  async function refresh(){
    try{
      const d = await api.get("/api/validation/datasets");
      setDatasets(d.data);
    }catch(e){
      if (isLockedError(e)) return setLocked(lockedMessage(e));
    }
    try{
      const r = await api.get("/api/validation/runs");
      setRuns(r.data);
    }catch{}
  }

  useEffect(()=>{ refresh(); },[]);

  async function upload(){
    setErr(""); setBusy(true);
    try{
      if(!file) throw new Error("Select a CSV file");
      if(!String(file.name || "").toLowerCase().endsWith(".csv")) throw new Error("Only .csv files are allowed.");
      if (file.size > MAX_CSV_BYTES) throw new Error("CSV file is too large (max 10MB).");
      if(!siteName.trim()) throw new Error("Enter site name");
      if(siteName.trim().length < 2 || siteName.trim().length > 120) throw new Error("Site name must be 2-120 characters.");
      if(!COUNTRY_RE.test(country.trim().toUpperCase())) throw new Error("Country must be a 2-letter code (for example, NG).");
      if(desc.trim().length > 300) throw new Error("Description must be at most 300 characters.");
      const fd = new FormData();
      fd.append("site_name", siteName.trim());
      fd.append("country_code", country.trim().toUpperCase());
      fd.append("description", desc.trim());
      fd.append("file", file);
      await api.post("/api/validation/datasets/upload", fd);
      setSiteName(""); setDesc(""); setFile(null);
      await refresh();
    }catch(e){
      if (isLockedError(e)) setLocked(lockedMessage(e));
      else setErr(e?.response?.data?.detail || e.message || "Upload failed");
    }finally{
      setBusy(false);
    }
  }

  async function runValidation(datasetId){
    setErr(""); setBusy(true);
    try{
      await api.post(`/api/validation/run/${datasetId}`);
      await refresh();
    }catch(e){
      if (isLockedError(e)) setLocked(lockedMessage(e));
      else setErr(e?.response?.data?.detail || "Run failed");
    }finally{
      setBusy(false);
    }
  }

  async function downloadTemplate(){
    setErr("");
    try {
      const res = await api.get("/api/validation/template/tabular.csv", { responseType: "blob" });
      const blob = new Blob([res.data], { type: "text/csv" });
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "tabular_template.csv";
      document.body.appendChild(a);
      a.click();
      a.remove();
      window.URL.revokeObjectURL(url);
    } catch (e) {
      if (isLockedError(e)) setLocked(lockedMessage(e));
      else setErr(e?.response?.data?.detail || "Template download failed");
    }
  }

  async function downloadReport(runId){
    setErr("");
    try {
      const res = await api.get(`/api/validation/runs/${runId}/report.pdf`, { responseType: "blob" });
      const blob = new Blob([res.data], { type: "application/pdf" });
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `validation_report_${runId}.pdf`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      window.URL.revokeObjectURL(url);
    } catch (e) {
      if (isLockedError(e)) setLocked(lockedMessage(e));
      else setErr(e?.response?.data?.detail || "Report download failed");
    }
  }

  if (locked) return <Locked message={locked} />;

  return (
    <div className="container">
      <div className="card">
        <div style={{display:"flex", justifyContent:"space-between", gap:10, flexWrap:"wrap"}}>
          <h2 style={{margin:0}}>External Validation (Real Site Data)</h2>
          <button className="btn secondary" onClick={downloadTemplate}>Download CSV template</button>
        </div>

        <p className="small">
          Upload de-identified site data with columns matching the model card features + <b>label</b> (0/1).
        </p>

        {err && <p style={{ color:"#ff8080" }}>{err}</p>}

        <div className="card" style={{marginTop:12}}>
          <h3 style={{marginTop:0}}>Upload dataset</h3>
          <label className="small">Site name</label>
          <input className="input" value={siteName} maxLength={120} onChange={e=>setSiteName(e.target.value)} placeholder="Clinic X - Lagos" />
          <div className="small">Expected length: 2-120 characters</div>
          <div style={{height:8}} />
          <label className="small">Country</label>
          <input className="input" value={country} maxLength={2} onChange={e=>setCountry(e.target.value.toUpperCase())} placeholder="NG" />
          <div className="small">Expected format: 2-letter ISO code</div>
          <div style={{height:8}} />
          <label className="small">Description</label>
          <input className="input" value={desc} maxLength={300} onChange={e=>setDesc(e.target.value)} placeholder="De-identified external validation cohort" />
          <div className="small">Max length: 300 characters</div>
          <div style={{height:8}} />
          <input type="file" accept=".csv" onChange={e=>setFile(e.target.files?.[0] || null)} />
          <div className="small">Only .csv, max 10MB</div>
          <div style={{height:10}} />
          <button className="btn" onClick={upload} disabled={busy}>{busy ? "Working…" : "Upload"}</button>
        </div>

        <div className="row" style={{alignItems:"start", marginTop:12}}>
          <div className="card">
            <h3 style={{marginTop:0}}>Datasets</h3>
            <div className="small">
              {datasets.map(ds=>(
                <div key={ds.id} className="card" style={{marginBottom:10}}>
                  <b>{ds.site_name}</b> ({ds.country_code || "??"})<br/>
                  rows: {ds.n_rows}<br/>
                  sha256: {ds.sha256.slice(0,16)}…<br/>
                  <button className="btn secondary" onClick={()=>runValidation(ds.id)} disabled={busy}>Run validation</button>
                </div>
              ))}
              {!datasets.length && <p className="small">No datasets uploaded yet.</p>}
            </div>
          </div>

          <div className="card">
            <h3 style={{marginTop:0}}>Validation runs</h3>
            <div className="small">
              {runs.map(r=>(
                <div key={r.id} className="card" style={{marginBottom:10}}>
                  <b>Run:</b> {r.id.slice(0,8)}…<br/>
                  dataset: {r.dataset_id.slice(0,8)}…<br/>
                  model: {r.model_name} / {r.model_version}<br/>
                  status: {r.status}<br/>
                  <button className="btn secondary" onClick={()=>downloadReport(r.id)}>Download report</button>
                </div>
              ))}
              {!runs.length && <p className="small">No runs yet.</p>}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
