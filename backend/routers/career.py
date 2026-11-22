"""Carreira e educação: empregos (CLT/PJ), vagas, currículo, freelas, cursos e FGTS."""
from decimal import Decimal

from fastapi import APIRouter
from pydantic import BaseModel

from backend.dependencies import CurrentUser, DbSession
from backend.models import CareerJob, Education
from backend.routers.budget import _run
from backend.services import budget_service as bs
from backend.services import career_hub as ch
from backend.services import career_hub_rules as H
from backend.services import career_rules, item_sync
from backend.services import life_rules as R
from backend.services import life_service as ls
from sqlalchemy import select

router = APIRouter(prefix="/career", tags=["career"])


class ApplyIn(BaseModel):
    field: str
    offer_key: str


class AcceptIn(BaseModel):
    kind: str = "CLT"
    replace_job_id: int | None = None


class ResumeIn(BaseModel):
    kind: str
    id: int
    in_resume: bool


class GigIn(BaseModel):
    field: str
    key: str


class CourseIn(BaseModel):
    key: str


class WorkIn(BaseModel):
    work_level: str


def _job_out(db, j: CareerJob, ref) -> dict:
    status = "PENDING" if j.start_month > ref else "ENDED" if j.end_month is not None and j.end_month < ref else "ACTIVE"
    clt = j.kind == "CLT"
    perks = (["13º salário", "Férias + 1/3", "FGTS (8% do bruto)"] + ([f"Vale-refeição R$ {j.vr}"] if j.vr > 0 else []) + (["Plano de saúde"] if j.health_plan else [])) if clt \
        else ["Sem 13º, férias, FGTS ou benefícios", "Ganha mais no bolso", "Pode acumular outros trabalhos"]
    can_raise, raise_note, raise_wait = ch.raise_status(j, ref)
    return {"can_raise": can_raise, "raise_note": raise_note, "raise_ready_in": raise_wait,
            "id": j.id, "title": j.title, "employer": j.employer, "field": j.field, "field_label": career_rules.FIELDS[j.field]["label"], "kind": j.kind,
            "level_name": H.LEVEL_NAME[j.level], "net": str(ch.job_net(db, j, ref) if status != "ENDED" else j.net), "hired_net": str(j.net), "since": j.start_month.isoformat(),
            "until": j.end_month.isoformat() if j.end_month else None, "status": status, "in_resume": j.in_resume, "hours": j.hours, "perks": perks, "end_reason": j.end_reason}


def _edu_out(e: Education) -> dict:
    fl = career_rules.FIELDS.get(e.field, {}).get("label", "Geral")
    return {"id": e.id, "key": e.key, "name": e.name, "kind": e.kind, "field": e.field, "field_label": fl, "months_total": e.months_total, "progress": e.progress,
            "cost_month": str(e.cost_month), "hours": e.hours, "status": e.status, "start": e.start_month.isoformat(), "end": e.end_month.isoformat() if e.end_month else None,
            "in_resume": e.in_resume, "points": e.points}


def _overview(db, user_id: int) -> dict:
    month = bs.ensure_setup(db, user_id)
    ref = month.ref_month
    ch.ensure_jobs(db, user_id, month)
    p = ls.get_profile(db, user_id)
    cur = career_rules.FIELDS.get(p.career_field or "")
    next_raise = None
    if p.career_field and p.career_since:
        k = bs.months_between(p.career_since, ref) // 12 + 1
        next_raise = bs.shift_month(p.career_since, 12 * k).isoformat()
    js = [_job_out(db, j, ref) for j in ch.jobs(db, user_id)]
    scores = {k: {"score": ch.resume_score(db, user_id, k, ref)[0], "label": f["label"], "emoji": f["emoji"]} for k, f in career_rules.FIELDS.items()}
    main = p.career_field
    _, items = ch.resume_score(db, user_id, main or career_rules.DEFAULT_FIELD, ref)
    apps = [{"id": a.id, "title": a.offer["title"], "employer": a.offer["employer"], "status": a.status, "chance": a.chance, "offer": a.offer,
             "can_accept": a.status == "APPROVED"} for a in ch._apps(db, user_id, ref)]
    return {"month": ref.isoformat(), "field": {"key": p.career_field, "label": cur["label"] if cur else None, "emoji": cur["emoji"] if cur else None,
                                               "outlook": cur["outlook"] if cur else None, "growth_pct": cur["growth"] if cur else None, "next_raise": next_raise},
            "salary": str(item_sync.salary_total(db, user_id, ref)), "jobs": js, "fgts_balance": str(p.fgts_balance),
            "fgts_can_withdraw": p.fgts_balance > 0 and not any(j["kind"] == "CLT" and j["status"] == "ACTIVE" for j in js),
            "work_level": p.work_level, "work_options": list(R.LEVELS["work_level"]), "free_hours": ls.free_hours(p) - p.hours_used,
            "resume_scores": scores, "resume_items": items, "applications": apps, "applications_left": H.MAX_APPLICATIONS - len(apps),
            "fields": [{"key": k, "label": f["label"], "emoji": f["emoji"]} for k, f in career_rules.FIELDS.items()],
            "merit": p.merit, "merit_needed": ch.MERIT_NEEDED, "raise_chance": ch.raise_chance(db, p, ref),
            "raise_ready_in": max(0, ch.RAISE_COOLDOWN - (bs.months_between(p.raise_asked_month, ref) if p.raise_asked_month else ch.RAISE_COOLDOWN)),
            "rules": {"pj_premium_pct": int((H.PJ_PREMIUM * (1 - H.PJ_TAX) - 1) * 100), "apply_hours": H.APPLY_HOURS, "pj_extra_hours": H.PJ_EXTRA_HOURS}}


@router.get("")
def overview(user: CurrentUser, db: DbSession):
    return _run(db, lambda: _overview(db, user.id))


@router.get("/offers")
def offers(field: str, user: CurrentUser, db: DbSession):
    def go():
        m = bs.ensure_setup(db, user.id)
        applied = {a.offer_key: a.status for a in ch._apps(db, user.id, m.ref_month)}
        return {"field": field, "score": ch.resume_score(db, user.id, field, m.ref_month)[0],
                "offers": [{**o, "applied": applied.get(o["key"])} for o in ch.offers(db, user.id, m, field)]}
    return _run(db, go)


@router.post("/apply")
def apply(body: ApplyIn, user: CurrentUser, db: DbSession):
    def go():
        a = ch.apply(db, user.id, bs.ensure_setup(db, user.id), body.field, body.offer_key)
        return {**_overview(db, user.id), "result": {"status": a.status, "chance": a.chance, "title": a.offer["title"], "employer": a.offer["employer"], "app_id": a.id}}
    return _run(db, go)


@router.post("/applications/{app_id}/accept")
def accept(app_id: int, body: AcceptIn, user: CurrentUser, db: DbSession):
    def go():
        ch.accept(db, user.id, bs.ensure_setup(db, user.id), app_id, body.kind, body.replace_job_id)
        return _overview(db, user.id)
    return _run(db, go)


@router.post("/jobs/{job_id}/quit")
def quit_job(job_id: int, user: CurrentUser, db: DbSession):
    def go():
        ch.quit_job(db, user.id, bs.ensure_setup(db, user.id), job_id)
        return _overview(db, user.id)
    return _run(db, go)


@router.put("/resume")
def resume(body: ResumeIn, user: CurrentUser, db: DbSession):
    def go():
        ch.set_resume(db, user.id, body.kind, body.id, body.in_resume)
        return _overview(db, user.id)
    return _run(db, go)


@router.put("/work")
def work(body: WorkIn, user: CurrentUser, db: DbSession):
    def go():
        ls.set_choices(db, user.id, bs.ensure_setup(db, user.id), work_level=body.work_level)
        return _overview(db, user.id)
    return _run(db, go)


@router.post("/raise/ask")
def ask_raise(user: CurrentUser, db: DbSession):
    def go():
        res = ch.ask_raise(db, user.id, bs.ensure_setup(db, user.id))
        return {**_overview(db, user.id), "raise_result": res}
    return _run(db, go)


@router.post("/jobs/{job_id}/raise/ask")
def ask_raise_for_job(job_id: int, user: CurrentUser, db: DbSession):
    """Pede aumento NESTE emprego (cada emprego CLT tem o seu botão e o seu intervalo de 6 meses)."""
    def go():
        res = ch.ask_raise(db, user.id, bs.ensure_setup(db, user.id), job_id)
        return {**_overview(db, user.id), "raise_result": res}
    return _run(db, go)


@router.get("/freelance")
def freelance(field: str, user: CurrentUser, db: DbSession):
    def go():
        m = bs.ensure_setup(db, user.id)
        p = ls.get_profile(db, user.id)
        return {"field": field, "free_hours": ls.free_hours(p) - p.hours_used, "gigs": ch.gigs(db, user.id, m, field),
                "score": ch.resume_score(db, user.id, field, m.ref_month)[0]}
    return _run(db, go)


@router.post("/freelance/accept")
def freelance_accept(body: GigIn, user: CurrentUser, db: DbSession):
    def go():
        ch.accept_gig(db, user.id, bs.ensure_setup(db, user.id), body.field, body.key)
        return _overview(db, user.id)
    return _run(db, go)


@router.post("/fgts/withdraw")
def fgts(user: CurrentUser, db: DbSession):
    def go():
        ch.withdraw_fgts(db, user.id, bs.ensure_setup(db, user.id))
        return _overview(db, user.id)
    return _run(db, go)


# ---------------------------------------------------------------- educação
def _education(db, user_id: int) -> dict:
    month = bs.ensure_setup(db, user_id)
    ch.ensure_degree_rows(db, user_id, month.ref_month)
    p = ls.get_profile(db, user_id)
    rows = list(db.scalars(select(Education).where(Education.user_id == user_id).order_by(Education.id.desc())))
    state = {(e.kind, e.key): e for e in rows if e.status in ("ACTIVE", "DONE")}
    courses = []
    for k, (name, field, months, cost, hours, pts) in H.COURSES.items():
        e = state.get(("COURSE", k))
        courses.append({"key": k, "name": name, "field": field, "field_label": career_rules.FIELDS.get(field, {}).get("label", "Geral"), "months": months,
                        "cost_month": cost, "hours": hours, "points": pts, "status": e.status if e else None, "id": e.id if e else None})
    degrees = []
    for k, f in career_rules.FIELDS.items():
        e = state.get(("DEGREE", k))
        degrees.append({"key": k, "label": f["label"], "emoji": f["emoji"], "degree": f["degree"], "months": f["months"], "cost_month": f["cost"], "hours": f["hours"],
                        "premium_pct": f["premium"], "status": e.status if e else None})
    return {"month": month.ref_month.isoformat(), "courses": courses, "degrees": degrees, "history": [_edu_out(e) for e in rows], "free_hours": ls.free_hours(p) - p.hours_used,
            "studying": {"field": p.degree_field, "progress": p.degree_progress, "total": p.degree_total} if p.degree_field else None}


@router.get("/education")
def education(user: CurrentUser, db: DbSession):
    return _run(db, lambda: _education(db, user.id))


@router.post("/education/courses")
def enroll(body: CourseIn, user: CurrentUser, db: DbSession):
    def go():
        ch.enroll_course(db, user.id, bs.ensure_setup(db, user.id), body.key)
        return _education(db, user.id)
    return _run(db, go)


@router.delete("/education/courses/{edu_id}")
def drop(edu_id: int, user: CurrentUser, db: DbSession):
    def go():
        ch.drop_course(db, user.id, bs.ensure_setup(db, user.id), edu_id)
        return _education(db, user.id)
    return _run(db, go)
