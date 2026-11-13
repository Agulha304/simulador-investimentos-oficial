from datetime import timedelta
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from backend.core.calendar_br import add_months, business_days_between
from backend.core.dates import today_br
from backend.database import SessionLocal
from backend.models import (
    EventStatus, FinancialEvent, FixedIncomeProduct, InvestmentStatus, Portfolio, ProductSource, Transaction,
)
from backend.services import fixed_income_catalog as catalog_svc
from backend.services import fixed_income_math as fm
from backend.services import fixed_income_service as svc
from backend.services import index_data
from backend.workers import fixed_income_worker

D = Decimal
TODAY = today_br()
q2 = lambda x: D(x).quantize(D("0.01"))  # noqa: E731


@pytest.fixture
def products(client, db):
    """Catálogo sincronizado com as fontes falsas. Chaves: template (CDB...) ou tipo do título público."""
    assert fixed_income_worker.sync_all(db)
    return {p.template_key or p.product_type.value: p for p in db.scalars(
        select(FixedIncomeProduct).where(FixedIncomeProduct.is_active))}


def pid(db) -> int:
    return db.scalar(select(Portfolio.id))


def cash(db) -> Decimal:
    db.expire_all()
    return db.scalar(select(Portfolio.cash_balance))


def invest(client, h, product, amount, **kw):
    return client.post("/api/fixed-income/invest", headers=h, json={"product_id": product.id, "amount_brl": str(amount)}, **kw)


def first_investment(db):
    db.expire_all()
    return svc.list_investments(db, pid(db))[0]


# ------------------------------------------------------------------ catálogo

def test_sync_creates_treasury_and_sample_products(client, db, products):
    treasury = [p for p in products.values() if p.source == ProductSource.TESOURO_TRANSPARENTE]
    samples = [p for p in products.values() if p.source == ProductSource.SAMPLE]
    assert len(treasury) == 5 and len(samples) == len(catalog_svc.TEMPLATES) == 12
    pre = products["TESOURO_PREFIXADO"]
    assert (pre.rate, pre.market_rate, pre.unit_price, pre.issuer) == (D("14.65"), D("14.77"), D("749.2900000000"), "Tesouro Nacional")
    assert pre.uses_mtm and pre.liquidity.value == "DAILY" and pre.name.startswith("Tesouro Prefixado ")
    assert products["TESOURO_SELIC"].indexer.value == "SELIC" and not products["TESOURO_SELIC"].uses_mtm
    assert products["TESOURO_IPCA_JUROS"].payment_frequency.value == "SEMIANNUAL" and not products["TESOURO_IPCA_JUROS"].uses_mtm
    assert all("EXEMPLO" in (p.description or "") for p in samples)       # ofertas de exemplo sempre sinalizadas


def test_sample_rates_are_derived_from_real_references(client, db, products):
    assert products["cdb-pos-2a"].rate == 112 and products["lci-pos-2a"].rate == 92
    assert products["cdb-pre-3a"].rate == D("15.15")                    # Tesouro Prefixado 3a (14,65) + 0,5
    assert products["cdb-hibrido-5a"].rate == D("7.92")                 # Tesouro IPCA+ 5a (7,42) + 0,5
    assert products["cri-ipca-6a"].rate == D("8.62")                    # IPCA+ 5a (7,42) + 1,2
    assert products["lci-pos-2a"].tax_regime.value == "EXEMPT" and products["cdb-pos-2a"].tax_regime.value == "REGRESSIVE"
    assert products["cri-ipca-6a"].payment_frequency.value == "SEMIANNUAL" and products["cdb-janelas"].liquidity_dates
    assert svc.rate_label(products["cdb-pos-2a"]) == "112,00% do CDI"
    assert svc.rate_label(products["TESOURO_IPCA"]) == "IPCA + 7,42% a.a."
    assert svc.rate_label(products["cdb-pre-3a"]) == "15,15% a.a."


def test_sync_is_idempotent_and_deactivates_dropped_bonds(client, db, products, _fake_fixed_income_sources):
    _, td = _fake_fixed_income_sources
    before = db.scalar(select(func.count()).select_from(FixedIncomeProduct))
    assert fixed_income_worker.sync_all(db)
    assert db.scalar(select(func.count()).select_from(FixedIncomeProduct)) == before
    td.drop.add("Tesouro Selic")
    fixed_income_worker.sync_all(db)
    db.expire_all()
    assert not db.get(FixedIncomeProduct, products["TESOURO_SELIC"].id).is_active
    assert db.get(FixedIncomeProduct, products["TESOURO_PREFIXADO"].id).is_active


def test_expired_products_are_deactivated(client, db, products):
    p = products["cdb-pos-2a"]
    p.maturity_date = TODAY
    db.commit()
    assert catalog_svc.deactivate_expired(db, TODAY) == 1


def test_sync_survives_data_source_failure(client, db, _fake_fixed_income_sources):
    idx_provider, _ = _fake_fixed_income_sources
    idx_provider.fail = True
    assert fixed_income_worker.sync_all(db)                           # Banco Central fora: segue com os demais
    assert db.scalar(select(func.count()).select_from(FixedIncomeProduct)) == 17
    assert index_data.load(db).annual_rate(index_data.IndexName.CDI) == pytest.approx(D("13.65"), abs=D("1e-6"))  # fallback configurado


def test_products_and_indexes_endpoints(client, auth_headers, db, products):
    r = client.get("/api/fixed-income/products", headers=auth_headers)
    assert r.status_code == 200 and len(r.json()) == 17
    by_type = lambda t: client.get(f"/api/fixed-income/products?product_type={t}", headers=auth_headers).json()  # noqa: E731
    assert (len(by_type("CDB")), len(by_type("LCI")), len(by_type("LCA")), len(by_type("CRI")),
            len(by_type("CRA")), len(by_type("DEBENTURE"))) == (6, 1, 1, 1, 1, 2)
    assert all(p["tax_regime"] == "EXEMPT" for p in client.get("/api/fixed-income/products?tax_regime=EXEMPT", headers=auth_headers).json())
    assert {p["indexer"] for p in client.get("/api/fixed-income/products?indexer=IPCA", headers=auth_headers).json()} == {"IPCA"}
    assert [p["name"] for p in client.get("/api/fixed-income/products?q=liquidez", headers=auth_headers).json()] == ["CDB Liquidez Diária"]
    assert client.get("/api/fixed-income/products/999999", headers=auth_headers).status_code == 404
    assert client.get("/api/fixed-income/products").status_code == 401

    ix = client.get("/api/fixed-income/indexes", headers=auth_headers).json()
    assert D(ix["cdi_annual"]) == q2((D("1.0005") ** 252 - 1) * 100) and ix["last_cdi_date"]
    assert D(ix["ipca_12m"]) == q2((D("1.005") ** 12 - 1) * 100)


# ------------------------------------------------------------------ aplicar

def test_invest_debits_cash_and_shows_in_equity(client, auth_headers, db, products):
    r = invest(client, auth_headers, products["cdb-pos-2a"], "10000")
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["status"] == "ACTIVE" and D(body["principal_brl"]) == 10000 and body["product"]["rate_label"] == "112,00% do CDI"
    assert body["can_redeem"] is False and "só pode ser resgatado no vencimento" in body["redeem_block_reason"]
    p = client.get("/api/portfolio", headers=auth_headers).json()
    assert p["cash_balance"] == "90000.00" and p["fixed_income_invested_brl"] == "10000.00"
    assert p["fixed_income_value_brl"] == "10000.00" and p["total_equity_brl"] == "100000.00"     # aplicar não gera lucro
    tx = client.get("/api/portfolio/transactions", headers=auth_headers).json()[0]
    assert tx["type"] == "FIXED_INCOME_APPLY" and tx["cash_amount_brl"] == "-10000.00" and "CDB Pós-fixado 2 anos" in tx["note"]
    ev = first_investment(db).events
    assert [e.kind.value for e in ev] == ["MATURITY"] and ev[0].scheduled_date == products["cdb-pos-2a"].maturity_date


def test_invest_validations(client, auth_headers, db, products):
    pos = products["cdb-pos-2a"]
    assert invest(client, auth_headers, pos, "999").status_code == 422                       # abaixo do mínimo
    r = invest(client, auth_headers, pos, "200000")
    assert r.status_code == 422 and "saldo insuficiente" in r.json()["detail"]
    assert invest(client, auth_headers, pos, "1000.005").status_code == 422                  # mais de 2 casas
    assert client.post("/api/fixed-income/invest", headers=auth_headers, json={"product_id": 999999, "amount_brl": "2000"}).status_code == 422
    tes = products["TESOURO_PREFIXADO"]
    assert invest(client, auth_headers, tes, "5").status_code == 422                         # menos de 0,01 título
    pos.maturity_date = TODAY - timedelta(days=1)
    db.commit()
    r = invest(client, auth_headers, pos, "2000")
    assert r.status_code == 422 and "venceu" in r.json()["detail"]
    assert cash(db) == D("100000.00")


def test_invest_idempotency_key(client, auth_headers, db, products):
    hdr = {**auth_headers, "Idempotency-Key": "fi-1"}
    body = {"product_id": products["cdb-pos-2a"].id, "amount_brl": "2000"}
    assert client.post("/api/fixed-income/invest", headers=hdr, json=body).status_code == 201
    assert client.post("/api/fixed-income/invest", headers=hdr, json=body).status_code == 409
    assert cash(db) == D("98000.00") and len(svc.list_investments(db, pid(db))) == 1


def test_treasury_units_follow_unit_price(client, auth_headers, db, products):
    r = invest(client, auth_headers, products["TESOURO_PREFIXADO"], "1000")
    assert r.status_code == 201
    assert D(r.json()["units"]) == (D("1000") / D("749.29")).quantize(D("1e-18"), rounding="ROUND_DOWN")


# ------------------------------------------------------------------ valor e imposto ao longo do tempo

def test_cdi_accrual_and_regressive_ir(client, auth_headers, db, products):
    invest(client, auth_headers, products["cdb-liquidez-diaria"], "10000")
    inv, idx = first_investment(db), index_data.load(db)
    target = TODAY + timedelta(days=400)
    n = business_days_between(TODAY, target)
    gross = q2(D(10000) * D("1.0005") ** n)                                    # 100% do CDI a 0,05% ao dia
    v = svc.describe(inv, idx, target)
    assert abs(v.current_gross - gross) <= D("0.01") and v.method == "CURVE"
    assert v.estimated_tax == q2((v.current_gross - 10000) * D("0.175"))           # 400 dias: 17,5%
    assert v.estimated_net == v.current_gross - v.estimated_tax

    long_target = TODAY + timedelta(days=800)                                  # > 720 dias: 15%
    v2 = svc.describe(inv, idx, long_target)
    assert v2.estimated_tax == q2((v2.current_gross - 10000) * D("0.15"))
    assert v2.estimated_net > v.estimated_net


def test_lci_is_tax_exempt(client, auth_headers, db, products):
    invest(client, auth_headers, products["lci-pos-2a"], "10000")
    v = svc.describe(first_investment(db), index_data.load(db), TODAY + timedelta(days=500))
    assert v.estimated_tax == 0 and v.current_gross > 10000 and v.estimated_net == v.current_gross


# ------------------------------------------------------------------ resgate antecipado

def test_at_maturity_product_cannot_be_redeemed(client, auth_headers, db, products):
    inv_id = invest(client, auth_headers, products["cdb-pos-2a"], "5000").json()["id"]
    r = client.post(f"/api/fixed-income/investments/{inv_id}/redeem", headers=auth_headers)
    assert r.status_code == 422 and "só pode ser resgatado no vencimento" in r.json()["detail"]
    assert cash(db) == D("95000.00")


def test_daily_liquidity_redeem_same_day_and_double_redeem(client, auth_headers, db, products):
    inv_id = invest(client, auth_headers, products["cdb-liquidez-diaria"], "10000").json()["id"]
    r = client.post(f"/api/fixed-income/investments/{inv_id}/redeem", headers=auth_headers)
    assert r.status_code == 200 and r.json()["status"] == "REDEEMED"
    assert cash(db) == D("100000.00")                                           # sem rendimento, sem imposto
    tx = client.get("/api/portfolio/transactions", headers=auth_headers).json()[0]
    assert tx["type"] == "FIXED_INCOME_REDEEM" and tx["realized_pnl_brl"] == "0.00"
    assert client.post(f"/api/fixed-income/investments/{inv_id}/redeem", headers=auth_headers).status_code == 422
    assert cash(db) == D("100000.00")


def test_iof_applies_in_first_30_days(client, auth_headers, db, products):
    client.post("/api/portfolio/deposit", headers=auth_headers, json={"amount": "100000"})
    invest(client, auth_headers, products["cdb-liquidez-diaria"], "100000")
    inv, idx = first_investment(db), index_data.load(db)
    on = TODAY + timedelta(days=10)
    before = cash(db)
    svc.redeem(db, inv.portfolio_id, inv.id, idx, on)
    gross = q2(D(100000) * D("1.0005") ** business_days_between(TODAY, on))
    gain = gross - 100000
    iof = q2(gain * D("0.66"))                                                  # dia 10: 66% do rendimento
    ir = q2((gain - iof) * D("0.225"))
    tx = db.scalar(select(Transaction).where(Transaction.type == "FIXED_INCOME_REDEEM"))
    assert abs(tx.gross_amount_brl - gross) <= D("0.01") and abs(tx.tax_brl - (iof + ir)) <= D("0.02")
    assert cash(db) - before == tx.cash_amount_brl == tx.gross_amount_brl - tx.tax_brl


def test_grace_period_blocks_until_day_90(client, auth_headers, db, products):
    inv_id = invest(client, auth_headers, products["cdb-carencia-90d"], "5000").json()["id"]
    r = client.post(f"/api/fixed-income/investments/{inv_id}/redeem", headers=auth_headers)
    assert r.status_code == 422 and "carência" in r.json()["detail"].lower() and f"{TODAY + timedelta(days=90):%d/%m/%Y}" in r.json()["detail"]
    inv, idx = first_investment(db), index_data.load(db)
    with pytest.raises(svc.FixedIncomeError):
        svc.redeem(db, inv.portfolio_id, inv.id, idx, TODAY + timedelta(days=89))
    done = svc.redeem(db, inv.portfolio_id, inv.id, idx, TODAY + timedelta(days=90))
    assert done.status == InvestmentStatus.REDEEMED and done.closed_net_brl > 5000 - 1


def test_redemption_windows(client, auth_headers, db, products):
    invest(client, auth_headers, products["cdb-janelas"], "5000")
    inv, idx = first_investment(db), index_data.load(db)
    with pytest.raises(svc.FixedIncomeError, match="janelas"):
        svc.redeem(db, inv.portfolio_id, inv.id, idx, TODAY + timedelta(days=10))
    window = add_months(TODAY, 6)
    assert svc.redemption_block_reason(inv, window) is None
    assert svc.redeem(db, inv.portfolio_id, inv.id, idx, window).status == InvestmentStatus.REDEEMED


def test_secondary_market_discount_on_credit_products(client, auth_headers, db, products):
    invest(client, auth_headers, products["cra-cdi-4a"], "5000")
    inv, idx = first_investment(db), index_data.load(db)
    on = TODAY + timedelta(days=40)                                             # carência de 30 dias já passou
    quote = svc.quote_redemption(inv, idx, on, apply_discount=True)
    assert quote.discount_brl == q2(quote.gross_value * D("0.025")) and quote.tax.total_brl == 0     # CRA: isento
    svc.redeem(db, inv.portfolio_id, inv.id, idx, on)
    tx = db.scalar(select(Transaction).where(Transaction.type == "FIXED_INCOME_REDEEM"))
    assert tx.cash_amount_brl == quote.net and "deságio" in tx.note
    assert tx.realized_pnl_brl == quote.net - 5000


def test_treasury_mark_to_market_on_early_sale(client, auth_headers, db, products):
    r = invest(client, auth_headers, products["TESOURO_PREFIXADO"], "1000")
    assert r.json()["valuation_method"] == "MTM"
    assert D("990") < D(r.json()["estimated_net_brl"]) < D("1000")              # taxa de venda um pouco acima da de compra
    inv_id = r.json()["id"]
    r = client.post(f"/api/fixed-income/investments/{inv_id}/redeem", headers=auth_headers)
    assert r.status_code == 200 and D("990") < cash(db) - D("99000") < D("1000")
    tx = db.scalar(select(Transaction).where(Transaction.type == "FIXED_INCOME_REDEEM"))
    assert tx.tax_brl == 0 and tx.realized_pnl_brl < 0                          # prejuízo: sem imposto
    assert invest(client, auth_headers, products["TESOURO_SELIC"], "1000").json()["valuation_method"] == "CURVE"


# ------------------------------------------------------------------ eventos: cupons e vencimento

def test_coupons_and_maturity_match_the_simulation(client, auth_headers, db, products):
    cra = products["cra-cdi-4a"]
    sim_idx = index_data.load(db)
    expected = fm.simulate_cashflows(svc.terms_of(cra), D(5000), TODAY, sim_idx)
    assert len(expected) > 5 and expected[-1].kind == "MATURITY"
    invest(client, auth_headers, cra, "5000")
    inv = first_investment(db)
    coupons = [e for e in inv.events if e.kind.value == "COUPON"]
    assert len(coupons) == len(expected) - 1 and all(e.status == EventStatus.PENDING for e in inv.events)

    idx = index_data.load(db)
    assert svc.process_due_events(db, idx, coupons[0].scheduled_date - timedelta(days=1)) == 0     # ainda não venceu
    assert svc.process_due_events(db, idx, coupons[0].scheduled_date) == 1
    assert svc.process_due_events(db, idx, coupons[0].scheduled_date) == 0                         # idempotente
    tx = db.scalar(select(Transaction).where(Transaction.type == "FIXED_INCOME_COUPON"))
    assert tx.cash_amount_brl == expected[0].net and tx.idempotency_key.startswith("fi-event:")
    assert tx.source.value == "FIXED_INCOME_WORKER"
    db.expire_all()
    assert db.get(type(inv), inv.id).interest_paid_net_brl == expected[0].net

    assert svc.process_due_events(db, idx, cra.maturity_date + timedelta(days=3)) == len(expected) - 1
    assert svc.process_due_events(db, idx, cra.maturity_date + timedelta(days=30)) == 0
    db.expire_all()
    inv = first_investment(db)
    assert inv.status == InvestmentStatus.MATURED and inv.closed_net_brl == expected[-1].net
    assert cash(db) == D("100000") - 5000 + sum((f.net for f in expected), D(0))
    assert db.scalar(select(func.count()).select_from(Transaction).where(Transaction.type == "FIXED_INCOME_COUPON")) == len(coupons)
    mat = db.scalar(select(Transaction).where(Transaction.type == "FIXED_INCOME_MATURITY"))
    assert mat.realized_pnl_brl == expected[-1].net - 5000


def test_treasury_maturity_pays_15_percent_ir_after_two_years(client, auth_headers, db, products):
    tes = products["TESOURO_IPCA"]
    invest(client, auth_headers, tes, "1000")
    idx = index_data.load(db)
    assert svc.process_due_events(db, idx, tes.maturity_date) == 1
    tx = db.scalar(select(Transaction).where(Transaction.type == "FIXED_INCOME_MATURITY"))
    assert tx.tax_brl == q2((tx.gross_amount_brl - 1000) * D("0.15")) and tx.gross_amount_brl > 1000
    assert tx.cash_amount_brl == tx.gross_amount_brl - tx.tax_brl


def test_redeeming_cancels_pending_events(client, auth_headers, db, products):
    invest(client, auth_headers, products["cdb-liquidez-diaria"], "2000")
    inv, idx = first_investment(db), index_data.load(db)
    svc.redeem(db, inv.portfolio_id, inv.id, idx, TODAY + timedelta(days=5))
    db.expire_all()
    assert all(e.status == EventStatus.CANCELLED for e in first_investment(db).events)
    assert svc.process_due_events(db, idx, products["cdb-liquidez-diaria"].maturity_date + timedelta(days=1)) == 0


def test_two_workers_cannot_pay_the_same_event_twice(client, auth_headers, db, products):
    invest(client, auth_headers, products["cdb-pos-2a"], "3000")
    ev = first_investment(db).events[0]
    idx = index_data.load(db)
    with SessionLocal() as s1, SessionLocal() as s2:
        assert svc._pay_event(s1, ev.id, idx) is True
        assert svc._pay_event(s2, ev.id, idx) is False
    assert db.scalar(select(func.count()).select_from(Transaction).where(Transaction.type == "FIXED_INCOME_MATURITY")) == 1


def test_investment_keeps_contracted_rate_when_offer_changes(client, auth_headers, db, products):
    pos = products["cdb-pos-2a"]
    invest(client, auth_headers, pos, "5000")
    pos.rate = D("90")                                                           # oferta piorou depois da compra
    db.commit()
    inv = first_investment(db)
    assert inv.rate == 112 and svc.terms_of(inv).rate == 112


# ------------------------------------------------------------------ simulação

def test_simulation_endpoint(client, auth_headers, db, products):
    cdb = products["cdb-pos-2a"]
    r = client.post("/api/fixed-income/simulate", headers=auth_headers, json={"product_id": cdb.id, "amount_brl": "10000"})
    assert r.status_code == 200, r.text
    s = r.json()
    assert len(s["flows"]) == 1 and s["flows"][0]["kind"] == "MATURITY"
    gross = D(s["total_gross_brl"])
    assert D(s["total_tax_brl"]) == q2((gross - 10000) * D("0.15"))              # 2 anos ou mais: 15%
    assert D(s["profit_net_brl"]) == D(s["total_net_brl"]) - 10000 and 10 < D(s["annualized_net_pct"]) < 14
    assert "CDI" in s["assumptions"]
    cra = client.post("/api/fixed-income/simulate", headers=auth_headers,
                      json={"product_id": products["cra-cdi-4a"].id, "amount_brl": "5000"}).json()
    assert len(cra["flows"]) > 5 and D(cra["total_tax_brl"]) == 0 and cra["annualized_net_pct"] is None   # isento; com cupons
    assert client.post("/api/fixed-income/simulate", headers=auth_headers, json={"product_id": 999999, "amount_brl": "100"}).status_code == 404


def test_list_investments_endpoint_and_isolation(client, auth_headers, db, products):
    invest(client, auth_headers, products["cdb-liquidez-diaria"], "2000")
    invest(client, auth_headers, products["lci-pos-2a"], "3000")
    rows = client.get("/api/fixed-income/investments", headers=auth_headers).json()
    assert [r["product"]["name"] for r in rows] == ["LCI Pós-fixada 2 anos", "CDB Liquidez Diária"]
    assert rows[0]["next_event_kind"] == "MATURITY" and rows[1]["can_redeem"] is True
    other = client.post("/api/auth/register", json={"email": "z@example.com", "name": "Z", "password": "segredo123"}).json()
    h2 = {"Authorization": f"Bearer {other['access_token']}"}
    assert client.get("/api/fixed-income/investments", headers=h2).json() == []
    assert client.post(f"/api/fixed-income/investments/{rows[1]['id']}/redeem", headers=h2).status_code == 422   # não é dele


def test_scheduler_registers_fixed_income_jobs():
    from backend.workers.scheduler import shutdown_scheduler, start_scheduler
    sch = start_scheduler()
    try:
        assert {"fixed_income_sync", "fixed_income_events"} <= {j.id for j in sch.get_jobs()}
    finally:
        shutdown_scheduler()
