import React, { useEffect, useState } from "react";
import { api } from "../lib/api";
import { getAuth } from "../lib/authStore";

export default function Billing(){
  const [plans,setPlans]=useState([]);
  const [err,setErr]=useState("");
  const auth = getAuth();

  useEffect(()=>{
    api.get("/api/billing/plans").then(r=>setPlans(r.data)).catch(e=>setErr("Failed to load plans"));
  },[]);

  return (
    <div className="container">
      <div className="card">
        <h2>Billing</h2>
        <p className="small">Pick a plan. Next commit adds Paystack inline + callback.</p>
        {err && <p style={{ color:"#ff8080" }}>{err}</p>}
        <div className="row">
          {plans.map((p)=>(
            <div key={`${p.tier}-${p.interval}`} className="card">
              <h3 style={{ marginTop: 0 }}>{p.tier.toUpperCase()} • {p.interval}</h3>
              <p className="small">Amount: ₦{(p.amount_kobo/100).toLocaleString()}</p>
              <p className="small">Org: {auth?.org_id || "n/a"}</p>
              <button className="btn" disabled>Subscribe (next)</button>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}