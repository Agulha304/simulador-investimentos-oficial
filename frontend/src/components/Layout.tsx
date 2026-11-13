import { NavLink, Outlet } from "react-router-dom";
import { useAuth } from "../services/auth";
import { SearchBar } from "./SearchBar";

const NAV = [
  { to: "/", label: "Dashboard", ready: true },
  { to: "/carteira", label: "Carteira", ready: true },
  { to: "/renda-fixa", label: "Renda Fixa", ready: false },
  { to: "/historico", label: "Histórico", ready: false },
];

export function Layout() {
  const { user, logout } = useAuth();
  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="brand">
          <span className="brand-mark" aria-hidden>◆</span>
          <span>Simula<b>Invest</b></span>
        </div>
        <nav>
          {NAV.map((n) =>
            n.ready ? (
              <NavLink key={n.to} to={n.to} end className={({ isActive }) => `nav-item${isActive ? " active" : ""}`}>
                {n.label}
              </NavLink>
            ) : (
              <span key={n.to} className="nav-item disabled" title="Disponível nas próximas fases">
                {n.label} <small>em breve</small>
              </span>
            ),
          )}
        </nav>
        <div className="sidebar-foot">
          <div className="user-chip">
            <div className="avatar">{user?.name.slice(0, 1).toUpperCase()}</div>
            <div className="user-meta">
              <span>{user?.name}</span>
              <small>{user?.email}</small>
            </div>
          </div>
          <button className="btn ghost small" onClick={logout}>Sair</button>
        </div>
      </aside>
      <main className="content">
        <div className="topbar">
          <SearchBar />
          <div className="sim-banner">Ambiente simulado — sem dinheiro real.</div>
        </div>
        <Outlet />
      </main>
    </div>
  );
}
