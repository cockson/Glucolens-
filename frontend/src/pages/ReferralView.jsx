import React, { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { api } from "../lib/api";
import Locked from "./Locked.jsx";
import { isLockedError, lockedMessage } from "../lib/errors";

export default function ReferralView(){
  const { id } = useParams();
  const [ref,setRef]=useState(null);
  const [err,setErr]=useState("");
  const [note,setNote]=useState("");
  const [busy,setBusy]=useState(false);
  const [locked,setLocked]=useState(null);

  async function fetchReferral(){
    const r = await api.get(`/api/referrals/${id}`);
    setRef(r.data);
  }

  useEffect(()=>{
    fetchReferral()
      .catch(e=>{
        if (isLockedError(e)) setLocked(lockedMessage(e));
        else setErr(e?.response?.data?.detail || "Failed");
      });
  },[id]);

  async function accept(){
    setErr("");
    setNote("");
    setBusy(true);
    try{
      await api.post(`/api/referrals/${id}/accept`);
      await fetchReferral();
      setNote("Referral accepted successfully.");
    }catch(e){
      if (isLockedError(e)) setLocked(lockedMessage(e));
      else setErr(e?.response?.data?.detail || "Accept failed");
    }finally{
      setBusy(false);
    }
  }

  if (locked) return <Locked message={locked} />;

  return (
    <div className="container">
      <div className="card">
        <h2>Referral</h2>
        {err && <p style={{ color:"#ff8080" }}>{err}</p>}
        {note && <p className="small" style={{ color:"#9ad1ff" }}>{note}</p>}
        {!ref ? <p className="small">Loading...</p> : (
          <>
            <p className="small">Status: <b>{ref.status}</b></p>
            <p className="small">Patient Key: {ref.patient_key}</p>
            <p className="small">Risk Score: {ref.risk_score}/100</p>
            <p className="small">Reason: {ref.reason}</p>
            <button className="btn" onClick={accept} disabled={busy || ref.status !== "open"}>
              {busy ? "Accepting..." : "Accept Referral"}
            </button>
          </>
        )}
      </div>
    </div>
  );
}
