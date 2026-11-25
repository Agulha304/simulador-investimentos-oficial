"""Franquias da marca. Qualquer empresa pode franquear (inclusive antes das 50 unidades próprias), mas é DIFÍCIL: ninguém abre franquia de
marca desconhecida. Fazer PUBLICIDADE DA FRANQUIA eleva a atratividade (decai todo mês) e, com a marca relevante, de vez em quando um
franqueado assina. Cada franquia paga taxa inicial e royalties mensais (bem menos que o resultado de uma filial própria), leva meses para
abrir e pode fechar. Franquias dão relevância à marca. Regras puras no topo; banco embaixo (sem commit)."""
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.core.money import quantize_money
from backend.models import Company, CompanyEventType, CompanyFranchise, FlowKind, SimMonth
from backend.services import company_rules as rules
from backend.services.budget_service import require_open, shift_month
from backend.services.finance_ledger import ConflictError, FinanceError
from backend.services.goods_rules import hash01

D = Decimal
ZERO = D("0.00")
ROYALTY_PCT = D("6.0")            # royalty sobre o faturamento estimado da franquia (uma filial própria fica com ~todo o resultado)
FEE_SHARE = D("0.25")             # taxa inicial = 25% do custo de uma filial barata
BUILD_MONTHS = 3                  # o franqueado monta a loja
MAX_FRANCHISES = 200
MIN_RELEVANCE_AD = 15.0           # abaixo disto a marca é desconhecida: nem a publicidade é aceita
INTEREST_MIN_RELEVANCE = 25.0     # abaixo disto ninguém procura a franquia
APPEAL_DECAY = 0.92
AD_GAIN = {"BARATO": 6.0, "MEDIO": 14.0, "CARO": 28.0}
AD_NOISE = (0.5, 1.3)             # o resultado da publicidade varia de 50% a 130% do ganho nominal
CLOSE_P = 0.012                   # chance mensal de uma franquia fechar (o dobro e mais com viabilidade baixa)
REL_GAIN_EACH = 0.12
REL_GAIN_CAP = 1.5


def interest_probability(appeal: float, relevance: float, reputation: int) -> float:
    """Chance mensal de um franqueado assinar. Marca com relevância < 25: zero. No melhor caso fica perto de 9%."""
    relfac = max(0.0, min(1.0, (relevance - INTEREST_MIN_RELEVANCE) / 60))
    if relfac <= 0:
        return 0.0
    return min(0.12, 0.006 + 0.09 * (appeal / 100) * relfac * (0.6 + 0.4 * reputation / 100))


def franchise_viability(seed, company_id: int, n: int) -> float:
    u = hash01(seed, "fr-viab", company_id, n)
    return round(0.4 + 0.8 * u ** 1.3, 3)


def estimated_sales(matriz_sold: float, price: Decimal, viability: float) -> Decimal:
    return quantize_money(D(str(matriz_sold)) * price * D(str(viability)) * D("0.8"))


def royalty(matriz_sold: float, price: Decimal, viability: float, pct: Decimal = ROYALTY_PCT) -> Decimal:
    return quantize_money(estimated_sales(matriz_sold, price, viability) * pct / 100)


# ------------------------------------------------------------------ banco

def franchises(db: Session, c: Company, only_open: bool = True) -> list[CompanyFranchise]:
    q = select(CompanyFranchise).where(CompanyFranchise.company_id == c.id)
    if only_open:
        q = q.where(CompanyFranchise.status == "OPEN")
    return list(db.scalars(q.order_by(CompanyFranchise.id)))


def ad_cost(c: Company, tier: str) -> Decimal:
    return rules.expansion_cost(rules.SEGMENTS[c.segment], "MARKETING", c.size, c.units, tier)


def advertise(db: Session, user_id: int, month: SimMonth, company_id: int, tier: str, idempotency_key: str) -> Company:
    """Publicidade da franquia: paga e eleva a atratividade para novos franqueados (efeito variável; decai ~8% ao mês)."""
    from backend.services import company_service as cs
    require_open(month)
    c = cs.get_company(db, user_id, company_id, lock=True)
    cs._active(c)
    if tier not in rules.TIERS:
        raise FinanceError("nível inexistente (BARATO, MEDIO ou CARO)")
    if cs._opening(c, month.ref_month):
        raise ConflictError("a empresa ainda está em abertura: espere ela começar a operar")
    if float(c.relevance) < MIN_RELEVANCE_AD:
        raise ConflictError(f"marca ainda desconhecida (relevância {float(c.relevance):.1f}): ninguém quer franquear uma marca que ninguém conhece. "
                            f"Chegue a {MIN_RELEVANCE_AD:.0f} de relevância")
    key = f"co:{c.id}:franchise-ad:{idempotency_key}"
    if cs._replayed(db, key):
        return c
    cost = ad_cost(c, tier)
    if cs.cash(db, c) < cost:
        raise FinanceError(f"caixa da empresa insuficiente para a publicidade ({cost})")
    ref = month.ref_month
    cs._post(db, c, ref, kind=FlowKind.EXPENSE, amount=cost, desc=f"Publicidade da franquia ({rules.TIER_LABEL[tier]})", line="MARKETING", key=key)
    noise = AD_NOISE[0] + (AD_NOISE[1] - AD_NOISE[0]) * hash01(cs._seed(db, user_id), "fr-ad", c.id, ref.isoformat(), idempotency_key)
    gain = AD_GAIN[tier] * noise
    c.franchise_appeal = D(str(round(min(100.0, float(c.franchise_appeal) + gain), 2)))
    cs._event(db, c, ref, CompanyEventType.EXPANSION, f"Publicidade da franquia: atratividade +{gain:.1f} (agora {float(c.franchise_appeal):.1f}/100)", cost)
    return c


def process_month(db: Session, c: Company, ref: date, k: str, *, matriz_sold: float, seed) -> Decimal:
    """Fechamento mensal das franquias: assinatura de novos franqueados, royalties, fechamentos e ganho de relevância. Devolve a receita
    (taxas iniciais + royalties) já lançada no caixa."""
    from backend.services import company_service as cs
    income = ZERO
    # novas assinaturas (só uma por mês)
    open_all = franchises(db, c, only_open=False)
    open_now = [f for f in open_all if f.status == "OPEN"]
    if len(open_now) < MAX_FRANCHISES and not cs._opening(c, ref):
        p = interest_probability(float(c.franchise_appeal), float(c.relevance), c.reputation)
        if p > 0 and hash01(seed, "fr-sign", c.id, ref.isoformat()) < p:
            seg = rules.SEGMENTS[c.segment]
            n = len(open_all) + 1
            viab = franchise_viability(seed, c.id, n)
            fee = quantize_money(rules.expansion_cost(seg, "NEW_UNIT", c.size, c.units, "BARATO") * FEE_SHARE)
            f = CompanyFranchise(company_id=c.id, name=f"Franquia {n}", location=c.location, signed_month=ref,
                                 opens_month=shift_month(ref, BUILD_MONTHS), viability=D(str(viab)), royalty_pct=ROYALTY_PCT, initial_fee=fee)
            db.add(f)
            db.flush()
            cs._post(db, c, ref, kind=FlowKind.INCOME, amount=fee, desc=f"Taxa inicial de franquia: {f.name}", line="ROYALTY", key=f"{k}:fr-fee:{f.id}", overdraft=True)
            income += fee
            c.franchise_appeal = D(str(round(float(c.franchise_appeal) * 0.8, 2)))
            cs._event(db, c, ref, CompanyEventType.EXPANSION, f"Novo franqueado assinou ({f.name}): taxa inicial {fee}; a loja abre em "
                      f"{f.opens_month:%m/%Y}", fee)
    # royalties e fechamentos
    live = 0
    for f in franchises(db, c):
        if f.opens_month > ref:
            continue
        live += 1
        pay = royalty(matriz_sold, c.price, float(f.viability), f.royalty_pct)
        if pay > 0:
            cs._post(db, c, ref, kind=FlowKind.INCOME, amount=pay, desc=f"Royalties: {f.name}", line="ROYALTY", key=f"{k}:fr-roy:{f.id}", overdraft=True)
            f.total_royalties = f.total_royalties + pay
            income += pay
        pc = CLOSE_P * (2.5 if f.viability < D("0.6") else 1.0)
        if hash01(seed, "fr-close", c.id, f.id, ref.isoformat()) < pc:
            f.status, f.closed_month = "CLOSED", ref
            f.closed_reason = "o franqueado não se sustentou e devolveu a bandeira"
            cs._event(db, c, ref, CompanyEventType.EXPANSION, f"{f.name} fechou: {f.closed_reason}")
    # a marca ganha presença
    if live:
        gain = min(REL_GAIN_CAP, REL_GAIN_EACH * live) * (1 - float(c.relevance) / 100)
        c.relevance = D(str(round(min(100.0, float(c.relevance) + gain), 2)))
    c.franchise_appeal = D(str(round(float(c.franchise_appeal) * APPEAL_DECAY, 2)))
    return quantize_money(income)


def view(db: Session, c: Company, ref: date | None = None) -> dict:
    rows = franchises(db, c, only_open=False)
    open_rows = [f for f in rows if f.status == "OPEN"]
    return {
        "appeal": float(c.franchise_appeal), "royalty_pct": str(ROYALTY_PCT), "open": len(open_rows),
        "building": sum(1 for f in open_rows if ref and f.opens_month > ref), "closed": len(rows) - len(open_rows),
        "total_royalties": str(quantize_money(sum((f.total_royalties for f in rows), ZERO))),
        "min_relevance_ad": MIN_RELEVANCE_AD, "ad_costs": {t: str(ad_cost(c, t)) for t in rules.TIERS},
        "monthly_interest_pct": round(interest_probability(float(c.franchise_appeal), float(c.relevance), c.reputation) * 100, 2),
        "units_cap": rules.MAX_UNITS,
        "franchises": [{"id": f.id, "name": f.name, "status": f.status, "opens_month": f.opens_month, "viability": float(f.viability),
                        "total_royalties": str(f.total_royalties), "closed_reason": f.closed_reason} for f in rows],
    }
