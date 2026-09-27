import { Navigate, Outlet } from "react-router-dom";
import { useAuthStore } from "../stores/auth";

export default function ProtectedRoute() {
  const accessToken = useAuthStore((s) => s.accessToken);
  if (!accessToken) {
    return <Navigate to="/login" replace />;
  }
  return <Outlet />;
}
