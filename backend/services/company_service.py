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
    InstallmentStatus, InventoryItem, CompanyAide, CompanyRecruiter, CompanySupplier, CompanyUnit, LeaseKind, LedgerEntry, LoanStatus, Occupancy, Person, RealEstateDetails, SimMonth, WorkSchedule,
)
from backend.services import company_aides as aides
from backend.services import country_rules as cr
from backend.services import world_service as ws
from backend.services import company_world as cw
from backend.services import company_recruiter as recruiter
from backend.services import company_rules as rules
from backend.services import company_supply as supply
from backend.services import company_taxes
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
CAPITAL_LINES = {"CAPITAL_IN", "LAND", "STOCK_PURCHASE", "EQUIPMENT", "LOAN_IN", "LOAN_PRINCIPAL", "DISTRIBUTION", "ACQUISITION"}


# ------------------------------------------------------------------ acesso e utilidades

def get_company(db: Session, user_id: int, company_id: int, *, lock: bool = False) -> Company:
    q = select(Company).where(Company.id == company_id, Company.user_id == user_id)
    c = db.scalar(q.with_for_update() if lock else q)
    if c is None:
        raise NotFoundError("empresa não encontrada")
    return c


def _opening(c: Company, ref: date) -> bool:
    """Empresa ainda em abertura/obra no mês `ref` (não vende nem franqueia)."""
    return c.opens_month is not None and ref < c.opens_month


def _active(c: Company) -> None:
    if c.status != CompanyStatus.ACTIVE:
        raise ConflictError("esta empresa está encerrada")


def _event(db: Session, c: Company, ref: date, etype: CompanyEventType, text: str, amount: Decimal | None = None) -> None:
    db.add(CompanyEvent(company_id=c.id, ref_month=ref, type=etype, description=text, amount=amount))
    db.flush()


def cash(db: Session, c: Company) -> Decimal:
    return db.scalar(select(FinanceAccount.balance).where(FinanceAccount.id == c.account_id))


def _post(db: Session, c: Company, ref: date, *, kind: FlowKind, amount: Decimal, desc: str, line: str, key: str,
          overdraft: bool = False, origin_ref: str | None = None) -> LedgerEntry | None:
    """Movimentação NA conta da empresa. `line` define a natureza; linhas de capital não são resultado.
    `origin_ref` padrão: company:{id}:{linha}; compras de fornecedor usam company:{id}:supplier:{contrato}."""
    if amount <= 0:
        return None
    return finance_ledger.post_entry(
        db, c.user_id, kind=kind, amount=amount, description=desc, ref_month=ref, entry_date=ref, origin=EntryOrigin.COMPANY,
        origin_ref=origin_ref or f"company:{c.id}:{line.lower()}", idempotency_key=key, capital=line in CAPITAL_LINES, company_id=c.id,
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
    ref0 = c.last_processed_month or c.founded_on
    fz = cw.company_factor(db, c, ref0)
    payroll = sum((cw.emp_cost(db, c, e, ref0) for e in _employees(db, c)), ZERO) + c.owner_salary
    fixed = sum((x.amount * (c.units if x.scales_with_units else 1) for x in db.scalars(
        select(CompanyCost).where(CompanyCost.company_id == c.id, CompanyCost.active.is_(True)))), ZERO) * fz
    return quantize_money(payroll + fixed + _rent(db, c, seg) * fz + recruiter_fee(db, c) + aide_fees(db, c) + marketing_budget(db, c))


def active_recruiter(db: Session, c: Company) -> CompanyRecruiter | None:
    return db.scalar(select(CompanyRecruiter).where(CompanyRecruiter.company_id == c.id, CompanyRecruiter.status == "ACTIVE"))


def recruiter_fee(db: Session, c: Company) -> Decimal:
    """Taxa mensal do contratador ativo (0 sem contratador): entra nas obrigações mensais e no runway."""
    r = active_recruiter(db, c)
    return recruiter.monthly_fee(r.tier, c.size) if r is not None else ZERO


def active_aide(db: Session, c: Company, kind: str) -> CompanyAide | None:
    return db.scalar(select(CompanyAide).where(CompanyAide.company_id == c.id, CompanyAide.kind == kind, CompanyAide.status == "ACTIVE"))


def aide_fees(db: Session, c: Company) -> Decimal:
    """Taxas mensais do marketeiro e do gerente ativos (0 sem eles)."""
    return quantize_money(sum((aides.monthly_fee(a.kind, a.level, c.size) for a in db.scalars(select(CompanyAide).where(
        CompanyAide.company_id == c.id, CompanyAide.status == "ACTIVE"))), ZERO))


def marketing_budget(db: Session, c: Company) -> Decimal:
    """Orçamento mensal de campanhas definido no briefing do marketeiro ativo (0 sem marketeiro)."""
    a = active_aide(db, c, "MARKETER")
    return D(str(a.settings.get("monthly_budget", "0"))) if a is not None else ZERO


def manager_boost(db: Session, c: Company) -> float:
    a = active_aide(db, c, "MANAGER")
    return aides.productivity_boost(a.level, int(a.settings.get("rigor", 40))) if a is not None else 1.0


def _manager_turnover(db: Session, c: Company, ref: date) -> None:
    """Gerente rígido demais faz funcionários pedirem demissão (sem rescisão; a empresa pode ficar sem um cargo obrigatório)."""
    a = active_aide(db, c, "MANAGER")
    if a is None:
        return
    rigor, seed = int(a.settings.get("rigor", 40)), _seed(db, c.user_id)
    for e in _employees(db, c):
        if aides.quits(a.level, rigor, seed=seed, company_id=c.id, employee_id=e.id, ref=ref):
            e.status = EmployeeStatus.TERMINATED
            e.terminated_on = ref
            _event(db, c, ref, CompanyEventType.FIRE, f"Pediu demissão: {e.name or e.role} ({e.regime.value}) — rigidez do gerente "
                   f"({aides.LEVEL_LABEL[a.level]}, rigidez {rigor}) pesou na equipe")


def _run_marketing(db: Session, c: Company, seg: rules.Segment, ref: date, k: str) -> bool:
    """Campanha do marketeiro no mês: gasta o orçamento do briefing (se houver caixa) e sorteia o resultado pelo nível. Devolve True se
    a campanha deu efeito (vale como campanha ativa no mês)."""
    a = active_aide(db, c, "MARKETER")
    budget = marketing_budget(db, c)
    if a is None or budget <= 0:
        return False
    if cash(db, c) < budget:
        _event(db, c, ref, CompanyEventType.SETTINGS, f"Marketeiro sem verba: caixa abaixo do orçamento mensal de {budget}; campanha não rodou")
        return False
    _post(db, c, ref, kind=FlowKind.EXPENSE, amount=budget, desc="Campanhas do marketeiro (orçamento mensal)", line="MARKETING", key=f"{k}:mkt-budget", overdraft=True)
    reference = rules.expansion_cost(seg, "MARKETING", c.size, c.units, "MEDIO")
    res = aides.campaign(a.level, budget=budget, reference=reference, seed=_seed(db, c.user_id), company_id=c.id, ref=ref)
    if res.outcome == "NONE":
        _event(db, c, ref, CompanyEventType.SETTINGS, f"Campanha do marketeiro ({aides.LEVEL_LABEL[a.level]}) não deu resultado neste mês "
               f"(chance era {round(res.chance * 100)}%)")
        return False
    if c.marketing_until is None or c.marketing_until <= ref:       # campanha manual mais longa em curso: mantém a dela
        c.marketing_boost = D(str(res.boost))
        c.marketing_until = ref
    c.relevance = D(str(round(min(100.0, float(c.relevance) + res.relevance * (1 - float(c.relevance) / 100)), 2)))
    _event(db, c, ref, CompanyEventType.SETTINGS, f"Campanha do marketeiro {'VIRAL' if res.outcome == 'VIRAL' else 'deu certo'}: "
           f"demanda +{round(res.boost * 100)}% no mês e +{res.relevance:.1f} de relevância")
    return True


def employee_cost(e: Employee) -> Decimal:
    """Custo mensal REAL do funcionário: CLT = 2x o salário negociado, PJ = 1x."""
    return rules.payroll_cost(e.salary, e.regime)


def _employees(db: Session, c: Company) -> list[Employee]:
    return list(db.scalars(select(Employee).where(Employee.company_id == c.id, Employee.status == EmployeeStatus.ACTIVE)
                           .order_by(Employee.id)))


def _lease(db: Session, c: Company) -> CompanyLease | None:
    return db.scalar(select(CompanyLease).where(CompanyLease.company_id == c.id, CompanyLease.active.is_(True)))


def open_branches(db: Session, c: Company) -> list[CompanyUnit]:
    """Filiais ABERTAS (fase 5). A matriz é a própria empresa; `Company.units` = 1 + len(filiais abertas)."""
    return list(db.scalars(select(CompanyUnit).where(CompanyUnit.company_id == c.id, CompanyUnit.status == "OPEN").order_by(CompanyUnit.id)))


def _rent(db: Session, c: Company, seg: rules.Segment) -> Decimal:
    """Aluguel mensal: o contrato da matriz + o aluguel de cada filial aberta (filial em terreno próprio ou online: zero)."""
    lease = _lease(db, c)
    extra = sum((u.monthly_rent for u in open_branches(db, c)), ZERO)
    return quantize_money((lease.monthly_rent if lease else ZERO) + extra)


def eff_capacity_level(c: Company) -> float:
    """Níveis EFETIVOS de capacidade (1 nível = +25%): fracionário, pois os aportes podem funcionar só em parte."""
    return float(c.capacity_boost)


# ------------------------------------------------------------------ criação e capital

def create_company(db: Session, user_id: int, month: SimMonth, *, name: str, segment: CompanySegment, size: CompanySize,
                   extra_capital: Decimal = ZERO, owner_share_pct: Decimal = D(100), channel: CompanyChannel = CompanyChannel.PHYSICAL,
                   location: str | None = None, site_mode: SiteMode | None = None,
                   partner_invite_ids: list[int] | None = None, country: str = "BR") -> Company:
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
    country = country.upper()
    try:
        ccountry = cr.get(country)
    except ValueError as e:
        raise FinanceError(str(e)) from None
    ref = month.ref_month
    fz0 = D(str(round(ccountry.cost_index * float(ws.fx(db, user_id, country, ref) * ws.price_level(db, user_id, country, ref)) / ccountry.fx0, 6))) if country != "BR" else D(1)
    minimum = quantize_money(rules.minimum_capital(seg, location, size, channel, site_mode) * fz0)
    land = quantize_money(rules.land_value(seg, channel, site_mode, location, size) * fz0)
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
                site_value=land, location=location, size=size, price=seg.price, owner_share_pct=owner_share_pct, founded_on=ref, country=country,
                opens_month=shift_month(ref, rules.opening_months(size, site_mode) + (cw.FOREIGN_OPEN_EXTRA_MONTHS if country != "BR" else 0)))
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
    _post(db, c, ref, kind=FlowKind.EXPENSE, amount=quantize_money(rules.setup_cost(seg, size, channel) * fz0), desc="Estruturação do negócio (reforma, licenças e abertura)",
          line="SETUP", key=f"co:{c.id}:setup")
    if land > 0:                                                            # terreno comprado: sai do caixa, vira ativo (patrimônio)
        _post(db, c, ref, kind=FlowKind.EXPENSE, amount=land, desc=f"Compra do terreno — {where}", line="LAND", key=f"co:{c.id}:land")
    for kind, label, amount in seg.fixed:
        db.add(CompanyCost(company_id=c.id, kind=kind, name=label, amount=quantize_money(amount * rules.cost_scale(size, channel, seg))))
    if channel == CompanyChannel.PHYSICAL and site_mode == SiteMode.RENT:
        db.add(CompanyLease(company_id=c.id, kind=LeaseKind.EXTERNAL, name=f"Ponto comercial — {where}",
                            monthly_rent=rules.default_rent(seg, location, size), start_month=ref))
    # fase 4: a empresa NASCE SEM ESTOQUE e SEM fornecedores (o capital mínimo reserva em caixa a 1ª compra). Cria 1 item vazio por
    # categoria de fornecimento; o jogador procura/contrata fornecedores e compra (ou a reposição automática compra) com o contrato.
    for stock, qty in rules.initial_stock_quantities(seg, location, size):
        db.add(InventoryItem(company_id=c.id, name=stock.name, unit=stock.unit, quantity=ZERO, unit_cost=stock.unit_cost, supplier="",
                             min_quantity=(qty * D("0.5")).quantize(D("0.001")), units_per_sale=stock.units_per_sale,
                             waste_pct=stock.waste_pct, category=stock.category))
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


def _role(seg: rules.Segment, role_key: str, size: CompanySize = CompanySize.SMALL) -> rules.Role:
    try:
        return seg.role_for(role_key, size)
    except KeyError:
        raise FinanceError("cargo inexistente neste segmento") from None


def _blocked(db: Session, c: Company) -> set[str]:
    return set(db.scalars(select(CandidateBlock.candidate_id).where(CandidateBlock.company_id == c.id)))


def _scaled(db: Session, user_id: int, cand: team.Candidate, country: str, ref: date) -> team.Candidate:
    """Candidato de outro país pede o salário do mercado de lá (índice de salários x o de referência do Brasil, corrigido pela inflação simulada do país)."""
    from dataclasses import replace
    if country == cw.HOME:
        return cand
    return replace(cand, asking_salary=quantize_money(cand.asking_salary * cw.wage_scale(country) * ws.price_level(db, user_id, country, ref)))


def list_candidates(db: Session, user_id: int, month: SimMonth, company_id: int, role_key: str,
                    regime: EmployeeRegime, country: str | None = None) -> list[team.Candidate]:
    """Candidatos do mês para o cargo/regime (determinísticos). Quem recusou a proposta ou já foi contratado some da lista."""
    require_open(month)
    c = get_company(db, user_id, company_id)
    _active(c)
    role = _role(rules.SEGMENTS[c.segment], role_key, c.size)
    blocked = _blocked(db, c)
    country = (country or c.country).upper()
    return [_scaled(db, user_id, x, country, month.ref_month) for x in team.candidates_for(_seed(db, user_id), c.id, month.ref_month, role, regime) if x.id not in blocked]


def staff_capacity(staff: list[Employee]) -> list[tuple[str, Decimal]]:
    """(cargo, produtividade efetiva) para a capacidade: meio período rende proporcionalmente à jornada (40 h = integral)."""
    return [(e.role, e.productivity * min(D(1), D(e.hours_week) / 40) * cw.staff_productivity(e)) for e in staff]


def _check_staff_cap(db: Session, c: Company) -> None:
    """Teto de funcionários do porte (por unidade): acima dele só ampliando as instalações ou mudando de endereço."""
    cap = rules.max_staff(c.size, c.units)
    n = len(_employees(db, c))
    if n >= cap:
        raise ConflictError(
            f"Teto de funcionários atingido: o porte {rules.SIZES[c.size].label} comporta {cap} pessoa(s) ({n} contratadas). "
            f"Amplie as instalações (expansão 'Instalações maiores' ou nova unidade) ou mude de endereço para um espaço maior.")


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
         schedule: WorkSchedule, regime: EmployeeRegime, confirm_risk: bool = False, idempotency_key: str,
         work_mode: str = "ONSITE", country: str | None = None) -> HireResult:
    """Proposta a um candidato. O candidato é RECALCULADO no servidor a partir do id (pretensão, nível e escolaridade nunca vêm
    do cliente). Recusa bloqueia o candidato no mês (repetir não muda nada); contraproposta não bloqueia."""
    require_open(month)
    c = get_company(db, user_id, company_id, lock=True)
    _active(c)
    seg = rules.SEGMENTS[c.segment]
    ref = month.ref_month
    try:
        cand = team.resolve_token(_seed(db, user_id), c.id, ref, candidate_id, seg, c.size)
    except ValueError as e:
        raise FinanceError(str(e)) from None
    if cand.regime != regime:
        raise FinanceError("o regime informado não é o do candidato")
    country = (country or c.country).upper()
    try:
        work_mode, country = cw.validate_hire(c, cand.role, work_mode, country)
    except ValueError as e:
        raise FinanceError(str(e)) from None
    cand = _scaled(db, user_id, cand, country, ref)
    salary = quantize_money(salary)
    if salary <= 0 or not team.MIN_WEEK <= hours_week <= team.MAX_WEEK:
        raise FinanceError(f"informe salário positivo e jornada entre {team.MIN_WEEK} e {team.MAX_WEEK} horas por semana")
    hire_key = f"co:{c.id}:hire:{idempotency_key}"
    if _replayed(db, hire_key):
        return HireResult("ACCEPTED", f"{cand.name}: contratação já registrada.")
    if cand.id in _blocked(db, c):
        return HireResult("REFUSED", f"{cand.name} não está mais disponível neste mês.")
    _check_staff_cap(db, c)
    offer = team.evaluate_offer(cand, salary, hours_week, schedule)
    if offer.status == "REFUSED":
        _block(db, c, cand, ref, "REFUSED")
        return HireResult("REFUSED", offer.message)
    if offer.status == "COUNTER":
        return HireResult("COUNTER", offer.message, offer.counter_offer)
    role = _role(seg, cand.role, c.size)
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
    _create_employee(db, c, cand, role, salary, hours_week, schedule, regime, ref, work_mode=work_mode, country=country)
    _block(db, c, cand, ref, "HIRED")
    return HireResult("ACCEPTED", offer.message)


def _create_employee(db: Session, c: Company, cand: team.Candidate, role: rules.Role, salary: Decimal, hours_week: int,
                     schedule: WorkSchedule, regime: EmployeeRegime, ref: date, via: str = "", work_mode: str = "ONSITE",
                     country: str | None = None) -> Employee:
    country = (country or c.country).upper()
    e = Employee(company_id=c.id, role=role.key, level=cand.level, salary=salary, hours_week=hours_week, productivity=cand.productivity,
                 hired_on=ref, name=cand.name, regime=regime, schedule=schedule, education=cand.education,
                 experience_years=cand.experience_years, lawsuit_history=cand.lawsuit_history, work_mode=work_mode, country=country)
    db.add(e)
    db.flush()
    _event(db, c, ref, CompanyEventType.HIRE,
           f"Contratado{via}: {cand.name}, {role.label} ({cand.level.value}, {regime.value}, {schedule.value}"
           + (", remoto" if work_mode == "REMOTE" else "") + (f", em {cr.get(country).name}" if country != "BR" else "") + f"), salário {salary}", salary)
    return e


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
    p = team.lawsuit_probability(e.regime, e.hours_week, e.schedule, tenure, e.lawsuit_history)
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
    active = {e.role for e in _employees(db, c) if rules.counts_as_filled(e.hours_week)}
    required = rules.mandatory_roles(c.channel)
    missing = rules.missing_mandatory(c.channel, active)
    return {"regular": not missing,
            "required": [{"role": r, "label": seg.role(r).label, "present": r in active} for r in required],
            "missing": missing, "missing_labels": [seg.role(r).label for r in missing],
            "estimated_fine": rules.compliance_fine(seg, missing, c.size),
            "grace_months": c.compliance_grace_months if missing else 0}


# ------------------------------------------------------------------ fornecedores (fase 4) e estoque

def _contracts(db: Session, c: Company) -> dict[str, CompanySupplier]:
    """Contratos ATIVOS por categoria (no máximo 1 por categoria: índice parcial único)."""
    return {x.category: x for x in db.scalars(select(CompanySupplier).where(
        CompanySupplier.company_id == c.id, CompanySupplier.status == "ACTIVE").order_by(CompanySupplier.id))}


def missing_supply(seg: rules.Segment, contracts: dict[str, CompanySupplier]) -> list[rules.SupplyCategory]:
    return [x for x in seg.supply_categories if x.key not in contracts]


def effective_volume(sup: CompanySupplier) -> Decimal:
    """Volume mensal do contrato: o menor entre o que o fornecedor aguenta/contratado e o limite de volume do contrato (se houver)."""
    return min(sup.max_units_month, sup.volume_cap) if sup.volume_cap is not None else sup.max_units_month


def volume_left(sup: CompanySupplier, ref: date) -> Decimal:
    """Volume que o fornecedor ainda entrega no mês (o contador zera a cada mês), já respeitando o limite de volume do contrato."""
    used = sup.volume_used if sup.volume_month == ref else ZERO
    return max(effective_volume(sup) - used, ZERO)


def spend_left(sup: CompanySupplier, ref: date) -> Decimal | None:
    """Quanto ainda pode ser gasto no mês neste contrato (None = sem limite de gasto)."""
    if sup.max_monthly_spend is None:
        return None
    used = sup.spend_used if sup.volume_month == ref else ZERO
    return max(sup.max_monthly_spend - used, ZERO)


def _roll_usage(sup: CompanySupplier, ref: date) -> None:
    """Zera os contadores do mês (volume e gasto) quando o mês muda."""
    if sup.volume_month != ref:
        sup.volume_used = ZERO
        sup.spend_used = ZERO
        sup.volume_month = ref


def limit_note(sup: CompanySupplier) -> str:
    bits = []
    if sup.max_monthly_spend is not None:
        bits.append(f"gasto máximo de {sup.max_monthly_spend}/mês")
    if sup.volume_cap is not None:
        bits.append(f"volume máximo de {sup.volume_cap}/mês")
    return ", ".join(bits)


def _price_mult(db: Session, c: Company, ref: date) -> Decimal:
    return economy_service.supplier_mult(db, c, ref)


def _supplier_ref(c: Company, sup: CompanySupplier) -> str:
    return f"company:{c.id}:supplier:{sup.id}"


def _validate_category(seg: rules.Segment, category: str) -> rules.SupplyCategory:
    if not seg.needs_suppliers:
        raise FinanceError(f"{seg.label} não usa fornecedores")
    try:
        return seg.supply(category)
    except KeyError:
        raise FinanceError("categoria de fornecimento inexistente neste segmento") from None


def search_suppliers(db: Session, user_id: int, month: SimMonth, company_id: int, category: str) -> list[supply.SupplierOffer]:
    """Fornecedores do mês para a categoria (determinísticos). Quem recusou a proposta ou já foi contratado some da lista."""
    require_open(month)
    c = get_company(db, user_id, company_id)
    _active(c)
    seg = rules.SEGMENTS[c.segment]
    _validate_category(seg, category)
    blocked = _blocked(db, c)
    offers = supply.search(_seed(db, user_id), c.id, month.ref_month, seg, category, size=c.size, units=c.units,
                           capacity_level=eff_capacity_level(c), price_mult=_price_mult(db, c, month.ref_month))
    return [o for o in offers if o.id not in blocked]


@dataclass
class SupplierResult:
    status: str                         # ACCEPTED | COUNTER | REFUSED
    message: str
    counter_offer: Decimal | None = None
    contract: CompanySupplier | None = None

    @property
    def accepted(self) -> bool:
        return self.status == "ACCEPTED"


def negotiate_supplier(db: Session, user_id: int, month: SimMonth, company_id: int, *, supplier_id: str, unit_price: Decimal,
                       monthly_volume: Decimal | None, idempotency_key: str) -> SupplierResult:
    """Proposta de preço a um fornecedor. A oferta é RECALCULADA no servidor a partir do token (preço de lista, volume, piso e
    confiabilidade nunca vêm do cliente). Aceite cria o contrato ativo; recusa bloqueia o fornecedor no mês; contraproposta não."""
    require_open(month)
    c = get_company(db, user_id, company_id, lock=True)
    _active(c)
    seg = rules.SEGMENTS[c.segment]
    ref = month.ref_month
    try:
        offer = supply.resolve_token(_seed(db, user_id), c.id, ref, supplier_id, seg, size=c.size, units=c.units,
                                     capacity_level=eff_capacity_level(c), price_mult=_price_mult(db, c, ref))
    except ValueError as e:
        raise FinanceError(str(e)) from None
    cat = seg.supply(offer.category)
    price = D(unit_price).quantize(D("0.01"))
    if price <= 0:
        raise FinanceError("informe um preço unitário positivo")
    done = db.scalar(select(CompanySupplier).where(CompanySupplier.company_id == c.id, CompanySupplier.idempotency_key == idempotency_key))
    if done is not None:                                               # repetição da mesma solicitação: nada muda
        return SupplierResult("ACCEPTED", f"{done.name}: contrato já registrado.", contract=done)
    if offer.id in _blocked(db, c):
        return SupplierResult("REFUSED", f"{offer.name} não está mais disponível neste mês.")
    if _contracts(db, c).get(offer.category) is not None:
        raise ConflictError(f"já existe um contrato ativo de {cat.label}: encerre-o antes de contratar outro fornecedor")
    volume = D(monthly_volume) if monthly_volume is not None else offer.max_units_month
    if volume > offer.max_units_month or volume < offer.min_monthly_order:
        raise FinanceError(f"o volume mensal deve ficar entre o pedido mínimo ({offer.min_monthly_order}) e o que o fornecedor aguenta "
                           f"({offer.max_units_month}) {cat.unit}")
    deal = supply.evaluate(offer, price, float(c.relevance), volume)
    if deal.status == "REFUSED":
        _block(db, c, _TokenBlock(offer.id), ref, "REFUSED")
        return SupplierResult("REFUSED", deal.message)
    if deal.status == "COUNTER":
        return SupplierResult("COUNTER", deal.message, deal.counter_offer)
    sup = _sign_contract(db, c, offer, cat, deal.price, volume, ref, idempotency_key)
    return SupplierResult("ACCEPTED", deal.message, contract=sup)


def _sign_contract(db: Session, c: Company, offer: supply.SupplierOffer, cat: rules.SupplyCategory, price: Decimal, volume: Decimal, ref: date,
                   idempotency_key: str, *, limits: recruiter.Limits | None = None, via: str = "") -> CompanySupplier:
    """Cria o contrato ativo (a oferta já foi aceita). `limits` = critérios/limites guardados no contrato (contratador)."""
    sup = CompanySupplier(company_id=c.id, category=offer.category, name=offer.name, unit_price=price, reference_price=cat.ref_price,
                          min_monthly_order=offer.min_monthly_order, max_units_month=volume, reliability=D(str(offer.reliability)),
                          lead_days=offer.lead_days, status="ACTIVE", started_month=ref, term_months=supply.CONTRACT_TERM_MONTHS,
                          idempotency_key=idempotency_key)
    if limits is not None:
        sup.max_monthly_spend, sup.volume_cap = limits.max_spend, limits.volume_cap
        sup.min_reliability = D(str(limits.min_reliability)) if limits.min_reliability is not None else None
        sup.max_lead_days = limits.max_lead_days
    db.add(sup)
    _block(db, c, _TokenBlock(offer.id), ref, "SIGNED")
    db.flush()
    _event(db, c, ref, CompanyEventType.STOCK,
           f"Fornecedor contratado{via} ({cat.label}): {offer.name}, {price} por {cat.unit}, até {volume} {cat.unit}/mês, "
           f"confiabilidade {round(offer.reliability * 100)}%", price)
    return sup


def set_supplier_limits(db: Session, user_id: int, month: SimMonth, company_id: int, supplier_id: int, *, max_monthly_spend: Decimal | None,
                        min_reliability: float | None, max_lead_days: int | None, volume_cap: Decimal | None) -> CompanySupplier:
    """Limites do contrato (substitui os quatro; None = sem limite). Gasto e volume valem nas compras (manual e reposição automática);
    confiabilidade mínima e prazo máximo são critérios do contratador ao renovar/trocar o fornecedor."""
    require_open(month)
    c = get_company(db, user_id, company_id, lock=True)
    _active(c)
    sup = db.get(CompanySupplier, supplier_id)
    if sup is None or sup.company_id != c.id:
        raise NotFoundError("contrato de fornecedor não encontrado")
    if sup.status != "ACTIVE":
        raise ConflictError("este contrato já foi encerrado")
    try:
        if max_monthly_spend is not None and max_monthly_spend <= 0:
            raise ValueError("o gasto máximo mensal deve ser maior que zero")
        if volume_cap is not None and volume_cap <= 0:
            raise ValueError("o volume máximo deve ser maior que zero")
        if min_reliability is not None and not 0 < min_reliability <= 1:
            raise ValueError("a confiabilidade mínima deve ficar entre 0 e 1 (ex.: 0,9 = 90%)")
        if max_lead_days is not None and not 1 <= max_lead_days <= recruiter.MAX_LEAD_LIMIT:
            raise ValueError(f"o prazo máximo deve ficar entre 1 e {recruiter.MAX_LEAD_LIMIT} dias")
    except ValueError as e:
        raise FinanceError(str(e)) from None
    sup.max_monthly_spend = quantize_money(max_monthly_spend) if max_monthly_spend is not None else None
    sup.volume_cap = volume_cap.quantize(D("0.001")) if volume_cap is not None else None
    sup.min_reliability = D(str(round(min_reliability, 3))) if min_reliability is not None else None
    sup.max_lead_days = max_lead_days
    db.flush()
    _event(db, c, month.ref_month, CompanyEventType.STOCK, f"Limites do contrato com {sup.name} ({sup.category}) atualizados: "
           + (limit_note(sup) or "sem limites de gasto/volume"))
    return sup


@dataclass(frozen=True)
class _TokenBlock:
    """Adaptador: `_block` usa só o `id` do candidato (aqui, o token do fornecedor)."""
    id: str


def end_supplier(db: Session, user_id: int, month: SimMonth, company_id: int, supplier_id: int) -> CompanySupplier:
    """Encerra o contrato. Antes de `MIN_TENURE_MONTHS` meses de contrato há multa de 2 pedidos mínimos (o Fornecedor padrão das
    empresas antigas nunca tem multa). O estoque já comprado fica; a categoria volta a exigir um novo contrato para repor."""
    require_open(month)
    c = get_company(db, user_id, company_id, lock=True)
    _active(c)
    sup = db.get(CompanySupplier, supplier_id)
    if sup is None or sup.company_id != c.id:
        raise NotFoundError("contrato de fornecedor não encontrado")
    if sup.status != "ACTIVE":
        raise ConflictError("este contrato já foi encerrado")
    ref = month.ref_month
    tenure = months_between(sup.started_month, ref)
    fine = ZERO if (sup.is_default or tenure >= supply.MIN_TENURE_MONTHS) else quantize_money(
        sup.min_monthly_order * sup.unit_price * supply.EARLY_END_FINE_ORDERS)
    if fine > 0:
        _post(db, c, ref, kind=FlowKind.EXPENSE, amount=fine, desc=f"Multa por encerrar contrato antes de {supply.MIN_TENURE_MONTHS} meses: {sup.name}",
              line="FEES", key=f"co:{c.id}:supend:{sup.id}", overdraft=True, origin_ref=_supplier_ref(c, sup))
    sup.status = "ENDED"
    sup.ended_month = ref
    db.flush()
    _event(db, c, ref, CompanyEventType.STOCK, f"Contrato encerrado: {sup.name} ({sup.category})"
           + (f", multa {fine}" if fine > 0 else ", sem multa"), fine if fine > 0 else None)
    return sup


def _buy_stock(db: Session, c: Company, item: InventoryItem, qty: Decimal, ref: date, key: str, seg: rules.Segment,
               sup: CompanySupplier) -> Decimal:
    """Compra do contrato da categoria: preço contratado; se o fornecedor falhar no mês entrega só parte (e só a parte é paga)."""
    qty = qty.quantize(D("0.001")) if seg.fractional else D(math.ceil(qty))
    if qty <= 0:
        return ZERO
    f = D(str(supply.delivery_factor(_seed(db, c.user_id), c.id, sup.id, ref, float(sup.reliability))))
    delivered = qty if f >= 1 else ((qty * f).quantize(D("0.001")) if seg.fractional else D(math.floor(qty * f)))
    if f < 1:
        _event(db, c, ref, CompanyEventType.STOCK,
               f"Falha de entrega: {sup.name} entregou só {delivered} de {qty} {item.unit} de {item.name} ({round(float(f) * 100)}%)")
    if delivered <= 0:
        return ZERO
    price = quantize_money(sup.unit_price * rules.quality_cost_mult(float(c.quality)) * cw.company_factor(db, c, ref))   # qualidade maior = insumo mais caro; país muda o nível de preços
    total = quantize_money(delivered * price)
    _post(db, c, ref, kind=FlowKind.EXPENSE, amount=total, desc=f"Compra de estoque: {item.name} ({delivered} {item.unit}) — {sup.name}",
          line="STOCK_PURCHASE", key=key, origin_ref=_supplier_ref(c, sup))
    new_qty = item.quantity + delivered
    item.unit_cost = ((item.quantity * item.unit_cost + delivered * price) / new_qty).quantize(D("0.0001"))
    item.quantity = new_qty
    item.supplier = sup.name
    _roll_usage(sup, ref)
    sup.volume_used += delivered
    sup.spend_used += total
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
    ref = month.ref_month
    cap = rules.storage_cap_qty(seg, c.size, c.units, item, float(c.storage_boost))
    if item.quantity + D(quantity) > cap:
        room = max(cap - item.quantity, ZERO)
        raise ConflictError(
            f"Teto de estoque atingido: o espaço de armazenagem do porte {rules.SIZES[c.size].label} comporta {cap} {item.unit} de "
            f"{item.name} (você tem {item.quantity}; cabem mais {room}). Amplie as instalações ('Instalações maiores', nova unidade) "
            f"ou mude de endereço para um espaço maior.")
    sup = _contracts(db, c).get(item.category or "")
    if sup is None:
        raise ConflictError(f"Sem fornecedor contratado para {item.name}: procure e contrate um fornecedor desta categoria antes de comprar.")
    q = D(quantity)
    if q < sup.min_monthly_order:
        raise FinanceError(f"{sup.name} exige pedido mínimo de {sup.min_monthly_order} {item.unit}")
    left = volume_left(sup, ref)
    if q > left:
        capped = sup.volume_cap is not None and sup.volume_cap < sup.max_units_month
        raise ConflictError(f"{sup.name} não aguenta esse volume: restam {left} {item.unit} no mês "
                            + (f"(limite de volume do contrato: {sup.volume_cap} por mês)" if capped else f"(contrato de {sup.max_units_month} por mês)"))
    room_spend = spend_left(sup, ref)
    cost_est = quantize_money(q * sup.unit_price * rules.quality_cost_mult(float(c.quality)))
    if room_spend is not None and cost_est > room_spend:
        raise ConflictError(f"Limite de gasto do contrato atingido: {sup.name} permite no máximo {sup.max_monthly_spend} por mês e restam "
                            f"{room_spend} (esta compra custaria cerca de {cost_est}). Aumente o limite do contrato ou compre menos.")
    total = _buy_stock(db, c, item, q, ref, f"company:{c.id}:stock:{key}", seg, sup)
    _event(db, c, ref, CompanyEventType.STOCK, f"Compra de {item.name}: {quantity} {item.unit} ({sup.name})", total)
    return item


def delivery_status(db: Session, c: Company, sup: CompanySupplier, ref: date) -> float:
    return supply.delivery_factor(_seed(db, c.user_id), c.id, sup.id, ref, float(sup.reliability))


def supply_state(db: Session, c: Company, ref: date, contracts: dict[str, CompanySupplier] | None = None) -> dict:
    """Capacidade efetiva dos fornecedores no mês: menor `max_units_month / (consumo x (1 + perda))` entre as categorias
    (nos serviços já descontando a falha de entrega do mês; nos segmentos com estoque a falha só reduz a compra)."""
    seg = rules.SEGMENTS[c.segment]
    contracts = contracts if contracts is not None else _contracts(db, c)
    service = seg.metrics_kind == rules.MetricsKind.SERVICE
    volumes = {k: float(effective_volume(s)) * (delivery_status(db, c, s, ref) if service else 1.0) for k, s in contracts.items()}
    cap = rules.supply_capacity(seg, volumes, missing_is_zero=service)
    return {"missing": missing_supply(seg, contracts), "cap": cap, "failed": [s for s in contracts.values() if delivery_status(db, c, s, ref) < 1]}


@dataclass
class UnitPlan:
    """Uma unidade no cálculo do mês: a MATRIZ (`unit=None`) ou uma filial aberta. `share` = fatia da capacidade dos cargos produtivos
    globais que cabe à unidade (proporcional à demanda dela: a equipe é distribuída onde há clientes)."""
    unit: CompanyUnit | None
    name: str
    location: str
    relevance: float
    viability: float
    demand: float = 0.0
    share: float = 1.0
    key: object = None                    # `company_id` usado nos sorteios da unidade (matriz: o id; filial: "<id>u<unidade>")


def plan_units(db: Session, c: Company, seg: rules.Segment, ref: date, *, season: bool = True, marketing: bool = False,
               econ_mult: float = 1.0, relocation_mult: float = 1.0, branches: list[CompanyUnit] | None = None) -> list[UnitPlan]:
    """Demanda por unidade e a repartição da equipe produtiva global entre elas (documentado em `docs/EMPRESAS_V2.md`)."""
    branches = open_branches(db, c) if branches is None else branches
    branches = [u for u in branches if u.opens_month is None or u.opens_month <= ref]
    plans = [UnitPlan(None, "Matriz", c.location, float(c.relevance), 1.0, key=c.id)] + [
        UnitPlan(u, u.name or f"Filial {u.id}", u.location, float(u.relevance), float(u.viability), key=f"{c.id}u{u.id}") for u in branches]
    for i, p in enumerate(plans):
        p.demand = rules.demand_units(seg, location=p.location, size=c.size, units=1, reputation=c.reputation, price=c.price,
                                      company_id=p.key, ref=ref, marketing=marketing, season=season, relevance=p.relevance,
                                      quality=float(c.quality), marketing_boost=float(c.marketing_boost)) \
            * econ_mult * (relocation_mult if i == 0 else 1.0) * p.viability
    total = sum(p.demand for p in plans)
    for p in plans:
        p.share = (p.demand / total) if total > 0 else 1 / len(plans)
    return plans


def unit_capacity(db: Session, c: Company, seg: rules.Segment, plan: UnitPlan, staff_cap: list, equipment: float) -> float:
    return rules.capacity_units(seg, size=c.size, units=1, capacity_level=eff_capacity_level(c), staff=staff_cap,
                                equipment_factor=equipment, people_share=plan.share)


def expected_totals(db: Session, c: Company, seg: rules.Segment, staff: list[Employee]) -> tuple[float, float]:
    """(demanda esperada, capacidade esperada) da empresa inteira (matriz + filiais), sem sazonalidade nem sorteios."""
    plans = plan_units(db, c, seg, c.founded_on, season=False)
    sc, eq = staff_capacity(staff), _equipment_factor(db, c)
    return sum(p.demand for p in plans), sum(unit_capacity(db, c, seg, p, sc, eq) for p in plans)


def _planned_sales(db: Session, c: Company, seg: rules.Segment, cap: float) -> float:
    """Vendas esperadas no mês (demanda com a relevância atual, limitada pela equipe e pelos fornecedores), sem sorteios."""
    plans = plan_units(db, c, seg, c.founded_on, season=False)
    sc, eq = staff_capacity(_employees(db, c)), _equipment_factor(db, c)
    return max(min(sum(min(p.demand, unit_capacity(db, c, seg, p, sc, eq)) for p in plans), cap), 0.0)


def supplier_budget(db: Session, c: Company, ref: date | None = None) -> dict:
    """Orçamento de fornecedores: por categoria, o preço contratado, o volume previsto do mês, o gasto previsto (demanda esperada x
    consumo x preço) e o gasto REALIZADO do último mês fechado (lançamentos com origin_ref do fornecedor)."""
    seg = rules.SEGMENTS[c.segment]
    if not seg.needs_suppliers:
        return {"rows": [], "total_planned": ZERO, "total_last_actual": ZERO, "last_month": None}
    ref = ref or c.last_processed_month or c.founded_on
    contracts = _contracts(db, c)
    state = supply_state(db, c, ref, contracts)
    planned = _planned_sales(db, c, seg, state["cap"])
    last = db.scalar(select(CompanyMonth.ref_month).where(CompanyMonth.company_id == c.id).order_by(CompanyMonth.ref_month.desc()).limit(1))
    by_cat: dict[str, list[str]] = {}
    for s in db.scalars(select(CompanySupplier).where(CompanySupplier.company_id == c.id)):
        by_cat.setdefault(s.category, []).append(_supplier_ref(c, s))
    rows, total, total_last = [], ZERO, ZERO
    for cat in seg.supply_categories:
        sup = contracts.get(cat.key)
        price = sup.unit_price if sup else cat.ref_price
        volume = quantize_money(D(str(planned)) * cat.per_sale * (1 + cat.waste_pct / 100))
        spend = quantize_money(volume * price)
        actual = ZERO
        if last is not None and by_cat.get(cat.key):
            actual = quantize_money(db.scalar(select(func.coalesce(func.sum(LedgerEntry.amount), 0)).where(
                LedgerEntry.company_id == c.id, LedgerEntry.ref_month == last, LedgerEntry.kind == FlowKind.EXPENSE,
                LedgerEntry.line.in_(["STOCK_PURCHASE", "SUPPLIES"]), LedgerEntry.origin_ref.in_(by_cat[cat.key]))))
        rows.append({"category": cat.key, "label": cat.label, "unit": cat.unit, "weight": cat.weight, "supplier_id": sup.id if sup else None,
                     "supplier": sup.name if sup else None, "unit_price": price, "estimated": sup is None, "planned_volume": volume,
                     "planned_spend": spend, "last_actual": actual, "max_units_month": sup.max_units_month if sup else None,
                     "max_monthly_spend": sup.max_monthly_spend if sup else None, "volume_cap": sup.volume_cap if sup else None,
                     "over_limit": bool(sup and sup.max_monthly_spend is not None and spend > sup.max_monthly_spend)})
        total += spend if sup else ZERO
        total_last += actual
    total_limit = None
    rec = active_recruiter(db, c)
    if rec is not None:
        total_limit = recruiter.settings_from_json(rec.settings, {x.key for x in seg.supply_categories}).supplier_max_total_spend
    return {"rows": rows, "total_planned": quantize_money(total), "total_last_actual": quantize_money(total_last), "last_month": last,
            "total_limit": total_limit, "over_total": bool(total_limit is not None and total > total_limit)}


def grant_default_suppliers(db: Session, c: Company, ref: date | None = None) -> list[CompanySupplier]:
    """Compatibilidade (empresas anteriores à fase 4; a migration faz o mesmo em SQL): contrato ATIVO com o "Fornecedor padrão"
    ao preço de referência, sem pedido mínimo prático, volume ilimitado e confiabilidade 100%, em cada categoria sem contrato."""
    seg = rules.SEGMENTS[c.segment]
    have = _contracts(db, c)
    out = []
    for cat in seg.supply_categories:
        if cat.key in have:
            continue
        sup = CompanySupplier(company_id=c.id, category=cat.key, name=supply.DEFAULT_SUPPLIER_NAME, unit_price=cat.ref_price,
                              reference_price=cat.ref_price, min_monthly_order=supply.LEGACY_MIN_ORDER, max_units_month=supply.DEFAULT_MAX_UNITS,
                              reliability=D(1), lead_days=2, status="ACTIVE", started_month=ref or c.founded_on,
                              term_months=supply.CONTRACT_TERM_MONTHS, is_default=True)
        db.add(sup)
        out.append(sup)
    db.flush()
    return out


def supply_checklist(db: Session, c: Company) -> list[dict]:
    seg = rules.SEGMENTS[c.segment]
    contracts = _contracts(db, c)
    return [{"category": x.key, "label": x.label, "present": x.key in contracts,
             "supplier": contracts[x.key].name if x.key in contracts else None} for x in seg.supply_categories]


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


def relocation_quote(db: Session, c: Company, *, location: str, site_mode: SiteMode | None, size: CompanySize | None = None) -> dict:
    """Quanto custa mudar de endereço (sem alterar nada). Levanta FinanceError/ConflictError se a mudança não for válida."""
    seg = rules.SEGMENTS[c.segment]
    if c.channel != CompanyChannel.PHYSICAL:
        raise ConflictError("empresa online não tem endereço físico: não há mudança de endereço")
    new_size = size or c.size
    try:
        loc, mode = rules.validate_site(seg, c.channel, location, site_mode)
    except ValueError as e:
        raise FinanceError(str(e)) from None
    if loc == c.location and mode == c.site_mode and new_size == c.size and c.suspended_until is None:
        raise FinanceError("a empresa já funciona neste endereço: escolha outro local, outro modo (comprar/alugar) ou outro porte")
    if rules.SIZE_ORDER.index(new_size) < rules.SIZE_ORDER.index(c.size) and len(_employees(db, c)) > rules.max_staff(new_size, c.units):
        raise ConflictError(f"o porte {rules.SIZES[new_size].label} comporta {rules.max_staff(new_size, c.units)} pessoas: desligue funcionários antes de reduzir")
    lease = _lease(db, c)
    breaks = lease is not None and lease.kind == LeaseKind.EXTERNAL and lease.monthly_rent > 0
    parts = rules.relocation_cost(seg, loc, new_size, current_rent=lease.monthly_rent if lease else ZERO, breaks_lease=breaks)
    land_new = rules.land_value(seg, c.channel, mode, loc, new_size)
    land_back = quantize_money(c.site_value * rules.LAND_RESALE) if c.site_mode == SiteMode.BUY else ZERO
    return {"location": loc, "site_mode": mode, "size": new_size, **parts, "land_cost": land_new, "land_resale": land_back,
            "total": quantize_money(parts["total"] + land_new - land_back),
            "relevance_after": rules.relevance_after_move(seg, float(c.relevance), c.location, loc),
            "sales_mult": rules.RELOCATION_SALES_MULT}


def relocate(db: Session, user_id: int, month: SimMonth, company_id: int, *, location: str, site_mode: SiteMode | None,
             size: CompanySize | None, idempotency_key: str) -> Company:
    """Mudança de endereço: cobra (meses de aluguel + reinstalação + multa do aluguel encerrado), troca terreno/contrato, mantém
    funcionários e parte da relevância, e a empresa vende pouco no fechamento do mês (ficou parte do mês sem operar)."""
    require_open(month)
    c = get_company(db, user_id, company_id, lock=True)
    _active(c)
    seg = rules.SEGMENTS[c.segment]
    ref = month.ref_month
    key = f"co:{c.id}:reloc:{idempotency_key}"
    if _replayed(db, f"{key}:move"):
        return c
    if c.relocated_on == ref:
        raise ConflictError("a empresa já mudou de endereço neste mês: aguarde o fechamento")
    q = relocation_quote(db, c, location=location, site_mode=site_mode, size=size)
    balance = cash(db, c)
    if balance < q["total"]:
        raise FinanceError(f"a empresa não tem caixa para a mudança ({q['total']}); caixa atual: {balance}")
    return _do_relocate(db, c, seg, ref, q, key)


def _do_relocate(db: Session, c: Company, seg: rules.Segment, ref: date, q: dict, key: str, *, overdraft: bool = False) -> Company:
    """Executa a mudança já cotada (também usada pela decisão de despejo, com `overdraft`)."""
    old_label = rules.resolve_location(seg, c.location).label
    new_label = rules.resolve_location(seg, q["location"]).label
    _post(db, c, ref, kind=FlowKind.EXPENSE, amount=q["move"], desc=f"Mudança de endereço: {new_label} (3 meses de aluguel)",
          line="RELOCATION", key=f"{key}:move", overdraft=overdraft)
    _post(db, c, ref, kind=FlowKind.EXPENSE, amount=q["reinstall"], desc="Reinstalação no novo endereço", line="RELOCATION", key=f"{key}:reinstall", overdraft=overdraft)
    _post(db, c, ref, kind=FlowKind.EXPENSE, amount=q["fine"], desc="Multa pela rescisão do contrato de aluguel", line="RELOCATION", key=f"{key}:fine", overdraft=overdraft)
    if q["land_resale"] > 0:                                         # terreno antigo vendido: volta ao caixa (capital, não é receita)
        _post(db, c, ref, kind=FlowKind.INCOME, amount=q["land_resale"], desc=f"Venda do terreno anterior — {old_label}", line="LAND", key=f"{key}:landsale")
    if q["land_cost"] > 0:
        _post(db, c, ref, kind=FlowKind.EXPENSE, amount=q["land_cost"], desc=f"Compra do terreno — {new_label}", line="LAND", key=f"{key}:land", overdraft=overdraft)
    lease = _lease(db, c)
    if lease:                                                          # encerra o contrato antigo (libera o imóvel próprio, se for o caso)
        lease.active = False
        lease.end_month = ref
        if lease.good_id:
            g = db.get(Good, lease.good_id)
            det = db.get(RealEstateDetails, g.id) if g else None
            if det and det.occupancy == Occupancy.COMPANY_USE:
                det.occupancy = Occupancy.VACANT
                det.monthly_rent = ZERO
        db.flush()
    old_size = c.size
    if q["site_mode"] == SiteMode.RENT:
        db.add(CompanyLease(company_id=c.id, kind=LeaseKind.EXTERNAL, name=f"Ponto comercial — {new_label}",
                            monthly_rent=rules.default_rent(seg, q["location"], q["size"]), start_month=ref))
    if q["size"] != old_size:
        ratio = rules.SIZES[q["size"]].fixed / rules.SIZES[old_size].fixed
        for cost_row in db.scalars(select(CompanyCost).where(CompanyCost.company_id == c.id)):
            cost_row.amount = quantize_money(cost_row.amount * ratio)
    c.relevance = D(str(q["relevance_after"]))
    c.location, c.site_mode, c.size = q["location"], q["site_mode"], q["size"]
    c.site_value = q["land_cost"] if q["site_mode"] == SiteMode.BUY else ZERO
    c.relocated_on = ref
    c.suspended_until = None                                           # mudar de endereço encerra o período sem operar (despejo)
    db.flush()
    _event(db, c, ref, CompanyEventType.EXPANSION,
           f"Mudança de endereço: {old_label} -> {new_label} ({q['site_mode'].value if q['site_mode'] else '—'}). Custo {q['total']}; "
           f"vendas do mês reduzidas e relevância {q['relevance_after']}", q["total"])
    return c


def end_suspension(db: Session, c: Company, ref: date) -> None:
    """Fim do período sem operar do despejo (sem relocar): a empresa consegue um novo ponto no mesmo bairro, a aluguel de referência."""
    seg = rules.SEGMENTS[c.segment]
    c.suspended_until = None
    if c.channel == CompanyChannel.PHYSICAL and c.site_mode == SiteMode.RENT and _lease(db, c) is None:
        label = rules.resolve_location(seg, c.location).label
        db.add(CompanyLease(company_id=c.id, kind=LeaseKind.EXTERNAL, name=f"Ponto comercial — {label} (novo contrato)",
                            monthly_rent=rules.default_rent(seg, c.location, c.size), start_month=ref))
    db.flush()
    _event(db, c, ref, CompanyEventType.LEASE, "Novo ponto alugado após o despejo: a empresa volta a operar")


def apply_incident_action(db: Session, c: Company, ev_id: int, ref: date, action: dict) -> str:
    """Ações de resultado dos imprevistos (despejo, quebra), chamadas por `economy_service._activate`."""
    seg = rules.SEGMENTS[c.segment]
    kind = action.get("type")
    if kind == "renew_lease":
        lease = _lease(db, c)
        if lease:
            lease.start_month = ref                                   # contrato novo: a idade do contrato zera
        _event(db, c, ref, CompanyEventType.LEASE, "Contrato de aluguel renovado: o proprietário aceitou a permanência")
        return "renew"
    if kind == "evict":
        lease = _lease(db, c)
        months = int(action.get("months", 2))
        if lease:
            lease.active = False
            lease.end_month = ref
        c.suspended_until = shift_month(ref, months - 1)
        db.flush()
        _event(db, c, ref, CompanyEventType.LEASE,
               f"DESPEJO: a empresa perdeu o ponto e fica sem operar por {months} mês(es) ou até mudar de endereço (vendas zeradas)")
        return "evict"
    if kind == "relocate_equiv":
        cands = [x for x in seg.locations if x.key != c.location]
        cur = rules.resolve_location(seg, c.location).demand
        loc = min(cands, key=lambda x: (abs(x.demand - cur), x.key)).key
        q = relocation_quote(db, c, location=loc, site_mode=SiteMode.RENT, size=None)
        _do_relocate(db, c, seg, ref, q, f"co:{c.id}:evictmove:{ev_id}", overdraft=True)
        return "relocate"
    if kind == "shield":
        c.incident_shield_until = shift_month(ref, int(action.get("months", 12)))
        _event(db, c, ref, CompanyEventType.EQUIPMENT, "Conserto premium: sem quebras de equipamento pelos próximos meses")
        return "shield"
    return ""


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
    return f * manager_boost(db, c)


def process_month(db: Session, user_id: int, month: SimMonth) -> list[CompanyMonth]:
    """Processa todas as empresas ativas no fechamento do mês. Cada empresa só é processada uma vez por mês."""
    out = []
    for c in db.scalars(select(Company).where(Company.user_id == user_id, Company.status == CompanyStatus.ACTIVE).order_by(Company.id)):
        if db.scalar(select(CompanyMonth.id).where(CompanyMonth.company_id == c.id, CompanyMonth.ref_month == month.ref_month)):
            continue
        out.append(_process_company(db, c, month))
    return out


def _compute_month_taxes(db: Session, c: Company, seg: rules.Segment, ref: date, staff: list, *, revenue: Decimal, payroll: Decimal,
                         purchases: Decimal) -> company_taxes.TaxResult:
    """RBT12 e folha de 12 meses (proporcionalizados se a empresa tem menos de 12 meses) + regime do mês anterior."""
    prior = list(db.execute(select(CompanyMonth.revenue, CompanyMonth.payroll, CompanyMonth.tax_regime).where(
        CompanyMonth.company_id == c.id, CompanyMonth.ref_month < ref).order_by(CompanyMonth.ref_month.desc()).limit(12)))[::-1]
    hint = None
    if prior:                                      # meses antigos sem regime: empresa já existia, nunca volta ao MEI
        hint = prior[-1].tax_regime or company_taxes.SIMPLES
    rbt12 = company_taxes.annualize([p.revenue for p in prior], revenue)
    payroll12 = company_taxes.annualize([p.payroll for p in prior], payroll)
    clt = sum(1 for e in staff if e.regime == EmployeeRegime.CLT)
    return company_taxes.compute_taxes(c.segment.value, hint, rbt12, revenue, payroll12, clt, purchases=purchases)


def _units_detail(db: Session, c: Company, seg: rules.Segment, plans: list[UnitPlan], results: list, unit_sold: list, *, revenue: Decimal,
                  variable_total: Decimal, payroll_staff: Decimal, operating: Decimal) -> list[dict]:
    """Resultado do mês por unidade (fase 5). Receita = vendas da unidade x preço; custo variável rateado pelas vendas; folha dos
    funcionários rateada pela fatia de equipe da unidade; custos fixos da filial = aluguel dela + custos fixos por unidade. A
    matriz fica com o que sobra (inclui impostos não rateados, pró-labore e extras da empresa), de modo que a soma bate com o total."""
    total_sold = sum(unit_sold)
    scalable = sum((x.amount for x in db.scalars(select(CompanyCost).where(
        CompanyCost.company_id == c.id, CompanyCost.active.is_(True), CompanyCost.scales_with_units.is_(True)))), ZERO)
    rows, used = [], {"revenue": ZERO, "variable": ZERO, "fixed": ZERO, "payroll": ZERO}
    for p, r, sold_u in list(zip(plans, results, unit_sold))[1:]:
        rev = quantize_money(D(str(sold_u)) * c.price)
        var = quantize_money(variable_total * D(str(sold_u)) / D(str(total_sold))) if total_sold > 0 else ZERO
        fix = quantize_money(p.unit.monthly_rent + scalable)
        pay = quantize_money(payroll_staff * D(str(round(p.share, 6))))
        res = quantize_money(rev - var - fix - pay)
        p.unit.cumulative_result = quantize_money(p.unit.cumulative_result + res)
        for k_, v_ in (("revenue", rev), ("variable", var), ("fixed", fix), ("payroll", pay)):
            used[k_] += v_
        rows.append({"unit_id": p.unit.id, "name": p.name, "kind": "BRANCH", "location": p.location,
                     "demand": round(r.demand, 2), "capacity": round(r.capacity, 2), "sold": float(sold_u), "relevance": round(p.relevance, 2),
                     "revenue": str(rev), "variable_costs": str(var), "fixed_costs": str(fix), "payroll": str(pay), "result": str(res),
                     "cumulative_result": str(p.unit.cumulative_result)})
    hq = plans[0]
    hq_rev = quantize_money(revenue - used["revenue"])
    hq_var = quantize_money(variable_total - used["variable"])
    hq_pay = quantize_money(payroll_staff - used["payroll"])
    hq_res = quantize_money(operating - sum((D(x["result"]) for x in rows), ZERO))
    hq_row = {"unit_id": None, "name": "Matriz", "kind": "HQ", "location": hq.location, "demand": round(results[0].demand, 2),
              "capacity": round(results[0].capacity, 2), "sold": float(unit_sold[0]), "relevance": round(hq.relevance, 2),
              "revenue": str(hq_rev), "variable_costs": str(hq_var), "fixed_costs": str(quantize_money(hq_rev - hq_var - hq_pay - hq_res)),
              "payroll": str(hq_pay), "result": str(hq_res), "cumulative_result": None}
    return [hq_row] + rows


def _review_branches(db: Session, c: Company, seg: rules.Segment, ref: date, plans: list[UnitPlan], detail: list[dict]) -> None:
    """Falência de filial: fecha se o resultado acumulado cair abaixo de -60% do custo de abertura (com >= 3 meses de vida) ou se o
    caixa da empresa não cobre o prejuízo do mês (caixa negativo e filial no vermelho). Fecha com evento, encerra o aluguel, vende
    o terreno a 92% e o investimento é perdido."""
    db.flush()
    balance = cash(db, c)
    by_id = {d["unit_id"]: d for d in detail if d["unit_id"] is not None}
    for p in plans[1:]:
        u = p.unit
        age = months_between(u.opened_month, ref)
        res = D(by_id[u.id]["result"])
        limit = -quantize_money(max(u.investment, D(1)) * rules.BRANCH_CLOSE_LOSS)
        reason = None
        if age >= rules.BRANCH_MIN_AGE and u.cumulative_result < limit:
            reason = f"prejuízo acumulado de {-u.cumulative_result} passou do limite de {-limit}"
        elif balance < 0 and res < 0 and age >= 1:
            reason = "o caixa da empresa não cobre o prejuízo da filial"
        if reason:
            close_branch(db, c, seg, u, ref, reason)


def close_branch(db: Session, c: Company, seg: rules.Segment, u: CompanyUnit, ref: date, reason: str) -> None:
    u.status, u.closed_month, u.closed_reason = "CLOSED", ref, reason[:160]
    back = ZERO
    if u.site_value > 0:
        back = quantize_money(u.site_value * rules.BRANCH_LAND_RESALE)
        _post(db, c, ref, kind=FlowKind.INCOME, amount=back, desc=f"Venda do terreno da {u.name} (92%)", line="LAND", key=f"co:{c.id}:unit:{u.id}:landsale")
    c.units = max(1, c.units - 1)
    db.flush()
    _event(db, c, ref, CompanyEventType.EXPANSION,
           f"{u.name} FALIU e foi fechada: {reason}. Aluguel encerrado" + (f", terreno vendido por {back}" if back > 0 else "")
           + f"; o investimento de {u.investment} foi perdido", back if back > 0 else None)


def _process_company(db: Session, c: Company, month: SimMonth) -> CompanyMonth:
    ref = month.ref_month
    seg = rules.SEGMENTS[c.segment]
    k = f"co:{c.id}:{ref:%Y-%m}"
    _manager_turnover(db, c, ref)
    staff = _employees(db, c)
    items = list(db.scalars(select(InventoryItem).where(InventoryItem.company_id == c.id).order_by(InventoryItem.id))) \
        if seg.has_stock else []                                        # segmentos de serviço não têm estoque
    opening_cash = cash(db, c)
    if c.suspended_until is not None and ref > c.suspended_until:
        end_suspension(db, c, ref)                                      # fase 5: acabou o período sem operar do despejo
    suspended = c.suspended_until is not None and ref <= c.suspended_until
    branches = [u for u in open_branches(db, c) if u.opens_month is None or u.opens_month <= ref]

    # 1) condições do mês (relevância, demanda, sazonalidade, campanha, economia, mudança de endereço)
    _run_marketing(db, c, seg, ref, k)
    marketing = c.marketing_until is not None and ref <= c.marketing_until
    relevance = float(c.relevance)
    missing = rules.missing_mandatory(c.channel, [e.role for e in staff if rules.counts_as_filled(e.hours_week)])   # fase 2/3a: cargos obrigatórios
    grace = c.compliance_grace_months if missing else 0          # período de adaptação (empresas legadas): sem bloqueio nem multa
    if not missing and c.compliance_grace_months:
        c.compliance_grace_months = 0                              # regular: a tolerância não é mais necessária
    in_grace = grace > 0
    opening = _opening(c, ref)                                           # em abertura/obra: ainda não vende
    irregular = bool(missing) and not in_grace and not opening
    stock_cap = min((float(i.quantity / (i.units_per_sale * (1 + i.waste_pct / 100))) for i in items), default=math.inf)
    # fase 4: fornecedores. Serviços sem contrato numa categoria NÃO operam (vendas 0); nos segmentos com estoque a falta de contrato
    # só impede a reposição (o estoque que sobrou ainda vende). A capacidade efetiva é limitada pelo menor volume contratado.
    contracts = _contracts(db, c)
    sup_state = supply_state(db, c, ref, contracts)
    service_supply = seg.metrics_kind == rules.MetricsKind.SERVICE and seg.needs_suppliers
    supply_blocked = service_supply and bool(sup_state["missing"])
    if supply_blocked:
        _event(db, c, ref, CompanyEventType.STOCK, "Operação bloqueada: sem fornecedor contratado de "
               + ", ".join(x.label for x in sup_state["missing"]) + ". Vendas zeradas no mês")
    elif sup_state["missing"]:
        _event(db, c, ref, CompanyEventType.STOCK, "Sem fornecedor contratado de " + ", ".join(x.label for x in sup_state["missing"])
               + ": esses itens não serão repostos e o estoque vai zerar")
    if service_supply:
        for sp in sup_state["failed"]:
            _event(db, c, ref, CompanyEventType.STOCK, f"Falha de entrega de {sp.name} ({sp.category}): capacidade do mês reduzida")
    blocked = irregular or supply_blocked or suspended or opening
    if opening:
        _event(db, c, ref, CompanyEventType.MONTH, f"Empresa em abertura/obra: começa a vender em {c.opens_month:%m/%Y}")
    if suspended:
        _event(db, c, ref, CompanyEventType.LEASE, "Empresa sem ponto (despejo): vendas zeradas até mudar de endereço ou o prazo acabar")
    seed = _seed(db, c.user_id)
    econ = economy_service.company_demand_mult(db, c, ref) * cw.market_mult(db, c, ref)   # economia, crises e eventos + tamanho do mercado do país
    fz = cw.company_factor(db, c, ref)                                   # preços e custos do país (câmbio x nível de preços); 1 no Brasil
    reloc = rules.RELOCATION_SALES_MULT if c.relocated_on == ref else 1.0
    qual = float(c.quality)
    plans = plan_units(db, c, seg, ref, marketing=marketing, econ_mult=econ, relocation_mult=reloc, branches=branches)
    staff_cap, equip = staff_capacity(staff), _equipment_factor(db, c)
    multi = len(plans) > 1
    results = []
    for p in plans:
        results.append(rules.sales_month(
            seg, location=p.location, size=c.size, units=1, capacity_level=eff_capacity_level(c), relevance=p.relevance,
            reputation=c.reputation, price=c.price, company_id=p.key, ref=ref, seed=seed, marketing=marketing, staff=staff_cap,
            econ_mult=econ * p.viability, relocation_mult=reloc if p is plans[0] else 1.0, equipment_factor=equip,
            stock_cap=math.inf if multi else stock_cap, irregular=blocked, supply_cap=math.inf if multi else sup_state["cap"],
            quality=qual, marketing_boost=float(c.marketing_boost), people_share=p.share))
    if not multi:
        sales = results[0]
        demand, capacity, potential, sold, stockout = sales.demand, sales.capacity, sales.potential, sales.sold, sales.stockout
        unit_sold = [sold]
    else:                                  # fase 5: matriz + filiais; fornecedores e estoque limitam o TOTAL (rateio proporcional)
        sales = results[0]
        limit = min(sup_state["cap"], stock_cap)
        pot = sum(r.potential for r in results)
        scale = 1.0 if pot <= limit else limit / pot
        unit_sold = [r.sold if scale >= 1.0 else (round(max(r.potential * scale, 0), 2) if seg.fractional else math.floor(max(r.potential * scale + 1e-9, 0)))
                     for r in results]
        demand = sum(r.demand for r in results)
        capacity = min(sum(r.capacity for r in results), sup_state["cap"])
        potential = pot * min(scale, 1.0)
        sold = round(sum(unit_sold), 2) if seg.fractional else sum(unit_sold)
        stockout = bool(stock_cap != math.inf and stock_cap < pot)
    cogs = ZERO
    for i in items:
        used = (D(str(sold)) * i.units_per_sale * (1 + i.waste_pct / 100)).quantize(D("0.001"))
        used = min(used, i.quantity)
        i.quantity -= used
        cogs += used * i.unit_cost
    cogs = quantize_money(cogs)
    # 3) receitas
    qmult = rules.quality_cost_mult(qual)                  # fase 5: qualidade maior encarece os insumos/custos variáveis
    revenue = quantize_money(D(str(sold)) * c.price * fz)
    _post(db, c, ref, kind=FlowKind.INCOME, amount=revenue, desc=f"Vendas do mês ({sold} {seg.unit_label})", line="REVENUE", key=f"{k}:revenue", overdraft=True)
    if service_supply:                  # serviços com fornecedor: o custo variável é o consumo das categorias ao PREÇO CONTRATADO
        variable = ZERO
        for cat in seg.supply_categories:
            sup = contracts.get(cat.key)
            if sup is None:
                continue
            amount = quantize_money(D(str(sold)) * cat.per_sale * sup.unit_price * qmult * fz)
            variable += amount
            _post(db, c, ref, kind=FlowKind.EXPENSE, amount=amount, desc=f"Insumos do serviço: {cat.label} — {sup.name}", line="SUPPLIES",
                  key=f"{k}:supplies:{sup.id}", overdraft=True, origin_ref=_supplier_ref(c, sup))
            _roll_usage(sup, ref)
            sup.volume_used = D(str(sold)) * cat.per_sale
            sup.spend_used = amount
    else:
        variable = quantize_money(revenue * seg.variable_pct / 100 * qmult)
        _post(db, c, ref, kind=FlowKind.EXPENSE, amount=variable, desc="Custos variáveis (frete, taxas, comissões)", line="VARIABLE", key=f"{k}:variable", overdraft=True)
    from backend.services import company_franchise as franchise_svc
    revenue = quantize_money(revenue + franchise_svc.process_month(db, c, ref, k, matriz_sold=unit_sold[0], seed=seed))   # taxas e royalties de franquias
    # 4) folha de pagamento (+ pró-labore, que vira receita PESSOAL do usuário)
    payroll = quantize_money(sum((cw.emp_cost(db, c, e, ref) for e in staff), ZERO))
    _post(db, c, ref, kind=FlowKind.EXPENSE, amount=payroll, desc=f"Folha de pagamento ({len(staff)} funcionários; CLT 2x, PJ 1x)", line="PAYROLL", key=f"{k}:payroll", overdraft=True)
    payroll_staff = payroll
    fine = rules.compliance_fine(seg, missing, c.size) if irregular else ZERO
    if in_grace:
        labels = ", ".join(seg.role(r).label for r in missing)
        _event(db, c, ref, CompanyEventType.COMPLIANCE,
               f"Período de adaptação: faltam {grace} {'mês' if grace == 1 else 'meses'} para contratar {labels}")
        c.compliance_grace_months = grace - 1
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
    rent = quantize_money(_rent(db, c, seg) * fz)
    _post(db, c, ref, kind=FlowKind.EXPENSE, amount=rent, desc="Aluguel", line="RENT", key=f"{k}:rent", overdraft=True)
    if lease and lease.kind == LeaseKind.OWN_GOOD and lease.monthly_rent > 0:
        _post_personal(db, c, ref, kind=FlowKind.INCOME, amount=lease.monthly_rent, desc=f"Aluguel recebido de {c.name}",
                       category="Aluguéis recebidos", key=f"{k}:rent:personal", capital=False)
    fixed_costs = quantize_money(sum((x.amount * (c.units if x.scales_with_units else 1) for x in db.scalars(
        select(CompanyCost).where(CompanyCost.company_id == c.id, CompanyCost.active.is_(True)))), ZERO) * fz)
    _post(db, c, ref, kind=FlowKind.EXPENSE, amount=fixed_costs, desc="Custos fixos (energia, ferramentas, contabilidade)", line="FIXED", key=f"{k}:fixed", overdraft=True)
    rfee = recruiter_fee(db, c)
    if rfee > 0:                                          # contratador (headhunter) opcional: taxa mensal por nível, linha FEES
        rec = active_recruiter(db, c)
        _post(db, c, ref, kind=FlowKind.EXPENSE, amount=rfee, desc=f"Taxa mensal do contratador ({recruiter.tier_of(rec.tier).label})",
              line="FEES", key=f"{k}:recruiter", overdraft=True)
    for a in db.scalars(select(CompanyAide).where(CompanyAide.company_id == c.id, CompanyAide.status == "ACTIVE")):
        _post(db, c, ref, kind=FlowKind.EXPENSE, amount=aides.monthly_fee(a.kind, a.level, c.size),
              desc=f"Taxa mensal: {aides.KIND_LABEL[a.kind].lower()} ({aides.LEVEL_LABEL[a.level]})", line="FEES", key=f"{k}:aide:{a.kind}", overdraft=True)
    asset_costs = ZERO
    for g in db.scalars(select(Good).where(Good.owner_account_id == c.account_id, Good.status == GoodStatus.ACTIVE)):
        for gc in db.scalars(select(GoodCost).where(GoodCost.good_id == g.id)):
            if _cost_due(gc, ref):
                asset_costs += gc.amount
                _post(db, c, ref, kind=FlowKind.EXPENSE, amount=gc.amount, desc=f"{gc.name} — {g.name}", line="ASSET_COSTS",
                      key=f"{k}:goodcost:{gc.id}", overdraft=True)
    # 7) impostos reais (company_taxes): regime escolhido pelo RBT12; encargos da folha já estão no custo CLT de 2x
    if c.country != cw.HOME:                                  # empresa no exterior: tributos do país (IVA + imposto sobre o lucro)
        pre = revenue - cogs - variable - payroll - rent - fixed_costs - asset_costs
        tax = cw.foreign_taxes(c.country, revenue, pre)
    else:
        tax = _compute_month_taxes(db, c, seg, ref, staff, revenue=revenue, payroll=payroll, purchases=cogs)
    taxes = tax.total
    if tax.lines:
        _post(db, c, ref, kind=FlowKind.EXPENSE, amount=taxes, desc=f"Impostos ({company_taxes.REGIME_LABELS[tax.regime]}): "
              + ", ".join(ln.name for ln in tax.lines), line="TAX", key=f"{k}:tax", overdraft=True)
    else:
        _post(db, c, ref, kind=FlowKind.EXPENSE, amount=taxes, desc="Impostos", line="TAX", key=f"{k}:tax", overdraft=True)
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
    # reposição de estoque (pagamento a fornecedores): só com caixa disponível e com CONTRATO ativo da categoria do item
    if c.auto_restock:
        for i in items:
            sup = contracts.get(i.category or "")
            if sup is None:
                continue                                                 # sem fornecedor: não repõe (ruptura; evento acima)
            want = 0 if irregular else min(demand, capacity)             # o que o mercado pediria (mês zerado por sorte não esvazia a reposição)
            need = D(str(max(sold, want) * 1.1)) * i.units_per_sale * (1 + i.waste_pct / 100)
            if i.quantity < max(need * D("0.6"), i.min_quantity):
                price = sup.unit_price * rules.quality_cost_mult(float(c.quality)) * fz
                room = max(rules.storage_cap_qty(seg, c.size, c.units, i, float(c.storage_boost)) - i.quantity, ZERO)      # teto de estoque do porte
                limit_room = volume_left(sup, ref)                                                   # volume que o fornecedor aguenta/contrato permite
                spend_room = spend_left(sup, ref)                                                    # e o gasto máximo do contrato
                if spend_room is not None and price > 0:
                    limit_room = min(limit_room, spend_room / price)
                if not seg.fractional:
                    limit_room = D(math.floor(limit_room))                                           # a compra é arredondada para cima: não estourar o limite
                room = min(room, limit_room)
                buy = min(need - i.quantity, room)
                if buy < sup.min_monthly_order:                           # pedido mínimo: sobe até ele se couber no depósito e nos limites
                    buy = sup.min_monthly_order if room >= sup.min_monthly_order else ZERO
                    if buy == 0 and limit_room < sup.min_monthly_order and limit_note(sup):
                        _event(db, c, ref, CompanyEventType.STOCK,
                               f"Reposição de {i.name} travada pelo limite do contrato com {sup.name} ({limit_note(sup)}): aumente o limite para repor")
                affordable = (max(cash(db, c), ZERO) * D("0.9") / price) if price > 0 else D(0)
                qty = min(buy, affordable)
                if qty >= sup.min_monthly_order and (qty >= 1 or (seg.fractional and qty > 0)):
                    _buy_stock(db, c, i, qty, ref, f"{k}:restock:{i.id}", seg, sup)
    # 9/10) resultados e patrimônio
    db.flush()                                          # a sessão não faz autoflush: estoque e saldo precisam estar no banco
    oneoff = quantize_money(db.scalar(select(func.coalesce(func.sum(LedgerEntry.amount), 0)).where(
        LedgerEntry.company_id == c.id, LedgerEntry.ref_month == ref, LedgerEntry.kind == FlowKind.EXPENSE,
        LedgerEntry.line.in_(["SETUP", "HIRING", "SEVERANCE", "EXPANSION", "MARKETING", "FEES", "RELOCATION"]))))
    variable_total = cogs + variable
    fixed_total = quantize_money(rent + fixed_costs + asset_costs + oneoff)
    operating = quantize_money(revenue - variable_total - fixed_total - payroll)
    net = quantize_money(operating - taxes - interest)
    served = sold >= math.floor(min(demand, capacity)) and not stockout
    ratio = rules.price_ratio(seg, c.price, qual)
    units_detail = _units_detail(db, c, seg, plans, results, unit_sold, revenue=revenue, variable_total=variable_total, payroll_staff=payroll_staff,
                                 operating=operating)
    new_relevance = rules.next_relevance(relevance, sold=unit_sold[0], demand=results[0].demand, reputation=c.reputation, marketing=marketing,
                                         stockout=stockout, price_ratio=ratio, irregular=blocked, quality=qual)
    for p, r, sold_u in list(zip(plans, results, unit_sold))[1:]:        # cada filial evolui com os SEUS números
        p.unit.relevance = D(str(round(rules.next_relevance(
            p.relevance, sold=sold_u, demand=r.demand, reputation=c.reputation, marketing=marketing, stockout=stockout, price_ratio=ratio,
            irregular=blocked, quality=qual), 2)))
    _review_branches(db, c, seg, ref, plans, units_detail)
    balance = cash(db, c)
    loans = db.scalar(select(func.coalesce(func.sum(CompanyLoan.balance), 0)).where(
        CompanyLoan.company_id == c.id, CompanyLoan.status == LoanStatus.ACTIVE))
    c.relevance = D(str(round(new_relevance, 2)))
    c.reputation = rules.next_reputation(c.reputation, served=served, stockout=stockout, irregular=blocked)
    from backend.services import company_ipo
    company_ipo.process_month(db, c, ref, k, seed=seed, sentiment=(econ - 1.0) * 0.08)   # abertura de capital: estreia/preço da ação
    balance = cash(db, c)
    equity = wealth_service.company_equity(db, c)
    row = CompanyMonth(company_id=c.id, ref_month=ref, demand_units=D(str(round(demand, 2))), capacity_units=D(str(round(capacity, 2))),
                       units_sold=D(str(sold)), stockout=stockout, revenue=revenue, variable_costs=variable_total,
                       fixed_costs=fixed_total, payroll=payroll, taxes=taxes, tax_regime=tax.regime, tax_breakdown=tax.breakdown(), interest=quantize_money(interest),
                       operating_result=operating, net_result=net, cash_end=balance,
                       debts_end=quantize_money(loans + max(-balance, ZERO)), equity_end=equity, reputation_end=c.reputation,
                       irregular=irregular, fines=fine, relevance_end=c.relevance, zero_sales=sales.zero_month, units_detail=units_detail)
    db.add(row)
    c.last_processed_month = ref
    _event(db, c, ref, CompanyEventType.MONTH, f"Mês fechado: receita {revenue}, resultado líquido {net}"
           + (" (mês sem nenhuma venda: relevância ainda baixa ou preço fora do mercado)" if sales.zero_month else ""), net)
    db.flush()
    return row


# ------------------------------------------------------------------ consultas agregadas

def user_companies(db: Session, user_id: int) -> list[Company]:
    return list(db.scalars(select(Company).where(Company.user_id == user_id).order_by(Company.id)))
