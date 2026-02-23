import React, { useEffect, useMemo, useState } from "react";
import { api } from "../lib/api";
import { getAuth } from "../lib/authStore";
import { useNavigate } from "react-router-dom";

function naira(kobo){ return "NGN " + (kobo/100).toLocaleString(); }

export default function Billing(){
  const [plans, setPlans] = useState([]);
  const [me, setMe] = useState(null);
  const [err, setErr] = useState("");
  const [busyPlanKey, setBusyPlanKey] = useState(null);
  const auth = getAuth();
  const nav = useNavigate();

  const email = useMemo(() => me?.email || auth?.email || "", [me, auth]);
  const orgId = useMemo(() => me?.org_id || auth?.org_id || null, [me, auth]);
  const role = useMemo(() => me?.role || auth?.role || null, [me, auth]);
  const isBusiness = useMemo(() => !!orgId && role !== "public", [orgId, role]);

  useEffect(() => {
    api.get("/api/billing/plans")
      .then((r) => setPlans(r.data))
      .catch(() => setErr("Failed to load plans"));

    api.get("/api/auth/me")
      .then((r) => setMe(r.data))
      .catch(() => {});
  }, []);

  async function subscribe(plan){
    const planKey = `${plan.tier}-${plan.interval}`;

    if (!orgId) {
      setErr("Business account details not found. Please log out and log in again.");
      return;
    }

    const key = import.meta.env.VITE_PAYSTACK_PUBLIC_KEY;
    if (!key || !(key.startsWith("pk_test_") || key.startsWith("pk_live_"))) {
      setErr("Invalid Paystack public key. Set VITE_PAYSTACK_PUBLIC_KEY in frontend/.env.");
      return;
    }

    setErr("");
    setBusyPlanKey(planKey);

    try {
      const init = await api.post("/api/billing/checkout/initialize", {
        org_id: orgId,
        tier: plan.tier,
        interval: plan.interval,
        email,
      });

      const { reference } = init.data;

      if (!window.PaystackPop) {
        throw new Error("Paystack SDK not loaded. Check index.html script tag.");
      }

      const handler = window.PaystackPop.setup({
        key,
        email,
        amount: plan.amount_kobo,
        currency: "NGN",
        ref: reference,
        callback: function(){
          setBusyPlanKey(null);
          nav(`/billing/callback?reference=${encodeURIComponent(reference)}`);
        },
        onClose: function(){
          setBusyPlanKey(null);
        }
      });

      handler.openIframe();
    } catch (e) {
      setBusyPlanKey(null);
      setErr(e?.response?.data?.detail || e.message || "Checkout failed");
    }
  }

  return (
    <div className="container">
      <div className="card">
        <h2>Billing</h2>
        <p className="small">Choose a subscription plan. Immediate lockout is enforced when inactive.</p>
        {err && <p style={{ color: "#ff8080" }}>{err}</p>}

        <div className="row" style={{ marginTop: 12 }}>
          {plans.map((p) => {
            const planKey = `${p.tier}-${p.interval}`;
            const isBusy = busyPlanKey === planKey;
            return (
              <div key={planKey} className="card">
                <h3 style={{ marginTop: 0 }}>{p.tier.toUpperCase()} | {p.interval.toUpperCase()}</h3>
                <p className="small">Price: <b>{naira(p.amount_kobo)}</b></p>
                <p className="small">Org ID: {orgId || "n/a"}</p>
                <button className="btn" onClick={() => subscribe(p)} disabled={!!busyPlanKey || !isBusiness}>
                  {isBusy ? "Processing..." : "Subscribe"}
                </button>
              </div>
            );
          })}
        </div>

        {!isBusiness && (
          <p className="small" style={{ marginTop: 10 }}>
            Billing is only available for business accounts.
          </p>
        )}
      </div>
    </div>
  );
}
