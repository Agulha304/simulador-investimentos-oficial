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

import math
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.core.money import quantize_money
from backend.models import (
    BudgetCategory, BudgetItem, Child, EntryOrigin, FlowKind, LedgerEntry, LifeLog, LifeProfile, Person, Portfolio,
    Relationship, SimMonth, TransactionSource,
)
from backend.services import budget_service, career_rules, finance_ledger, housing_service, item_sync, pricing
from backend.services import life_rules as R
from backend.services import university_rules as uni_rules
from backend.services.finance_ledger import ConflictError, FinanceError, NotFoundError

ZERO = Decimal("0.00")
D_ = Decimal
D1 = Decimal("1.00")


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
    return max(0, raw_free_hours(p))                                                         # faculdade e gestão consomem horas do mês


def raw_free_hours(p: LifeProfile) -> int:
    """Horas livres do mês SEM cortar em zero: negativo = você assumiu mais compromissos do que o seu tempo permite."""
    studying = int(round(career_rules.FIELDS[p.degree_field]["hours"] * uni_rules.get(p.degree_uni or uni_rules.OPEN_KEY).load)) if p.degree_field else 0
    return R.FREE_HOURS[p.work_level] - R.FAMILY_TIME_HOURS[p.family_time] - studying - p.hours_committed - (p.career_hours or 0)


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


def _used_first_names(db: Session, user_id: int) -> set[str]:
    names = {n.split()[0].lower() for n in db.scalars(select(Person.name).where(Person.user_id == user_id))}
    names |= {n.split()[0].lower() for n in db.scalars(select(Child.name).where(Child.user_id == user_id))}
    return names


def _pick_age(p: LifeProfile, u: int, seq: int) -> int:
    r = R.hash01("agekind", u, seq)
    if r < 0.50:
        base = p.age_years + (R.hash01("age1", u, seq) - 0.5) * 16             # perto da sua idade
    elif r < 0.80:
        base = p.age_years + (R.hash01("age2", u, seq) - 0.5) * 32
    else:
        base = 18 + R.hash01("age3", u, seq) * 55                              # qualquer adulto
    return _clamp(base, 18, 80)


def _financial_profile(income: Decimal, u: int, seq: int) -> tuple[Decimal, Decimal, str]:
    total = sum(w for _, w, _, _ in R.FINANCE_ARCHETYPES)
    r, acc = R.hash01("fin", u, seq) * total, 0
    for name, w, (a_lo, a_hi), (d_lo, d_hi) in R.FINANCE_ARCHETYPES:
        acc += w
        if r <= acc:
            break
    ma = a_lo + R.hash01("fa", u, seq) * (a_hi - a_lo)
    md = d_lo + R.hash01("fd", u, seq) * (d_hi - d_lo)
    base = max(income, Decimal(1500))
    return quantize_money(base * Decimal(str(round(ma, 2)))), quantize_money(base * Decimal(str(round(md, 2)))), name


def _generate_person(db: Session, p: LifeProfile, month: date, seq: int, interest_hint: str | None, *, where: str | None = None) -> Person:
    """Pessoa nova com nome (sem repetir primeiro nome já conhecido), sexo, idade, profissão, interesses e situação financeira variados."""
    u = p.user_id
    used = _used_first_names(db, u)
    attempt = first = gender = None
    for k in range(60):
        attempt = seq * 61 + k
        gender = p.interested_in if p.interested_in in ("M", "F") else R.pick(["M", "F"], "gender", u, attempt)
        first = R.pick(R.NAMES[gender], "name", u, attempt)
        if first.lower() not in used:
            break
    last = R.pick(R.LAST_NAMES, "last", u, attempt)
    name = f"{first} {last}"
    age = _pick_age(p, u, attempt)
    interests = [interest_hint] if interest_hint else []
    for i in range(2 + int(R.hash01("nint", u, attempt) * 3)):                  # 2 a 4 interesses
        it = R.pick(R.INTERESTS, "int", u, attempt, i)
        if it not in interests:
            interests.append(it)
    r = R.hash01("job", u, attempt)
    if age >= 62 and r < 0.55:
        occ_m, occ_f, base = R.RETIRED
    elif age <= 24 and r < 0.45:
        occ_m, occ_f, base = R.STUDENT
    elif r > 0.965:
        occ_m, occ_f, base = R.JOBSEEKER
    else:
        occ_m, occ_f, base = R.pick(R.OCCUPATIONS, "occ", u, attempt)
    income = quantize_money(Decimal(base) * Decimal(str(round(0.8 + R.hash01("inc", u, attempt) * 0.5, 2))))
    assets, debts, _label = _financial_profile(income, u, attempt)
    person = Person(
        user_id=u, name=name, gender=gender, age=age, personality=R.pick(R.PERSONALITIES, "pers2", u, attempt), interests=interests,
        occupation=occ_m if gender == "M" else occ_f, income=income, assets=assets, debts=debts,
        sociability=_clamp(20 + R.hash01("soc", u, attempt) * 75), wants_children=_clamp(R.hash01("kids", u, attempt) * 100),
        preferences={"likes": interests, "met_at": where or ""}, met_month=month)
    db.add(person)
    db.flush()
    return person


def meet_person(db: Session, p: LifeProfile, month: date, *, where: str, interest: str | None = None) -> Person:
    """Conhece alguém novo (atividade, faculdade ou uma decisão do mês): vira conhecido(a) e fica registrado."""
    p.activity_seq += 1
    met = _generate_person(db, p, month, p.activity_seq, interest, where=where)
    db.add(Relationship(user_id=p.user_id, person_id=met.id, stage="ACQUAINTANCE", affinity=20 + min(10, compatibility(p, met) // 10), trust=20,
                        since_month=month, stage_since=month))
    log(db, p.user_id, month, "MET", f"Você conheceu {met.name} ({met.occupation.lower()}, {met.age} anos) {where}", person_id=met.id)
    db.flush()
    return met


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


def spend_hours(p: LifeProfile, hours: int, label: str = "Outras atividades") -> None:
    _use_hours(p, hours, label)


def _use_hours(p: LifeProfile, hours: int, label: str = "Outras atividades") -> None:
    if p.hours_used + hours > free_hours(p):
        raise ConflictError(f"tempo livre insuficiente neste mês ({free_hours(p) - p.hours_used}h restantes, precisa de {hours}h)")
    p.hours_used += hours
    log_ = dict(p.hours_log or {})
    log_[label] = log_.get(label, 0) + hours
    p.hours_log = log_


@dataclass
class ActivityResult:
    activity: str
    cost: Decimal
    met: Person | None
    profile: LifeProfile
    story: str = ""


def do_activity(db: Session, user_id: int, month: SimMonth, key: str) -> ActivityResult:
    budget_service.require_open(month)
    a = R.ACTIVITIES.get(key)
    if a is None:
        raise FinanceError("atividade desconhecida")
    p = get_profile(db, user_id, lock=True)
    _use_hours(p, a["hours"], a["label"])
    cost = pricing.scale(db, user_id, month.ref_month, "lazer", a["cost"])
    _spend(db, user_id, month, p, amount=cost, description=a["label"], category="Lazer", key_part=f"act:{key}")
    for attr in ("social", "health", "wellbeing", "quality", "satisfaction"):
        if a.get(attr):
            setattr(p, attr, _clamp(getattr(p, attr) + a[attr]))
    met = None
    chance = a["meets"] * (0.6 + p.social / 100)
    if R.hash01("meet", user_id, month.ref_month.isoformat(), p.activity_seq, key) < chance:
        met = meet_person(db, p, month.ref_month, where=f"em: {a['label']}", interest=a.get("interest"))
    db.flush()
    story = f"Você foi a: {a['label']}." + (f" E acabou conhecendo {met.name}, {met.occupation.lower()}!" if met else " Foi um bom momento, mas ninguém novo apareceu.")
    return ActivityResult(key, cost, met, p, story)


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


def story_for(key: str, name: str, user_id: int, seq: int, ref: date) -> str:
    options = R.STORIES.get(key) or ["Vocês passaram um tempo juntos."]
    return R.pick(options, "story", user_id, ref.isoformat(), seq, key).format(name=name.split()[0])


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
    if not person.alive:
        raise ConflictError(f"{person.name.split()[0]} já faleceu")
    _use_hours(p, it["hours"], f"{it['label']} com {person.name.split()[0]}")
    _spend(db, user_id, month, p, amount=pricing.scale(db, user_id, month.ref_month, "lazer", it["cost"]),
           description=f"{it['label']} com {person.name}", category="Lazer", key_part=f"int:{person_id}:{key}")
    # conviver aproxima: cada atividade soma à compatibilidade; fazer algo do interesse dela(e) soma mais
    bonus = R.COMPAT_BONUS_MATCH if it.get("interest") in (person.interests or []) else R.COMPAT_BONUS_BASE
    r.compat_bonus = min(R.COMPAT_BONUS_CAP, r.compat_bonus + bonus)
    comp = compatibility(p, person, r.compat_bonus)
    # afinidade cresce mais com compatibilidade alta; programas gratuitos funcionam (só rendem um pouco menos)
    match = it.get("interest") in (person.interests or [])
    score = 0.40 + (0.28 if match else 0.0) + 0.25 * (comp / 100) + (R.hash01("react", user_id, person_id, p.activity_seq, month.ref_month.isoformat()) - 0.5) * 0.4
    react = next(x for x in R.REACTIONS if score >= x[0])
    base_gain = it["gain"] * (0.5 + comp / 100)
    delta = -max(1, round(it["gain"] * 0.5)) if react[1] == "DISLIKED" else max(1, round(base_gain * react[2]))
    _bump(r, delta, trust=(1 + (1 if r.interactions_month == 0 else 0)) if delta > 0 else 0)
    r.reaction = {"key": react[1], "text": react[3].format(n=person.name.split()[0]), "delta": delta}
    r.interactions_month += 1
    r.last_interaction_month = month.ref_month
    if delta > 0:
        p.social = _clamp(p.social + 1)
        p.wellbeing = _clamp(p.wellbeing + 1)
    r.last_story = story_for(key, person.name, user_id, p.activity_seq, month.ref_month)
    log(db, user_id, month.ref_month, "TOGETHER", f"{person.name}: {r.last_story}", person_id=person_id)
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
    if r.stage == "FAMILY":
        raise ConflictError("é da sua família: esse tipo de convite não se aplica")

    def go(stage: str, text: str) -> Relationship:
        r.stage, r.stage_since = stage, ref
        log(db, user_id, ref, stage, text, person_id=person_id)
        db.flush()
        return r

    PENALTY = {"befriend": 3, "date": 5, "cohabit": 6, "marry": 8}

    def refuse(why: str):
        """Ser recusado machuca a relação: a afinidade (e um pouco da confiança) cai e isso fica gravado."""
        _bump(r, -PENALTY.get(action, 3), trust=-2)
        _hit_mood(p, -3, -2)                                       # ser recusado machuca: bem-estar e satisfação caem
        db.flush()
        raise RelationshipRefused(f"{why}. A afinidade com {person.name} diminuiu.")

    if action == "end":
        was_household = r.stage in R.HOUSEHOLD_STAGES
        r.ended_month = ref
        r.finance_mode = "SEPARATE"
        go("ENDED", f"Você encerrou o relacionamento com {person.name}")
        if p.pregnancy_relationship_id == r.id:
            log(db, user_id, ref, "PREGNANCY_PARTNER_LEFT", f"{person.name} saiu do relacionamento durante a gestação (a gravidez continua)")
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


# --- tentar ter um filho: 2 etapas determinísticas (aceite do(a) parceiro(a) e concepção) ----------------
CHILD_PERSONALITY = {"caseiro": 0.08, "tranquilo": 0.03, "metódico": 0.02, "criativo": 0.01, "extrovertido": 0.0,
                     "reservado": -0.02, "aventureiro": -0.05, "ambicioso": -0.06}
# idade fértil mínima -> chance mensal de concepção (tabela do pedido)
CONCEPTION_BY_AGE = ((29, 0.28), (34, 0.22), (37, 0.14), (39, 0.09), (42, 0.04))
CONCEPTION_OLD = 0.015


def _roll(*key) -> float:
    """Sorteio determinístico (hash01). Existe só para os testes poderem forçar o resultado (monkeypatch)."""
    return R.hash01(*key)


def _seed(db: Session, user_id: int):
    g = economy_service_game(db, user_id)
    return g.seed if g is not None else user_id


def fertile_age(p: LifeProfile, person: Person) -> int:
    """Idade usada na fertilidade: parceiro(a) F -> idade dele(a); senão jogador F -> idade do jogador; senão a média.
    O gênero vem de `Person.gender` (M/F) e `LifeProfile.gender` (M/F/N); 'N' ou casal M+M usa a média das idades."""
    if person.gender == "F":
        return person.age
    if p.gender == "F":
        return p.age_years
    return round((person.age + p.age_years) / 2)


def conception_base(age: int) -> float:
    for top, prob in CONCEPTION_BY_AGE:
        if age <= top:
            return prob
    return CONCEPTION_OLD


def health_factor(p: LifeProfile) -> float:
    """0,7..1,1: 60% saúde, 25% bem-estar, 15% ausência de estresse; +10% com tempo em família ALTO (pode passar de 1,1)."""
    score = 0.60 * p.health + 0.25 * p.wellbeing + 0.15 * (100 - (p.stress or 0))
    f = 0.7 + 0.4 * score / 100
    return f * 1.10 if p.family_time == "HIGH" else f


def conception_probability(p: LifeProfile, person: Person) -> float:
    return round(min(0.35, conception_base(fertile_age(p, person)) * health_factor(p)), 4)


def _accept_parts(db: Session, p: LifeProfile, r: Relationship, person: Person, month: SimMonth) -> tuple[float, list[tuple[float, str]]]:
    """Probabilidade de aceite e, para a mensagem de recusa, os motivos (peso, texto)."""
    nome = person.name.split()[0]
    comp = compatibility(p, person, r.compat_bonus)
    n_kids = len(children(db, p.user_id))
    tight = financial_stability(db, p.user_id, month) <= 40       # caixa < 3 meses das despesas planejadas do mês
    kids_pen = 0.08 * n_kids
    recent = 0.0
    if p.last_child_refusal_month is not None:
        since = budget_service.months_between(p.last_child_refusal_month, month.ref_month)
        recent = 0.10 if since <= 1 else 0.05 if since == 2 else 0.0
    prob = (0.20 + 0.004 * r.affinity + 0.003 * r.trust + 0.002 * comp + 0.35 * person.wants_children / 100
            + (0.12 if r.stage == "MARRIED" else 0.0) + CHILD_PERSONALITY.get(person.personality, 0.0)
            - kids_pen - (0.10 if tight else 0.0) - recent)
    prob = round(max(0.05, min(0.90, prob)), 4)
    reasons = [
        (0.004 * max(0, 70 - r.affinity), f"{nome} acha que ainda não é a hora: falta afinidade entre vocês"),
        (0.003 * max(0, 60 - r.trust), f"{nome} acha que ainda não é a hora: falta confiança"),
        (kids_pen, f"{nome} acha que já tem muita coisa com os filhos que vocês têm"),
        (0.10 if tight else 0.0, f"{nome} está preocupado(a) com as finanças da casa"),
        (recent, f"{nome} ainda está chateado(a) com o último pedido: deem um tempo"),
        (0.35 * max(0, 60 - person.wants_children) / 100, f"{nome} ainda não está muito animado(a) com a ideia de ter filhos"),
    ]
    return prob, reasons


def accept_probability(db: Session, p: LifeProfile, r: Relationship, person: Person, month: SimMonth) -> float:
    return _accept_parts(db, p, r, person, month)[0]


def child_try_info(db: Session, user_id: int, month: SimMonth, p: LifeProfile | None = None) -> dict:
    """Estado exibido na tela: se dá para tentar agora, por que não e as chances (transparência)."""
    p = p or get_profile(db, user_id)
    r = active_partner(db, user_id)
    person = db.get(Person, r.person_id) if r is not None else None
    info = {"can_try": False, "blocked_reason": None, "accept_chance_pct": None, "conceive_chance_pct": None, "tries": p.child_tries or 0,
            "last_try_month": p.last_child_try_month.isoformat() if p.last_child_try_month else None,
            "partner_name": person.name if person else None,
            "pregnancy_due_month": p.pregnancy_due_month.isoformat() if p.pregnancy_due_month else None}
    if p.pregnancy_due_month:
        info["blocked_reason"] = "já existe uma gestação em andamento"
    elif r is None or r.stage not in R.HOUSEHOLD_STAGES:
        info["blocked_reason"] = "tentar ter um filho exige um parceiro(a) em união estável ou casamento"
    elif p.last_child_try_month == month.ref_month:
        info["blocked_reason"] = "vocês já tentaram este mês"
    if r is not None and r.stage in R.HOUSEHOLD_STAGES:
        info["accept_chance_pct"] = 0 if person.wants_children < 25 else round(100 * accept_probability(db, p, r, person, month))
        info["conceive_chance_pct"] = round(100 * conception_probability(p, person))
    info["can_try"] = info["blocked_reason"] is None
    return info


def try_for_child(db: Session, user_id: int, month: SimMonth) -> dict:
    """Uma tentativa por mês: 1) o(a) parceiro(a) aceita? 2) se aceitou, engravidou? Sorteios por hash01 (determinísticos)."""
    budget_service.require_open(month)
    p = get_profile(db, user_id, lock=True)
    ref = month.ref_month
    if p.pregnancy_due_month:
        raise ConflictError("já existe uma gestação em andamento")
    r = active_partner(db, user_id)
    if r is None or r.stage not in R.HOUSEHOLD_STAGES:
        raise ConflictError("tentar ter um filho exige um parceiro(a) em união estável ou casamento")
    if p.last_child_try_month == ref:
        raise ConflictError("vocês já tentaram este mês")
    person = db.get(Person, r.person_id)
    nome = person.name.split()[0]
    p.last_child_try_month = ref                                  # recusa também consome a tentativa do mês
    accept = 0.0 if person.wants_children < 25 else accept_probability(db, p, r, person, month)
    conceive = conception_probability(p, person)
    out = {"accept_chance_pct": round(100 * accept), "conceive_chance_pct": round(100 * conceive)}

    def refused(text: str, aff: int, trust: int, mood: int, sat: int) -> dict:
        p.last_child_refusal_month = ref
        _bump(r, aff, trust=trust)
        _hit_mood(p, mood, sat)
        log(db, user_id, ref, "CHILD_REFUSED", text, person_id=person.id)
        return {**out, "outcome": "REFUSED", "text": text}

    if person.wants_children < 25:
        return refused(f"{nome} não quer ter filhos no momento.", -1, 0, -1, 0)
    if _roll("child-accept", _seed(db, user_id), user_id, person.id, ref.isoformat()) >= accept:
        reasons = _accept_parts(db, p, r, person, month)[1]
        w, why = max(reasons, key=lambda t: t[0])
        why = why if w > 0 else f"{nome} acha que ainda não é a hora"
        return refused(f"{why}. A afinidade e a confiança com {person.name} diminuíram um pouco.", -3, -1, -3, -2)
    if _roll("child-conceive", _seed(db, user_id), user_id, person.id, ref.isoformat()) < conceive:
        p.pregnancy_due_month = budget_service.shift_month(ref, R.PREGNANCY_MONTHS)
        p.pregnancy_relationship_id = r.id
        p.child_tries = 0
        text = f"Vocês estão esperando um bebê! Nascimento previsto: {p.pregnancy_due_month:%m/%Y}."
        log(db, user_id, ref, "PREGNANCY", f"Vocês estão esperando um bebê (nascimento previsto: {p.pregnancy_due_month:%m/%Y})")
        return {**out, "outcome": "PREGNANT", "text": text}
    p.child_tries = (p.child_tries or 0) + 1
    text = f"{nome} topou, mas desta vez não deu certo. Podem tentar de novo no mês que vem."
    log(db, user_id, ref, "CHILD_TRY", f"Tentaram ter um filho, mas não deu certo desta vez ({p.child_tries} tentativa(s) seguida(s))")
    return {**out, "outcome": "NOT_CONCEIVED", "text": text}


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


# ------------------------------------------------------------------ família de origem, envelhecimento e morte
def _family_member(db: Session, user_id: int, month: date, seed: int, role: str, age: int, last: str, idx: int) -> Person:
    gender = "F" if role in ("MOTHER", "SISTER") else "M"
    used = _used_first_names(db, user_id)
    first = next((n for n in (R.pick(R.NAMES[gender], "fam", seed, role, idx, k) for k in range(40)) if n.lower() not in used), R.pick(R.NAMES[gender], "fam", seed, role, idx))
    retired = age >= 62
    occ_m, occ_f, base = R.RETIRED if retired else R.pick(R.OCCUPATIONS, "famocc", seed, role, idx)
    income = quantize_money(Decimal(base) * Decimal(str(round(0.8 + R.hash01("faminc", seed, role, idx) * 0.5, 2))))
    assets, debts, _ = _financial_profile(income, seed, hash(role) % 997 + idx)
    interests = [R.pick(R.INTERESTS, "famint", seed, role, idx, i) for i in range(3)]
    person = Person(user_id=user_id, name=f"{first} {last}", gender=gender, age=age, role=role, alive=True, personality=R.pick(R.PERSONALITIES, "fampers", seed, role, idx),
                    interests=list(dict.fromkeys(interests)), occupation=occ_m if gender == "M" else occ_f, income=income, assets=assets, debts=debts,
                    sociability=50, wants_children=50, preferences={}, met_month=month,
                    death_age=(66 + int(R.hash01("deathage", seed, role) * 28)) if role in ("MOTHER", "FATHER") else None)
    db.add(person)
    db.flush()
    db.add(Relationship(user_id=user_id, person_id=person.id, stage="FAMILY", affinity=55 + int(R.hash01("faff", seed, role, idx) * 30),
                        trust=60 + int(R.hash01("ftr", seed, role, idx) * 25), since_month=month, stage_since=month))
    return person


def create_family(db: Session, user_id: int, month: date, seed: int) -> list[Person]:
    """Já começa com pai e mãe vivos e, por sorteio, 0 a 3 irmãos. O sobrenome é o da família."""
    p = get_profile(db, user_id)
    if db.scalar(select(Person.id).where(Person.user_id == user_id, Person.role.is_not(None)).limit(1)):
        return []
    last = R.pick(R.LAST_NAMES, "famlast", seed, user_id)
    people = [_family_member(db, user_id, month, seed, "MOTHER", p.age_years + 22 + int(R.hash01("ma", seed) * 11), last, 0),
              _family_member(db, user_id, month, seed, "FATHER", p.age_years + 24 + int(R.hash01("pa", seed) * 13), last, 0)]
    total = sum(w for _, w in R.SIBLING_COUNT_WEIGHTS)
    r, acc, n_sib = R.hash01("siblings", seed, user_id) * total, 0, 0
    for n, w in R.SIBLING_COUNT_WEIGHTS:
        acc += w
        if r <= acc:
            n_sib = n
            break
    for i in range(n_sib):
        role = "BROTHER" if R.hash01("sibg", seed, user_id, i) < 0.5 else "SISTER"
        age = _clamp(p.age_years + (R.hash01("siba", seed, user_id, i) - 0.5) * 16, 18, 80)
        people.append(_family_member(db, user_id, month, seed, role, age, last, i + 1))
    log(db, user_id, month, "FAMILY", "Sua família: " + ", ".join(f"{R.FAMILY_LABEL[x.role].lower()} {x.name.split()[0]}" for x in people))
    return people


def family(db: Session, user_id: int) -> list[Person]:
    return list(db.scalars(select(Person).where(Person.user_id == user_id, Person.role.is_not(None)).order_by(Person.id)))


def _hit_mood(p: LifeProfile, wellbeing: int = 0, satisfaction: int = 0, social: int = 0) -> None:
    p.wellbeing, p.satisfaction, p.social = _clamp(p.wellbeing + wellbeing), _clamp(p.satisfaction + satisfaction), _clamp(p.social + social)


def _death_hazard_monthly(age: int, health: int) -> float:
    base = 0.0004 * math.exp(0.095 * (age - 30)) / 12.0                         # risco anual que cresce com a idade (tipo Gompertz)
    factor = 0.7 if health >= 80 else 1.0 if health >= 60 else 1.8 if health >= 40 else 3.5 if health >= 25 else 7.0     # cuidar da saúde adia
    return min(1.0, base * factor)


def check_death(db: Session, p: LifeProfile, ref: date) -> bool:
    from backend.services import debt_service
    g = economy_service_game(db, p.user_id)
    if g is None or g.ended_reason:
        return False
    hazard = 1.0 if p.age_years >= 105 else _death_hazard_monthly(p.age_years, p.health)
    if R.hash01("death", g.seed, p.user_id, ref.isoformat()) < hazard:
        debt_service.end_game(db, p.user_id, ref, "DEAD", f"{p.name} faleceu aos {p.age_years} anos. Fim de jogo.")
        return True
    return False


def economy_service_game(db: Session, user_id: int):
    from backend.models import GameProfile
    return db.scalar(select(GameProfile).where(GameProfile.user_id == user_id))


def _parents_pass_away(db: Session, p: LifeProfile, ref: date) -> None:
    nxt = budget_service.shift_month(ref, 1)
    for per in family(db, p.user_id):
        if per.alive and per.role in ("MOTHER", "FATHER") and per.death_age is not None and per.age >= per.death_age:
            per.alive, per.death_month = False, nxt
            _hit_mood(p, wellbeing=-14, satisfaction=-10, social=-2)
            log(db, p.user_id, ref, "DEATH", f"{R.FAMILY_LABEL[per.role]} {per.name.split()[0]} faleceu aos {per.age} anos", person_id=per.id)


def _anniversary(db: Session, p: LifeProfile, ref: date) -> None:
    """A cada aniversário da partida: todos envelhecem um ano e a saúde cobra o passar do tempo."""
    p.age_years += 1
    for per in db.scalars(select(Person).where(Person.user_id == p.user_id, Person.alive.is_(True))):
        per.age += 1
    p.health = _clamp(p.health - (2 if p.age_years >= 60 else 1 if p.age_years >= 40 else 0))
    log(db, p.user_id, ref, "BIRTHDAY", f"Você fez {p.age_years} anos")


def _world_mood(db: Session, p: LifeProfile, ref: date) -> None:
    """Acontecimentos do mundo (crises, boom, choques de preço) mexem com o humor de todo mundo."""
    from backend.models import WorldEvent
    w = sat = 0.0
    for ev in db.scalars(select(WorldEvent).where(WorldEvent.user_id == p.user_id, WorldEvent.status == "ACTIVE", WorldEvent.scope.in_(("WORLD", "SECTOR")),
                                                  WorldEvent.start_month <= ref, WorldEvent.end_month >= ref)):
        k = ev.intensity * (0.5 if not ev.positive else 0.3)
        w += -k if not ev.positive else k
        sat += (-k if not ev.positive else k) * 0.6
    _hit_mood(p, int(round(max(-3, min(3, w)))), int(round(max(-2, min(2, sat)))))


# ------------------------------------------------------------------ sobrecarga, doenças e burnout
def active_conditions(p: LifeProfile, ref: date | None = None) -> list[dict]:
    return [c for c in (p.conditions or []) if c.get("until") is None or ref is None or c["until"] >= ref.isoformat()]


def condition_out(p: LifeProfile, ref: date) -> list[dict]:
    out = []
    for c in active_conditions(p, ref):
        d = R.CONDITIONS[c["key"]]
        out.append({"key": c["key"], "label": d["label"], "kind": d["kind"], "text": d["text"], "since": c["since"], "until": c.get("until"),
                    "treated": bool(c.get("treated")), "treatment_cost": d["cost"], "chronic": d["months"] is None})
    return out


def set_treatment(db: Session, user_id: int, month: SimMonth, key: str, treated: bool) -> LifeProfile:
    budget_service.require_open(month)
    p = get_profile(db, user_id, lock=True)
    cs = [dict(c) for c in (p.conditions or [])]
    hit = next((c for c in cs if c["key"] == key), None)
    if hit is None:
        raise NotFoundError("condição não encontrada")
    hit["treated"] = bool(treated)
    p.conditions = cs
    log(db, user_id, month.ref_month, "TREATMENT", f"Você {'começou o tratamento de' if treated else 'parou o tratamento de'} {R.CONDITIONS[key]['label'].lower()}")
    db.flush()
    sync_month(db, user_id, month)
    return p


def _stress_and_conditions(db: Session, p: LifeProfile, ref: date) -> None:
    """Fim do mês: sobrecarga (pouco tempo livre, jornada intensa, saúde ruim) acumula estresse; estresse alto adoece e pode levar ao burnout."""
    left = raw_free_hours(p) - p.hours_used
    st = p.stress or 0
    if left <= R.STRESS_FREE_THRESHOLD:
        st += 10
    elif p.work_level == "INTENSE":
        st += 4
    elif left >= 40 and p.work_level != "INTENSE":
        st -= 5
    st += (3 if p.health < 40 else 0) + (3 if p.wellbeing < 35 else 0)
    cs = [dict(c) for c in (p.conditions or [])]
    # efeitos mensais, recuperação e término
    keep = []
    for c in cs:
        d = R.CONDITIONS[c["key"]]
        k = 0.5 if c.get("treated") else 1.0
        p.health = _clamp(p.health + round(d["fx"].get("health", 0) * k))
        _hit_mood(p, round(d["fx"].get("wellbeing", 0) * k), round(d["fx"].get("satisfaction", 0) * k))
        if c.get("treated"):
            st -= 4
        if c.get("until") is not None and c["until"] < ref.isoformat():
            log(db, p.user_id, ref, "RECOVERED", f"Você se recuperou: {d['label'].lower()}.")
            if c["key"] == "BURNOUT":
                st = min(st, 55)
            continue
        if d["months"] is None and R.hash01("recover", p.user_id, c["key"], ref.isoformat()) < (0.20 if c.get("treated") else 0.04):
            log(db, p.user_id, ref, "RECOVERED", f"Você superou: {d['label'].lower()}.")
            continue
        keep.append(c)
    st = max(0, min(100, st))
    have = {c["key"] for c in keep}
    if st >= 50:
        chance = min(0.30, (st - 40) / 100 * 0.5)
        if R.hash01("fall-ill", p.user_id, ref.isoformat()) < chance:
            pool = ["BURNOUT"] if (st >= 85 and "BURNOUT" not in have and R.hash01("burn", p.user_id, ref.isoformat()) < 0.6) else \
                [k for k, d in R.CONDITIONS.items() if k != "BURNOUT" and k not in have and (d["kind"] == "MENTAL") == (p.wellbeing < 50 or R.hash01("kind", p.user_id, ref.isoformat()) < 0.5)]
            if pool:
                key = pool[int(R.hash01("which", p.user_id, ref.isoformat()) * len(pool))]
                d = R.CONDITIONS[key]
                until = None
                if d["months"]:
                    lo, hi = d["months"]
                    until = budget_service.shift_month(ref, lo + int(R.hash01("dur", p.user_id, ref.isoformat()) * (hi - lo + 1))).isoformat()
                keep.append({"key": key, "since": ref.isoformat(), "until": until, "treated": False})
                _hit_mood(p, -4, -3)
                log(db, p.user_id, ref, "ILLNESS", f"Sobrecarga cobrou o preço: {d['label'].lower()}. {d['text']}")
    p.conditions = keep
    p.stress = st


# ------------------------------------------------------------------ calendário do mês
def calendar(db: Session, user_id: int, month: SimMonth) -> dict:
    from backend.services import career_hub
    p = get_profile(db, user_id)
    ref = month.ref_month
    work = R.WORK_HOURS[p.work_level]
    rows = [("sleep", "😴 Sono", R.SLEEP_HOURS), ("work", f"💼 Trabalho (jornada {p.work_level.lower()})", work),
            ("routine", "🏠 Casa, refeições e deslocamento", R.MONTH_HOURS - R.SLEEP_HOURS - work - R.FREE_HOURS[p.work_level])]
    fam = R.FAMILY_TIME_HOURS[p.family_time]
    if fam:
        rows.append(("family", "👨‍👩‍👧 Tempo com a família", fam))
    if p.degree_field:
        rows.append(("degree", f"🎓 Faculdade de {career_rules.FIELDS[p.degree_field]['degree']}", career_rules.FIELDS[p.degree_field]["hours"]))
    from backend.models import Education
    for e in db.scalars(select(Education).where(Education.user_id == user_id, Education.kind == "COURSE", Education.status == "ACTIVE")):
        rows.append((f"course{e.id}", f"📚 Curso: {e.name}", e.hours))
    for j in career_hub.jobs(db, user_id):
        if j.end_month is None and j.hours:
            rows.append((f"job{j.id}", f"🧾 Trabalho PJ extra: {j.title}", j.hours))
    if p.hours_committed:
        rows.append(("assets", "🏢 Gestão de empresas e bens", p.hours_committed))
    for i, (label, h) in enumerate((p.hours_log or {}).items()):
        rows.append((f"log{i}", f"🎯 {label}", h))
    used = sum(h for _, _, h in rows)
    free = max(0, R.MONTH_HOURS - used)
    rows.append(("free", "🟢 Tempo livre restante", free))
    return {"month": ref.isoformat(), "total": R.MONTH_HOURS, "free_left": free, "overloaded": free <= R.STRESS_FREE_THRESHOLD, "stress": p.stress or 0,
            "rows": [{"key": k, "label": l, "hours": h} for k, l, h in rows if h > 0]}


# ------------------------------------------------------------------ o orçamento do mês muda os atributos
def budget_impact(db: Session, user_id: int, month: SimMonth) -> dict:
    """Como as escolhas do orçamento (quanto vai para saúde, lazer, comida, estudo, dívidas, poupança...) afetam quem você é.
    É o MESMO cálculo aplicado no fechamento do mês; aqui serve de prévia ao vivo."""
    from backend.models import BudgetCategory, LedgerEntry
    s = budget_service.summarize(db, user_id, month)
    cats = {c.id: c.name for c in db.scalars(select(BudgetCategory).where(BudgetCategory.user_id == user_id))}
    planned: dict[str, Decimal] = {}
    for bi in db.scalars(select(BudgetItem).where(BudgetItem.month_id == month.id, BudgetItem.kind == FlowKind.EXPENSE, BudgetItem.capital.is_(False))):
        planned[cats.get(bi.category_id, "Outros")] = planned.get(cats.get(bi.category_id, "Outros"), ZERO) + bi.planned_amount
    real: dict[str, Decimal] = {}
    for cid, tot in db.execute(select(LedgerEntry.category_id, func.sum(LedgerEntry.amount)).where(
            LedgerEntry.user_id == user_id, LedgerEntry.ref_month == month.ref_month, LedgerEntry.kind == FlowKind.EXPENSE,
            LedgerEntry.capital.is_(False), LedgerEntry.company_id.is_(None)).group_by(LedgerEntry.category_id)):
        real[cats.get(cid, "Outros")] = tot
    total_exp = sum((max(planned.get(n, ZERO), real.get(n, ZERO)) for n in set(planned) | set(real)), ZERO)
    income = max(s.planned_income, s.realized_income, total_exp, D1)           # base de comparação (sem renda, usa o total gasto)
    out, total = [], {"health": 0, "wellbeing": 0, "satisfaction": 0, "quality": 0}
    if total_exp <= 0:                                                          # sem orçamento montado, sem efeitos
        return {"income": str(income), "effects": out, "totals": total, "savings_rate": 0.0}

    def add(label, text, fx, spend=None, level=None):
        out.append({"label": label, "text": text, "spend": str(spend) if spend is not None else None, "level": level, **{k: fx.get(k, 0) for k in total}})
        for k in total:
            total[k] += fx.get(k, 0)

    for name, rule in R.BUDGET_RULES.items():
        spend = max(planned.get(name, ZERO), real.get(name, ZERO))
        ratio = float(spend / income) / rule["target"]
        level = "great" if ratio >= rule["great"] else "good" if ratio >= rule["good"] else "low" if ratio < rule["low"] else None
        if level and level in rule["fx"]:
            add(name, f"{name}: {R.LEVEL_TEXT[level]} ({rule['text']}).", rule["fx"][level], spend, level)
    for name, (lim1, lim2, why) in R.EXCESS_RULES.items():
        spend = max(planned.get(name, ZERO), real.get(name, ZERO))
        share = float(spend / income)
        if share > lim1:
            add(name, f"{name} ocupa {share * 100:.0f}% da renda: {why}.", dict(wellbeing=-2 if share > lim2 else -1), spend, "high")
    has_income = max(s.planned_income, s.realized_income) > 0
    savings = float((s.planned_income - s.planned_expense) / income) if has_income else 0.0
    if not has_income:
        pass
    elif savings >= 0.20:
        add("Poupança", f"Você poupa {savings * 100:.0f}% da renda: segurança e tranquilidade.", dict(satisfaction=+1, wellbeing=+1))
    elif savings < 0:
        add("Poupança", "As despesas passam da renda do mês: o estresse com dinheiro pesa.", dict(satisfaction=-1, wellbeing=-1))
    if has_income and float(month.planned_investment / income) >= 0.10:
        add("Investimentos", "Você separa 10% ou mais da renda para investir: confiança no futuro.", dict(satisfaction=+1))
    return {"income": str(income), "effects": out, "totals": total, "savings_rate": round(savings * 100, 1)}


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
    uni = uni_rules.get((p.degree_unis or {}).get(field, uni_rules.OPEN_KEY)) if degree else None
    factor = ratio * ((1 + new["premium"] / 100 * uni_rules.premium_factor(uni)) if degree else career_rules.NO_DEGREE_SWITCH)
    p.pending_career = {"field": field, "factor": round(factor, 4), "degree": degree}
    log(db, user_id, month.ref_month, "CAREER_PLANNED",
        f"Você vai mudar para {new['label']} no mês que vem ({'com diploma' if degree else 'sem diploma: recomeço por baixo'}, salário {'+' if factor >= 1 else ''}{(factor - 1) * 100:.0f}%)")
    db.flush()
    return p


def enroll_degree(db: Session, user_id: int, month: SimMonth, field: str, uni_key: str = uni_rules.OPEN_KEY) -> LifeProfile:
    """Matricula na graduação de `field` na faculdade `uni_key`. Faculdades concorridas têm vestibular: a chance depende da concorrência e do
    seu currículo; reprovado, só dá para tentar a mesma faculdade/área daqui a 12 meses (o resultado fica em `p.admission`, sem erro)."""
    budget_service.require_open(month)
    f = _field(field)
    try:
        uni = uni_rules.get(uni_key)
    except ValueError as e:
        raise FinanceError(str(e)) from None
    if not uni_rules.offers_field(uni, field):
        raise FinanceError(f"a {uni.short} não oferece graduação em {f['degree']}")
    p = get_profile(db, user_id, lock=True)
    p.admission = None
    if p.degree_field:
        raise ConflictError("você já está cursando uma faculdade")
    if field in (p.degrees or []):
        raise ConflictError("você já se formou nessa área")
    if len(p.degrees or []) >= career_rules.MAX_DEGREES:
        raise ConflictError("limite de formações atingido")
    if p.country != "BR":
        raise ConflictError("as faculdades brasileiras exigem que você more no Brasil (volte, ou faça um intercâmbio)")
    ref = month.ref_month
    attempts = dict(p.uni_attempts or {})
    akey = f"{uni.key}:{field}"
    last = attempts.get(akey)
    if last and budget_service.months_between(date.fromisoformat(last), ref) < uni_rules.REAPPLY_MONTHS:
        wait = uni_rules.REAPPLY_MONTHS - budget_service.months_between(date.fromisoformat(last), ref)
        raise ConflictError(f"você foi reprovado(a) no vestibular da {uni.short}: nova tentativa em {wait} {'mês' if wait == 1 else 'meses'}")
    from backend.services import career_hub
    prep, _ = career_hub.resume_score(db, user_id, field, ref)
    prep = max(0.0, min(100.0, prep + 0.6 * (float(p.study if p.study is not None else 20.0) - 20.0)))      # estudar por conta própria ajuda no vestibular
    chance = uni_rules.admission_chance(uni, prep)
    if R.hash01("vestibular", user_id, uni.key, field, ref.isoformat()) >= chance:
        attempts[akey] = ref.isoformat()
        p.uni_attempts = attempts
        p.satisfaction = _clamp(p.satisfaction - 3)
        p.admission = {"admitted": False, "chance": chance, "uni": uni.key}
        log(db, user_id, ref, "VESTIBULAR_FAIL", f"Você prestou o vestibular da {uni.short} para {f['degree']} (chance {chance * 100:.0f}%) e não passou. Nova tentativa em 12 meses.")
        db.flush()
        return p
    months = uni_rules.months_for(uni, field, f["months"])
    p.degree_field, p.degree_uni, p.degree_progress, p.degree_total = field, uni.key, 0, months
    career_hub.on_degree_start(db, p, field, ref)
    p.admission = {"admitted": True, "chance": chance, "uni": uni.key}
    log(db, user_id, ref, "DEGREE_START", f"Você passou na {uni.short} e começou a faculdade de {f['degree']} ({months} meses)")
    db.flush()
    sync_month(db, user_id, month)
    return p


STUDY_MAX_HOURS_DAY = 6.0


def set_study_hours(db: Session, user_id: int, month: SimMonth, hours_day: float) -> LifeProfile:
    """Define quantas horas por dia você estuda por conta própria (1 h/dia = ~30 h do seu tempo livre no mês). Só cabe o que o calendário permite."""
    budget_service.require_open(month)
    try:
        h = round(float(hours_day) * 2) / 2
    except (TypeError, ValueError):
        raise FinanceError("horas de estudo inválidas") from None
    if not 0 <= h <= STUDY_MAX_HOURS_DAY:
        raise FinanceError(f"estude entre 0 e {STUDY_MAX_HOURS_DAY:g} horas por dia")
    p = get_profile(db, user_id, lock=True)
    free_without = raw_free_hours(p) + int(round((p.study_hours_day or 0) * 30))
    if h * 30 > free_without:
        raise ConflictError(f"o seu calendário não comporta {h:g} h/dia ({int(h * 30)} h/mês): você só tem {max(0, free_without)} h livres por mês")
    p.study_hours_day = h
    from backend.services import career_hub
    career_hub.recalc_hours(db, user_id)
    log(db, user_id, month.ref_month, "STUDY_HOURS", f"Você passou a estudar {h:g} h por dia por conta própria")
    db.flush()
    return p


def _study_monthly(p: LifeProfile) -> None:
    """Estudo: sobe com as horas diárias (rendimento decrescente), cai devagar sem estudar, e cresce um pouco enquanto você cursa faculdade."""
    h = float(p.study_hours_day or 0.0)
    cur = float(p.study if p.study is not None else 20.0)
    if h > 0:
        cur += 0.9 * h * (1 - cur / 130)
    else:
        cur -= 0.4
    if p.degree_field:
        cur += 0.25
    p.study = round(max(0.0, min(100.0, cur)), 2)


def drop_degree(db: Session, user_id: int, month: SimMonth) -> LifeProfile:
    budget_service.require_open(month)
    p = get_profile(db, user_id, lock=True)
    if not p.degree_field:
        raise ConflictError("você não está cursando faculdade")
    from backend.services import career_hub
    career_hub.on_degree_end(db, p, p.degree_field, month.ref_month, False)
    log(db, user_id, month.ref_month, "DEGREE_DROP", f"Você trancou a faculdade de {career_rules.FIELDS[p.degree_field]['degree']}")
    p.degree_field, p.degree_uni, p.degree_progress, p.degree_total = None, None, 0, 0
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
    from backend.services import career_hub
    career_hub.reprice_foreign_jobs(db, user_id, ref)
    career_hub.merit_raise_on_open(db, user_id, new_month)


# ------------------------------------------------------------------ moradia
def search_housing(db: Session, user_id: int, month: SimMonth, budget: Decimal) -> dict:
    """O jogo decide se existe oferta de aluguel para o valor que o jogador quer pagar."""
    g = economy_service_game(db, user_id)
    return housing_service.search(g.seed if g else user_id, user_id, month.ref_month, budget)


def housing_quality(db: Session, p: LifeProfile) -> tuple[int, str]:
    """Condição da moradia: imóvel próprio em que você mora (pelo estado e valor) ou a do aluguel escolhido."""
    from backend.models import Good, GoodStatus, Occupancy, RealEstateDetails
    row = db.execute(select(Good, RealEstateDetails).join(RealEstateDetails, RealEstateDetails.good_id == Good.id).where(
        Good.user_id == p.user_id, Good.status == GoodStatus.ACTIVE, RealEstateDetails.occupancy == Occupancy.OWNER_OCCUPIED).limit(1)).first()
    if row is not None:
        good, det = row
        base = {"NEW": 2, "EXCELLENT": 2, "GOOD": 1, "FAIR": 0, "POOR": -1}.get(good.condition.value if good.condition else "GOOD", 1)
        base += 1 if good.current_value >= Decimal("1500000") else 0
        base -= 1 if det.area_m2 and det.area_m2 < 30 else 0
        return max(-3, min(3, base)), f"Seu imóvel próprio: {good.name}"
    return p.housing_quality, p.housing_desc or ""


def move(db: Session, user_id: int, month: SimMonth, *, kind: str, monthly_cost: Decimal) -> LifeProfile:
    """Agenda a mudança para o PRÓXIMO mês: os custos antigos terminam e os novos começam lá.
    Aluguel (RENT/SHARED): o valor é o que você ESTÁ DISPOSTO a pagar; só existe mudança se o jogo achar uma oferta nessa faixa."""
    budget_service.require_open(month)
    if kind not in R.HOUSING_KINDS:
        raise FinanceError("tipo de moradia inválido")
    monthly_cost = quantize_money(monthly_cost)
    quality, desc = None, None
    if kind == "EXISTING":
        monthly_cost = ZERO
    elif kind == "FAMILY_HOME":
        monthly_cost, quality, desc = (monthly_cost if monthly_cost > 0 else ZERO), 0, "Você mora na casa de familiares."
    else:
        if monthly_cost <= 0:
            raise FinanceError("informe quanto você quer pagar de aluguel")
        offer = search_housing(db, user_id, month, monthly_cost)
        if not offer["available"]:
            raise ConflictError(offer["message"])
        monthly_cost, quality, desc = D_(offer["rent"]), offer["quality"], f"{offer['title']}: {offer['description']}"
    p = get_profile(db, user_id, lock=True)
    p.pending_housing_kind, p.pending_housing_cost = kind, monthly_cost
    p.pending_housing_quality, p.pending_housing_desc = quality, (desc[:160] if desc else None)
    p.pending_housing_month = budget_service.shift_month(month.ref_month, 1)
    log(db, user_id, month.ref_month, "MOVE_PLANNED", f"Mudança de residência agendada para {p.pending_housing_month:%m/%Y}" + (f": {desc}" if desc else ""))
    db.flush()
    return p


# ------------------------------------------------------------------ orçamento: itens gerados pela vida pessoal
def add_one_off(p: LifeProfile, key: str, name: str, amount, cat: str, ref: date, kind: str = "EXPENSE") -> None:
    """Agenda uma despesa/receita pontual no orçamento do mês `ref` (vira item `life:*`). Mantém só os últimos 18 meses."""
    keep = {k: v for k, v in (p.one_offs or {}).items() if v.get("month", "") >= budget_service.shift_month(ref, -18).isoformat()}
    keep[key] = {"name": name, "amount": str(quantize_money(Decimal(str(amount)))), "cat": cat, "month": ref.isoformat(), "kind": kind}
    p.one_offs = keep


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

    if any(c["key"] == "BURNOUT" for c in active_conditions(p, ref)):
        sal = item_sync.salary_total(db, user_id, ref)
        want("life:burnout", "Renda a menos (afastamento por burnout)", FlowKind.EXPENSE, "Outros", sal * R.BURNOUT_INCOME_LOSS_PCT / 100)
    for c in active_conditions(p, ref):
        if c.get("treated"):
            want(f"life:treat:{c['key']}", f"Tratamento: {R.CONDITIONS[c['key']]['label'].lower()}", FlowKind.EXPENSE, "Saúde", scale("saude", R.CONDITIONS[c['key']]['cost']))
    from backend.services import career_hub
    career_hub.ensure_jobs(db, user_id, month)
    career_hub.desired_items(db, user_id, ref, want)
    from backend.services import abroad_service, artist_service
    abroad_service.desired_items(db, user_id, ref, want)
    artist_service.desired_items(db, user_id, ref, want)

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
    for per in family(db, user_id):
        if per.death_month == ref and not per.alive:
            heirs = 1 + sum(1 for x in family(db, user_id) if x.alive and x.role in ("BROTHER", "SISTER"))
            share = quantize_money(per.assets / heirs) if per.assets > 0 else ZERO
            want(f"life:funeral:{per.id}", f"Funeral — {per.name.split()[0]}", FlowKind.EXPENSE, "Outros", scale("saude", 4500))
            if share > 0:
                want(f"life:inherit:{per.id}", f"Herança de {per.name.split()[0]}", FlowKind.INCOME, "Renda extra", share)
                want(f"life:itcmd:{per.id}", f"ITCMD (imposto sobre herança, 4%) — {per.name.split()[0]}", FlowKind.EXPENSE, "Impostos", share * Decimal("0.04"))
    if p.degree_field:
        u = uni_rules.get(p.degree_uni or uni_rules.OPEN_KEY)
        want("life:tuition", f"Mensalidade — {career_rules.FIELDS[p.degree_field]['degree']} ({u.short})", FlowKind.EXPENSE, "Educação",
             scale("educacao", uni_rules.monthly_cost(u, p.degree_field, career_rules.FIELDS[p.degree_field]["cost"])))
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
    bud = budget_impact(db, user_id, month)                  # cada escolha do orçamento mexe com os atributos
    for k in d:
        d[k] += bud["totals"][k]
    hq, _ = housing_quality(db, p)
    hw, hs, hh = housing_service.monthly_effect(hq)          # onde você mora muda saúde, bem-estar e satisfação
    d["wellbeing"] += hw
    d["satisfaction"] += hs
    d["health"] += hh
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
    target_quality = 0.4 * p.wellbeing + 0.3 * p.health + 0.15 * stability + 0.15 * p.social + 2 * hq
    p.quality = _clamp(p.quality + max(-3, min(3, target_quality - p.quality)) + d["quality"])
    target_sat = (p.wellbeing + p.quality) / 2
    p.satisfaction = _clamp(p.satisfaction + max(-3, min(3, target_sat - p.satisfaction)) + d["satisfaction"])

    for r in db.scalars(select(Relationship).where(Relationship.user_id == user_id, Relationship.stage != "ENDED")):
        person = db.get(Person, r.person_id)
        if not person.alive:
            continue
        if r.stage == "FAMILY":                                    # família esfria devagar e nunca "termina"
            if r.interactions_month == 0:
                r.affinity = max(25, r.affinity - 1)
            r.interactions_month = 0
            continue
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
            _hit_mood(p, -2, -1)
            log(db, user_id, ref, "DRIFT_APART", f"O relacionamento com {person.name} esfriou e acabou")
            if p.pregnancy_relationship_id == r.id:
                log(db, user_id, ref, "PREGNANCY_PARTNER_LEFT", f"{person.name} saiu do relacionamento durante a gestação (a gravidez continua)")
    for c in children(db, user_id):
        c.development = _clamp(c.development + (1 if c.school_kind == "PRIVATE" else 0) + (1 if c.activities else 0)
                               + {"LOW": -1, "NORMAL": 0, "HIGH": 1}[p.family_time])
        c.health = _clamp(c.health + (1 if p.health_level == "PLUS" else 0) - (1 if p.health_level == "NONE" else 0))
    _study_monthly(p)
    if p.degree_field:                                  # faculdade: um mês cursado; ao final, formatura
        p.degree_progress += 1
        if p.degree_progress >= p.degree_total:
            f = career_rules.FIELDS[p.degree_field]
            p.degrees = list(p.degrees or []) + [p.degree_field]
            p.degree_unis = {**(p.degree_unis or {}), p.degree_field: p.degree_uni or uni_rules.OPEN_KEY}
            from backend.services import career_hub
            career_hub.on_degree_end(db, p, p.degree_field, ref, True)
            p.satisfaction = _clamp(p.satisfaction + 8)
            log(db, user_id, ref, "GRADUATED", f"Você se formou em {f['degree']} ({uni_rules.get(p.degree_uni or uni_rules.OPEN_KEY).short})! Agora pode mudar de área e ganhar mais.")
            p.degree_field, p.degree_uni, p.degree_progress, p.degree_total = None, None, 0, 0
    from backend.services import abroad_service, artist_service, career_hub
    abroad_service.process_month(db, p, ref)
    artist_service.process_month(db, p, ref)
    career_hub.process_month(db, p, ref)
    _world_mood(db, p, ref)
    if p.degree_field and R.hash01("classmate", p.user_id, ref.isoformat()) < 0.30:           # na faculdade você conhece gente nova
        meet_person(db, p, ref, where=f"na faculdade de {career_rules.FIELDS[p.degree_field]['degree']}", interest="estudos")
    _parents_pass_away(db, p, ref)
    check_death(db, p, ref)
    _stress_and_conditions(db, p, ref)
    p.hours_used, p.hours_log = 0, {}
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
        if p.pending_housing_quality is not None:
            p.housing_quality, p.housing_desc = p.pending_housing_quality, p.pending_housing_desc
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
    started = economy_service_game(db, user_id)
    if started is not None and started.started_month and ref > started.started_month and budget_service.months_between(started.started_month, ref) % 12 == 0:
        _anniversary(db, p, ref)
    sync_month(db, user_id, new_month)
    if p.pending_housing_month is not None and p.pending_housing_month <= ref:
        p.pending_housing_kind = p.pending_housing_cost = p.pending_housing_month = p.pending_housing_quality = p.pending_housing_desc = None
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
