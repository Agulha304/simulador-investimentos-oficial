import { useEffect, useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { StatCard } from "../components/StatCard";
import { sim, type Life, type Rel } from "../services/sim";
import { useApi } from "../services/dataCache";
import { api, type CoAcqTarget, type CoAcquisitions, type CoCatalog, type CoChannel, type CoOverview, type CoQuote, type CoSegment, type CoSiteMode, type Company } from "../services/api";
import { fmtBRL, parseMoneyInput, trend } from "../lib/format";

const errMsg = (e: unknown) => (e instanceof Error ? e.message : "Erro inesperado");
type Tab = "overview" | "mine" | "market" | "buy";

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
        <button className={tab === "buy" ? "on" : ""} onClick={() => setTab("buy")}>🤝 Comprar empresas</button>
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
      {tab === "buy" && <BuyCompanies mine={ov.companies} onDone={(id) => nav(`/empresas/${id}`)} />}
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
              <td><span className="tag">{c.status === "ACTIVE" ? "Ativa" : "Encerrada"}</span> <span className="muted small">reputação {c.reputation}</span>{c.supply_ready === false && <> <span className="tag tone-warn">sem fornecedores</span></>}{c.supplier_budget && Number(c.supplier_budget) > 0 ? <><br /><span className="muted small">insumos previstos: {fmtBRL(c.supplier_budget)}/mês</span></> : null}</td>
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
  const [country, setCountry] = useState("BR");
  const [countries, setCountries] = useState<{ code: string; name: string; flag: string; currency: string }[]>([{ code: "BR", name: "Brasil", flag: "🇧🇷", currency: "BRL" }]);
  useEffect(() => { sim.economyCountries().then((r) => setCountries(r.countries)).catch(() => undefined); }, []);
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
    api.coQuote({ segment: segment.key, channel, site_mode: physical ? siteMode : undefined, location: physical ? location : undefined, size, extra_capital: extraValue, owner_share_pct: ownerShare, country })
      .then((q) => { if (live) { setQuote(q); setMsg(null); } }).catch((e) => { if (live) setMsg(errMsg(e)); });
    return () => { live = false; };
  }, [segment.key, channel, siteMode, location, size, extraValue, ownerShare, physical, country]);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true); setMsg(null);
    try {
      const d = await api.coCreate({ country, name, segment: segment.key, channel, site_mode: physical ? siteMode : undefined, location: physical ? location : undefined, size, extra_capital: extraValue, owner_share_pct: accepted.length ? "100" : (share || "100"), partner_invite_ids: accepted.map((i) => i.id) });
      onCreated(d.company.id);
    } catch (err) { setMsg(errMsg(err)); setBusy(false); }
  }

  return (
    <div className="modal-back" onMouseDown={onClose}>
      <form className="card modal" onMouseDown={(e) => e.stopPropagation()} onSubmit={submit}>
        <div className="row"><h2>Abrir {segment.label.toLowerCase()}</h2><button type="button" className="link-btn" onClick={onClose}>fechar ✕</button></div>
        <label>Nome da empresa<input value={name} onChange={(e) => setName(e.target.value)} maxLength={80} required /></label>
        <label>País da empresa<select value={country} onChange={(e) => setCountry(e.target.value)}>{countries.map((c) => <option key={c.code} value={c.code}>{c.flag} {c.name} ({c.currency})</option>)}</select></label>
        {quote && quote.country && quote.country !== "BR" && <p className="muted small" style={{ margin: 0 }}>Empresa em {quote.country_name}: preços, aluguel e salários seguem o país e a moeda ({quote.currency}: R$ {Number(quote.rate).toFixed(4)}); tributos locais: IVA {quote.vat}% e imposto sobre o lucro {quote.corp_tax}%. Abrir leva {quote.open_months} meses.</p>}
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
        {(segment.supply_categories?.length ?? 0) > 0 && (
          <div className="alert" style={{ margin: 0 }}><b>Contrate fornecedores antes de operar.</b> {segment.label} precisa de um fornecedor ativo para cada categoria ({segment.supply_categories!.map((x) => x.label).join(", ")}). A empresa nasce sem fornecedores{segment.metrics_kind === "SERVICE" ? ": sem eles a operação fica bloqueada e não há vendas" : " e sem estoque: sem eles o estoque não é reposto e as vendas travam"}. Depois de abrir, procure e negocie cada um na página da empresa.</div>
        )}
        {!physical && <p className="muted small" style={{ margin: 0 }}>Online: sem aluguel nem terreno, custos fixos menores e alcance digital no lugar da demanda local.</p>}
        <label>Porte inicial<select value={size} onChange={(e) => setSize(e.target.value)}>{catalog.sizes.map((s) => <option key={s.key} value={s.key}>{s.label}</option>)}</select></label>
        {quote && (
          <dl className="facts">
            <div><dt>Estruturação (abertura, licenças, reforma)</dt><dd className="num">{fmtBRL(quote.setup_cost)}</dd></div>
            {segment.metrics_kind !== "SERVICE" && <div><dt>Reserva em caixa para a 1ª compra de fornecedores (a empresa nasce sem estoque)</dt><dd className="num">{fmtBRL(quote.first_purchase_reserve ?? quote.initial_stock)}</dd></div>}
            {physical && siteMode === "BUY" && <div><dt>Terreno (vira patrimônio da empresa)</dt><dd className="num">{fmtBRL(quote.land_cost)}</dd></div>}
            <div><dt>Folha mensal dos cargos obrigatórios ({quote.mandatory_roles.join(", ")}) — CLT custa 2× o salário</dt><dd className="num">{fmtBRL(quote.monthly_payroll)}</dd></div>
            <div><dt>Equipe obrigatória no capital mínimo (1 mês de folha + custo de contratação)</dt><dd className="num">{fmtBRL(quote.mandatory_cost)}</dd></div>
            <div><dt>Custos fixos mensais{physical && siteMode === "RENT" ? " (aluguel e outros)" : ""}</dt><dd className="num">{fmtBRL(quote.monthly_fixed)}</dd></div>
            {quote.operating_reserve != null && <div><dt>Reserva de operação já inclusa no capital mínimo ({quote.reserve_months ?? 6} meses de custos fixos e folha, para aguentar as vendas fracas do começo)</dt><dd className="num">{fmtBRL(quote.operating_reserve)}</dd></div>}
            {quote.first_month_units != null && <div><dt>Vendas esperadas no 1º mês (relevância zero: o mercado ainda não conhece você; demanda madura ≈ {quote.expected_units})</dt><dd className="num">≈ {quote.first_month_units} {segment.unit_label}(s)</dd></div>}
            {quote.max_staff != null && <div><dt>Teto de funcionários neste porte (por unidade)</dt><dd className="num">{quote.max_staff} pessoas</dd></div>}
            <div><dt>Capital mínimo para abrir</dt><dd className="num"><b>{fmtBRL(quote.minimum_capital)}</b></dd></div>
            {quote.tax && <div><dt>Regime tributário provável</dt><dd>{quote.tax.regime_label}, alíquota efetiva de {quote.tax.effective_min_pct}% a {quote.tax.effective_max_pct}% conforme o faturamento dos últimos 12 meses (o regime muda sozinho: MEI até R$ 81 mil/ano, Simples até R$ 4,8 mi, depois Lucro Presumido). Simplificações: ICMS 18%, IPI 10% e ISS típico; encargos da folha já estão no custo CLT de 2×.</dd></div>}
          </dl>
        )}
        {quote && (
          <div className="card" style={{ margin: 0 }} aria-label="Checklist de abertura">
            <b>Checklist para operar (depois de abrir)</b>
            <ul className="small" style={{ margin: "6px 0 0", paddingLeft: 18 }}>
              {quote.mandatory_roles.map((r) => <li key={r}>☐ Contratar <b>{r}</b> — cargo obrigatório (sem ele a empresa fica irregular e não vende)</li>)}
              {(quote.supply_categories ?? []).map((x) => <li key={x.key}>☐ Contratar fornecedor de <b>{x.label}</b> ({x.unit}) — obrigatório para repor estoque/produzir</li>)}
              <li>☐ Contratar a equipe produtiva (até {quote.max_staff ?? "?"} pessoas neste porte) conforme a demanda</li>
            </ul>
          </div>
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

/** Compra de empresas: ofertas de todos os portes e países, com negociação em rodadas. */
function BuyCompanies({ mine, onDone }: { mine: Company[]; onDone: (id: number) => void }) {
  const [data, setData] = useState<CoAcquisitions | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [pick, setPick] = useState<CoAcqTarget | null>(null);
  const [offer, setOffer] = useState("");
  const [mode, setMode] = useState<"MERGE" | "KEEP">("KEEP");
  const [buyer, setBuyer] = useState<number | "">("");
  const [busy, setBusy] = useState(false);
  const load = () => { api.coAcquisitions().then(setData).catch((e) => setErr(errMsg(e))); };
  useEffect(load, []);
  if (!data) return err ? <div className="alert">{err}</div> : <div className="muted">Carregando empresas à venda…</div>;
  const mergeable = (t: CoAcqTarget) => mine.filter((c) => c.segment === t.segment && (c.country ?? "BR") === t.country && c.status === "ACTIVE");
  async function send() {
    if (!pick) return;
    setBusy(true); setErr(null);
    try {
      const r = await api.coAcquisitionOffer({ target_key: pick.key, offer: parseMoneyInput(offer), mode, buyer_company_id: mode === "MERGE" && buyer ? Number(buyer) : undefined });
      setData(r); setMsg(r.message);
      if (r.status === "ACCEPTED" && r.company_id) onDone(r.company_id);
      else { const t = r.listings.find((x) => x.key === pick.key); if (t && t.deal?.status === "OPEN") { setPick(t); setOffer(""); } else setPick(null); }
    } catch (e) { setErr(errMsg(e)); } finally { setBusy(false); }
  }
  return (
    <section className="card stack">
      <h2>🤝 Empresas à venda</h2>
      <p className="muted small">Todo mês aparecem negócios de todos os portes, no Brasil e no exterior. Você faz ofertas e o dono aceita, contrapropõe ou recusa conforme o valor (até {data.max_rounds} rodadas; oferta ofensiva ou outro comprador encerram a conversa).
        <b> Incorporar</b> (mesmo segmento e país): vira filiais da sua empresa. <b>Manter separada</b>: nasce uma empresa nova sua, com a equipe e a marca da compra.</p>
      {err && <div className="alert">{err}</div>}
      {msg && <div className="notice">{msg}</div>}
      <div className="goods-grid">{data.listings.map((t) => (
        <div key={t.key} className="card good-card">
          <div className="row between"><b>{t.name}</b><span className="chip">{t.size_label}</span></div>
          <span className="muted small">{t.flag} {t.country_name} · {t.segment_label} · {t.employees} funcionários · relevância {t.relevance}</span>
          <span className="small">Faturamento {fmtBRL(String(t.monthly_revenue))}/mês · margem {t.margin_pct}% · patrimônio {fmtBRL(String(t.assets))}</span>
          <span className="small">Avaliação: <b>{fmtBRL(String(t.valuation))}</b> · pedem <b>{fmtBRL(t.ask_now)}</b></span>
          {t.deal?.status === "DONE" && <span className="chip up">Comprada</span>}
          {t.deal?.status === "WALKED" && <span className="chip down">Negociação encerrada</span>}
          {(!t.deal || t.deal.status === "OPEN") && <button className="btn small primary" onClick={() => { setPick(t); setOffer(""); setMsg(null); setMode(mergeable(t).length ? "MERGE" : "KEEP"); setBuyer(mergeable(t)[0]?.id ?? ""); }}>{t.deal ? `Continuar negociando (${t.deal.rounds}/${data.max_rounds})` : "Negociar"}</button>}
        </div>))}</div>
      {data.done.length > 0 && <><h3>Compras feitas</h3><ul className="list-plain">{data.done.map((d, i) => <li key={i}><span>{d.name}</span><b className="num">{fmtBRL(d.price)}</b></li>)}</ul></>}
      {pick && (
        <div className="modal-back" role="dialog" aria-modal="true" aria-label="Negociar compra">
          <div className="card modal">
            <div className="row between"><h2>Negociar: {pick.name}</h2><button className="link-btn" onClick={() => setPick(null)}>fechar ✕</button></div>
            <p className="small">{pick.flag} {pick.country_name} · avaliação {fmtBRL(String(pick.valuation))} · o dono pede agora <b>{fmtBRL(pick.deal?.ask ?? String(pick.ask))}</b>{pick.deal ? ` · rodada ${pick.deal.rounds + 1} de ${data.max_rounds}` : ""}</p>
            {pick.deal?.log.map((l, i) => <p key={i} className="muted small" style={{ margin: 0 }}>Você ofereceu {fmtBRL(l.offer)} → {l.message ?? "aceito"}</p>)}
            <div className="seg">
              <button className={mode === "KEEP" ? "on" : ""} onClick={() => setMode("KEEP")}>Manter separada</button>
              <button className={mode === "MERGE" ? "on" : ""} disabled={mergeable(pick).length === 0} title={mergeable(pick).length === 0 ? "Você não tem empresa do mesmo segmento e país" : ""} onClick={() => setMode("MERGE")}>Incorporar</button>
            </div>
            {mode === "MERGE" && <label>Empresa que incorpora e paga<select value={buyer} onChange={(e) => setBuyer(Number(e.target.value))}>{mergeable(pick).map((c) => <option key={c.id} value={c.id}>{c.name} — caixa {fmtBRL(c.cash)}</option>)}</select></label>}
            {mode === "KEEP" && <p className="muted small">O valor sai do seu dinheiro pessoal, mais o capital de abertura da nova empresa.</p>}
            <label>Sua oferta (R$)<input inputMode="decimal" value={offer} onChange={(e) => setOffer(e.target.value)} placeholder={fmtBRL(pick.deal?.ask ?? String(pick.ask))} /></label>
            <button className="btn primary" disabled={busy || !offer.trim()} onClick={() => void send()}>Fazer oferta</button>
          </div>
        </div>)}
    </section>
  );
}
