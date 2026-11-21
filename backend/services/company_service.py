"""Empresas: criação, capital, folha, estoque, expansão, locação, empréstimo, lucros e processamento mensal.

Princípios:
  * conta empresarial separada (`FinanceAccount.balance`), mas o MESMO ledger (`post_entry(company_id=...)`);
  * o orçamento pessoal só recebe o que pertence ao usuário (aporte, lucros, pró-labore, aluguel de imóvel pessoal);
  * o processamento mensal roda dentro do fechamento global do mês (mesma transação), uma vez por empresa e mês
    (`company_months` único + chaves de idempotência nos lançamentos).
Nenhuma função aqui faz commit.
"""
import logging
import math
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.core.money import quantize_money
from backend.models import (
    AccountKind, AmortizationSystem, Company, CompanyChannel, SiteMode, CompanyCost, CompanyEvent, CompanyEventType, CompanyLease, CompanyLoan,
    CandidateBlock, CompanyLoanInstallment, CompanyMonth, CompanyPartner, CompanySegment, CompanySize, CompanyStatus, Employee, EmployeeLevel, EmployeeStatus,
    EmployeeRegime, EntryOrigin, FinanceAccount, FlowKind, Frequency, Good, GoodCategory, GoodCost, GoodEvent, GoodEventType, GoodStatus,
    InstallmentStatus, InventoryItem, LeaseKind, LedgerEntry, LoanStatus, Occupancy, Person, RealEstateDetails, SimMonth, WorkSchedule,
)
from backend.services import company_rules as rules
from backend.services import company_team as team
from backend.services import economy_service, partners
from backend.services import finance_ledger, loan_math, wealth_service
from backend.services.budget_service import months_between, require_open, shift_month
from backend.services.finance_ledger import ConflictError, FinanceError, NotFoundError
from backend.services.goods_rules import hash01
from backend.services.goods_service import _category, _cost_due

log = logging.getLogger(__name__)
ZERO = Decimal("0.00")
D = Decimal
CAPITAL_LINES = {"CAPITAL_IN", "LAND", "STOCK_PURCHASE", "EQUIPMENT", "LOAN_IN", "LOAN_PRINCIPAL", "DISTRIBUTION"}


# ------------------------------------------------------------------ acesso e utilidades

def get_company(db: Session, user_id: int, company_id: int, *, lock: bool = False) -> Company:
    q = select(Company).where(Company.id == company_id, Company.user_id == user_id)
    c = db.scalar(q.with_for_update() if lock else q)
    if c is None:
        raise NotFoundError("empresa não encontrada")
    return c


def _active(c: Company) -> None:
    if c.status != CompanyStatus.ACTIVE:
        raise ConflictError("esta empresa está encerrada")


def _event(db: Session, c: Company, ref: date, etype: CompanyEventType, text: str, amount: Decimal | None = None) -> None:
    db.add(CompanyEvent(company_id=c.id, ref_month=ref, type=etype, description=text, amount=amount))
    db.flush()


def cash(db: Session, c: Company) -> Decimal:
    return db.scalar(select(FinanceAccount.balance).where(FinanceAccount.id == c.account_id))


def _post(db: Session, c: Company, ref: date, *, kind: FlowKind, amount: Decimal, desc: str, line: str, key: str,
          overdraft: bool = False) -> LedgerEntry | None:
    """Movimentação NA conta da empresa. `line` define a natureza; linhas de capital não são resultado."""
    if amount <= 0:
        return None
    return finance_ledger.post_entry(
        db, c.user_id, kind=kind, amount=amount, description=desc, ref_month=ref, entry_date=ref, origin=EntryOrigin.COMPANY,
        origin_ref=f"company:{c.id}:{line.lower()}", idempotency_key=key, capital=line in CAPITAL_LINES, company_id=c.id,
        line=line, allow_overdraft=overdraft)


def _post_personal(db: Session, c: Company, ref: date, *, kind: FlowKind, amount: Decimal, desc: str, category: str,
                   key: str, capital: bool) -> LedgerEntry | None:
    """Lado PESSOAL de uma transferência com a empresa (aparece no orçamento pessoal)."""
    if amount <= 0:
        return None
    cat = _category(db, c.user_id, kind, category)
    return finance_ledger.post_entry(
        db, c.user_id, kind=kind, amount=amount, description=desc, ref_month=ref, entry_date=ref, category_id=cat.id,
        origin=EntryOrigin.COMPANY, origin_ref=f"company:{c.id}", idempotency_key=key, capital=capital)


def _replayed(db: Session, key: str) -> bool:
    """A mesma solicitação (mesma chave de idempotência) já foi processada: não repetir nenhum efeito."""
    return db.scalar(select(LedgerEntry.id).where((LedgerEntry.idempotency_key == key) | LedgerEntry.idempotency_key.endswith(f"|{key}", autoescape=True))) is not None


def monthly_obligations(db: Session, c: Company) -> Decimal:
    """Folha + aluguel + custos fixos: o que a empresa paga por mês independentemente das vendas."""
    seg = rules.SEGMENTS[c.segment]
    payroll = sum((employee_cost(e) for e in _employees(db, c)), ZERO) + c.owner_salary
    fixed = sum((x.amount * (c.units if x.scales_with_units else 1) for x in db.scalars(
        select(CompanyCost).where(CompanyCost.company_id == c.id, CompanyCost.active.is_(True)))), ZERO)
    return quantize_money(payroll + fixed + _rent(db, c, seg))


def employee_cost(e: Employee) -> Decimal:
    """Custo mensal REAL do funcionário: CLT = 2x o salário negociado, PJ = 1x."""
    return rules.payroll_cost(e.salary, e.regime)


def _employees(db: Session, c: Company) -> list[Employee]:
    return list(db.scalars(select(Employee).where(Employee.company_id == c.id, Employee.status == EmployeeStatus.ACTIVE)
                           .order_by(Employee.id)))


def _lease(db: Session, c: Company) -> CompanyLease | None:
    return db.scalar(select(CompanyLease).where(CompanyLease.company_id == c.id, CompanyLease.active.is_(True)))


def _rent(db: Session, c: Company, seg: rules.Segment) -> Decimal:
    lease = _lease(db, c)
    extra = rules.default_rent(seg, c.location, c.size) * max(c.units - 1, 0) if c.channel == CompanyChannel.PHYSICAL else ZERO
    return quantize_money((lease.monthly_rent if lease else ZERO) + extra)


# ------------------------------------------------------------------ criação e capital

def create_company(db: Session, user_id: int, month: SimMonth, *, name: str, segment: CompanySegment, size: CompanySize,
                   extra_capital: Decimal = ZERO, owner_share_pct: Decimal = D(100), channel: CompanyChannel = CompanyChannel.PHYSICAL,
                   location: str | None = None, site_mode: SiteMode | None = None,
                   partner_invite_ids: list[int] | None = None) -> Company:
    """Abre a empresa. A empresa recebe o capital MÍNIMO para abrir (dividido entre dono e sócios conforme a participação)
    mais o capital adicional do dono: o dono paga `participação% × mínimo + adicional`, cada sócio paga a sua % do mínimo."""
    require_open(month)
    invites = partners.usable_invites(db, user_id, month, partner_invite_ids or []) if partner_invite_ids else []
    if invites:
        if owner_share_pct != D(100):
            raise FinanceError("com sócios convidados a participação do dono é calculada: deixe em 100%")
        owner_share_pct = partners.owner_share(invites)
    name = name.strip()
    if not name:
        raise FinanceError("informe o nome da empresa")
    if not D(0) < owner_share_pct <= D(100):
        raise FinanceError("a participação societária deve ficar entre 0 e 100%")
    seg = rules.SEGMENTS[segment]
    try:
        location, site_mode = rules.validate_site(seg, channel, location, site_mode)
    except ValueError as e:
        raise FinanceError(str(e)) from None
    extra = quantize_money(extra_capital)
    if extra < 0:
        raise FinanceError("o capital adicional não pode ser negativo")
    if db.scalar(select(Company.id).where(Company.user_id == user_id, Company.name == name)):
        raise ConflictError("você já tem uma empresa com esse nome")
    minimum = rules.minimum_capital(seg, location, size, channel, site_mode)
    land = rules.land_value(seg, channel, site_mode, location, size)
    ref = month.ref_month
    parts = partners.contributions(invites, minimum) if invites else []
    for inv, amount in parts:                                               # aporte de cada sócio sai do patrimônio DELE(A)
        person = db.get(Person, inv.person_id)
        if person.assets < amount:
            raise FinanceError(f"{person.name} não tem {amount} para aportar: reduza o capital ou a participação")
    owner_part = quantize_money(minimum * owner_share_pct / 100)
    account = FinanceAccount(user_id=user_id, kind=AccountKind.BUSINESS, name=f"Conta empresarial — {name}"[:80], balance=ZERO)
    db.add(account)
    db.flush()
    c = Company(user_id=user_id, account_id=account.id, name=name, segment=segment, channel=channel, site_mode=site_mode,
                site_value=land, location=location, size=size, price=seg.price, owner_share_pct=owner_share_pct, founded_on=ref)
    db.add(c)
    db.flush()
    where = "online" if channel == CompanyChannel.ONLINE else rules.resolve_location(seg, location).label
    _event(db, c, ref, CompanyEventType.CREATED, f"Empresa criada: {seg.label}, {rules.SIZES[size].label}, {where}")
    transfer_in(db, c, ref, owner_part + extra, key=f"company:{c.id}:capital:initial")
    for inv, amount in parts:
        person = db.get(Person, inv.person_id)
        person.assets -= amount
        db.add(CompanyPartner(company_id=c.id, person_id=person.id, share_pct=inv.share_pct, contribution=amount, joined_month=ref))
        inv.used = True
        _post(db, c, ref, kind=FlowKind.INCOME, amount=amount, desc=f"Aporte do sócio {person.name}", line="CAPITAL_IN",
              key=f"company:{c.id}:capital:partner:{person.id}")
        _event(db, c, ref, CompanyEventType.CAPITAL, f"Sócio {person.name} entrou com {amount} ({inv.share_pct}%)", amount)
    _event(db, c, ref, CompanyEventType.CAPITAL, "Capital inicial integralizado", owner_part + extra + sum((a for _, a in parts), ZERO))
    _post(db, c, ref, kind=FlowKind.EXPENSE, amount=rules.setup_cost(seg, size, channel), desc="Estruturação do negócio (reforma, licenças e abertura)",
          line="SETUP", key=f"co:{c.id}:setup")
    if land > 0:                                                            # terreno comprado: sai do caixa, vira ativo (patrimônio)
        _post(db, c, ref, kind=FlowKind.EXPENSE, amount=land, desc=f"Compra do terreno — {where}", line="LAND", key=f"co:{c.id}:land")
    for kind, label, amount in seg.fixed:
        db.add(CompanyCost(company_id=c.id, kind=kind, name=label, amount=quantize_money(amount * rules.cost_scale(size, channel, seg))))
    if channel == CompanyChannel.PHYSICAL and site_mode == SiteMode.RENT:
        db.add(CompanyLease(company_id=c.id, kind=LeaseKind.EXTERNAL, name=f"Ponto comercial — {where}",
                            monthly_rent=rules.default_rent(seg, location, size), start_month=ref))
    for stock, qty in rules.initial_stock_quantities(seg, location, size):
        item = InventoryItem(company_id=c.id, name=stock.name, unit=stock.unit, quantity=qty, unit_cost=stock.unit_cost,
                             supplier=stock.supplier, min_quantity=(qty * D("0.5")).quantize(D("0.001")),
                             units_per_sale=stock.units_per_sale, waste_pct=stock.waste_pct)
        db.add(item)
        db.flush()
        _post(db, c, ref, kind=FlowKind.EXPENSE, amount=quantize_money(qty * stock.unit_cost), desc=f"Estoque inicial: {stock.name}",
              line="STOCK_PURCHASE", key=f"co:{c.id}:stock:init:{item.id}")
    db.flush()
    log.info("empresa criada id=%s user=%s segmento=%s canal=%s", c.id, user_id, segment, channel)
    return c


def transfer_in(db: Session, c: Company, ref: date, amount: Decimal, *, key: str) -> None:
    """Aporte: sai da conta pessoal (patrimonial, não é despesa) e entra na conta da empresa (capital, não é receita)."""
    amount = quantize_money(amount)
    if amount <= 0:
        raise FinanceError("o valor do aporte deve ser positivo")
    _post_personal(db, c, ref, kind=FlowKind.EXPENSE, amount=amount, desc=f"Aporte de capital: {c.name}",
                   category="Aportes em empresas", key=f"{key}:personal", capital=True)
    _post(db, c, ref, kind=FlowKind.INCOME, amount=amount, desc="Aporte de capital do sócio", line="CAPITAL_IN", key=f"{key}:company")


def contribute(db: Session, user_id: int, month: SimMonth, company_id: int, amount: Decimal, key: str) -> Company:
    require_open(month)
    c = get_company(db, user_id, company_id, lock=True)
    _active(c)
    if _replayed(db, f"company:{c.id}:capital:{key}:personal"):
        return c
    transfer_in(db, c, month.ref_month, amount, key=f"company:{c.id}:capital:{key}")
    _event(db, c, month.ref_month, CompanyEventType.CAPITAL, "Aporte de capital", quantize_money(amount))
    return c


# ------------------------------------------------------------------ lucros e retiradas

def distributable_profit(db: Session, c: Company) -> Decimal:
    net = db.scalar(select(func.coalesce(func.sum(CompanyMonth.net_result), 0)).where(
        CompanyMonth.company_id == c.id))
    paid = db.scalar(select(func.coalesce(func.sum(LedgerEntry.amount), 0)).where(
        LedgerEntry.company_id == c.id, LedgerEntry.line == "DISTRIBUTION"))
    return max(quantize_money(net - paid), ZERO)


def distribute(db: Session, user_id: int, month: SimMonth, company_id: int, amount: Decimal, key: str) -> Company:
    """Distribuição de lucros: só do lucro acumulado ainda não distribuído e só com caixa positivo."""
    require_open(month)
    c = get_company(db, user_id, company_id, lock=True)
    _active(c)
    amount = quantize_money(amount)
    if amount <= 0:
        raise FinanceError("o valor da distribuição deve ser positivo")
    if _replayed(db, f"company:{c.id}:distribution:{key}:company"):
        return c
    available = distributable_profit(db, c)
    balance = cash(db, c)
    if amount > available:
        raise FinanceError(f"valor acima do lucro distribuível: {available}")
    if amount > balance:
        raise FinanceError(f"a empresa não tem caixa suficiente: {balance}")
    ref = month.ref_month
    _post(db, c, ref, kind=FlowKind.EXPENSE, amount=amount, desc="Distribuição de lucros", line="DISTRIBUTION",
          key=f"company:{c.id}:distribution:{key}:company")
    mine = quantize_money(amount * c.owner_share_pct / 100)
    _post_personal(db, c, ref, kind=FlowKind.INCOME, amount=mine, desc=f"Distribuição de lucros: {c.name}",
                   category="Distribuição de lucros", key=f"company:{c.id}:distribution:{key}:personal", capital=False)
    _event(db, c, ref, CompanyEventType.DISTRIBUTION, f"Distribuídos {amount} (sua parte: {mine})", amount)
    return c


# ------------------------------------------------------------------ pessoas

def runway(db: Session, c: Company, cash_now: Decimal | None = None) -> Decimal | None:
    obligations = monthly_obligations(db, c)
    if obligations <= 0:
        return None
    return quantize_money((cash(db, c) if cash_now is None else cash_now) / obligations)


def _seed(db: Session, user_id: int) -> int:
    g = economy_service.get_game(db, user_id, create=False)
    return g.seed if g is not None else user_id


def _role(seg: rules.Segment, role_key: str) -> rules.Role:
    try:
        return seg.role(role_key)
    except KeyError:
        raise FinanceError("cargo inexistente neste segmento") from None


def _blocked(db: Session, c: Company) -> set[str]:
    return set(db.scalars(select(CandidateBlock.candidate_id).where(CandidateBlock.company_id == c.id)))


def list_candidates(db: Session, user_id: int, month: SimMonth, company_id: int, role_key: str,
                    regime: EmployeeRegime) -> list[team.Candidate]:
    """Candidatos do mês para o cargo/regime (determinísticos). Quem recusou a proposta ou já foi contratado some da lista."""
    require_open(month)
    c = get_company(db, user_id, company_id)
    _active(c)
    role = _role(rules.SEGMENTS[c.segment], role_key)
    blocked = _blocked(db, c)
    return [x for x in team.candidates_for(_seed(db, user_id), c.id, month.ref_month, role, regime) if x.id not in blocked]


def _block(db: Session, c: Company, cand: team.Candidate, ref: date, reason: str) -> None:
    db.add(CandidateBlock(company_id=c.id, candidate_id=cand.id, ref_month=ref, reason=reason))
    db.flush()


@dataclass
class HireResult:
    status: str                         # ACCEPTED | COUNTER | REFUSED
    message: str
    counter_offer: Decimal | None = None

    @property
    def accepted(self) -> bool:
        return self.status == "ACCEPTED"


def hire(db: Session, user_id: int, month: SimMonth, company_id: int, *, candidate_id: str, salary: Decimal, hours_week: int,
         schedule: WorkSchedule, regime: EmployeeRegime, confirm_risk: bool = False, idempotency_key: str) -> HireResult:
    """Proposta a um candidato. O candidato é RECALCULADO no servidor a partir do id (pretensão, nível e escolaridade nunca vêm
    do cliente). Recusa bloqueia o candidato no mês (repetir não muda nada); contraproposta não bloqueia."""
    require_open(month)
    c = get_company(db, user_id, company_id, lock=True)
    _active(c)
    seg = rules.SEGMENTS[c.segment]
    ref = month.ref_month
    try:
        cand = team.resolve_token(_seed(db, user_id), c.id, ref, candidate_id, seg)
    except ValueError as e:
        raise FinanceError(str(e)) from None
    if cand.regime != regime:
        raise FinanceError("o regime informado não é o do candidato")
    salary = quantize_money(salary)
    if salary <= 0 or not team.MIN_WEEK <= hours_week <= team.MAX_WEEK:
        raise FinanceError(f"informe salário positivo e jornada entre {team.MIN_WEEK} e {team.MAX_WEEK} horas por semana")
    hire_key = f"co:{c.id}:hire:{idempotency_key}"
    if _replayed(db, hire_key):
        return HireResult("ACCEPTED", f"{cand.name}: contratação já registrada.")
    if cand.id in _blocked(db, c):
        return HireResult("REFUSED", f"{cand.name} não está mais disponível neste mês.")
    offer = team.evaluate_offer(cand, salary, hours_week, schedule)
    if offer.status == "REFUSED":
        _block(db, c, cand, ref, "REFUSED")
        return HireResult("REFUSED", offer.message)
    if offer.status == "COUNTER":
        return HireResult("COUNTER", offer.message, offer.counter_offer)
    role = _role(seg, cand.role)
    cost = quantize_money(salary * rules.HIRING_COST_MONTHS)
    balance = cash(db, c)
    if balance < cost:
        raise FinanceError(f"a empresa não tem caixa para o custo de contratação ({cost}); caixa atual: {balance}")
    after = balance - cost
    obligations = monthly_obligations(db, c) + rules.payroll_cost(salary, regime)
    months_cover = after / obligations if obligations > 0 else D(99)
    if months_cover < 2 and not confirm_risk:
        raise ConflictError(
            f"RISCO: após contratar, o caixa cobre apenas {months_cover:.1f} mês(es) de custos fixos e folha "
            f"(novo custo mensal total {quantize_money(obligations)}). Confirme explicitamente para contratar assim mesmo.")
    _post(db, c, ref, kind=FlowKind.EXPENSE, amount=cost, desc=f"Custo de contratação: {role.label} ({cand.name})", line="HIRING", key=hire_key)
    e = Employee(company_id=c.id, role=role.key, level=cand.level, salary=salary, hours_week=hours_week, productivity=cand.productivity,
                 hired_on=ref, name=cand.name, regime=regime, schedule=schedule, education=cand.education,
                 experience_years=cand.experience_years)
    db.add(e)
    _block(db, c, cand, ref, "HIRED")
    _event(db, c, ref, CompanyEventType.HIRE,
           f"Contratado: {cand.name}, {role.label} ({cand.level.value}, {regime.value}, {schedule.value}), salário {salary}", salary)
    return HireResult("ACCEPTED", offer.message)


def headhunter(db: Session, user_id: int, month: SimMonth, company_id: int, *, role_key: str, regime: EmployeeRegime,
               max_salary: Decimal, min_level: EmployeeLevel, idempotency_key: str) -> tuple[list[team.Candidate], Decimal]:
    """Briefing -> até 3 candidatos que cumprem o briefing. Honorário = 1x o salário-teto; se nenhum servir, metade do honorário.
    Idempotente: a mesma chave não cobra de novo (a lista é determinística)."""
    require_open(month)
    c = get_company(db, user_id, company_id, lock=True)
    _active(c)
    role = _role(rules.SEGMENTS[c.segment], role_key)
    max_salary = quantize_money(max_salary)
    if max_salary <= 0:
        raise FinanceError("informe o salário máximo do briefing")
    blocked = _blocked(db, c)
    found = [x for x in team.headhunter_search(_seed(db, user_id), c.id, month.ref_month, role, regime, max_salary, min_level)
             if x.id not in blocked]
    fee = quantize_money(max_salary * team.HEADHUNTER_FEE_MONTHS * (1 if found else team.HEADHUNTER_EMPTY_FEE_FACTOR))
    key = f"co:{c.id}:hh:{idempotency_key}"
    if _replayed(db, key):
        return found, fee
    balance = cash(db, c)
    if balance < fee:
        raise FinanceError(f"a empresa não tem caixa para o honorário do headhunter ({fee}); caixa atual: {balance}")
    _post(db, c, month.ref_month, kind=FlowKind.EXPENSE, amount=fee, desc=f"Honorário do headhunter: {role.label}", line="HIRING", key=key)
    _event(db, c, month.ref_month, CompanyEventType.HIRE,
           f"Headhunter contratado para {role.label} ({regime.value}, até {max_salary}): "
           + (f"{len(found)} candidato(s)" if found else "nenhum candidato serviu ao briefing (honorário pela metade)"), fee)
    return found, fee


def _next_key(db: Session, c: Company) -> int:
    return db.scalar(select(func.count()).select_from(CompanyEvent).where(CompanyEvent.company_id == c.id)) + 1


def fire(db: Session, user_id: int, month: SimMonth, company_id: int, employee_id: int) -> Employee:
    require_open(month)
    c = get_company(db, user_id, company_id, lock=True)
    _active(c)
    e = db.get(Employee, employee_id)
    if e is None or e.company_id != c.id:
        raise NotFoundError("funcionário não encontrado")
    if e.status != EmployeeStatus.ACTIVE:
        raise ConflictError("funcionário já desligado")
    ref = month.ref_month
    tenure = team.tenure_months(e.hired_on, ref)
    severance = team.severance(e.regime, e.salary, tenure)
    _post(db, c, ref, kind=FlowKind.EXPENSE, amount=severance, desc=f"Rescisão ({e.regime.value}): {e.name or e.role}", line="SEVERANCE",
          key=f"co:{c.id}:fire:{e.id}", overdraft=True)
    e.status = EmployeeStatus.TERMINATED
    e.terminated_on = ref
    _event(db, c, ref, CompanyEventType.FIRE,
           f"Desligado: {e.name or e.role} ({e.regime.value}), rescisão {severance}" if severance > 0
           else f"Desligado: {e.name or e.role} ({e.regime.value}), sem rescisão", severance)
    p = team.lawsuit_probability(e.regime, e.hours_week, e.schedule, tenure)
    if hash01(_seed(db, user_id), "lawsuit", c.id, e.id, f"{ref:%Y-%m}") < p:
        who = e.name or e.role
        ev = economy_service.spawn_company_event(
            db, c, "processo_trabalhista", shift_month(ref, 1),
            f"{who} ({e.regime.value}, {e.hours_week} h/semana, escala {e.schedule.value}) entrou com um processo trabalhista "
            f"{'alegando vínculo empregatício' if e.regime == EmployeeRegime.PJ else 'pedindo verbas'}. Como reagir?")
        if ev is not None:
            _event(db, c, ref, CompanyEventType.FIRE, f"Processo trabalhista a caminho: {who} vai processar a empresa (decisão no mês seguinte)")
    return e


def compliance(db: Session, c: Company) -> dict:
    """Situação dos cargos obrigatórios: quais existem, quais faltam e a multa que seria aplicada no fechamento."""
    seg = rules.SEGMENTS[c.segment]
    active = {e.role for e in _employees(db, c)}
    required = rules.mandatory_roles(c.channel)
    missing = rules.missing_mandatory(c.channel, active)
    return {"regular": not missing,
            "required": [{"role": r, "label": seg.role(r).label, "present": r in active} for r in required],
            "missing": missing, "missing_labels": [seg.role(r).label for r in missing],
            "estimated_fine": rules.compliance_fine(seg, missing)}


# ------------------------------------------------------------------ estoque

def supplier_cost(item: InventoryItem, ref: date, mult: Decimal = D(1)) -> Decimal:
    """Preço do fornecedor no mês: custo de referência ± 3% (determinístico)."""
    seg_cost = None
    for seg in rules.SEGMENTS.values():
        for s in seg.stock:
            if s.name == item.name:
                seg_cost = s.unit_cost
                break
    base = seg_cost or item.unit_cost
    return (base * mult * (1 + D(str((hash01("supplier", item.id, ref.isoformat()) - 0.5) * 0.06)))).quantize(D("0.0001"))


def _buy_stock(db: Session, c: Company, item: InventoryItem, qty: Decimal, ref: date, key: str, seg: rules.Segment) -> Decimal:
    qty = qty.quantize(D("0.001")) if seg.fractional else D(math.ceil(qty))
    if qty <= 0:
        return ZERO
    price = supplier_cost(item, ref, economy_service.supplier_mult(db, c, ref))
    total = quantize_money(qty * price)
    _post(db, c, ref, kind=FlowKind.EXPENSE, amount=total, desc=f"Compra de estoque: {item.name} ({qty} {item.unit})",
          line="STOCK_PURCHASE", key=key)
    new_qty = item.quantity + qty
    item.unit_cost = ((item.quantity * item.unit_cost + qty * price) / new_qty).quantize(D("0.0001"))
    item.quantity = new_qty
    return total


def buy_stock(db: Session, user_id: int, month: SimMonth, company_id: int, item_id: int, quantity: Decimal, key: str) -> InventoryItem:
    require_open(month)
    c = get_company(db, user_id, company_id, lock=True)
    _active(c)
    item = db.get(InventoryItem, item_id)
    if item is None or item.company_id != c.id:
        raise NotFoundError("item de estoque não encontrado")
    if quantity <= 0:
        raise FinanceError("a quantidade deve ser positiva")
    if _replayed(db, f"company:{c.id}:stock:{key}"):
        return item
    seg = rules.SEGMENTS[c.segment]
    total = _buy_stock(db, c, item, D(quantity), month.ref_month, f"company:{c.id}:stock:{key}", seg)
    _event(db, c, month.ref_month, CompanyEventType.STOCK, f"Compra de {item.name}: {quantity} {item.unit}", total)
    return item


# ------------------------------------------------------------------ preço, configurações, expansão, locação, empréstimo

def update_settings(db: Session, user_id: int, month: SimMonth, company_id: int, *, price: Decimal | None = None,
                    owner_salary: Decimal | None = None, auto_restock: bool | None = None) -> Company:
    c = get_company(db, user_id, company_id, lock=True)
    _active(c)
    if price is not None:
        if price <= 0:
            raise FinanceError("o preço deve ser positivo")
        c.price = quantize_money(price)
    if owner_salary is not None:
        if owner_salary < 0:
            raise FinanceError("o pró-labore não pode ser negativo")
        c.owner_salary = quantize_money(owner_salary)
    if auto_restock is not None:
        c.auto_restock = auto_restock
    _event(db, c, month.ref_month, CompanyEventType.SETTINGS, f"Preço {c.price}, pró-labore {c.owner_salary}, reposição automática {c.auto_restock}")
    return c


def expand(db: Session, user_id: int, month: SimMonth, company_id: int, kind: str) -> Company:
    require_open(month)
    c = get_company(db, user_id, company_id, lock=True)
    _active(c)
    seg = rules.SEGMENTS[c.segment]
    ref = month.ref_month
    if kind == "CAPACITY" and c.capacity_level >= rules.MAX_CAPACITY_LEVEL:
        raise ConflictError("a capacidade já está no nível máximo")
    if kind == "NEW_UNIT" and c.units >= rules.MAX_UNITS:
        raise ConflictError("número máximo de unidades atingido")
    if kind == "LARGER_PREMISES" and c.size == CompanySize.LARGE:
        raise ConflictError("a empresa já está no maior porte")
    if kind not in ("CAPACITY", "NEW_UNIT", "LARGER_PREMISES", "MARKETING"):
        raise FinanceError("tipo de expansão inválido")
    cost = rules.expansion_cost(seg, kind, c.size, c.units)
    if cash(db, c) < cost:
        raise FinanceError(f"a empresa não tem caixa para esta expansão ({cost}); caixa atual: {cash(db, c)}")
    n = _next_key(db, c)
    if kind == "MARKETING":
        _post(db, c, ref, kind=FlowKind.EXPENSE, amount=cost, desc="Campanha de marketing", line="MARKETING", key=f"co:{c.id}:exp:{n}")
        c.marketing_until = shift_month(ref, rules.MARKETING_MONTHS - 1)
        text = f"Campanha de publicidade até {c.marketing_until:%m/%Y}"
    else:
        _post(db, c, ref, kind=FlowKind.EXPENSE, amount=cost, desc=f"Expansão: {kind}", line="EXPANSION", key=f"co:{c.id}:exp:{n}")
        if kind == "CAPACITY":
            c.capacity_level += 1
            text = f"Capacidade ampliada (nível {c.capacity_level})"
        elif kind == "NEW_UNIT":
            c.units += 1
            text = f"Nova unidade aberta (total: {c.units})"
        else:
            old, new = c.size, rules.SIZE_ORDER[rules.SIZE_ORDER.index(c.size) + 1]
            ratio = rules.SIZES[new].fixed / rules.SIZES[old].fixed
            for cost_row in db.scalars(select(CompanyCost).where(CompanyCost.company_id == c.id)):
                cost_row.amount = quantize_money(cost_row.amount * ratio)
            lease = _lease(db, c)
            if lease and lease.kind == LeaseKind.EXTERNAL:
                lease.monthly_rent = rules.default_rent(seg, c.location, new)
            c.size = new
            text = f"Mudança para instalações maiores: porte {rules.SIZES[new].label}"
    _event(db, c, ref, CompanyEventType.EXPANSION, text, cost)
    return c


def set_lease(db: Session, user_id: int, month: SimMonth, company_id: int, kind: LeaseKind, *, good_id: int | None = None,
              monthly_rent: Decimal | None = None, name: str | None = None) -> CompanyLease:
    require_open(month)
    c = get_company(db, user_id, company_id, lock=True)
    _active(c)
    seg = rules.SEGMENTS[c.segment]
    ref = month.ref_month
    if c.channel == CompanyChannel.ONLINE:
        raise ConflictError("empresa online não tem ponto físico nem aluguel")
    if c.site_mode == SiteMode.BUY:
        raise ConflictError("o terreno desta empresa é próprio (comprado na abertura): não há aluguel a contratar")
    current = _lease(db, c)
    if current:
        current.active = False
        current.end_month = ref
        if current.good_id:
            g = db.get(Good, current.good_id)
            det = db.get(RealEstateDetails, g.id) if g else None
            if det and det.occupancy == Occupancy.COMPANY_USE:
                det.occupancy = Occupancy.VACANT
                det.monthly_rent = ZERO
            if g:
                db.add(GoodEvent(good_id=g.id, user_id=user_id, ref_month=ref, type=GoodEventType.OCCUPANCY,
                                 description=f"Contrato com a empresa {c.name} encerrado"))
        db.flush()
    if kind == LeaseKind.EXTERNAL:
        rent = quantize_money(monthly_rent) if monthly_rent is not None else rules.default_rent(seg, c.location, c.size)
        if rent < 0:
            raise FinanceError("aluguel inválido")
        lease = CompanyLease(company_id=c.id, kind=kind, name=(name or f"Ponto comercial — {rules.resolve_location(seg, c.location).label}")[:120],
                             monthly_rent=rent, start_month=ref)
    else:
        if good_id is None:
            raise FinanceError("informe o imóvel")
        g = db.scalar(select(Good).where(Good.id == good_id, Good.user_id == user_id).with_for_update())
        if g is None:
            raise NotFoundError("imóvel não encontrado")
        det = db.get(RealEstateDetails, g.id)
        if g.status != GoodStatus.ACTIVE or det is None or g.category == GoodCategory.LAND:
            raise FinanceError("o imóvel precisa estar ativo e ser uma casa, apartamento ou imóvel comercial")
        if db.scalar(select(CompanyLease.id).where(CompanyLease.good_id == g.id, CompanyLease.active.is_(True))):
            raise ConflictError("este imóvel já é usado por uma empresa")
        personal = finance_ledger.personal_account(db, user_id)
        if kind == LeaseKind.OWN_GOOD:
            if g.owner_account_id != personal.id:
                raise FinanceError("este imóvel pertence a uma empresa")
            if det.occupancy not in (Occupancy.VACANT, Occupancy.LISTED_FOR_RENT):
                raise ConflictError("o imóvel está ocupado (moradia própria ou alugado a terceiros)")
            rent = quantize_money(monthly_rent) if monthly_rent is not None else rules.default_rent(seg, c.location, c.size)
        else:
            if g.owner_account_id != c.account_id:
                raise FinanceError("este imóvel não pertence à empresa")
            if det.occupancy != Occupancy.VACANT:
                raise ConflictError("o imóvel está ocupado")
            rent = ZERO
        det.occupancy = Occupancy.COMPANY_USE
        det.monthly_rent = rent if kind == LeaseKind.OWN_GOOD else ZERO
        db.add(GoodEvent(good_id=g.id, user_id=user_id, ref_month=ref, type=GoodEventType.OCCUPANCY,
                         description=f"Cedido à empresa {c.name}" + (f" por {rent}/mês" if rent else "")))
        lease = CompanyLease(company_id=c.id, kind=kind, good_id=g.id, name=g.name[:120], monthly_rent=rent, start_month=ref)
    db.add(lease)
    db.flush()
    _event(db, c, ref, CompanyEventType.LEASE, f"Instalações: {lease.name} ({kind.value}), aluguel {lease.monthly_rent}", lease.monthly_rent)
    return lease


def loan_limit(db: Session, c: Company) -> Decimal:
    owed = db.scalar(select(func.coalesce(func.sum(CompanyLoan.balance), 0)).where(
        CompanyLoan.company_id == c.id, CompanyLoan.status == LoanStatus.ACTIVE))
    cap = max(D(50000), 2 * wealth_service.company_equity(db, c))
    return max(quantize_money(cap - owed), ZERO)


def take_loan(db: Session, user_id: int, month: SimMonth, company_id: int, amount: Decimal, term_months: int) -> CompanyLoan:
    require_open(month)
    c = get_company(db, user_id, company_id, lock=True)
    _active(c)
    amount = quantize_money(amount)
    if amount <= 0 or not 1 <= term_months <= rules.LOAN_MAX_TERM:
        raise FinanceError(f"informe valor positivo e prazo entre 1 e {rules.LOAN_MAX_TERM} meses")
    limit = loan_limit(db, c)
    if amount > limit:
        raise FinanceError(f"valor acima do limite de crédito da empresa: {limit}")
    ref = month.ref_month
    rate = rules.LOAN_ANNUAL_RATE + economy_service.financing_rate_add(db, c.user_id, ref)
    loan = CompanyLoan(company_id=c.id, principal=amount, annual_rate_pct=rate, term_months=term_months,
                       system=AmortizationSystem.PRICE, start_month=ref, balance=amount)
    db.add(loan)
    db.flush()
    for r in loan_math.schedule(amount, rate, term_months, AmortizationSystem.PRICE):
        db.add(CompanyLoanInstallment(loan_id=loan.id, number=r.number, due_month=shift_month(ref, r.number), payment=r.payment,
                                      interest=r.interest, amortization=r.amortization, balance_after=r.balance_after))
    _post(db, c, ref, kind=FlowKind.INCOME, amount=amount, desc=f"Empréstimo bancário ({term_months}x)", line="LOAN_IN",
          key=f"co:{c.id}:loan:{loan.id}")
    _event(db, c, ref, CompanyEventType.LOAN, f"Empréstimo de {amount} em {term_months} meses a {rate}% a.a.", amount)
    return loan


# ------------------------------------------------------------------ processamento mensal (dentro do fechamento global)

def _equipment_factor(db: Session, c: Company) -> float:
    goods = list(db.scalars(select(Good).where(Good.owner_account_id == c.account_id, Good.status == GoodStatus.ACTIVE)))
    eq = sum(1 for g in goods if g.category == GoodCategory.EQUIPMENT)
    veh = sum(1 for g in goods if g.category in (GoodCategory.CAR, GoodCategory.MOTORCYCLE))
    f = 1 + min(0.25, 0.05 * eq)
    if c.segment == CompanySegment.TRANSPORT:
        f += min(0.6, 0.15 * veh)
    return f


def process_month(db: Session, user_id: int, month: SimMonth) -> list[CompanyMonth]:
    """Processa todas as empresas ativas no fechamento do mês. Cada empresa só é processada uma vez por mês."""
    out = []
    for c in db.scalars(select(Company).where(Company.user_id == user_id, Company.status == CompanyStatus.ACTIVE).order_by(Company.id)):
        if db.scalar(select(CompanyMonth.id).where(CompanyMonth.company_id == c.id, CompanyMonth.ref_month == month.ref_month)):
            continue
        out.append(_process_company(db, c, month))
    return out


def _process_company(db: Session, c: Company, month: SimMonth) -> CompanyMonth:
    ref = month.ref_month
    seg = rules.SEGMENTS[c.segment]
    k = f"co:{c.id}:{ref:%Y-%m}"
    staff = _employees(db, c)
    items = list(db.scalars(select(InventoryItem).where(InventoryItem.company_id == c.id).order_by(InventoryItem.id))) \
        if seg.has_stock else []                                        # segmentos de serviço não têm estoque
    opening_cash = cash(db, c)

    # 1) condições do mês (demanda, sazonalidade, campanha)
    marketing = c.marketing_until is not None and ref <= c.marketing_until
    demand = rules.demand_units(seg, location=c.location, size=c.size, units=c.units, reputation=c.reputation, price=c.price,
                                company_id=c.id, ref=ref, marketing=marketing)
    demand *= economy_service.company_demand_mult(db, c, ref)          # economia e eventos (etapa 5)
    capacity = rules.capacity_units(seg, size=c.size, units=c.units, capacity_level=c.capacity_level,
                                    staff=[(e.role, e.productivity) for e in staff], equipment_factor=_equipment_factor(db, c))
    # 2) consumo de estoque limita as vendas
    stock_cap = min((float(i.quantity / (i.units_per_sale * (1 + i.waste_pct / 100))) for i in items), default=math.inf)
    missing = rules.missing_mandatory(c.channel, [e.role for e in staff])          # fase 2: cargos obrigatórios
    irregular = bool(missing)
    potential = 0.0 if irregular else min(demand, capacity)                        # empresa irregular não opera: vendas = 0
    sold = min(potential, stock_cap)
    sold = round(max(sold, 0), 2) if seg.fractional else math.floor(max(sold, 0))
    stockout = bool(items) and stock_cap < potential
    cogs = ZERO
    for i in items:
        used = (D(str(sold)) * i.units_per_sale * (1 + i.waste_pct / 100)).quantize(D("0.001"))
        used = min(used, i.quantity)
        i.quantity -= used
        cogs += used * i.unit_cost
    cogs = quantize_money(cogs)
    # 3) receitas
    revenue = quantize_money(D(str(sold)) * c.price)
    _post(db, c, ref, kind=FlowKind.INCOME, amount=revenue, desc=f"Vendas do mês ({sold} {seg.unit_label})", line="REVENUE", key=f"{k}:revenue", overdraft=True)
    variable = quantize_money(revenue * seg.variable_pct / 100)
    _post(db, c, ref, kind=FlowKind.EXPENSE, amount=variable, desc="Custos variáveis (frete, taxas, comissões)", line="VARIABLE", key=f"{k}:variable", overdraft=True)
    # 4) folha de pagamento (+ pró-labore, que vira receita PESSOAL do usuário)
    payroll = quantize_money(sum((employee_cost(e) for e in staff), ZERO))
    _post(db, c, ref, kind=FlowKind.EXPENSE, amount=payroll, desc=f"Folha de pagamento ({len(staff)} funcionários; CLT 2x, PJ 1x)", line="PAYROLL", key=f"{k}:payroll", overdraft=True)
    fine = rules.compliance_fine(seg, missing) if irregular else ZERO
    if irregular:
        labels = ", ".join(seg.role(r).label for r in missing)
        _post(db, c, ref, kind=FlowKind.EXPENSE, amount=fine, desc=f"Multa por irregularidade (sem {labels})", line="FEES", key=f"{k}:fine", overdraft=True)
        _event(db, c, ref, CompanyEventType.COMPLIANCE,
               f"Empresa irregular: sem {labels}. Vendas zeradas no mês e multa de {fine}", fine)
    if c.owner_salary > 0:
        _post(db, c, ref, kind=FlowKind.EXPENSE, amount=c.owner_salary, desc="Pró-labore do sócio", line="PRO_LABORE", key=f"{k}:prolabore", overdraft=True)
        _post_personal(db, c, ref, kind=FlowKind.INCOME, amount=c.owner_salary, desc=f"Pró-labore: {c.name}",
                       category="Salário", key=f"{k}:prolabore:personal", capital=False)
        payroll += c.owner_salary
    # 5/6) fornecedores (reposição, abaixo) e aluguel/outras despesas fixas
    lease = _lease(db, c)
    rent = _rent(db, c, seg)
    _post(db, c, ref, kind=FlowKind.EXPENSE, amount=rent, desc="Aluguel", line="RENT", key=f"{k}:rent", overdraft=True)
    if lease and lease.kind == LeaseKind.OWN_GOOD and lease.monthly_rent > 0:
        _post_personal(db, c, ref, kind=FlowKind.INCOME, amount=lease.monthly_rent, desc=f"Aluguel recebido de {c.name}",
                       category="Aluguéis recebidos", key=f"{k}:rent:personal", capital=False)
    fixed_costs = quantize_money(sum((x.amount * (c.units if x.scales_with_units else 1) for x in db.scalars(
        select(CompanyCost).where(CompanyCost.company_id == c.id, CompanyCost.active.is_(True)))), ZERO))
    _post(db, c, ref, kind=FlowKind.EXPENSE, amount=fixed_costs, desc="Custos fixos (energia, ferramentas, contabilidade)", line="FIXED", key=f"{k}:fixed", overdraft=True)
    asset_costs = ZERO
    for g in db.scalars(select(Good).where(Good.owner_account_id == c.account_id, Good.status == GoodStatus.ACTIVE)):
        for gc in db.scalars(select(GoodCost).where(GoodCost.good_id == g.id)):
            if _cost_due(gc, ref):
                asset_costs += gc.amount
                _post(db, c, ref, kind=FlowKind.EXPENSE, amount=gc.amount, desc=f"{gc.name} — {g.name}", line="ASSET_COSTS",
                      key=f"{k}:goodcost:{gc.id}", overdraft=True)
    # 7) impostos
    taxes = quantize_money(revenue * seg.tax_pct / 100)
    _post(db, c, ref, kind=FlowKind.EXPENSE, amount=taxes, desc="Impostos sobre a receita", line="TAX", key=f"{k}:tax", overdraft=True)
    # 8) financiamentos (juros = despesa, amortização = redução da dívida) e juros do saldo negativo
    interest = ZERO
    for loan in db.scalars(select(CompanyLoan).where(CompanyLoan.company_id == c.id, CompanyLoan.status == LoanStatus.ACTIVE)):
        for inst in db.scalars(select(CompanyLoanInstallment).where(
                CompanyLoanInstallment.loan_id == loan.id, CompanyLoanInstallment.due_month == ref,
                CompanyLoanInstallment.status == InstallmentStatus.PENDING)):
            _post(db, c, ref, kind=FlowKind.EXPENSE, amount=inst.interest, desc=f"Juros do empréstimo {inst.number}/{loan.term_months}", line="INTEREST", key=f"{k}:loan:{loan.id}:{inst.number}:i", overdraft=True)
            _post(db, c, ref, kind=FlowKind.EXPENSE, amount=inst.amortization, desc=f"Amortização do empréstimo {inst.number}/{loan.term_months}", line="LOAN_PRINCIPAL", key=f"{k}:loan:{loan.id}:{inst.number}:p", overdraft=True)
            interest += inst.interest
            inst.status = InstallmentStatus.PAID
            loan.balance = inst.balance_after
            if inst.number == loan.term_months:
                loan.status = LoanStatus.PAID
    if opening_cash < 0:
        od = quantize_money(-opening_cash * rules.OVERDRAFT_RATE_MONTHLY)
        _post(db, c, ref, kind=FlowKind.EXPENSE, amount=od, desc="Juros do saldo negativo (cheque especial)", line="INTEREST", key=f"{k}:overdraft", overdraft=True)
        interest += od
    # reposição de estoque (pagamento a fornecedores): só com caixa disponível
    if c.auto_restock:
        for i in items:
            need = D(str(max(sold, potential if not math.isinf(potential) else 0) * 1.1)) * i.units_per_sale * (1 + i.waste_pct / 100)
            if i.quantity < max(need * D("0.6"), i.min_quantity):
                price = supplier_cost(i, ref, economy_service.supplier_mult(db, c, ref))
                buy = need - i.quantity
                affordable = (max(cash(db, c), ZERO) * D("0.9") / price) if price > 0 else D(0)
                qty = min(buy, affordable)
                if qty >= 1 or (seg.fractional and qty > 0):
                    _buy_stock(db, c, i, qty, ref, f"{k}:restock:{i.id}", seg)
    # 9/10) resultados e patrimônio
    db.flush()                                          # a sessão não faz autoflush: estoque e saldo precisam estar no banco
    oneoff = quantize_money(db.scalar(select(func.coalesce(func.sum(LedgerEntry.amount), 0)).where(
        LedgerEntry.company_id == c.id, LedgerEntry.ref_month == ref, LedgerEntry.kind == FlowKind.EXPENSE,
        LedgerEntry.line.in_(["SETUP", "HIRING", "SEVERANCE", "EXPANSION", "MARKETING", "FEES"]))))
    variable_total = cogs + variable
    fixed_total = quantize_money(rent + fixed_costs + asset_costs + oneoff)
    operating = quantize_money(revenue - variable_total - fixed_total - payroll)
    net = quantize_money(operating - taxes - interest)
    balance = cash(db, c)
    loans = db.scalar(select(func.coalesce(func.sum(CompanyLoan.balance), 0)).where(
        CompanyLoan.company_id == c.id, CompanyLoan.status == LoanStatus.ACTIVE))
    served = sold >= math.floor(min(demand, capacity)) and not stockout
    c.reputation = max(5, min(100, c.reputation + (2 if served else -4 if stockout or irregular else -1)))
    equity = wealth_service.company_equity(db, c)
    row = CompanyMonth(company_id=c.id, ref_month=ref, demand_units=D(str(round(demand, 2))), capacity_units=D(str(round(capacity, 2))),
                       units_sold=D(str(sold)), stockout=stockout, revenue=revenue, variable_costs=variable_total,
                       fixed_costs=fixed_total, payroll=payroll, taxes=taxes, interest=quantize_money(interest),
                       operating_result=operating, net_result=net, cash_end=balance,
                       debts_end=quantize_money(loans + max(-balance, ZERO)), equity_end=equity, reputation_end=c.reputation,
                       irregular=irregular, fines=fine)
    db.add(row)
    c.last_processed_month = ref
    _event(db, c, ref, CompanyEventType.MONTH, f"Mês fechado: receita {revenue}, resultado líquido {net}", net)
    db.flush()
    return row


# ------------------------------------------------------------------ consultas agregadas

def user_companies(db: Session, user_id: int) -> list[Company]:
    return list(db.scalars(select(Company).where(Company.user_id == user_id).order_by(Company.id)))
