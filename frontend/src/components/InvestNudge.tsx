import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { fmtBRL } from "../lib/format";
import { useApi } from "../services/dataCache";
import type { InvestPlan } from "../services/sim";

type Group = "renda-fixa" | "mercado" | "geral";
const groupOf = (path: string): Group => (path.startsWith("/renda-fixa") ? "renda-fixa" : path.startsWith("/mercado") || path.startsWith("/ativo") ? "mercado" : "geral");
const storeKey = (gameId: number, month: string, g: Group) => `invest-nudge:${gameId}:${month}:${g}`;
const readDismissed = (k: string) => { try { return localStorage.getItem(k) === "1"; } catch { return false; } };

/** Faixa dispensável nas telas de investir: lembra quanto ainda falta investir no mês, segundo a carteira-alvo. */
export function InvestNudge({ gameId, path }: { gameId: number; path: string }) {
  const { data } = useApi<InvestPlan>("/invest-plan");
  const n = data?.nudge;
  const group = groupOf(path);
  const key = n ? storeKey(gameId, n.month, group) : null;
  const [hidden, setHidden] = useState(false);
  useEffect(() => { setHidden(key ? readDismissed(key) : false); }, [key]);
  if (!n || !n.active || hidden) return null;

  const rem = (k: string) => Number(n.rows.find((r) => r.key === k)?.remaining ?? 0);
  const others = (): string => {
    const parts: [string, number][] = [["em ações", rem("STOCKS")], ["em FIIs", rem("FII")], ["em ETFs", rem("ETF")], ["em cripto", rem("CRYPTO")]];
    return parts.filter(([, v]) => v > 0).map(([l, v]) => `${fmtBRL(String(v))} ${l}`).join(" · ");
  };
  const fixed = rem("FIXED");
  const rest = others();
  let text: string | null = null;
  if (group === "renda-fixa") {
    text = fixed > 0 ? `Baseado na sua carteira-alvo, você deve investir mais ${fmtBRL(String(fixed))} em renda fixa este mês.`
      : rest ? `Você já cumpriu a parte de renda fixa; ainda faltam ${rest}.` : null;
  } else if (group === "mercado") {
    if (n.reserve_mode) text = "Este mês o foco é a sua reserva de emergência: invista em renda fixa.";
    else if (rest) text = `${fixed > 0 ? "Baseado na sua carteira-alvo, este mês você ainda deve investir" : "Você já cumpriu a parte de renda fixa; ainda faltam"}${fixed > 0 ? ": " : " "}${rest}`;
  } else {
    text = `Faltam ${fmtBRL(n.remaining)} do seu investimento planejado do mês.`;
  }
  if (!text) return null;
  const dismiss = () => { setHidden(true); try { if (key) localStorage.setItem(key, "1"); } catch { /* sem storage */ } };
  return (
    <div className="invest-nudge" role="status">
      <span aria-hidden>💡</span><span className="grow">{text}</span>
      <Link to="/orcamento" className="small">Ajustar plano</Link>
      <button className="link-btn" onClick={dismiss} aria-label="Dispensar aviso" title="Dispensar">×</button>
    </div>
  );
}
