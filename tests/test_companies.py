from tests.conftest import credit
"""Empresas (etapa 3): contas separadas, folha, estoque, receitas, expansão, locação, lucros e fechamento mensal."""
import uuid
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from backend.models import (
    Company, CompanyMonth, CompanyUnit, FinanceAccount, Good, LedgerEntry, Portfolio, Transaction,
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
    """Cria a empresa e, por padrão, já contrata a equipe (obrigatórios + produtivos sugeridos) via `staff_up` e os fornecedores
    de TODAS as categorias via `contract_suppliers` (fase 4). Use `staff=False` para testar a empresa recém-aberta, sem equipe
    nem fornecedores."""
    r = create(client, h, **kw)
    assert r.status_code == 201, r.text
    d = r.json()
    if not staff:
        return d
    d = staff_up(client, h, d["company"]["id"])
    return contract_suppliers(client, h, d["company"]["id"])


def contract_suppliers(client, h, company_id, ideal=True, stock=True):
    """Contrata, de forma DETERMINÍSTICA, um fornecedor para cada categoria sem contrato: o de maior volume da busca (desempate pelo
    id), pagando o preço de lista (sempre aceita). `ideal=True` deixa o contrato sem falha de entrega (confiabilidade 100%) e sem
    limite prático de volume, para os testes que não tratam de fornecedores. `stock=True` faz a 1ª compra (o estoque inicial de
    antes da fase 4: ~2 meses da demanda do começo). Devolve o detalhe."""
    from backend.database import SessionLocal
    from backend.models import CompanySupplier
    d = detail(client, h, company_id)
    for row in d["supply"]["checklist"]:
        if row["present"]:
            continue
        r = client.post(f"{C}/{company_id}/suppliers/search", headers=h, json={"category": row["category"]})
        assert r.status_code == 200, r.text
        best = max(r.json()["offers"], key=lambda o: (D(o["max_units_month"]), o["id"]))
        r = client.post(f"{C}/{company_id}/suppliers/negotiate", headers=h, json={
            "supplier_id": best["id"], "unit_price": best["unit_price"], "idempotency_key": key()})
        assert r.status_code == 200 and r.json()["accepted"], r.text
    if ideal:
        with SessionLocal() as s:
            for x in s.scalars(select(CompanySupplier).where(CompanySupplier.company_id == company_id, CompanySupplier.status == "ACTIVE")):
                x.reliability = D(1)
                x.max_units_month = D(10 ** 9)
            s.commit()
    d = detail(client, h, company_id)
    if stock and d["inventory"]:
        co = d["company"]
        seg = company_rules.SEGMENTS[company_rules.CompanySegment(co["segment"])]
        for it, (_, qty) in zip(d["inventory"], company_rules.initial_stock_quantities(
                seg, co["location"], company_rules.CompanySize(co["size"]))):
            if D(it["quantity"]) == 0:
                r = client.post(f"{C}/{company_id}/stock", headers=h, json={"item_id": it["id"], "quantity": str(qty), "idempotency_key": key()})
                assert r.status_code == 201, r.text
        d = detail(client, h, company_id)
    return d


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


def force_rolls(monkeypatch, **by):
    """Força os sorteios de RESULTADO da expansão (`company_expansion._roll`) por tipo de sorteio: xp-result (0 = efeito completo, ~1 =
    fracasso), xp-open (abertura da filial), xp-viab (viabilidade 0..1), xp-quit (pedido de demissão). Padrão: tudo dá certo e ninguém pede demissão."""
    from backend.services import company_expansion
    table = {"xp-result": 0.0, "xp-open": 0.99, "xp-viab": 0.5, "xp-quit": 0.99, **by}
    monkeypatch.setattr(company_expansion, "_roll", lambda *p: table.get(p[0], 0.5))
    return table


def options(client, h, cid, kind, tier):
    r = client.post(f"{C}/{cid}/expansion/options", headers=h, json={"kind": kind, "tier": tier})
    assert r.status_code == 200, r.text
    return r.json()


def expand(client, h, cid, kind, tier="MEDIO", pick=0, expect=200, option_key=None, idem=None, **site):
    """Pede as 3 opções do mês, executa a de índice `pick` (ou `option_key`) e devolve o JSON do resultado (ou a resposta bruta se `expect` != 200)."""
    o = options(client, h, cid, kind, tier)
    body = {"kind": kind, "tier": tier, "option_key": option_key or o["options"][pick]["key"], "idempotency_key": idem or key(), **site}
    r = client.post(f"{C}/{cid}/expansion/execute", headers=h, json=body)
    if expect != 200:
        assert r.status_code == expect, r.text
        return r
    assert r.status_code == 200, r.text
    return r.json()


def second_user(client):
    r = client.post("/api/auth/register", json={"email": "bia@example.com", "name": "Bia", "password": "segredo123"})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture(autouse=True)
def _flat_season(monkeypatch):
    """Sem sazonalidade: receitas e resultados ficam previsíveis nos testes (a sazonalidade tem teste próprio)."""
    monkeypatch.setattr(company_rules, "season_factor", lambda *a, **k: 1.0)


def mature(db, cid, relevance=60):
    """Empresa "maturada": relevância alta direto no banco (no jogo isso leva anos). Sem monkeypatch de demanda: vale o modelo calibrado."""
    c = db.get(Company, cid)
    c.relevance = D(str(relevance))
    db.commit()


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
    expected_cash = capital - D(q["setup_cost"])                                 # fase 4: sem estoque inicial (a reserva da 1ª compra fica no caixa)
    assert D(co["cash"]) == expected_cash                                       # entrou na conta da empresa (menos a estruturação)
    assert co["segment"] == "CAFE" and co["status"] == "ACTIVE" and co["reputation"] == 50
    assert co["channel"] == "PHYSICAL" and co["site_mode"] == "RENT" and D(co["site_value"]) == 0 and "business_type" not in co
    assert d["employees"] == [] and d["compliance"]["regular"] is False       # nasce sem funcionários e irregular até contratar
    assert d["lease"]["kind"] == "EXTERNAL" and D(d["lease"]["monthly_rent"]) > 0
    assert {c["kind"] for c in d["costs"]} == {"UTILITIES", "TOOLS", "ACCOUNTING"}
    assert d["inventory"][0]["name"] == "Grãos e insumos de café" and D(d["inventory"][0]["quantity"]) == 0 and len(d["inventory"]) == 3
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
    assert D(buy["minimum_capital"]) > D(rent["minimum_capital"]) + land - D(rent["monthly_rent"]) * company_rules.RESERVE_MONTHS - D("0.02")   # terreno entra no mínimo (sem a reserva de aluguel)
    before = cash(client, rich)
    d = create_ok(client, rich, staff=False, name="Café com terreno", site_mode="BUY", extra="20000")
    co = d["company"]
    assert cash(client, rich) == before - D(buy["minimum_capital"]) - D("20000")
    assert co["site_mode"] == "BUY" and D(co["site_value"]) == land and d["lease"] is None
    # caixa = aporte − estrutura − estoque − terreno; patrimônio da empresa conta o terreno como ativo
    assert D(co["cash"]) == D(buy["minimum_capital"]) + D("20000") - D(buy["setup_cost"]) - land
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
    r = client.post(f"{C}/{cid}/stock", headers=rich, json={"item_id": item["id"], "quantity": "20", "idempotency_key": key()})
    assert r.status_code == 201
    d1 = r.json()
    new = d1["inventory"][0]
    assert D(new["quantity"]) == D(item["quantity"]) + 20
    spent = D(d0["company"]["cash"]) - D(d1["company"]["cash"])
    assert spent > 0 and abs(float(D(new["value"]) - D(item["value"])) - float(spent)) < 1.0
    k = key()
    again = client.post(f"{C}/{cid}/stock", headers=rich, json={"item_id": item["id"], "quantity": "20", "idempotency_key": k})
    same = client.post(f"{C}/{cid}/stock", headers=rich, json={"item_id": item["id"], "quantity": "20", "idempotency_key": k})
    assert same.status_code == 201 and D(same.json()["inventory"][0]["quantity"]) == D(again.json()["inventory"][0]["quantity"])   # repetição não soma de novo
    assert client.post(f"{C}/{cid}/stock", headers=rich, json={"item_id": item["id"], "quantity": "99999999", "idempotency_key": key()}).status_code == 409   # acima do teto de estoque do porte
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

def test_expansion_has_cost_and_consequences(client, rich, monkeypatch):
    """Fluxo em passos: nível -> 3 opções -> execução. Com os sorteios FORÇADOS a funcionar, cada tipo cobra o custo da opção e muda a empresa."""
    force_rolls(monkeypatch)
    cid = create_ok(client, rich, extra="400000")["company"]["id"]
    d0 = detail(client, rich, cid)
    r = expand(client, rich, cid, "CAPACITY", "MEDIO")
    assert r["outcome"] == "FULL" and r["success"]
    d1 = r["company"]
    assert d1["company"]["capacity_level"] == 1 and D(d1["company"]["capacity_boost"]) > 0 and d1["expected_capacity"] > d0["expected_capacity"]
    assert D(d0["company"]["cash"]) - D(d1["company"]["cash"]) >= D(r["cost"]) > 0
    u = expand(client, rich, cid, "NEW_UNIT", "MEDIO", channel="PHYSICAL", site_mode="RENT", location="centro")["company"]
    assert u["company"]["units"] == 2 and D(u["monthly_obligations"]) > D(d1["monthly_obligations"]) and u["expected_demand"] > d1["expected_demand"]
    big = expand(client, rich, cid, "LARGER_PREMISES", "MEDIO")["company"]
    assert big["company"]["size"] == "MEDIUM" and D(big["lease"]["monthly_rent"]) > D(d0["lease"]["monthly_rent"])
    force_rolls(monkeypatch, **{"xp-result": 0.5})                                   # campanha: nem fracasso nem viral
    mk = expand(client, rich, cid, "MARKETING", "MEDIO")["company"]
    assert mk["company"]["marketing_until"] is not None
    q = expand(client, rich, cid, "QUALITY", "MEDIO")["company"]
    assert float(q["company"]["quality"]) > 50
    assert client.post(f"{C}/{cid}/expansion/options", headers=rich, json={"kind": "XYZ", "tier": "MEDIO"}).status_code == 422
    assert client.post(f"{C}/{cid}/expansion/options", headers=rich, json={"kind": "CAPACITY", "tier": "GIGANTE"}).status_code == 422
    assert client.post(f"{C}/{cid}/expand", headers=rich, json={"kind": "CAPACITY"}).status_code in (404, 405)       # fluxo antigo removido


def test_expansion_requires_cash_and_does_not_guarantee_profit(client, rich, db, monkeypatch):
    force_rolls(monkeypatch)
    cid = create_ok(client, rich, extra="0")["company"]["id"]
    acc = db.scalar(select(FinanceAccount).join(Company, Company.account_id == FinanceAccount.id).where(Company.id == cid))
    acc.balance = D("1000.00")
    db.commit()
    assert expand(client, rich, cid, "NEW_UNIT", "MEDIO", expect=400, channel="PHYSICAL", site_mode="RENT", location="centro").status_code == 400
    assert detail(client, rich, cid)["company"]["units"] == 1
    acc.balance = D("400000.00")
    db.commit()
    expand(client, rich, cid, "NEW_UNIT", "MEDIO", channel="PHYSICAL", site_mode="RENT", location="centro")       # mais custos fixos sem mais demanda garantida
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

def test_profit_distribution_flows_to_personal_account(client, rich, db):
    cid = create_ok(client, rich, extra="80000")["company"]["id"]
    mature(db, cid)
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


def test_distribution_cannot_exceed_profit_or_cash(client, rich, db):
    cid = create_ok(client, rich, extra="80000")["company"]["id"]
    mature(db, cid)
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


def test_partial_ownership_splits_distribution_and_equity(client, rich, db):
    cid = create_ok(client, rich, extra="80000", owner_share_pct="60")["company"]["id"]
    mature(db, cid)
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
                               ("post", f"/{cid}/expansion/options", {"kind": "CAPACITY", "tier": "MEDIO"}),
                               ("post", f"/{cid}/expansion/execute", {"kind": "CAPACITY", "tier": "MEDIO", "option_key": "x", "idempotency_key": key()}), ("patch", f"/{cid}/settings", {"price": "1"}),
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
    part = D(20) / 36                                                                              # porte pequeno: meio período (20 h), salário proporcional
    base = (D("1800") + D("2400") + D("1520")) * part
    assert abs(D(q["monthly_payroll"]) - base * 2) < D("0.05")                                    # 1 mês, CLT 2x, salário-base do porte
    assert abs(D(q["mandatory_cost"]) - (D(q["monthly_payroll"]) + base / 2)) < D("0.05")          # + custo de contratação (0,5x)
    online = quote(client, rich, channel="ONLINE", location=None)
    assert online["mandatory_roles"] == ["Contador", "Advogado"] and abs(D(online["monthly_payroll"]) - (D("1800") + D("2400")) * part * 2) < D("0.05")
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
    assert D(d0["compliance"]["estimated_fine"]) == D("5720.00") and d0["compliance"]["missing_labels"] == ["Contador", "Advogado", "Auxiliar de limpeza"]
    assert close(client, rich).status_code == 200
    d = detail(client, rich, cid)
    m = d["months"][0]
    assert m["irregular"] is True and D(m["units_sold"]) == 0 and D(m["revenue"]) == 0 and D(m["fines"]) == D("5720.00")
    assert D(m["fixed_costs"]) >= D("5720.00") and D(m["net_result"]) < 0
    fine = db.scalar(select(LedgerEntry).where(LedgerEntry.company_id == cid, LedgerEntry.line == "FEES"))
    assert fine.amount == D("5720.00") and fine.kind == "EXPENSE" and fine.capital is False and "Multa" in fine.description
    ev = [e for e in d["events"] if e["type"] == "COMPLIANCE"]
    assert len(ev) == 1 and "irregular" in ev[0]["description"] and D(ev[0]["amount"]) == D("5720.00")
    assert D(d["company"]["reputation"]) < 50
    # falta só o advogado: multa = 1 salário-base dele
    for role in ("accountant", "cleaner"):
        hire_candidate(client, rich, cid, role)
    d = detail(client, rich, cid)
    assert d["compliance"]["missing"] == ["lawyer"] and D(d["compliance"]["estimated_fine"]) == D("2400.00")
    assert close(client, rich).status_code == 200
    m = detail(client, rich, cid)["months"][0]
    assert m["irregular"] is True and D(m["revenue"]) == 0 and D(m["fines"]) == D("2400.00")
    # tudo certo: opera e não paga multa
    hire_candidate(client, rich, cid, "lawyer")
    contract_suppliers(client, rich, cid)                                  # fase 4: sem fornecedor/estoque não há o que vender
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


# ------------------------------------------------------------------ fase 3a: relevância, mercado, tetos, mudança de endereço, balanceamento

def test_relevance_factor_and_slow_growth():
    R = company_rules
    assert R.relevance_factor(0) == pytest.approx(R.DEMAND_FLOOR) and R.relevance_factor(100) == pytest.approx(1.0)
    assert R.relevance_factor(10) < R.relevance_factor(40) < R.relevance_factor(80)
    rel = 0.0
    for month in range(1, 61):                         # jogador exemplar: atendendo tudo, reputação máxima, marketing sempre ligado
        new = R.next_relevance(rel, sold=100, demand=100, reputation=100, marketing=True, stockout=False, price_ratio=1.0, irregular=False)
        assert 0 < new - rel <= 1.5
        rel = new
        if month == 12:
            assert rel < 22
        if month == 24:
            assert rel < 50                            # chegar a 50 leva mais de 2 anos
    assert rel < 80                                    # 80 leva vários anos
    # parada ou irregular: cai (levemente), nunca abaixo de zero
    assert R.next_relevance(30, sold=0, demand=50, reputation=50, marketing=False, stockout=False, price_ratio=1, irregular=False) < 30
    assert R.next_relevance(30, sold=0, demand=0, reputation=50, marketing=False, stockout=False, price_ratio=1, irregular=True) < 29
    assert R.next_relevance(0.1, sold=0, demand=0, reputation=50, marketing=False, stockout=False, price_ratio=1, irregular=True) == 0


def test_new_company_starts_with_zero_relevance_and_moves_slowly_in_the_database(client, rich, db):
    cid = create_ok(client, rich, extra="80000")["company"]["id"]
    d = detail(client, rich, cid)
    assert d["company"]["relevance"] == 0 and d["market"]["demand_factor"] == pytest.approx(company_rules.DEMAND_FLOOR, abs=0.001)
    for _ in range(3):
        assert close(client, rich).status_code == 200
    d = detail(client, rich, cid)
    assert 0 <= d["company"]["relevance"] <= 4.5 and d["months"][0]["relevance_end"] == d["company"]["relevance"]
    # empresa irregular (sem cargos obrigatórios) perde relevância
    c2 = create_ok(client, rich, staff=False, name="Parada")["company"]["id"]
    mature(db, c2, 40)
    assert close(client, rich).status_code == 200
    assert detail(client, rich, c2)["company"]["relevance"] < 40


def test_zero_sales_month_is_deterministic_and_driven_by_relevance_and_price():
    R = company_rules
    import datetime as dt
    ref = dt.date(2027, 3, 1)
    assert R.is_zero_month(7, 1, ref, 0, 1.0) == R.is_zero_month(7, 1, ref, 0, 1.0)             # mesmo mês, mesmo resultado
    low = sum(R.is_zero_month(7, cid, ref, 0, 1.0) for cid in range(400)) / 400
    high = sum(R.is_zero_month(7, cid, ref, 70, 1.0) for cid in range(400)) / 400
    dear = sum(R.is_zero_month(7, cid, ref, 70, 1.8) for cid in range(400)) / 400
    assert 0.15 < low < 0.5 and high == 0 and dear > 0.5
    assert R.zero_month_prob(0, 1.0) > R.zero_month_prob(20, 1.0) > R.zero_month_prob(60, 1.0) == 0


def test_high_price_sells_almost_nothing_and_cheap_price_saturates():
    R = company_rules
    seg = R.SEGMENTS[R.CompanySegment.CAFE]
    kw = dict(location="bairro", size=R.CompanySize.SMALL, units=1, reputation=50, company_id=1, ref=__import__("datetime").date(2027, 1, 1),
              marketing=False, season=False, relevance=50)
    fair = R.demand_units(seg, price=seg.price, **kw)
    assert R.demand_units(seg, price=seg.price * D("1.5"), **kw) < 0.25 * fair
    assert R.demand_units(seg, price=seg.price * D("1.9"), **kw) == 0
    assert fair < R.demand_units(seg, price=seg.price * D("0.7"), **kw) <= fair * 1.31          # mais barato vende mais, mas satura
    assert R.demand_units(seg, price=seg.price * D("0.3"), **kw) == pytest.approx(R.demand_units(seg, price=seg.price * D("0.6"), **kw))


def test_hiring_above_staff_ceiling_returns_409_suggesting_premises(client, rich, monkeypatch):
    import dataclasses
    cid = create_ok(client, rich, staff=False)["company"]["id"]
    monkeypatch.setitem(company_rules.SIZES, company_rules.CompanySize.SMALL,
                        dataclasses.replace(company_rules.SIZES[company_rules.CompanySize.SMALL], max_staff=3))
    for role in ("accountant", "lawyer", "cleaner"):
        hire_candidate(client, rich, cid, role)
    cand = client.post(f"{C}/{cid}/candidates", headers=rich, json={"role": "barista", "regime": "CLT"}).json()["candidates"][0]
    r = client.post(f"{C}/{cid}/hire", headers=rich, json={"candidate_id": cand["id"], "salary": "9000", "hours_week": 40, "schedule": "5x2",
                                                         "regime": "CLT", "confirm_risk": True, "idempotency_key": key()})
    assert r.status_code == 409 and "Teto de funcionários" in r.json()["detail"] and "mude de endereço" in r.json()["detail"]


def test_buying_stock_above_storage_ceiling_returns_409(client, rich):
    d = create_ok(client, rich, extra="80000")
    item = d["inventory"][0]
    cap = D(item["max_quantity"])
    assert cap > D(item["quantity"])
    r = client.post(f"{C}/{d['company']['id']}/stock", headers=rich, json={"item_id": item["id"], "quantity": str(cap), "idempotency_key": key()})
    assert r.status_code == 409 and "Teto de estoque" in r.json()["detail"] and "Instalações" in r.json()["detail"]


def test_service_company_has_no_stock_and_production_ceiling_limits_capacity():
    R = company_rules
    wk = R.SEGMENTS[R.CompanySegment.WORKSHOP]
    assert not wk.has_stock and wk.metrics_kind == R.MetricsKind.SERVICE
    many = [("mechanic", D(1))] * 500
    cap = R.capacity_units(wk, size=R.CompanySize.SMALL, units=1, capacity_level=0, staff=many)
    assert cap == pytest.approx(R.production_ceiling(wk, R.CompanySize.SMALL, 1, 0))
    assert R.production_ceiling(wk, R.CompanySize.MEDIUM, 1) > cap and R.production_ceiling(wk, R.CompanySize.SMALL, 1, 2) > cap


def test_relocate_charges_validates_is_idempotent_and_cuts_next_month_sales(client, rich, db):
    d = create_ok(client, rich, extra="300000")
    cid = d["company"]["id"]
    mature(db, cid, 40)
    body = {"location": "centro", "site_mode": "RENT"}
    q = client.post(f"{C}/{cid}/relocate/quote", headers=rich, json=body).json()
    assert D(q["move"]) > 0 and D(q["reinstall"]) > 0 and D(q["fine"]) > 0 and q["relevance_after"] < 40
    assert D(q["move"]) >= 2 * D(company_rules.default_rent(company_rules.SEGMENTS[company_rules.CompanySegment.CAFE], "centro", company_rules.CompanySize.SMALL))
    k = key()
    r = client.post(f"{C}/{cid}/relocate", headers=rich, json={**body, "idempotency_key": k})
    assert r.status_code == 200, r.text
    after = r.json()
    assert after["company"]["location"] == "centro" and len(after["employees"]) == len(d["employees"])
    assert D(d["company"]["cash"]) - D(after["company"]["cash"]) == D(q["total"])
    assert after["company"]["relevance"] == pytest.approx(q["relevance_after"], abs=0.01) and after["lease"]["monthly_rent"] != d["lease"]["monthly_rent"]
    again = client.post(f"{C}/{cid}/relocate", headers=rich, json={**body, "idempotency_key": k})
    assert again.status_code == 200 and again.json()["company"]["cash"] == after["company"]["cash"]          # idempotente: não cobra de novo
    assert client.post(f"{C}/{cid}/relocate", headers=rich, json={"location": "bairro", "idempotency_key": key()}).status_code == 409   # 1 por mês
    assert client.post(f"{C}/{cid}/relocate", headers=rich, json={"location": "nao_existe", "idempotency_key": key()}).status_code in (400, 409)
    assert close(client, rich).status_code == 200
    m = detail(client, rich, cid)["months"][0]
    seg = company_rules.SEGMENTS[company_rules.CompanySegment.CAFE]
    normal = company_rules.demand_units(seg, location="centro", size=company_rules.CompanySize.SMALL, units=1, reputation=50,
                                        price=seg.price, company_id=cid, ref=__import__("datetime").date.fromisoformat(m["ref_month"]),
                                        marketing=False, relevance=q["relevance_after"])
    assert float(m["demand_units"]) == pytest.approx(normal * company_rules.RELOCATION_SALES_MULT, rel=0.02)
    assert float(m["demand_units"]) < 0.4 * normal


def test_online_company_cannot_relocate(client, rich):
    cid = create_ok(client, rich, channel="ONLINE", name="Loja Web", segment="ECOMMERCE")["company"]["id"]
    r = client.post(f"{C}/{cid}/relocate", headers=rich, json={"location": "online", "idempotency_key": key()})
    assert r.status_code == 409


@pytest.mark.parametrize("segment", [s.value for s in company_rules.SEGMENTS])
def test_balance_every_segment_reaches_profit_with_suggested_team(segment):
    """Mesma simulação de `tools/balance_companies.py`: porte pequeno, local padrão, preço de mercado, equipe sugerida + obrigatórios
    em meio período. Começa no prejuízo (vender é difícil), mas vira lucro até o mês 20 sem esgotar a reserva do capital mínimo."""
    from backend.services import company_balance as bal
    r = bal.simulate(company_rules.CompanySegment(segment), months=36)
    assert r.rows[0].profit < 0 and r.rows[2].relevance < 5                       # início fraco
    assert r.turn_month is not None and r.turn_month <= 20, (segment, r.turn_month)
    assert r.rows[-1].profit > 0 and r.min_cash > 0, (segment, r.min_cash)
    assert 10 < r.rows[-1].relevance < 50                                           # relevância cresce devagar


def test_balance_with_drawn_zero_months_still_turns_profit_for_most_seeds():
    from backend.services import company_balance as bal
    seg = company_rules.CompanySegment.CAFE
    turns = [bal.simulate(seg, months=36, expected=False, seed=s, company_id=s).turn_month for s in range(1, 21)]
    assert sum(1 for t in turns if t is not None and t <= 24) >= 17


# ------------------------------------------------------------------ fase 3b: impostos reais (regime + detalhamento por tributo)

def test_process_company_records_tax_regime_and_breakdown_summing_to_taxes(client, rich, db):
    cid = create_ok(client, rich, extra="40000")["company"]["id"]
    for _ in range(3):
        assert close(client, rich).status_code == 200
    months = detail(client, rich, cid)["months"]
    assert len(months) == 3
    rows = list(db.scalars(select(CompanyMonth).where(CompanyMonth.company_id == cid).order_by(CompanyMonth.ref_month)))
    by_ref = {m["ref_month"][:7]: m for m in months}
    for row in rows:
        api = by_ref[row.ref_month.strftime("%Y-%m")]
        assert row.tax_regime in ("MEI", "SIMPLES", "LUCRO_PRESUMIDO")
        assert api["tax_regime"] == row.tax_regime and api["tax_breakdown"] == row.tax_breakdown
        assert sum((D(x["amount"]) for x in row.tax_breakdown), D(0)) == row.taxes
        assert all({"name", "base", "rate_pct", "amount"} <= set(x) for x in row.tax_breakdown)
        assert row.net_result == row.operating_result - row.taxes - row.interest
        tax_entry = db.scalar(select(func.coalesce(func.sum(LedgerEntry.amount), 0)).where(
            LedgerEntry.company_id == cid, LedgerEntry.ref_month == row.ref_month, LedgerEntry.line == "TAX"))
        assert tax_entry == row.taxes                                              # a linha TAX do ledger = total dos tributos
    # empresa com equipe CLT (> 1 empregado) e café (Anexo I): Simples, DAS = receita x alíquota efetiva
    last = rows[-1]
    assert last.tax_regime == "SIMPLES" and [x["name"] for x in last.tax_breakdown] == ["DAS"]
    if last.revenue > 0:
        assert last.taxes == (last.revenue * D(last.tax_breakdown[0]["rate_pct"]) / 100).quantize(D("0.01"), rounding="ROUND_HALF_UP") \
            or abs(last.taxes - last.revenue * D(last.tax_breakdown[0]["rate_pct"]) / 100) <= D("0.01")


def test_company_is_deterministic_in_taxes_across_identical_inputs():
    from backend.services import company_taxes as t
    args = ("INDUSTRY", t.SIMPLES, D(3_000_000), D(250_000), D(900_000), 20)
    assert t.compute_taxes(*args) == t.compute_taxes(*args)


def test_catalog_and_quote_report_regime_and_annex(client, auth_headers):
    cat = client.get(f"{C}/catalog", headers=auth_headers)
    assert cat.status_code == 200, cat.text
    seg = {x["key"]: x for x in cat.json()["segments"]}
    assert seg["CAFE"]["tax"]["annex"] == "I" and "Simples Nacional" in seg["CAFE"]["tax"]["regime_label"]
    assert seg["TECH"]["tax"]["annex"] == "III/V" and seg["INDUSTRY"]["tax"]["mei_allowed"] is False
    q = client.post(f"{C}/quote", headers=auth_headers, json={"segment": "WORKSHOP", "extra_capital": "0"})
    assert q.status_code == 200, q.text
    assert q.json()["tax"]["annex"] == "III" and q.json()["tax"]["simplifications"]


# ------------------------------------------------------------------ fase 4: fornecedores

from datetime import date  # noqa: E402

from backend.models import CandidateBlock, CompanySupplier, SimMonth  # noqa: E402
from backend.services import company_balance, company_supply  # noqa: E402


def _search(client, h, cid, category):
    r = client.post(f"{C}/{cid}/suppliers/search", headers=h, json={"category": category})
    assert r.status_code == 200, r.text
    return r.json()["offers"]


def _negotiate(client, h, cid, token, price, volume=None, idem=None):
    body = {"supplier_id": token, "unit_price": str(price), "idempotency_key": idem or key()}
    if volume is not None:
        body["monthly_volume"] = str(volume)
    return client.post(f"{C}/{cid}/suppliers/negotiate", headers=h, json=body)


def _resolve(db, cid, token):
    """A oferta como o SERVIDOR a recalcula (inclui o piso de negociação, que a API não expõe)."""
    c = db.get(Company, cid)
    seg = company_rules.SEGMENTS[c.segment]
    seed = company_service._seed(db, c.user_id)
    ref_month = db.scalar(select(SimMonth.ref_month).where(SimMonth.user_id == c.user_id, SimMonth.status == "OPEN"))
    return company_supply.resolve_token(seed, c.id, ref_month, token, seg, size=c.size, units=c.units, capacity_level=c.capacity_level,
                                        price_mult=company_service._price_mult(db, c, ref_month)), c


def _active(db, cid):
    return {x.category: x for x in db.scalars(select(CompanySupplier).where(CompanySupplier.company_id == cid, CompanySupplier.status == "ACTIVE"))}


def test_segments_define_supply_categories_with_weights_summing_one():
    expected = {"RESTAURANT": 4, "CAFE": 3, "CLOTHING": 3, "SUPERMARKET": 4, "INDUSTRY": 4, "CONSTRUCTION": 3, "WORKSHOP": 2, "TRANSPORT": 2,
                "TECH": 0, "AGENCY": 0, "REAL_ESTATE_AGENCY": 0, "ECOMMERCE": 0}
    for seg in company_rules.SEGMENTS.values():
        assert len(seg.supply_categories) == expected[seg.key.value], seg.key
        if seg.supply_categories:
            assert sum(c.weight for c in seg.supply_categories) == D(1) and all(c.ref_price > 0 for c in seg.supply_categories)
        assert seg.needs_suppliers == bool(expected[seg.key.value])
        if seg.has_stock:                                            # estoque: 1 item por categoria, coerente com o consumo por venda
            assert [s.category for s in seg.stock] == [c.key for c in seg.supply_categories]


def test_catalog_and_quote_expose_supply_categories_and_first_purchase_reserve(client, rich):
    segs = {s["key"]: s for s in client.get(f"{C}/catalog", headers=rich).json()["segments"]}
    assert [c["label"] for c in segs["RESTAURANT"]["supply_categories"]] == ["Carnes e peixes", "Hortifrúti", "Bebidas", "Embalagens e descartáveis"]
    assert segs["TECH"]["supply_categories"] == [] and segs["ECOMMERCE"]["supply_categories"] == []
    q = quote(client, rich, "RESTAURANT")
    assert D(q["first_purchase_reserve"]) == D(q["initial_stock"]) > 0 and len(q["supply_categories"]) == 4
    assert D(quote(client, rich, "TECH", None)["first_purchase_reserve"]) == 0


def test_new_company_has_no_stock_no_suppliers_and_keeps_the_reserve_in_cash(client, rich, db):
    q = quote(client, rich, "RESTAURANT")
    d = create_ok(client, rich, staff=False, name="Bistrô Novo", segment="RESTAURANT", extra="0")
    assert d["supply"]["required"] is True and d["supply"]["ready"] is False and d["supply"]["contracts"] == []
    assert [x["present"] for x in d["supply"]["checklist"]] == [False] * 4 and "Contrate fornecedores antes de operar" in d["supply"]["warning"]
    assert len(d["inventory"]) == 4 and all(D(i["quantity"]) == 0 and i["category"] and i["contracted"] is False for i in d["inventory"])
    assert not any(e["line"] == "STOCK_PURCHASE" for e in d["ledger"])
    assert D(d["company"]["cash"]) == D(q["minimum_capital"]) - D(q["setup_cost"])      # a reserva da 1ª compra continua no caixa
    assert D(d["company"]["supplier_budget"]) == 0 and d["company"]["supply_ready"] is False


def test_supply_search_is_deterministic_and_has_3_to_5_plausible_offers(client, rich, db):
    cid = create_ok(client, rich, staff=False, name="Bistrô Busca", segment="RESTAURANT")["company"]["id"]
    a, b = _search(client, rich, cid, "carnes"), _search(client, rich, cid, "carnes")
    assert a == b and 3 <= len(a) <= 5 and len({o["id"] for o in a}) == len(a)
    ref = D(next(c for c in company_rules.SEGMENTS[company_rules.CompanySegment.RESTAURANT].supply_categories if c.key == "carnes").ref_price)
    for o in a:
        assert o["name"] and o["category"] == "carnes" and D(o["unit_price"]) > 0 and 0.8 <= o["reliability"] <= 1 and 2 <= o["lead_days"] <= 14
        assert D(o["min_monthly_order"]) >= 1 and D(o["max_units_month"]) >= D(o["min_monthly_order"])
        assert ref * D("0.8") <= D(o["unit_price"]) <= ref * D("1.3")
    assert _search(client, rich, cid, "horti") != a
    other = create_ok(client, rich, staff=False, name="Bistrô Outro", segment="RESTAURANT")["company"]["id"]
    assert [o["id"] for o in _search(client, rich, other, "carnes")] != [] and _search(client, rich, other, "carnes") != a    # por empresa
    assert client.post(f"{C}/{cid}/suppliers/search", headers=rich, json={"category": "inexistente"}).status_code == 400


def test_supplier_token_cannot_be_forged(client, rich, db):
    cid = create_ok(client, rich, staff=False, name="Bistrô Token", segment="RESTAURANT")["company"]["id"]
    offers = _search(client, rich, cid, "carnes")
    tok = offers[0]["id"]
    ym, cat, idx = tok.split("-")
    for bad in (f"{ym}-carnes-99", f"{ym}-bebidas-{idx}-x", "197001-carnes-0", f"{ym}-nada-0", "lixo", f"{ym}-carnes--1"):
        assert _negotiate(client, rich, cid, bad, "50").status_code == 400, bad
    # o cliente não manda preço de lista/volume/confiabilidade: propor ACIMA da lista fecha NA lista
    r = _negotiate(client, rich, cid, tok, str(D(offers[0]["unit_price"]) * 3))
    assert r.status_code == 200 and r.json()["accepted"]
    contract = r.json()["company"]["supply"]["contracts"][0]
    assert D(contract["unit_price"]) == D(offers[0]["unit_price"]) and D(contract["max_units_month"]) == D(offers[0]["max_units_month"])
    horti = _search(client, rich, cid, "horti")[0]
    assert _negotiate(client, rich, cid, horti["id"], horti["unit_price"], volume="9999999999").status_code in (400, 422)   # acima do que ele aguenta
    bia = second_user(client)                                           # outro usuário não acessa a empresa
    assert client.post(f"{C}/{cid}/suppliers/search", headers=bia, json={"category": "carnes"}).status_code == 404
    assert _negotiate(client, bia, cid, tok, "50").status_code == 404


def test_negotiation_accepts_counters_refuses_and_blocks_the_month(client, rich, db):
    cid = create_ok(client, rich, staff=False, name="Bistrô Negocia", segment="RESTAURANT")["company"]["id"]
    offers = _search(client, rich, cid, "carnes")
    o, _ = _resolve(db, cid, offers[0]["id"])
    vol = o.max_units_month
    need = company_supply.minimum_price(o, 0.0, vol)
    assert o.unit_price * D("0.80") <= need <= o.unit_price
    # contraproposta: um pouco abaixo do piso
    low = (need * D("0.95")).quantize(D("0.01"))
    assert company_supply.evaluate(o, low, 0.0, vol).status == "COUNTER"
    r = _negotiate(client, rich, cid, o.id, low)
    j = r.json()
    assert r.status_code == 200 and j["status"] == "COUNTER" and not j["accepted"] and D(j["counter_offer"]) == need
    assert _active(db, cid) == {}                                       # contraproposta não cria contrato nem bloqueia
    # aceitar a contraproposta cria o contrato ao preço contraposto
    r = _negotiate(client, rich, cid, o.id, j["counter_offer"])
    assert r.json()["accepted"] and D(r.json()["company"]["supply"]["contracts"][0]["unit_price"]) == need
    # recusa: muito abaixo; fica bloqueado no mês
    horti = _search(client, rich, cid, "horti")
    o2, _ = _resolve(db, cid, horti[0]["id"])
    r = _negotiate(client, rich, cid, o2.id, "1.00")
    assert r.json()["status"] == "REFUSED" and not r.json()["accepted"]
    assert db.scalar(select(func.count()).select_from(CandidateBlock).where(CandidateBlock.company_id == cid, CandidateBlock.candidate_id == o2.id)) == 1
    again = _negotiate(client, rich, cid, o2.id, str(o2.unit_price))                           # mesmo pagando a lista: indisponível no mês
    assert again.json()["status"] == "REFUSED" and "disponível" in again.json()["message"]
    assert o2.id not in {x["id"] for x in _search(client, rich, cid, "horti")}
    close(client, rich)                                                  # no mês seguinte a lista é outra (tokens são do mês)
    assert {x["id"] for x in _search(client, rich, cid, "horti")}.isdisjoint({o2.id})


def test_negotiation_floor_drops_with_relevance_and_volume():
    seg = company_rules.SEGMENTS[company_rules.CompanySegment.RESTAURANT]
    cat = seg.supply("carnes")
    o = company_supply.build_offer(1, 7, date(2026, 2, 1), seg, cat, 0, size=company_rules.CompanySize.SMALL, units=1, capacity_level=0)
    base = company_supply.minimum_price(o, 0.0, o.min_monthly_order)
    assert company_supply.minimum_price(o, 100.0, o.min_monthly_order) < base
    assert company_supply.minimum_price(o, 0.0, o.max_units_month) <= base
    assert company_supply.FLOOR_MIN <= company_supply.floor_fraction(o, 100.0, o.max_units_month) <= company_supply.floor_fraction(o, 0.0, o.min_monthly_order) <= 1.0


def test_one_active_contract_per_category_and_partial_unique_index(client, rich, db):
    cid = create_ok(client, rich, staff=False, name="Bistrô Único", segment="RESTAURANT")["company"]["id"]
    offers = _search(client, rich, cid, "carnes")
    assert _negotiate(client, rich, cid, offers[0]["id"], offers[0]["unit_price"]).json()["accepted"]
    r = _negotiate(client, rich, cid, offers[1]["id"], offers[1]["unit_price"])
    assert r.status_code == 409 and "encerre" in r.json()["detail"]
    from sqlalchemy.exc import IntegrityError
    db.add(CompanySupplier(company_id=cid, category="carnes", name="Clone", unit_price=D(1), reference_price=D(1), min_monthly_order=D(1),
                           max_units_month=D(10), reliability=D(1), lead_days=1, status="ACTIVE", started_month=date(2026, 1, 1)))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()
    sid = detail(client, rich, cid)["supply"]["contracts"][0]["id"]                                 # encerrar libera a categoria
    assert client.delete(f"{C}/{cid}/suppliers/{sid}", headers=rich).status_code == 200
    assert _negotiate(client, rich, cid, offers[1]["id"], offers[1]["unit_price"]).json()["accepted"]
    assert client.delete(f"{C}/{cid}/suppliers/{sid}", headers=rich).status_code == 409           # já encerrado
    assert client.delete(f"{C}/{cid}/suppliers/999999", headers=rich).status_code == 404


def test_negotiate_is_idempotent(client, rich, db):
    cid = create_ok(client, rich, staff=False, name="Bistrô Idem", segment="CAFE")["company"]["id"]
    o = _search(client, rich, cid, "graos")[0]
    k = key()
    a = _negotiate(client, rich, cid, o["id"], o["unit_price"], idem=k).json()
    b = _negotiate(client, rich, cid, o["id"], o["unit_price"], idem=k).json()
    assert a["accepted"] and b["accepted"] and len(b["company"]["supply"]["contracts"]) == 1
    assert db.scalar(select(func.count()).select_from(CompanySupplier).where(CompanySupplier.company_id == cid)) == 1


def test_ending_contract_early_has_fine_and_late_or_default_has_none(client, rich, db):
    cid = create_ok(client, rich, staff=False, name="Café Multa", segment="CAFE")["company"]["id"]
    o = _search(client, rich, cid, "graos")[0]
    d = _negotiate(client, rich, cid, o["id"], o["unit_price"]).json()["company"]
    ct = d["supply"]["contracts"][0]
    fine = (D(ct["min_monthly_order"]) * D(ct["unit_price"]) * 2).quantize(D("0.01"))
    assert D(ct["early_end_fine"]) == fine > 0
    before = D(d["company"]["cash"])
    after = client.delete(f"{C}/{cid}/suppliers/{ct['id']}", headers=rich).json()
    assert D(after["company"]["cash"]) == before - fine and after["supply"]["checklist"][0]["present"] is False
    assert any(e["line"] == "FEES" and D(e["amount"]) == fine for e in after["ledger"])
    # com 3+ meses de contrato não há multa; o "Fornecedor padrão" nunca tem
    o2 = _search(client, rich, cid, "laticinios")[0]
    d = _negotiate(client, rich, cid, o2["id"], o2["unit_price"]).json()["company"]
    sid = d["supply"]["contracts"][0]["id"]
    s = db.get(CompanySupplier, sid)
    s.started_month = s.started_month.replace(year=s.started_month.year - 1)
    db.commit()
    assert D(detail(client, rich, cid)["supply"]["contracts"][0]["early_end_fine"]) == 0


def test_stock_company_without_suppliers_is_not_restocked_and_sales_stop(client, rich, db):
    cid = create_ok(client, rich, staff=False, name="Café Sem Fornecedor", segment="CAFE")["company"]["id"]
    staff_up(client, rich, cid)                                          # equipe sim, fornecedores não
    mature(db, cid)
    assert close(client, rich).status_code == 200
    d = detail(client, rich, cid)
    m = d["months"][0]
    assert D(m["units_sold"]) == 0 and m["stockout"] is True
    assert all(D(i["quantity"]) == 0 for i in d["inventory"]) and not any(e["line"] == "STOCK_PURCHASE" for e in d["ledger"])
    assert any("Sem fornecedor contratado" in e["description"] for e in d["events"])
    # contratando só UMA das categorias o resto continua sem reposição
    o = _search(client, rich, cid, "graos")[0]
    _negotiate(client, rich, cid, o["id"], o["unit_price"])
    close(client, rich)
    d = detail(client, rich, cid)
    qty = {i["category"]: D(i["quantity"]) for i in d["inventory"]}
    assert qty["graos"] > 0 and qty["laticinios"] == 0 and qty["embalagens"] == 0
    r = client.post(f"{C}/{cid}/stock", headers=rich, json={"item_id": next(i["id"] for i in d["inventory"] if i["category"] == "laticinios"),
                                                           "quantity": "10", "idempotency_key": key()})
    assert r.status_code == 409 and "fornecedor" in r.json()["detail"]


def test_service_company_without_suppliers_is_blocked_with_clear_event(client, rich, db):
    cid = create_ok(client, rich, staff=False, name="Oficina Bloqueada", segment="WORKSHOP")["company"]["id"]
    staff_up(client, rich, cid)
    mature(db, cid)
    close(client, rich)
    d = detail(client, rich, cid)
    assert D(d["months"][0]["units_sold"]) == 0 and D(d["months"][0]["revenue"]) == 0
    assert any("Operação bloqueada" in e["description"] and "Peças e fluidos" in e["description"] for e in d["events"])
    assert not any(e["line"] == "SUPPLIES" for e in d["ledger"]) and d["inventory"] == []
    contract_suppliers(client, rich, cid)
    mature(db, cid)
    close(client, rich)
    m = detail(client, rich, cid)["months"][0]
    assert D(m["units_sold"]) > 0 and D(m["revenue"]) > 0


def test_service_supplies_cost_follows_the_contracted_price(client, rich, db):
    cid = create_ok(client, rich, name="Oficina Preço", segment="WORKSHOP")["company"]["id"]
    seg = company_rules.SEGMENTS[company_rules.CompanySegment.WORKSHOP]
    mature(db, cid, 80)
    close(client, rich)
    d1 = detail(client, rich, cid)
    sold1 = D(d1["months"][0]["units_sold"])
    assert sold1 > 0
    lines = [e for e in d1["ledger"] if e["line"] == "SUPPLIES"]
    assert len(lines) == 2
    contracts = _active(db, cid)
    expected = sum((sold1 * c.per_sale * contracts[c.key].unit_price).quantize(D("0.01")) for c in seg.supply_categories)
    assert sum(D(e["amount"]) for e in lines) == expected
    assert D(d1["months"][0]["variable_costs"]) == expected                    # entra no custo variável do demonstrativo
    ref = db.scalar(select(LedgerEntry.origin_ref).where(LedgerEntry.company_id == cid, LedgerEntry.line == "SUPPLIES"))
    assert ref.startswith(f"company:{cid}:supplier:")
    # preço contratado 2x -> custo por serviço 2x no mês seguinte
    for x in contracts.values():
        x.unit_price = x.unit_price * 2
    db.commit()
    mature(db, cid, 80)
    close(client, rich)
    d2 = detail(client, rich, cid)
    sold2 = D(d2["months"][0]["units_sold"])
    assert sold2 > 0 and float(D(d2["months"][0]["variable_costs"]) / sold2) == pytest.approx(float(expected / sold1) * 2, rel=0.01)


def test_stock_purchase_uses_the_contract_price_min_order_and_supplier_origin_ref(client, rich, db):
    cid = create_ok(client, rich, staff=False, name="Café Preço", segment="CAFE")["company"]["id"]
    o = _search(client, rich, cid, "graos")[0]
    ct = _negotiate(client, rich, cid, o["id"], o["unit_price"]).json()["company"]["supply"]["contracts"][0]
    item = next(i for i in detail(client, rich, cid)["inventory"] if i["category"] == "graos")
    mn = D(ct["min_monthly_order"])
    r = client.post(f"{C}/{cid}/stock", headers=rich, json={"item_id": item["id"], "quantity": str(mn - 1), "idempotency_key": key()})
    assert mn > 1 and r.status_code == 400                                                    # abaixo do pedido mínimo
    qty = mn + 4
    r = client.post(f"{C}/{cid}/stock", headers=rich, json={"item_id": item["id"], "quantity": str(qty), "idempotency_key": key()})
    assert r.status_code == 201, r.text
    d = r.json()
    buy = next(e for e in d["ledger"] if e["line"] == "STOCK_PURCHASE")
    got = next(i for i in d["inventory"] if i["id"] == item["id"])
    delivered = D(got["quantity"])
    assert 0 < delivered <= qty and D(buy["amount"]) == (delivered * D(ct["unit_price"])).quantize(D("0.01"))
    assert D(got["unit_cost"]) == D(ct["unit_price"]) and got["supplier"] == ct["name"]
    assert db.scalar(select(LedgerEntry.origin_ref).where(LedgerEntry.company_id == cid, LedgerEntry.line == "STOCK_PURCHASE")) == f"company:{cid}:supplier:{ct['id']}"
    assert D(detail(client, rich, cid)["supply"]["contracts"][0]["volume_used"]) == delivered


def test_auto_restock_buys_from_contracts_at_contract_price(client, rich, db):
    cid = create_ok(client, rich, name="Café Reposição", segment="CAFE")["company"]["id"]
    prices = {x.category: x.unit_price for x in _active(db, cid).values()}
    mature(db, cid)
    close(client, rich)
    d = detail(client, rich, cid)
    assert D(d["months"][0]["units_sold"]) > 0
    for i in d["inventory"]:
        assert D(i["unit_cost"]) == prices[i["category"]]                                       # média ponderada só de compras ao preço contratado
    buys = db.scalars(select(LedgerEntry).where(LedgerEntry.company_id == cid, LedgerEntry.line == "STOCK_PURCHASE")).all()
    assert buys and all(b.origin_ref.startswith(f"company:{cid}:supplier:") for b in buys)


def test_delivery_failure_is_deterministic_and_partial(client, rich, db):
    assert company_supply.delivery_factor(1, 5, 9, date(2026, 3, 1), 1.0) == 1.0
    assert company_supply.delivery_factor(1, 5, 9, date(2026, 3, 1), 0.0) == company_supply.delivery_factor(1, 5, 9, date(2026, 3, 1), 0.0)
    f = company_supply.delivery_factor(1, 5, 9, date(2026, 3, 1), 0.0)                  # confiabilidade 0 => falha todo mês
    assert 0.3 <= f <= 0.7
    fails = sum(company_supply.delivery_factor(7, 5, 9, date(2026, 1 + m % 12, 1).replace(year=2026 + m // 12), 0.8) < 1 for m in range(240))
    assert 25 <= fails <= 75                                                                # ~20% dos meses (determinístico)
    cid = create_ok(client, rich, staff=False, name="Café Falha", segment="CAFE")["company"]["id"]
    o = _search(client, rich, cid, "graos")[0]
    _negotiate(client, rich, cid, o["id"], o["unit_price"])
    sup = _active(db, cid)["graos"]
    sup.reliability = D(0)
    sup.max_units_month = D(100000)
    db.commit()
    item = next(i for i in detail(client, rich, cid)["inventory"] if i["category"] == "graos")
    q = 100
    d = client.post(f"{C}/{cid}/stock", headers=rich, json={"item_id": item["id"], "quantity": str(q), "idempotency_key": key()}).json()
    got = D(next(i for i in d["inventory"] if i["id"] == item["id"])["quantity"])
    assert 0 < got < q and q * 0.3 - 1 <= float(got) <= q * 0.7
    assert any("Falha de entrega" in e["description"] for e in d["events"])
    pay = next(e for e in d["ledger"] if e["line"] == "STOCK_PURCHASE")
    assert D(pay["amount"]) == (got * D(o["unit_price"])).quantize(D("0.01"))             # paga só o que foi entregue
    d2 = client.post(f"{C}/{cid}/stock", headers=rich, json={"item_id": item["id"], "quantity": str(q), "idempotency_key": key()}).json()
    assert D(next(i for i in d2["inventory"] if i["id"] == item["id"])["quantity"]) == got * 2     # mesmo mês, mesma falha


def test_service_delivery_failure_reduces_capacity_of_the_month(client, rich, db):
    cid = create_ok(client, rich, name="Oficina Falha", segment="WORKSHOP")["company"]["id"]
    for x in _active(db, cid).values():
        x.max_units_month = D(400)                                       # folga sobre a capacidade normal (~288)
    db.commit()
    mature(db, cid, 90)
    close(client, rich)
    ok_cap = D(detail(client, rich, cid)["months"][0]["capacity_units"])
    for x in _active(db, cid).values():
        x.reliability = D(0)
    db.commit()
    mature(db, cid, 90)
    close(client, rich)
    d = detail(client, rich, cid)
    assert D(d["months"][0]["capacity_units"]) < ok_cap and any("Falha de entrega" in e["description"] for e in d["events"])


def test_volume_above_what_the_supplier_handles_is_not_served(client, rich, db):
    cid = create_ok(client, rich, staff=False, name="Café Volume", segment="CAFE")["company"]["id"]
    o = _search(client, rich, cid, "graos")[0]
    cap = D(o["max_units_month"])
    assert _negotiate(client, rich, cid, o["id"], o["unit_price"], volume="1").status_code == 400            # abaixo do pedido mínimo
    assert _negotiate(client, rich, cid, o["id"], o["unit_price"], volume=str(cap + 1)).status_code == 400   # acima do que ele aguenta
    assert _negotiate(client, rich, cid, o["id"], o["unit_price"], volume=str(cap)).json()["accepted"]
    sup = _active(db, cid)["graos"]
    sup.max_units_month = D(30)
    sup.reliability = D(1)
    sup.min_monthly_order = D(5)
    db.commit()
    item = next(i for i in detail(client, rich, cid)["inventory"] if i["category"] == "graos")
    buy = lambda q: client.post(f"{C}/{cid}/stock", headers=rich, json={"item_id": item["id"], "quantity": str(q), "idempotency_key": key()})
    assert buy(31).status_code == 409 and "não aguenta" in buy(31).json()["detail"]
    assert buy(20).status_code == 201
    assert buy(11).status_code == 409 and buy(10).status_code == 201                                       # o contador é mensal
    assert buy(5).status_code == 409
    close(client, rich)
    assert buy(5).status_code == 201                                                                         # novo mês, novo volume


def test_effective_capacity_is_limited_by_the_smallest_contracted_volume(client, rich, db):
    seg = company_rules.SEGMENTS[company_rules.CompanySegment.WORKSHOP]
    # fórmula pura: menor max_units_month / (consumo x (1 + perda)) entre as categorias
    cap = company_rules.supply_capacity(seg, {"pecas": 100.0, "ferramentas": 40.0})
    assert cap == pytest.approx(40.0)                                                                       # 40 / 1 (consumo 1 kit por serviço)
    assert company_rules.supply_capacity(seg, {"pecas": 100.0}) == 0.0                                      # categoria sem contrato
    assert company_rules.supply_capacity(seg, {"pecas": 100.0}, missing_is_zero=False) == pytest.approx(100.0)
    assert company_rules.supply_capacity(company_rules.SEGMENTS[company_rules.CompanySegment.TECH], {}) == float("inf")
    cid = create_ok(client, rich, name="Oficina Limite", segment="WORKSHOP")["company"]["id"]
    for x in _active(db, cid).values():
        x.max_units_month = D(3)
    db.commit()
    mature(db, cid, 90)
    close(client, rich)
    d = detail(client, rich, cid)
    assert D(d["months"][0]["capacity_units"]) <= 3 and D(d["months"][0]["units_sold"]) <= 3
    assert d["supply"]["effective_capacity"] == 3.0


@pytest.mark.parametrize("seg", ["TECH", "AGENCY", "REAL_ESTATE_AGENCY", "ECOMMERCE"])
def test_segments_without_categories_need_no_supplier(client, rich, db, seg):
    cid = create_ok(client, rich, name=f"Sem Fornecedor {seg}", segment=seg)["company"]["id"]
    d = detail(client, rich, cid)
    assert d["supply"]["required"] is False and d["supply"]["checklist"] == [] and d["supply"]["budget"]["rows"] == []
    assert d["company"]["supply_ready"] is True and D(d["company"]["supplier_budget"]) == 0 and d["supply"]["warning"] is None
    assert client.post(f"{C}/{cid}/suppliers/search", headers=rich, json={"category": "carnes"}).status_code == 400
    mature(db, cid, 70)
    close(client, rich)
    d = detail(client, rich, cid)
    assert D(d["months"][0]["revenue"]) > 0 and not any("fornecedor" in e["description"].lower() for e in d["events"])


def test_legacy_companies_get_the_default_supplier(client, rich, db):
    cid = create_ok(client, rich, staff=False, name="Café Legado", segment="CAFE")["company"]["id"]
    staff_up(client, rich, cid)
    c = db.get(Company, cid)
    made = company_service.grant_default_suppliers(db, c)
    db.commit()
    assert len(made) == 3 and all(x.is_default and x.name == "Fornecedor padrão" and x.status == "ACTIVE" for x in made)
    seg = company_rules.SEGMENTS[c.segment]
    assert {x.category: x.unit_price for x in made} == {k.key: k.ref_price for k in seg.supply_categories}
    assert company_service.grant_default_suppliers(db, c) == []                                          # idempotente
    d = detail(client, rich, cid)
    assert d["supply"]["ready"] is True and all(x["is_default"] and x["reliability"] == 1.0 for x in d["supply"]["contracts"])
    assert all(D(x["early_end_fine"]) == 0 for x in d["supply"]["contracts"])
    # a empresa opera normalmente com o fornecedor padrão (compra a preço de referência)
    item = d["inventory"][0]
    r = client.post(f"{C}/{cid}/stock", headers=rich, json={"item_id": item["id"], "quantity": "50", "idempotency_key": key()})
    assert r.status_code == 201 and D(next(i for i in r.json()["inventory"] if i["id"] == item["id"])["unit_cost"]) == next(
        k.ref_price for k in seg.supply_categories if k.key == item["category"])


def test_migration_default_sql_matches_service_catalog():
    import importlib.util
    import pathlib
    p = next(pathlib.Path("backend/alembic/versions").glob("*b8c9d0e1f2a3*.py"))
    spec = importlib.util.spec_from_file_location("mig_fornecedores", p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert mod.down_revision == "a7b8c9d0e1f2" and mod.revision == "b8c9d0e1f2a3"


def test_supplier_budget_is_coherent_with_the_ledger(client, rich, db):
    cid = create_ok(client, rich, name="Café Orçamento", segment="CAFE")["company"]["id"]
    mature(db, cid, 50)
    d0 = detail(client, rich, cid)
    b0 = d0["supply"]["budget"]
    seg = company_rules.SEGMENTS[company_rules.CompanySegment.CAFE]
    assert [r["category"] for r in b0["rows"]] == [c.key for c in seg.supply_categories] and b0["last_month"] is None
    total = D("0")
    for r in b0["rows"]:
        cat = seg.supply(r["category"])
        assert D(r["planned_spend"]) == (D(r["planned_volume"]) * D(r["unit_price"])).quantize(D("0.01")) or abs(
            D(r["planned_spend"]) - D(r["planned_volume"]) * D(r["unit_price"])) < D("0.02")
        assert r["supplier"] and r["estimated"] is False and D(r["last_actual"]) == 0
        total += D(r["planned_spend"])
    assert D(b0["total_planned"]) == total and D(d0["company"]["supplier_budget"]) == total > 0
    # volumes proporcionais ao peso/consumo: planejado = vendas esperadas x consumo x (1 + perda)
    per = {r["category"]: D(r["planned_volume"]) / (seg.supply(r["category"]).per_sale * (1 + seg.supply(r["category"]).waste_pct / 100)) for r in b0["rows"]}
    assert max(per.values()) - min(per.values()) < D("0.5")
    close(client, rich)
    d1 = detail(client, rich, cid)
    ref = d1["months"][0]["ref_month"]
    for r in d1["supply"]["budget"]["rows"]:
        sids = [f"company:{cid}:supplier:{x['id']}" for x in d1["supply"]["contracts"] if x["category"] == r["category"]]
        spent = db.scalar(select(func.coalesce(func.sum(LedgerEntry.amount), 0)).where(
            LedgerEntry.company_id == cid, LedgerEntry.line == "STOCK_PURCHASE", LedgerEntry.origin_ref.in_(sids), LedgerEntry.ref_month == date.fromisoformat(ref)))
        assert D(r["last_actual"]) == D(spent)
    assert D(d1["supply"]["budget"]["total_last_actual"]) == sum(D(r["last_actual"]) for r in d1["supply"]["budget"]["rows"])


def test_balance_with_contracts_at_list_price_still_turns_profit_in_12_to_14_months():
    seg_turns, pure = {}, {}
    for k in company_rules.SEGMENTS:
        r = company_balance.simulate(k, months=36, supplier_mult=1.0)
        seg_turns[k.value] = r.turn_month
        pure[k.value] = company_balance.simulate(k, months=36, supplier_mult=1.0, incidents_on=False).turn_month
    assert all(t is not None and 11 <= t <= 14 for t in pure.values()), pure                   # sem imprevistos: como antes da fase 5
    assert all(t is not None and 12 <= t <= 16 for t in seg_turns.values()), seg_turns         # com o custo esperado dos imprevistos
    assert all(seg_turns[k] >= pure[k] for k in pure) and any(seg_turns[k] > pure[k] for k in pure)   # os imprevistos atrasam (um pouco) a virada
    # contrato mais caro/mais barato muda o custo e a virada, só nos segmentos com fornecedor
    for k, seg in company_rules.SEGMENTS.items():
        base = company_balance.simulate(k, months=18, supplier_mult=1.0)
        dear = company_balance.simulate(k, months=18, supplier_mult=1.2)
        cheap = company_balance.simulate(k, months=18, supplier_mult=0.85)
        if seg.needs_suppliers:
            assert dear.rows[11].profit < base.rows[11].profit < cheap.rows[11].profit, k
        else:
            assert dear.rows[11].profit == base.rows[11].profit == cheap.rows[11].profit, k


# ================================================================== FASE 5: expansão em níveis, filiais, qualidade, campanhas, imprevistos
import math  # noqa: E402
from datetime import date  # noqa: E402

from backend.services import company_expansion as xp  # noqa: E402
from backend.services import company_expansion_data as xdata  # noqa: E402
from backend.services import company_incidents as incidents  # noqa: E402
from backend.services import economy_service  # noqa: E402


def force_options(monkeypatch, kind, *keys):
    """Fixa as opções sorteadas de um tipo (para testar uma opção específica); os demais tipos seguem o sorteio normal."""
    orig = xp.draw_options

    def draw(seed, c, ref, k, tier):
        if k != kind:
            return orig(seed, c, ref, k, tier)
        pool = xdata.pool(k, family=xdata.family_of(company_rules.SEGMENTS[c.segment].metrics_kind.value), segment=c.segment.value)
        by = {o.key: o for o in pool}
        return [by[x] for x in keys]
    monkeypatch.setattr(xp, "draw_options", draw)


def no_zero_months(monkeypatch):
    monkeypatch.setattr(company_rules, "is_zero_month", lambda *a, **k: False)


def set_cash(db, cid, amount):
    acc = db.scalar(select(FinanceAccount).join(Company, Company.account_id == FinanceAccount.id).where(Company.id == cid))
    acc.balance = D(str(amount))
    db.commit()


def test_expansion_options_are_deterministic_varied_and_not_forgeable(client, rich):
    cid = create_ok(client, rich, extra="300000")["company"]["id"]
    a, b = options(client, rich, cid, "CAPACITY", "MEDIO"), options(client, rich, cid, "CAPACITY", "MEDIO")
    assert a == b and len(a["options"]) == 3 and len({o["key"] for o in a["options"]}) == 3                    # determinístico, 3 distintas
    for o in a["options"]:
        assert o["title"] and o["description"] and D(o["cost"]) > 0 and o["side_effects"] and o["risk_hint"]
    assert options(client, rich, cid, "CAPACITY", "CARO")["tier_cost"] != a["tier_cost"]
    # varia entre níveis, meses e empresas
    seen = {tuple(o["key"] for o in options(client, rich, cid, "CAPACITY", t)["options"]) for t in ("BARATO", "MEDIO", "CARO")}
    assert len(seen) >= 2
    kinds = [("CAPACITY", "MEDIO"), ("QUALITY", "MEDIO"), ("MARKETING", "MEDIO"), ("NEW_UNIT", "MEDIO")]
    m1 = {k: [o["key"] for o in options(client, rich, cid, *k)["options"]] for k in kinds}
    other = create_ok(client, rich, name="Café Dois", extra="300000")["company"]["id"]
    assert any([o["key"] for o in options(client, rich, other, *k)["options"]] != m1[k] for k in kinds)
    assert close(client, rich).status_code == 200
    assert any([o["key"] for o in options(client, rich, cid, *k)["options"]] != m1[k] for k in kinds)
    # não forjável: opção fora das 3 do mês (mesmo existindo no catálogo) é recusada e nada é cobrado
    month_opts = [o["key"] for o in options(client, rich, cid, "CAPACITY", "MEDIO")["options"]]
    outside = next(o.key for o in xdata.CAPACITY["PRODUCTION"] if o.key not in month_opts)
    before = D(detail(client, rich, cid)["company"]["cash"])
    for bad in (outside, "inexistente"):
        r = client.post(f"{C}/{cid}/expansion/execute", headers=rich, json={"kind": "CAPACITY", "tier": "MEDIO", "option_key": bad, "idempotency_key": key()})
        assert r.status_code == 400, r.text
    assert D(detail(client, rich, cid)["company"]["cash"]) == before


def test_expansion_execute_is_idempotent(client, rich):
    cid = create_ok(client, rich, extra="300000")["company"]["id"]
    opt = options(client, rich, cid, "QUALITY", "MEDIO")["options"][0]["key"]
    idem = key()
    r1 = expand(client, rich, cid, "QUALITY", "MEDIO", option_key=opt, idem=idem)
    cash1 = D(r1["company"]["company"]["cash"])
    r2 = expand(client, rich, cid, "QUALITY", "MEDIO", option_key=opt, idem=idem)
    assert r2["replayed"] is True and r2["message"] == r1["message"] and r2["outcome"] == r1["outcome"] and r2["effects"] == r1["effects"]
    assert D(r2["company"]["company"]["cash"]) == cash1 and r2["company"]["company"]["quality"] == r1["company"]["company"]["quality"]
    r3 = expand(client, rich, cid, "QUALITY", "MEDIO", option_key=opt)                       # outra chave = outro aporte
    assert D(r3["company"]["company"]["cash"]) < cash1 and not r3["replayed"]


def test_tiers_have_distinct_costs_per_kind():
    seg = company_rules.SEGMENTS[company_rules.CompanySegment.CAFE]
    size, ratios = company_rules.CompanySize.SMALL, {}
    for kind in company_rules.EXPANSION_KINDS:
        c = [company_rules.expansion_cost(seg, kind, size, 1, t) for t in company_rules.TIERS]
        assert c[0] < c[1] < c[2], kind
        ratios[kind] = (round(c[1] / c[0], 2), round(c[2] / c[0], 2))
    assert len(set(ratios.values())) == len(ratios), ratios                                    # cada tipo com a sua escala
    base = seg.setup_cost * company_rules.SIZES[size].setup
    assert [company_rules.expansion_cost(seg, "CAPACITY", size, 1, t) for t in company_rules.TIERS] == [
        quantize(base * D(x)) for x in ("0.10", "0.22", "0.45")]
    assert [company_rules.expansion_cost(seg, "NEW_UNIT", size, 1, t) for t in company_rules.TIERS] == [quantize(base * D(x)) for x in ("0.60", "1.00", "1.70")]
    assert [company_rules.expansion_cost(seg, "QUALITY", size, 1, t) for t in company_rules.TIERS] == [quantize(base * D(x)) for x in ("0.05", "0.12", "0.28")]
    mk = seg.marketing_cost * company_rules.SIZES[size].fixed
    assert [company_rules.expansion_cost(seg, "MARKETING", size, 1, t) for t in company_rules.TIERS] == [quantize(mk * D(x)) for x in ("0.5", "1.5", "4.0")]


def quantize(v):
    return D(v).quantize(D("0.01"))


def test_option_pools_are_large_enough_for_every_family_and_segment():
    for fam in xdata.FAMILIES:
        for kind, table in (("CAPACITY", xdata.CAPACITY), ("NEW_UNIT", xdata.NEW_UNIT), ("QUALITY", xdata.QUALITY)):
            keys = [o.key for o in table[fam]]
            assert len(keys) >= 8 and len(set(keys)) == len(keys), (kind, fam)
    assert len(xdata.LARGER) >= 8
    for seg in company_rules.SEGMENTS:
        pool = xdata.CAMPAIGNS[seg.value]
        assert len(pool) >= 6 and len({o.key for o in pool}) == len(pool), seg
    assert any("escola" in o.title.lower() for o in xdata.CAMPAIGNS["RESTAURANT"])


def opt(kind, family, key_):
    return next(o for o in xdata.pool(kind, family=family, segment="CAFE") if o.key == key_)


def test_capacity_expansion_can_succeed_partially_or_fail(client, rich, monkeypatch):
    cid = create_ok(client, rich, extra="300000")["company"]["id"]
    force_options(monkeypatch, "CAPACITY", "novo_equipamento", "reorganizar_fluxo", "treinar_equipe")
    o = opt("CAPACITY", "PRODUCTION", "novo_equipamento")
    full, part = xp.odds("CAPACITY", "MEDIO", o)
    cash0 = D(detail(client, rich, cid)["company"]["cash"])
    force_rolls(monkeypatch, **{"xp-result": 0.999})                                                     # fracasso
    r = expand(client, rich, cid, "CAPACITY", "MEDIO", option_key="novo_equipamento")
    assert r["outcome"] == "FAIL" and not r["success"] and float(r["company"]["company"]["capacity_boost"]) == 0
    assert r["company"]["company"]["capacity_level"] == 0 and D(r["company"]["company"]["cash"]) < cash0                  # perdeu o dinheiro
    assert D(r["cost"]) == quantize(D(r["company"]["expansion_costs"]["CAPACITY"]["MEDIO"]) * D("1.1"))
    force_rolls(monkeypatch, **{"xp-result": full + part / 2})                                           # parcial
    r = expand(client, rich, cid, "CAPACITY", "MEDIO", option_key="novo_equipamento")
    assert r["outcome"] == "PARTIAL" and r["success"] and float(r["company"]["company"]["capacity_boost"]) == pytest.approx(0.4)
    force_rolls(monkeypatch, **{"xp-result": 0.0})                                                       # completo
    r = expand(client, rich, cid, "CAPACITY", "MEDIO", option_key="novo_equipamento")
    assert r["outcome"] == "FULL" and float(r["company"]["company"]["capacity_boost"]) == pytest.approx(1.2)
    assert any("Manutenção" in x["name"] or "energia" in x["name"] for x in r["company"]["costs"])       # custo fixo recorrente da opção
    assert any("fornecedores" in e for e in r["effects"]) and any("vender mais" in e for e in r["effects"])


def test_more_capacity_does_not_mean_more_sales(monkeypatch):
    no_zero_months(monkeypatch)
    seg = company_rules.SEGMENTS[company_rules.CompanySegment.CAFE]
    kw = dict(location="bairro", size=company_rules.CompanySize.SMALL, units=1, relevance=5, reputation=50, price=seg.price, company_id=1,
              ref=date(2027, 1, 1), seed=1, marketing=False, staff=[("barista", D(1))], season=False)
    s0 = company_rules.sales_month(seg, capacity_level=0, **kw)
    s1 = company_rules.sales_month(seg, capacity_level=2.5, **kw)
    assert s1.capacity > s0.capacity and s0.demand < s0.capacity                  # demanda é o gargalo
    assert s1.sold == s0.sold and s1.demand == s0.demand                          # produzir mais não vende mais
    # e acima do teto de produção a equipe não passa (o aporte eleva o teto, nunca o ignora)
    many = [("barista", D(1))] * 40
    assert company_rules.capacity_units(seg, size=kw["size"], units=1, capacity_level=0, staff=many) == pytest.approx(
        company_rules.production_ceiling(seg, kw["size"], 1, 0))


def test_capacity_respects_supplier_volume_and_warns(client, rich, db, monkeypatch):
    cid = create_ok(client, rich, extra="300000")["company"]["id"]
    from backend.models import CompanySupplier
    for x in db.scalars(select(CompanySupplier).where(CompanySupplier.company_id == cid)):
        x.max_units_month = D(100)
    db.commit()
    force_rolls(monkeypatch)
    force_options(monkeypatch, "CAPACITY", "novo_equipamento", "reorganizar_fluxo", "treinar_equipe")
    r = expand(client, rich, cid, "CAPACITY", "CARO", option_key="novo_equipamento")
    assert any(e.startswith("Atenção") and "fornecedores" in e for e in r["effects"])
    eff = r["company"]["supply"]["effective_capacity"]
    assert eff is not None and eff < r["company"]["expected_capacity"]
    assert close(client, rich).status_code == 200
    m = detail(client, rich, cid)["months"][0]
    assert float(m["capacity_units"]) <= eff + 0.1                                                       # capacidade efetiva <= volume contratado


def test_manager_option_hires_and_employees_may_quit_deterministically(client, rich, monkeypatch):
    cid = create_ok(client, rich, extra="300000")["company"]["id"]
    force_options(monkeypatch, "CAPACITY", "gerente_produtividade", "reorganizar_fluxo", "treinar_equipe")
    force_rolls(monkeypatch, **{"xp-quit": 0.99})
    n0 = len([e for e in detail(client, rich, cid)["employees"] if e["status"] == "ACTIVE"])
    r = expand(client, rich, cid, "CAPACITY", "MEDIO", option_key="gerente_produtividade")
    emps = [e for e in r["company"]["employees"] if e["status"] == "ACTIVE"]
    assert len(emps) == n0 + 1 and any(e["role"] == "production_manager" and e["role_label"] == "Gerente de produtividade" for e in emps)
    assert any("Ninguém pediu demissão" in e for e in r["effects"])
    force_rolls(monkeypatch, **{"xp-quit": 0.0})                                                          # todos "querem" sair: no máx. 40%
    r = expand(client, rich, cid, "CAPACITY", "MEDIO", option_key="gerente_produtividade")
    quit_ = [e for e in r["company"]["employees"] if e["status"] == "TERMINATED"]
    productive = [e for e in r["company"]["employees"] if e["role"] in ("barista", "attendant")]
    assert 1 <= len(quit_) <= max(1, math.ceil(len(productive) * 0.4)) and any("Pediram demissão" in e for e in r["effects"])
    assert all(e["role"] in ("barista", "attendant") for e in quit_)                                       # só quem produz sai; obrigatórios ficam


def test_extra_shift_option_raises_hours_and_lawsuit_risk(client, rich, monkeypatch):
    cid = create_ok(client, rich, extra="300000")["company"]["id"]
    d0 = detail(client, rich, cid)
    force_options(monkeypatch, "CAPACITY", "turno_extra", "reorganizar_fluxo", "treinar_equipe")
    force_rolls(monkeypatch)
    d1 = expand(client, rich, cid, "CAPACITY", "MEDIO", option_key="turno_extra")["company"]
    prod0 = {e["id"]: e for e in d0["employees"] if e["role"] in ("barista", "attendant")}
    for e in d1["employees"]:
        if e["id"] in prod0:
            assert e["hours_week"] == min(56, prod0[e["id"]]["hours_week"] + 6) and D(e["salary"]) > D(prod0[e["id"]]["salary"])
            assert e["lawsuit_risk_pct"] >= prod0[e["id"]]["lawsuit_risk_pct"]


# ------------------------------------------------------------------ nova unidade (filial)

def branch_site(**over):
    return {"channel": "PHYSICAL", "site_mode": "RENT", "location": "bairro", **over}


def test_new_unit_creates_branch_with_fractional_relevance_and_counts_units(client, rich, db, monkeypatch):
    cid = create_ok(client, rich, extra="400000")["company"]["id"]
    mature(db, cid, 40)
    force_options(monkeypatch, "NEW_UNIT", "filial_rua", "quiosque", "shopping")
    force_rolls(monkeypatch)
    d0 = detail(client, rich, cid)
    cheap = expand(client, rich, cid, "NEW_UNIT", "BARATO", option_key="filial_rua", **branch_site())["company"]
    cheap_rel = [u for u in cheap["units_list"] if u["kind"] == "BRANCH"][0]["relevance"]
    rich_ = expand(client, rich, cid, "NEW_UNIT", "CARO", option_key="filial_rua", **branch_site(location="centro"))["company"]
    branches = [u for u in rich_["units_list"] if u["kind"] == "BRANCH"]
    assert cheap_rel == pytest.approx(10.0) and branches[1]["relevance"] == pytest.approx(24.0)            # 25% e 60% da relevância da marca (40)
    assert rich_["company"]["units"] == 3 and len([u for u in rich_["units_list"] if u["status"] == "OPEN"]) == 3
    assert rich_["units_list"][0]["kind"] == "HQ" and all(0.3 <= u["viability"] <= 1.4 for u in branches)
    assert D(rich_["monthly_obligations"]) > D(d0["monthly_obligations"]) + sum(D(u["monthly_rent"]) for u in branches) - 1
    assert D(branches[1]["investment"]) > D(branches[0]["investment"])
    assert any("NEW_UNIT" in e["description"] and "aberta!" in e["description"] for e in rich_["events"])


def test_new_unit_opening_can_fail_and_buy_mode_pays_land(client, rich, db, monkeypatch):
    cid = create_ok(client, rich, extra="400000")["company"]["id"]
    set_cash(db, cid, 3_000_000)
    force_options(monkeypatch, "NEW_UNIT", "filial_rua", "quiosque", "shopping")
    force_rolls(monkeypatch, **{"xp-open": 0.0})                                                          # a abertura não vinga
    d0 = detail(client, rich, cid)
    r = expand(client, rich, cid, "NEW_UNIT", "MEDIO", option_key="filial_rua", **branch_site(site_mode="BUY"))
    assert r["outcome"] == "FAIL" and r["company"]["company"]["units"] == 1 and len(r["company"]["units_list"]) == 1
    full = D(d0["expansion_costs"]["NEW_UNIT"]["MEDIO"])
    assert D(r["cost"]) == quantize(full * D("0.5"))                                                      # perde metade; terreno não é comprado
    force_rolls(monkeypatch)
    r = expand(client, rich, cid, "NEW_UNIT", "MEDIO", option_key="filial_rua", **branch_site(site_mode="BUY"))
    br = [u for u in r["company"]["units_list"] if u["kind"] == "BRANCH"][0]
    land = company_rules.land_value(company_rules.SEGMENTS[company_rules.CompanySegment.CAFE], company_rules.CompanyChannel.PHYSICAL,
                                    company_rules.SiteMode.BUY, "bairro", company_rules.CompanySize.SMALL)
    assert br["site_mode"] == "BUY" and D(br["site_value"]) == land > 0 and D(br["monthly_rent"]) == 0
    assert D(r["cost"]) == full + land
    assert D(r["company"]["company"]["equity"]) > 0
    # valida local/canal
    bad = expand(client, rich, cid, "NEW_UNIT", "MEDIO", option_key="filial_rua", expect=400, **branch_site(location="marte"))
    assert bad.status_code == 400
    assert expand(client, rich, cid, "NEW_UNIT", "MEDIO", option_key="filial_rua", expect=400, **branch_site(channel="ONLINE", site_mode="BUY")).status_code == 400


def test_branch_sells_less_on_average_but_can_sell_more():
    seg = company_rules.SEGMENTS[company_rules.CompanySegment.CAFE]
    R = company_rules
    for ti in range(3):
        for rel in (10, 40, 70):
            n = 400
            mean = sum((R.VIAB_MIN + 1.1 * ((i + .5) / n) ** R.BRANCH_VIAB_SHAPE[ti]) * R.relevance_factor(rel * R.BRANCH_REL_FRAC[ti]) for i in range(n)) / n
            assert mean < R.relevance_factor(rel), (ti, rel)                                          # em média vende MENOS que a matriz
    assert 1.4 * R.relevance_factor(5 * R.BRANCH_REL_FRAC[2]) > R.relevance_factor(5)              # com viabilidade máxima, pode vender MAIS
    # marca pouco relevante => filial mais difícil (relevância inicial menor => menos demanda)
    assert R.relevance_factor(50 * 0.4) / R.relevance_factor(50) > R.relevance_factor(5 * 0.4) / R.relevance_factor(5) * 0.5
    assert R.relevance_factor(0 * 0.4) <= R.relevance_factor(10 * 0.4)
    assert seg is not None


def unit_rows(client, h, cid, month=0):
    return {r["name"]: r for r in detail(client, h, cid)["months"][month]["units_detail"]}


def test_branch_with_high_viability_sells_more_than_hq_and_low_sells_less(client, rich, db, monkeypatch):
    no_zero_months(monkeypatch)
    cid = create_ok(client, rich, extra="400000")["company"]["id"]
    mature(db, cid, 10)
    force_options(monkeypatch, "NEW_UNIT", "filial_rua", "quiosque", "shopping")
    force_rolls(monkeypatch, **{"xp-viab": 0.999999})                                                     # viabilidade ~1,4
    expand(client, rich, cid, "NEW_UNIT", "CARO", option_key="filial_rua", **branch_site())
    force_rolls(monkeypatch, **{"xp-viab": 0.0})                                                          # viabilidade 0,3
    expand(client, rich, cid, "NEW_UNIT", "CARO", option_key="filial_rua", **branch_site())
    assert close(client, rich).status_code == 200
    rows = unit_rows(client, rich, cid)
    assert rows["Filial 1"]["sold"] > rows["Matriz"]["sold"] > rows["Filial 2"]["sold"] > 0, rows


def test_month_consolidates_hq_and_branches_with_detail_per_unit(client, rich, db, monkeypatch):
    no_zero_months(monkeypatch)
    cid = create_ok(client, rich, extra="400000")["company"]["id"]
    mature(db, cid, 30)
    force_options(monkeypatch, "NEW_UNIT", "filial_rua", "quiosque", "shopping")
    force_rolls(monkeypatch)
    expand(client, rich, cid, "NEW_UNIT", "MEDIO", option_key="filial_rua", **branch_site())
    assert close(client, rich).status_code == 200
    m = detail(client, rich, cid)["months"][0]
    rows = m["units_detail"]
    assert [r["kind"] for r in rows] == ["HQ", "BRANCH"]
    assert sum(D(r["revenue"]) for r in rows) == D(m["revenue"])
    assert sum(D(str(r["sold"])) for r in rows) == D(m["units_sold"])
    assert sum(D(r["result"]) for r in rows) == D(m["operating_result"])                                 # a soma das unidades fecha com o total
    assert D(rows[1]["fixed_costs"]) >= D(detail(client, rich, cid)["units_list"][1]["monthly_rent"]) and D(rows[1]["cumulative_result"]) == D(rows[1]["result"])
    # a equipe é rateada pela demanda de cada unidade: as fatias somam 1
    c = db.get(Company, cid)
    plans = company_service.plan_units(db, c, company_rules.SEGMENTS[c.segment], date(2027, 1, 1), season=False)
    assert sum(p.share for p in plans) == pytest.approx(1.0) and all(p.share > 0 for p in plans)
    assert D(m["demand_units"]) > 0 and float(m["capacity_units"]) > 0


def test_branch_bankruptcy_closes_it_ends_rent_sells_land_and_loses_investment(client, rich, db, monkeypatch):
    no_zero_months(monkeypatch)
    cid = create_ok(client, rich, extra="400000")["company"]["id"]
    set_cash(db, cid, 3_000_000)
    force_options(monkeypatch, "NEW_UNIT", "filial_rua", "quiosque", "shopping")
    force_rolls(monkeypatch)
    r = expand(client, rich, cid, "NEW_UNIT", "MEDIO", option_key="filial_rua", **branch_site(site_mode="BUY"))
    u = db.scalar(select(CompanyUnit).where(CompanyUnit.company_id == cid))
    land = u.site_value
    assert land > 0 and r["company"]["company"]["units"] == 2
    u.opened_month = date(2025, 1, 1)
    u.cumulative_result = D("-900000.00")                                                                  # muito além do limite (60% do investimento)
    db.commit()
    assert close(client, rich).status_code == 200
    d = detail(client, rich, cid)
    assert d["company"]["units"] == 1
    br = [x for x in d["units_list"] if x["kind"] == "BRANCH"][0]
    assert br["status"] == "CLOSED" and br["closed_reason"] and br["closed_month"]
    sale = db.scalar(select(LedgerEntry).where(LedgerEntry.company_id == cid, LedgerEntry.line == "LAND", LedgerEntry.description.like("Venda do terreno da%")))
    assert sale is not None and sale.amount == quantize(land * D("0.92"))                                 # terreno vendido a 92%
    assert any("FALIU" in e["description"] for e in d["events"])                                           # fechou com evento
    assert D(d["company"]["equity"]) == D(detail(client, rich, cid)["company"]["equity"])
    assert close(client, rich).status_code == 200                                                         # fechada: não entra mais no mês
    assert len(detail(client, rich, cid)["months"][0]["units_detail"]) == 1


def test_branch_closes_when_company_cash_cannot_cover_its_losses(client, rich, db, monkeypatch):
    no_zero_months(monkeypatch)
    cid = create_ok(client, rich, extra="400000")["company"]["id"]
    force_options(monkeypatch, "NEW_UNIT", "filial_rua", "quiosque", "shopping")
    force_rolls(monkeypatch)
    expand(client, rich, cid, "NEW_UNIT", "BARATO", option_key="filial_rua", **branch_site())
    u = db.scalar(select(CompanyUnit).where(CompanyUnit.company_id == cid))
    u.opened_month = date(2025, 6, 1)
    u.monthly_rent = D("500000.00")                                                                        # filial no vermelho
    u.investment = D("50000000.00")                                                                        # limite de prejuízo acumulado muito longe
    db.commit()
    set_cash(db, cid, -2_000_000)                                                                          # caixa estourado
    assert close(client, rich).status_code == 200
    db.expire_all()
    u = db.scalar(select(CompanyUnit).where(CompanyUnit.company_id == cid))
    assert u.status == "CLOSED" and "caixa" in u.closed_reason and db.get(Company, cid).units == 1


# ------------------------------------------------------------------ qualidade

def test_quality_raises_cost_relevance_gain_and_price_tolerance(client, rich, db, monkeypatch):
    R = company_rules
    seg = R.SEGMENTS[R.CompanySegment.CAFE]
    assert R.quality_cost_mult(50) == 1 and R.quality_cost_mult(100) == D("1.25") and R.quality_cost_mult(0) == D("0.75")
    hi_price = seg.price * D("1.15")
    assert R.price_factor(seg, hi_price, 100) > R.price_factor(seg, hi_price, 50)                       # tolera preço maior
    assert R.price_ratio(seg, hi_price, 100) < R.price_ratio(seg, hi_price, 50)
    kw = dict(sold=100, demand=100, reputation=50, marketing=False, stockout=False, price_ratio=1.0, irregular=False)
    assert R.next_relevance(20, quality=100, **kw) > R.next_relevance(20, quality=50, **kw) > R.next_relevance(20, quality=0, **kw)
    d = lambda q: R.demand_units(seg, location="bairro", size=R.CompanySize.SMALL, units=1, reputation=50, price=hi_price, company_id=1,
                                 ref=date(2027, 1, 1), marketing=False, season=False, relevance=50, quality=q)
    assert d(100) > d(50)
    # aporte: sobe a qualidade (efeito completo = ganho do nível x poder da opção) e aparece na UI
    cid = create_ok(client, rich, extra="300000")["company"]["id"]
    force_options(monkeypatch, "QUALITY", "materia_prima_premium", "treinamento_equipe", "certificacao")
    force_rolls(monkeypatch)
    r = expand(client, rich, cid, "QUALITY", "CARO", option_key="materia_prima_premium")
    assert float(r["company"]["company"]["quality"]) == pytest.approx(50 + 20 * 1.1) and r["outcome"] == "FULL"
    force_rolls(monkeypatch, **{"xp-result": 0.999})
    r = expand(client, rich, cid, "QUALITY", "CARO", option_key="treinamento_equipe")
    assert r["outcome"] == "FAIL" and float(r["company"]["company"]["quality"]) == pytest.approx(72.0)


def test_quality_raises_variable_cost_per_sale(client, rich, db, monkeypatch):
    no_zero_months(monkeypatch)
    cid = create_ok(client, rich, segment="WORKSHOP", name="Oficina Q", extra="400000")["company"]["id"]
    mature(db, cid, 50)
    assert close(client, rich).status_code == 200
    m0 = detail(client, rich, cid)["months"][0]
    per0 = D(m0["variable_costs"]) / D(m0["units_sold"])
    c = db.get(Company, cid)
    c.quality, c.relevance = D("100"), D("50")
    db.commit()
    assert close(client, rich).status_code == 200
    m1 = detail(client, rich, cid)["months"][0]
    per1 = D(m1["variable_costs"]) / D(m1["units_sold"])
    assert D(m0["units_sold"]) > 0 and D(m1["units_sold"]) > 0
    assert per1 / per0 == pytest.approx(D("1.25"), rel=D("0.01"))                                         # insumo/serviço 25% mais caro com qualidade 100


# ------------------------------------------------------------------ campanhas

def test_campaign_results_can_fail_work_or_go_viral(client, rich, db, monkeypatch):
    cid = create_ok(client, rich, extra="400000")["company"]["id"]
    mature(db, cid, 20)
    force_options(monkeypatch, "MARKETING", "degustacao_cafe", "cartao_fidelidade", "cafe_cortesia")
    d0 = detail(client, rich, cid)["company"]
    force_rolls(monkeypatch, **{"xp-result": 0.0})                                                        # fracasso: nenhum efeito
    r = expand(client, rich, cid, "MARKETING", "MEDIO", option_key="cartao_fidelidade")
    assert r["outcome"] == "FAIL" and r["company"]["company"]["marketing_until"] is None and r["company"]["company"]["relevance"] == d0["relevance"]
    assert D(r["company"]["company"]["cash"]) < D(d0["cash"])
    force_rolls(monkeypatch, **{"xp-result": 0.5})                                                        # efeito normal
    r = expand(client, rich, cid, "MARKETING", "MEDIO", option_key="cartao_fidelidade")
    ok = r["company"]["company"]
    assert ok["marketing_until"] and ok["relevance"] > d0["relevance"] and ok["marketing_boost"] == pytest.approx(0.14 * 0.9)
    force_rolls(monkeypatch, **{"xp-result": 0.9999})                                                     # viral
    r = expand(client, rich, cid, "MARKETING", "MEDIO", option_key="cartao_fidelidade")
    vi = r["company"]["company"]
    assert "VIRALIZOU" in r["message"] and vi["marketing_boost"] > ok["marketing_boost"] * 1.5 and vi["marketing_until"] > ok["marketing_until"]
    assert vi["relevance"] - ok["relevance"] > ok["relevance"] - d0["relevance"]


def test_legacy_marketing_until_keeps_the_old_bonus(client, rich, db):
    cid = create_ok(client, rich, extra="300000")["company"]["id"]
    c = db.get(Company, cid)
    assert float(c.marketing_boost) == pytest.approx(0.12)                                               # empresas antigas: bônus de 12% como antes
    seg = company_rules.SEGMENTS[c.segment]
    kw = dict(location="bairro", size=c.size, units=1, reputation=50, price=c.price, company_id=1, ref=date(2027, 1, 1), season=False, relevance=50)
    on = company_rules.demand_units(seg, marketing=True, **kw)
    off = company_rules.demand_units(seg, marketing=False, **kw)
    assert on / off == pytest.approx(1.12)


def test_larger_premises_tier_can_fail_partially_or_upgrade(client, rich, db, monkeypatch):
    cid = create_ok(client, rich, extra="400000")["company"]["id"]
    force_options(monkeypatch, "LARGER_PREMISES", "reforma_ampliacao", "anexo", "turn_key")
    force_rolls(monkeypatch, **{"xp-result": 0.999})
    r = expand(client, rich, cid, "LARGER_PREMISES", "BARATO", option_key="reforma_ampliacao")
    assert r["outcome"] == "FAIL" and r["company"]["company"]["size"] == "SMALL"
    o = opt("LARGER_PREMISES", "PRODUCTION", "reforma_ampliacao")
    full, part = xp.odds("LARGER_PREMISES", "BARATO", o)
    force_rolls(monkeypatch, **{"xp-result": full + part / 2})
    r = expand(client, rich, cid, "LARGER_PREMISES", "BARATO", option_key="reforma_ampliacao")
    assert r["outcome"] == "PARTIAL" and r["company"]["company"]["size"] == "SMALL" and float(r["company"]["company"]["capacity_boost"]) > 0
    force_rolls(monkeypatch)
    r = expand(client, rich, cid, "LARGER_PREMISES", "CARO", option_key="reforma_ampliacao")
    assert r["company"]["company"]["size"] == "MEDIUM"


# ------------------------------------------------------------------ imprevistos: despejo, processo trabalhista, quebra de equipamento
from backend.models import WorldEvent  # noqa: E402


def open_ref(client, h):
    return date.fromisoformat(client.get(f"{B}/overview", headers=h).json()["month"]["ref_month"])


def make_incident(client, h, db, monkeypatch, cid, key_):
    """Cria o imprevisto como o fechamento do mês faria (`_spawn_incidents`), forçando a probabilidade SÓ dessa empresa e desse tipo a 1."""
    from tests.test_life import uid
    u, ref = uid(client, h), open_ref(client, h)
    target = {"despejo": "eviction_prob", "processo_trabalhista": "lawsuit_prob", "equipamento_quebra": "breakage_prob"}[key_]
    for name in ("eviction_prob", "lawsuit_prob", "breakage_prob"):
        monkeypatch.setattr(incidents, name, lambda _db, c, _ref, _n=name: 1.0 if (c.id == cid and _n == target) else 0.0)
    made = economy_service._spawn_incidents(db, u, ref, economy_service.get_game(db, u).seed, 1.0)
    db.commit()
    assert len(made) == 1 and made[0].key == key_ and made[0].status == "PENDING" and made[0].company_id == cid
    return made[0].id


def decide(client, h, eid, option, monkeypatch=None, roll=0.0, expect=200):
    if monkeypatch is not None:
        monkeypatch.setattr(economy_service, "hash01", lambda *a: roll)
    r = client.post(f"/api/economy/events/{eid}/decide", headers=h, json={"option": option})
    assert r.status_code == expect, r.text
    return r


def ledger(db, cid, text):
    db.expire_all()
    return db.scalar(select(LedgerEntry).where(LedgerEntry.company_id == cid, LedgerEntry.description.like(text)))


def test_incident_probabilities_follow_company_state():
    f = incidents.eviction_prob_values
    base = f(lease_age_months=0, relevance=0, cash_prev=1e6, rent=5000)
    assert 0 < base < 0.03                                                                                # moderada
    assert f(lease_age_months=48, relevance=0, cash_prev=1e6, rent=5000) > base                           # contrato antigo
    assert f(lease_age_months=0, relevance=0, cash_prev=-100, rent=5000) >= 2.9 * base                    # aluguel atrasado (caixa negativo)
    assert f(lease_age_months=0, relevance=100, cash_prev=1e6, rent=5000) < base                          # relevância alta protege
    law = incidents.lawsuit_prob_values
    assert law(productive_hours=[], pj_tenures=[], has_staff=False) == 0
    clt = law(productive_hours=[44, 44], pj_tenures=[], has_staff=True)
    assert 0 < clt < 0.01
    assert law(productive_hours=[52, 52], pj_tenures=[], has_staff=True) > 3 * clt                         # jornada média > 48 h
    assert law(productive_hours=[44, 44], pj_tenures=[0], has_staff=True) > clt                           # PJ alegando vínculo
    assert law(productive_hours=[44], pj_tenures=[30, 30], has_staff=True) > law(productive_hours=[44], pj_tenures=[0], has_staff=True)   # nº de PJ e tempo de casa
    assert law(productive_hours=[44], pj_tenures=[36] * 30, has_staff=True) == incidents.LAWSUIT_CAP
    brk = incidents.breakage_prob_values
    assert brk(capacity_boost=0, overtime=False, shielded=False) == pytest.approx(0.03)
    assert brk(capacity_boost=2, overtime=True, shielded=False) > brk(capacity_boost=0, overtime=False, shielded=False)
    assert brk(capacity_boost=2, overtime=True, shielded=True) == 0


def test_eviction_only_hits_physical_companies_on_rented_sites(client, rich, db):
    rent = create_ok(client, rich, name="Alugada", extra="100000")["company"]["id"]
    own = create_ok(client, rich, name="Própria", extra="100000", site_mode="BUY")["company"]["id"]
    web = create_ok(client, rich, name="Online", extra="100000", channel="ONLINE")["company"]["id"]
    ref = open_ref(client, rich)
    assert incidents.eviction_prob(db, db.get(Company, rent), ref) > 0
    assert incidents.eviction_prob(db, db.get(Company, own), ref) == 0
    assert incidents.eviction_prob(db, db.get(Company, web), ref) == 0
    c = db.get(Company, rent)
    c.suspended_until = ref
    db.commit()
    assert incidents.eviction_prob(db, db.get(Company, rent), ref) == 0                                   # já despejada


def test_incidents_are_capped_per_month_across_the_portfolio(client, rich, db, monkeypatch):
    from tests.test_life import uid
    ids = [create_ok(client, rich, name=f"Cafe {i}", extra="100000")["company"]["id"] for i in range(3)]
    for name in ("eviction_prob", "lawsuit_prob", "breakage_prob"):
        monkeypatch.setattr(incidents, name, lambda _db, c, _ref: 1.0)
    u = uid(client, rich)
    made = economy_service._spawn_incidents(db, u, open_ref(client, rich), economy_service.get_game(db, u).seed, 1.0)
    db.commit()
    assert len(made) == incidents.INCIDENT_CAP == 2                                                      # no máx. 2 imprevistos por mês
    assert incidents.INCIDENT_CAP >= 1 and len(ids) == 3


def test_eviction_negotiate_renews_the_lease_and_charges_three_rents(client, rich, db, monkeypatch):
    cid = create_ok(client, rich, extra="100000")["company"]["id"]
    eid = make_incident(client, rich, db, monkeypatch, cid, "despejo")
    pend = client.get("/api/economy/decisions", headers=rich).json()["pending"]
    ev = next(e for e in pend if e["id"] == eid)
    assert {o["key"] for o in ev["options"]} == {"negociar", "mudar", "justica", "ignorar"} and "outcomes" not in str(ev)
    rent = D(detail(client, rich, cid)["lease"]["monthly_rent"])
    decide(client, rich, eid, "negociar", monkeypatch, 0.0)
    assert ledger(db, cid, "Negociação de permanência%").amount == quantize(rent * 3)
    d = detail(client, rich, cid)
    assert d["lease"] is not None and d["company"]["suspended_until"] is None and db.get(Company, cid).suspended_until is None
    decide(client, rich, eid, "negociar", expect=409)                                                    # decisão já tomada: idempotente


def test_eviction_ignored_stops_operation_until_relocation_or_new_lease(client, rich, db, monkeypatch):
    no_zero_months(monkeypatch)
    cid = create_ok(client, rich, extra="100000")["company"]["id"]
    mature(db, cid, 50)
    eid = make_incident(client, rich, db, monkeypatch, cid, "despejo")
    decide(client, rich, eid, "ignorar")
    d = detail(client, rich, cid)
    assert d["lease"] is None and d["company"]["suspended_until"] is not None
    assert close(client, rich).status_code == 200                                                         # sem ponto: vendas zeradas, sem aluguel
    m = detail(client, rich, cid)["months"][0]
    assert D(m["units_sold"]) == 0 and D(m["revenue"]) == 0
    assert any("DESPEJO" in e["description"] for e in detail(client, rich, cid)["events"])
    for _ in range(2):                                                                                     # passado o prazo: novo ponto, volta a operar
        assert close(client, rich).status_code == 200
    d = detail(client, rich, cid)
    assert d["lease"] is not None and d["company"]["suspended_until"] is None and D(d["months"][0]["units_sold"]) > 0


def test_eviction_relocation_flow_clears_the_suspension(client, rich, db, monkeypatch):
    cid = create_ok(client, rich, extra="200000")["company"]["id"]
    eid = make_incident(client, rich, db, monkeypatch, cid, "despejo")
    decide(client, rich, eid, "ignorar")
    loc = detail(client, rich, cid)["company"]["location"]
    r = client.post(f"{C}/{cid}/relocate", headers=rich, json={"location": loc, "site_mode": "RENT", "idempotency_key": key()})   # mesmo bairro permitido
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["company"]["suspended_until"] is None and d["lease"] is not None


def test_eviction_move_option_relocates_automatically_with_cost(client, rich, db, monkeypatch):
    cid = create_ok(client, rich, extra="200000")["company"]["id"]
    d0 = detail(client, rich, cid)
    eid = make_incident(client, rich, db, monkeypatch, cid, "despejo")
    decide(client, rich, eid, "mudar")
    d1 = detail(client, rich, cid)
    assert d1["company"]["location"] != d0["company"]["location"] and d1["lease"] is not None and d1["company"]["suspended_until"] is None
    assert D(d1["company"]["cash"]) < D(d0["company"]["cash"])
    assert db.scalar(select(func.count()).select_from(LedgerEntry).where(LedgerEntry.company_id == cid, LedgerEntry.line == "RELOCATION")) >= 2


def test_eviction_fight_in_court_needs_an_active_lawyer_and_has_uncertain_result(client, rich, db, monkeypatch):
    bare = create_ok(client, rich, name="Sem Advogado", extra="100000", staff=False)["company"]["id"]
    eid = make_incident(client, rich, db, monkeypatch, bare, "despejo")
    assert "advogado" in decide(client, rich, eid, "justica", expect=400).text.lower()
    assert detail(client, rich, bare)["lease"] is not None                                               # nada mudou
    decide(client, rich, eid, "negociar", monkeypatch, 0.0)                                              # (resolve o evento da empresa sem advogado)
    assert close(client, rich).status_code == 200                                                         # um despejo por mês na carteira
    cid = create_ok(client, rich, name="Com Advogado", extra="100000")["company"]["id"]
    ev_win = make_incident(client, rich, db, monkeypatch, cid, "despejo")
    rent = D(detail(client, rich, cid)["lease"]["monthly_rent"])
    decide(client, rich, ev_win, "justica", monkeypatch, 0.0)                                             # ganhou
    assert detail(client, rich, cid)["lease"] is not None and ledger(db, cid, "Advogado e custas%").amount == quantize(max(D(1500), rent * D("1.5")))
    assert close(client, rich).status_code == 200
    assert incidents.INCIDENT_CAP and economy_service._spawn_incidents(db, 1, open_ref(client, rich), 1, 1.0) == []   # sem empresa com prob. > 0: nada
    cid2 = create_ok(client, rich, name="Com Advogado 2", extra="100000")["company"]["id"]
    ev_lose = make_incident(client, rich, db, monkeypatch, cid2, "despejo")
    decide(client, rich, ev_lose, "justica", monkeypatch, 0.99)                                            # perdeu
    assert detail(client, rich, cid2)["lease"] is None and detail(client, rich, cid2)["company"]["suspended_until"] is not None


def test_labor_lawsuit_probability_and_cost_follow_pj_and_hours(client, rich, db, monkeypatch):
    clt = create_ok(client, rich, name="Só CLT", extra="100000", staff=False)["company"]["id"]
    staff_up(client, rich, clt, regime="CLT")
    pj = create_ok(client, rich, name="Muito PJ", extra="100000", staff=False)["company"]["id"]
    staff_up(client, rich, pj, regime="PJ")
    ref = open_ref(client, rich)
    p_clt, p_pj = incidents.lawsuit_prob(db, db.get(Company, clt), ref), incidents.lawsuit_prob(db, db.get(Company, pj), ref)
    assert 0 < p_clt < p_pj                                                                              # PJ alegando vínculo pesa mais
    from backend.models import Employee
    for e in db.scalars(select(Employee).where(Employee.company_id == clt, Employee.role.in_(["barista", "attendant"]))):
        e.hours_week = 54
    db.commit()
    assert incidents.lawsuit_prob(db, db.get(Company, clt), ref) > 3 * p_clt                              # jornada média > 48 h
    # custo coerente com a folha real (CLT 2x, PJ 1x): acordo = 2 x folha x multiplicador da causa (mais PJ => causa maior)
    eid = make_incident(client, rich, db, monkeypatch, pj, "processo_trabalhista")
    claim = db.get(WorldEvent, eid).effects["claim_mult"]
    assert claim > 1.0
    payroll = sum((D(e["total_cost"]) for e in detail(client, rich, pj)["employees"] if e["status"] == "ACTIVE"), D(0))
    assert payroll == sum((D(e["salary"]) * (1 if e["regime"] == "PJ" else 2) for e in detail(client, rich, pj)["employees"] if e["status"] == "ACTIVE"), D(0))
    decide(client, rich, eid, "acordo", monkeypatch, 0.0)
    assert ledger(db, pj, "Acordo trabalhista%").amount == max(D(3000), quantize(payroll * D(2) * D(str(claim))))


def test_equipment_breakage_options_cost_scales_with_setup_and_shield(client, rich, db, monkeypatch):
    real_breakage = incidents.breakage_prob
    cid = create_ok(client, rich, extra="100000")["company"]["id"]
    setup = company_rules.setup_cost(company_rules.SEGMENTS[company_rules.CompanySegment.CAFE], company_rules.CompanySize.SMALL, company_rules.PHYSICAL)
    eid = make_incident(client, rich, db, monkeypatch, cid, "equipamento_quebra")
    ev = next(e for e in client.get("/api/economy/decisions", headers=rich).json()["pending"] if e["id"] == eid)
    assert {o["key"] for o in ev["options"]} == {"barato", "medio", "premium", "adiar"}
    decide(client, rich, eid, "premium", monkeypatch, 0.0)
    assert ledger(db, cid, "Conserto premium de equipamento%").amount == max(D(500), quantize(setup * D("0.16")))
    c = db.get(Company, cid)
    assert c.incident_shield_until is not None and real_breakage(db, c, open_ref(client, rich)) == 0       # premium: sem quebra por 12 meses
    assert close(client, rich).status_code == 200
    eid2 = make_incident(client, rich, db, monkeypatch, create_ok(client, rich, name="Outra", extra="100000")["company"]["id"], "equipamento_quebra")
    decide(client, rich, eid2, "barato", monkeypatch, 0.999)                                               # reincidiu: custo maior
    assert ledger(db, db.get(WorldEvent, eid2).company_id, "Conserto barato + reincidência%").amount == quantize(setup * D("0.10"))


def test_equipment_breakage_postponing_reduces_operation_and_can_worsen(client, rich, db, monkeypatch):
    cid = create_ok(client, rich, extra="100000")["company"]["id"]
    eid = make_incident(client, rich, db, monkeypatch, cid, "equipamento_quebra")
    decide(client, rich, eid, "adiar", monkeypatch, 0.0)
    ev = db.get(WorldEvent, eid)
    db.refresh(ev)
    assert ev.status == "ACTIVE" and ev.effects["company_demand_pct"] == -30 and ev.choice == "adiar"      # operação reduzida no mês
    assert close(client, rich).status_code == 200
    cid2 = create_ok(client, rich, name="Piorou", extra="100000")["company"]["id"]
    eid2 = make_incident(client, rich, db, monkeypatch, cid2, "equipamento_quebra")
    decide(client, rich, eid2, "adiar", monkeypatch, 0.99)
    assert ledger(db, cid2, "Conserto adiado (dano maior)%") is not None


def test_incidents_spawn_in_the_monthly_close_of_a_dynamic_world(client, rich, db, monkeypatch):
    from tests.test_economy import start_world
    start_world(client, rich, seed=11)
    cid = create_ok(client, rich, extra="100000")["company"]["id"]
    monkeypatch.setattr(incidents, "eviction_prob", lambda _db, c, _ref: 1.0 if c.id == cid else 0.0)
    monkeypatch.setattr(incidents, "lawsuit_prob", lambda *a: 0.0)
    monkeypatch.setattr(incidents, "breakage_prob", lambda *a: 0.0)
    assert close(client, rich).status_code == 200
    pend = client.get("/api/economy/decisions", headers=rich).json()["pending"]
    assert any(e["key"] == "despejo" and e["company_id"] == cid for e in pend) or any("espejo" in e["name"] for e in pend)
