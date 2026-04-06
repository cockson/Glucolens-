import React, { useEffect, useState } from "react";
import { api } from "../lib/api";
import Locked from "./Locked.jsx";
import { isLockedError, lockedMessage } from "../lib/errors";
import QrImage from "../components/QrImage.jsx";
import ConsentCard from "../components/ConsentCard.jsx";

const COUNTRY_RE = /^[A-Z]{2}$/;
const PATIENT_KEY_RE = /^[A-Za-z0-9_-]{3,64}$/;

export default function CreateReferral() {
  const [facilities, setFacilities] = useState([]);
  const [country, setCountry] = useState("NG");
  const [q, setQ] = useState("");
  const [toFacilityId, setToFacilityId] = useState("");
  const [patientKey, setPatientKey] = useState("");
  const [riskScore, setRiskScore] = useState(70);
  const [reason, setReason] = useState("High diabetes risk - refer for confirmatory testing.");
  const [created, setCreated] = useState(null);

  const [consent, setConsent] = useState({ ok: false });
  const [err, setErr] = useState("");
  const [locked, setLocked] = useState(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    setCountry(import.meta.env.VITE_DEFAULT_COUNTRY || "NG");
  }, []);

  function validateReferral() {
    if (!consent.ok) return "Consent is required.";
    if (!COUNTRY_RE.test(country.trim().toUpperCase())) return "Country must be a 2-letter code (for example, NG).";
    if (!PATIENT_KEY_RE.test(patientKey.trim())) return "Patient key must be 3-64 chars (letters, numbers, underscore, hyphen).";
    const risk = Number(riskScore);
    if (!Number.isFinite(risk) || risk < 0 || risk > 100) return "Risk score must be between 0 and 100.";
    if (reason.trim().length < 5 || reason.trim().length > 500) return "Reason must be 5-500 characters.";
    return null;
  }

  async function searchFacilities() {
    setErr("");
    const cc = country.trim().toUpperCase();
    if (!COUNTRY_RE.test(cc)) {
      setErr("Country must be a 2-letter code (for example, NG).");
      return;
    }
    try {
      const res = await api.get("/api/tenancy/public/facilities", {
        params: { country_code: cc, facility_type: "hospital", q: q.trim() },
      });
      setFacilities(res.data);
    } catch {
      setErr("Failed to search facilities");
    }
  }

  async function submit() {
    setErr("");
    setBusy(true);
    setCreated(null);
    try {
      const v = validateReferral();
      if (v) throw new Error(v);

      const payload = {
        patient_key: patientKey.trim(),
        risk_score: Number(riskScore),
        reason: reason.trim(),
        to_facility_id: toFacilityId || null,
        consent,
      };
      const res = await api.post("/api/referrals/", payload);
      setCreated(res.data);
    } catch (e) {
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
        <h2>Create Referral (Pharmacy - Hospital)</h2>
        <p className="small">Generate a QR code the hospital can scan to accept and continue care.</p>

        <div className="row" style={{ alignItems: "start" }}>
          <div className="card">
            <h3 style={{ marginTop: 0 }}>Referral details</h3>
            <label className="small">Patient Key (pseudonym)</label>
            <input
              className="input"
              value={patientKey}
              onChange={(e) => setPatientKey(e.target.value)}
              placeholder="e.g., PAT_001_ABC"
              maxLength={64}
            />
            <div className="small">Expected format: 3-64 chars (A-Z, 0-9, _, -)</div>
            <div style={{ height: 10 }} />
            <label className="small">Risk score (0-100)</label>
            <input
              className="input"
              type="number"
              min="0"
              max="100"
              step="0.1"
              inputMode="decimal"
              value={riskScore}
              onChange={(e) => setRiskScore(e.target.value)}
              placeholder="70"
            />
            <div className="small">Expected range: 0-100</div>
            <div style={{ height: 10 }} />
            <label className="small">Reason</label>
            <textarea
              className="input"
              style={{ minHeight: 90 }}
              value={reason}
              maxLength={500}
              onChange={(e) => setReason(e.target.value)}
            />
            <div className="small">Expected length: 5-500 characters</div>
            <div style={{ height: 12 }} />
            <button className="btn" onClick={submit} disabled={busy}>
              {busy ? "Creating..." : "Create referral + QR"}
            </button>
            {err && <p style={{ color: "#ff8080" }}>{err}</p>}
          </div>

          <div style={{ display: "grid", gap: 14 }}>
            <ConsentCard
              country={country}
              lang={import.meta.env.VITE_DEFAULT_LANG || "en"}
              onChange={setConsent}
            />

            <div className="card">
              <h3 style={{ marginTop: 0 }}>Target hospital (optional)</h3>
              <div className="row">
                <div>
                  <label className="small">Country</label>
                  <input
                    className="input"
                    value={country}
                    maxLength={2}
                    onChange={(e) => setCountry(e.target.value.toUpperCase())}
                    placeholder="NG"
                  />
                </div>
                <div>
                  <label className="small">Search</label>
                  <input
                    className="input"
                    value={q}
                    maxLength={80}
                    onChange={(e) => setQ(e.target.value)}
                    placeholder="Ikeja, Abuja, etc."
                  />
                </div>
              </div>
              <div style={{ height: 10 }} />
              <button className="btn secondary" onClick={searchFacilities}>Find hospitals</button>

              <div style={{ marginTop: 12 }}>
                <label className="small">Select hospital</label>
                <select className="input" value={toFacilityId} onChange={(e) => setToFacilityId(e.target.value)}>
                  <option value="">Auto / Not specified</option>
                  {facilities.map((f) => (
                    <option key={f.id} value={f.id}>
                      {f.name} - {f.city || ""} {f.state || ""}
                    </option>
                  ))}
                </select>
              </div>
            </div>

            {created && (
              <div className="card">
                <h3 style={{ marginTop: 0 }}>Referral created</h3>
                <p className="small">Share this QR with the patient or send to the hospital.</p>
                <QrImage base64={created.qr_png_base64} />
                <div style={{ height: 10 }} />
                <div className="small">
                  Link: <a className="system-link" href={created.referral_url}>{created.referral_url}</a>
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

