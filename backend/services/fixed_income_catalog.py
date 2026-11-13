"""Catálogo de renda fixa.

* Tesouro Direto: dados REAIS do CSV oficial do Tesouro Nacional (treasury_data), atualizados por worker.
* CDB, LCI, LCA, CRI, CRA e debêntures: não há fonte pública estruturada e confiável. São ofertas
  de EXEMPLO (source=SAMPLE), com emissores fictícios e taxas derivadas por regra dos índices reais:
  múltiplos/spreads fixos sobre o CDI, o IPCA e as taxas do Tesouro na data do cadastro. Nunca aleatórias.
"""
import logging
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.core.calendar_br import add_months
from backend.core.money import quantize_money
from backend.models import (
    FixedIncomeProduct, FixedIncomeType as T, IndexName, Indexer as I, Liquidity as L, PaymentFrequency as P,
    ProductSource, RateMode as R, RiskLevel, TaxRegime,
)
from backend.services import treasury_data
from backend.services.index_data import IndexData

log = logging.getLogger(__name__)
D = Decimal


# ------------------------------------------------------------------ Tesouro Direto

@dataclass(frozen=True)
class TreasuryKind:
    type: T
    indexer: I
    mode: R
    frequency: P
    uses_mtm: bool
    note: str = ""


TREASURY_KINDS: dict[str, TreasuryKind] = {
    "Tesouro Selic": TreasuryKind(T.TESOURO_SELIC, I.SELIC, R.SPREAD, P.AT_MATURITY, False,
                                  "Rende a Selic mais um pequeno ágio/deságio. Menor oscilação de preço."),
    "Tesouro Prefixado": TreasuryKind(T.TESOURO_PREFIXADO, I.PRE, R.FIXED, P.AT_MATURITY, True,
                                      "Taxa fixa contratada; o preço de venda antecipada oscila com os juros de mercado."),
    "Tesouro Prefixado com Juros Semestrais": TreasuryKind(
        T.TESOURO_PREFIXADO_JUROS, I.PRE, R.FIXED, P.SEMIANNUAL, False,
        "Paga juros a cada semestre. No simulador, o fluxo é simplificado e o resgate antecipado usa a curva."),
    "Tesouro IPCA+": TreasuryKind(T.TESOURO_IPCA, I.IPCA, R.SPREAD, P.AT_MATURITY, True,
                                  "Inflação (IPCA) mais taxa real contratada; preço de venda antecipada oscila."),
    "Tesouro IPCA+ com Juros Semestrais": TreasuryKind(
        T.TESOURO_IPCA_JUROS, I.IPCA, R.SPREAD, P.SEMIANNUAL, False,
        "IPCA + taxa real, com juros semestrais. Fluxo simplificado; resgate antecipado pela curva."),
    "Tesouro IGPM+ com Juros Semestrais": TreasuryKind(
        T.TESOURO_IGPM_JUROS, I.IGPM, R.SPREAD, P.SEMIANNUAL, False,
        "IGP-M + taxa real, com juros semestrais. Fluxo simplificado; resgate antecipado pela curva."),
    "Tesouro Renda+ Aposentadoria Extra": TreasuryKind(
        T.TESOURO_RENDA_MAIS, I.IPCA, R.SPREAD, P.AT_MATURITY, True,
        "Simplificado: o simulador paga tudo na data de vencimento (o título real paga renda mensal por 20 anos)."),
    "Tesouro Educa+": TreasuryKind(
        T.TESOURO_EDUCA_MAIS, I.IPCA, R.SPREAD, P.AT_MATURITY, True,
        "Simplificado: o simulador paga tudo na data de vencimento (o título real paga renda mensal por 5 anos)."),
}


def sync_treasury(db: Session, today: date) -> int:
    """Atualiza os títulos ofertados hoje. Retorna quantos foram criados/atualizados."""
    quotes = treasury_data.fetch_latest()
    if not quotes:
        return 0
    newest = max(q.base_date for q in quotes)
    offered = [q for q in quotes if q.base_date >= newest - timedelta(days=7) and q.maturity > today
               and q.type_name in TREASURY_KINDS]
    existing = {p.external_id: p for p in db.scalars(select(FixedIncomeProduct).where(
        FixedIncomeProduct.source == ProductSource.TESOURO_TRANSPARENTE))}
    seen: set[str] = set()
    for q in offered:
        kind = TREASURY_KINDS[q.type_name]
        ext = f"tesouro:{q.type_name}:{q.maturity.isoformat()}"
        seen.add(ext)
        p = existing.get(ext) or FixedIncomeProduct(external_id=ext, source=ProductSource.TESOURO_TRANSPARENTE)
        p.name = f"{q.type_name} {q.maturity.year}"
        p.issuer = "Tesouro Nacional"
        p.product_type, p.indexer, p.rate_mode = kind.type, kind.indexer, kind.mode
        p.rate, p.maturity_date = q.buy_rate, q.maturity
        p.unit_price, p.market_rate, p.market_unit_price = q.buy_pu, q.sell_rate, q.sell_pu
        p.min_investment_brl = max(quantize_money(q.buy_pu * D("0.01")) + D("0.01"), D("1.00"))   # fração mínima de 0,01 título
        p.liquidity, p.grace_days, p.liquidity_dates = L.DAILY, 0, []
        p.early_redemption, p.secondary_discount_pct, p.uses_mtm = True, D(0), kind.uses_mtm
        p.payment_frequency, p.tax_regime = kind.frequency, TaxRegime.REGRESSIVE
        p.risk_level, p.fgc_covered, p.description = RiskLevel.LOW, False, kind.note
        p.as_of, p.is_active = q.base_date, True
        db.add(p)
    for ext, p in existing.items():                     # deixou de ser ofertado (ou venceu)
        if ext not in seen and p.is_active:
            p.is_active = False
    db.commit()
    log.info("Tesouro Direto: %s títulos atualizados (data-base %s)", len(offered), newest)
    return len(offered)


def deactivate_expired(db: Session, today: date) -> int:
    n = 0
    for p in db.scalars(select(FixedIncomeProduct).where(FixedIncomeProduct.is_active,
                                                         FixedIncomeProduct.maturity_date <= today)):
        p.is_active = False
        n += 1
    db.commit()
    return n


# ------------------------------------------------------------------ ofertas de exemplo

DISCLAIMER = ("Oferta de EXEMPLO para fins educacionais: emissor fictício, taxa derivada do CDI/IPCA/Tesouro "
              "na data de cadastro. Não é uma oferta real.")


@dataclass(frozen=True)
class Reference:
    """Taxas reais de referência (% a.a.) usadas para derivar as ofertas de exemplo."""
    cdi: Decimal
    ipca_12m: Decimal
    pre_3y: Decimal
    ipca_real_5y: Decimal


def build_reference(db: Session, idx: IndexData, today: date) -> Reference:
    cdi = idx.annual_rate(IndexName.CDI)

    def nearest(ptype: T, years: int) -> Decimal | None:
        target = add_months(today, 12 * years)
        rows = list(db.scalars(select(FixedIncomeProduct).where(
            FixedIncomeProduct.product_type == ptype, FixedIncomeProduct.is_active,
            FixedIncomeProduct.source == ProductSource.TESOURO_TRANSPARENTE)))
        return min(rows, key=lambda p: abs((p.maturity_date - target).days)).rate if rows else None

    return Reference(cdi=cdi, ipca_12m=idx.accumulated_12m(IndexName.IPCA),
                     pre_3y=nearest(T.TESOURO_PREFIXADO, 3) or cdi + D("0.5"),
                     ipca_real_5y=nearest(T.TESOURO_IPCA, 5) or D("6.5"))


@dataclass(frozen=True)
class Template:
    key: str
    name: str
    issuer: str
    type: T
    indexer: I
    mode: R
    rate: callable                      # (Reference) -> Decimal
    years: int
    liquidity: L = L.AT_MATURITY
    grace_days: int = 0
    early: bool = False
    discount: str = "0"
    frequency: P = P.AT_MATURITY
    tax: TaxRegime = TaxRegime.REGRESSIVE
    risk: RiskLevel = RiskLevel.LOW
    fgc: bool = False
    min_brl: str = "1000"
    windows: bool = False               # liquidez em janelas semestrais


TEMPLATES: list[Template] = [
    Template("cdb-liquidez-diaria", "CDB Liquidez Diária", "Banco Alfa S.A.", T.CDB, I.CDI, R.PERCENT_OF_INDEX,
             lambda r: D(100), 3, L.DAILY, 0, True, fgc=True, min_brl="100"),
    Template("cdb-pos-2a", "CDB Pós-fixado 2 anos", "Banco Beta S.A.", T.CDB, I.CDI, R.PERCENT_OF_INDEX,
             lambda r: D(112), 2, fgc=True),
    Template("cdb-carencia-90d", "CDB Pós-fixado com carência de 90 dias", "Banco Gama S.A.", T.CDB, I.CDI,
             R.PERCENT_OF_INDEX, lambda r: D(106), 2, L.DAILY, 90, True, fgc=True),
    Template("cdb-janelas", "CDB Pós-fixado com janelas de resgate", "Banco Delta S.A.", T.CDB, I.CDI,
             R.PERCENT_OF_INDEX, lambda r: D(108), 3, L.SPECIFIC_DATES, 0, True, fgc=True, windows=True),
    Template("cdb-pre-3a", "CDB Prefixado 3 anos", "Banco Épsilon S.A.", T.CDB, I.PRE, R.FIXED,
             lambda r: r.pre_3y + D("0.5"), 3, fgc=True),
    Template("cdb-hibrido-5a", "CDB Híbrido IPCA + taxa 5 anos", "Banco Zeta S.A.", T.CDB, I.IPCA, R.SPREAD,
             lambda r: r.ipca_real_5y + D("0.5"), 5, fgc=True),
    Template("lci-pos-2a", "LCI Pós-fixada 2 anos", "Banco Eta S.A.", T.LCI, I.CDI, R.PERCENT_OF_INDEX,
             lambda r: D(92), 2, tax=TaxRegime.EXEMPT, fgc=True),
    Template("lca-pos-1a", "LCA Pós-fixada com carência de 90 dias", "Cooperativa Agro Theta", T.LCA, I.CDI,
             R.PERCENT_OF_INDEX, lambda r: D(94), 1, L.DAILY, 90, True, tax=TaxRegime.EXEMPT, fgc=True),
    Template("cri-ipca-6a", "CRI IPCA + taxa, juros semestrais", "Securitizadora Iota (lastro imobiliário)", T.CRI,
             I.IPCA, R.SPREAD, lambda r: r.ipca_real_5y + D("1.2"), 6, L.AT_MATURITY, 30, True, "2.0",
             P.SEMIANNUAL, TaxRegime.EXEMPT, RiskLevel.MEDIUM),
    Template("cra-cdi-4a", "CRA CDI + taxa, juros semestrais", "Securitizadora Kappa (lastro agro)", T.CRA,
             I.CDI, R.SPREAD, lambda r: D("1.5"), 4, L.AT_MATURITY, 30, True, "2.5",
             P.SEMIANNUAL, TaxRegime.EXEMPT, RiskLevel.MEDIUM),
    Template("deb-incentivada-8a", "Debênture incentivada IPCA + taxa, juros anuais", "Infra Lambda Energia S.A.",
             T.DEBENTURE, I.IPCA, R.SPREAD, lambda r: r.ipca_real_5y + D("0.8"), 8, L.AT_MATURITY, 30, True, "2.0",
             P.ANNUAL, TaxRegime.EXEMPT, RiskLevel.MEDIUM),
    Template("deb-cdi-5a", "Debênture CDI + taxa, juros semestrais", "Indústria Mu S.A.", T.DEBENTURE, I.CDI, R.SPREAD,
             lambda r: D("2.2"), 5, L.AT_MATURITY, 30, True, "3.0", P.SEMIANNUAL, TaxRegime.REGRESSIVE, RiskLevel.HIGH),
]


def seed_samples(db: Session, today: date, idx: IndexData) -> int:
    """Cria a oferta de exemplo de cada modelo se não houver uma vigente e reprecifica as vigentes."""
    ref = build_reference(db, idx, today)
    created = 0
    for t in TEMPLATES:
        active = db.scalar(select(FixedIncomeProduct).where(
            FixedIncomeProduct.template_key == t.key, FixedIncomeProduct.is_active,
            FixedIncomeProduct.maturity_date > today + timedelta(days=45)))
        ext = f"sample:{t.key}:{today:%Y%m}"
        if active:                       # a oferta acompanha o mercado; aplicações já feitas mantêm a taxa contratada
            active.rate, active.as_of = t.rate(ref).quantize(D("0.01")), today
            continue
        if db.scalar(select(FixedIncomeProduct.id).where(FixedIncomeProduct.external_id == ext)):
            continue
        maturity = add_months(today, 12 * t.years)
        windows = [add_months(today, 6 * k).isoformat() for k in range(1, 2 * t.years + 1)] if t.windows else []
        db.add(FixedIncomeProduct(
            external_id=ext, template_key=t.key, name=t.name, issuer=t.issuer, product_type=t.type,
            indexer=t.indexer, rate_mode=t.mode, rate=t.rate(ref).quantize(D("0.01")), maturity_date=maturity,
            min_investment_brl=D(t.min_brl), liquidity=t.liquidity, grace_days=t.grace_days, liquidity_dates=windows,
            early_redemption=t.early, secondary_discount_pct=D(t.discount), uses_mtm=False,
            payment_frequency=t.frequency, tax_regime=t.tax, risk_level=t.risk, fgc_covered=t.fgc,
            description=DISCLAIMER, source=ProductSource.SAMPLE, as_of=today, is_active=True,
        ))
        created += 1
    db.commit()
    if created:
        log.info("renda fixa: %s ofertas de exemplo cadastradas", created)
    return created
