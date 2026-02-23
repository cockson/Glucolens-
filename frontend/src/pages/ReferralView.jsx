import React, { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { api } from "../lib/api";
import Locked from "./Locked.jsx";
import { isLockedError, lockedMessage } from "../lib/errors";

export default function ReferralView(){
  const { id } = useParams();
  const [ref,setRef]=useState(null);
  const [err,setErr]=useState("");
  const [locked,setLocked]=useState(null);

  useEffect(()=>{
    api.get(`/api/referrals/${id}`)
      .then(r=>setRef(r.data))
      .catch(e=>{
        if (isLockedError(e)) setLocked(lockedMessage(e));
        else setErr(e?.response?.data?.detail || "Failed");
      });
  },[id]);

  async function accept(){
    setErr("");
    try{
      const res = await api.post(`/api/referrals/${id}/accept`);
      setRef(prev=>({ ...prev, status: res.data.status, to_facility_id: res.data.to_facility_id }));
    }catch(e){
      if (isLockedError(e)) setLocked(lockedMessage(e));
      else setErr(e?.response?.data?.detail || "Accept failed");
    }
  }

  if (locked) return <Locked message={locked} />;

  return (
    <div className="container">
      <div className="card">
        <h2>Referral</h2>
        {err && <p style={{ color:"#ff8080" }}>{err}</p>}
        {!ref ? <p className="small">Loading…</p> : (
          <>
            <p className="small">Status: <b>{ref.status}</b></p>
            <p className="small">Patient Key: {ref.patient_key}</p>
            <p className="small">Risk Score: {ref.risk_score}/100</p>
            <p className="small">Reason: {ref.reason}</p>
            <button className="btn" onClick={accept} disabled={ref.status !== "open"}>Accept Referral</button>
          </>
        )}
      </div>
    </div>
  );
}