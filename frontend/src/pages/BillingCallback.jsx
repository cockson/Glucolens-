import React, { useEffect, useState } from "react";
import { useSearchParams, Link } from "react-router-dom";
import { api } from "../lib/api";

export default function BillingCallback(){
  const [params] = useSearchParams();
  const reference = params.get("reference");
  const [state,setState] = useState({ loading:true, ok:false, msg:"" });

  useEffect(()=>{
    async function run(){
      if(!reference){
        setState({ loading:false, ok:false, msg:"Missing reference." });
        return;
      }
      try{
        const res = await api.get(`/api/billing/checkout/verify/${encodeURIComponent(reference)}`);
        setState({ loading:false, ok:true, msg:`Subscription status: ${res.data.subscription_status}` });
      }catch(e){
        setState({ loading:false, ok:false, msg:e?.response?.data?.detail || "Verification failed" });
      }
    }
    run();
  },[reference]);

  return (
    <div className="container">
      <div className="card">
        <h2>Billing Verification</h2>
        {state.loading ? <p className="small">Verifying payment…</p> : (
          <>
            <p className="small">{state.ok ? "✅ " : "❌ "}{state.msg}</p>
            <div style={{ display:"flex", gap:10, flexWrap:"wrap" }}>
              <Link className="btn" to="/dashboard">Go to dashboard</Link>
              <Link className="btn secondary" to="/billing">Back to billing</Link>
            </div>
          </>
        )}
      </div>
    </div>
  );
}