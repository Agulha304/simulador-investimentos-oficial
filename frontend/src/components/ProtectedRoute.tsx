import { Navigate, Outlet } from "react-router-dom";
import { useAuth } from "../services/auth";

export function ProtectedRoute() {
  const { user, loading } = useAuth();
  if (loading) return <div className="center-screen muted">Carregando…</div>;
  return user ? <Outlet /> : <Navigate to="/login" replace />;
}
