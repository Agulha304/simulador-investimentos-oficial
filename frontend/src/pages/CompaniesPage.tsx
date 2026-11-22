import { useEffect, useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { StatCard } from "../components/StatCard";
import { type Life, type Rel } from "../services/sim";
import { useApi } from "../services/dataCache";
import { api, type CoCatalog, type CoChannel, type CoOverview, type CoQuote, type CoSegment, type CoSiteMode, type Company } from "../services/api";
import { fmtBRL, parseMoneyInput, trend } from "../lib/format";

const errMsg = (e: unknown) => (e instanceof Error ? e.message : "Erro inesperado");
type Tab = "overview" | "mine" | "market";

export function CompaniesPage() {
  const nav = useNavigate();
  const [tab, setTab] = useState<Tab>("overview");
  const [creating, setCreating] = useState<CoSegment | null>(null);
  const { data: ov, error: ovErr } = useApi<CoOverview>("/companies/overview");
  const { data: catalog, error: catErr } = useApi<CoCatalog>("/companies/catalog");
  const error = ovErr ?? catErr;

  if (error && !ov) return <div className="alert">Não foi possível carregar as empresas: {error}</div>;
  if (!ov || !catalog) return <div className="muted">Carregando empresas…</div>;

  return (
    <div className="page">
      <header className="page-head">
        <div><h1>Empresas</h1><p className="muted">Cada empresa tem conta, estoque e resultados próprios. O dinheiro dela não é seu dinheiro pessoal até você retirar lucros.</p></div>
        <button className="btn primary" onClick={() => setTab("market")}>+ Abrir empresa</button>
      </header>
      {error && <div className="alert">{error}</div>}
      <div className="seg compact tabs">
        <button className={tab === "overview" ? "on" : ""} onClick={() => setTab("overview")}>Visão geral</button>
        <button className={tab === "mine" ? "on" : ""} onClick={() => setTab("mine")}>Minhas empresas ({ov.count})</button>
        <button className={tab === "market" ? "on" : ""} onClick={() => setTab("market")}>Mercado de negócios</button>
      </div>

      {tab === "overview" && (
        <>
          <section className="stats-grid">
            <StatCard label="Empresas ativas" value={ov.count} emphasis />
            <StatCard label="Patrimônio empresarial" value={fmtBRL(ov.equity_total)} sub={`sua participação ${fmtBRL(ov.equity_user_share)}`} />
            <StatCard label="Caixa empresarial total" value={fmtBRL(ov.cash_total)} />
            <StatCard label="Dívidas empresariais" value={fmtBRL(ov.debts_total)} />
            <StatCard label="Receita do último mês" value={fmtBRL(ov.revenue_last_month)} tone="up" />
            <StatCard label="Despesas do último mês" value={fmtBRL(ov.expenses_last_month)} />
            <StatCard label="Lucro / prejuízo agregado" value={fmtBRL(ov.net_last_month)} tone={trend(ov.net_last_month)} sub="último mês fechado" />
          </section>
          <CompanyTable companies={ov.companies} onOpen={(id) => nav(`/empresas/${id}`)} />
        </>
      )}
      {tab === "mine" && <CompanyTable companies={ov.companies} onOpen={(id) => nav(`/empresas/${id}`)} />}
      {tab === "market" && (
        <section className="card">
          <h2>Mercado de negócios</h2>
          <p className="muted small">Escolha o segmento. Cada um tem demanda, estoque, equipe e custos próprios, e nenhum garante lucro.</p>
          <div className="goods-grid">{catalog.segments.map((s) => (
            <div key={s.key} className="card good-card">
              <b>{s.label}</b>
              <span className="muted small">{s.description}</span>
              <span className="muted small">Vende por {s.unit_label} · preço padrão {fmtBRL(s.price)}</span>
              <span className="muted small">Impostos: {s.tax.regime_label}, alíquota efetiva de {s.tax.effective_min_pct}% a {s.tax.effective_max_pct}% conforme o faturamento dos últimos 12 meses{s.tax.mei_allowed ? " · pode começar como MEI (até R$ 81 mil/ano e 1 empregado)" : " · não pode ser MEI"}</span>
              <span className="muted small">Equipe: {s.roles.map((r) => r.label).join(", ")}{s.stock.length ? ` · Estoque: ${s.stock.join(", ")}` : " · sem estoque (serviço)"}</span>
              <span className="num good-value">a partir de {fmtBRL(s.minimum_capital)} · {s.channels.length > 1 ? "online ou física" : s.channels[0] === "ONLINE" ? "só online" : "só física"}</span>
              <button className="btn small primary" onClick={() => setCreating(s)}>Criar empresa</button>
            </div>
          ))}</div>
        </section>
      )}
      {creating && <CreateModal segment={creating} catalog={catalog} onClose={() => setCreating(null)} onCreated={(id) => nav(`/empresas/${id}`)} />}
    </div>
  );
}

function CompanyTable({ companies, onOpen }: { companies: Company[]; onOpen: (id: number) => void }) {
  return (
    <section className="card">
      <h2>Minhas empresas</h2>
      {companies.length === 0 ? <div className="empty">Você ainda não tem empresas. Veja o Mercado de negócios.</div> : (
        <div className="table-wrap"><table>
          <thead><tr><th>Empresa</th><th>Setor</th><th>Situação</th><th className="r">Receita</th><th className="r">Resultado</th><th className="r">Caixa</th><th /></tr></thead>
          <tbody>{companies.map((c) => (
            <tr key={c.id}>
              <td><b>{c.name}</b> <span className="muted small">{c.location_label}</span></td>
              <td>{c.segment_label}</td>
              <td><span className="tag">{c.status === "ACTIVE" ? "Ativa" : "Encerrada"}</span> <span className="muted small">reputação {c.reputation}</span></td>
              <td className="r num">{c.last_revenue ? fmtBRL(c.last_revenue) : "—"}</td>
              <td className={`r num tone-${trend(c.last_net_result)}`}>{c.last_net_result ? `${Number(c.last_net_result) >= 0 ? "▲ " : "▼ "}${fmtBRL(c.last_net_result)}` : "—"}</td>
              <td className={`r num ${Number(c.cash) < 0 ? "tone-down" : ""}`}>{fmtBRL(c.cash)}</td>
              <td className="r"><button className="link-btn" onClick={() => onOpen(c.id)}>abrir</button></td>
            </tr>
          ))}</tbody>
        </table></div>
      )}
    </section>
  );
}

function CreateModal({ segment, catalog, onClose, onCreated }: { segment: CoSegment; catalog: CoCatalog; onClose: () => void; onCreated: (id: number) => void }) {
  const [name, setName] = useState("");
  const [channel, setChannel] = useState<CoChannel>(segment.channels.includes("PHYSICAL") ? "PHYSICAL" : "ONLINE");
  const [siteMode, setSiteMode] = useState<CoSiteMode>("RENT");
  const [location, setLocation] = useState(segment.default_location);
  const [size, setSize] = useState("SMALL");
  const [extra, setExtra] = useState("0");
  const [share, setShare] = useState("100");
  const [quote, setQuote] = useState<CoQuote | null>(null);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [friends, setFriends] = useState<Rel[]>([]);
  const [shares, setShares] = useState<Record<number, string>>({});
  const [invites, setInvites] = useState<Record<number, { id: number; accepted: boolean; message: string; share: string }>>({});
  const { data: life } = useApi<Life>("/life"); // mesmo /life da tela Vida (cache compartilhado)
  useEffect(() => { if (life) setFriends(life.relationships.filter((r) => r.stage !== "ENDED")); }, [life]);
  const accepted = Object.values(invites).filter((i) => i.accepted);
  const partnersShare = accepted.reduce((a, i) => a + Number(i.share), 0);
  const ownerShare = accepted.length ? String(100 - partnersShare) : (share || "100");
  const physical = channel === "PHYSICAL";
  const extraValue = parseMoneyInput(extra) || "0";
  async function invite(r: Rel) {
    setMsg(null);
    try {
      // o convite combina o teto de capital do sócio: usamos o mínimo para abrir (a parte dele é % do mínimo)
      const res = await api.coInvitePartner(r.person_id, shares[r.person_id] || "20", String(Math.ceil(Number(quote?.minimum_capital ?? 0)) || 1));
      setInvites((p) => ({ ...p, [r.person_id]: { id: res.id, accepted: res.accepted, message: res.message, share: res.share_pct } }));
    } catch (err) { setMsg(errMsg(err)); }
  }

  useEffect(() => {
    let live = true;
    api.coQuote({ segment: segment.key, channel, site_mode: physical ? siteMode : undefined, location: physical ? location : undefined, size, extra_capital: extraValue, owner_share_pct: ownerShare })
      .then((q) => { if (live) { setQuote(q); setMsg(null); } }).catch((e) => { if (live) setMsg(errMsg(e)); });
    return () => { live = false; };
  }, [segment.key, channel, siteMode, location, size, extraValue, ownerShare, physical]);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true); setMsg(null);
    try {
      const d = await api.coCreate({ name, segment: segment.key, channel, site_mode: physical ? siteMode : undefined, location: physical ? location : undefined, size, extra_capital: extraValue, owner_share_pct: accepted.length ? "100" : (share || "100"), partner_invite_ids: accepted.map((i) => i.id) });
      onCreated(d.company.id);
    } catch (err) { setMsg(errMsg(err)); setBusy(false); }
  }

  return (
    <div className="modal-back" onMouseDown={onClose}>
      <form className="card modal" onMouseDown={(e) => e.stopPropagation()} onSubmit={submit}>
        <div className="row"><h2>Abrir {segment.label.toLowerCase()}</h2><button type="button" className="link-btn" onClick={onClose}>fechar ✕</button></div>
        <label>Nome da empresa<input value={name} onChange={(e) => setName(e.target.value)} maxLength={80} required /></label>
        {segment.channels.length > 1 ? (
          <label>Canal de venda<select value={channel} onChange={(e) => setChannel(e.target.value as CoChannel)}>
            <option value="PHYSICAL">Física (ponto comercial)</option><option value="ONLINE">Online</option></select></label>
        ) : <p className="muted small" style={{ margin: 0 }}>Canal: <b>{channel === "ONLINE" ? "Online" : "Física"}</b> (único permitido para este negócio)</p>}
        {physical && (
          <>
            <label>Terreno / ponto<select value={siteMode} onChange={(e) => setSiteMode(e.target.value as CoSiteMode)}>
              <option value="RENT">Alugar (aluguel mensal)</option><option value="BUY">Comprar o terreno (sem aluguel)</option></select></label>
            <label>Localização<select value={location} onChange={(e) => setLocation(e.target.value)}>
              {segment.locations.map((l) => <option key={l.key} value={l.key}>{l.label}</option>)}</select></label>
          </>
        )}
        <div className="alert" style={{ margin: 0 }}>A empresa nasce <b>sem funcionários</b>. <b>Contador e Advogado são obrigatórios{physical ? " (e Auxiliar de limpeza, por ser física)" : ""}</b>: sem eles a empresa fica irregular, não vende e paga multa no mês. O capital mínimo já inclui um mês de folha deles; contrate depois de abrir. Quem produz (cozinheiros, vendedores…) você contrata conforme a demanda — sem equipe produtiva só o dono produz.</div>
        {!physical && <p className="muted small" style={{ margin: 0 }}>Online: sem aluguel nem terreno, custos fixos menores e alcance digital no lugar da demanda local.</p>}
        <label>Porte inicial<select value={size} onChange={(e) => setSize(e.target.value)}>{catalog.sizes.map((s) => <option key={s.key} value={s.key}>{s.label}</option>)}</select></label>
        {quote && (
          <dl className="facts">
            <div><dt>Estruturação (abertura, licenças, reforma)</dt><dd className="num">{fmtBRL(quote.setup_cost)}</dd></div>
            {segment.metrics_kind !== "SERVICE" && <div><dt>Estoque inicial</dt><dd className="num">{fmtBRL(quote.initial_stock)}</dd></div>}
            {physical && siteMode === "BUY" && <div><dt>Terreno (vira patrimônio da empresa)</dt><dd className="num">{fmtBRL(quote.land_cost)}</dd></div>}
            <div><dt>Folha mensal dos cargos obrigatórios ({quote.mandatory_roles.join(", ")}) — CLT custa 2× o salário</dt><dd className="num">{fmtBRL(quote.monthly_payroll)}</dd></div>
            <div><dt>Equipe obrigatória no capital mínimo (1 mês de folha + custo de contratação)</dt><dd className="num">{fmtBRL(quote.mandatory_cost)}</dd></div>
            <div><dt>Custos fixos mensais{physical && siteMode === "RENT" ? " (aluguel e outros)" : ""}</dt><dd className="num">{fmtBRL(quote.monthly_fixed)}</dd></div>
            <div><dt>Capital mínimo para abrir</dt><dd className="num"><b>{fmtBRL(quote.minimum_capital)}</b></dd></div>
            {quote.tax && <div><dt>Regime tributário provável</dt><dd>{quote.tax.regime_label}, alíquota efetiva de {quote.tax.effective_min_pct}% a {quote.tax.effective_max_pct}% conforme o faturamento dos últimos 12 meses (o regime muda sozinho: MEI até R$ 81 mil/ano, Simples até R$ 4,8 mi, depois Lucro Presumido). Simplificações: ICMS 18%, IPI 10% e ISS típico; encargos da folha já estão no custo CLT de 2×.</dd></div>}
          </dl>
        )}
        {accepted.length === 0 && <label>Sua participação societária (%)<input inputMode="decimal" value={share} onChange={(e) => setShare(e.target.value)} /></label>}
        <label>Capital adicional a aportar (R$) — dinheiro a mais além do mínimo para abrir que você investirá na empresa<input inputMode="decimal" value={extra} onChange={(e) => setExtra(e.target.value)} /></label>
        {quote && (
          <p className="card" style={{ margin: 0 }}>
            Mínimo para abrir: <b>{fmtBRL(quote.minimum_capital)}</b> · sua parte ({quote.owner_share_pct}%): <b>{fmtBRL(quote.owner_cost)}</b> · adicional: <b>{fmtBRL(quote.extra_capital)}</b> · total que sai da sua conta: <b>{fmtBRL(quote.total_owner_cost)}</b>
          </p>
        )}
        <details className="card" open={friends.length > 0}>
          <summary><b>🤝 Sócios</b> — convide amigos ou parceiros {accepted.length > 0 && <span className="chip up">você fica com {100 - partnersShare}%</span>}</summary>
          <p className="muted small">Cada pessoa decide se aceita (pela amizade, confiança e pelo que ela pode investir). Quem aceita aporta a sua parte do capital mínimo e recebe lucros proporcionais. Sociedade tem riscos: um sócio pode dar calote.</p>
          {friends.length === 0 && <p className="muted small">Você ainda não conhece ninguém. Conheça pessoas na aba Vida pessoal.</p>}
          {friends.map((r) => (
            <div key={r.person_id} className="row" style={{ marginBottom: 8 }}>
              <span style={{ minWidth: 190 }}>{r.gender === "F" ? "👩" : "👨"} <b>{r.name}</b> <span className="muted small">({r.finance_label}, {r.stage === "FRIEND" ? "amigo(a)" : r.stage === "ACQUAINTANCE" ? "conhecido(a)" : "parceiro(a)"})</span></span>
              <input style={{ width: 70 }} inputMode="decimal" placeholder="20" value={shares[r.person_id] ?? ""} onChange={(e) => setShares({ ...shares, [r.person_id]: e.target.value })} aria-label={`Participação de ${r.name} (%)`} />%
              <button type="button" className="btn ghost small" disabled={!!invites[r.person_id]} onClick={() => void invite(r)}>{invites[r.person_id] ? "Respondido" : "Convidar"}</button>
              {invites[r.person_id] && <span className={`small ${invites[r.person_id].accepted ? "tone-up" : "tone-down"}`}>{invites[r.person_id].accepted ? "✅" : "❌"} {invites[r.person_id].message}</span>}
            </div>))}
        </details>
        <p className="muted small" style={{ margin: 0 }}>O aporte não é despesa nem perda: vira o caixa da empresa. Só a estruturação inicial é custo{physical && siteMode === "BUY" ? "; o terreno comprado vira patrimônio" : ""}.</p>
        {msg && <div className="alert">{msg}</div>}
        <button className="btn primary" disabled={busy}>{busy ? "Abrindo…" : "Abrir empresa"}</button>
      </form>
    </div>
  );
}
