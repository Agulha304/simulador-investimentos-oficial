import { Suspense } from "react";
import { Link, Outlet } from "react-router-dom";
import { useAuth } from "../services/auth";

/** Moldura de fora da partida: logotipo à esquerda, conta no canto direito. */
export function HubLayout() {
  const { user, logout } = useAuth();
  return (
    <div className="hub-shell">
      <header className="hub-top">
        <Link to="/" className="logo"><span className="logo-mark" aria-hidden>🪙</span><span>Simula<b>Invest</b></span></Link>
        <div className="account">
          <div className="avatar big">{user?.name.slice(0, 1).toUpperCase()}</div>
          <div className="user-meta"><b>{user?.name}</b><small>{user?.email}</small></div>
          <Link to="/configuracoes" className="btn ghost small" title="Configurações da conta">⚙ Configurações</Link>
          <button className="btn ghost small" onClick={logout}>Sair</button>
        </div>
      </header>
      <main className="hub-main"><Suspense fallback={<div className="muted">Carregando…</div>}><Outlet /></Suspense></main>
    </div>
  );
}
