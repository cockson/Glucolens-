import React, { useEffect, useMemo, useState } from "react";
import { api } from "../lib/api";
import { getAuth } from "../lib/authStore";
import Locked from "./Locked.jsx";
import { isLockedError, lockedMessage } from "../lib/errors";
import QrImage from "../components/QrImage.jsx";
import ConsentCard from "../components/ConsentCard.jsx";

export default function CreateReferral(){
  const auth = getAuth();
  const [facilities, setFacilities] = useState([]);
  const [country, setCountry] = useState("NG");
  const [q, setQ] = useState("");
  const [toFacilityId, setToFacilityId] = useState("");
  const [patientKey, setPatientKey] = useState("");
  const [riskScore, setRiskScore] = useState(70);
  const [reason, setReason] = useState("High diabetes risk — refer for confirmatory testing.");
  const [created, setCreated] = useState(null);

  const [consent, setConsent] = useState({ ok:false });
  const [err, setErr] = useState("");
  const [locked, setLocked] = useState(null);
  const [busy, setBusy] = useState(false);

  useEffect(()=>{
    // default country from org if you want later; for now use env
    setCountry(import.meta.env.VITE_DEFAULT_COUNTRY || "NG");
  },[]);

  async function searchFacilities(){
    setErr("");
    try{
      const res = await api.get("/api/tenancy/public/facilities", {
        params: { country_code: country, facility_type: "hospital", q }
      });
      setFacilities(res.data);
    } catch(e){
      setErr("Failed to search facilities");
    }
  }

  async function submit(){
    setErr(""); setBusy(true); setCreated(null);
    try{
      if(!consent.ok) throw new Error("Consent is required.");
      if(!patientKey.trim()) throw new Error("Patient key is required.");
      const payload = {
        patient_key: patientKey.trim(),
        risk_score: Number(riskScore),
        reason,
        to_facility_id: toFacilityId || null,
        consent: consent, // stored later in Phase 2 when we persist consent per submission
      };
      const res = await api.post("/api/referrals/", payload);
      setCreated(res.data);
    } catch(e){
      if (isLockedError(e)) setLocked(lockedMessage(e));
      else setErr(e?.response?.data?.detail || e.message || "Create failed");
    } finally {
      setBusy(false);
    }
  }

  if (locked) return <Locked message={locked} />;

  return (
    <div className="container">
      <div className="card">
        <h2>Create Referral (Pharmacy → Hospital)</h2>
        <p className="small">
          Generate a QR code the hospital can scan to accept and continue care.
        </p>

        <div className="row" style={{ alignItems: "start" }}>
          <div className="card">
            <h3 style={{ marginTop: 0 }}>Referral details</h3>
            <label className="small">Patient Key (pseudonym)</label>
            <input className="input" value={patientKey} onChange={e=>setPatientKey(e.target.value)} placeholder="e.g., PAT_001_ABC" />
            <div style={{ height: 10 }} />
            <label className="small">Risk score (0–100)</label>
            <input className="input" type="number" min="0" max="100" value={riskScore} onChange={e=>setRiskScore(e.target.value)} />
            <div style={{ height: 10 }} />
            <label className="small">Reason</label>
            <textarea className="input" style={{ minHeight: 90 }} value={reason} onChange={e=>setReason(e.target.value)} />
            <div style={{ height: 12 }} />
            <button className="btn" onClick={submit} disabled={busy}>
              {busy ? "Creating…" : "Create referral + QR"}
            </button>
            {err && <p style={{ color:"#ff8080" }}>{err}</p>}
          </div>

          <div style={{ display:"grid", gap:14 }}>
            <ConsentCard
              country={country}
              lang={(import.meta.env.VITE_DEFAULT_LANG || "en")}
              onChange={setConsent}
            />

            <div className="card">
              <h3 style={{ marginTop: 0 }}>Target hospital (optional)</h3>
              <div className="row">
                <div>
                  <label className="small">Country</label>
                  <input className="input" value={country} onChange={e=>setCountry(e.target.value.toUpperCase())} />
                </div>
                <div>
                  <label className="small">Search</label>
                  <input className="input" value={q} onChange={e=>setQ(e.target.value)} placeholder="Ikeja, Abuja, etc." />
                </div>
              </div>
              <div style={{ height: 10 }} />
              <button className="btn secondary" onClick={searchFacilities}>Find hospitals</button>

              <div style={{ marginTop: 12 }}>
                <label className="small">Select hospital</label>
                <select className="input" value={toFacilityId} onChange={e=>setToFacilityId(e.target.value)}>
                  <option value="">Auto / Not specified</option>
                  {facilities.map(f=>(
                    <option key={f.id} value={f.id}>
                      {f.name} — {f.city || ""} {f.state || ""}
                    </option>
                  ))}
                </select>
              </div>
            </div>

            {created && (
              <div className="card">
                <h3 style={{ marginTop: 0 }}>Referral created ✅</h3>
                <p className="small">Share this QR with the patient or send to the hospital.</p>
                <QrImage base64={created.qr_png_base64} />
                <div style={{ height: 10 }} />
                <div className="small">
                  Link: <a href={created.referral_url} style={{ color:"white" }}>{created.referral_url}</a>
                </div>
                <div className="small">Referral ID: {created.id}</div>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}