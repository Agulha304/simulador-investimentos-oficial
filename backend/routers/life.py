"""Vida pessoal e família (etapa 4)."""
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
from backend.services import life_service as ls

router = APIRouter(prefix="/life", tags=["life"])


class CharacterIn(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    age_years: int = Field(default=28, ge=18, le=80)
    gender: str | None = None
    interested_in: str | None = None


class FieldIn(BaseModel):
    field: str


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
                      "total": p.degree_total, "cost": career_rules.FIELDS[p.degree_field]["cost"]} if p.degree_field else None),
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
        "housing": {"kind": p.housing_kind, "monthly_cost": str(p.housing_cost),
                    "pending": ({"kind": p.pending_housing_kind, "monthly_cost": str(p.pending_housing_cost),
                                 "effective_month": p.pending_housing_month.isoformat()} if p.pending_housing_month else None)},
        "pregnancy_due_month": p.pregnancy_due_month.isoformat() if p.pregnancy_due_month else None,
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
        out["result"] = {"story": r.last_story, "person_id": person_id}
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


@router.post("/children/plan")
def plan_child(user: CurrentUser, db: DbSession):
    def go():
        ls.plan_child(db, user.id, bs.ensure_setup(db, user.id))
        return _overview(db, user.id)
    return _run(db, go)


@router.patch("/children/{child_id}")
def patch_child(child_id: int, body: ChildIn, user: CurrentUser, db: DbSession):
    def go():
        ls.update_child(db, user.id, bs.ensure_setup(db, user.id), child_id, **body.model_dump())
        return _overview(db, user.id)
    return _run(db, go)


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
def degree_enroll(body: FieldIn, user: CurrentUser, db: DbSession):
    def go():
        ls.enroll_degree(db, user.id, bs.ensure_setup(db, user.id), body.field)
        return _overview(db, user.id)
    return _run(db, go)


@router.delete("/degree")
def degree_drop(user: CurrentUser, db: DbSession):
    def go():
        ls.drop_degree(db, user.id, bs.ensure_setup(db, user.id))
        return _overview(db, user.id)
    return _run(db, go)
