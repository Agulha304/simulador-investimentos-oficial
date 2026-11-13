from typing import Annotated

from fastapi import APIRouter, Header, HTTPException, Query, status
from sqlalchemy import select

from backend.core.dates import today_br
from backend.dependencies import CurrentUser, DbSession
from backend.models import (
    FixedIncomeProduct, FixedIncomeType, IndexName, Indexer, InvestmentStatus, Liquidity, TaxRegime,
)
from backend.schemas.fixed_income import (
    FlowOut, IndexesOut, InvestmentOut, InvestRequest, ProductBrief, ProductOut, SimulateRequest, SimulationOut,
)
from backend.services import fixed_income_service as svc
from backend.services import index_data, ledger_service, portfolio_service
from backend.workers import fixed_income_worker

router = APIRouter(prefix="/fixed-income", tags=["fixed-income"])
IdemKey = Annotated[str | None, Header(alias="Idempotency-Key", max_length=64)]


def investment_out(v: svc.InvestmentView) -> InvestmentOut:
    i = v.inv
    profit = v.estimated_net + i.interest_paid_net_brl - i.principal_brl
    return InvestmentOut(
        id=i.id, product=ProductBrief.model_validate(i.product), status=i.status, applied_on=i.applied_on,
        maturity_date=i.maturity_date, principal_brl=i.principal_brl, units=i.units, current_gross_brl=v.current_gross,
        estimated_tax_brl=v.estimated_tax, estimated_net_brl=v.estimated_net, interest_paid_net_brl=i.interest_paid_net_brl,
        profit_net_brl=profit, valuation_method=v.method, can_redeem=v.redeem_block_reason is None,
        redeem_block_reason=v.redeem_block_reason, redeem_net_brl=v.redeem_net,
        next_event_date=v.next_event.scheduled_date if v.next_event else None,
        next_event_kind=v.next_event.kind if v.next_event else None, closed_on=i.closed_on,
    )


@router.get("/products", response_model=list[ProductOut])
def list_products(
    _: CurrentUser, db: DbSession,
    product_type: FixedIncomeType | None = None, indexer: Indexer | None = None, tax_regime: TaxRegime | None = None,
    liquidity: Liquidity | None = None, q: Annotated[str | None, Query(max_length=60)] = None,
    limit: Annotated[int, Query(ge=1, le=300)] = 200,
):
    stmt = select(FixedIncomeProduct).where(FixedIncomeProduct.is_active, FixedIncomeProduct.maturity_date > today_br())
    for col, val in ((FixedIncomeProduct.product_type, product_type), (FixedIncomeProduct.indexer, indexer),
                     (FixedIncomeProduct.tax_regime, tax_regime), (FixedIncomeProduct.liquidity, liquidity)):
        if val is not None:
            stmt = stmt.where(col == val)
    if q:
        stmt = stmt.where(FixedIncomeProduct.name.ilike(f"%{q}%") | FixedIncomeProduct.issuer.ilike(f"%{q}%"))
    return list(db.scalars(stmt.order_by(FixedIncomeProduct.product_type, FixedIncomeProduct.maturity_date).limit(limit)))


@router.get("/products/{product_id}", response_model=ProductOut)
def get_product(product_id: int, _: CurrentUser, db: DbSession):
    p = db.get(FixedIncomeProduct, product_id)
    if p is None:
        raise HTTPException(404, "Produto não encontrado")
    return p


@router.get("/indexes", response_model=IndexesOut)
def get_indexes(_: CurrentUser, db: DbSession):
    idx = index_data.load(db)
    return IndexesOut(cdi_annual=idx.annual_rate(IndexName.CDI).quantize(index_data.D("0.01")),
                      selic_annual=idx.annual_rate(IndexName.SELIC).quantize(index_data.D("0.01")),
                      ipca_12m=idx.accumulated_12m(IndexName.IPCA).quantize(index_data.D("0.01")),
                      igpm_12m=idx.accumulated_12m(IndexName.IGPM).quantize(index_data.D("0.01")),
                      last_cdi_date=idx.last_known_day(IndexName.CDI))


@router.post("/simulate", response_model=SimulationOut)
def simulate(body: SimulateRequest, _: CurrentUser, db: DbSession):
    p = db.get(FixedIncomeProduct, body.product_id)
    if p is None or not p.is_active:
        raise HTTPException(404, "Produto não encontrado")
    idx, today = index_data.load(db), today_br()
    s = svc.simulate(p, body.amount_brl, today, idx)
    return SimulationOut(
        product=ProductBrief.model_validate(p), principal_brl=s.principal, total_gross_brl=s.total_gross,
        total_tax_brl=s.total_tax, total_net_brl=s.total_net, profit_net_brl=s.profit_net,
        annualized_net_pct=s.annualized_net_pct.quantize(index_data.D("0.01")) if s.annualized_net_pct is not None else None,
        flows=[FlowOut(on=f.on, kind=f.kind, gross=f.gross, tax=f.tax, net=f.net) for f in s.flows],
        assumptions=(f"Projeção com CDI de {idx.annual_rate(IndexName.CDI):.2f}% a.a. e IPCA de "
                     f"{idx.accumulated_12m(IndexName.IPCA):.2f}% (12 meses) mantidos; rendimento passado não garante o futuro."),
    )


@router.post("/invest", response_model=InvestmentOut, status_code=status.HTTP_201_CREATED)
def invest(body: InvestRequest, user: CurrentUser, db: DbSession, idempotency_key: IdemKey = None):
    portfolio = portfolio_service.get_portfolio_for_user(db, user.id)
    try:
        inv = svc.invest(db, portfolio.id, body.product_id, body.amount_brl, today_br(), idempotency_key)
    except (svc.FixedIncomeError, ledger_service.InsufficientFundsError) as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from None
    except ledger_service.DuplicateTransactionError:
        raise HTTPException(status.HTTP_409_CONFLICT, "Operação já processada (Idempotency-Key repetida)") from None
    return investment_out(svc.describe(_reload(db, inv.id), index_data.load(db), today_br()))


def _reload(db, investment_id: int):
    from backend.models import FixedIncomeInvestment
    from sqlalchemy.orm import joinedload
    return db.execute(select(FixedIncomeInvestment).where(FixedIncomeInvestment.id == investment_id)
                      .options(joinedload(FixedIncomeInvestment.product), joinedload(FixedIncomeInvestment.events))
                      ).unique().scalar_one()


@router.get("/investments", response_model=list[InvestmentOut])
def list_investments(user: CurrentUser, db: DbSession, only_active: bool = False):
    portfolio = portfolio_service.get_portfolio_for_user(db, user.id)
    idx, today = index_data.load(db), today_br()
    rows = svc.list_investments(db, portfolio.id)
    return [investment_out(svc.describe(i, idx, today)) for i in rows
            if not only_active or i.status == InvestmentStatus.ACTIVE]


@router.post("/investments/{investment_id}/redeem", response_model=InvestmentOut)
def redeem(investment_id: int, user: CurrentUser, db: DbSession):
    portfolio = portfolio_service.get_portfolio_for_user(db, user.id)
    idx, today = index_data.load(db), today_br()
    try:
        inv = svc.redeem(db, portfolio.id, investment_id, idx, today)
    except svc.FixedIncomeError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from None
    return investment_out(svc.describe(_reload(db, inv.id), idx, today))


@router.post("/refresh")
def refresh(_: CurrentUser, db: DbSession):
    """Atualiza índices e Tesouro Direto (no máximo uma vez a cada 10 minutos)."""
    return {"refreshed": fixed_income_worker.sync_all(db, min_interval=600)}
