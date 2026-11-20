"""Vida pessoal e família (etapa 4).

Integração com o resto do simulador:
  * o dinheiro só passa pelo ledger/orçamento: despesas e contribuições viram `BudgetItem` com `source_key`
    `family:*` / `child:<id>:<linha>` / `life:*` (mesmo padrão dos bens) e são lançadas no fechamento do mês;
  * `sync_month` alinha os itens do mês ABERTO com o estado atual (idempotente) — só mexe nas próprias chaves;
  * `process_month` (no fechamento) evolui atributos e relacionamentos; `advance_to_month` (na abertura do mês
    seguinte) aplica mudanças agendadas (moradia, nascimentos, escola), envelhece os filhos e regera os itens;
  * evita dupla contagem: as despesas pessoais do próprio usuário continuam no orçamento dele — a vida pessoal
    só acrescenta o que é novo (filhos, moradia compartilhada, o que passa do nível-base de estilo de vida).
"""
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.core.money import quantize_money
from backend.models import (
    BudgetCategory, BudgetItem, Child, EntryOrigin, FlowKind, LedgerEntry, LifeLog, LifeProfile, Person, Portfolio,
    Relationship, SimMonth, TransactionSource,
)
from backend.services import budget_service, career_rules, finance_ledger, item_sync, pricing
from backend.services import life_rules as R
from backend.services.finance_ledger import ConflictError, FinanceError, NotFoundError

ZERO = Decimal("0.00")


class RelationshipRefused(ConflictError):
    """A pessoa recusou o convite. O efeito (afinidade menor) PRECISA ser gravado mesmo com a resposta de erro."""


OWN_PREFIXES = ("family:", "child:", "life:")


def _clamp(v: float | int, lo: int = 0, hi: int = 100) -> int:
    return int(max(lo, min(hi, round(v))))


def _category(db: Session, user_id: int, kind: FlowKind, name: str) -> BudgetCategory:
    c = db.scalar(select(BudgetCategory).where(
        BudgetCategory.user_id == user_id, BudgetCategory.kind == kind, BudgetCategory.name == name))
    if c is None:
        c = BudgetCategory(user_id=user_id, kind=kind, name=name, sort_order=100)
        db.add(c)
        db.flush()
    return c


def log(db: Session, user_id: int, ref: date, kind: str, text: str, **data) -> None:
    db.add(LifeLog(user_id=user_id, ref_month=ref, kind=kind, text=text[:240], data=data))
    db.flush()


# ------------------------------------------------------------------ perfil
def get_profile(db: Session, user_id: int, *, create: bool = True, lock: bool = False) -> LifeProfile | None:
    q = select(LifeProfile).where(LifeProfile.user_id == user_id)
    p = db.scalar(q.with_for_update() if lock else q)
    if p is None and create:
        p = LifeProfile(user_id=user_id)
        db.add(p)
        db.flush()
    return p


def create_character(db: Session, user_id: int, *, name: str, age_years: int = 28, gender: str | None = None,
                     interested_in: str | None = None) -> LifeProfile:
    if not 18 <= age_years <= 80:
        raise FinanceError("a idade deve estar entre 18 e 80 anos")
    if gender is not None and gender not in ("M", "F", "N"):
        raise FinanceError("sexo inválido (M, F ou N)")
    if interested_in is not None and interested_in not in ("ANY", "M", "F"):
        raise FinanceError("preferência inválida (ANY, M ou F)")
    name = name.strip()
    if not name:
        raise FinanceError("informe o nome")
    p = get_profile(db, user_id)
    p.name, p.age_years = name[:60], age_years
    if gender is not None:
        p.gender = gender
    if interested_in is not None:
        p.interested_in = interested_in
    db.flush()
    return p


def financial_stability(db: Session, user_id: int, month: SimMonth) -> int:
    """Estabilidade financeira 0..100 derivada do caixa em relação às despesas planejadas do mês."""
    cash = db.scalar(select(Portfolio.cash_balance).where(Portfolio.user_id == user_id)) or ZERO
    exp = db.scalar(select(func.coalesce(func.sum(BudgetItem.planned_amount), 0)).where(
        BudgetItem.month_id == month.id, BudgetItem.kind == FlowKind.EXPENSE)) or ZERO
    if exp <= 0:
        return 75 if cash > 0 else 40
    runway = float(cash / exp)
    return 15 if runway < 1 else 40 if runway < 3 else 65 if runway < 6 else 85


def free_hours(p: LifeProfile) -> int:
    studying = career_rules.FIELDS[p.degree_field]["hours"] if p.degree_field else 0          # a faculdade consome horas do mês
    return max(0, R.FREE_HOURS[p.work_level] - R.FAMILY_TIME_HOURS[p.family_time] - studying)


def set_choices(db: Session, user_id: int, month: SimMonth, **choices: str) -> LifeProfile:
    """Define decisões de estilo de vida (jornada, alimentação, saúde, lazer, tempo em família)."""
    budget_service.require_open(month)
    p = get_profile(db, user_id, lock=True)
    for field, value in choices.items():
        if value is None:
            continue
        if field not in R.LEVELS or value not in R.LEVELS[field]:
            raise FinanceError(f"opção inválida para {field}: {value}")
        setattr(p, field, value)
    db.flush()
    sync_month(db, user_id, month)
    return p


# ------------------------------------------------------------------ pessoas e compatibilidade
def compatibility(p: LifeProfile, person: Person, bonus: int = 0) -> int:
    """0..100 — interesses (40%), personalidade (25%), estilo de vida/filhos (20%), idade (15%). Não usa dinheiro."""
    mine = set(p_interests(p))
    theirs = set(person.interests or [])
    jacc = len(mine & theirs) / len(mine | theirs) if (mine | theirs) else 0.0
    pers = R.person_affinity(own_personality(p), person.personality)
    fam_pref = {"LOW": 20, "NORMAL": 50, "HIGH": 80}[p.family_time]
    life = 1 - abs(fam_pref - person.wants_children) / 100
    age = 1 - min(abs(p.age_years - person.age), 15) / 15
    return _clamp(100 * (0.40 * jacc + 0.25 * pers + 0.20 * life + 0.15 * age) + bonus)


def p_interests(p: LifeProfile) -> list[str]:
    return [R.INTERESTS[(int(R.hash01("interest", p.user_id, i) * 100) + i) % len(R.INTERESTS)] for i in range(3)]


def own_personality(p: LifeProfile) -> str:
    return R.pick(R.PERSONALITIES, "pers", p.user_id)


def _generate_person(db: Session, p: LifeProfile, month: date, seq: int, interest_hint: str | None) -> Person:
    u = p.user_id
    gender = p.interested_in if p.interested_in in ("M", "F") else R.pick(["M", "F"], "gender", u, seq)
    first = R.pick(R.NAMES[gender], "name", u, seq)
    last = R.pick(R.LAST_NAMES, "last", u, seq)
    name = f"{first} {last}"
    interests = []
    if interest_hint:
        interests.append(interest_hint)
    for i in range(2):
        it = R.pick(R.INTERESTS, "int", u, seq, i)
        if it not in interests:
            interests.append(it)
    occ_m, occ_f, base = R.pick(R.OCCUPATIONS, "occ", u, seq)
    occ = occ_m if gender == "M" else occ_f
    income = quantize_money(Decimal(base) * Decimal(str(round(0.8 + R.hash01("inc", u, seq) * 0.5, 2))))
    person = Person(
        user_id=u, name=name, gender=gender, age=_clamp(p.age_years + (R.hash01("age", u, seq) - 0.5) * 14, 18, 80),
        personality=R.pick(R.PERSONALITIES, "pers2", u, seq), interests=interests, occupation=occ, income=income,
        assets=quantize_money(income * Decimal(str(round(R.hash01("as", u, seq) * 18, 1)))),
        debts=quantize_money(income * Decimal(str(round(R.hash01("db", u, seq) * 6, 1)))),
        sociability=_clamp(20 + R.hash01("soc", u, seq) * 75), wants_children=_clamp(R.hash01("kids", u, seq) * 100),
        preferences={"likes": interests}, met_month=month)
    db.add(person)
    db.flush()
    return person


# ------------------------------------------------------------------ atividades sociais
def _spend(db: Session, user_id: int, month: SimMonth, p: LifeProfile, *, amount, description: str, category: str,
           key_part: str) -> None:
    amount = quantize_money(Decimal(str(amount)))
    if amount <= 0:
        return
    p.activity_seq += 1
    cat = _category(db, user_id, FlowKind.EXPENSE, category)
    finance_ledger.post_entry(
        db, user_id, kind=FlowKind.EXPENSE, amount=amount, description=description, ref_month=month.ref_month,
        entry_date=month.ref_month, category_id=cat.id, origin=EntryOrigin.FAMILY, origin_ref=key_part,
        idempotency_key=f"life:{key_part}:{month.ref_month:%Y-%m}:{p.activity_seq}", source=TransactionSource.USER)


def _use_hours(p: LifeProfile, hours: int) -> None:
    if p.hours_used + hours > free_hours(p):
        raise ConflictError(f"tempo livre insuficiente neste mês ({free_hours(p) - p.hours_used}h restantes, precisa de {hours}h)")
    p.hours_used += hours


@dataclass
class ActivityResult:
    activity: str
    cost: Decimal
    met: Person | None
    profile: LifeProfile


def do_activity(db: Session, user_id: int, month: SimMonth, key: str) -> ActivityResult:
    budget_service.require_open(month)
    a = R.ACTIVITIES.get(key)
    if a is None:
        raise FinanceError("atividade desconhecida")
    p = get_profile(db, user_id, lock=True)
    _use_hours(p, a["hours"])
    cost = pricing.scale(db, user_id, month.ref_month, "lazer", a["cost"])
    _spend(db, user_id, month, p, amount=cost, description=a["label"], category="Lazer", key_part=f"act:{key}")
    for attr in ("social", "health", "wellbeing", "quality", "satisfaction"):
        if a.get(attr):
            setattr(p, attr, _clamp(getattr(p, attr) + a[attr]))
    met = None
    chance = a["meets"] * (0.6 + p.social / 100)
    if R.hash01("meet", user_id, month.ref_month.isoformat(), p.activity_seq, key) < chance:
        met = _generate_person(db, p, month.ref_month, p.activity_seq, a.get("interest"))
        db.add(Relationship(user_id=user_id, person_id=met.id, stage="ACQUAINTANCE", affinity=20 + min(10, compatibility(p, met) // 10),
                            trust=20, since_month=month.ref_month, stage_since=month.ref_month))
        log(db, user_id, month.ref_month, "MET", f"Você conheceu {met.name} ({met.occupation}) em: {a['label']}", person_id=met.id)
    db.flush()
    return ActivityResult(key, cost, met, p)


# ------------------------------------------------------------------ relacionamentos
def get_relationship(db: Session, user_id: int, person_id: int, *, lock: bool = False) -> Relationship:
    q = select(Relationship).where(Relationship.user_id == user_id, Relationship.person_id == person_id)
    r = db.scalar(q.with_for_update() if lock else q)
    if r is None:
        raise NotFoundError("relacionamento não encontrado")
    return r


def active_partner(db: Session, user_id: int) -> Relationship | None:
    return db.scalar(select(Relationship).where(
        Relationship.user_id == user_id, Relationship.stage.in_(R.PARTNER_STAGES)))


def _bump(r: Relationship, delta: int, trust: int = 0) -> None:
    r.affinity = _clamp(r.affinity + delta)
    r.trust = _clamp(r.trust + trust)


def interact(db: Session, user_id: int, month: SimMonth, person_id: int, key: str) -> Relationship:
    budget_service.require_open(month)
    it = R.INTERACTIONS.get(key)
    if it is None:
        raise FinanceError("interação desconhecida")
    r = get_relationship(db, user_id, person_id, lock=True)
    if r.stage == "ENDED":
        raise ConflictError("este relacionamento já foi encerrado")
    p = get_profile(db, user_id, lock=True)
    person = db.get(Person, person_id)
    _use_hours(p, it["hours"])
    _spend(db, user_id, month, p, amount=pricing.scale(db, user_id, month.ref_month, "lazer", it["cost"]),
           description=f"{it['label']} com {person.name}", category="Lazer", key_part=f"int:{person_id}:{key}")
    # conviver aproxima: cada atividade soma à compatibilidade; fazer algo do interesse dela(e) soma mais
    bonus = R.COMPAT_BONUS_MATCH if it.get("interest") in (person.interests or []) else R.COMPAT_BONUS_BASE
    r.compat_bonus = min(R.COMPAT_BONUS_CAP, r.compat_bonus + bonus)
    comp = compatibility(p, person, r.compat_bonus)
    # afinidade cresce mais com compatibilidade alta; programas gratuitos funcionam (só rendem um pouco menos)
    gain = it["gain"] * (0.5 + comp / 100)
    _bump(r, round(gain), trust=1 + (1 if r.interactions_month == 0 else 0))
    r.interactions_month += 1
    r.last_interaction_month = month.ref_month
    p.social = _clamp(p.social + 1)
    p.wellbeing = _clamp(p.wellbeing + 1)
    db.flush()
    return r


def _months_in_stage(r: Relationship, month: SimMonth) -> int:
    return budget_service.months_between(r.stage_since, month.ref_month)


def advance_relationship(db: Session, user_id: int, month: SimMonth, person_id: int, action: str) -> Relationship:
    """action: befriend | date | cohabit | marry | end."""
    budget_service.require_open(month)
    r = get_relationship(db, user_id, person_id, lock=True)
    person = db.get(Person, person_id)
    p = get_profile(db, user_id, lock=True)
    ref = month.ref_month
    if r.stage == "ENDED":
        raise ConflictError("este relacionamento já foi encerrado")

    def go(stage: str, text: str) -> Relationship:
        r.stage, r.stage_since = stage, ref
        log(db, user_id, ref, stage, text, person_id=person_id)
        db.flush()
        return r

    PENALTY = {"befriend": 3, "date": 5, "cohabit": 6, "marry": 8}

    def refuse(why: str):
        """Ser recusado machuca a relação: a afinidade (e um pouco da confiança) cai e isso fica gravado."""
        _bump(r, -PENALTY.get(action, 3), trust=-2)
        db.flush()
        raise RelationshipRefused(f"{why}. A afinidade com {person.name} diminuiu.")

    if action == "end":
        was_household = r.stage in R.HOUSEHOLD_STAGES
        r.ended_month = ref
        r.finance_mode = "SEPARATE"
        go("ENDED", f"Você encerrou o relacionamento com {person.name}")
        if was_household:
            p.wellbeing = _clamp(p.wellbeing - 8)
            p.satisfaction = _clamp(p.satisfaction - 6)
        else:
            p.wellbeing = _clamp(p.wellbeing - 2)
        sync_month(db, user_id, month)
        return r
    comp = compatibility(p, person, r.compat_bonus)
    if action == "befriend":
        if r.stage != "ACQUAINTANCE":
            raise ConflictError("vocês já são mais do que conhecidos")
        if r.affinity < 35:
            refuse(f"{person.name} ainda não tem intimidade suficiente: convivam mais")
        return go("FRIEND", f"{person.name} agora é seu amigo(a)")
    if action == "date":
        if r.stage != "FRIEND":
            raise ConflictError("só é possível iniciar namoro com um amigo(a)")
        if active_partner(db, user_id):
            raise ConflictError("você já está em um relacionamento")
        if r.affinity < 55 or r.trust < 40 or comp < 40:
            refuse(f"{person.name} não correspondeu (afinidade/confiança/compatibilidade insuficientes)")
        return go("DATING", f"Você começou a namorar {person.name}")
    if action == "cohabit":
        if r.stage != "DATING":
            raise ConflictError("só é possível morar junto durante o namoro")
        if _months_in_stage(r, month) < R.MIN_MONTHS_TO_COHABIT or r.affinity < 65 or r.trust < 55:
            refuse("o relacionamento ainda não está maduro para morarem juntos")
        return go("COHABITING", f"Você e {person.name} passaram a viver juntos")
    if action == "marry":
        if r.stage not in ("DATING", "COHABITING"):
            raise ConflictError("só é possível casar durante um namoro ou união estável")
        if _months_in_stage(r, month) < R.MIN_MONTHS_TO_MARRY and budget_service.months_between(r.since_month, ref) < 8:
            refuse("é cedo para casar: o relacionamento precisa de mais tempo")
        if r.affinity < 70 or r.trust < 60 or comp < 45:
            refuse(f"{person.name} recusou o pedido")
        return go("MARRIED", f"Você se casou com {person.name}")
    raise FinanceError("ação desconhecida")


def set_finance_rules(db: Session, user_id: int, month: SimMonth, person_id: int, *, mode: str,
                      contribution_pct: Decimal | None = None) -> Relationship:
    """Administração financeira do casal: SEPARATE (cada um com o seu) ou SHARED (parceiro contribui com % das despesas comuns)."""
    budget_service.require_open(month)
    r = get_relationship(db, user_id, person_id, lock=True)
    if r.stage not in R.HOUSEHOLD_STAGES:
        raise ConflictError("a administração conjunta exige união estável ou casamento")
    if mode not in ("SEPARATE", "SHARED"):
        raise FinanceError("modo inválido")
    if contribution_pct is not None:
        if not Decimal(0) <= contribution_pct <= 100:
            raise FinanceError("a contribuição deve estar entre 0 e 100%")
        r.contribution_pct = quantize_money(contribution_pct)
    r.finance_mode = mode
    db.flush()
    sync_month(db, user_id, month)
    return r


# ------------------------------------------------------------------ filhos
def child_age_years(c: Child, ref: date) -> int:
    return budget_service.months_between(c.birth_month, ref) // 12


def plan_child(db: Session, user_id: int, month: SimMonth) -> LifeProfile:
    budget_service.require_open(month)
    p = get_profile(db, user_id, lock=True)
    if p.pregnancy_due_month:
        raise ConflictError("já existe uma gestação em andamento")
    r = active_partner(db, user_id)
    if r is None or r.stage not in R.HOUSEHOLD_STAGES:
        raise ConflictError("planejar filhos exige um parceiro(a) em união estável ou casamento")
    person = db.get(Person, r.person_id)
    if person.wants_children < 25:
        raise ConflictError(f"{person.name} não quer ter filhos no momento")
    p.pregnancy_due_month = budget_service.shift_month(month.ref_month, R.PREGNANCY_MONTHS)
    p.pregnancy_relationship_id = r.id
    log(db, user_id, month.ref_month, "PREGNANCY", f"Vocês estão esperando um bebê (nascimento previsto: {p.pregnancy_due_month:%m/%Y})")
    return p


def update_child(db: Session, user_id: int, month: SimMonth, child_id: int, *, school_kind: str | None = None,
                 daycare: bool | None = None, activities: bool | None = None) -> Child:
    budget_service.require_open(month)
    c = db.get(Child, child_id)
    if c is None or c.user_id != user_id:
        raise NotFoundError("filho(a) não encontrado")
    if school_kind is not None:
        if school_kind not in ("PUBLIC", "PRIVATE"):
            raise FinanceError("tipo de escola inválido")
        if school_kind != c.school_kind:
            log(db, user_id, month.ref_month, "SCHOOL_CHANGE", f"{c.name} mudou para a escola {'particular' if school_kind == 'PRIVATE' else 'pública'}")
        c.school_kind = school_kind
    if daycare is not None:
        c.daycare = daycare
    if activities is not None:
        c.activities = activities
    db.flush()
    sync_month(db, user_id, month)
    return c


def children(db: Session, user_id: int, *, active_only: bool = True) -> list[Child]:
    q = select(Child).where(Child.user_id == user_id).order_by(Child.id)
    if active_only:
        q = q.where(Child.active.is_(True))
    return list(db.scalars(q))


def child_lines(c: Child, ref: date) -> dict[str, int]:
    """Custos mensais de referência por linha, conforme a idade e as escolhas (sem índice de preços)."""
    age = child_age_years(c, ref)
    if age >= 18:
        return {}
    band = next(b for top, b in R.CHILD_BANDS if age <= top)
    lines = {k: v for k, v in band.items() if k != "name" and v > 0}
    edu = next(e for e in R.EDUCATION.values() if e[0] <= age <= e[1])
    if age <= 2:
        if c.daycare:
            lines["education"] = edu[2]
    else:
        lines["education"] = edu[3] if c.school_kind == "PRIVATE" else edu[2]
    if c.activities and age >= R.ACTIVITIES_COST["min_age"]:
        lines["leisure"] = lines.get("leisure", 0) + R.ACTIVITIES_COST["cost"]
    return lines


# ------------------------------------------------------------------ carreira e faculdade
def _field(key: str) -> dict:
    f = career_rules.FIELDS.get(key)
    if f is None:
        raise FinanceError("área de atuação desconhecida")
    return f


def set_initial_field(db: Session, user_id: int, month: SimMonth, field: str) -> LifeProfile:
    _field(field)
    p = get_profile(db, user_id)
    p.career_field, p.career_since = field, month.ref_month
    db.flush()
    return p


def change_career(db: Session, user_id: int, month: SimMonth, field: str) -> LifeProfile:
    """Muda de área a partir do mês seguinte. Com diploma na área nova o salário sobe (prêmio da formação); sem diploma, recomeça por baixo."""
    budget_service.require_open(month)
    new = _field(field)
    p = get_profile(db, user_id, lock=True)
    if p.career_field == field:
        raise ConflictError("você já atua nessa área")
    if p.pending_career:
        raise ConflictError("já existe uma mudança de área agendada")
    old = career_rules.FIELDS.get(p.career_field or career_rules.DEFAULT_FIELD)
    ratio = new["start"] / old["start"]
    degree = field in (p.degrees or [])
    factor = ratio * ((1 + new["premium"] / 100) if degree else career_rules.NO_DEGREE_SWITCH)
    p.pending_career = {"field": field, "factor": round(factor, 4), "degree": degree}
    log(db, user_id, month.ref_month, "CAREER_PLANNED",
        f"Você vai mudar para {new['label']} no mês que vem ({'com diploma' if degree else 'sem diploma: recomeço por baixo'}, salário {'+' if factor >= 1 else ''}{(factor - 1) * 100:.0f}%)")
    db.flush()
    return p


def enroll_degree(db: Session, user_id: int, month: SimMonth, field: str) -> LifeProfile:
    budget_service.require_open(month)
    f = _field(field)
    p = get_profile(db, user_id, lock=True)
    if p.degree_field:
        raise ConflictError("você já está cursando uma faculdade")
    if field in (p.degrees or []):
        raise ConflictError("você já se formou nessa área")
    if len(p.degrees or []) >= career_rules.MAX_DEGREES:
        raise ConflictError("limite de formações atingido")
    p.degree_field, p.degree_progress, p.degree_total = field, 0, f["months"]
    log(db, user_id, month.ref_month, "DEGREE_START", f"Você começou a faculdade de {f['degree']} ({f['months']} meses)")
    db.flush()
    sync_month(db, user_id, month)
    return p


def drop_degree(db: Session, user_id: int, month: SimMonth) -> LifeProfile:
    budget_service.require_open(month)
    p = get_profile(db, user_id, lock=True)
    if not p.degree_field:
        raise ConflictError("você não está cursando faculdade")
    log(db, user_id, month.ref_month, "DEGREE_DROP", f"Você trancou a faculdade de {career_rules.FIELDS[p.degree_field]['degree']}")
    p.degree_field, p.degree_progress, p.degree_total = None, 0, 0
    db.flush()
    sync_month(db, user_id, month)
    return p


def _apply_salary_factor(db: Session, user_id: int, effective: date, factor: float) -> int:
    """Cria (ou compõe) a nova versão do salário a partir de `effective`: o contrato muda de verdade, o histórico fica."""
    from backend.models import RecurringItem, RecurringItemVersion
    cat = db.scalar(select(BudgetCategory.id).where(BudgetCategory.user_id == user_id, BudgetCategory.kind == FlowKind.INCOME,
                                                    BudgetCategory.name == "Salário"))
    n = 0
    if cat is None:
        return n
    for r in db.scalars(select(RecurringItem).where(RecurringItem.user_id == user_id, RecurringItem.category_id == cat, RecurringItem.active.is_(True))):
        existing = db.scalar(select(RecurringItemVersion).where(RecurringItemVersion.item_id == r.id, RecurringItemVersion.effective_from == effective))
        if existing is not None:
            existing.amount = quantize_money(existing.amount * Decimal(str(factor)))
            n += 1
            continue
        cur = budget_service.version_amount(db, r.id, effective)
        if cur:
            db.add(RecurringItemVersion(item_id=r.id, amount=quantize_money(cur * Decimal(str(factor))), effective_from=effective))
            n += 1
    db.flush()
    return n


def apply_career_changes(db: Session, user_id: int, new_month: SimMonth) -> None:
    """Abertura do mês (ANTES de gerar os itens): mudança de área agendada e reajuste anual da área. Idempotente."""
    p = get_profile(db, user_id, create=False, lock=True)
    if p is None:
        return
    ref = new_month.ref_month
    factor = 1.0
    if p.pending_career:
        pc = p.pending_career
        factor *= pc["factor"]
        p.career_field, p.career_since, p.pending_career = pc["field"], ref, None
        log(db, user_id, ref, "CAREER_CHANGED", f"Você agora atua em {career_rules.FIELDS[p.career_field]['label']}")
    elif p.career_field and p.career_since and p.last_raise_month != ref and budget_service.months_between(p.career_since, ref) > 0 \
            and budget_service.months_between(p.career_since, ref) % 12 == 0:
        pct = career_rules.FIELDS[p.career_field]["growth"] + (1.0 if p.wellbeing >= 70 else -1.0 if p.wellbeing < 35 else 0.0)
        factor *= 1 + pct / 100
        p.last_raise_month = ref
        log(db, user_id, ref, "RAISE", f"Reajuste anual de {pct:.1f}% em {career_rules.FIELDS[p.career_field]['label']}")
    if factor != 1.0:
        _apply_salary_factor(db, user_id, ref, factor)


# ------------------------------------------------------------------ moradia
def move(db: Session, user_id: int, month: SimMonth, *, kind: str, monthly_cost: Decimal) -> LifeProfile:
    """Agenda a mudança para o PRÓXIMO mês: os custos antigos terminam e os novos começam lá."""
    budget_service.require_open(month)
    if kind not in R.HOUSING_KINDS:
        raise FinanceError("tipo de moradia inválido")
    monthly_cost = quantize_money(monthly_cost)
    if kind == "EXISTING":
        monthly_cost = ZERO
    elif monthly_cost <= 0 and kind != "FAMILY_HOME":
        raise FinanceError("informe o custo mensal da nova moradia")
    p = get_profile(db, user_id, lock=True)
    p.pending_housing_kind, p.pending_housing_cost = kind, monthly_cost
    p.pending_housing_month = budget_service.shift_month(month.ref_month, 1)
    log(db, user_id, month.ref_month, "MOVE_PLANNED", f"Mudança de residência agendada para {p.pending_housing_month:%m/%Y}")
    db.flush()
    return p


# ------------------------------------------------------------------ orçamento: itens gerados pela vida pessoal
def _want_builder(db: Session, user_id: int, ref: date):
    desired: dict[str, dict] = {}

    def want(key, name, kind, cat, amount):
        amount = quantize_money(Decimal(str(amount)))
        if amount > 0:
            desired[key] = {"name": name[:80], "kind": kind, "cat": cat, "amount": amount}
    return desired, want


def sync_month(db: Session, user_id: int, month: SimMonth) -> None:
    """Alinha os itens do orçamento do mês ABERTO com a vida pessoal (idempotente; só mexe nas chaves próprias)."""
    if month.status.value != "OPEN":
        return
    p = get_profile(db, user_id, create=False)
    if p is None:
        return
    ref = month.ref_month
    desired, want = _want_builder(db, user_id, ref)
    scale = lambda cat, amt: pricing.scale(db, user_id, ref, cat, amt)          # noqa: E731

    # estilo de vida: só o que passa do nível-base (o resto já está no orçamento do usuário)
    for fld, cat_name, price_cat in (("food_level", "Alimentação", "alimentacao"), ("health_level", "Saúde", "saude"),
                                     ("leisure_level", "Lazer", "lazer")):
        extra = R.LEVELS[fld][getattr(p, fld)]["extra"] - R.BASELINE_EXTRA[fld]
        if extra > 0:
            want(f"life:style:{fld}", f"Estilo de vida: {R.LEVELS[fld][getattr(p, fld)] and getattr(p, fld).lower()} ({cat_name.lower()})",
                 FlowKind.EXPENSE, cat_name, scale(price_cat, extra))
    # jornada: variação de renda sobre os salários do orçamento
    pct = R.LEVELS["work_level"][p.work_level]["income_pct"]
    if pct:
        salary = db.scalar(select(func.coalesce(func.sum(BudgetItem.planned_amount), 0)).join(
            BudgetCategory, BudgetCategory.id == BudgetItem.category_id).where(
            BudgetItem.month_id == month.id, BudgetItem.recurring_item_id.is_not(None), BudgetItem.kind == FlowKind.INCOME,
            BudgetCategory.name == "Salário")) or ZERO
        if salary > 0 and pct > 0:
            want("life:work_adjust", "Horas extras (jornada intensa)", FlowKind.INCOME, "Renda extra", salary * pct / 100)
        elif salary > 0:
            want("life:work_adjust", "Renda a menos (jornada reduzida)", FlowKind.EXPENSE, "Outros", salary * abs(pct) / 100)

    shared_total = ZERO
    if p.housing_kind != "EXISTING" and p.housing_cost > 0:
        amt = scale("moradia", p.housing_cost)
        want("family:housing", "Moradia (família)", FlowKind.EXPENSE, "Moradia", amt)
        shared_total += amt
    if p.pending_housing_month == ref:   # custo único da mudança
        want(f"life:move:{ref:%Y-%m}", "Mudança de residência", FlowKind.EXPENSE, "Moradia", scale("moradia", 600))
    for c in children(db, user_id):
        for line, base in child_lines(c, ref).items():
            cat_name, price_cat = R.LINE_CATEGORY[line]
            amt = scale(price_cat, base)
            want(f"child:{c.id}:{line}", f"{c.name} — {R.LINE_LABEL[line].lower()}", FlowKind.EXPENSE, cat_name, amt)
            shared_total += amt
        if c.birth_month == ref:
            want(f"life:birth:{c.id}", f"Parto e enxoval — {c.name}", FlowKind.EXPENSE, "Saúde", scale("saude", R.BIRTH_COST))
    if p.degree_field:
        want("life:tuition", f"Mensalidade — {career_rules.FIELDS[p.degree_field]['degree']}", FlowKind.EXPENSE, "Educação",
             scale("educacao", career_rules.FIELDS[p.degree_field]["cost"]))
    if p.health < 30:
        want(f"life:medical:{ref:%Y-%m}", "Despesa médica (saúde debilitada)", FlowKind.EXPENSE, "Saúde", scale("saude", R.MEDICAL_CRISIS_COST))

    partner = active_partner(db, user_id)
    if partner and partner.stage in R.HOUSEHOLD_STAGES and partner.finance_mode == "SHARED" and shared_total > 0:
        person = db.get(Person, partner.person_id)
        cap = max(ZERO, person.income * Decimal("0.5") - person.debts * Decimal("0.01"))
        contribution = min(cap, shared_total * partner.contribution_pct / 100)
        want("family:partner:contribution", f"Contribuição de {person.name} às despesas comuns", FlowKind.INCOME,
             "Outras receitas", contribution)

    item_sync.reconcile(db, user_id, month, desired, OWN_PREFIXES)


# ------------------------------------------------------------------ ciclo mensal
def process_month(db: Session, user_id: int, month: SimMonth) -> None:
    """Fechamento: evolui atributos e relacionamentos do mês que termina (uma vez por mês)."""
    p = get_profile(db, user_id, create=False, lock=True)
    ref = month.ref_month
    if p is None or p.last_processed_month == ref:
        return
    stability = financial_stability(db, user_id, month)
    d = {"health": 0.0, "wellbeing": 0.0, "quality": 0.0, "satisfaction": 0.0}
    for fld in R.LEVELS:
        for k in d:
            d[k] += R.LEVELS[fld][getattr(p, fld)].get(k, 0)
    if stability < 30:
        d["wellbeing"] -= 2
        d["satisfaction"] -= 1
    elif stability >= 70:
        d["wellbeing"] += 1
    if free_hours(p) < 15:
        d["wellbeing"] -= 1
    if p.health < 30:
        d["wellbeing"] -= 2
    p.health = _clamp(p.health + d["health"])
    p.wellbeing = _clamp(p.wellbeing + d["wellbeing"])
    social_gain = -1 if p.hours_used == 0 else 0
    p.social = _clamp(p.social + social_gain)
    target_quality = 0.4 * p.wellbeing + 0.3 * p.health + 0.15 * stability + 0.15 * p.social
    p.quality = _clamp(p.quality + max(-3, min(3, target_quality - p.quality)) + d["quality"])
    target_sat = (p.wellbeing + p.quality) / 2
    p.satisfaction = _clamp(p.satisfaction + max(-3, min(3, target_sat - p.satisfaction)) + d["satisfaction"])

    for r in db.scalars(select(Relationship).where(Relationship.user_id == user_id, Relationship.stage != "ENDED")):
        person = db.get(Person, r.person_id)
        comp = compatibility(p, person, r.compat_bonus)
        drift = 0
        if r.interactions_month == 0:
            idle = budget_service.months_between(r.last_interaction_month or r.since_month, ref)       # meses sem fazer nada juntos
            drift -= (3 if r.stage in R.PARTNER_STAGES else 2) + min(3, max(0, idle - 1) // 2)           # quanto mais tempo, mais esfria
        if comp >= 65 and p.family_time != "LOW" and r.stage in R.PARTNER_STAGES:
            drift += 1
        if comp < 35:
            drift -= 1
        if r.stage in R.PARTNER_STAGES and free_hours(p) < 15:
            drift -= 1
        _bump(r, drift, trust=1 if r.interactions_month else -1)
        r.interactions_month = 0
        if r.affinity <= 10 and r.stage != "ACQUAINTANCE":
            r.stage, r.stage_since, r.ended_month, r.finance_mode = "ENDED", ref, ref, "SEPARATE"
            log(db, user_id, ref, "DRIFT_APART", f"O relacionamento com {person.name} esfriou e acabou")
    for c in children(db, user_id):
        c.development = _clamp(c.development + (1 if c.school_kind == "PRIVATE" else 0) + (1 if c.activities else 0)
                               + {"LOW": -1, "NORMAL": 0, "HIGH": 1}[p.family_time])
        c.health = _clamp(c.health + (1 if p.health_level == "PLUS" else 0) - (1 if p.health_level == "NONE" else 0))
    if p.degree_field:                                  # faculdade: um mês cursado; ao final, formatura
        p.degree_progress += 1
        if p.degree_progress >= p.degree_total:
            f = career_rules.FIELDS[p.degree_field]
            p.degrees = list(p.degrees or []) + [p.degree_field]
            p.satisfaction = _clamp(p.satisfaction + 8)
            log(db, user_id, ref, "GRADUATED", f"Você se formou em {f['degree']}! Agora pode mudar de área e ganhar mais.")
            p.degree_field, p.degree_progress, p.degree_total = None, 0, 0
    p.hours_used = 0
    p.last_processed_month = ref
    db.flush()


def advance_to_month(db: Session, user_id: int, new_month: SimMonth) -> None:
    """Abertura do mês seguinte: mudanças agendadas, nascimentos, marcos escolares e geração dos itens."""
    p = get_profile(db, user_id, create=False, lock=True)
    if p is None:
        return
    ref = new_month.ref_month
    if p.pending_housing_month is not None and p.pending_housing_month <= ref:
        p.housing_kind, p.housing_cost = p.pending_housing_kind, p.pending_housing_cost
        log(db, user_id, ref, "MOVED", f"Você mudou de residência ({p.housing_kind.lower()}, custo mensal {p.housing_cost})")
        # o custo único da mudança (life:move:<mês>) é gerado em sync_month neste mesmo mês
    if p.pregnancy_due_month is not None and p.pregnancy_due_month <= ref:
        name = R.pick(R.CHILD_NAMES, "child", user_id, db.scalar(select(func.count(Child.id)).where(Child.user_id == user_id)))
        child = Child(user_id=user_id, relationship_id=p.pregnancy_relationship_id, name=name, birth_month=ref)
        db.add(child)
        db.flush()
        p.pregnancy_due_month = p.pregnancy_relationship_id = None
        p.wellbeing = _clamp(p.wellbeing + 3)
        log(db, user_id, ref, "BIRTH", f"Nasceu {name}!", child_id=child.id)
    for c in children(db, user_id):
        age_m = budget_service.months_between(c.birth_month, ref)
        if age_m > 0 and age_m % 12 == 0:
            age = age_m // 12
            log(db, user_id, ref, "BIRTHDAY", f"{c.name} fez {age} anos", child_id=c.id)
            if age == 3:
                log(db, user_id, ref, "SCHOOL_ENTRY", f"{c.name} entrou na escola (educação infantil)", child_id=c.id)
            elif age == 6:
                log(db, user_id, ref, "SCHOOL_ENTRY", f"{c.name} começou o ensino fundamental", child_id=c.id)
            elif age == 12:
                log(db, user_id, ref, "SCHOOL_ENTRY", f"{c.name} começou o ensino médio/fundamental II", child_id=c.id)
            elif age >= 18:
                c.active = False
                log(db, user_id, ref, "EMANCIPATED", f"{c.name} completou 18 anos: despesas dependentes encerradas", child_id=c.id)
    if ref.month == 1 and p.last_processed_month and p.last_processed_month < ref:
        p.age_years += 1
    sync_month(db, user_id, new_month)
    if p.pending_housing_month is not None and p.pending_housing_month <= ref:
        p.pending_housing_kind = p.pending_housing_cost = p.pending_housing_month = None
    db.flush()


def pending_decisions(db: Session, user_id: int, month: SimMonth) -> list[dict]:
    """Decisões que o usuário pode/deve tomar agora (derivadas do estado real)."""
    p = get_profile(db, user_id, create=False)
    out: list[dict] = []
    if p is None:
        return out
    if p.pending_housing_month:
        out.append({"key": "housing", "text": f"Mudança de residência prevista para {p.pending_housing_month:%m/%Y}"})
    for c in children(db, user_id):
        age = child_age_years(c, month.ref_month)
        if age in (2, 5, 11) and budget_service.months_between(c.birth_month, month.ref_month) % 12 >= 9:
            out.append({"key": f"school:{c.id}", "text": f"{c.name} está perto de mudar de etapa escolar: revise escola e atividades"})
    for r in db.scalars(select(Relationship).where(Relationship.user_id == user_id, Relationship.stage != "ENDED")):
        person = db.get(Person, r.person_id)
        if r.stage == "ACQUAINTANCE" and r.affinity >= 35:
            out.append({"key": f"befriend:{person.id}", "text": f"Você e {person.name} já têm intimidade para virar amigos"})
        elif r.stage == "FRIEND" and r.affinity >= 55 and r.trust >= 40 and not active_partner(db, user_id):
            out.append({"key": f"date:{person.id}", "text": f"Há clima com {person.name}: convidar para sair?"})
        elif r.stage == "DATING" and _months_in_stage(r, month) >= R.MIN_MONTHS_TO_MARRY and r.affinity >= 70:
            out.append({"key": f"marry:{person.id}", "text": f"O relacionamento com {person.name} está maduro para o próximo passo"})
    if p.health < 40:
        out.append({"key": "health", "text": "Sua saúde está baixa: considere investir em saúde ou reduzir a jornada"})
    return out
