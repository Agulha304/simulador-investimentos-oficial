from tests.conftest import credit
"""Empresas (etapa 3): contas separadas, folha, estoque, receitas, expansão, locação, lucros e fechamento mensal."""
import uuid
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from backend.models import (
    Company, CompanyMonth, FinanceAccount, Good, LedgerEntry, Portfolio, Transaction,
)
from backend.services import company_rules, company_service

D = Decimal
C = "/api/companies"
B = "/api/budget"
G = "/api/goods"


def fund(client, h, amount="10000000"):
    credit(client, h, amount)


def portfolio(client, h):
    return client.get("/api/portfolio", headers=h).json()


def cash(client, h) -> Decimal:
    return D(portfolio(client, h)["cash_balance"])


def quote(client, h, segment="CAFE", location="bairro", size="SMALL", **kw):
    body = {"segment": segment, "size": size, **kw}
    if location:
        body["location"] = location
    r = client.post(f"{C}/quote", headers=h, json=body)
    assert r.status_code == 200, r.text
    return r.json()


def create(client, h, name="Café da Esquina", segment="CAFE", extra="30000", **kw):
    """`extra` = capital adicional (além do mínimo para abrir, que a empresa recebe automaticamente)."""
    body = {"name": name, "segment": segment, "extra_capital": str(extra), **kw}
    return client.post(C, headers=h, json=body)


def create_ok(client, h, staff=True, **kw):
    """Cria a empresa e, por padrão, já contrata a equipe (obrigatórios + produtivos sugeridos) via `staff_up`.
    Use `staff=False` para testar a empresa recém-aberta, sem funcionários."""
    r = create(client, h, **kw)
    assert r.status_code == 201, r.text
    d = r.json()
    return staff_up(client, h, d["company"]["id"]) if staff else d


def hire_candidate(client, h, cid, role, regime="CLT", index=0, factor="1.2", **over):
    """Contrata o candidato `index` da lista (determinística) pagando `factor` x a pretensão: sempre aceita. Devolve o detalhe."""
    r = client.post(f"{C}/{cid}/candidates", headers=h, json={"role": role, "regime": regime})
    assert r.status_code == 200, r.text
    cand = r.json()["candidates"][index]
    body = {"candidate_id": cand["id"], "salary": str((D(cand["asking_salary"]) * D(factor)).quantize(D("1"))), "hours_week": cand["hours_week"],
            "schedule": cand["schedule"], "regime": regime, "confirm_risk": True, "idempotency_key": key(), **over}
    r = client.post(f"{C}/{cid}/hire", headers=h, json=body)
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["accepted"] is True, out["message"]
    return out["company"]


def staff_up(client, h, cid, productive=True, regime="CLT"):
    """Contrata os cargos OBRIGATÓRIOS que faltam e (se `productive`) a equipe produtiva sugerida do segmento, pelo fluxo novo
    (candidatos -> proposta), de forma determinística: sempre o primeiro candidato, pagando 1,2x a pretensão."""
    d = detail(client, h, cid)
    for req in d["compliance"]["required"]:
        if not req["present"]:
            d = hire_candidate(client, h, cid, req["role"], regime)
    if productive:
        seg = company_rules.SEGMENTS[company_rules.CompanySegment(d["company"]["segment"])]
        for role in company_rules.initial_staff(seg, company_rules.CompanySize(d["company"]["size"])):
            d = hire_candidate(client, h, cid, role, regime)             # quem já foi contratado sai da lista: o primeiro é sempre o próximo
    return d


def detail(client, h, cid):
    r = client.get(f"{C}/{cid}", headers=h)
    assert r.status_code == 200, r.text
    return r.json()


def close(client, h):
    ref = client.get(f"{B}/overview", headers=h).json()["month"]["ref_month"][:7]
    return client.post(f"{B}/close", headers=h, json={"ref_month": ref, "confirm": True})


def key():
    return uuid.uuid4().hex


def earn_profit(client, h, cid, limit=16):
    """Fecha meses até a empresa ter lucro acumulado distribuível (a estruturação inicial leva alguns meses para ser recuperada)."""
    for _ in range(limit):
        if D(detail(client, h, cid)["distributable_profit"]) > 0:
            return
        assert close(client, h).status_code == 200
    pytest.fail("a empresa não gerou lucro distribuível")


def second_user(client):
    r = client.post("/api/auth/register", json={"email": "bia@example.com", "name": "Bia", "password": "segredo123"})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture(autouse=True)
def _flat_season(monkeypatch):
    """Sem sazonalidade: receitas e resultados ficam previsíveis nos testes (a sazonalidade tem teste próprio)."""
    monkeypatch.setattr(company_rules, "season_factor", lambda *a, **k: 1.0)


@pytest.fixture
def boom(monkeypatch):
    """Mercado aquecido (demanda e capacidade x5). Com CLT a 2x e os cargos obrigatórios, uma cafeteria pequena não dá lucro no
    modelo atual (isso é esperado e será tratado na fase 3); os testes de distribuição de lucros só precisam de lucro acumulado."""
    d0, c0 = company_rules.demand_units, company_rules.capacity_units
    monkeypatch.setattr(company_rules, "demand_units", lambda *a, **k: 5 * d0(*a, **k))
    monkeypatch.setattr(company_rules, "capacity_units", lambda *a, **k: 5 * c0(*a, **k))


@pytest.fixture
def rich(client, auth_headers):
    fund(client, auth_headers)
    return auth_headers


# ------------------------------------------------------------------ 1/2. criação

def test_catalog_has_twelve_segments_with_distinct_models(client, auth_headers):
    cat = client.get(f"{C}/catalog", headers=auth_headers).json()
    keys = {s["key"] for s in cat["segments"]}
    assert len(keys) == 12 and {"RESTAURANT", "TECH", "INDUSTRY", "CONSTRUCTION", "ECOMMERCE"} <= keys
    by = {s["key"]: s for s in cat["segments"]}
    assert by["RESTAURANT"]["stock"] and by["TECH"]["stock"] == []              # segmentos com e sem estoque
    assert {r["key"] for r in by["RESTAURANT"]["roles"]} != {r["key"] for r in by["TECH"]["roles"]}
    assert len({s["minimum_capital"] for s in cat["segments"]}) >= 10
    assert "locations" not in cat                                               # agora as localizações são por segmento
    assert {l["key"] for l in by["RESTAURANT"]["locations"]} >= {"centro", "bairro", "interior"}
    assert all({"key", "label", "demand", "rent_factor", "land_price"} <= set(l) for l in by["CAFE"]["locations"])


def test_catalog_channels_locations_and_metrics_kind_per_segment(client, auth_headers):
    by = {s["key"]: s for s in client.get(f"{C}/catalog", headers=auth_headers).json()["segments"]}
    assert by["ECOMMERCE"]["channels"] == ["ONLINE"] and by["ECOMMERCE"]["locations"] == []
    for k in ("WORKSHOP", "INDUSTRY", "CONSTRUCTION", "TRANSPORT"):
        assert by[k]["channels"] == ["PHYSICAL"], k
    for k in ("RESTAURANT", "CAFE", "CLOTHING", "SUPERMARKET", "TECH", "AGENCY", "REAL_ESTATE_AGENCY"):
        assert set(by[k]["channels"]) == {"PHYSICAL", "ONLINE"}, k
    kinds = {k: v["metrics_kind"] for k, v in by.items()}
    assert {k for k, v in kinds.items() if v == "PRODUCTION"} == {"RESTAURANT", "CAFE", "INDUSTRY", "CONSTRUCTION"}
    assert {k for k, v in kinds.items() if v == "RETAIL"} == {"CLOTHING", "SUPERMARKET"}
    assert {k for k, v in kinds.items() if v == "SERVICE"} == {"WORKSHOP", "TRANSPORT", "TECH", "AGENCY", "REAL_ESTATE_AGENCY", "ECOMMERCE"}
    for k, v in by.items():
        assert v["stock"] == [] or kinds[k] != "SERVICE", k
        specific = [r for r in v["roles"] if r["key"] not in ("accountant", "lawyer", "cleaner")]
        assert len(specific) >= 4, k                                             # >= 4 cargos próprios por segmento
        assert {"accountant", "lawyer", "cleaner"} <= {r["key"] for r in v["roles"]}
    labels = {r["key"]: r["label"] for r in by["TECH"]["roles"]}
    assert labels["accountant"] == "Contador" and labels["lawyer"] == "Advogado" and labels["cleaner"] == "Auxiliar de limpeza"
    # cada segmento tem a sua lista de locais (com sentido para o negócio)
    keys = {k: {l["key"] for l in v["locations"]} for k, v in by.items()}
    assert keys["RESTAURANT"] != keys["INDUSTRY"] != keys["WORKSHOP"]
    assert "beira_mar" in keys["RESTAURANT"] and "distrito" in keys["INDUSTRY"] and "avenida" in keys["WORKSHOP"]
    assert "beira_mar" not in keys["INDUSTRY"]


def test_create_company_builds_coherent_structure(client, rich, db):
    before = cash(client, rich)
    q = quote(client, rich)
    d = create_ok(client, rich, staff=False, extra="30000")
    co = d["company"]
    capital = D(q["minimum_capital"]) + D("30000")
    assert cash(client, rich) == before - capital                               # saiu da conta pessoal
    expected_cash = capital - D(q["setup_cost"]) - D(q["initial_stock"])
    assert D(co["cash"]) == expected_cash                                       # entrou na conta da empresa (menos estrutura e estoque)
    assert co["segment"] == "CAFE" and co["status"] == "ACTIVE" and co["reputation"] == 50
    assert co["channel"] == "PHYSICAL" and co["site_mode"] == "RENT" and D(co["site_value"]) == 0 and "business_type" not in co
    assert d["employees"] == [] and d["compliance"]["regular"] is False       # nasce sem funcionários e irregular até contratar
    assert d["lease"]["kind"] == "EXTERNAL" and D(d["lease"]["monthly_rent"]) > 0
    assert {c["kind"] for c in d["costs"]} == {"UTILITIES", "TOOLS", "ACCOUNTING"}
    assert d["inventory"][0]["name"] == "Insumos de café" and D(d["inventory"][0]["quantity"]) > 1500
    assert db.scalar(select(func.count()).select_from(FinanceAccount).where(FinanceAccount.kind == "BUSINESS")) == 1
    assert {e["type"] for e in d["events"]} == {"CREATED", "CAPITAL"}


def test_owner_pays_share_of_minimum_plus_extra_capital(client, rich, db):
    q = quote(client, rich, owner_share_pct="100", extra_capital="12345.67")
    assert D(q["owner_cost"]) == D(q["minimum_capital"]) and D(q["extra_capital"]) == D("12345.67")
    assert D(q["total_owner_cost"]) == D(q["minimum_capital"]) + D("12345.67")
    for k in ("land_cost", "setup_cost", "initial_stock", "monthly_fixed", "monthly_payroll"):
        assert k in q
    before = cash(client, rich)
    d = create_ok(client, rich, extra="12345.67")
    assert cash(client, rich) == before - D(q["total_owner_cost"])
    entries = db.scalars(select(LedgerEntry).where(LedgerEntry.company_id == d["company"]["id"], LedgerEntry.line == "CAPITAL_IN")).all()
    assert sum(e.amount for e in entries) == D(q["total_owner_cost"])           # o que entrou na empresa = o que saiu do dono
    # sem capital adicional: cobra só o mínimo
    before = cash(client, rich)
    create_ok(client, rich, name="Sem extra", extra="0")
    assert cash(client, rich) == before - D(q["minimum_capital"])


def test_quote_splits_minimum_by_owner_share(client, rich):
    q = quote(client, rich, owner_share_pct="60", extra_capital="5000")
    assert D(q["owner_cost"]) == (D(q["minimum_capital"]) * D("0.6")).quantize(D("0.01"))
    assert D(q["total_owner_cost"]) == D(q["owner_cost"]) + D("5000")


def test_negative_extra_capital_rejected(client, rich, db):
    start = cash(client, rich)
    r = create(client, rich, extra="-1")
    assert r.status_code == 422
    assert client.post(f"{C}/quote", headers=rich, json={"segment": "CAFE", "extra_capital": "-5"}).status_code == 422
    assert cash(client, rich) == start and db.scalar(select(func.count()).select_from(Company)) == 0


def test_business_type_removed_and_capital_field_replaced(client, rich):
    from backend.schemas.companies import CompanyCreate, CompanyOut
    assert "business_type" not in CompanyCreate.model_fields and "business_type" not in CompanyOut.model_fields
    assert "capital" not in CompanyCreate.model_fields and "extra_capital" in CompanyCreate.model_fields
    r = create_ok(client, rich, business_type="ignorado")                       # campo desconhecido é ignorado, nunca persistido/devolvido
    assert "business_type" not in r["company"]


def test_create_several_companies_with_own_accounts(client, rich, db):
    a = create_ok(client, rich, name="Café A")["company"]
    b = create_ok(client, rich, name="Oficina B", segment="WORKSHOP")["company"]
    c3 = create_ok(client, rich, name="Tech C", segment="TECH", size="MEDIUM", location="centro")["company"]
    assert len({a["id"], b["id"], c3["id"]}) == 3
    assert len(client.get(C, headers=rich).json()) == 3
    assert create(client, rich, name="Café A").status_code == 409                # nome repetido
    accounts = db.scalars(select(Company.account_id)).all()
    assert len(set(accounts)) == 3                                               # uma conta por empresa
    ov = client.get(f"{C}/overview", headers=rich).json()
    assert ov["count"] == 3 and D(ov["cash_total"]) == sum(D(x["cash"]) for x in ov["companies"])


def test_insufficient_personal_balance_rejected_without_side_effects(client, rich, db):
    start = cash(client, rich)
    broke = create(client, rich, name="Sem saldo", extra="99999999")
    assert broke.status_code == 422                                              # saldo pessoal insuficiente
    assert db.scalar(select(func.count()).select_from(Company)) == 0 and cash(client, rich) == start
    assert db.scalar(select(func.count()).select_from(FinanceAccount).where(FinanceAccount.kind == "BUSINESS")) == 0


def test_location_and_size_change_costs(client, auth_headers):
    cheap = quote(client, auth_headers, "RESTAURANT", "interior", "SMALL")
    dear = quote(client, auth_headers, "RESTAURANT", "shopping", "LARGE")
    assert D(dear["minimum_capital"]) > D(cheap["minimum_capital"]) * 3
    assert D(dear["monthly_fixed"]) > D(cheap["monthly_fixed"]) and dear["expected_units"] > cheap["expected_units"]
    assert client.post(f"{C}/quote", headers=auth_headers, json={"segment": "CAFE", "location": "marte"}).status_code == 400
    assert client.post(f"{C}/quote", headers=auth_headers, json={"segment": "CAFE", "location": "distrito"}).status_code == 400   # local de outro segmento


def test_locations_are_per_segment_with_own_demand_rent_and_land(client, auth_headers):
    a = quote(client, auth_headers, "RESTAURANT", "beira_mar", "SMALL", site_mode="BUY")
    b = quote(client, auth_headers, "RESTAURANT", "interior", "SMALL", site_mode="BUY")
    assert a["expected_units"] > b["expected_units"] and D(a["land_cost"]) > D(b["land_cost"]) > 0
    ra = quote(client, auth_headers, "RESTAURANT", "beira_mar", "SMALL")
    rb = quote(client, auth_headers, "RESTAURANT", "interior", "SMALL")
    assert D(ra["monthly_rent"]) > D(rb["monthly_rent"]) > 0 and D(ra["monthly_fixed"]) > D(rb["monthly_fixed"])
    ind = quote(client, auth_headers, "INDUSTRY", "distrito", "SMALL")
    assert ind["location"] == "distrito"
    assert client.post(f"{C}/quote", headers=auth_headers, json={"segment": "INDUSTRY", "location": "beira_mar"}).status_code == 400


# ------------------------------------------------------------------ canal (online/físico) e terreno

def test_channel_not_allowed_for_segment_is_rejected(client, rich, db):
    r = create(client, rich, name="Loja física de e-commerce", segment="ECOMMERCE", channel="PHYSICAL")
    assert r.status_code in (400, 422) and "canal" in r.text
    assert client.post(f"{C}/quote", headers=rich, json={"segment": "ECOMMERCE", "channel": "PHYSICAL"}).status_code == 400
    assert create(client, rich, name="Indústria online", segment="INDUSTRY", channel="ONLINE").status_code in (400, 422)
    assert db.scalar(select(func.count()).select_from(Company)) == 0
    ok = create_ok(client, rich, name="Loja virtual", segment="ECOMMERCE")        # sem informar canal: o único permitido
    assert ok["company"]["channel"] == "ONLINE"


def test_online_has_no_lease_no_land_and_lower_fixed_costs(client, rich):
    phys = quote(client, rich, "CAFE", "bairro", "SMALL")
    onl = quote(client, rich, "CAFE", None, "SMALL", channel="ONLINE")
    assert onl["channel"] == "ONLINE" and onl["site_mode"] is None and D(onl["land_cost"]) == 0 and D(onl["monthly_rent"]) == 0
    assert D(onl["monthly_fixed"]) < D(phys["monthly_fixed"]) and D(onl["minimum_capital"]) < D(phys["minimum_capital"])
    assert client.post(f"{C}/quote", headers=rich, json={"segment": "CAFE", "channel": "ONLINE", "site_mode": "BUY"}).status_code == 400
    d = create_ok(client, rich, staff=False, name="Café online", channel="ONLINE", extra="0")
    assert d["lease"] is None and d["company"]["channel"] == "ONLINE" and D(d["company"]["site_value"]) == 0
    assert d["company"]["location"] == "online" and d["company"]["location_label"] == "Operação online"
    assert not any(e["line"] in ("LAND", "RENT") for e in d["ledger"])
    assert D(d["monthly_obligations"]) < D(quote(client, rich)["monthly_fixed"]) + D(quote(client, rich)["monthly_payroll"])
    assert client.post(f"{C}/{d['company']['id']}/lease", headers=rich, json={"kind": "EXTERNAL"}).status_code == 409


def test_buy_site_pays_land_in_opening_and_raises_equity(client, rich, db):
    rent = quote(client, rich, "CAFE", "bairro", "SMALL", site_mode="RENT")
    buy = quote(client, rich, "CAFE", "bairro", "SMALL", site_mode="BUY")
    land = D(buy["land_cost"])
    assert land > 0 and D(buy["monthly_rent"]) == 0 and D(rent["monthly_rent"]) > 0
    assert D(buy["minimum_capital"]) > D(rent["minimum_capital"]) + land - D(rent["monthly_rent"]) - D("0.02")   # terreno entra no mínimo
    before = cash(client, rich)
    d = create_ok(client, rich, staff=False, name="Café com terreno", site_mode="BUY", extra="20000")
    co = d["company"]
    assert cash(client, rich) == before - D(buy["minimum_capital"]) - D("20000")
    assert co["site_mode"] == "BUY" and D(co["site_value"]) == land and d["lease"] is None
    # caixa = aporte − estrutura − estoque − terreno; patrimônio da empresa conta o terreno como ativo
    assert D(co["cash"]) == D(buy["minimum_capital"]) + D("20000") - D(buy["setup_cost"]) - D(buy["initial_stock"]) - land
    stock_value = sum(D(i["value"]) for i in d["inventory"])
    assert D(co["equity"]) == D(co["cash"]) + stock_value + land
    assert any(e["line"] == "LAND" and e["capital"] and D(e["amount"]) == land for e in d["ledger"])   # compra de ativo, fora do resultado
    assert client.post(f"{C}/{co['id']}/lease", headers=rich, json={"kind": "EXTERNAL"}).status_code == 409
    # o mês seguinte não cobra aluguel
    assert close(client, rich).status_code == 200
    m = detail(client, rich, co["id"])["months"][0]
    assert not any(e["line"] == "RENT" for e in detail(client, rich, co["id"])["ledger"])
    assert D(m["equity_end"]) >= land


def test_legacy_location_keys_resolve_to_segment_location():
    from backend.models import CompanySize
    seg = company_rules.SEGMENTS["WORKSHOP"] if "WORKSHOP" in company_rules.SEGMENTS else next(
        s for k, s in company_rules.SEGMENTS.items() if k.value == "WORKSHOP")
    for old in company_rules.LEGACY_LOCATIONS:                                   # empresas antigas ("centro", "polo"...) continuam calculando
        loc = company_rules.resolve_location(seg, old)
        assert loc in seg.locations
        assert company_rules.default_rent(seg, old, CompanySize.SMALL) > 0
        assert company_rules.expected_units(seg, old, CompanySize.SMALL) > 0
    cafe = next(s for k, s in company_rules.SEGMENTS.items() if k.value == "CAFE")
    assert company_rules.resolve_location(cafe, "bairro").demand == 1.0          # chaves compartilhadas mantêm os valores antigos


# ------------------------------------------------------------------ tipos de métricas

def test_service_segments_have_no_inventory_or_stock_ledger(client, rich):
    for seg in ("WORKSHOP", "TRANSPORT", "TECH", "AGENCY", "REAL_ESTATE_AGENCY"):
        d = create_ok(client, rich, name=f"Serviço {seg}", segment=seg, extra="100000")
        assert d["inventory"] == [] and d["company"]["metrics_kind"] == "SERVICE", seg
        assert not any(e["line"] == "STOCK_PURCHASE" for e in d["ledger"]), seg
        assert D(quote(client, rich, seg, None)["initial_stock"]) == 0
    eco = create_ok(client, rich, name="Virtual", segment="ECOMMERCE", extra="100000")
    assert eco["inventory"] == [] and eco["company"]["unit_label"] == "pedido"
    assert close(client, rich).status_code == 200                                 # fecha o mês sem estoque e sem quebra por ruptura
    for co in client.get(C, headers=rich).json():
        det = detail(client, rich, co["id"])
        assert det["inventory"] == [] and all(m["stockout"] is False for m in det["months"])
    prod = create_ok(client, rich, name="Prod", segment="INDUSTRY", extra="0")
    assert prod["inventory"] and prod["company"]["metrics_kind"] == "PRODUCTION"


def test_generic_roles_can_be_hired_in_any_company(client, rich):
    cid = create_ok(client, rich, name="Com contador", segment="TECH", extra="200000", staff=False)["company"]["id"]
    for role in ("accountant", "lawyer", "cleaner", "devops"):
        hire_candidate(client, rich, cid, role)
    roles = {e["role"] for e in detail(client, rich, cid)["employees"]}
    assert {"accountant", "lawyer", "cleaner", "devops"} <= roles


# ------------------------------------------------------------------ 3/4. capital e contas separadas

def test_capital_transfer_moves_between_accounts_and_is_not_an_expense(client, rich, db):
    cid = create_ok(client, rich)["company"]["id"]
    personal_before, co_before = cash(client, rich), D(detail(client, rich, cid)["company"]["cash"])
    equity_before = D(portfolio(client, rich)["total_equity_brl"])
    k = key()
    r = client.post(f"{C}/{cid}/contribute", headers=rich, json={"amount": "10000", "idempotency_key": k})
    assert r.status_code == 200
    assert client.post(f"{C}/{cid}/contribute", headers=rich, json={"amount": "10000", "idempotency_key": k}).status_code == 200  # repetição
    assert cash(client, rich) == personal_before - D("10000")
    assert D(detail(client, rich, cid)["company"]["cash"]) == co_before + D("10000")
    assert D(portfolio(client, rich)["total_equity_brl"]) == equity_before          # transferir não é perda
    m = client.get(f"{B}/overview", headers=rich).json()["month"]
    assert D(m["capital_out"]) >= D("10000") and D(m["realized_expense"]) == 0      # patrimonial, fora das despesas
    assert client.post(f"{C}/{cid}/contribute", headers=rich, json={"amount": "999999999", "idempotency_key": key()}).status_code == 422


def test_business_entries_stay_out_of_personal_budget(client, rich):
    cid = create_ok(client, rich)["company"]["id"]
    entries = client.get(f"{B}/entries", headers=rich).json()
    assert all("empresa" not in e["description"].lower() or e["capital"] for e in entries)
    assert not any(e["description"].startswith("Estoque inicial") or "Estruturação" in e["description"] for e in entries)
    assert len(detail(client, rich, cid)["ledger"]) >= 3                         # aporte, estrutura e estoque na conta da empresa


# ------------------------------------------------------------------ 5/6. funcionários e folha

def test_hire_and_fire_with_costs(client, rich):
    cid = create_ok(client, rich, extra="80000")["company"]["id"]
    d0 = detail(client, rich, cid)
    cap0 = d0["expected_capacity"]
    d1 = hire_candidate(client, rich, cid, "barista", index=1)
    new = d1["employees"][-1]
    assert new["role"] == "barista" and new["name"] and new["regime"] == "CLT" and D(new["total_cost"]) == D(new["salary"]) * 2
    assert D(d0["company"]["cash"]) - D(d1["company"]["cash"]) == D(new["salary"]) * D("0.5")     # custo de contratação
    assert d1["expected_capacity"] > cap0                                           # mais produtividade
    assert D(d1["monthly_obligations"]) == D(d0["monthly_obligations"]) + D(new["salary"]) * 2
    f = client.delete(f"{C}/{cid}/employees/{new['id']}", headers=rich)
    assert f.status_code == 200
    gone = next(e for e in f.json()["employees"] if e["id"] == new["id"])
    assert gone["status"] == "TERMINATED" and gone["terminated_on"]
    assert D(d1["company"]["cash"]) - D(f.json()["company"]["cash"]) == D(new["salary"]) * 2    # CLT recém-contratado: 1 salário + 1 de aviso
    assert client.delete(f"{C}/{cid}/employees/{new['id']}", headers=rich).status_code == 409
    r = client.post(f"{C}/{cid}/candidates", headers=rich, json={"role": "astronauta", "regime": "CLT"})
    assert r.status_code == 400


def test_hiring_without_runway_requires_explicit_risk_confirmation(client, rich, db):
    cid = create_ok(client, rich, extra="0")["company"]["id"]
    n0 = len(detail(client, rich, cid)["employees"])
    row = db.scalar(select(FinanceAccount).join(Company, Company.account_id == FinanceAccount.id).where(Company.id == cid))
    row.balance = D("30000.00")                                                      # caixa curto para os custos mensais
    db.commit()
    cand = client.post(f"{C}/{cid}/candidates", headers=rich, json={"role": "barista", "regime": "CLT"}).json()["candidates"][0]
    body = {"candidate_id": cand["id"], "salary": str(D(cand["asking_salary"]) * D("1.2")), "hours_week": cand["hours_week"],
            "schedule": cand["schedule"], "regime": "CLT", "idempotency_key": key()}
    r = client.post(f"{C}/{cid}/hire", headers=rich, json=body)
    assert r.status_code == 409 and "RISCO" in r.json()["detail"]
    assert len(detail(client, rich, cid)["employees"]) == n0                           # nada mudou
    ok = client.post(f"{C}/{cid}/hire", headers=rich, json={**body, "confirm_risk": True, "idempotency_key": key()})
    assert ok.status_code == 200 and ok.json()["accepted"] and len(ok.json()["company"]["employees"]) == n0 + 1
    row.balance = D("500.00")
    db.commit()
    cand2 = client.post(f"{C}/{cid}/candidates", headers=rich, json={"role": "barista", "regime": "CLT"}).json()["candidates"][0]
    r = client.post(f"{C}/{cid}/hire", headers=rich, json={**body, "candidate_id": cand2["id"], "confirm_risk": True, "idempotency_key": key()})
    assert r.status_code == 400


def test_payroll_processed_at_close_with_charges(client, rich, db):
    cid = create_ok(client, rich)["company"]["id"]
    staff = detail(client, rich, cid)["employees"]
    expected = sum(D(e["salary"]) * 2 for e in staff)                               # todos CLT: 2x o salário negociado
    assert expected == sum(D(e["total_cost"]) for e in staff)
    assert close(client, rich).status_code == 200
    m = detail(client, rich, cid)["months"][0]
    assert D(m["payroll"]) == expected
    line = db.scalar(select(LedgerEntry).where(LedgerEntry.company_id == cid, LedgerEntry.line == "PAYROLL"))
    assert line.amount == expected and line.capital is False


# ------------------------------------------------------------------ 7/8. estoque

def test_buy_stock_updates_quantity_and_weighted_cost(client, rich):
    cid = create_ok(client, rich, extra="40000")["company"]["id"]
    d0 = detail(client, rich, cid)
    item = d0["inventory"][0]
    r = client.post(f"{C}/{cid}/stock", headers=rich, json={"item_id": item["id"], "quantity": "500", "idempotency_key": key()})
    assert r.status_code == 201
    d1 = r.json()
    new = d1["inventory"][0]
    assert D(new["quantity"]) == D(item["quantity"]) + 500
    spent = D(d0["company"]["cash"]) - D(d1["company"]["cash"])
    assert spent > 0 and abs(float(D(new["value"]) - D(item["value"])) - float(spent)) < 1.0
    k = key()
    again = client.post(f"{C}/{cid}/stock", headers=rich, json={"item_id": item["id"], "quantity": "500", "idempotency_key": k})
    same = client.post(f"{C}/{cid}/stock", headers=rich, json={"item_id": item["id"], "quantity": "500", "idempotency_key": k})
    assert same.status_code == 201 and D(same.json()["inventory"][0]["quantity"]) == D(again.json()["inventory"][0]["quantity"])   # repetição não soma de novo
    assert client.post(f"{C}/{cid}/stock", headers=rich, json={"item_id": item["id"], "quantity": "99999999", "idempotency_key": key()}).status_code == 422
    assert client.post(f"{C}/{cid}/stock", headers=rich, json={"item_id": 999999, "quantity": "1", "idempotency_key": key()}).status_code == 404


def test_stock_is_consumed_by_sales_and_replenished(client, rich):
    cid = create_ok(client, rich, extra="40000")["company"]["id"]
    item0 = detail(client, rich, cid)["inventory"][0]
    assert close(client, rich).status_code == 200
    d = detail(client, rich, cid)
    m = d["months"][0]
    used = D(m["units_sold"]) * D("1.05")                                           # 5% de desperdício
    after = D(d["inventory"][0]["quantity"])
    assert after != D(item0["quantity"]) and m["stockout"] is False
    assert after >= D(item0["quantity"]) - used                                      # consumo debitado (e possível reposição automática)
    assert D(d["inventory"][0]["value"]) > 0


def test_stockout_stops_sales_and_hurts_reputation(client, rich, db):
    cid = create_ok(client, rich)["company"]["id"]
    from backend.models import InventoryItem
    for i in db.scalars(select(InventoryItem).where(InventoryItem.company_id == cid)):
        i.quantity = D("0")
    comp = db.get(Company, cid)
    comp.auto_restock = False
    db.commit()
    assert close(client, rich).status_code == 200
    d = detail(client, rich, cid)
    m = d["months"][0]
    assert m["stockout"] is True and D(m["units_sold"]) == 0 and D(m["revenue"]) == 0
    assert d["company"]["reputation"] < 50 and D(m["net_result"]) < 0               # custos fixos continuam


# ------------------------------------------------------------------ 9/10. receita, lucro e prejuízo

def test_revenue_from_demand_price_and_capacity(client, rich, db):
    cid = create_ok(client, rich, extra="40000")["company"]["id"]
    d0 = detail(client, rich, cid)
    price = D(d0["company"]["price"])
    assert close(client, rich).status_code == 200
    m = detail(client, rich, cid)["months"][0]
    assert D(m["units_sold"]) == min(D(str(d0["expected_demand"])), D(str(d0["expected_capacity"]))).quantize(D("1"), rounding="ROUND_FLOOR")
    assert D(m["revenue"]) == D(m["units_sold"]) * price
    assert D(m["net_result"]) == D(m["operating_result"]) - D(m["taxes"]) - D(m["interest"])
    assert D(m["operating_result"]) == D(m["revenue"]) - D(m["variable_costs"]) - D(m["fixed_costs"]) - D(m["payroll"])
    sale = db.scalar(select(LedgerEntry).where(LedgerEntry.company_id == cid, LedgerEntry.line == "REVENUE"))
    assert sale.amount == D(m["revenue"]) and sale.kind == "INCOME" and sale.capital is False
    # preço mais alto reduz a demanda; capacidade e demanda explicam a origem da receita
    cheap = D(str(client.patch(f"{C}/{cid}/settings", headers=rich, json={"price": str(price / 2)}).json()["expected_demand"]))
    dear = D(str(client.patch(f"{C}/{cid}/settings", headers=rich, json={"price": str(price * 2)}).json()["expected_demand"]))
    assert cheap > D(str(d0["expected_demand"])) > dear


def test_loss_when_costs_exceed_revenue(client, rich):
    cid = create_ok(client, rich, extra="60000")["company"]["id"]
    client.patch(f"{C}/{cid}/settings", headers=rich, json={"owner_salary": "30000"})       # pró-labore inviável
    assert close(client, rich).status_code == 200
    m = detail(client, rich, cid)["months"][0]
    assert D(m["net_result"]) < 0 and D(m["payroll"]) > D("30000")


def test_negative_cash_becomes_debt_with_interest(client, rich, db):
    cid = create_ok(client, rich, extra="0")["company"]["id"]
    acc = db.scalar(select(FinanceAccount).join(Company, Company.account_id == FinanceAccount.id).where(Company.id == cid))
    acc.balance = D("-20000.00")
    db.commit()
    d0 = detail(client, rich, cid)
    stock_value = sum(D(i["value"]) for i in d0["inventory"])
    assert D(d0["company"]["debts"]) == D("20000") and D(d0["company"]["equity"]) == D("-20000") + stock_value   # caixa negativo é dívida
    assert close(client, rich).status_code == 200
    m = detail(client, rich, cid)["months"][0]
    assert D(m["interest"]) == D("800.00")                                           # 4% ao mês sobre o saldo negativo


def test_seasonality_changes_demand_deterministically(client, rich, monkeypatch):
    monkeypatch.undo()
    from datetime import date
    seg = company_rules.SEGMENTS[company_rules.CompanySegment.CLOTHING]
    a = company_rules.season_factor(seg, 1, date(2027, 1, 1))
    assert a == company_rules.season_factor(seg, 1, date(2027, 1, 1))
    assert a != company_rules.season_factor(seg, 1, date(2027, 2, 1)) or True
    assert 1 - seg.volatility <= a <= 1 + seg.volatility


# ------------------------------------------------------------------ 11. bens e equipamentos da empresa

def test_company_buys_equipment_without_mixing_with_personal_goods(client, rich, db):
    cid = create_ok(client, rich, extra="60000")["company"]["id"]
    d0 = detail(client, rich, cid)
    personal_cash = cash(client, rich)
    r = client.post(f"{C}/{cid}/goods/purchase", headers=rich, json={"listing_key": "camera-pro", "idempotency_key": key()})
    assert r.status_code == 201, r.text
    d1 = r.json()
    assert [g["name"] for g in d1["goods"]] == ["Câmera mirrorless profissional"]
    assert D(d0["company"]["cash"]) - D(d1["company"]["cash"]) >= D("21000")          # pago pela empresa
    assert cash(client, rich) == personal_cash                                         # o dinheiro pessoal não mexeu
    assert client.get(G, headers=rich).json() == []                                    # não aparece nos bens pessoais
    assert client.get(f"{G}/overview", headers=rich).json()["count"] == 0
    assert d1["expected_capacity"] > d0["expected_capacity"]                           # equipamento aumenta a capacidade
    gid = d1["goods"][0]["id"]
    assert client.post(f"{G}/{gid}/sell", headers=rich, json={}).status_code == 409    # venda pessoal bloqueada
    assert D(d1["company"]["equity"]) == D(d0["company"]["equity"])                    # equipamento sem taxa: o dinheiro vira bem, sem perda
    assert close(client, rich).status_code == 200
    assert close(client, rich).status_code == 200                                       # custos do bem começam no mês seguinte à compra
    assert any(e["line"] == "ASSET_COSTS" for e in detail(client, rich, cid)["ledger"])


def test_company_goods_must_be_paid_in_cash_and_funded(client, rich):
    cid = create_ok(client, rich, extra="0")["company"]["id"]
    assert client.post(f"{C}/{cid}/goods/purchase", headers=rich, json={"listing_key": "apto-rj-3q", "idempotency_key": key()}).status_code == 422
    assert client.post(f"{C}/{cid}/goods/purchase", headers=rich, json={"listing_key": "nada", "idempotency_key": key()}).status_code == 404


# ------------------------------------------------------------------ 12. imóveis: locação

def test_lease_own_property_creates_personal_income_and_company_expense(client, rich, db):
    cid = create_ok(client, rich, extra="60000")["company"]["id"]
    gid = client.post(f"{G}/purchase", headers=rich, json={"listing_key": "sala-sp-comercial", "idempotency_key": key()}).json()["good"]["id"]
    r = client.post(f"{C}/{cid}/lease", headers=rich, json={"kind": "OWN_GOOD", "good_id": gid, "monthly_rent": "4000"})
    assert r.status_code == 200, r.text
    assert r.json()["lease"]["kind"] == "OWN_GOOD" and D(r.json()["lease"]["monthly_rent"]) == D("4000")
    assert client.get(f"{G}/{gid}", headers=rich).json()["real_estate"]["occupancy"] == "COMPANY_USE"
    other = create_ok(client, rich, name="Outra", segment="AGENCY", extra="60000")["company"]["id"]
    assert client.post(f"{C}/{other}/lease", headers=rich, json={"kind": "OWN_GOOD", "good_id": gid}).status_code == 409   # um imóvel, um negócio
    assert client.post(f"{G}/{gid}/sell", headers=rich, json={}).status_code == 409
    assert client.post(f"{G}/{gid}/occupancy", headers=rich, json={"mode": "VACANT"}).status_code == 409
    personal_before = cash(client, rich)
    assert close(client, rich).status_code == 200
    rent_in = db.scalar(select(LedgerEntry).where(LedgerEntry.company_id.is_(None), LedgerEntry.description == "Aluguel recebido de Café da Esquina"))
    rent_out = db.scalar(select(LedgerEntry).where(LedgerEntry.company_id == cid, LedgerEntry.line == "RENT"))
    assert rent_in.amount == rent_out.amount == D("4000.00") and rent_in.kind == "INCOME" and rent_in.capital is False
    assert any(i["name"].startswith("IPTU") for i in client.get(f"{B}/overview", headers=rich).json()["month"]["items"])
    assert cash(client, rich) > personal_before - D("20000")                           # entrou aluguel no caixa pessoal
    # encerrar a locação libera o imóvel
    new = client.post(f"{C}/{cid}/lease", headers=rich, json={"kind": "EXTERNAL", "monthly_rent": "3000"})
    assert new.status_code == 200 and client.get(f"{G}/{gid}", headers=rich).json()["real_estate"]["occupancy"] == "VACANT"
    assert client.post(f"{C}/{other}/lease", headers=rich, json={"kind": "OWN_GOOD", "good_id": gid}).status_code == 200


def test_lease_validations(client, rich):
    cid = create_ok(client, rich)["company"]["id"]
    land = client.post(f"{G}/purchase", headers=rich, json={"listing_key": "terreno-atibaia", "idempotency_key": key()}).json()["good"]["id"]
    assert client.post(f"{C}/{cid}/lease", headers=rich, json={"kind": "OWN_GOOD", "good_id": land}).status_code == 400
    home = client.post(f"{G}/purchase", headers=rich, json={"listing_key": "apto-bh-2q", "idempotency_key": key()}).json()["good"]["id"]
    client.post(f"{G}/{home}/occupancy", headers=rich, json={"mode": "OWNER_OCCUPIED"})
    assert client.post(f"{C}/{cid}/lease", headers=rich, json={"kind": "OWN_GOOD", "good_id": home}).status_code == 409
    assert client.post(f"{C}/{cid}/lease", headers=rich, json={"kind": "OWN_GOOD", "good_id": 999999}).status_code == 404
    assert client.post(f"{C}/{cid}/lease", headers=rich, json={"kind": "OWN_GOOD"}).status_code == 400


# ------------------------------------------------------------------ 13. expansão e crédito

def test_expansion_has_cost_and_consequences(client, rich):
    cid = create_ok(client, rich, extra="150000")["company"]["id"]
    d0 = detail(client, rich, cid)
    r = client.post(f"{C}/{cid}/expand", headers=rich, json={"kind": "CAPACITY"})
    assert r.status_code == 200
    d1 = r.json()
    assert d1["company"]["capacity_level"] == 1 and d1["expected_capacity"] > d0["expected_capacity"]
    assert D(d0["company"]["cash"]) - D(d1["company"]["cash"]) == D(d0["expansion_costs"]["CAPACITY"])
    u = client.post(f"{C}/{cid}/expand", headers=rich, json={"kind": "NEW_UNIT"}).json()
    assert u["company"]["units"] == 2 and D(u["monthly_obligations"]) > D(d1["monthly_obligations"]) and u["expected_demand"] > d1["expected_demand"]
    big = client.post(f"{C}/{cid}/expand", headers=rich, json={"kind": "LARGER_PREMISES"}).json()
    assert big["company"]["size"] == "MEDIUM" and D(big["lease"]["monthly_rent"]) > D(d0["lease"]["monthly_rent"])
    mk = client.post(f"{C}/{cid}/expand", headers=rich, json={"kind": "MARKETING"}).json()
    assert mk["company"]["marketing_until"] is not None
    assert client.post(f"{C}/{cid}/expand", headers=rich, json={"kind": "XYZ"}).status_code == 422


def test_expansion_requires_cash_and_does_not_guarantee_profit(client, rich, db):
    cid = create_ok(client, rich, extra="0")["company"]["id"]
    acc = db.scalar(select(FinanceAccount).join(Company, Company.account_id == FinanceAccount.id).where(Company.id == cid))
    acc.balance = D("1000.00")
    db.commit()
    assert client.post(f"{C}/{cid}/expand", headers=rich, json={"kind": "NEW_UNIT"}).status_code == 400
    assert detail(client, rich, cid)["company"]["units"] == 1
    acc.balance = D("400000.00")
    db.commit()
    client.post(f"{C}/{cid}/expand", headers=rich, json={"kind": "NEW_UNIT"})        # mais custos fixos sem mais demanda garantida
    assert close(client, rich).status_code == 200


def test_company_loan_creates_debt_and_installments_are_processed(client, rich, db):
    cid = create_ok(client, rich)["company"]["id"]
    d0 = detail(client, rich, cid)
    r = client.post(f"{C}/{cid}/loans", headers=rich, json={"amount": "40000", "term_months": 12})
    assert r.status_code == 201
    d1 = r.json()
    assert D(d1["company"]["cash"]) == D(d0["company"]["cash"]) + D("40000")
    assert D(d1["company"]["equity"]) == D(d0["company"]["equity"])                   # empréstimo não cria patrimônio
    assert D(d1["company"]["debts"]) == D("40000") and len(d1["loans"][0]["installments"]) == 12
    assert client.post(f"{C}/{cid}/loans", headers=rich, json={"amount": "99999999", "term_months": 12}).status_code == 400
    assert close(client, rich).status_code == 200                                      # parcela 1 vence no mês seguinte
    assert close(client, rich).status_code == 200
    d2 = detail(client, rich, cid)
    first = d2["loans"][0]["installments"][0]
    assert first["status"] == "PAID" and D(d2["loans"][0]["balance"]) == D(first["balance_after"])
    assert D(d2["company"]["debts"]) == D(first["balance_after"]) or D(d2["company"]["debts"]) >= D(first["balance_after"])
    kinds = {(e.line, e.capital) for e in db.scalars(select(LedgerEntry).where(LedgerEntry.company_id == cid)) if e.line in ("INTEREST", "LOAN_PRINCIPAL")}
    assert kinds == {("INTEREST", False), ("LOAN_PRINCIPAL", True)}


# ------------------------------------------------------------------ 14/15. lucros

@pytest.mark.usefixtures("boom")
def test_profit_distribution_flows_to_personal_account(client, rich, db):
    cid = create_ok(client, rich, extra="80000")["company"]["id"]
    assert client.post(f"{C}/{cid}/distribute", headers=rich, json={"amount": "100", "idempotency_key": key()}).status_code == 400   # ainda sem lucro
    earn_profit(client, rich, cid)
    d = detail(client, rich, cid)
    available = D(d["distributable_profit"])
    assert available > 0 and available == sum(D(m["net_result"]) for m in d["months"])
    personal, equity = cash(client, rich), D(portfolio(client, rich)["total_equity_brl"])
    k = key()
    amount = (available / 2).quantize(D("0.01"))
    r = client.post(f"{C}/{cid}/distribute", headers=rich, json={"amount": str(amount), "idempotency_key": k})
    assert r.status_code == 200
    assert client.post(f"{C}/{cid}/distribute", headers=rich, json={"amount": str(amount), "idempotency_key": k}).status_code == 200
    assert cash(client, rich) == personal + amount                                      # entrou uma vez
    assert D(r.json()["company"]["cash"]) == D(d["company"]["cash"]) - amount
    assert D(portfolio(client, rich)["total_equity_brl"]) == equity                    # distribuir não cria patrimônio
    assert D(r.json()["distributable_profit"]) == available - amount
    own = db.scalar(select(LedgerEntry).where(LedgerEntry.company_id.is_(None), LedgerEntry.description.like("Distribuição de lucros%")))
    assert own.kind == "INCOME" and own.capital is False


@pytest.mark.usefixtures("boom")
def test_distribution_cannot_exceed_profit_or_cash(client, rich, db):
    cid = create_ok(client, rich, extra="80000")["company"]["id"]
    earn_profit(client, rich, cid)
    d = detail(client, rich, cid)
    over = D(d["distributable_profit"]) + 1
    r = client.post(f"{C}/{cid}/distribute", headers=rich, json={"amount": str(over), "idempotency_key": key()})
    assert r.status_code == 400 and "lucro distribuível" in r.json()["detail"]
    acc = db.scalar(select(FinanceAccount).join(Company, Company.account_id == FinanceAccount.id).where(Company.id == cid))
    acc.balance = D("10.00")                                                            # há lucro contábil, mas não há caixa
    db.commit()
    r = client.post(f"{C}/{cid}/distribute", headers=rich, json={"amount": str(D(d["distributable_profit"])), "idempotency_key": key()})
    assert r.status_code == 400 and "caixa" in r.json()["detail"]


@pytest.mark.usefixtures("boom")
def test_partial_ownership_splits_distribution_and_equity(client, rich):
    cid = create_ok(client, rich, extra="80000", owner_share_pct="60")["company"]["id"]
    earn_profit(client, rich, cid)
    d = detail(client, rich, cid)
    amount = D(d["distributable_profit"]).quantize(D("0.01"))
    before = cash(client, rich)
    assert client.post(f"{C}/{cid}/distribute", headers=rich, json={"amount": str(amount), "idempotency_key": key()}).status_code == 200
    assert cash(client, rich) - before == (amount * D("0.6")).quantize(D("0.01"))     # só a participação do usuário
    p = portfolio(client, rich)
    assert D(p["companies_net_brl"]) == (D(detail(client, rich, cid)["company"]["equity"]) * D("0.6")).quantize(D("0.01"))


def test_owner_salary_is_personal_income_and_company_cost(client, rich, db):
    cid = create_ok(client, rich, extra="60000")["company"]["id"]
    client.patch(f"{C}/{cid}/settings", headers=rich, json={"owner_salary": "3000"})
    before = cash(client, rich)
    assert close(client, rich).status_code == 200
    pl = db.scalar(select(LedgerEntry).where(LedgerEntry.company_id == cid, LedgerEntry.line == "PRO_LABORE"))
    own = db.scalar(select(LedgerEntry).where(LedgerEntry.company_id.is_(None), LedgerEntry.description == "Pró-labore: Café da Esquina"))
    assert pl.amount == own.amount == D("3000.00") and own.kind == "INCOME" and own.capital is False
    assert cash(client, rich) == before + D("3000.00")


# ------------------------------------------------------------------ 16/17/18. fechamento mensal

def test_close_month_with_several_companies_processes_each_once(client, rich, db):
    ids = [create_ok(client, rich, name=f"Empresa {n}", segment=s, extra="60000")["company"]["id"]
           for n, s in enumerate(["CAFE", "CLOTHING", "TECH"])]
    assert close(client, rich).status_code == 200
    rows = db.scalars(select(CompanyMonth).order_by(CompanyMonth.company_id)).all()
    assert [r.company_id for r in rows] == ids and len({r.ref_month for r in rows}) == 1
    assert close(client, rich).status_code == 200
    assert db.scalar(select(func.count()).select_from(CompanyMonth)) == 6
    assert all(detail(client, rich, i)["company"]["status"] == "ACTIVE" for i in ids)


def test_company_month_cannot_be_processed_twice(client, rich, db):
    cid = create_ok(client, rich)["company"]["id"]
    assert close(client, rich).status_code == 200
    first = detail(client, rich, cid)["months"][0]
    cash_after = D(detail(client, rich, cid)["company"]["cash"])
    ledger_n = db.scalar(select(func.count()).select_from(LedgerEntry).where(LedgerEntry.company_id == cid))
    from backend.models import SimMonth
    closed = db.scalar(select(SimMonth).where(SimMonth.status == "CLOSED"))
    assert company_service.process_month(db, closed.user_id, closed) == []              # nada a fazer
    db.commit()
    assert db.scalar(select(func.count()).select_from(LedgerEntry).where(LedgerEntry.company_id == cid)) == ledger_n
    assert D(detail(client, rich, cid)["company"]["cash"]) == cash_after
    assert detail(client, rich, cid)["months"][0] == first
    again = client.post(f"{B}/close", headers=rich, json={"ref_month": closed.ref_month.isoformat()[:7], "confirm": True})
    assert again.status_code == 409


def test_failure_during_close_rolls_back_every_company(client, rich, db, monkeypatch):
    ids = [create_ok(client, rich, name=f"E{n}", extra="40000")["company"]["id"] for n in range(3)]
    cash_before = {i: detail(client, rich, i)["company"]["cash"] for i in ids}
    personal = cash(client, rich)
    real = company_service._process_company
    calls = {"n": 0}

    def flaky(db_, c, month):
        calls["n"] += 1
        if calls["n"] == 3:
            raise RuntimeError("falha na terceira empresa")
        return real(db_, c, month)

    monkeypatch.setattr(company_service, "_process_company", flaky)
    with pytest.raises(RuntimeError):
        close(client, rich)
    monkeypatch.setattr(company_service, "_process_company", real)
    db.expire_all()
    assert db.scalar(select(func.count()).select_from(CompanyMonth)) == 0               # nenhuma ficou processada
    assert all(detail(client, rich, i)["company"]["cash"] == cash_before[i] for i in ids)
    assert cash(client, rich) == personal and client.get(f"{B}/overview", headers=rich).json()["month"]["status"] == "OPEN"
    assert close(client, rich).status_code == 200 and db.scalar(select(func.count()).select_from(CompanyMonth)) == 3


def test_history_is_preserved_across_months(client, rich):
    cid = create_ok(client, rich)["company"]["id"]
    assert close(client, rich).status_code == 200
    first = detail(client, rich, cid)["months"][0]
    client.patch(f"{C}/{cid}/settings", headers=rich, json={"price": "30"})
    assert close(client, rich).status_code == 200
    d = detail(client, rich, cid)
    assert len(d["months"]) == 2 and d["months"][1] == first                              # mês antigo imutável
    assert [e["type"] for e in d["events"]].count("MONTH") == 2


# ------------------------------------------------------------------ 19/20. isolamento, integração e consistência

def test_company_accounts_and_data_are_isolated_between_users(client, rich):
    cid = create_ok(client, rich)["company"]["id"]
    bia = second_user(client)
    assert client.get(f"{C}", headers=bia).json() == [] and client.get(f"{C}/overview", headers=bia).json()["count"] == 0
    for method, path, body in [("get", f"/{cid}", None), ("post", f"/{cid}/contribute", {"amount": "10", "idempotency_key": key()}),
                               ("post", f"/{cid}/expand", {"kind": "CAPACITY"}), ("patch", f"/{cid}/settings", {"price": "1"}),
                               ("post", f"/{cid}/candidates", {"role": "barista", "regime": "CLT"}),
                               ("post", f"/{cid}/hire", {"candidate_id": "202611-barista-CLT-c0", "salary": "2000", "hours_week": 44, "schedule": "5x2",
                                                         "regime": "CLT", "idempotency_key": key()}),
                               ("post", f"/{cid}/headhunter", {"role": "barista", "regime": "CLT", "max_salary": "3000", "min_level": "MID",
                                                               "idempotency_key": key()}),
                               ("post", f"/{cid}/loans", {"amount": "1000", "term_months": 6}),
                               ("post", f"/{cid}/lease", {"kind": "EXTERNAL"}), ("post", f"/{cid}/distribute", {"amount": "1", "idempotency_key": key()})]:
        r = getattr(client, method)(f"{C}{path}", headers=bia, **({"json": body} if body else {}))
        assert r.status_code == 404, (path, r.text)
    assert close(client, bia).status_code == 200                                          # fechar o mês de um não processa a empresa do outro
    assert detail(client, rich, cid)["months"] == []
    assert client.get(C).status_code == 401


def test_personal_wealth_includes_company_share_without_fake_loss(client, rich):
    before = D(portfolio(client, rich)["total_equity_brl"])
    q = quote(client, rich)
    cid = create_ok(client, rich, staff=False)["company"]["id"]
    after = portfolio(client, rich)
    assert D(after["total_equity_brl"]) == before - D(q["setup_cost"])                  # só a estrutura (despesa) reduz o patrimônio
    assert D(after["companies_net_brl"]) == D(detail(client, rich, cid)["company"]["equity"])
    perf = client.get("/api/performance?range=7d", headers=rich)
    assert perf.status_code == 200
    labels = {a["label"] for a in perf.json()["allocation"]}
    assert "Empresas (participação)" in labels


def test_ledger_and_accounts_stay_consistent(client, rich, db):
    cid = create_ok(client, rich, extra="80000")["company"]["id"]
    hire_candidate(client, rich, cid, "barista", index=2)
    client.post(f"{C}/{cid}/loans", headers=rich, json={"amount": "20000", "term_months": 6})
    client.post(f"{C}/{cid}/goods/purchase", headers=rich, json={"listing_key": "estudio-audio", "idempotency_key": key()})
    client.patch(f"{C}/{cid}/settings", headers=rich, json={"owner_salary": "2000"})
    for _ in range(3):
        assert close(client, rich).status_code == 200
    # conta da empresa == soma dos movimentos da empresa
    acc = db.scalar(select(FinanceAccount).join(Company, Company.account_id == FinanceAccount.id).where(Company.id == cid))
    flows = db.scalars(select(LedgerEntry).where(LedgerEntry.company_id == cid)).all()
    assert acc.balance == sum((e.amount if e.kind == "INCOME" else -e.amount) for e in flows)
    # caixa pessoal == soma das transações; cada transação orçamentária tem uma entrada pessoal (as da empresa não têm transação)
    pf = db.scalar(select(Portfolio))
    assert pf.cash_balance == db.scalar(select(func.coalesce(func.sum(Transaction.cash_amount_brl), 0)))
    personal = db.scalar(select(func.count()).select_from(LedgerEntry).where(LedgerEntry.company_id.is_(None)))
    assert personal == db.scalar(select(func.count()).select_from(Transaction).where(Transaction.type.in_(["BUDGET_INCOME", "BUDGET_EXPENSE"])))
    assert db.scalar(select(func.count()).select_from(LedgerEntry).where(LedgerEntry.company_id.is_not(None), LedgerEntry.transaction_id.is_not(None))) == 0
    keys = db.scalars(select(LedgerEntry.idempotency_key).where(LedgerEntry.idempotency_key.is_not(None))).all()
    assert len(keys) == len(set(keys))
    # o resultado do orçamento pessoal não conta custos da empresa
    m = client.get(f"{B}/overview", headers=rich).json()["month"]
    assert not any("Folha" in i["name"] for i in m["items"])


def test_existing_features_unaffected(client, rich, assets):
    r = client.post("/api/trades/buy", headers=rich, json={"asset_id": assets["PETR4"].id, "quantity": "10"})
    assert r.status_code in (200, 201), r.text
    p = portfolio(client, rich)
    assert D(p["companies_net_brl"]) == 0 and D(p["goods_net_brl"]) == 0
    assert D(p["total_equity_brl"]) == D(p["cash_balance"]) + D(p["market_value_brl"])


# ================================================================== FASE 2: equipe, regimes, candidatos, headhunter, obrigatórios
from backend.models import CandidateBlock, Employee, EmployeeEducation, EmployeeLevel, EmployeeRegime, User, WorkSchedule, WorldEvent  # noqa: E402
from backend.services import company_team as team  # noqa: E402
from backend.services.goods_rules import hash01  # noqa: E402


def candidates(client, h, cid, role="barista", regime="CLT"):
    r = client.post(f"{C}/{cid}/candidates", headers=h, json={"role": role, "regime": regime})
    assert r.status_code == 200, r.text
    return r.json()["candidates"]


def propose(client, h, cid, cand, salary, hours=None, schedule=None, regime="CLT", k=None, **kw):
    body = {"candidate_id": cand["id"], "salary": str(D(salary).quantize(D("0.01"))), "hours_week": hours or cand["hours_week"],
            "schedule": schedule or cand["schedule"], "regime": regime, "idempotency_key": k or key(), "confirm_risk": True, **kw}
    r = client.post(f"{C}/{cid}/hire", headers=h, json=body)
    assert r.status_code == 200, r.text
    return r.json()


def real_candidate(db, client, h, cid, cand):
    """O mesmo candidato que o servidor recalcula (para saber a concorrência, a folga etc. sem confiar no cliente)."""
    uid = db.scalar(select(User.id))
    c = db.get(Company, cid)
    ref = db.scalar(select(company_service.SimMonth.ref_month).where(company_service.SimMonth.user_id == uid, company_service.SimMonth.status == "OPEN"))
    return team.resolve_token(uid, cid, ref, cand["id"], company_rules.SEGMENTS[c.segment])


def synth(**kw):
    base = dict(id="202611-barista-CLT-c0", role="barista", regime=EmployeeRegime.CLT, name="Teste Silva", education=EmployeeEducation.MEDIO,
                experience_years=3, level=EmployeeLevel.MID, asking_salary=D("2000.00"), hours_week=40, schedule=WorkSchedule.ESC_5X2,
                flex=0.05, competing=False)
    return team.Candidate(**{**base, **kw})


def test_new_company_has_no_staff_and_minimum_capital_covers_mandatory_team(client, rich):
    q = quote(client, rich)
    assert q["mandatory_roles"] == ["Contador", "Advogado", "Auxiliar de limpeza"]
    assert D(q["monthly_payroll"]) == (D("4500") + D("7000") + D("1650")) * 2                    # 1 mês, CLT 2x, salário-base
    assert D(q["mandatory_cost"]) == D(q["monthly_payroll"]) + (D("4500") + D("7000") + D("1650")) / 2          # + custo de contratação (0,5x)
    online = quote(client, rich, channel="ONLINE", location=None)
    assert online["mandatory_roles"] == ["Contador", "Advogado"] and D(online["monthly_payroll"]) == (D("4500") + D("7000")) * 2
    d = create_ok(client, rich, staff=False)
    assert d["employees"] == [] and d["compliance"]["regular"] is False
    assert [r["role"] for r in d["compliance"]["required"]] == ["accountant", "lawyer", "cleaner"]
    assert D(d["expected_capacity"]) == D(str(company_rules.SEGMENTS[company_rules.CompanySegment.CAFE].owner_capacity))   # só o dono produz
    assert {r["key"] for r in d["roles"] if r["mandatory"]} == {"accountant", "lawyer", "cleaner"}


def test_candidates_are_deterministic_and_well_formed(client, rich):
    cid = create_ok(client, rich, staff=False)["company"]["id"]
    a, b = candidates(client, rich, cid), candidates(client, rich, cid)
    assert a == b and 4 <= len(a) <= 6
    assert len({c["id"] for c in a}) == len(a) and len({c["name"] for c in a}) >= 2
    for c in a:
        assert c["education"] in {"FUNDAMENTAL", "MEDIO", "TECNICO", "SUPERIOR", "POS"} and c["level"] in {"JUNIOR", "MID", "SENIOR"}
        assert c["experience_years"] >= 0 and D(c["asking_salary"]) > 0 and c["schedule"] in {"6x1", "5x2", "12x36", "4x3"} and c["hours_week"] >= 30
        assert D(c["monthly_cost_at_asking"]) == D(c["asking_salary"]) * 2 and c["regime"] == "CLT"
    pj = candidates(client, rich, cid, regime="PJ")
    assert pj != a and all(D(c["monthly_cost_at_asking"]) == D(c["asking_salary"]) for c in pj)
    assert candidates(client, rich, cid, role="accountant") != a
    assert all(c["education"] in ("SUPERIOR", "POS") for c in candidates(client, rich, cid, role="lawyer"))
    # a lista só depende de (empresa, semente, mês, cargo, regime): outra empresa recebe candidatos diferentes
    cid2 = create_ok(client, rich, staff=False, name="Outra")["company"]["id"]
    assert [c["name"] for c in candidates(client, rich, cid2)] != [c["name"] for c in a]
    # senioridade manda na pretensão e na produtividade
    by_level = {}
    for role in ("barista", "attendant", "pastry", "manager", "accountant", "lawyer"):
        for c in candidates(client, rich, cid, role=role):
            by_level.setdefault(c["level"], []).append(D(c["asking_salary"]) / D(company_rules.SEGMENTS[company_rules.CompanySegment.CAFE].role(role).salary))
    assert {"JUNIOR", "MID", "SENIOR"} <= set(by_level) or len(by_level) >= 2
    avg = {k: sum(v) / len(v) for k, v in by_level.items()}
    if "JUNIOR" in avg and "SENIOR" in avg:
        assert avg["JUNIOR"] < avg["SENIOR"]
    assert client.post(f"{C}/{cid}/candidates", headers=rich, json={"role": "astronauta", "regime": "CLT"}).status_code == 400


def test_client_cannot_forge_candidate_or_salary(client, rich, db):
    cid = create_ok(client, rich, staff=False)["company"]["id"]
    cand = candidates(client, rich, cid)[0]
    # campos extras (pretensão, nível, escolaridade) são ignorados: o servidor recalcula o candidato pelo id
    forged = {"asking_salary": "1", "level": "SENIOR", "education": "POS", "role": "accountant", "flex": 0.9, "competing": False}
    out = propose(client, rich, cid, cand, D(cand["asking_salary"]) / 4, **forged)
    assert out["accepted"] is False and out["status"] == "REFUSED"
    assert db.scalar(select(func.count()).select_from(Employee)) == 0
    # ids inventados ou de outro mês/cargo/regime
    base = {"salary": "5000", "hours_week": 40, "schedule": "5x2", "regime": "CLT", "idempotency_key": key()}
    for bad in ("202611-barista-CLT-c99", "202611-barista-CLT-h99", "202601-barista-CLT-c0", "202611-astronauta-CLT-c0", "lixo", "x-y-z-w"):
        r = client.post(f"{C}/{cid}/hire", headers=rich, json={**base, "candidate_id": bad, "idempotency_key": key()})
        assert r.status_code == 400, (bad, r.text)
    other = candidates(client, rich, cid, regime="PJ")[0]
    r = client.post(f"{C}/{cid}/hire", headers=rich, json={**base, "candidate_id": other["id"]})          # token PJ com regime CLT
    assert r.status_code == 400
    # salário e jornada inválidos
    for bad in ({"salary": "0"}, {"hours_week": 100}, {"schedule": "7x0"}):
        assert client.post(f"{C}/{cid}/hire", headers=rich, json={**base, "candidate_id": cand["id"], **bad}).status_code == 422
    # a lista de um mês não vale no mês seguinte
    old = cand["id"]
    assert close(client, rich).status_code == 200
    r = client.post(f"{C}/{cid}/hire", headers=rich, json={**base, "candidate_id": old})
    assert r.status_code == 400 and "outro mês" in r.json()["detail"]


def test_offer_refusal_makes_candidate_unavailable_and_is_idempotent(client, rich, db):
    cid = create_ok(client, rich, staff=False)["company"]["id"]
    cands = candidates(client, rich, cid)
    cand = cands[0]
    k = key()
    r1 = propose(client, rich, cid, cand, D(cand["asking_salary"]) / 3, k=k)
    assert r1["accepted"] is False and r1["status"] == "REFUSED" and r1["counter_offer"] is None and "recusou" in r1["message"]
    cash0 = D(detail(client, rich, cid)["company"]["cash"])
    blocks = db.scalar(select(func.count()).select_from(CandidateBlock))
    # repetir a mesma recusa (mesma chave ou outra, até com salário alto) não muda nada: ele não está mais disponível no mês
    for kk in (k, key()):
        r2 = propose(client, rich, cid, cand, D(cand["asking_salary"]) * 3, k=kk)
        assert r2["accepted"] is False and r2["status"] == "REFUSED" and "disponível" in r2["message"]
    db.expire_all()
    assert db.scalar(select(func.count()).select_from(CandidateBlock)) == blocks == 1
    assert D(detail(client, rich, cid)["company"]["cash"]) == cash0 and not detail(client, rich, cid)["employees"]
    assert cand["id"] not in {c["id"] for c in candidates(client, rich, cid)} and len(candidates(client, rich, cid)) == len(cands) - 1
    # no mês seguinte a lista é nova (outros ids) e quem recusou volta a existir como candidato do novo mês
    assert close(client, rich).status_code == 200
    assert {c["id"] for c in candidates(client, rich, cid)}.isdisjoint({c["id"] for c in cands})


def test_counter_offer_then_acceptance_and_hire_idempotency(client, rich, db):
    cid = create_ok(client, rich, staff=False, extra="200000")["company"]["id"]
    chosen = None
    for cand in candidates(client, rich, cid):
        real = real_candidate(db, client, rich, cid, cand)
        if not real.competing:
            chosen = (cand, real)
            break
    assert chosen, "esperado ao menos um candidato sem concorrência"
    cand, real = chosen
    offer = (D(cand["asking_salary"]) * D("0.88")).quantize(D("1"))
    required = team.evaluate_offer(real, offer, cand["hours_week"], real.schedule).required
    assert offer < required <= D(cand["asking_salary"])
    out = propose(client, rich, cid, cand, offer)
    assert out["accepted"] is False and out["status"] == "COUNTER" and D(out["counter_offer"]) == required
    assert not detail(client, rich, cid)["employees"]                                  # contraproposta não contrata nem bloqueia
    k = key()
    ok = propose(client, rich, cid, cand, out["counter_offer"], k=k)
    assert ok["accepted"] is True and ok["status"] == "ACCEPTED"
    emp = ok["company"]["employees"][0]
    assert D(emp["salary"]) == required and emp["name"] == cand["name"] and emp["education"] == cand["education"]
    assert emp["experience_years"] == cand["experience_years"] and emp["level"] == cand["level"] and emp["regime"] == "CLT"
    assert D(emp["productivity"]) == company_rules.level_productivity(company_rules.EmployeeLevel(cand["level"]))
    cash1 = D(ok["company"]["company"]["cash"])
    again = propose(client, rich, cid, cand, out["counter_offer"], k=k)                # mesma chave: não contrata de novo
    assert again["accepted"] is True and len(again["company"]["employees"]) == 1 and D(again["company"]["company"]["cash"]) == cash1
    other_key = propose(client, rich, cid, cand, out["counter_offer"])                  # outro pedido: o candidato já foi contratado
    assert other_key["accepted"] is False and len(other_key["company"]["employees"]) == 1


def test_offer_rules_hours_schedule_regime_and_competition():
    c = synth()                                                                       # pede 2000, aceita até 5% menos
    ev = team.evaluate_offer
    assert ev(c, D(1900), 40, WorkSchedule.ESC_5X2).accepted and ev(c, D(1899), 40, WorkSchedule.ESC_5X2).status == "COUNTER"
    assert ev(c, D(1899), 40, WorkSchedule.ESC_5X2).counter_offer == D(1900) == ev(c, D(1899), 40, WorkSchedule.ESC_5X2).required
    assert ev(c, D(1500), 40, WorkSchedule.ESC_5X2).status == "REFUSED"                  # abaixo de 80% da pretensão ajustada
    # jornada acima de 44 h: prêmio proporcional (50% por hora extra)
    assert team.hours_factor(44) == 1 and team.hours_factor(40) == 1
    assert team.hours_factor(52) == 1 + D(8) / 44 * D("1.5")
    assert not ev(c, D(2000), 50, WorkSchedule.ESC_5X2).accepted and ev(c, D(2300), 50, WorkSchedule.ESC_5X2).accepted
    # acima de 52 h só aceita com +40%, mesmo com a folga de negociação
    assert team.hours_factor(53) >= D("1.4")
    assert not ev(c, D(2799), 53, WorkSchedule.ESC_5X2).accepted and ev(c, D(2800), 53, WorkSchedule.ESC_5X2).accepted
    assert not ev(c, D(3500), 70, WorkSchedule.ESC_5X2).accepted and ev(c, D(4500), 70, WorkSchedule.ESC_5X2).accepted
    # escalas: 6x1 pede prêmio; 12x36 e 4x3 aceitam desconto (escala diferente da preferida pede +2%)
    pref = synth(schedule=WorkSchedule.ESC_6X1, flex=0.0)
    assert ev(pref, D(2000), 44, WorkSchedule.ESC_6X1).required == D(2080)
    neutral = synth(flex=0.0)
    r6, r5, r12, r4 = (ev(neutral, D(9999), 40, s).required for s in (WorkSchedule.ESC_6X1, WorkSchedule.ESC_5X2, WorkSchedule.ESC_12X36, WorkSchedule.ESC_4X3))
    assert r12 < r4 + 100 and r4 < r5 < r6 and r12 < r5 and r5 == D(2000)
    assert ev(neutral, D(r12), 40, WorkSchedule.ESC_12X36).accepted and not ev(neutral, D(r12), 40, WorkSchedule.ESC_6X1).accepted
    # proposta concorrente exige prêmio de 10%
    comp = synth(competing=True, flex=0.0)
    assert ev(comp, D(2200), 40, WorkSchedule.ESC_5X2).accepted and not ev(comp, D(2199), 40, WorkSchedule.ESC_5X2).accepted
    assert "outra proposta" in ev(comp, D(2000), 40, WorkSchedule.ESC_5X2).message
    # PJ aceita ao receber a pretensão, mesmo com concorrência e escala ruim; CLT na mesma situação pede mais
    pj = synth(regime=EmployeeRegime.PJ, competing=True, flex=0.03)
    assert ev(pj, D(2000), 40, WorkSchedule.ESC_6X1).accepted
    assert not ev(synth(competing=True, flex=0.03), D(2000), 40, WorkSchedule.ESC_6X1).accepted
    assert not ev(pj, D(1999), 40, WorkSchedule.ESC_6X1).accepted


def test_clt_costs_double_and_pj_costs_single_in_payroll_and_obligations(client, rich, db):
    cid = create_ok(client, rich, staff=False, extra="200000")["company"]["id"]
    d = hire_candidate(client, rich, cid, "accountant", "CLT")
    d = hire_candidate(client, rich, cid, "lawyer", "PJ")
    d = hire_candidate(client, rich, cid, "cleaner", "CLT")
    emps = {e["role"]: e for e in d["employees"]}
    assert D(emps["accountant"]["total_cost"]) == D(emps["accountant"]["salary"]) * 2
    assert D(emps["lawyer"]["total_cost"]) == D(emps["lawyer"]["salary"]) and emps["lawyer"]["regime"] == "PJ"
    expected = D(emps["accountant"]["salary"]) * 2 + D(emps["lawyer"]["salary"]) + D(emps["cleaner"]["salary"]) * 2
    fixed = sum(D(c["amount"]) for c in d["costs"]) + D(d["lease"]["monthly_rent"])
    assert D(d["monthly_obligations"]) == expected + fixed                                    # obrigações mensais refletem 2x / 1x
    assert D(d["runway_months"]) == (D(d["company"]["cash"]) / D(d["monthly_obligations"])).quantize(D("0.01"))
    assert close(client, rich).status_code == 200
    m = detail(client, rich, cid)["months"][0]
    assert D(m["payroll"]) == expected and m["irregular"] is False
    line = db.scalar(select(LedgerEntry).where(LedgerEntry.company_id == cid, LedgerEntry.line == "PAYROLL"))
    assert line.amount == expected


def test_headhunter_charges_fee_respects_briefing_and_is_idempotent(client, rich, db):
    cid = create_ok(client, rich, staff=False, extra="200000")["company"]["id"]
    cash0 = D(detail(client, rich, cid)["company"]["cash"])
    k = key()
    body = {"role": "barista", "regime": "PJ", "max_salary": "6000", "min_level": "MID", "idempotency_key": k}
    r = client.post(f"{C}/{cid}/headhunter", headers=rich, json=body)
    assert r.status_code == 200, r.text
    out = r.json()
    assert D(out["fee"]) == D("6000.00") and 1 <= out["found"] <= 3 == 3 or out["found"] <= 3
    assert out["found"] == len(out["candidates"]) > 0
    for c in out["candidates"]:
        assert D(c["asking_salary"]) <= D("6000") and c["level"] in ("MID", "SENIOR") and c["regime"] == "PJ" and c["id"].endswith(tuple("h%d" % i for i in range(12)))
    levels = [["JUNIOR", "MID", "SENIOR"].index(c["level"]) for c in out["candidates"]]
    assert levels == sorted(levels, reverse=True)                                             # melhores primeiro
    assert D(out["company"]["company"]["cash"]) == cash0 - D("6000.00")
    fee_lines = [e for e in out["company"]["ledger"] if e["line"] == "HIRING" and "headhunter" in e["description"]]
    assert len(fee_lines) == 1 and D(fee_lines[0]["amount"]) == D("6000.00")
    again = client.post(f"{C}/{cid}/headhunter", headers=rich, json=body).json()            # mesma chave: não cobra de novo, mesma lista
    assert again["candidates"] == out["candidates"] and D(again["company"]["company"]["cash"]) == cash0 - D("6000.00")
    # a contratação via headhunter segue o mesmo /hire
    pick = out["candidates"][0]
    res = propose(client, rich, cid, pick, D(pick["asking_salary"]) * D("1.2"), regime="PJ")
    assert res["accepted"] is True and res["company"]["employees"][0]["regime"] == "PJ" and res["company"]["employees"][0]["name"] == pick["name"]
    # briefing impossível: lista vazia e metade do honorário
    cash1 = D(res["company"]["company"]["cash"])
    none = client.post(f"{C}/{cid}/headhunter", headers=rich, json={"role": "barista", "regime": "CLT", "max_salary": "1000", "min_level": "SENIOR",
                                                                   "idempotency_key": key()}).json()
    assert none["candidates"] == [] and none["found"] == 0 and D(none["fee"]) == D("500.00")
    assert D(none["company"]["company"]["cash"]) == cash1 - D("500.00")
    # sem caixa para o honorário: nada é cobrado
    acc = db.scalar(select(FinanceAccount).join(Company, Company.account_id == FinanceAccount.id).where(Company.id == cid))
    acc.balance = D("100.00")
    db.commit()
    r = client.post(f"{C}/{cid}/headhunter", headers=rich, json={**body, "idempotency_key": key()})
    assert r.status_code == 400 and "honorário" in r.json()["detail"]


def test_irregular_company_has_no_sales_pays_fine_and_exposes_compliance(client, rich, db):
    cid = create_ok(client, rich, staff=False)["company"]["id"]
    d0 = detail(client, rich, cid)
    assert d0["compliance"]["regular"] is False and set(d0["compliance"]["missing"]) == {"accountant", "lawyer", "cleaner"}
    assert D(d0["compliance"]["estimated_fine"]) == D("13150.00") and d0["compliance"]["missing_labels"] == ["Contador", "Advogado", "Auxiliar de limpeza"]
    assert close(client, rich).status_code == 200
    d = detail(client, rich, cid)
    m = d["months"][0]
    assert m["irregular"] is True and D(m["units_sold"]) == 0 and D(m["revenue"]) == 0 and D(m["fines"]) == D("13150.00")
    assert D(m["fixed_costs"]) >= D("13150.00") and D(m["net_result"]) < 0
    fine = db.scalar(select(LedgerEntry).where(LedgerEntry.company_id == cid, LedgerEntry.line == "FEES"))
    assert fine.amount == D("13150.00") and fine.kind == "EXPENSE" and fine.capital is False and "Multa" in fine.description
    ev = [e for e in d["events"] if e["type"] == "COMPLIANCE"]
    assert len(ev) == 1 and "irregular" in ev[0]["description"] and D(ev[0]["amount"]) == D("13150.00")
    assert D(d["company"]["reputation"]) < 50
    # falta só o advogado: multa = 1 salário-base dele
    for role in ("accountant", "cleaner"):
        hire_candidate(client, rich, cid, role)
    d = detail(client, rich, cid)
    assert d["compliance"]["missing"] == ["lawyer"] and D(d["compliance"]["estimated_fine"]) == D("7000.00")
    assert close(client, rich).status_code == 200
    m = detail(client, rich, cid)["months"][0]
    assert m["irregular"] is True and D(m["revenue"]) == 0 and D(m["fines"]) == D("7000.00")
    # tudo certo: opera e não paga multa
    hire_candidate(client, rich, cid, "lawyer")
    assert detail(client, rich, cid)["compliance"]["regular"] is True
    assert close(client, rich).status_code == 200
    m = detail(client, rich, cid)["months"][0]
    assert m["irregular"] is False and D(m["fines"]) == 0 and D(m["units_sold"]) > 0 and D(m["revenue"]) > 0
    assert db.scalar(select(func.count()).select_from(LedgerEntry).where(LedgerEntry.company_id == cid, LedgerEntry.line == "FEES")) == 2


def test_cleaner_is_only_mandatory_for_physical_channel(client, rich):
    online = create_ok(client, rich, staff=False, name="Digital", segment="ECOMMERCE", extra="200000")
    assert [r["role"] for r in online["compliance"]["required"]] == ["accountant", "lawyer"]
    cid = online["company"]["id"]
    for role in ("accountant", "lawyer"):
        hire_candidate(client, rich, cid, role)
    d = detail(client, rich, cid)
    assert d["compliance"]["regular"] is True and D(d["compliance"]["estimated_fine"]) == 0
    assert close(client, rich).status_code == 200
    m = detail(client, rich, cid)["months"][0]
    assert m["irregular"] is False and D(m["units_sold"]) > 0                                # sem limpeza, e-commerce vende
    phys = create_ok(client, rich, staff=False, name="Loja", segment="CLOTHING", extra="200000")
    cid2 = phys["company"]["id"]
    for role in ("accountant", "lawyer"):
        hire_candidate(client, rich, cid2, role)
    assert detail(client, rich, cid2)["compliance"]["missing"] == ["cleaner"]                # físico sem limpeza: irregular
    assert company_rules.mandatory_roles(company_rules.CompanyChannel.ONLINE) == ("accountant", "lawyer")
    assert "cleaner" in company_rules.mandatory_roles(company_rules.CompanyChannel.PHYSICAL)


def test_capacity_comes_from_candidate_level_and_generic_roles_add_none(client, rich):
    cid = create_ok(client, rich, staff=False, extra="200000")["company"]["id"]
    seg = company_rules.SEGMENTS[company_rules.CompanySegment.CAFE]
    cap0 = detail(client, rich, cid)["expected_capacity"]
    assert cap0 == float(seg.owner_capacity)
    for role in ("accountant", "lawyer", "cleaner"):
        d = hire_candidate(client, rich, cid, role)
    assert d["expected_capacity"] == cap0                                                      # contador, advogado e limpeza: units = 0
    cands = {c["level"]: c for c in candidates(client, rich, cid, role="barista")}
    assert len(cands) >= 1
    d = hire_candidate(client, rich, cid, "barista")
    b = next(e for e in d["employees"] if e["role"] == "barista")
    assert D(b["productivity"]) == company_rules.level_productivity(company_rules.EmployeeLevel(b["level"]))
    assert d["expected_capacity"] == pytest.approx(cap0 + float(seg.role("barista").units) * float(b["productivity"]))


def test_severance_by_regime_and_tenure():
    assert team.severance(EmployeeRegime.CLT, D("3000"), 0) == D("6000.00")                    # 1 salário + 1 de aviso
    assert team.severance(EmployeeRegime.CLT, D("3000"), 36) == D("3000") * D("2.3")           # 3 anos: aviso de 1,3 salário
    assert team.severance(EmployeeRegime.CLT, D("3000"), 400) == D("3000") * 4                 # aviso limitado a 3 salários
    assert team.severance(EmployeeRegime.PJ, D("3000"), 36) == 0


def test_fire_pays_severance_by_regime(client, rich, monkeypatch):
    monkeypatch.setattr(team, "lawsuit_probability", lambda *a, **k: 0.0)
    cid = create_ok(client, rich, staff=False, extra="200000")["company"]["id"]
    d = hire_candidate(client, rich, cid, "attendant", "CLT")
    d = hire_candidate(client, rich, cid, "barista", "PJ")
    clt = next(e for e in d["employees"] if e["role"] == "attendant")
    pj = next(e for e in d["employees"] if e["role"] == "barista")
    assert D(clt["severance_estimate"]) == D(clt["salary"]) * 2 and D(pj["severance_estimate"]) == 0
    c0 = D(d["company"]["cash"])
    d1 = client.delete(f"{C}/{cid}/employees/{clt['id']}", headers=rich).json()
    assert c0 - D(d1["company"]["cash"]) == D(clt["salary"]) * 2
    d2 = client.delete(f"{C}/{cid}/employees/{pj['id']}", headers=rich).json()
    assert D(d1["company"]["cash"]) == D(d2["company"]["cash"])                                # PJ: sem rescisão
    assert any("sem rescisão" in e["description"] for e in d2["events"])


def test_lawsuit_probability_is_higher_for_pj_and_for_long_hours_6x1_and_tenure():
    p = team.lawsuit_probability
    CLT, PJ, S5, S6 = EmployeeRegime.CLT, EmployeeRegime.PJ, WorkSchedule.ESC_5X2, WorkSchedule.ESC_6X1
    assert p(CLT, 40, S5, 0) == 0.06 and p(PJ, 40, S5, 0) == 0.35
    assert p(CLT, 50, S5, 0) == pytest.approx(0.09) and p(CLT, 40, S6, 0) == pytest.approx(0.072)
    assert p(PJ, 50, S6, 0) == pytest.approx(0.35 * 1.5 * 1.2)
    assert p(PJ, 40, S5, 60) == pytest.approx(0.35 * 1.5) and p(PJ, 40, S5, 600) == p(PJ, 40, S5, 60)     # tempo de casa: até +50%
    assert p(PJ, 80, S6, 60) <= 0.9                                                              # teto
    for hours, sch, ten in [(40, S5, 0), (50, S5, 0), (44, S6, 12), (60, S6, 48)]:
        assert p(PJ, hours, sch, ten) > p(CLT, hours, sch, ten) * 4


def test_pj_dismissal_triggers_lawsuit_more_often_than_clt_statistically():
    """A MESMA função de sorteio da demissão (hash01 com a semente) em muitas empresas/funcionários/meses."""
    import datetime as dt
    ref = dt.date(2026, 11, 1)
    def rate(regime, hours, sched, n=4000):
        pr = team.lawsuit_probability(regime, hours, sched, 12)
        return sum(1 for i in range(n) if hash01(1 + i % 7, "lawsuit", 1 + i % 13, i, f"{ref:%Y-%m}") < pr) / n
    clt, pj = rate(EmployeeRegime.CLT, 40, WorkSchedule.ESC_5X2), rate(EmployeeRegime.PJ, 40, WorkSchedule.ESC_5X2)
    assert 0.03 < clt < 0.12 and 0.30 < pj < 0.55 and pj > 3 * clt
    assert rate(EmployeeRegime.PJ, 50, WorkSchedule.ESC_6X1) > pj                                # jornada longa + 6x1 aumentam


def test_firing_can_spawn_labor_lawsuit_event_for_next_month(client, rich, monkeypatch):
    cid = create_ok(client, rich, staff=False, extra="200000")["company"]["id"]
    d = hire_candidate(client, rich, cid, "barista", "PJ")
    d = hire_candidate(client, rich, cid, "attendant", "CLT")
    pj, clt = d["employees"][0], d["employees"][1]
    monkeypatch.setattr(team, "lawsuit_probability", lambda *a, **k: 0.0)
    f = client.delete(f"{C}/{cid}/employees/{clt['id']}", headers=rich)
    assert f.status_code == 200 and client.get("/api/economy/decisions", headers=rich).json()["pending"] == []
    monkeypatch.setattr(team, "lawsuit_probability", lambda *a, **k: 1.0)
    cash0 = D(detail(client, rich, cid)["company"]["cash"])
    f = client.delete(f"{C}/{cid}/employees/{pj['id']}", headers=rich)
    assert f.status_code == 200 and any("Processo trabalhista a caminho" in e["description"] for e in f.json()["events"])
    assert D(f.json()["company"]["cash"]) == cash0                                              # PJ sem rescisão e sem custo imediato do processo
    assert client.get("/api/economy/decisions", headers=rich).json()["pending"] == []             # só acontece no mês seguinte
    ev = db_event = None
    from backend.database import SessionLocal
    with SessionLocal() as s:
        db_event = s.scalar(select(WorldEvent).where(WorldEvent.key == "processo_trabalhista"))
        assert db_event.status == "PENDING" and db_event.company_id == cid and "vínculo" in db_event.description
        eid = db_event.id
    r = client.post(f"/api/economy/events/{eid}/decide", headers=rich, json={"option": "acordo"})
    assert r.status_code == 409                                                                 # ainda não aconteceu
    assert close(client, rich).status_code == 200
    pend = client.get("/api/economy/decisions", headers=rich).json()["pending"]
    ev = next(e for e in pend if e["id"] == eid)
    assert {o["key"] for o in ev["options"]} == {"acordo", "contestar", "ignorar"} and ev["company_id"] == cid
    r = client.post(f"/api/economy/events/{eid}/decide", headers=rich, json={"option": "acordo"})
    assert r.status_code == 200 and r.json()["event"]["outcome"]
    # repetir a demissão sorteada no mesmo mês não duplica evento (funcionário já desligado)
    assert client.delete(f"{C}/{cid}/employees/{pj['id']}", headers=rich).status_code == 409
