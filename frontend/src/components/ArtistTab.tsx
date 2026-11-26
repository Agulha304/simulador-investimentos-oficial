import { useCallback, useEffect, useState } from "react";
import { Toast } from "./Toast";
import { fmtBRL } from "../lib/format";
import { sim, type ArtistAccount, type ArtistOffer, type ArtistView } from "../services/sim";

const errMsg = (e: unknown) => (e instanceof Error ? e.message : "Erro inesperado");
type Sub = "acting" | "music" | "painting" | "influencer";
const SUBS: [Sub, string][] = [["acting", "🎭 Ator"], ["music", "🎸 Músico"], ["painting", "🎨 Pintor"], ["influencer", "📱 Influenciador"]];
const n0 = (v: number) => v.toLocaleString("pt-BR");

/** Aba especial de artista: ator, músico, pintor e influenciador. */
export function ArtistTab() {
  const [v, setV] = useState<ArtistView | null>(null);
  const [sub, setSub] = useState<Sub>("acting");
  const [err, setErr] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => { sim.artist().then(setV).catch((e) => setErr(errMsg(e))); }, []);
  const run = useCallback(async (path: string, method: "POST" | "PUT" | "DELETE" = "POST", body?: unknown, msg?: string) => {
    setBusy(true); setErr(null); setNote(null);
    try { const r = await sim.artistDo(path, method, body); setV(r); setNote(r.result?.message ?? msg ?? null); }
    catch (e) { setErr(errMsg(e)); } finally { setBusy(false); }
  }, []);
  if (!v) return err ? <div className="alert">{err}</div> : <div className="muted">Carregando…</div>;
  const dec = v.decisions[0];
  return (
    <>
      {err && <div className="alert">{err}</div>}
      {note && <Toast text={note} onClose={() => setNote(null)} />}
      <section className="card stack">
        <div className="row-gap" style={{ flexWrap: "wrap" }}>
          {SUBS.map(([k, l]) => <span key={k} className="chip">{l}: habilidade <b>{v.skills[k === "influencer" ? "influencer" : k]}</b> · fama <b>{v.fame[k]}</b></span>)}
        </div>
        <span className="muted small">Tempo livre restante no mês: <b>{v.free_hours}h</b> · já comprometido todo mês com a arte: <b>{v.committed_hours}h</b>. Pagamentos entram no orçamento do mês seguinte; equipamentos, aulas e divulgação saem no mês da compra.</span>
      </section>
      <div className="seg compact tabs">{SUBS.map(([k, l]) => <button key={k} className={sub === k ? "on" : ""} onClick={() => setSub(k)}>{l}</button>)}</div>
      {sub !== "influencer" && <Train v={v} d={sub} busy={busy} run={run} />}
      {sub === "acting" && <Offers v={v} d="acting" busy={busy} run={run} empty="Sem testes abertos neste mês." />}
      {sub === "painting" && <Painter v={v} busy={busy} run={run} />}
      {sub === "music" && <Musician v={v} busy={busy} run={run} />}
      {sub === "influencer" && <Influencer v={v} busy={busy} run={run} />}
      {dec && (
        <div className="modal-back" role="dialog" aria-modal="true" aria-label="Decisão de divulgação">
          <div className="card modal">
            <h2>{dec.title}</h2>
            <p className="muted small">{dec.work === "EVENT" ? dec.desc : dec.work === "SONG" ? "Decida como divulgar. Gravadoras só aceitam músicas de qualidade e bandas com reputação." : "Decida como divulgar. Galerias e leilões dependem da qualidade e da sua fama."}</p>
            {dec.options.map((o) => (
              <div key={o.key} className="card stack" style={{ marginBottom: 8 }}>
                <b>{o.label}{o.cost ? ` — ${fmtBRL(String(o.cost))}` : ""}</b>{o.desc ? <span className="muted small">{o.desc}</span> : null}
                <div><button className="btn primary small" disabled={busy} onClick={() => void run(`/decisions/${dec.id}`, "POST", { option: o.key })}>Escolher</button></div>
              </div>))}
          </div>
        </div>)}
    </>
  );
}
type R = (path: string, method?: "POST" | "PUT" | "DELETE", body?: unknown, msg?: string) => Promise<void>;
type PV = { v: ArtistView; busy: boolean; run: R };

function Train({ v, d, busy, run }: PV & { d: Sub }) {
  const t = v.catalog.train[d];
  const [inst, setInst] = useState("geral");
  const spec = d === "music" && inst !== "geral";
  return (
    <section className="card stack">
      <div className="row between">
        <span><b>{spec ? `Aulas de ${v.catalog.instruments.find((i) => i.key === inst)?.name}` : d === "music" ? "Aulas de música (gerais)" : t.name}</b> — {fmtBRL(String(spec ? 520 : t.cost))}/mês, {spec ? 18 : t.hours}h: melhora a sua habilidade{spec ? " nesse instrumento (mais currículo nele)" : d === "music" ? " em música (vale um pouco para todos os instrumentos)" : ""}.</span>
        <span className="row-gap">
          {d === "music" && <select value={inst} onChange={(e) => setInst(e.target.value)} aria-label="Tipo de aula">
            <option value="geral">Aula geral de música</option>{v.catalog.instruments.map((i) => <option key={i.key} value={i.key}>Aula de {i.name}{v.inst_skills[i.key] ? ` (hab. ${v.inst_skills[i.key]})` : ""}</option>)}</select>}
          <button className="btn small" disabled={busy} onClick={() => void run("/train", "POST", { discipline: d, instrument: d === "music" ? inst : undefined })}>Treinar</button>
        </span>
      </div>
      {d === "music" && <span className="muted small">Habilidade efetiva no seu instrumento: <b>{v.effective_music}</b> (aulas específicas do instrumento valem mais no currículo para vagas com ele).</span>}
    </section>
  );
}

function Offers({ v, d, busy, run, empty }: PV & { d: "acting" | "music" | "painting"; empty: string }) {
  const list = v.offers[d];
  const jobs = v.jobs.filter((j) => j.discipline === d);
  return (
    <>
      <h3>{d === "acting" ? "Testes e vagas de atuação" : d === "music" ? "Vagas para músicos" : "Encomendas"}</h3>
      {list.length === 0 ? <p className="muted">{empty}</p> : <div className="cols-2">{list.map((o: ArtistOffer) => (
        <div key={o.key} className="card stack">
          <div className="row between"><b>{o.title}</b><span className="chip">{o.monthly ? `${fmtBRL(String(o.pay))}/mês × ${o.months}` : fmtBRL(String(o.pay))}</span></div>
          <span className="muted small">{o.employer} · pede habilidade ~{o.need_skill}{o.need_fame ? ` e fama ~${o.need_fame}` : ""}{o.hours ? ` · ${o.hours}h/mês` : ""}</span>
          <span className="small">Chance: <b>{o.chance}%</b></span>
          <div><button className="btn primary small" disabled={busy || v.applied.includes(o.key)} onClick={() => void run("/apply", "POST", { discipline: d, offer_key: o.key })}>{v.applied.includes(o.key) ? "Candidatura feita" : o.callback_id ? "Aceitar convite" : "Candidatar-me"}</button></div>
        </div>))}</div>}
      {jobs.length > 0 && <><h3>Meus contratos</h3><ul className="list-plain">{jobs.map((j) => (
        <li key={j.id}><span>{j.title} — {j.employer} · {j.pay_type === "MONTHLY" ? `${fmtBRL(String(j.pay))}/mês até ${j.end.slice(0, 7)}` : `${fmtBRL(String(j.pay))} (um serviço)`}</span>
          {j.status === "ACTIVE" ? <button className="btn danger small" disabled={busy} onClick={() => void run(`/jobs/${j.id}`, "DELETE")}>Sair</button> : <span className="chip">{j.status === "DONE" ? "concluído" : j.status}</span>}</li>))}</ul></>}
    </>
  );
}

function Painter({ v, busy, run }: PV) {
  const [theme, setTheme] = useState("paisagem"), [style, setStyle] = useState("realismo"), [size, setSize] = useState("pequeno");
  const paintings = v.works.filter((w) => w.work === "PAINTING");
  const sz = v.catalog.paint_sizes.find((s) => s.key === size);
  return (
    <>
      <Offers v={v} d="painting" busy={busy} run={run} empty="Sem encomendas neste mês." />
      <section className="card stack">
        <h3>🖌️ Pintar um quadro</h3>
        <div className="row-gap" style={{ flexWrap: "wrap" }}>
          <label>Tema<select value={theme} onChange={(e) => setTheme(e.target.value)}>{v.catalog.paint_themes.map((x) => <option key={x.key} value={x.key}>{x.name}</option>)}</select></label>
          <label>Estilo<select value={style} onChange={(e) => setStyle(e.target.value)}>{v.catalog.paint_styles.map((x) => <option key={x.key} value={x.key}>{x.name}</option>)}</select></label>
          <label>Tamanho<select value={size} onChange={(e) => setSize(e.target.value)}>{v.catalog.paint_sizes.map((x) => <option key={x.key} value={x.key}>{x.name}</option>)}</select></label>
        </div>
        <span className="muted small">Material {fmtBRL(String(sz?.material ?? 0))} · {sz?.hours}h do seu tempo livre. Ao terminar, você decide como divulgar o quadro.</span>
        <div><button className="btn primary" disabled={busy} onClick={() => void run("/painting", "POST", { theme, style, size })}>Pintar</button></div>
      </section>
      {paintings.length > 0 && <><h3>Meus quadros</h3><ul className="list-plain">{paintings.map((w) => <li key={w.id}><span>{w.name} · qualidade {w.quality}</span><span className="chip">{w.status === "SOLD" ? "vendido/divulgado" : w.status === "UNSOLD" ? "não vendeu" : "aguardando divulgação"}</span></li>)}</ul></>}
    </>
  );
}

function Musician({ v, busy, run }: PV) {
  const [bandName, setBandName] = useState(""), [style, setStyle] = useState("rock"), [theme, setTheme] = useState("amor"), [scope, setScope] = useState<"BAND" | "SOLO">(v.band ? "BAND" : "SOLO");
  const works = v.works.filter((w) => w.work === "SONG" || w.work === "ALBUM");
  return (
    <>
      <section className="card stack">
        <h3>🎼 Instrumento dominante</h3>
        <div className="row-gap" style={{ flexWrap: "wrap" }}>
          <select value={v.instrument ?? ""} onChange={(e) => e.target.value && void run("/instrument", "POST", { instrument: e.target.value })} disabled={busy}>
            <option value="">Escolha…</option>{v.catalog.instruments.map((i) => <option key={i.key} value={i.key}>{i.name} (procura {i.demand.toFixed(2)}×)</option>)}</select>
          <span className="muted small">Instrumentos com mais procura recebem mais convites; trocar de instrumento custa parte da prática.</span>
        </div>
      </section>
      {v.instrument && <Offers v={v} d="music" busy={busy} run={run} empty="Ninguém procura o seu instrumento neste mês." />}
      <section className="card stack">
        <h3>🎤 Banda</h3>
        {!v.band ? (
          <div className="row-gap" style={{ flexWrap: "wrap" }}>
            <input placeholder="Nome da banda" value={bandName} onChange={(e) => setBandName(e.target.value)} />
            <select value={style} onChange={(e) => setStyle(e.target.value)}>{v.catalog.styles.map((s) => <option key={s.key} value={s.key}>{s.name}</option>)}</select>
            <button className="btn primary small" disabled={busy || !v.instrument || !bandName.trim()} onClick={() => void run("/band", "POST", { name: bandName, style })}>Abrir banda</button>
          </div>
        ) : (
          <>
            <div className="row between"><b>{v.band.name} · {v.band.style_name}</b><span className="chip">reputação {v.band.reputation} · qualidade {v.band.quality}</span></div>
            <ul className="list-plain">{v.band.members.map((m, i) => <li key={i}><span>{m.name} — {v.catalog.instruments.find((x) => x.key === m.instrument)?.name ?? m.instrument}</span><span className="muted small">habilidade {m.skill}</span></li>)}</ul>
            <span className="muted small">{v.band.gigs} shows · {v.band.songs} músicas. Chame músicos do mercado ou conhecidos seus (eles podem recusar).</span>
            <div className="cols-2">
              <div><b className="small">Músicos do mercado</b>{v.market_musicians.map((m) => <div key={m.key} className="row between small"><span>{m.name} · {v.catalog.instruments.find((x) => x.key === m.instrument)?.name} · hab. {m.skill}</span><button className="btn small" disabled={busy} onClick={() => void run("/band/recruit", "POST", { key: m.key })}>Convidar</button></div>)}</div>
              <div><b className="small">Conhecidos seus</b>{v.friend_musicians.length === 0 ? <p className="muted small">Nenhum conhecido toca.</p> : v.friend_musicians.map((m) => <div key={m.key} className="row between small"><span>{m.name} · {v.catalog.instruments.find((x) => x.key === m.instrument)?.name} · hab. {m.skill}</span><button className="btn small" disabled={busy} onClick={() => void run("/band/recruit", "POST", { key: m.key })}>Chamar</button></div>)}</div>
            </div>
            <button className="btn danger small" disabled={busy} onClick={() => window.confirm("Encerrar a banda?") && void run("/band", "DELETE")}>Encerrar a banda</button>
          </>)}
      </section>
      {v.instrument && (
        <section className="card stack">
          <h3>🎵 Criar música e álbum</h3>
          <div className="row-gap" style={{ flexWrap: "wrap" }}>
            <label>Em nome de<select value={scope} onChange={(e) => setScope(e.target.value as "BAND" | "SOLO")}><option value="BAND" disabled={!v.band}>Banda</option><option value="SOLO">Carreira solo</option></select></label>
            <label>Estilo<select value={style} onChange={(e) => setStyle(e.target.value)}>{v.catalog.styles.map((s) => <option key={s.key} value={s.key}>{s.name}</option>)}</select></label>
            <label>Tema<select value={theme} onChange={(e) => setTheme(e.target.value)}>{v.catalog.themes.map((s) => <option key={s.key} value={s.key}>{s.name}</option>)}</select></label>
            <button className="btn primary small" disabled={busy} onClick={() => void run("/song", "POST", { scope, style, theme })}>Compor (12h)</button>
            <button className="btn small" disabled={busy} onClick={() => void run("/album", "POST", { scope, mode: "INDIE" })}>Álbum independente (R$ 14 mil)</button>
            <button className="btn small ghost" disabled={busy} onClick={() => void run("/album", "POST", { scope, mode: "LABEL" })}>Álbum pela gravadora</button>
          </div>
          <span className="muted small">Compor pode não dar em nada. Quando sai uma música, você decide como divulgá-la (gravadora, streaming, clipe, rádio…). Álbum exige 6 músicas.</span>
          <h4>Oferecer-se para tocar</h4>
          <div className="row-gap" style={{ flexWrap: "wrap" }}>{v.catalog.venues.map((x) => (
            <button key={x.key} className="btn small" disabled={busy} title={`Reputação mínima ${x.need_rep}; cachê ${fmtBRL(String(x.min))} a ${fmtBRL(String(x.max))}`} onClick={() => void run("/gig", "POST", { tier: x.key, scope })}>{x.name}</button>))}</div>
        </section>)}
      {works.length > 0 && <><h3>Minhas músicas e álbuns</h3><ul className="list-plain">{works.map((w) => <li key={w.id}><span>{w.name} · {w.work === "ALBUM" ? "álbum" : w.scope === "BAND" ? "banda" : "solo"} · qualidade {w.quality}</span><span className="chip">{w.status === "PUBLISHED" ? `royalties ~${fmtBRL(String(w.royalty ?? 0))}/mês` : w.status === "UNPROMOTED" ? "engavetada" : "aguardando divulgação"}</span></li>)}</ul></>}
    </>
  );
}

function Influencer({ v, busy, run }: PV) {
  const inf = v.influencer;
  const [name, setName] = useState(""), [niche, setNiche] = useState("games");
  const [plats, setPlats] = useState<string[]>(["youtube"]);
  const toggle = (k: string) => setPlats((p) => (p.includes(k) ? p.filter((x) => x !== k) : [...p, k]));
  return (
    <>
      <section className="card stack">
        <h3>📱 Criar uma conta de criador</h3>
        <p className="muted small" style={{ margin: 0 }}>Uma conta é um tema/nicho (ex.: games, tecnologia) e pode ter canais em várias plataformas. Você pode ter até {v.catalog.max_accounts} contas, cada uma com seu equipamento, público e investimentos.</p>
        <div className="row-gap" style={{ flexWrap: "wrap" }}>
          <input placeholder="Nome da conta" value={name} onChange={(e) => setName(e.target.value)} />
          <select value={niche} onChange={(e) => setNiche(e.target.value)}>{v.catalog.niches.map((p) => <option key={p.key} value={p.key}>{p.name} (concorrência {p.competition.toFixed(1)})</option>)}</select>
        </div>
        <div className="row-gap" style={{ flexWrap: "wrap" }}>{v.catalog.platforms.map((p) => (
          <label key={p.key} className="check"><input type="checkbox" checked={plats.includes(p.key)} onChange={() => toggle(p.key)} />{p.name}</label>))}</div>
        <div><button className="btn primary small" disabled={busy || !name.trim() || plats.length === 0} onClick={() => void run("/accounts", "POST", { name, niche, platforms: plats })}>Criar conta</button></div>
      </section>
      {inf.accounts.map((a) => <Account key={a.id} a={a} v={v} busy={busy} run={run} />)}
    </>
  );
}

function Account({ a, v, busy, run }: PV & { a: ArtistAccount }) {
  const inf = v.influencer;
  const [sel, setSel] = useState<string[]>(a.channels.map((c) => c.platform));
  const [topic, setTopic] = useState("conteudo");
  const [ref, setRef] = useState<number | "">("");
  const used = new Set(a.channels.map((c) => c.platform));
  const refs = topic === "painting" ? inf.promotable.painting : topic === "song" ? inf.promotable.song : topic === "play" ? inf.promotable.play : topic === "company" ? inf.promotable.company : [];
  const chosen = sel.filter((p) => used.has(p));
  return (
    <section className="card stack">
      <div className="row between"><h3>{a.name} · {a.niche_name}</h3>
        <button className="btn danger small" disabled={busy} onClick={() => window.confirm("Encerrar a conta e todos os canais?") && void run(`/accounts/${a.id}`, "DELETE")}>Encerrar conta</button></div>
      <div className="stats-grid">
        <div className="card"><span className="muted small">Qualidade dos vídeos</span><b className="num">{a.quality}</b></div>
        <div className="card"><span className="muted small">Comunidade</span><b className="num">{a.community}</b></div>
        <div className="card"><span className="muted small">Tendência do nicho</span><b className="num">{a.trend.toFixed(2)}×</b></div>
      </div>
      <b className="small">Canais desta conta</b>
      <div className="table-wrap"><table>
        <thead><tr><th>Plataforma</th><th className="r">Inscritos</th><th className="r">Views (mês)</th><th className="r">Receita</th><th>Monetização</th><th></th></tr></thead>
        <tbody>{a.channels.map((c) => (
          <tr key={c.id}><td>{c.platform_name}{c.posted ? ` · ${c.posted} vídeo(s) no mês` : ""}</td><td className="r num">{n0(c.subs)}</td><td className="r num">{n0(c.views)}</td><td className="r num">{fmtBRL(String(c.income))}</td>
            <td>{c.tier ? <span className="chip up">{c.tier.label}</span> : c.next ? <span className="muted small">Meta: {c.next.label} — falta {c.next.missing.map((m) => `${m.need} (${n0(Math.round(m.have))}/${n0(m.goal)})`).join("; ")}</span> : null}</td>
            <td><button className="link-btn" disabled={busy} onClick={() => window.confirm("Encerrar este canal?") && void run(`/channels/${c.id}`, "DELETE")}>encerrar</button></td></tr>))}</tbody>
      </table></div>
      <div className="row-gap" style={{ flexWrap: "wrap" }}>
        <span className="muted small">Adicionar canal:</span>
        {v.catalog.platforms.filter((p) => !used.has(p.key)).map((p) => <button key={p.key} className="btn small ghost" disabled={busy} onClick={() => void run(`/accounts/${a.id}/channels`, "POST", { platform: p.key })}>+ {p.name}</button>)}
      </div>
      <h4>🎬 Criar um vídeo</h4>
      <div className="row-gap" style={{ flexWrap: "wrap" }}>
        <span className="muted small">Postar em:</span>
        {a.channels.map((c) => <label key={c.id} className="check"><input type="checkbox" checked={sel.includes(c.platform)} onChange={() => setSel((s) => (s.includes(c.platform) ? s.filter((x) => x !== c.platform) : [...s, c.platform]))} />{c.platform_name}</label>)}
        <button type="button" className="link-btn" onClick={() => setSel(a.channels.map((c) => c.platform))}>todas</button>
      </div>
      <div className="row-gap" style={{ flexWrap: "wrap" }}>
        <label>Tema<select value={topic} onChange={(e) => { setTopic(e.target.value); setRef(""); }}>{inf.topics.map((t) => <option key={t.key} value={t.key}>{t.name}</option>)}</select></label>
        {topic !== "conteudo" && <label>O que divulgar<select value={ref} onChange={(e) => setRef(Number(e.target.value))}><option value="">Escolha…</option>{refs.map((r) => <option key={r.id} value={r.id}>{r.name}</option>)}</select></label>}
        <button className="btn primary small" disabled={busy || chosen.length === 0 || (topic !== "conteudo" && !ref)}
          onClick={() => void run(`/accounts/${a.id}/video`, "POST", { platforms: chosen, topic, ref_id: topic === "conteudo" ? undefined : Number(ref) })}>Gravar e publicar ({a.hours_per_video + Math.round(1.5 * Math.max(0, chosen.length - 1))}h)</button>
      </div>
      <span className="muted small">Vídeos temáticos podem vender o que você divulga e atrair inscritos, mas se o assunto não combina com o nicho do canal ele pode vender pouco e afastar parte do público. Quanto mais vídeos no mês, mais visualizações.</span>
      {a.sponsors.length > 0 && <>
        <h4>🤝 Propostas de publi</h4>
        <div className="cols-2">{a.sponsors.map((o) => (
          <div key={o.key} className="card stack">
            <div className="row between"><b>{o.brand}</b><span className="chip">{fmtBRL(String(o.pay))}</span></div>
            <span className="muted small">{o.category} · encaixe com o seu nicho {Math.round(o.fit * 100)}% · efeito esperado no público {o.subs_effect_pct > 0 ? "+" : ""}{o.subs_effect_pct}%</span>
            {o.warning && <span className="small" style={{ color: "#ffd23f" }}>⚠ {o.warning}</span>}
            <div><button className="btn small primary" disabled={busy} onClick={() => void run(`/accounts/${a.id}/sponsor`, "POST", { offer_key: o.key })}>Aceitar publi (8h)</button></div>
          </div>))}</div></>}
      <b className="small">Equipamento (vale para todos os canais da conta)</b>
      <div className="goods-grid">{v.catalog.gear.map((g) => { const lvl = a.gear[g.key] ?? 0; return (
        <div key={g.key} className="card good-card"><b>{g.name}</b><span className="muted small">{v.catalog.gear_levels[lvl]}</span>
          <button className="btn small" disabled={busy || lvl >= 5} onClick={() => void run(`/accounts/${a.id}/gear`, "POST", { category: g.key })}>{lvl >= 5 ? "Máximo" : `Melhorar — ${fmtBRL(String(g.prices[lvl]))}`}</button></div>); })}</div>
      <b className="small">Investimentos na conta</b>
      <div className="goods-grid">{v.catalog.invest.map((i) => { const on = a.flags[i.key] ?? false; return (
        <div key={i.key} className="card good-card"><b>{i.name}</b><span className="muted small">{i.desc}</span>
          {on && i.type !== "ONCE" && i.key !== "merch" ? <button className="btn ghost small" disabled={busy} onClick={() => void run(`/accounts/${a.id}/invest/${i.key}`, "DELETE")}>Desligar</button>
            : <button className="btn small" disabled={busy || (on && (i.type === "ONCE" || i.key === "merch"))} onClick={() => void run(`/accounts/${a.id}/invest`, "POST", { kind: i.key })}>{on ? "Ativo" : i.type === "ONCE" ? `Fazer — ${fmtBRL(String(i.cost))}` : i.type === "COMMISSION" ? "Contratar" : `Contratar — ${fmtBRL(String(i.cost))}/mês`}</button>}</div>); })}</div>
    </section>
  );
}
