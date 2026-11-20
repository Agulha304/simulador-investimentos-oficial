import { useEffect, useState, type FormEvent } from "react";
import { api, type RankEntry, type Ranking, type RankingSettings } from "../services/api";
import { fmtBRL, fmtPct, trend } from "../lib/format";

const BOARDS = [{ id: "wealth", label: "Mais ricos" }, { id: "return", label: "Maior rentabilidade" }];
const PERIODS = [{ id: "all", label: "Geral" }, { id: "30d", label: "30 dias" }, { id: "7d", label: "7 dias" }];
const arrow = (v: string) => (Number(v) > 0 ? "▲ " : Number(v) < 0 ? "▼ " : "");

export function RankingPage() {
  const [board, setBoard] = useState("wealth");
  const [period, setPeriod] = useState("all");
  const [data, setData] = useState<Ranking | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setLoading(true); setError(null);
    api.ranking(board, period)
      .then((d) => { if (!cancelled) setData(d); })
      .catch((e: Error) => { if (!cancelled) setError(e.message); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [board, period]);

  const reload = () => api.ranking(board, period).then(setData).catch(() => undefined);
  const primary = (e: RankEntry) => (board === "wealth" ? fmtBRL(e.wealth_brl) : `${arrow(e.return_pct)}${fmtPct(e.return_pct)}`);
  const secondary = (e: RankEntry) => (board === "wealth" ? `${arrow(e.return_pct)}${fmtPct(e.return_pct)}` : fmtBRL(e.wealth_brl));

  return (
    <div className="page">
      <header className="page-head"><div><h1>Ranking</h1><p className="muted">Compare seus resultados com os de outros investidores do simulador.</p></div></header>
      {error && <div className="alert">{error}</div>}

      <div className="chart-toolbar">
        {BOARDS.map((b) => <button key={b.id} className={`tool${board === b.id ? " on" : ""}`} onClick={() => setBoard(b.id)}>{b.label}</button>)}
        <span className="grow" />
        {PERIODS.map((p) => <button key={p.id} className={`tool${period === p.id ? " on" : ""}`} onClick={() => setPeriod(p.id)}>{p.label}</button>)}
      </div>

      {!data ? <div className="muted">Carregando…</div> : (
        <div className={loading ? "dim" : ""}>
          {data.entries.length >= 3 && (
            <section className="podium" aria-label="Pódio">
              {[data.entries[1], data.entries[0], data.entries[2]].map((e) => (
                <div key={e.rank} className={`pod pod-${e.rank}${e.is_me ? " me" : ""}`}>
                  <span className="pod-rank">{e.rank}º</span>
                  <b>{e.nickname}{e.is_me && <span className="tag"> você</span>}</b>
                  <span className="num big">{primary(e)}</span>
                  <span className={`num small tone-${board === "wealth" ? trend(e.return_pct) : "flat"}`}>{secondary(e)}</span>
                </div>))}
            </section>
          )}

          {data.me && (
            <section className="card me-card">
              <div><span className="muted small">Sua posição</span><div className="big">{data.me.rank}º <span className="muted small">de {data.participants}</span></div></div>
              <div className="num">{primary(data.me)}<div className="muted small">{secondary(data.me)}</div></div>
            </section>
          )}
          {data.me_hidden && <div className="alert info">Você está oculto no ranking. Ative a opção abaixo para aparecer.</div>}

          {board === "wealth" && <div className="notice">🏆 O ranking de patrimônio só conta partidas do <b>modo ranqueado</b> (18 anos, R$ 1.800/mês num subemprego): todo mundo começa igual.</div>}
          <section className="card">
            {data.entries.length === 0 ? <div className="empty">Ninguém no ranking ainda.</div> : (
              <div className="table-wrap"><table>
                <thead><tr><th>#</th><th>Investidor</th><th className="r">{board === "wealth" ? "Patrimônio" : "Rentabilidade"}</th><th className="r">{board === "wealth" ? "Rentabilidade" : "Patrimônio"}</th><th className="r">Resultado</th></tr></thead>
                <tbody>{data.entries.map((e) => (
                  <tr key={e.rank} className={e.is_me ? "me-row" : ""}>
                    <td className="num">{e.rank}º</td>
                    <td><b>{e.nickname}</b>{e.is_me && <span className="tag"> você</span>}</td>
                    <td className="r num">{primary(e)}</td>
                    <td className={`r num tone-${board === "wealth" ? trend(e.return_pct) : "flat"}`}>{secondary(e)}</td>
                    <td className={`r num tone-${trend(e.gain_brl)}`}>{arrow(e.gain_brl)}{fmtBRL(e.gain_brl)}</td>
                  </tr>))}</tbody>
              </table></div>
            )}
            <p className="muted small">{data.note} {period !== "all" && "Nos períodos curtos, o resultado parte do último registro antes da janela (ou do primeiro, se o app ainda é novo)."}</p>
          </section>
        </div>
      )}
      <Settings onSaved={reload} />
    </div>
  );
}

function Settings({ onSaved }: { onSaved: () => void }) {
  const [s, setS] = useState<RankingSettings | null>(null);
  const [nick, setNick] = useState("");
  const [show, setShow] = useState(true);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => { api.rankingSettings().then((v) => { setS(v); setNick(v.nickname ?? ""); setShow(v.show_in_ranking); }).catch(() => undefined); }, []);

  async function save(e: FormEvent) {
    e.preventDefault(); setBusy(true); setMsg(null);
    try {
      const v = await api.saveRankingSettings(show, nick.trim() || null);
      setS(v); setMsg({ ok: true, text: "Preferências salvas." }); onSaved();
    } catch (err) { setMsg({ ok: false, text: err instanceof Error ? err.message : "Erro" }); }
    finally { setBusy(false); }
  }

  return (
    <form className="card inline-form" onSubmit={save}>
      <h2>Privacidade no ranking</h2>
      <p className="muted small">Os outros usuários veem só o apelido, nunca seu e-mail. Sem apelido, usamos <b>{s?.default_nickname ?? "…"}</b>.</p>
      <div className="row-gap">
        <input placeholder={s?.default_nickname ?? "Apelido"} value={nick} maxLength={24} onChange={(e) => setNick(e.target.value)} />
        <button className="btn primary" disabled={busy}>Salvar</button>
      </div>
      <label className="check"><input type="checkbox" checked={show} onChange={(e) => setShow(e.target.checked)} /> Aparecer no ranking</label>
      {msg && <div className={msg.ok ? "ok" : "alert"}>{msg.text}</div>}
    </form>
  );
}
