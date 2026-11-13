import { useState, type FormEvent } from "react";
import { Link, Navigate, useNavigate } from "react-router-dom";
import { useAuth } from "../services/auth";

export function AuthPage({ mode }: { mode: "login" | "register" }) {
  const { user, login, register } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  if (user) return <Navigate to="/" replace />;
  const isLogin = mode === "login";

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      if (isLogin) await login(email, password);
      else await register(email, name, password);
      navigate("/");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Erro inesperado");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="auth-wrap">
      <form className="card auth-card" onSubmit={onSubmit}>
        <div className="brand big"><span className="brand-mark">◆</span><span>Simula<b>Invest</b></span></div>
        <h1>{isLogin ? "Entrar" : "Criar conta"}</h1>
        <p className="muted">
          {isLogin ? "Acesse sua carteira simulada." : "Você começa com R$ 100.000,00 virtuais para praticar."}
        </p>
        {!isLogin && (
          <label>Nome<input value={name} onChange={(e) => setName(e.target.value)} required maxLength={120} /></label>
        )}
        <label>E-mail<input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required autoComplete="email" /></label>
        <label>Senha
          <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} required
            minLength={isLogin ? 1 : 8} maxLength={72} autoComplete={isLogin ? "current-password" : "new-password"} />
        </label>
        {error && <div className="alert">{error}</div>}
        <button className="btn primary" disabled={busy}>{busy ? "Aguarde…" : isLogin ? "Entrar" : "Criar conta"}</button>
        <p className="muted small center">
          {isLogin ? <>Não tem conta? <Link to="/cadastro">Cadastre-se</Link></> : <>Já tem conta? <Link to="/login">Entrar</Link></>}
        </p>
      </form>
    </div>
  );
}
