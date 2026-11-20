import { useEffect, useState, type FormEvent, type ReactNode } from "react";
import {
  api, type AmortSystem, type GoodDetail, type Listing, type Occupancy, type SaleQuote, type Simulation,
} from "../services/api";
import { COST_LABEL, FREQUENCY_LABEL, fmtBRL, parseMoneyInput, trend } from "../lib/format";

const errMsg = (e: unknown) => (e instanceof Error ? e.message : "Erro inesperado");

function Modal({ title, onClose, onSubmit, children }: { title: string; onClose: () => void; onSubmit: (e: FormEvent) => void; children: ReactNode }) {
  return (
    <div className="modal-back" onMouseDown={onClose}>
      <form className="card modal" onMouseDown={(e) => e.stopPropagation()} onSubmit={onSubmit}>
        <div className="row"><h2>{title}</h2><button type="button" className="link-btn" onClick={onClose}>fechar ✕</button></div>
        {children}
      </form>
    </div>
  );
}

/** Compra à vista ou financiada (Price/SAC), com simulação das parcelas antes de confirmar. */
export function PurchaseModal({ listing, cash, onClose, onBought }: {
  listing: Listing; cash: string; onClose: () => void; onBought: (g: GoodDetail) => void;
}) {
  const fin = listing.financing;
  const [financed, setFinanced] = useState(false);
  const [down, setDown] = useState(fin ? fin.min_down_payment : "");
  const [term, setTerm] = useState(fin ? String(Math.min(fin.max_term_months, 120)) : "");
  const [system, setSystem] = useState<AmortSystem>("PRICE");
  const [extra, setExtra] = useState("0");
  const [key] = useState(() => crypto.randomUUID());
  const [sim, setSim] = useState<Simulation | null>(null);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);

  useEffect(() => {
    setSim(null);
    if (!financed || !fin) return;
    const t = window.setTimeout(() => {
      api.simulateFinancing({ listing_key: listing.key, down_payment: parseMoneyInput(down) || "0", term_months: Number(term) || 1, system })
        .then((s) => { setSim(s); setMsg(null); }).catch((e) => setMsg(errMsg(e)));
    }, 350);
    return () => window.clearTimeout(t);
  }, [financed, down, term, system, listing.key, fin]);

  const needed = Number(sim ? sim.cash_needed_now : listing.price) + (sim ? 0 : Number(listing.purchase_fee)) + Number(parseMoneyInput(extra) || 0);
  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true); setMsg(null);
    try {
      const g = await api.buyGood({
        listing_key: listing.key, idempotency_key: key, financed, extra_costs: parseMoneyInput(extra) || "0",
        ...(financed ? { down_payment: parseMoneyInput(down), term_months: Number(term), system } : {}),
      });
      onBought(g);
    } catch (err) { setMsg(errMsg(err)); setBusy(false); }
  }

  return (
    <Modal title={`Comprar: ${listing.name}`} onClose={onClose} onSubmit={submit}>
      <p className="muted small" style={{ margin: 0 }}>{listing.description} · {listing.location}</p>
      <dl className="facts">
        <div><dt>Preço</dt><dd className="num"><b>{fmtBRL(listing.price)}</b></dd></div>
        <div><dt>Taxas e impostos da compra</dt><dd className="num">{fmtBRL(listing.purchase_fee)}</dd></div>
        {(listing.fee_breakdown ?? []).map((f) => <div key={f.name}><dt className="muted small">↳ {f.name} ({Number(f.rate_pct)}%)</dt><dd className="num small">{fmtBRL(f.amount)}</dd></div>)}
        <div><dt>Saldo disponível</dt><dd className="num">{fmtBRL(cash)}</dd></div>
      </dl>
      {fin && (
        <div className="seg" role="group" aria-label="Forma de pagamento">
          <button type="button" className={!financed ? "on" : ""} onClick={() => setFinanced(false)}>À vista</button>
          <button type="button" className={financed ? "on" : ""} onClick={() => setFinanced(true)}>Financiado</button>
        </div>
      )}
      {financed && fin && (
        <>
          <label>Entrada (R$) — mínimo {fmtBRL(fin.min_down_payment)}<input inputMode="decimal" value={down} onChange={(e) => setDown(e.target.value)} /></label>
          <label>Prazo (meses) — máximo {fin.max_term_months}<input inputMode="numeric" value={term} onChange={(e) => setTerm(e.target.value.replace(/\D/g, ""))} /></label>
          <label>Sistema de amortização
            <select value={system} onChange={(e) => setSystem(e.target.value as AmortSystem)}>
              <option value="PRICE">Price (parcelas fixas)</option><option value="SAC">SAC (parcelas decrescentes)</option>
            </select>
          </label>
          <p className="muted small" style={{ margin: 0 }}>Juros de {fin.annual_rate_pct.replace(".", ",")}% ao ano (efetivos), parcelas a partir do mês seguinte.</p>
          {sim && (
            <div className="sim">
              <div className="row"><span>1ª parcela</span><b className="num">{fmtBRL(sim.first_payment)}</b></div>
              <div className="row muted small"><span>Última parcela</span><span className="num">{fmtBRL(sim.last_payment)}</span></div>
              <div className="row muted small"><span>Total de juros</span><span className="num">{fmtBRL(sim.total_interest)}</span></div>
              <div className="row muted small"><span>Total pago (com entrada)</span><span className="num">{fmtBRL(sim.total_paid)}</span></div>
            </div>
          )}
        </>
      )}
      <label>Custos adicionais (R$, opcional)<input inputMode="decimal" value={extra} onChange={(e) => setExtra(e.target.value)} /></label>
      <div className="row"><span className="muted small">Saem do caixa agora</span><b className="num">{fmtBRL(needed.toFixed(2))}</b></div>
      {msg && <div className="alert">{msg}</div>}
      <button className="btn primary" disabled={busy || (financed && !sim)}>{busy ? "Comprando…" : "Confirmar compra"}</button>
    </Modal>
  );
}

export function SellModal({ good, onClose, onSold }: { good: GoodDetail; onClose: () => void; onSold: (g: GoodDetail) => void }) {
  const [price, setPrice] = useState(good.good.current_value);
  const [quote, setQuote] = useState<SaleQuote | null>(null);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  useEffect(() => {
    const t = window.setTimeout(() => { api.saleQuote(good.good.id, parseMoneyInput(price) || undefined).then(setQuote).catch((e) => setMsg(errMsg(e))); }, 300);
    return () => window.clearTimeout(t);
  }, [price, good.good.id]);
  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true); setMsg(null);
    try { onSold(await api.sellGood(good.good.id, { sale_price: parseMoneyInput(price) })); }
    catch (err) { setMsg(errMsg(err)); setBusy(false); }
  }
  return (
    <Modal title={`Vender: ${good.good.name}`} onClose={onClose} onSubmit={submit}>
      <label>Preço de venda (R$)<input inputMode="decimal" value={price} onChange={(e) => setPrice(e.target.value)} required /></label>
      {quote && (
        <dl className="facts">
          <div><dt>Taxas e custos da venda</dt><dd className="num">{fmtBRL(quote.fees)}</dd></div>
          {quote.brokerage != null && <div><dt className="muted small">↳ Corretagem e custos</dt><dd className="num small">{fmtBRL(quote.brokerage)}</dd></div>}
          {quote.capital_gains_tax != null && <div><dt className="muted small">↳ Imposto de renda sobre o ganho</dt><dd className="num small">{fmtBRL(quote.capital_gains_tax)}</dd></div>}
          {quote.tax_note && <p className="muted small" style={{ margin: 0 }}>{quote.tax_note}</p>}
          {Number(quote.loan_payoff) > 0 && <div><dt>Quitação do financiamento</dt><dd className="num">{fmtBRL(quote.loan_payoff)}</dd></div>}
          <div><dt>Dinheiro que entra no caixa</dt><dd className="num"><b>{fmtBRL(quote.net_cash)}</b></dd></div>
          <div><dt>Resultado sobre o custo de aquisição</dt><dd className={`num tone-${trend(quote.result)}`}>{fmtBRL(quote.result)}</dd></div>
        </dl>
      )}
      <p className="muted small" style={{ margin: 0 }}>A venda é definitiva e o histórico do bem fica preservado.</p>
      {msg && <div className="alert">{msg}</div>}
      <button className="btn primary" disabled={busy}>{busy ? "Vendendo…" : "Confirmar venda"}</button>
    </Modal>
  );
}

/** Morar no imóvel (encerrando o aluguel residencial) ou anunciá-lo para alugar. */
export function OccupancyModal({ good, onClose, onDone }: { good: GoodDetail; onClose: () => void; onDone: (g: GoodDetail) => void }) {
  const re = good.real_estate!;
  const residential = good.good.category === "RESIDENTIAL";
  const [mode, setMode] = useState<Occupancy>(residential ? "OWNER_OCCUPIED" : "LISTED_FOR_RENT");
  const [rent, setRent] = useState(Number(re.monthly_rent) > 0 ? re.monthly_rent : re.market_rent);
  const [nightly, setNightly] = useState(Number(re.nightly_rate) > 0 ? re.nightly_rate! : (re.market_nightly ?? "0"));
  const [mgmt, setMgmt] = useState<"SELF" | "HIRED">(re.management ?? "SELF");
  const [cands, setCands] = useState<{ id: number; name: string; amount: string | null }[]>([]);
  const [ending, setEnding] = useState<number[]>([]);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  useEffect(() => {
    api.housingCandidates().then((c) => { setCands(c); setEnding(c.filter((x) => /alug/i.test(x.name)).map((x) => x.id)); }).catch(() => undefined);
  }, []);
  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true); setMsg(null);
    try {
      onDone(await api.setOccupancy(good.good.id, {
        mode, ...(mode === "LISTED_FOR_RENT" ? { monthly_rent: parseMoneyInput(rent) } : {}),
        ...(mode === "OWNER_OCCUPIED" ? { end_recurring_item_ids: ending } : {}),
        ...(mode === "SHORT_STAY" ? { nightly_rate: parseMoneyInput(nightly), management: mgmt } : {}),
      }));
    } catch (err) { setMsg(errMsg(err)); setBusy(false); }
  }
  return (
    <Modal title={`Uso do imóvel: ${good.good.name}`} onClose={onClose} onSubmit={submit}>
      <div className="seg" role="group" aria-label="Uso do imóvel">
        {residential && <button type="button" className={mode === "OWNER_OCCUPIED" ? "on" : ""} onClick={() => setMode("OWNER_OCCUPIED")}>Morar</button>}
        {good.good.category !== "LAND" && <button type="button" className={mode === "LISTED_FOR_RENT" ? "on" : ""} onClick={() => setMode("LISTED_FOR_RENT")}>Aluguel fixo</button>}
        {residential && <button type="button" className={mode === "SHORT_STAY" ? "on" : ""} onClick={() => setMode("SHORT_STAY")}>Temporada</button>}
        <button type="button" className={mode === "VACANT" ? "on" : ""} onClick={() => setMode("VACANT")}>Desocupado</button>
      </div>
      {mode === "OWNER_OCCUPIED" && (
        <>
          <p className="muted small" style={{ margin: 0 }}>IPTU, condomínio e manutenção deste imóvel já entram no orçamento. Marque o aluguel residencial que deixa de ser cobrado (o histórico dos meses anteriores é preservado).</p>
          {cands.length === 0 ? <p className="muted small" style={{ margin: 0 }}>Nenhuma despesa recorrente de moradia encontrada.</p> : cands.map((c) => (
            <label key={c.id} className="check"><input type="checkbox" checked={ending.includes(c.id)}
              onChange={(e) => setEnding(e.target.checked ? [...ending, c.id] : ending.filter((i) => i !== c.id))} />
              Encerrar “{c.name}” {c.amount ? `(${fmtBRL(c.amount)}/mês)` : ""}</label>
          ))}
        </>
      )}
      {mode === "SHORT_STAY" && (
        <>
          <p className="muted small" style={{ margin: 0 }}>🏖️ <b>Temporada</b> é o “Airbnb” do jogo: rende mais que o aluguel fixo, mas dá trabalho. Cobram-se taxa da plataforma (3%), limpeza, ISS (3%) e imposto de renda sobre o que você ganha.</p>
          <label>Diária (R$) — referência {fmtBRL(re.market_nightly ?? "0")}<input inputMode="decimal" value={nightly} onChange={(e) => setNightly(e.target.value)} /></label>
          <div className="seg" role="group" aria-label="Gestão">
            <button type="button" className={mgmt === "SELF" ? "on" : ""} onClick={() => setMgmt("SELF")}>Eu cuido (14h/mês)</button>
            <button type="button" className={mgmt === "HIRED" ? "on" : ""} onClick={() => setMgmt("HIRED")}>Contratar gestor (20%)</button></div>
          <p className="muted small" style={{ margin: 0 }}>{mgmt === "SELF" ? "Você gasta 14 horas livres por mês e, se não tiver tempo, a nota e as reservas caem." : "O gestor fica com 20% da receita, mas você não gasta tempo."} Diária acima do mercado reduz as reservas.</p>
        </>
      )}
      {mode === "LISTED_FOR_RENT" && (
        <>
          <label>Aluguel mensal (R$) — referência de mercado {fmtBRL(re.market_rent)}<input inputMode="decimal" value={rent} onChange={(e) => setRent(e.target.value)} /></label>
          <p className="muted small" style={{ margin: 0 }}>Achar inquilino não é garantido: o imóvel fica vago até alugar, e pode voltar a ficar vago depois. Aluguel acima do mercado demora mais. Você recebe no fechamento de cada mês alugado, com IR de {re.rent_tax_pct}% sobre o aluguel.</p>
        </>
      )}
      {msg && <div className="alert">{msg}</div>}
      <button className="btn primary" disabled={busy}>{busy ? "Salvando…" : "Confirmar"}</button>
    </Modal>
  );
}

export function MaintenanceModal({ good, onClose, onDone }: { good: GoodDetail; onClose: () => void; onDone: (g: GoodDetail) => void }) {
  const [amount, setAmount] = useState("");
  const [desc, setDesc] = useState("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true); setMsg(null);
    try { onDone(await api.goodMaintenance(good.good.id, parseMoneyInput(amount), desc)); }
    catch (err) { setMsg(errMsg(err)); setBusy(false); }
  }
  return (
    <Modal title={`Manutenção: ${good.good.name}`} onClose={onClose} onSubmit={submit}>
      <p className="muted small" style={{ margin: 0 }}>Despesa paga agora, registrada no orçamento do mês. Manutenções relevantes podem melhorar a conservação de bens em estado regular ou ruim.</p>
      <label>Descrição<input value={desc} onChange={(e) => setDesc(e.target.value)} maxLength={200} placeholder="Ex.: troca de freios" /></label>
      <label>Valor (R$)<input inputMode="decimal" value={amount} onChange={(e) => setAmount(e.target.value)} required /></label>
      {msg && <div className="alert">{msg}</div>}
      <button className="btn primary" disabled={busy}>{busy ? "Registrando…" : "Registrar manutenção"}</button>
    </Modal>
  );
}

export function CostModal({ good, onClose, onDone }: { good: GoodDetail; onClose: () => void; onDone: (g: GoodDetail) => void }) {
  const [kind, setKind] = useState("INSURANCE");
  const [amount, setAmount] = useState("");
  const [freq, setFreq] = useState<"MONTHLY" | "QUARTERLY" | "SEMIANNUAL" | "ANNUAL">("MONTHLY");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true); setMsg(null);
    try { onDone(await api.addGoodCost(good.good.id, { kind, name: COST_LABEL[kind], amount: parseMoneyInput(amount), frequency: freq })); }
    catch (err) { setMsg(errMsg(err)); setBusy(false); }
  }
  return (
    <Modal title="Novo custo do bem" onClose={onClose} onSubmit={submit}>
      <label>Tipo<select value={kind} onChange={(e) => setKind(e.target.value)}>{Object.entries(COST_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></label>
      <label>Valor (R$)<input inputMode="decimal" value={amount} onChange={(e) => setAmount(e.target.value)} required /></label>
      <label>Frequência<select value={freq} onChange={(e) => setFreq(e.target.value as typeof freq)}>{Object.entries(FREQUENCY_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></label>
      {msg && <div className="alert">{msg}</div>}
      <button className="btn primary" disabled={busy}>{busy ? "Salvando…" : "Adicionar custo"}</button>
    </Modal>
  );
}

