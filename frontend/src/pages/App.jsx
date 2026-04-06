import React, { useEffect } from "react";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { getAuth } from "../lib/authStore";
import { setAuthHeader } from "../lib/api";
import { applyTheme } from "../lib/theme";
import Sidebar from "../components/Sidebar.jsx";
import CreateReferral from "./CreateReferral.jsx";
import RecordOutcome from "./RecordOutcome.jsx";
import Login from "./Login.jsx";
import RegisterBusiness from "./RegisterBusiness.jsx";
import RegisterPublic from "./RegisterPublic.jsx";
import Landing from "./Landing.jsx";
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
import FusionInsights from "./FusionInsights.jsx";
import ThresholdGovernance from "./ThresholdGovernance.jsx";
import SkinScreening from "./SkinScreening.jsx";
import SkinInsights from "./SkinInsights.jsx";
import GenomicsScreening from "./GenomicsScreening.jsx";
import GenomicsInsights from "./GenomicsInsights.jsx";
import AdminConsole from "./AdminConsole.jsx";

const CLINICIAN_ROLES = new Set(["clinician", "facility_admin", "org_admin", "super_admin"]);
const ADMIN_ROLES = new Set(["facility_admin", "org_admin", "super_admin"]);

function Protected({ children }) {
  const auth = getAuth();
  if (!auth?.access_token) return <Navigate to="/login" replace />;
  return children;
}

function ClinicianOnly({ children }) {
  const auth = getAuth();
  if (!auth?.access_token) return <Navigate to="/login" replace />;
  if (!CLINICIAN_ROLES.has(auth?.role)) return <Navigate to="/screening/fusion" replace />;
  return children;
}

function AdminOnly({ children }) {
  const auth = getAuth();
  if (!auth?.access_token) return <Navigate to="/login" replace />;
  if (!ADMIN_ROLES.has(auth?.role)) return <Navigate to="/dashboard" replace />;
  return children;
}

export default function App() {
  useEffect(() => {
    const auth = getAuth();
    if (auth?.access_token) setAuthHeader(auth.access_token);
    applyTheme();
  }, []);

  return (
    <BrowserRouter>
      <div className="app-shell">
        <Sidebar />
        <div className="app-content">
          <Routes>
            <Route path="/" element={<Landing />} />
            <Route path="/login" element={<Login />} />
            <Route path="/register-business" element={<RegisterBusiness />} />
            <Route path="/register-public" element={<RegisterPublic />} />
            <Route path="/referrals/new" element={<ClinicianOnly><CreateReferral /></ClinicianOnly>} />
            <Route path="/outcomes/new" element={<ClinicianOnly><RecordOutcome /></ClinicianOnly>} />
            <Route path="/dashboard" element={<ClinicianOnly><Dashboard /></ClinicianOnly>} />
            <Route path="/billing" element={<ClinicianOnly><Billing /></ClinicianOnly>} />
            <Route path="/billing/callback" element={<ClinicianOnly><BillingCallback /></ClinicianOnly>} />
            <Route path="/referrals" element={<ClinicianOnly><ReferralsList /></ClinicianOnly>} />
            <Route path="/outcomes" element={<ClinicianOnly><OutcomesList /></ClinicianOnly>} />
            <Route path="/facilities" element={<ClinicianOnly><Facilities /></ClinicianOnly>} />
            <Route path="/referral/:id" element={<ClinicianOnly><ReferralView /></ClinicianOnly>} />
            <Route path="/models/tabular" element={<ClinicianOnly><TabularInsights /></ClinicianOnly>} />
            <Route path="/screening/tabular" element={<ClinicianOnly><TabularScreening /></ClinicianOnly>} />
            <Route path="/quick-check" element={<ClinicianOnly><PublicQuickCheck /></ClinicianOnly>} />
            <Route path="/monitoring" element={<ClinicianOnly><Monitoring /></ClinicianOnly>} />
            <Route path="/validation" element={<ClinicianOnly><ExternalValidation /></ClinicianOnly>} />
            <Route path="/screening/retina" element={<ClinicianOnly><RetinaScreening /></ClinicianOnly>} />
            <Route path="/models/retina" element={<ClinicianOnly><RetinaInsights /></ClinicianOnly>} />
            <Route path="/models/skin" element={<ClinicianOnly><SkinInsights /></ClinicianOnly>} />
            <Route path="/models/fusion" element={<ClinicianOnly><FusionInsights /></ClinicianOnly>} />
            <Route path="/screening/fusion" element={<Protected><FusionScreening /></Protected>} />
            <Route path="/governance/thresholds" element={<ClinicianOnly><ThresholdGovernance /></ClinicianOnly>} />
            <Route path="/screening/skin" element={<ClinicianOnly><SkinScreening /></ClinicianOnly>} />
            <Route path="/screening/genomics" element={<ClinicianOnly><GenomicsScreening /></ClinicianOnly>} />
            <Route path="/models/genomics" element={<ClinicianOnly><GenomicsInsights /></ClinicianOnly>} />
            <Route path="/admin" element={<AdminOnly><AdminConsole /></AdminOnly>} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </div>
      </div>
    </BrowserRouter>
  );
}
