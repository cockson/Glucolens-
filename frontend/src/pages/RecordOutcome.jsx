import React, { useEffect, useState } from "react";
import { api } from "../lib/api";
import Locked from "./Locked.jsx";
import { isLockedError, lockedMessage } from "../lib/errors";
import { useSearchParams } from "react-router-dom";

const PATIENT_KEY_RE = /^[A-Za-z0-9_-]{3,64}$/;
const UUID_LIKE_RE = /^[0-9a-fA-F-]{8,64}$/;

export default function RecordOutcome(){
  const [params] = useSearchParams();
  const [patientKey, setPatientKey] = useState("");
  const [referralId, setReferralId] = useState("");
  const [label, setLabel] = useState("confirmed_t2d");
  const [notes, setNotes] = useState("");
  const [ok, setOk] = useState(false);
  const [err, setErr] = useState("");
  const [locked, setLocked] = useState(null);

  useEffect(() => {
    const pk = params.get("patient_key") || "";
    const rid = params.get("referral_id") || "";
    if (pk) setPatientKey(pk);
    if (rid) setReferralId(rid);
  }, [params]);

  async function submit(){
    setErr(""); setOk(false);
    try{
      const pk = patientKey.trim();
      const rid = referralId.trim();
      if (!PATIENT_KEY_RE.test(pk)) throw new Error("Patient key must be 3-64 chars (letters, numbers, underscore, hyphen).");
      if (rid && !UUID_LIKE_RE.test(rid)) throw new Error("Referral ID format is invalid.");
      if (notes.length > 2000) throw new Error("Clinical notes must be at most 2000 characters.");
      const payload = {
        patient_key: pk,
        referral_id: rid || null,
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
            <input className="input" value={patientKey} onChange={e=>setPatientKey(e.target.value)} placeholder="PAT_001_ABC" maxLength={64} />
            <div className="small">Expected format: 3-64 chars (A-Z, 0-9, _, -)</div>
          </div>
          <div>
            <label className="small">Referral ID (optional)</label>
            <input className="input" value={referralId} onChange={e=>setReferralId(e.target.value)} placeholder="referral UUID" maxLength={64} />
          </div>
        </div>

        <div style={{ height: 10 }} />

        <label className="small">Outcome label</label>
        <select className="input" value={label} onChange={e=>setLabel(e.target.value)}>
          <option value="confirmed_t2d">Confirmed Type 2 Diabetes</option>
          <option value="confirmed_not_diabetic">Confirmed Not Diabetic</option>
          <option value="prediabetes">Prediabetes</option>
          <option value="unknown">Unknown / Not confirmed</option>
        </select>

        <div style={{ height: 10 }} />
        <label className="small">Clinical notes (optional)</label>
        <textarea className="input" style={{ minHeight: 110 }} value={notes} maxLength={2000} onChange={e=>setNotes(e.target.value)} />
        <div className="small">Max length: 2000 characters</div>

        <div style={{ height: 12 }} />
        <button className="btn" onClick={submit}>Save outcome</button>

        {ok && <p className="small">✅ Outcome saved.</p>}
        {err && <p style={{ color:"#ff8080" }}>{err}</p>}
      </div>
    </div>
  );
}
