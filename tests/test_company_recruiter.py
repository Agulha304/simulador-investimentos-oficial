"""Contratador (headhunter) opcional, histórico trabalhista, canal restrito e limites de contrato de fornecedor (Empresas v2)."""
import datetime as dt
from decimal import Decimal

import pytest
from sqlalchemy import select

from backend.models import Company, CompanyRecruiter, CompanySupplier, Employee, EmployeeRegime, LedgerEntry, WorkSchedule
from backend.services import company_recruiter as rec
from backend.services import company_rules as rules
from backend.services import company_service as cs
from backend.services import company_team as team
from tests.test_companies import (  # noqa: F401  (fixtures e helpers compartilhados)
    B, C, _flat_season, close, contract_suppliers, create, create_ok, detail, fund, key, rich,
)

D = Decimal
REF = dt.date(2026, 11, 1)


def hire_rec(client, h, cid, tier="ELITE", **settings):
    r = client.post(f"{C}/{cid}/recruiter", headers=h, json={"tier": tier, "idempotency_key": key()})
    assert r.status_code == 200, r.text
    body = {"max_salary": "30000", "schedule": "5x2", "regime_policy": "BOTH", **settings}
    r = client.put(f"{C}/{cid}/recruiter/settings", headers=h, json=body)
    assert r.status_code == 200, r.text
    return r.json()


def post(client, h, cid, path, **body):
    return client.post(f"{C}/{cid}/recruiter/{path}", headers=h, json={"idempotency_key": key(), **body})


def new_company(client, h, **kw):
    return create_ok(client, h, staff=False, extra=kw.pop("extra", "300000"), **kw)["company"]["id"]


# ------------------------------------------------------------------ canal restrito

def test_restaurant_cafe_supermarket_cannot_be_online_but_clothing_can(client, rich):
    for seg in ("RESTAURANT", "CAFE", "SUPERMARKET"):
        r = create(client, rich, name=f"{seg} online", segment=seg, channel="ONLINE")
        assert r.status_code == 400 and "canal não permitido" in r.json()["detail"] and "física" in r.json()["detail"], seg
        assert client.post(f"{C}/quote", headers=rich, json={"segment": seg, "channel": "ONLINE"}).status_code == 400
        assert create(client, rich, name=f"{seg} física", segment=seg, channel="PHYSICAL").status_code == 201
    assert create(client, rich, name="Roupas online", segment="CLOTHING", channel="ONLINE").status_code == 201
    by = {s["key"]: s for s in client.get(f"{C}/catalog", headers=rich).json()["segments"]}
    assert [by[k]["channels"] for k in ("RESTAURANT", "CAFE", "SUPERMARKET")] == [["PHYSICAL"]] * 3


# ------------------------------------------------------------------ histórico trabalhista

def test_lawsuit_history_is_deterministic_and_has_realistic_frequency():
    seg = rules.SEGMENTS[rules.CompanySegment.CAFE]
    role = seg.role_for("barista", rules.CompanySize.SMALL)
    a = [team.build_candidate(1, 7, REF, role, EmployeeRegime.PJ, i).lawsuit_history for i in range(40)]
    assert a == [team.build_candidate(1, 7, REF, role, EmployeeRegime.PJ, i).lawsuit_history for i in range(40)]

    def freq(regime):
        n = with_h = 0
        for cid in range(1, 40):
            for i in range(10):
                c = team.build_candidate(3, cid, REF, role, regime, i)
                n += 1
                with_h += c.lawsuit_history > 0
                assert 0 <= c.lawsuit_history <= 3
        return with_h / n
    clt, pj = freq(EmployeeRegime.CLT), freq(EmployeeRegime.PJ)
    assert 0.05 < clt < 0.16 and 0.10 < pj < 0.28 and pj > clt                                    # ~12-15% na média, mais comum em PJ
    long_role = seg.role_for("accountant", rules.CompanySize.LARGE)                                # jornada longa (40 h) vs. 44 h do 6x1 não muda a regra básica
    assert all(0 <= team.build_candidate(3, 1, REF, long_role, EmployeeRegime.CLT, i).lawsuit_history <= 3 for i in range(10))


def test_lawsuit_history_raises_dismissal_lawsuit_probability():
    p = team.lawsuit_probability
    CLT, PJ, S5 = EmployeeRegime.CLT, EmployeeRegime.PJ, WorkSchedule.ESC_5X2
    assert p(CLT, 40, S5, 0) == p(CLT, 40, S5, 0, 0) == 0.06
    assert p(CLT, 40, S5, 0, 1) == pytest.approx(0.06 * 1.6) and p(CLT, 40, S5, 0, 2) == pytest.approx(0.06 * 2.2)
    assert p(PJ, 40, S5, 0, 3) == 0.9 and p(PJ, 40, S5, 0, 1) == pytest.approx(0.35 * 1.6) and p(PJ, 80, WorkSchedule.ESC_6X1, 60, 3) <= 0.9


def test_candidates_expose_history_and_employee_keeps_it(client, rich, db):
    cid = new_company(client, rich)
    cands = client.post(f"{C}/{cid}/candidates", headers=rich, json={"role": "barista", "regime": "PJ"}).json()["candidates"]
    assert all("lawsuit_history" in c for c in cands)
    withh = None
    for regime in ("PJ", "CLT"):                                                                    # procura um candidato com histórico entre os cargos/regimes
        for role in ("barista", "attendant", "pastry", "manager", "accountant", "lawyer", "cleaner"):
            for c in client.post(f"{C}/{cid}/candidates", headers=rich, json={"role": role, "regime": regime}).json()["candidates"]:
                if c["lawsuit_history"] > 0 and withh is None:
                    withh = (c, regime)
    if withh is None:
        pytest.skip("nenhum candidato com histórico nesta semente")
    c, regime = withh
    r = client.post(f"{C}/{cid}/hire", headers=rich, json={"candidate_id": c["id"], "salary": str(int(D(c["asking_salary"]) * D("1.3"))), "hours_week": c["hours_week"],
                                                          "schedule": c["schedule"], "regime": regime, "confirm_risk": True, "idempotency_key": key()})
    e = r.json()["company"]["employees"][0]
    assert e["lawsuit_history"] == c["lawsuit_history"]
    p = team.lawsuit_probability(EmployeeRegime(regime), e["hours_week"], WorkSchedule(e["schedule"]), 0, e["lawsuit_history"])
    assert e["lawsuit_risk_pct"] == pytest.approx(round(p * 100, 1))


# ------------------------------------------------------------------ contratar / dispensar / trocar / cobrança

def test_recruiter_is_optional_and_requires_active_for_actions(client, rich):
    cid = new_company(client, rich)
    d = detail(client, rich, cid)
    assert d["recruiter"] is None and [t["tier"] for t in d["recruiter_tiers"]] == ["BASIC", "PRO", "ELITE"]
    assert [D(t["monthly_fee"]) for t in d["recruiter_tiers"]] == [D(900), D(2200), D(4800)]               # porte pequeno
    assert post(client, rich, cid, "hire-mandatory").status_code == 409
    assert post(client, rich, cid, "hire-team", roles=[{"role": "barista", "count": 1}]).status_code == 409
    assert post(client, rich, cid, "contract-suppliers").status_code == 409
    assert client.put(f"{C}/{cid}/recruiter/settings", headers=rich, json={"max_salary": "1000"}).status_code == 409
    assert client.delete(f"{C}/{cid}/recruiter", headers=rich).status_code == 409
    assert "Contrate um contratador" in post(client, rich, cid, "hire-mandatory").json()["detail"]


def test_recruiter_fee_scales_with_size():
    assert [rec.monthly_fee(t, rules.CompanySize.MEDIUM) for t in ("BASIC", "PRO", "ELITE")] == [D("1440.00"), D("3520.00"), D("7680.00")]
    assert [rec.monthly_fee(t, rules.CompanySize.LARGE) for t in ("BASIC", "PRO", "ELITE")] == [D("2340.00"), D("5720.00"), D("12480.00")]
    assert [rec.commission(t, D(1000)) for t in ("BASIC", "PRO", "ELITE")] == [D("250.00"), D("200.00"), D("150.00")]


def test_hire_switch_dismiss_recruiter_and_monthly_fee(client, rich, db):
    cid = new_company(client, rich)
    d0 = detail(client, rich, cid)
    k = key()
    body = {"tier": "BASIC", "idempotency_key": k}
    d1 = client.post(f"{C}/{cid}/recruiter", headers=rich, json=body).json()
    assert d1["recruiter"]["tier"] == "BASIC" and d1["recruiter"]["status"] == "ACTIVE" and D(d1["recruiter"]["monthly_fee"]) == D(900)
    assert D(d1["company"]["cash"]) == D(d0["company"]["cash"])                                       # sem custo imediato
    assert D(d1["monthly_obligations"]) == D(d0["monthly_obligations"]) + D(900)                      # taxa entra nas obrigações mensais...
    assert D(d1["runway_months"]) == (D(d1["company"]["cash"]) / D(d1["monthly_obligations"])).quantize(D("0.01"))   # ...e no runway
    assert D(d1["runway_months"]) < D(d0["runway_months"])
    again = client.post(f"{C}/{cid}/recruiter", headers=rich, json=body).json()                      # idempotente
    assert again["recruiter"]["tier"] == "BASIC" and len(db.scalars(select(CompanyRecruiter)).all()) == 1
    assert client.post(f"{C}/{cid}/recruiter", headers=rich, json={"tier": "GOLD", "idempotency_key": key()}).status_code == 400
    d2 = client.post(f"{C}/{cid}/recruiter", headers=rich, json={"tier": "PRO", "idempotency_key": key()}).json()      # troca de nível
    assert d2["recruiter"]["tier"] == "PRO" and D(d2["monthly_obligations"]) == D(d0["monthly_obligations"]) + D(2200)
    assert close(client, rich).status_code == 200                                                    # cobrança no fechamento (linha FEES)
    def rec_fees():
        return [e for e in db.scalars(select(LedgerEntry).where(LedgerEntry.company_id == cid, LedgerEntry.line == "FEES")) if "contratador" in e.description.lower()]
    fees = rec_fees()
    assert len(fees) == 1 and fees[0].amount == D("2200.00") and "contratador" in fees[0].description.lower()
    d3 = client.delete(f"{C}/{cid}/recruiter", headers=rich).json()                                   # dispensa sem multa
    assert d3["recruiter"]["status"] == "ENDED" and D(d3["monthly_obligations"]) == D(d0["monthly_obligations"])
    assert D(d3["company"]["cash"]) == D(detail(client, rich, cid)["company"]["cash"])
    assert close(client, rich).status_code == 200
    db.expire_all()
    assert len(rec_fees()) == 1                                                                       # não cobra mais
    assert post(client, rich, cid, "hire-mandatory").status_code == 409
    d4 = client.post(f"{C}/{cid}/recruiter", headers=rich, json={"tier": "ELITE", "idempotency_key": key()}).json()   # recontratar
    assert d4["recruiter"]["status"] == "ACTIVE" and d4["recruiter"]["tier"] == "ELITE"


# ------------------------------------------------------------------ briefing

def test_briefing_validation_and_persistence(client, rich):
    cid = new_company(client, rich)
    hire_rec(client, rich, cid, "PRO")
    url = f"{C}/{cid}/recruiter/settings"
    bad = [{"max_salary": "0"}, {"max_salary": "-5"}, {"hours_week": 50}, {"hours_week": 10}, {"regime_policy": "XYZ"}, {"schedule": "7x0"},
           {"supplier_min_reliability": 1.5}, {"supplier_max_lead_days": 0}, {"supplier_volume_cap": "0"}, {"max_monthly_payroll": "-1"},
           {"supplier_overrides": {"nao_existe": {"max_spend": "100"}}}, {"supplier_overrides": {"graos": {"min_reliability": 0}}}]
    for b in bad:
        r = client.put(url, headers=rich, json={"max_salary": "5000", **b} if "max_salary" not in b else b)
        assert r.status_code == 400, (b, r.text)
    ok = {"max_salary": "4500.50", "schedule": "12x36", "hours_week": 36, "regime_policy": "PJ_ONLY", "max_monthly_payroll": "20000",
          "supplier_max_total_spend": "50000", "supplier_min_reliability": 0.9, "supplier_max_lead_days": 10, "supplier_volume_cap": "5000",
          "supplier_overrides": {"graos": {"max_spend": "8000", "min_reliability": 0.95, "max_lead_days": 5, "volume_cap": "300"}}}
    r = client.put(url, headers=rich, json=ok)
    assert r.status_code == 200, r.text
    s = detail(client, rich, cid)["recruiter"]["settings"]
    assert s["max_salary"] == "4500.50" and s["schedule"] == "12x36" and s["hours_week"] == 36 and s["regime_policy"] == "PJ_ONLY"
    assert s["supplier_overrides"]["graos"] == {"max_spend": "8000", "min_reliability": 0.95, "max_lead_days": 5, "volume_cap": "300"}
    assert s["supplier_min_reliability"] == 0.9 and s["supplier_max_total_spend"] == "50000"
    s2 = client.put(url, headers=rich, json={"max_salary": "1000"}).json()["recruiter"]["settings"]                # PUT substitui; escala padrão => 40 h
    assert s2["hours_week"] == 40 and s2["regime_policy"] == "BOTH" and s2["supplier_overrides"] == {}
    r = client.put(url, headers=rich, json={"max_salary": "1000", "schedule": "6x1"})
    assert r.json()["recruiter"]["settings"]["hours_week"] == 44


# ------------------------------------------------------------------ cargos obrigatórios

def test_hire_mandatory_hires_missing_within_cap_makes_company_regular_and_is_idempotent(client, rich, db):
    cid = new_company(client, rich)
    assert detail(client, rich, cid)["compliance"]["regular"] is False
    hire_rec(client, rich, cid, "ELITE", max_salary="9000", schedule="5x2")
    cash0 = D(detail(client, rich, cid)["company"]["cash"])
    k = key()
    r = client.post(f"{C}/{cid}/recruiter/hire-mandatory", headers=rich, json={"idempotency_key": k})
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["kind"] == "MANDATORY" and out["replayed"] is False and not out["skipped"]
    assert sorted(h["role"] for h in out["hired"]) == ["accountant", "cleaner", "lawyer"]
    for h in out["hired"]:
        assert D(h["salary"]) <= D("9000") and h["schedule"] == "5x2" and 20 <= h["hours_week"] <= 40
        assert D(h["commission"]) == (D(h["salary"]) * D("0.15")).quantize(D("0.01"))                 # ELITE: 15% do salário
        assert D(h["monthly_cost"]) == D(h["salary"]) * (2 if h["regime"] == "CLT" else 1)
        assert h["why_regime"]
    assert D(out["total_commission"]) == sum(D(h["commission"]) for h in out["hired"])
    assert D(out["total_monthly_cost"]) == sum(D(h["monthly_cost"]) for h in out["hired"])
    d = out["company"]
    assert d["compliance"]["regular"] is True and D(d["company"]["cash"]) == cash0 - D(out["total_commission"])
    lines = [e for e in d["ledger"] if e["line"] == "HIRING"]
    assert len(lines) == 3 and all("contratador" in e["description"].lower() for e in lines)
    # mandatórios do porte pequeno: a jornada reduzida (20 h) custa menos e é a escolhida
    assert any(h["hours_week"] == 20 for h in out["hired"])
    again = client.post(f"{C}/{cid}/recruiter/hire-mandatory", headers=rich, json={"idempotency_key": k}).json()
    assert again["replayed"] is True and again["hired"] == out["hired"] and D(again["company"]["company"]["cash"]) == D(d["company"]["cash"])
    assert len(db.scalars(select(Employee).where(Employee.company_id == cid)).all()) == 3
    nothing = post(client, rich, cid, "hire-mandatory").json()
    assert nothing["hired"] == [] and "já estão preenchidos" in nothing["message"]


def test_hire_mandatory_does_not_hire_when_nothing_fits_the_salary_cap(client, rich):
    cid = new_company(client, rich)
    hire_rec(client, rich, cid, "PRO", max_salary="300")
    cash0 = D(detail(client, rich, cid)["company"]["cash"])
    out = post(client, rich, cid, "hire-mandatory").json()
    assert out["hired"] == [] and len(out["skipped"]) == 3 and D(out["total_commission"]) == 0
    assert all("teto" in x["reason"] for x in out["skipped"]), out["skipped"]
    assert out["company"]["compliance"]["regular"] is False and D(out["company"]["company"]["cash"]) == cash0
    assert out["company"]["employees"] == []


def test_hire_mandatory_respects_cash_and_runs_with_a_partial_cap(client, rich, db):
    cid = new_company(client, rich)
    hire_rec(client, rich, cid, "BASIC", max_salary="9000")
    from backend.models import FinanceAccount
    acc = db.scalar(select(FinanceAccount).join(Company, Company.account_id == FinanceAccount.id).where(Company.id == cid))
    acc.balance = D("1.00")
    db.commit()
    out = post(client, rich, cid, "hire-mandatory").json()
    assert out["hired"] == [] and all("caixa" in x["reason"] for x in out["skipped"])


# ------------------------------------------------------------------ equipe

def test_hire_team_counts_ranking_and_commission(client, rich):
    cid = new_company(client, rich)
    hire_rec(client, rich, cid, "ELITE", max_salary="12000", regime_policy="CLT_ONLY")
    out = post(client, rich, cid, "hire-team", roles=[{"role": "barista", "count": 2}, {"role": "attendant", "count": 1}]).json()
    assert out["kind"] == "TEAM" and len(out["hired"]) == 3 and not out["skipped"]
    by = {}
    for h in out["hired"]:
        by.setdefault(h["role"], []).append(h)
        assert h["regime"] == "CLT" and D(h["salary"]) <= D("12000") and D(h["commission"]) == (D(h["salary"]) * D("0.15")).quantize(D("0.01"))
    assert len(by["barista"]) == 2 and len(by["attendant"]) == 1
    # ranking por custo-benefício: o 1o contratado do cargo é o de maior produtividade/custo; o 2o não é melhor
    assert by["barista"][0]["cost_benefit"] >= by["barista"][1]["cost_benefit"]
    emps = out["company"]["employees"]
    assert len(emps) == 3 and len({e["name"] for e in emps}) == 3
    assert all(e["schedule"] == "5x2" and e["hours_week"] == 40 for e in emps)
    again = post(client, rich, cid, "hire-team", roles=[{"role": "barista", "count": 1}]).json()
    assert len(again["hired"]) == 1 and again["hired"][0]["name"] not in {e["name"] for e in emps}      # ninguém é contratado duas vezes
    assert client.post(f"{C}/{cid}/recruiter/hire-team", headers=rich, json={"idempotency_key": key(), "roles": [{"role": "inexistente", "count": 1}]}).status_code == 400


def test_hire_team_respects_staff_cap_payroll_cap_and_cash(client, rich, db, monkeypatch):
    cid = new_company(client, rich)
    hire_rec(client, rich, cid, "ELITE", max_salary="12000", regime_policy="CLT_ONLY")
    monkeypatch.setattr(rules, "max_staff", lambda size, units: 2)
    out = post(client, rich, cid, "hire-team", roles=[{"role": "barista", "count": 4}]).json()
    assert len(out["hired"]) == 2 and out["skipped"][0]["missing"] == 2 and "teto de funcionários" in out["skipped"][0]["reason"]
    monkeypatch.undo()
    # teto de folha extra do briefing: só entra o que cabe
    cid2 = new_company(client, rich, name="Café 2")
    hire_rec(client, rich, cid2, "ELITE", max_salary="12000", regime_policy="CLT_ONLY", max_monthly_payroll="4000")
    out2 = post(client, rich, cid2, "hire-team", roles=[{"role": "barista", "count": 5}]).json()
    assert sum(D(h["monthly_cost"]) for h in out2["hired"]) <= D("4000") and len(out2["hired"]) < 5 and out2["skipped"]
    assert "folha" in out2["skipped"][0]["reason"] or "orçamento" in out2["skipped"][0]["reason"]
    # caixa: runway pós-contratação < 2 meses não contrata
    cid3 = new_company(client, rich, name="Café 3")
    hire_rec(client, rich, cid3, "ELITE", max_salary="12000", regime_policy="CLT_ONLY")
    from backend.models import FinanceAccount
    acc = db.scalar(select(FinanceAccount).join(Company, Company.account_id == FinanceAccount.id).where(Company.id == cid3))
    obligations = D(detail(client, rich, cid3)["monthly_obligations"])
    acc.balance = obligations * D("2.2")
    db.commit()
    out3 = post(client, rich, cid3, "hire-team", roles=[{"role": "barista", "count": 6}]).json()
    assert out3["skipped"] and "caixa" in out3["skipped"][0]["reason"]
    d3 = out3["company"]
    assert D(d3["runway_months"]) >= D(2) - D("0.05") or not out3["hired"]


def test_hire_team_reports_why_nobody_fits_the_salary_cap(client, rich):
    cid = new_company(client, rich)
    hire_rec(client, rich, cid, "PRO", max_salary="500")
    out = post(client, rich, cid, "hire-team", roles=[{"role": "chef" if False else "barista", "count": 2}]).json()
    assert out["hired"] == [] and out["skipped"][0]["missing"] == 2 and "teto" in out["skipped"][0]["reason"]


def test_regime_policy_both_uses_history_and_clt_only_pj_only_are_respected(client, rich):
    cid = new_company(client, rich, extra="2000000")
    hire_rec(client, rich, cid, "ELITE", max_salary="15000", regime_policy="BOTH")
    out = post(client, rich, cid, "hire-team", roles=[{"role": "barista", "count": 6}, {"role": "attendant", "count": 6}, {"role": "pastry", "count": 6}]).json()
    assert len(out["hired"]) >= 6
    for h in out["hired"]:
        if h["lawsuit_history"] > 0:
            assert h["regime"] == "CLT" and "processo" in h["why_regime"]                          # com histórico: CLT
        else:
            assert h["regime"] == "PJ" or "CLT" in h["why_regime"]                                 # sem histórico: PJ (ou CLT se o PJ não coube)
    assert any(h["regime"] == "PJ" for h in out["hired"]) and all(h["why_regime"] for h in out["hired"])
    emps = {e["name"]: e for e in out["company"]["employees"]}
    assert all(emps[h["name"]]["regime"] == h["regime"] and emps[h["name"]]["lawsuit_history"] == h["lawsuit_history"] for h in out["hired"])
    for policy, expect in (("CLT_ONLY", "CLT"), ("PJ_ONLY", "PJ")):
        c2 = new_company(client, rich, name=f"Café {policy}", extra="2000000")
        hire_rec(client, rich, c2, "ELITE", max_salary="15000", regime_policy=policy)
        o2 = post(client, rich, c2, "hire-team", roles=[{"role": "barista", "count": 4}]).json()
        assert o2["hired"] and all(h["regime"] == expect for h in o2["hired"]), policy


def test_both_policy_falls_back_to_clt_when_pj_exceeds_the_salary_cap():
    seg = rules.SEGMENTS[rules.CompanySegment.CAFE]
    role = seg.role_for("barista", rules.CompanySize.SMALL)
    cfg_clt = rec.Settings(max_salary=D(50000), regime_policy="BOTH")
    for cid in range(1, 25):
        for p in rec.person_pool(1, cid, REF, role, "ELITE"):
            if p.lawsuit_history > 0:
                continue
            pj = rec.plan_for(p, EmployeeRegime.PJ, 40, WorkSchedule.ESC_5X2, "ELITE", D(50000))
            clt = rec.plan_for(p, EmployeeRegime.CLT, 40, WorkSchedule.ESC_5X2, "ELITE", D(50000))
            assert not isinstance(pj, str) and not isinstance(clt, str)
            cap = max(pj.salary - 1, clt.salary)                                                   # PJ não cabe no teto, CLT cabe (PJ pede ~10% mais)
            if pj.salary > clt.salary:
                got = rec.choose_plan(p, "BOTH", [40], WorkSchedule.ESC_5X2, "ELITE", cap)
                assert not isinstance(got, str) and got.person.regime == EmployeeRegime.CLT and "PJ não coube" in got.why
                return
    pytest.fail("amostra sem caso PJ > CLT")


def test_recruiter_proposal_is_the_minimum_the_candidate_accepts():
    seg = rules.SEGMENTS[rules.CompanySegment.CAFE]
    role = seg.role_for("barista", rules.CompanySize.SMALL)
    for tier in ("BASIC", "ELITE"):
        extra = rec.TIERS[tier].discount
        for cid in range(1, 10):
            for p in rec.person_pool(2, cid, REF, role, tier):
                for regime in (EmployeeRegime.CLT, EmployeeRegime.PJ):
                    plan = rec.plan_for(p, regime, 40, WorkSchedule.ESC_5X2, tier, D(10 ** 6))
                    c = plan.person
                    assert team.evaluate_offer(c, plan.salary, 40, WorkSchedule.ESC_5X2, extra).accepted
                    assert not team.evaluate_offer(c, plan.salary - 1, 40, WorkSchedule.ESC_5X2, extra).accepted
                    # sem o desconto do nível (fluxo manual) o mesmo valor pode ser insuficiente, nunca o contrário
                    assert team.min_acceptable(c, 40, WorkSchedule.ESC_5X2, 0.0) >= plan.salary


def test_elite_gets_better_cost_benefit_than_basic_on_a_sample():
    seg = rules.SEGMENTS[rules.CompanySegment.CAFE]
    cfg = rec.Settings(max_salary=D(50000), regime_policy="BOTH")
    mean = {}
    count = {}
    for tier in ("BASIC", "PRO", "ELITE"):
        scores, n = [], 0
        for seed in (1, 2, 3):
            for cid in range(1, 41):
                for rk in ("barista", "attendant"):
                    plans, _ = rec.ranked_plans(seed, cid, REF, seg.role_for(rk, rules.CompanySize.SMALL), tier, cfg)
                    if plans:
                        scores.append(plans[0].score)
                        n += 1
        mean[tier] = sum(scores) / len(scores)
        count[tier] = n
    assert mean["ELITE"] > mean["PRO"] > mean["BASIC"], mean
    assert count["ELITE"] >= count["PRO"] >= count["BASIC"], count                                # e acha candidato em mais vagas
    # determinismo
    a, _ = rec.ranked_plans(1, 5, REF, seg.role_for("barista", rules.CompanySize.SMALL), "ELITE", cfg)
    b, _ = rec.ranked_plans(1, 5, REF, seg.role_for("barista", rules.CompanySize.SMALL), "ELITE", cfg)
    assert [(p.key, p.salary) for p in a] == [(p.key, p.salary) for p in b]


# ------------------------------------------------------------------ fornecedores

def sup_rows(client, h, cid):
    return {x["category"]: x for x in detail(client, h, cid)["supply"]["contracts"]}


def test_contract_suppliers_creates_contracts_with_limits_and_is_idempotent(client, rich):
    cid = new_company(client, rich)
    hire_rec(client, rich, cid, "ELITE", supplier_max_total_spend="900000", supplier_min_reliability=0.85, supplier_max_lead_days=14,
             supplier_overrides={"graos": {"max_spend": "500000", "volume_cap": "100000"}})
    k = key()
    r = client.post(f"{C}/{cid}/recruiter/contract-suppliers", headers=rich, json={"idempotency_key": k})
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["kind"] == "SUPPLIERS" and out["contracted"], out
    rows = sup_rows(client, rich, cid)
    assert set(rows) == {x["category"] for x in out["contracted"]}
    for x in out["contracted"]:
        ct = rows[x["category"]]
        assert x["reliability"] >= 0.85 and x["lead_days"] <= 14 and ct["min_reliability"] == 0.85 and ct["max_lead_days"] == 14
        assert D(ct["unit_price"]) == D(x["unit_price"]) and D(ct["unit_price"]) <= D(ct["reference_price"]) * D("1.07")
        assert D(ct["unit_price"]) >= D(ct["reference_price"]) * D("0.7")
    if "graos" in rows:
        assert D(rows["graos"]["max_monthly_spend"]) == D("500000") and D(rows["graos"]["volume_cap"]) == D("100000")
        assert D(rows["graos"]["max_units_month"]) <= D("100000")
    assert D(out["total_expected_spend"]) == sum(D(x["expected_spend"]) for x in out["contracted"]) <= D("900000")
    again = client.post(f"{C}/{cid}/recruiter/contract-suppliers", headers=rich, json={"idempotency_key": k}).json()
    assert again["replayed"] is True and again["contracted"] == out["contracted"] and len(sup_rows(client, rich, cid)) == len(rows)
    nothing = post(client, rich, cid, "contract-suppliers", categories=list(rows)).json()                 # já contratadas
    assert nothing["contracted"] == [] and all("já existe contrato" in s["reason"] for s in nothing["skipped"])


def test_contract_suppliers_filters_by_reliability_lead_volume_and_spend(client, rich):
    cid = new_company(client, rich)
    hire_rec(client, rich, cid, "ELITE", supplier_min_reliability=0.995)                                  # ninguém chega a 99,5%
    out = post(client, rich, cid, "contract-suppliers").json()
    assert out["contracted"] == [] and len(out["skipped"]) == 3 and all("confiabilidade" in s["reason"] for s in out["skipped"])
    assert sup_rows(client, rich, cid) == {}
    hire_rec(client, rich, cid, "ELITE", supplier_max_lead_days=1)                                          # prazo mínimo do universo é 2 dias
    out = post(client, rich, cid, "contract-suppliers").json()
    assert out["contracted"] == [] and all("prazo" in s["reason"] for s in out["skipped"])
    hire_rec(client, rich, cid, "ELITE", supplier_volume_cap="0.5")                                         # abaixo de qualquer pedido mínimo (>= 1)
    out = post(client, rich, cid, "contract-suppliers").json()
    assert out["contracted"] == [] and all("volume" in s["reason"] for s in out["skipped"])
    hire_rec(client, rich, cid, "ELITE", supplier_overrides={"graos": {"max_spend": "1"}})                  # gasto máximo de UMA categoria
    out = post(client, rich, cid, "contract-suppliers", categories=["graos"]).json()
    assert out["contracted"] == [] and "gasto previsto" in out["skipped"][0]["reason"]
    hire_rec(client, rich, cid, "ELITE", supplier_max_total_spend="1")                                      # gasto total
    out = post(client, rich, cid, "contract-suppliers").json()
    assert out["contracted"] == [] and all("gasto total" in s["reason"] for s in out["skipped"])
    assert client.post(f"{C}/{cid}/recruiter/contract-suppliers", headers=rich, json={"idempotency_key": key(), "categories": ["xx"]}).status_code == 400


def test_supplier_override_prevails_over_the_general_setting(client, rich):
    cid = new_company(client, rich)
    hire_rec(client, rich, cid, "ELITE", supplier_min_reliability=0.995, supplier_overrides={"graos": {"min_reliability": 0.5}})
    out = post(client, rich, cid, "contract-suppliers").json()
    assert [x["category"] for x in out["contracted"]] == ["graos"]                                       # só a categoria com override passa
    assert {s["category"] for s in out["skipped"]} == {"laticinios", "embalagens"}
    assert sup_rows(client, rich, cid)["graos"]["min_reliability"] == 0.5


def test_total_spend_limit_is_respected_across_categories(client, rich):
    cid = new_company(client, rich)
    hire_rec(client, rich, cid, "ELITE")
    full = post(client, rich, cid, "contract-suppliers").json()
    total = D(full["total_expected_spend"])
    assert len(full["contracted"]) >= 2 and total > 0
    biggest = max(D(x["expected_spend"]) for x in full["contracted"])
    cid2 = new_company(client, rich, name="Café limitado")
    hire_rec(client, rich, cid2, "ELITE", supplier_max_total_spend=str(biggest + D("1")))
    lim = post(client, rich, cid2, "contract-suppliers").json()
    assert D(lim["total_expected_spend"]) <= biggest + D("1") and len(lim["contracted"]) < len(full["contracted"])
    assert any("gasto total" in s["reason"] for s in lim["skipped"])


# ------------------------------------------------------------------ limites por contrato (manual e automático)

def first_item(d, cat):
    return next(i for i in d["inventory"] if i["category"] == cat)


def test_contract_limits_validation_and_persistence(client, rich):
    cid = new_company(client, rich)
    d = contract_suppliers(client, rich, cid, ideal=False, stock=False)
    ct = d["supply"]["contracts"][0]
    url = f"{C}/{cid}/suppliers/{ct['id']}/limits"
    for bad in ({"max_monthly_spend": "0"}, {"volume_cap": "-1"}, {"min_reliability": 1.2}, {"max_lead_days": 0}):
        assert client.put(url, headers=rich, json=bad).status_code == 400, bad
    r = client.put(url, headers=rich, json={"max_monthly_spend": "1234.5", "volume_cap": "10", "min_reliability": 0.9, "max_lead_days": 7})
    assert r.status_code == 200, r.text
    x = next(c for c in r.json()["supply"]["contracts"] if c["id"] == ct["id"])
    assert D(x["max_monthly_spend"]) == D("1234.50") and D(x["volume_cap"]) == 10 and x["min_reliability"] == 0.9 and x["max_lead_days"] == 7
    assert D(x["effective_volume"]) == 10
    cleared = client.put(url, headers=rich, json={}).json()["supply"]["contracts"]
    assert next(c for c in cleared if c["id"] == ct["id"])["max_monthly_spend"] is None
    assert client.put(f"{C}/{cid}/suppliers/999999/limits", headers=rich, json={}).status_code == 404


def test_manual_purchase_respects_contract_spend_and_volume_limits(client, rich):
    cid = new_company(client, rich)
    d = contract_suppliers(client, rich, cid, ideal=True, stock=False)
    ct = d["supply"]["contracts"][0]
    item = first_item(d, ct["category"])
    q = D(ct["min_monthly_order"])
    cost = q * D(ct["unit_price"])
    url = f"{C}/{cid}/suppliers/{ct['id']}/limits"
    client.put(url, headers=rich, json={"max_monthly_spend": str((cost / 2).quantize(D("0.01")))})
    r = client.post(f"{C}/{cid}/stock", headers=rich, json={"item_id": item["id"], "quantity": str(q), "idempotency_key": key()})
    assert r.status_code == 409 and "Limite de gasto" in r.json()["detail"]
    client.put(url, headers=rich, json={"max_monthly_spend": str((cost * D("1.5")).quantize(D("0.01")))})
    assert client.post(f"{C}/{cid}/stock", headers=rich, json={"item_id": item["id"], "quantity": str(q), "idempotency_key": key()}).status_code == 201
    r = client.post(f"{C}/{cid}/stock", headers=rich, json={"item_id": item["id"], "quantity": str(q), "idempotency_key": key()})
    assert r.status_code == 409 and "Limite de gasto" in r.json()["detail"]                         # o gasto do mês acumula
    x = next(c for c in detail(client, rich, cid)["supply"]["contracts"] if c["id"] == ct["id"])
    assert D(x["spend_used"]) == cost
    client.put(url, headers=rich, json={"volume_cap": str(q)})                                       # volume máximo = o já comprado
    r = client.post(f"{C}/{cid}/stock", headers=rich, json={"item_id": item["id"], "quantity": str(q), "idempotency_key": key()})
    assert r.status_code == 409 and "volume" in r.json()["detail"].lower()


def test_auto_restock_respects_contract_spend_limit_and_explains(client, rich):
    cid = new_company(client, rich)
    d = contract_suppliers(client, rich, cid, ideal=True, stock=False)
    hire = __import__("tests.test_companies", fromlist=["x"])
    for role in ("accountant", "lawyer", "cleaner"):
        hire.hire_candidate(client, rich, cid, role, "CLT")
    for role in rules.initial_staff(rules.SEGMENTS[rules.CompanySegment.CAFE], rules.CompanySize.SMALL):
        hire.hire_candidate(client, rich, cid, role, "CLT")
    d = detail(client, rich, cid)
    for ct in d["supply"]["contracts"]:                                                            # limite de gasto ínfimo (menor que o pedido mínimo)
        r = client.put(f"{C}/{cid}/suppliers/{ct['id']}/limits", headers=rich, json={"max_monthly_spend": "0.01"})
        assert r.status_code == 200
    assert close(client, rich).status_code == 200
    d = detail(client, rich, cid)
    assert all(D(i["quantity"]) == 0 for i in d["inventory"])                                      # nada foi reposto
    assert any("travada pelo limite do contrato" in e["description"] for e in d["events"])
    assert not any(e["line"] == "STOCK_PURCHASE" for e in d["ledger"])


def test_budget_shows_planned_spend_versus_limits(client, rich):
    cid = new_company(client, rich)
    hire_rec(client, rich, cid, "ELITE", supplier_max_total_spend="1000")
    d = contract_suppliers(client, rich, cid, ideal=True, stock=False)
    ct = d["supply"]["contracts"][0]
    d = client.put(f"{C}/{cid}/suppliers/{ct['id']}/limits", headers=rich, json={"max_monthly_spend": "0.01"}).json()
    b = d["supply"]["budget"]
    row = next(r for r in b["rows"] if r["category"] == ct["category"])
    assert D(row["max_monthly_spend"]) == D("0.01") and row["over_limit"] is True
    assert D(b["total_limit"]) == 1000 and b["over_total"] is (D(b["total_planned"]) > 1000)


# ------------------------------------------------------------------ especificações de fornecedores OPCIONAIS (vazio/null = sem restrição)

def test_briefing_saved_without_any_supplier_field(client, rich):
    cid = new_company(client, rich)
    client.post(f"{C}/{cid}/recruiter", headers=rich, json={"tier": "BASIC", "idempotency_key": key()})
    r = client.put(f"{C}/{cid}/recruiter/settings", headers=rich, json={"max_salary": "9000"})                    # nenhum campo de fornecedor
    assert r.status_code == 200, r.text
    s = r.json()["recruiter"]["settings"]
    assert s["supplier_max_total_spend"] is None and s["supplier_min_reliability"] is None and s["supplier_max_lead_days"] is None
    assert s["supplier_volume_cap"] is None and s["supplier_overrides"] == {}
    r = client.put(f"{C}/{cid}/recruiter/settings", headers=rich, json={               # vazios ("" / null) também valem como "sem restrição"
        "max_salary": "9000", "supplier_max_total_spend": "", "supplier_min_reliability": "", "supplier_max_lead_days": None, "supplier_volume_cap": " ",
        "supplier_overrides": {"graos": {"max_spend": "", "min_reliability": None, "max_lead_days": "", "volume_cap": None}, "laticinios": None}})
    assert r.status_code == 200, r.text
    s = r.json()["recruiter"]["settings"]
    assert s["supplier_overrides"] == {} and s["supplier_max_total_spend"] is None and s["supplier_min_reliability"] is None   # override vazio não vira lixo guardado


def test_contract_suppliers_without_any_criteria_contracts_the_best_value_available(client, rich):
    cid = new_company(client, rich)
    hire_rec(client, rich, cid, "ELITE")                                                                            # briefing só com salário/escala
    out = post(client, rich, cid, "contract-suppliers").json()
    assert {x["category"] for x in out["contracted"]} == {"graos", "laticinios", "embalagens"} and out["skipped"] == []
    for ct in sup_rows(client, rich, cid).values():
        assert ct["max_monthly_spend"] is None and ct["volume_cap"] is None and ct["min_reliability"] is None and ct["max_lead_days"] is None
    for x in out["contracted"]:                                                    # preço negociado, nunca acima da referência x 1,07
        assert D(x["unit_price"]) <= D(x["reference_price"]) * D("1.07")


def test_clearing_a_contract_limit_removes_the_purchase_block(client, rich):
    cid = new_company(client, rich)
    d = contract_suppliers(client, rich, cid, ideal=True, stock=False)
    ct = d["supply"]["contracts"][0]
    item = first_item(d, ct["category"])
    q = D(ct["min_monthly_order"])
    url = f"{C}/{cid}/suppliers/{ct['id']}/limits"
    buy = lambda: client.post(f"{C}/{cid}/stock", headers=rich, json={"item_id": item["id"], "quantity": str(q), "idempotency_key": key()})  # noqa: E731
    assert client.put(url, headers=rich, json={"max_monthly_spend": "0.01", "volume_cap": "1000000"}).status_code == 200
    assert buy().status_code == 409                                                  # travado pelo limite
    r = client.put(url, headers=rich, json={"max_monthly_spend": "", "min_reliability": None})                       # limpa (vazio e null)
    assert r.status_code == 200, r.text
    x = next(c for c in r.json()["supply"]["contracts"] if c["id"] == ct["id"])
    assert x["max_monthly_spend"] is None and x["volume_cap"] is None and x["min_reliability"] is None and x["max_lead_days"] is None
    assert buy().status_code == 201                                                  # sem limite: compra normalmente
    assert client.put(url, headers=rich, json={}).status_code == 200                 # tudo ausente também é aceito


def test_override_empty_fields_inherit_only_the_general_and_clearing_removes_it():
    st = rec.build_settings({"supplier_min_reliability": 0.9, "supplier_overrides": {"graos": {"max_lead_days": 5, "min_reliability": ""}}},
                            {"graos", "laticinios"})
    lim = st.limits_for("graos")
    assert lim.max_lead_days == 5 and lim.min_reliability == 0.9 and lim.volume_cap is None and lim.max_spend is None       # só herda o geral
    assert st.limits_for("laticinios") == st.general
    cleared = rec.build_settings({"supplier_overrides": {"graos": {"max_lead_days": 5}}}, {"graos"})
    assert cleared.general == rec.Limits() and cleared.limits_for("graos").min_reliability is None                           # limpar o geral remove
    assert rec.build_settings({"supplier_overrides": {"graos": {}}}, {"graos"}).overrides == {}
    with pytest.raises(ValueError):
        rec.build_settings({"supplier_overrides": {"graos": {"min_reliability": 1.5}}}, {"graos"})                           # preenchido => valida


def test_legacy_briefings_and_contracts_keep_working():
    cats = {"graos", "laticinios"}
    assert rec.settings_from_json({}, cats) == rec.Settings() and rec.settings_from_json(None, cats) == rec.Settings()
    old = {"max_salary": "5000", "schedule": "6x1", "hours_week": 44, "regime_policy": "CLT_ONLY", "supplier_min_reliability": 0,
           "supplier_max_lead_days": 999, "supplier_max_total_spend": "20000", "supplier_overrides": {"graos": {"volume_cap": -1, "max_spend": "300"}, "x": {}}}
    st = rec.settings_from_json(old, cats)                                         # campos de fornecedor inválidos viram "sem restrição"; o resto fica
    assert st.max_salary == D(5000) and st.regime_policy == "CLT_ONLY" and st.hours_week == 44 and st.supplier_max_total_spend == D(20000)
    assert st.general.min_reliability is None and st.general.max_lead_days is None
    assert st.overrides["graos"] == rec.Limits(max_spend=D(300)) and "x" not in st.overrides
