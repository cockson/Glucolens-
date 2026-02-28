import React, { useEffect } from "react";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { getAuth, setAuth } from "../lib/authStore";
import { setAuthHeader } from "../lib/api";
import Sidebar from "../components/Sidebar.jsx";
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
import ReferralsList from "./ReferralsList.jsx";
import OutcomesList from "./OutcomesList.jsx";
import TabularInsights from "./TabularInsights.jsx";
import TabularScreening from "./TabularScreening.jsx";
import PublicQuickCheck from "./PublicQuickCheck.jsx";
import Monitoring from "./Monitoring.jsx";
import ExternalValidation from "./ExternalValidation.jsx";
import RetinaScreening from "./RetinaScreening.jsx";
import RetinaInsights from "./RetinaInsights.jsx";
import FusionScreening from "./FusionScreening.jsx";
import ThresholdGovernance from "./ThresholdGovernance.jsx";
import SkinScreening from "./SkinScreening.jsx";



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
      <div className="app-shell">
        <Sidebar />
        <div className="app-content">
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
            <Route path="/referrals" element={<Protected><ReferralsList /></Protected>} />
            <Route path="/outcomes" element={<Protected><OutcomesList /></Protected>} />
            <Route path="/facilities" element={<Facilities />} />
            <Route path="/referral/:id" element={<Protected><ReferralView /></Protected>} />
            <Route path="/models/tabular" element={<Protected><TabularInsights /></Protected>} />
            <Route path="/screening/tabular" element={<Protected><TabularScreening /></Protected>} />
            <Route path="/quick-check" element={<Protected><PublicQuickCheck /></Protected>} />
            <Route path="/monitoring" element={<Protected><Monitoring /></Protected>} />
            <Route path="*" element={<Navigate to="/" replace />} />
            <Route path="/validation" element={<Protected><ExternalValidation /></Protected>} />
            <Route path="/screening/retina" element={<Protected><RetinaScreening /></Protected>} />
            <Route path="/models/retina" element={<Protected><RetinaInsights /></Protected>} />
            <Route path="/screening/fusion" element={<Protected><FusionScreening /></Protected>} />
            <Route path="/governance/thresholds" element={<Protected><ThresholdGovernance /></Protected>} />
            <Route path="/screening/skin" element={<Protected><SkinScreening /></Protected>} />
          </Routes>
        </div>
      </div>
    </BrowserRouter>
  );
}
