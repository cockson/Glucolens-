import React, { useState } from "react";
import { api } from "../lib/api";
import Locked from "./Locked.jsx";
import { isLockedError, lockedMessage } from "../lib/errors";

export default function RecordOutcome(){
  const [patientKey, setPatientKey] = useState("");
  const [referralId, setReferralId] = useState("");
  const [label, setLabel] = useState("confirmed_t2d");
  const [notes, setNotes] = useState("");
  const [ok, setOk] = useState(false);
  const [err, setErr] = useState("");
  const [locked, setLocked] = useState(null);

  async function submit(){
    setErr(""); setOk(false);
    try{
      const payload = {
        patient_key: patientKey.trim(),
        referral_id: referralId || null,
        outcome_label: label,
        notes: notes || null,
      };
      await api.post("/api/outcomes/", payload);
      setOk(true);
    }catch(e){
      if (isLockedError(e)) setLocked(lockedMessage(e));
      else setErr(e?.response?.data?.detail || "Failed to record outcome");
    }
  }

  if (locked) return <Locked message={locked} />;

  return (
    <div className="container">
      <div className="card" style={{ maxWidth: 860, margin:"20px auto" }}>
        <h2>Record Outcome (Hospital)</h2>
        <p className="small">
          Capture confirmed outcome for monitoring (drift/outcome-based monitoring comes later).
        </p>

        <div className="row">
          <div>
            <label className="small">Patient Key</label>
            <input className="input" value={patientKey} onChange={e=>setPatientKey(e.target.value)} placeholder="PAT_001_ABC" />
          </div>
          <div>
            <label className="small">Referral ID (optional)</label>
            <input className="input" value={referralId} onChange={e=>setReferralId(e.target.value)} placeholder="referral UUID" />
          </div>
        </div>

        <div style={{ height: 10 }} />

        <label className="small">Outcome label</label>
        <select className="input" value={label} onChange={e=>setLabel(e.target.value)}>
          <option value="confirmed_t2d">Confirmed T2D</option>
          <option value="confirmed_not_diabetic">Confirmed Not Diabetic</option>
          <option value="prediabetes">Prediabetes</option>
          <option value="unknown">Unknown / Not confirmed</option>
        </select>

        <div style={{ height: 10 }} />
        <label className="small">Clinical notes (optional)</label>
        <textarea className="input" style={{ minHeight: 110 }} value={notes} onChange={e=>setNotes(e.target.value)} />

        <div style={{ height: 12 }} />
        <button className="btn" onClick={submit}>Save outcome</button>

        {ok && <p className="small">✅ Outcome saved.</p>}
        {err && <p style={{ color:"#ff8080" }}>{err}</p>}
      </div>
    </div>
  );
}