import React from "react";
import "@/App.css";
import {
  BrowserRouter,
  Routes,
  Route,
  useLocation,
} from "react-router-dom";
import { AuthProvider } from "@/context/AuthContext";
import { Toaster } from "@/components/ui/sonner";
import Landing from "@/pages/Landing";
import Dashboard from "@/pages/Dashboard";
import Trip from "@/pages/Trip";
import AuthCallback from "@/pages/AuthCallback";
import InvitePage from "@/pages/InvitePage";
import ProtectedRoute from "@/components/ProtectedRoute";

function AppRouter() {
  const location = useLocation();
  // CRITICAL: detect session_id in the URL fragment synchronously (before
  // any /me check) to avoid race conditions with the global AuthProvider.
  if (location.hash?.includes("session_id=")) {
    return <AuthCallback />;
  }
  return (
    <Routes>
      <Route path="/" element={<Landing />} />
      <Route
        path="/dashboard"
        element={
          <ProtectedRoute>
            <Dashboard />
          </ProtectedRoute>
        }
      />
      <Route
        path="/trip/:trip_id"
        element={
          <ProtectedRoute>
            <Trip />
          </ProtectedRoute>
        }
      />
      <Route path="/invite/:token" element={<InvitePage />} />
      <Route path="*" element={<Landing />} />
    </Routes>
  );
}

export default function App() {
  return (
    <div className="App">
      <BrowserRouter>
        <AuthProvider>
          <AppRouter />
          <Toaster
            theme="dark"
            position="top-right"
            toastOptions={{
              style: {
                background: "rgba(15,17,22,0.9)",
                border: "1px solid rgba(255,255,255,0.08)",
                color: "#E7ECF3",
                backdropFilter: "blur(18px)",
              },
            }}
          />
        </AuthProvider>
      </BrowserRouter>
    </div>
  );
}
