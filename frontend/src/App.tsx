import { lazy, Suspense } from "react";
import { BrowserRouter, Navigate, Route, Routes, useLocation } from "react-router-dom";
import ProtectedRoute from "./components/ProtectedRoute";

const AgentChat = lazy(() => import("./pages/AgentChat"));
const Analytics = lazy(() => import("./pages/Analytics"));
const Automation = lazy(() => import("./pages/Automation"));
const Dashboard = lazy(() => import("./pages/Dashboard"));
const Login = lazy(() => import("./pages/Login"));
const MediaLibrary = lazy(() => import("./pages/MediaLibrary"));
const PlatformAccounts = lazy(() => import("./pages/PlatformAccounts"));
const Publishing = lazy(() => import("./pages/Publishing"));
const Register = lazy(() => import("./pages/Register"));

function ContentRoute() {
  const { search } = useLocation();
  return new URLSearchParams(search).get("tab") === "media"
    ? <Navigate to="/media" replace />
    : <Navigate to="/agent" replace />;
}

export default function App() {
  return (
    <BrowserRouter future={{ v7_startTransition: true }}>
      <Suspense fallback={<div className="p-6 text-sm text-muted-foreground">页面加载中…</div>}>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route path="/register" element={<Register />} />
          <Route element={<ProtectedRoute />}>
            <Route path="/" element={<Dashboard />} />
            <Route path="/agent" element={<AgentChat />} />
            <Route path="/content" element={<ContentRoute />} />
            <Route path="/media" element={<MediaLibrary />} />
            <Route path="/accounts" element={<PlatformAccounts />} />
            <Route path="/analytics" element={<Analytics />} />
            <Route path="/automation" element={<Automation />} />
            <Route path="/publishing" element={<Publishing />} />
          </Route>
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </Suspense>
    </BrowserRouter>
  );
}
