import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { AuthProvider, useAuth } from "./lib/auth.jsx";
import { LanguageProvider } from "./lib/i18n.jsx";
import Landing from "./pages/Landing.jsx";
import Login from "./pages/Login.jsx";
import DashboardLayout from "./pages/dashboard/DashboardLayout.jsx";
import Overview from "./pages/dashboard/Overview.jsx";
import Beneficiaries from "./pages/dashboard/Beneficiaries.jsx";
import VoiceVisit from "./pages/dashboard/VoiceVisit.jsx";
import QRScanner from "./pages/dashboard/QRScanner.jsx";
import PulseThread from "./pages/dashboard/PulseThread.jsx";
import PulseDrift from "./pages/dashboard/PulseDrift.jsx";
import GeoPulse from "./pages/dashboard/GeoPulse.jsx";
import Reminders from "./pages/dashboard/Reminders.jsx";
import Settings from "./pages/dashboard/Settings.jsx";
import Households from "./pages/dashboard/Households.jsx";
import HouseholdDetail from "./pages/dashboard/HouseholdDetail.jsx";
import HouseholdHealth from "./pages/dashboard/HouseholdHealth.jsx";
import Notifications from "./pages/dashboard/Notifications.jsx";

function RequireAuth({ children }) {
  const { user } = useAuth();
  if (!user) return <Navigate to="/login" replace />;
  return children;
}

export default function App() {
  return (
    <LanguageProvider>
      <AuthProvider>
        <BrowserRouter>
          <Routes>
            <Route path="/" element={<Landing />} />
            <Route path="/login" element={<Login />} />
            <Route
              path="/app"
              element={
                <RequireAuth>
                  <DashboardLayout />
                </RequireAuth>
              }
            >
              <Route index element={<Overview />} />
              <Route path="beneficiaries" element={<Beneficiaries />} />
              <Route path="beneficiaries/:id" element={<PulseThread />} />
              <Route path="households" element={<Households />} />
              <Route path="households/:id" element={<HouseholdDetail />} />
              <Route path="household-health" element={<HouseholdHealth />} />
              <Route path="voice-visit" element={<VoiceVisit />} />
              <Route path="qr-scanner" element={<QRScanner />} />
              <Route path="pulse-thread" element={<PulseThread />} />
              <Route path="pulse-drift" element={<PulseDrift />} />
              <Route path="geopulse" element={<GeoPulse />} />
              <Route path="alerts" element={<Navigate to="/app" replace />} />
              <Route path="reminders" element={<Reminders />} />
              <Route path="notifications" element={<Notifications />} />
              {/* Removed from ASHA worker interface; redirect old paths safely */}
              <Route path="research/*" element={<Navigate to="/app" replace />} />
              <Route path="connect" element={<Navigate to="/app" replace />} />
              <Route path="health-guide" element={<Navigate to="/app" replace />} />
              <Route path="asha-field-assistance" element={<Navigate to="/app" replace />} />
              <Route path="my-health-plan" element={<Navigate to="/app" replace />} />
              <Route path="settings" element={<Settings />} />
            </Route>
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </BrowserRouter>
      </AuthProvider>
    </LanguageProvider>
  );
}
