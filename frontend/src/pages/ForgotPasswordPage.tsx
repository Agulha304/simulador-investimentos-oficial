import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { api } from "../services/api";

export function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [sent, setSent] = useState(false);
  const [busy, setBusy] = useState(false);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      await api.forgotPassword(email);
      setSent(true);
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
        <h1>Esqueci minha senha</h1>
        {sent ? (
          <div className="alert info">Se o e-mail existir, enviaremos um link para redefinir a senha. O link vale por 1 hora; confira também a caixa de spam.</div>
        ) : (
          <>
            <p className="muted">Informe o e-mail da sua conta e enviaremos um link para criar uma nova senha.</p>
            <label>E-mail<input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required autoComplete="email" /></label>
            {error && <div className="alert">{error}</div>}
            <button className="btn primary" disabled={busy}>{busy ? "Aguarde…" : "Enviar link"}</button>
          </>
        )}
        <p className="muted small center"><Link to="/login">Voltar para o login</Link></p>
      </form>
    </div>
  );
}
