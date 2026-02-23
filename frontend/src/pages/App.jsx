import React, { useEffect } from "react";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { getAuth, setAuth } from "../lib/authStore";
import { setAuthHeader } from "../lib/api";
import CreateReferral from "./CreateReferral.jsx";
import RecordOutcome from "./RecordOutcome.jsx";
import Login from "./Login.jsx";
import RegisterBusiness from "./RegisterBusiness.jsx";
import RegisterPublic from "./RegisterPublic.jsx";
import Dashboard from "./Dashboard.jsx";
import Billing from "./Billing.jsx";
import BillingCallback from "./BillingCallback.jsx";
import Facilities from "./Facilities.jsx";
import ReferralView from "./ReferralView.jsx";

function Protected({ children }) {
  const auth = getAuth();
  if (!auth?.access_token) return <Navigate to="/login" replace />;
  return children;
}

export default function App() {
  useEffect(() => {
    const auth = getAuth();
    if (auth?.access_token) setAuthHeader(auth.access_token);
  }, []);

  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Navigate to="/dashboard" replace />} />
        <Route path="/login" element={<Login />} />
        <Route path="/register-business" element={<RegisterBusiness />} />
        <Route path="/register-public" element={<RegisterPublic />} />
        <Route path="/referrals/new" element={<Protected><CreateReferral /></Protected>} />
        <Route path="/outcomes/new" element={<Protected><RecordOutcome /></Protected>} />
        <Route path="/dashboard" element={<Protected><Dashboard /></Protected>} />
        <Route path="/billing" element={<Protected><Billing /></Protected>} />
        <Route path="/billing/callback" element={<Protected><BillingCallback /></Protected>} />

        <Route path="/facilities" element={<Facilities />} />
        <Route path="/referral/:id" element={<Protected><ReferralView /></Protected>} />

        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  );
}