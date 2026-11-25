"""Abertura de capital (IPO) da empresa. Exigente: empresa com pelo menos 12 meses, 6 meses fechados com lucro médio positivo, relevância
mínima e patrimônio mínimo. O processo leva 3 meses (auditoria, CVM, bookbuilding). No pregão o dono é DILUÍDO (vende ações novas ao
público, o dinheiro entra no caixa da empresa), e o preço da ação passa a acompanhar o valor da empresa com ruído de mercado. Depois o
dono pode vender parte da sua participação ou recomprar do mercado. Regras puras no topo; banco embaixo (sem commit)."""
import math
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.core.money import quantize_money
from backend.models import Company, CompanyEventType, CompanyListing, CompanyMonth, CompanyPartner, FlowKind, SimMonth
from backend.services import company_rules as rules
from backend.services.budget_service import months_between, require_open, shift_month
from backend.services.finance_ledger import ConflictError, FinanceError
from backend.services.goods_rules import hash01

D = Decimal
ZERO = D("0.00")
MIN_AGE_MONTHS = 12
MIN_CLOSED_MONTHS = 6
MIN_RELEVANCE = 40.0
MIN_EQUITY = D(500_000)
PROCESS_MONTHS = 3
PREP_FEE = D(80_000)                      # auditoria, advogados e taxas (porte pequeno); paga ao pedir
FEE_SIZE_MULT = {rules.CompanySize.SMALL: D(1), rules.CompanySize.MEDIUM: D("1.8"), rules.CompanySize.LARGE: D("3.2")}
UNDERWRITING = D("0.04")                  # comissão dos bancos sobre a captação
MIN_FLOAT, MAX_FLOAT = D(10), D(49)       # % do capital oferecido ao público (o dono mantém o controle)
BASE_SHARES = 1_000_000
PE_BASE, PE_REL = 8.0, 4.0                # múltiplo lucro/preço: 8x a 12x conforme a relevância da marca
PRICE_PULL = 0.30                         # a cada mês o preço anda 30% do caminho até o valor justo
NOISE = 0.10
SALE_FEE = D("0.005")
BUYBACK_PREMIUM = D("1.03")
HISTORY = 36


def pe_multiple(relevance: float) -> float:
    return PE_BASE + PE_REL * max(0.0, min(100.0, relevance)) / 100


def fair_value(equity: Decimal, avg_net_6m: Decimal, relevance: float) -> Decimal:
    """Valor justo da empresa: o maior entre o patrimônio e o lucro anualizado x múltiplo."""
    return quantize_money(max(equity, avg_net_6m * 12 * D(str(pe_multiple(relevance))), ZERO))


def next_price(price: Decimal, fair_per_share: Decimal, *, noise_u: float, sentiment: float) -> Decimal:
    """Preço do mês seguinte: puxa para o valor justo e soma ruído (±5%) e o humor da economia."""
    drift = PRICE_PULL * (float(fair_per_share) / max(float(price), 0.01) - 1)
    move = drift + (noise_u - 0.5) * NOISE + sentiment
    return max(D("0.01"), (price * D(str(1 + max(-0.4, min(0.4, move))))).quantize(D("0.0001")))


def ticker_for(name: str, company_id: int) -> str:
    letters = "".join(ch for ch in name.upper() if ch.isalpha())[:4].ljust(4, "X")
    return f"{letters}{3 + company_id % 6}"


# ------------------------------------------------------------------ banco

def listing_of(db: Session, c: Company) -> CompanyListing | None:
    return db.scalar(select(CompanyListing).where(CompanyListing.company_id == c.id))


def _last_net(db: Session, c: Company, n: int = 6) -> tuple[int, Decimal]:
    rows = list(db.scalars(select(CompanyMonth.net_result).where(CompanyMonth.company_id == c.id).order_by(CompanyMonth.ref_month.desc()).limit(n)))
    return len(rows), (quantize_money(sum(rows, ZERO) / len(rows)) if rows else ZERO)


def eligibility(db: Session, c: Company, ref: date) -> dict:
    from backend.services import company_service as cs
    from backend.services import wealth_service
    n, avg = _last_net(db, c)
    equity = wealth_service.company_equity(db, c)
    age = months_between(c.founded_on, ref)
    checks = [
        (age >= MIN_AGE_MONTHS, f"pelo menos {MIN_AGE_MONTHS} meses de empresa (tem {age})"),
        (n >= MIN_CLOSED_MONTHS, f"pelo menos {MIN_CLOSED_MONTHS} meses fechados (tem {n})"),
        (avg > 0, f"lucro líquido médio positivo nos últimos {MIN_CLOSED_MONTHS} meses (médio: {avg})"),
        (float(c.relevance) >= MIN_RELEVANCE, f"relevância da marca de pelo menos {MIN_RELEVANCE:.0f} (tem {float(c.relevance):.1f})"),
        (equity >= MIN_EQUITY, f"patrimônio da empresa de pelo menos {MIN_EQUITY} (tem {equity})"),
        (not cs._opening(c, ref), "empresa já operando"),
    ]
    value = fair_value(equity, avg, float(c.relevance))
    return {"ok": all(ok for ok, _ in checks), "missing": [m for ok, m in checks if not ok], "valuation": value, "equity": equity,
            "avg_net_6m": avg, "prep_fee": quantize_money(PREP_FEE * FEE_SIZE_MULT[c.size]), "process_months": PROCESS_MONTHS,
            "price_per_share": (value / BASE_SHARES).quantize(D("0.0001"))}


def apply(db: Session, user_id: int, month: SimMonth, company_id: int, float_pct: Decimal, idempotency_key: str) -> CompanyListing:
    from backend.services import company_service as cs
    require_open(month)
    c = cs.get_company(db, user_id, company_id, lock=True)
    cs._active(c)
    float_pct = D(str(float_pct))
    if not MIN_FLOAT <= float_pct <= MAX_FLOAT:
        raise FinanceError(f"o IPO deve oferecer entre {MIN_FLOAT}% e {MAX_FLOAT}% do capital")
    row = listing_of(db, c)
    if row is not None and row.status != "DELISTED":
        raise ConflictError("a empresa já abriu (ou está abrindo) o capital")
    ref = month.ref_month
    el = eligibility(db, c, ref)
    if not el["ok"]:
        raise ConflictError("a empresa ainda não pode abrir capital: " + "; ".join(el["missing"]))
    key = f"co:{c.id}:ipo-prep:{idempotency_key}"
    if cs._replayed(db, key):
        return listing_of(db, c)
    fee = el["prep_fee"]
    if cs.cash(db, c) < fee:
        raise FinanceError(f"caixa da empresa insuficiente para a preparação do IPO ({fee})")
    cs._post(db, c, ref, kind=FlowKind.EXPENSE, amount=fee, desc="Preparação do IPO (auditoria, advogados e taxas)", line="FEES", key=key)
    if row is None:
        row = CompanyListing(company_id=c.id, ticker=ticker_for(c.name, c.id), float_pct=float_pct, applied_month=ref,
                             lists_month=shift_month(ref, PROCESS_MONTHS))
        db.add(row)
    else:
        row.status, row.float_pct, row.applied_month, row.lists_month, row.listed_month = "PENDING", float_pct, ref, shift_month(ref, PROCESS_MONTHS), None
    row.valuation, row.prev_owner_share = el["valuation"], c.owner_share_pct
    db.flush()
    cs._event(db, c, ref, CompanyEventType.CAPITAL, f"IPO solicitado ({row.ticker}): {float_pct}% do capital ao público; a negociação começa em "
              f"{row.lists_month:%m/%Y} (avaliação atual {el['valuation']})", fee)
    return row


def process_month(db: Session, c: Company, ref: date, k: str, *, seed, sentiment: float) -> None:
    """Estreia no pregão (PENDING -> LISTED) e atualização mensal do preço da ação."""
    from backend.services import company_service as cs
    from backend.services import wealth_service
    row = listing_of(db, c)
    if row is None or row.status == "DELISTED":
        return
    n, avg = _last_net(db, c)
    equity = wealth_service.company_equity(db, c)
    value = fair_value(equity, avg, float(c.relevance))
    if row.status == "PENDING":
        if ref < row.lists_month:
            return
        f = row.float_pct / 100
        pre_price = (value / BASE_SHARES).quantize(D("0.0001"))
        gross = quantize_money(value * f / (1 - f))
        net = quantize_money(gross * (1 - UNDERWRITING))
        cs._post(db, c, ref, kind=FlowKind.INCOME, amount=net, desc=f"Captação do IPO {row.ticker} (líquida das comissões)", line="CAPITAL_IN",
                 key=f"{k}:ipo", overdraft=True)
        row.shares_total = int(round(BASE_SHARES / float(1 - f)))
        row.valuation, row.ipo_price, row.price, row.proceeds = value, pre_price, pre_price, net
        row.status, row.listed_month, row.prev_owner_share = "LISTED", ref, c.owner_share_pct
        keep = 1 - f
        c.owner_share_pct = (c.owner_share_pct * keep).quantize(D("0.01"))
        for p in db.scalars(select(CompanyPartner).where(CompanyPartner.company_id == c.id, CompanyPartner.status == "ACTIVE")):
            p.share_pct = (p.share_pct * keep).quantize(D("0.01"))
        row.history = [{"month": ref.isoformat(), "price": str(pre_price)}]
        cs._event(db, c, ref, CompanyEventType.CAPITAL, f"{row.ticker} estreou no pregão a {pre_price} por ação: captação líquida {net}; sua participação "
                  f"caiu para {c.owner_share_pct}%", net)
        return
    fair = (value / max(row.shares_total, 1)).quantize(D("0.0001"))
    new = next_price(row.price, fair, noise_u=hash01(seed, "ipo-noise", c.id, ref.isoformat()), sentiment=sentiment)
    row.price = new
    hist = list(row.history or [])
    hist.append({"month": ref.isoformat(), "price": str(new)})
    row.history = hist[-HISTORY:]


def market_cap(row: CompanyListing) -> Decimal:
    return quantize_money(row.price * row.shares_total)


def sell_stake(db: Session, user_id: int, month: SimMonth, company_id: int, pct: Decimal, idempotency_key: str) -> Company:
    """O dono vende parte do SEU capital (pontos percentuais do total da empresa) ao mercado, ao preço da ação menos 0,5% de corretagem."""
    from backend.services import company_service as cs
    require_open(month)
    c = cs.get_company(db, user_id, company_id, lock=True)
    cs._active(c)
    row = listing_of(db, c)
    if row is None or row.status != "LISTED":
        raise ConflictError("a empresa não tem ações negociadas em bolsa")
    pct = D(str(pct))
    # o dono precisa manter o controle (acima de 50% somando sócios não vale aqui: regra simples, mais de 30% do capital)
    if pct <= 0 or c.owner_share_pct - pct < D(30):
        raise FinanceError("venda inválida: o dono precisa manter pelo menos 30% do capital")
    key = f"co:{c.id}:ipo-sell:{idempotency_key}"
    if cs._replayed(db, f"{key}:personal"):
        return c
    gross = quantize_money(market_cap(row) * pct / 100)
    net = quantize_money(gross * (1 - SALE_FEE))
    cs._post_personal(db, c, month.ref_month, kind=FlowKind.INCOME, amount=net, desc=f"Venda de {pct}% de {row.ticker} no pregão",
                      category="Venda de participação", key=f"{key}:personal", capital=True)
    c.owner_share_pct = c.owner_share_pct - pct
    cs._event(db, c, month.ref_month, CompanyEventType.CAPITAL, f"Você vendeu {pct}% da empresa no pregão por {net}; participação agora {c.owner_share_pct}%", net)
    return c


def buy_back(db: Session, user_id: int, month: SimMonth, company_id: int, pct: Decimal, idempotency_key: str) -> Company:
    """O dono recompra do público (preço da ação + 3% de prêmio), até voltar ao que tinha antes do IPO."""
    from backend.services import company_service as cs
    require_open(month)
    c = cs.get_company(db, user_id, company_id, lock=True)
    cs._active(c)
    row = listing_of(db, c)
    if row is None or row.status != "LISTED":
        raise ConflictError("a empresa não tem ações negociadas em bolsa")
    pct = D(str(pct))
    if pct <= 0 or c.owner_share_pct + pct > row.prev_owner_share:
        raise FinanceError(f"recompra inválida: sua participação não pode passar de {row.prev_owner_share}%")
    key = f"co:{c.id}:ipo-buy:{idempotency_key}"
    if cs._replayed(db, f"{key}:personal"):
        return c
    cost = quantize_money(market_cap(row) * pct / 100 * BUYBACK_PREMIUM)
    cs._post_personal(db, c, month.ref_month, kind=FlowKind.EXPENSE, amount=cost, desc=f"Recompra de {pct}% de {row.ticker}",
                      category="Compra de participação", key=f"{key}:personal", capital=True)
    c.owner_share_pct = c.owner_share_pct + pct
    cs._event(db, c, month.ref_month, CompanyEventType.CAPITAL, f"Você recomprou {pct}% da empresa por {cost}; participação agora {c.owner_share_pct}%", cost)
    return c


def view(db: Session, c: Company, ref: date) -> dict:
    row = listing_of(db, c)
    out = {"eligibility": eligibility(db, c, ref), "listing": None, "min_float": str(MIN_FLOAT), "max_float": str(MAX_FLOAT)}
    if row is not None and row.status != "DELISTED":
        out["listing"] = {"ticker": row.ticker, "status": row.status, "float_pct": str(row.float_pct), "lists_month": row.lists_month,
                          "price": str(row.price), "ipo_price": str(row.ipo_price), "shares_total": row.shares_total,
                          "market_cap": str(market_cap(row)), "proceeds": str(row.proceeds), "history": row.history,
                          "my_stake_value": str(quantize_money(market_cap(row) * c.owner_share_pct / 100)),
                          "owner_share_pct": str(c.owner_share_pct), "prev_owner_share": str(row.prev_owner_share)}
    return out
