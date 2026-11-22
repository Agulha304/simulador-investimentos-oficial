"""Imprevistos da empresa (fase 5): probabilidades MENSAIS por estado da empresa e custos de referência.

Os imprevistos viram EVENTOS COM DECISÃO (`economy_events`: despejo, processo trabalhista, quebra de equipamento), sorteados em
`economy_service._spawn` com `hash01(semente, ...)`: no máximo `INCIDENT_CAP` por mês na carteira do jogador. As probabilidades abaixo
são moderadas e documentadas em `docs/EMPRESAS_V2.md`; `expected_monthly_cost` entra na simulação de balanceamento.

  * DESPEJO (só PHYSICAL + RENT com contrato EXTERNAL ativo): base 1,0%/mês x contrato antigo (1x a 2x em 5 anos) x aluguel atrasado
    (3x se o caixa fechou o mês anterior negativo; 1,5x se o caixa não cobre 1 aluguel) x relevância (1,3x com 0 até 0,5x com 100).
  * PROCESSO TRABALHISTA (com funcionários): base 0,4%/mês; jornada média dos produtivos > 48 h soma 1,5% + 0,4 pt por hora acima de 48;
    cada PJ soma 0,5% x (1 + tempo de casa/36 meses, até 2x) por alegar vínculo. Teto 12%.
  * QUEBRA DE EQUIPAMENTO: base 3%/mês x (1 + 0,25 por nível de capacidade ampliada, até +50%) x 1,25 se há turno extra (jornada > 44 h);
    zero com o conserto premium em vigor (12 meses).
"""
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.core.money import quantize_money
from backend.models import Company, CompanyChannel, CompanyLease, CompanyMonth, Employee, EmployeeRegime, EmployeeStatus, LeaseKind, SiteMode
from backend.services import company_rules as rules

D = Decimal
INCIDENT_CAP = 2                       # no máximo 2 imprevistos de empresa por mês na carteira do jogador
EVICTION_BASE = 0.010
EVICTION_MONTHS_OFF = 2                # despejo ignorado: a empresa fica sem operar este nº de meses (ou até relocar)
LAWSUIT_BASE = 0.004
LAWSUIT_HOURS_THRESHOLD = 48
LAWSUIT_PJ = 0.005
LAWSUIT_CAP = 0.12
BREAKAGE_BASE = 0.03
BREAKAGE_SETUP_SHARE = D("0.08")       # conserto médio = 8% do custo de estruturação do porte
SHIELD_MONTHS = 12


def _months(a: date, b: date) -> int:
    return max((b.year - a.year) * 12 + b.month - a.month, 0)


def eviction_prob_values(*, lease_age_months: int, relevance: float, cash_prev: float, rent: float) -> float:
    age = 1 + min(max(lease_age_months, 0), 60) / 60
    late = 3.0 if cash_prev < 0 else (1.5 if cash_prev < rent else 1.0)
    rel = max(0.5, 1.3 - 0.8 * float(relevance) / 100)
    return min(0.5, EVICTION_BASE * age * late * rel)


def lease_of(db: Session, c: Company) -> CompanyLease | None:
    return db.scalar(select(CompanyLease).where(CompanyLease.company_id == c.id, CompanyLease.active.is_(True)))


def eviction_prob(db: Session, c: Company, ref: date) -> float:
    if c.channel != CompanyChannel.PHYSICAL or c.site_mode != SiteMode.RENT:
        return 0.0
    if c.suspended_until is not None and ref <= c.suspended_until:
        return 0.0
    lease = lease_of(db, c)
    if lease is None or lease.kind != LeaseKind.EXTERNAL or lease.monthly_rent <= 0:
        return 0.0
    last_cash = db.scalar(select(CompanyMonth.cash_end).where(CompanyMonth.company_id == c.id, CompanyMonth.ref_month < ref)
                          .order_by(CompanyMonth.ref_month.desc()).limit(1))
    return eviction_prob_values(lease_age_months=_months(lease.start_month, ref), relevance=float(c.relevance),
                                cash_prev=float(last_cash if last_cash is not None else 0), rent=float(lease.monthly_rent))


def _active_staff(db: Session, c: Company) -> list[Employee]:
    return list(db.scalars(select(Employee).where(Employee.company_id == c.id, Employee.status == EmployeeStatus.ACTIVE)))


def lawsuit_prob_values(*, productive_hours: list[int], pj_tenures: list[int], has_staff: bool) -> float:
    if not has_staff:
        return 0.0
    p = LAWSUIT_BASE
    if productive_hours:
        avg = sum(productive_hours) / len(productive_hours)
        if avg > LAWSUIT_HOURS_THRESHOLD:
            p += 0.015 + 0.004 * (avg - LAWSUIT_HOURS_THRESHOLD)
    for t in pj_tenures:
        p += LAWSUIT_PJ * (1 + min(max(t, 0), 36) / 36)
    return min(LAWSUIT_CAP, p)


def lawsuit_profile(db: Session, c: Company, ref: date) -> dict:
    """Quem pesa no risco: jornada média dos produtivos, PJ com tempo de casa e o multiplicador de valor da causa."""
    seg = rules.SEGMENTS[c.segment]
    staff = _active_staff(db, c)
    productive = [e for e in staff if any(r.key == e.role and r.units > 0 for r in seg.roles)]
    pj = [e for e in staff if e.regime == EmployeeRegime.PJ]
    hours = [e.hours_week for e in productive]
    avg = sum(hours) / len(hours) if hours else 0.0
    tenures = [_months(e.hired_on, ref) for e in pj]
    claim = 1.0 + 0.5 * (len(pj) / len(staff) if staff else 0.0) + (0.25 if avg > LAWSUIT_HOURS_THRESHOLD else 0.0)
    return {"staff": staff, "pj": pj, "avg_hours": avg, "pj_tenures": tenures, "claim_mult": round(claim, 3), "hours": hours}


def lawsuit_prob(db: Session, c: Company, ref: date) -> float:
    prof = lawsuit_profile(db, c, ref)
    return lawsuit_prob_values(productive_hours=prof["hours"], pj_tenures=prof["pj_tenures"], has_staff=bool(prof["staff"]))


def breakage_prob_values(*, capacity_boost: float, overtime: bool, shielded: bool) -> float:
    if shielded:
        return 0.0
    return BREAKAGE_BASE * (1 + min(0.5, 0.25 * float(capacity_boost))) * (1.25 if overtime else 1.0)


def breakage_prob(db: Session, c: Company, ref: date) -> float:
    seg = rules.SEGMENTS[c.segment]
    shielded = c.incident_shield_until is not None and ref <= c.incident_shield_until
    overtime = any(e.hours_week > 44 and any(r.key == e.role and r.units > 0 for r in seg.roles) for e in _active_staff(db, c))
    return breakage_prob_values(capacity_boost=float(c.capacity_boost), overtime=overtime, shielded=shielded)


def breakage_base_cost(c: Company) -> Decimal:
    """Custo de referência do conserto (médio): proporcional ao custo de estruturação do porte."""
    seg = rules.SEGMENTS[c.segment]
    return quantize_money(rules.setup_cost(seg, c.size, c.channel) * BREAKAGE_SETUP_SHARE)


def expected_monthly_cost(seg: rules.Segment, size, channel, *, rent: Decimal, relevance: float, lease_age: int, payroll: Decimal) -> float:
    """Custo ESPERADO por mês dos imprevistos de uma empresa média (para o balanceamento): despejo (negociar = 3 aluguéis), quebra
    (conserto médio) e processo trabalhista (acordo = 2x a folha real; CLT)."""
    ev = 0.0
    if channel == CompanyChannel.PHYSICAL and rent > 0:
        ev = eviction_prob_values(lease_age_months=lease_age, relevance=relevance, cash_prev=1e9, rent=float(rent)) * float(rent) * 3
    br = breakage_prob_values(capacity_boost=0, overtime=False, shielded=False) * float(rules.setup_cost(seg, size, channel) * BREAKAGE_SETUP_SHARE)
    law = lawsuit_prob_values(productive_hours=[44], pj_tenures=[], has_staff=True) * max(3000.0, float(payroll) * 2.0)
    return ev + br + law


def describe(db: Session, c: Company, key: str, ref: date) -> tuple[str, dict]:
    """Texto do imprevisto e efeitos extras guardados no evento (ex.: multiplicador do valor da causa)."""
    if key == "despejo":
        lease = lease_of(db, c)
        age = _months(lease.start_month, ref) if lease else 0
        return (f"O proprietário de \"{lease.name if lease else 'o ponto'}\" quer o imóvel de volta (aluguel de {lease.monthly_rent if lease else 0}; "
                f"contrato com {age} mês(es)). Como reagir?"), {}
    if key == "processo_trabalhista":
        prof = lawsuit_profile(db, c, ref)
        parts = []
        if prof["pj"]:
            parts.append(f"{len(prof['pj'])} prestador(es) PJ alegam vínculo empregatício")
        if prof["avg_hours"] > LAWSUIT_HOURS_THRESHOLD:
            parts.append(f"a jornada média de {prof['avg_hours']:.0f} h/semana passou do limite")
        why = " e ".join(parts) if parts else "um funcionário pede verbas trabalhistas"
        return f"Processo trabalhista: {why}. Como reagir?", {"claim_mult": prof["claim_mult"]}
    if key == "equipamento_quebra":
        what = {"PRODUCTION": "um equipamento essencial da produção", "RETAIL": "o sistema de caixa ou a refrigeração",
                "SERVICE": "uma ferramenta/servidor essencial do serviço"}[rules.SEGMENTS[c.segment].metrics_kind.value]
        return f"Quebrou {what}. Conserto médio de referência: {breakage_base_cost(c)}. Como consertar?", {}
    return "", {}
