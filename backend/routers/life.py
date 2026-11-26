"""Vida pessoal e família (etapa 4)."""
from datetime import date
from decimal import Decimal

from fastapi import APIRouter
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.dependencies import CurrentUser, DbSession
from backend.models import BudgetCategory, BudgetItem, Child, LifeLog, Person, Relationship
from backend.routers.budget import _run
from backend.services import budget_service as bs
from backend.services import life_rules as R
from backend.services import career_rules, item_sync, partners
from backend.services import university_rules as ur
from backend.services import life_service as ls

router = APIRouter(prefix="/life", tags=["life"])


class CharacterIn(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    age_years: int = Field(default=28, ge=18, le=80)
    gender: str | None = None
    interested_in: str | None = None


class FieldIn(BaseModel):
    field: str


class DegreeIn(BaseModel):
    field: str
    uni: str = "aberta"


class ChoicesIn(BaseModel):
    work_level: str | None = None
    food_level: str | None = None
    health_level: str | None = None
    leisure_level: str | None = None
    family_time: str | None = None


class ActivityIn(BaseModel):
    key: str


class ActionIn(BaseModel):
    action: str


class FinanceRulesIn(BaseModel):
    mode: str
    contribution_pct: Decimal | None = None


class MoveIn(BaseModel):
    kind: str
    monthly_cost: Decimal = Decimal("0")


class ChildIn(BaseModel):
    school_kind: str | None = None
    daycare: bool | None = None
    activities: bool | None = None


def _person_out(db: Session, p, r: Relationship, person: Person) -> dict:
    return {"person_id": person.id, "name": person.name, "age": person.age, "personality": person.personality,
            "interests": person.interests, "occupation": person.occupation, "income": str(person.income),
            "assets": str(person.assets), "debts": str(person.debts), "finance_label": partners.finance_label(person), "wants_children": person.wants_children,
            "role": person.role, "alive": person.alive, "stage": r.stage, "affinity": r.affinity, "trust": r.trust, "compatibility": ls.compatibility(p, person, r.compat_bonus), "compat_bonus": r.compat_bonus, "gender": person.gender,
            "since_month": r.since_month.isoformat(), "stage_since": r.stage_since.isoformat(),
            "finance_mode": r.finance_mode, "contribution_pct": str(r.contribution_pct)}


def _expenses(db: Session, user_id: int, month) -> list[dict]:
    """Despesas da vida pessoal no mês, com a origem identificada pela chave."""
    cats = {c.id: c.name for c in db.scalars(select(BudgetCategory).where(BudgetCategory.user_id == user_id))}
    out = []
    for bi in db.scalars(select(BudgetItem).where(BudgetItem.month_id == month.id, BudgetItem.source_key.is_not(None))
                         .order_by(BudgetItem.id)):
        k = bi.source_key
        if not k.startswith(ls.OWN_PREFIXES):
            continue
        origin = "Filho(a)" if k.startswith("child:") else "Parceiro(a)" if "partner" in k else \
            "Moradia compartilhada" if k == "family:housing" else "Estilo de vida"
        out.append({"key": k, "name": bi.name, "kind": bi.kind.value, "category": cats.get(bi.category_id, ""),
                    "origin": origin, "amount": str(bi.planned_amount),
                    "child_id": int(k.split(":")[1]) if k.startswith("child:") else None})
    return out


def _career_out(db: Session, user_id: int, p, month) -> dict:
    cur = career_rules.FIELDS.get(p.career_field or "")
    next_raise = None
    if p.career_field and p.career_since:
        k = bs.months_between(p.career_since, month.ref_month) // 12 + 1
        next_raise = bs.shift_month(p.career_since, 12 * k).isoformat()
    return {
        "field": p.career_field, "label": cur["label"] if cur else None, "outlook": cur["outlook"] if cur else None,
        "growth_pct": cur["growth"] if cur else None, "since": p.career_since.isoformat() if p.career_since else None,
        "next_raise": next_raise, "salary": str(item_sync.salary_total(db, user_id, month.ref_month)),
        "degrees": list(p.degrees or []), "pending": p.pending_career,
        "studying": ({"field": p.degree_field, "name": career_rules.FIELDS[p.degree_field]["degree"], "progress": p.degree_progress,
                      "total": p.degree_total, "uni": p.degree_uni or "aberta",
                      "cost": ur.monthly_cost(ur.get(p.degree_uni or "aberta"), p.degree_field, career_rules.FIELDS[p.degree_field]["cost"])} if p.degree_field else None),
        "degree_unis": dict(p.degree_unis or {}),
        "fields": [{"key": k, "label": f["label"], "emoji": f["emoji"], "outlook": f["outlook"], "growth_pct": f["growth"], "start": f["start"],
                    "degree": f["degree"], "months": f["months"], "cost": f["cost"], "premium_pct": f["premium"], "hours": f["hours"]}
                   for k, f in career_rules.FIELDS.items()],
    }


def _overview(db: Session, user_id: int) -> dict:
    month = bs.ensure_setup(db, user_id)
    p = ls.get_profile(db, user_id)
    rels = []
    for r in db.scalars(select(Relationship).where(Relationship.user_id == user_id).order_by(Relationship.id)):
        rels.append(_person_out(db, p, r, db.get(Person, r.person_id)))
    kids = []
    for c in ls.children(db, user_id, active_only=False):
        lines = ls.child_lines(c, month.ref_month)
        kids.append({"id": c.id, "name": c.name, "age_years": ls.child_age_years(c, month.ref_month), "health": c.health,
                     "development": c.development, "school_kind": c.school_kind, "daycare": c.daycare,
                     "activities": c.activities, "active": c.active, "monthly_reference_cost": sum(lines.values()),
                     "needs": sorted(lines)})
    expenses = _expenses(db, user_id, month)
    stability = ls.financial_stability(db, user_id, month)
    return {
        "month": month.ref_month.isoformat(),
        "character": {"name": p.name, "age_years": p.age_years, "gender": p.gender, "interested_in": p.interested_in},
        "career": _career_out(db, user_id, p, month),
        "attributes": {"health": p.health, "wellbeing": p.wellbeing, "quality": p.quality, "satisfaction": p.satisfaction,
                       "social": p.social, "financial_stability": stability, "free_hours_left": ls.free_hours(p) - p.hours_used,
                       "free_hours_total": ls.free_hours(p)},
        "choices": {k: getattr(p, k) for k in R.LEVELS},
        "options": {k: list(v) for k, v in R.LEVELS.items()},
        "housing": {"kind": p.housing_kind, "monthly_cost": str(p.housing_cost), "quality": ls.housing_quality(db, p)[0], "description": ls.housing_quality(db, p)[1],
                    "pending": ({"kind": p.pending_housing_kind, "monthly_cost": str(p.pending_housing_cost),
                                 "effective_month": p.pending_housing_month.isoformat()} if p.pending_housing_month else None)},
        "stress": p.stress or 0, "conditions": ls.condition_out(p, month.ref_month),
        "pregnancy_due_month": p.pregnancy_due_month.isoformat() if p.pregnancy_due_month else None,
        "child_try": ls.child_try_info(db, user_id, month, p),
        "relationships": rels, "children": kids, "expenses": expenses,
        "family_expense_total": str(sum((Decimal(e["amount"]) for e in expenses if e["kind"] == "EXPENSE"), Decimal("0.00"))),
        "activities": [{"key": k, "label": a["label"], "cost": a["cost"], "hours": a["hours"]} for k, a in R.ACTIVITIES.items()],
        "interactions": [{"key": k, "label": a["label"], "cost": a["cost"], "hours": a["hours"]} for k, a in R.INTERACTIONS.items()],
        "history": [{"month": l.ref_month.isoformat(), "kind": l.kind, "text": l.text} for l in db.scalars(
            select(LifeLog).where(LifeLog.user_id == user_id).order_by(LifeLog.id.desc()).limit(30))],
    }


@router.get("")
def overview(user: CurrentUser, db: DbSession):
    return _run(db, lambda: _overview(db, user.id))


@router.put("/character")
def character(body: CharacterIn, user: CurrentUser, db: DbSession):
    def go():
        bs.ensure_setup(db, user.id)
        ls.create_character(db, user.id, name=body.name, age_years=body.age_years, gender=body.gender, interested_in=body.interested_in)
        return _overview(db, user.id)
    return _run(db, go)


@router.put("/choices")
def choices(body: ChoicesIn, user: CurrentUser, db: DbSession):
    def go():
        ls.set_choices(db, user.id, bs.ensure_setup(db, user.id), **body.model_dump())
        return _overview(db, user.id)
    return _run(db, go)


@router.post("/activities")
def activity(body: ActivityIn, user: CurrentUser, db: DbSession):
    def go():
        res = ls.do_activity(db, user.id, bs.ensure_setup(db, user.id), body.key)
        out = _overview(db, user.id)
        out["result"] = {"cost": str(res.cost), "met": res.met.name if res.met else None, "story": res.story}
        return out
    return _run(db, go)


@router.post("/people/{person_id}/interact")
def interact(person_id: int, body: ActivityIn, user: CurrentUser, db: DbSession):
    def go():
        r = ls.interact(db, user.id, bs.ensure_setup(db, user.id), person_id, body.key)
        out = _overview(db, user.id)
        react = getattr(r, "reaction", None) or {}
        out["result"] = {"story": r.last_story, "person_id": person_id, "reaction": react.get("key"), "reaction_text": react.get("text"), "delta": react.get("delta")}
        return out
    return _run(db, go)


@router.post("/people/{person_id}/relationship")
def relationship(person_id: int, body: ActionIn, user: CurrentUser, db: DbSession):
    def go():
        try:
            ls.advance_relationship(db, user.id, bs.ensure_setup(db, user.id), person_id, body.action)
        except ls.RelationshipRefused:
            db.commit()                      # grava a queda de afinidade antes de responder o erro
            raise
        return _overview(db, user.id)
    return _run(db, go)


@router.put("/people/{person_id}/finances")
def finances(person_id: int, body: FinanceRulesIn, user: CurrentUser, db: DbSession):
    def go():
        ls.set_finance_rules(db, user.id, bs.ensure_setup(db, user.id), person_id, mode=body.mode,
                             contribution_pct=body.contribution_pct)
        return _overview(db, user.id)
    return _run(db, go)


@router.post("/children/try")
def try_child(user: CurrentUser, db: DbSession):
    def go():
        res = ls.try_for_child(db, user.id, bs.ensure_setup(db, user.id))   # recusa/falha também gravam efeitos (200)
        return {**_overview(db, user.id), **res}
    return _run(db, go)


@router.patch("/children/{child_id}")
def patch_child(child_id: int, body: ChildIn, user: CurrentUser, db: DbSession):
    def go():
        ls.update_child(db, user.id, bs.ensure_setup(db, user.id), child_id, **body.model_dump())
        return _overview(db, user.id)
    return _run(db, go)


class HousingSearchIn(BaseModel):
    budget: Decimal = Field(gt=0, max_digits=20, decimal_places=2)


@router.post("/housing/search")
def housing_search(body: HousingSearchIn, user: CurrentUser, db: DbSession):
    """Procura um aluguel pelo valor que você quer pagar: o jogo diz se há oferta e em que condição."""
    return _run(db, lambda: ls.search_housing(db, user.id, bs.ensure_setup(db, user.id), body.budget))


@router.get("/budget-impact")
def budget_impact(user: CurrentUser, db: DbSession):
    """Prévia ao vivo: como o orçamento do mês afeta saúde, bem-estar, satisfação e qualidade de vida."""
    return _run(db, lambda: ls.budget_impact(db, user.id, bs.ensure_setup(db, user.id)))


class TreatIn(BaseModel):
    treated: bool


@router.put("/conditions/{key}/treatment")
def treatment(key: str, body: TreatIn, user: CurrentUser, db: DbSession):
    def go():
        ls.set_treatment(db, user.id, bs.ensure_setup(db, user.id), key, body.treated)
        return _overview(db, user.id)
    return _run(db, go)


@router.get("/calendar")
def calendar(user: CurrentUser, db: DbSession):
    return _run(db, lambda: ls.calendar(db, user.id, bs.ensure_setup(db, user.id)))


@router.post("/move")
def move(body: MoveIn, user: CurrentUser, db: DbSession):
    def go():
        ls.move(db, user.id, bs.ensure_setup(db, user.id), kind=body.kind, monthly_cost=body.monthly_cost)
        return _overview(db, user.id)
    return _run(db, go)


@router.post("/career/change")
def career_change(body: FieldIn, user: CurrentUser, db: DbSession):
    def go():
        ls.change_career(db, user.id, bs.ensure_setup(db, user.id), body.field)
        return _overview(db, user.id)
    return _run(db, go)


@router.post("/degree")
def degree_enroll(body: DegreeIn, user: CurrentUser, db: DbSession):
    def go():
        p = ls.enroll_degree(db, user.id, bs.ensure_setup(db, user.id), body.field, body.uni)
        out = _overview(db, user.id)
        out["admission"] = getattr(p, "admission", None)
        return out
    return _run(db, go)


class ExchangeIn(BaseModel):
    program_key: str


class CountryIn(BaseModel):
    country: str


@router.get("/abroad")
def abroad(user: CurrentUser, db: DbSession):
    """País onde você mora, intercâmbio em andamento, programas disponíveis e o custo de ir morar em cada país (convertido pelo câmbio de hoje)."""
    def go():
        from backend.services import abroad_service
        m = bs.ensure_setup(db, user.id)
        return abroad_service.view(db, user.id, m.ref_month)
    return _run(db, go)


@router.post("/exchange")
def exchange_start(body: ExchangeIn, user: CurrentUser, db: DbSession):
    def go():
        from backend.services import abroad_service
        m = bs.ensure_setup(db, user.id)
        abroad_service.start_exchange(db, user.id, m, body.program_key)
        return abroad_service.view(db, user.id, m.ref_month)
    return _run(db, go)


@router.delete("/exchange")
def exchange_cancel(user: CurrentUser, db: DbSession):
    def go():
        from backend.services import abroad_service
        m = bs.ensure_setup(db, user.id)
        abroad_service.cancel_exchange(db, user.id, m)
        return abroad_service.view(db, user.id, m.ref_month)
    return _run(db, go)


@router.post("/move-abroad")
def move_abroad(body: CountryIn, user: CurrentUser, db: DbSession):
    def go():
        from backend.services import abroad_service
        m = bs.ensure_setup(db, user.id)
        res = abroad_service.move_abroad(db, user.id, m, body.country)
        return {**abroad_service.view(db, user.id, m.ref_month), "result": res}
    return _run(db, go)


@router.post("/return-home")
def return_home(user: CurrentUser, db: DbSession):
    def go():
        from backend.services import abroad_service
        m = bs.ensure_setup(db, user.id)
        res = abroad_service.return_home(db, user.id, m)
        return {**abroad_service.view(db, user.id, m.ref_month), "result": res}
    return _run(db, go)


@router.get("/universities")
def universities(user: CurrentUser, db: DbSession, field: str | None = None):
    """Faculdades do Brasil (ranking, concorrência, mensalidade, peso no currículo) e a sua chance de passar em cada uma."""
    def go():
        from backend.services import career_hub, career_rules, university_rules as ur
        month = bs.ensure_setup(db, user.id)
        p = ls.get_profile(db, user.id)
        keys = [field] if field else list(career_rules.FIELDS)
        out = []
        for u in ur.UNIVERSITIES.values():
            fields = []
            for k in keys:
                if not ur.offers_field(u, k):
                    continue
                f = career_rules.FIELDS[k]
                prep, _ = career_hub.resume_score(db, user.id, k, month.ref_month)
                last = (p.uni_attempts or {}).get(f"{u.key}:{k}")
                wait = max(0, ur.REAPPLY_MONTHS - bs.months_between(date.fromisoformat(last), month.ref_month)) if last else 0
                fields.append({"field": k, "label": f["label"], "degree": f["degree"], "months": ur.months_for(u, k, f["months"]),
                               "monthly_cost": ur.monthly_cost(u, k, f["cost"]), "chance": ur.admission_chance(u, prep), "wait_months": wait,
                               "points": ur.points_for(u, 35), "hours": round(f["hours"] * u.load)})
            if fields:
                out.append({"key": u.key, "name": u.name, "short": u.short, "state": u.state, "kind": u.kind, "ranking": u.ranking, "weight": u.weight,
                            "demand": u.demand, "salary_premium_factor": round(ur.premium_factor(u), 2), "fields": fields})
        out.sort(key=lambda x: (x["key"] == ur.OPEN_KEY, x["ranking"]))
        return {"universities": out}
    return _run(db, go)


@router.delete("/degree")
def degree_drop(user: CurrentUser, db: DbSession):
    def go():
        ls.drop_degree(db, user.id, bs.ensure_setup(db, user.id))
        return _overview(db, user.id)
    return _run(db, go)
