import { useEffect, useState, type FormEvent } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { api } from "../services/api";

export function ResetPasswordPage() {
  const [params] = useSearchParams();
  const token = params.get("token") ?? "";
  const navigate = useNavigate();
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!done) return;
    const t = setTimeout(() => navigate("/login", { replace: true }), 3000);
    return () => clearTimeout(t);
  }, [done, navigate]);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    if (password !== confirm) { setError("As senhas não conferem."); return; }
    setBusy(true);
    try {
      await api.resetPassword(token, password);
      setDone(true);
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
        <h1>Redefinir senha</h1>
        {!token ? (
          <div className="alert">Link inválido ou expirado. <Link to="/esqueci-senha">Peça um novo</Link>.</div>
        ) : done ? (
          <div className="alert info">Senha redefinida com sucesso! Redirecionando para o login…</div>
        ) : (
          <>
            <p className="muted">Escolha uma nova senha (8 a 72 caracteres).</p>
            <label>Nova senha
              <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} required minLength={8} maxLength={72} autoComplete="new-password" />
            </label>
            <label>Confirmar nova senha
              <input type="password" value={confirm} onChange={(e) => setConfirm(e.target.value)} required minLength={8} maxLength={72} autoComplete="new-password" />
            </label>
            {error && <div className="alert">{error}</div>}
            <button className="btn primary" disabled={busy}>{busy ? "Aguarde…" : "Redefinir senha"}</button>
          </>
        )}
        <p className="muted small center"><Link to="/login">Ir para o login</Link></p>
      </form>
    </div>
  );
}
