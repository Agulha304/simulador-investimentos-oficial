"""Carreira: vagas, candidaturas, currículo, empregos (CLT/PJ), freelas e educação.

* O salário continua sendo um item recorrente do orçamento (categoria "Salário"); cada emprego novo cria o seu e, ao trocar de emprego, o antigo termina.
* CLT: 13º, férias + 1/3, FGTS (8% do bruto), vale-refeição e plano de saúde dependendo da vaga. PJ: ~18% a mais no bolso, sem benefícios, e dá para
  acumular outros trabalhos (cada extra consome horas livres).
* Currículo: só entram cursos, faculdades e empregos que o jogador deixou marcados. Vagas pedem experiência na área; quanto mais currículo, maior a chance.
"""
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.core.money import quantize_money
from backend.models import (
    BudgetCategory, CareerJob, Education, FlowKind, Gig, JobApplication, LifeProfile, RecurringItem, RecurringItemVersion, SimMonth,
)
from backend.services import budget_service, career_rules, finance_ledger, item_sync
from backend.services import career_hub_rules as H
from backend.services import life_service as ls
from backend.services import university_rules as uni_rules
from backend.services import country_rules as cr
from backend.services import exchange_rules as xr
from backend.services import world_service as ws
from backend.services.finance_ledger import ConflictError, FinanceError, NotFoundError
from backend.services.life_rules import hash01

ZERO = Decimal("0.00")
D = Decimal
MAX_COURSES = 3


def _field(key: str) -> dict:
    f = career_rules.FIELDS.get(key)
    if f is None:
        raise FinanceError("área inválida")
    return f


def _profile(db: Session, user_id: int) -> LifeProfile:
    p = ls.get_profile(db, user_id, create=False)
    if p is None:
        raise NotFoundError("crie o personagem primeiro")
    return p


# ------------------------------------------------------------------ empregos
def _item_amount(db: Session, rid: int, ref: date) -> Decimal:
    r = db.get(RecurringItem, rid)
    if r is None or not budget_service.is_due(r, ref):
        return ZERO
    return budget_service.version_amount(db, rid, ref) or ZERO


def _linked_ids(db: Session, user_id: int) -> set[int]:
    return {x for x in db.scalars(select(CareerJob.recurring_item_id).where(CareerJob.user_id == user_id, CareerJob.recurring_item_id.is_not(None)))}


def job_net(db: Session, j: CareerJob, ref: date) -> Decimal:
    """Salário líquido vigente do emprego (lê o item recorrente; o emprego inicial soma os salários sem vínculo)."""
    if j.recurring_item_id:
        return _item_amount(db, j.recurring_item_id, ref) or (j.net if j.start_month > ref else ZERO)
    total = item_sync.salary_total(db, j.user_id, ref)
    linked = sum((_item_amount(db, rid, ref) for rid in _linked_ids(db, j.user_id)), ZERO)
    return max(ZERO, total - linked)


def _level_for_salary(net: Decimal) -> int:
    return 0 if net < 2500 else 1 if net < 4500 else 2 if net < 8000 else 3


def ensure_jobs(db: Session, user_id: int, month: SimMonth, *, title: str | None = None, employer: str | None = None) -> None:
    """Cria o emprego inicial (CLT) a partir do salário já existente no orçamento."""
    if db.scalar(select(CareerJob.id).where(CareerJob.user_id == user_id).limit(1)) is not None:
        return
    p = _profile(db, user_id)
    net = item_sync.salary_total(db, user_id, month.ref_month)
    if net <= 0:
        return
    field = p.career_field or career_rules.DEFAULT_FIELD
    lvl = _level_for_salary(net)
    pick = hash01("first-job", user_id)
    db.add(CareerJob(user_id=user_id, title=title or H.LADDER[field][lvl][int(pick * 3)], employer=employer or H.EMPLOYERS[int(hash01("first-emp", user_id) * len(H.EMPLOYERS))],
                     field=field, kind="CLT", level=lvl, net=net, vr=ZERO, health_plan=False, hours=0, start_month=p.career_since or month.ref_month,
                     legacy=True, in_resume=True))
    db.flush()


def jobs(db: Session, user_id: int) -> list[CareerJob]:
    return list(db.scalars(select(CareerJob).where(CareerJob.user_id == user_id).order_by(CareerJob.start_month, CareerJob.id)))


def active_jobs(db: Session, user_id: int, ref: date) -> list[CareerJob]:
    return [j for j in jobs(db, user_id) if j.start_month <= ref and (j.end_month is None or j.end_month >= ref)]


def _stop_item(r: RecurringItem, ref: date) -> None:
    if r.start_month > ref:
        r.active = False
    else:
        r.end_month = ref


def _end_job(db: Session, j: CareerJob, ref: date, reason: str) -> None:
    j.end_month, j.end_reason = max(j.start_month, ref), reason
    if j.recurring_item_id:
        r = db.get(RecurringItem, j.recurring_item_id)
        if r:
            _stop_item(r, ref)
    else:
        cat = db.scalar(select(BudgetCategory.id).where(BudgetCategory.user_id == j.user_id, BudgetCategory.kind == FlowKind.INCOME, BudgetCategory.name == "Salário"))
        linked = _linked_ids(db, j.user_id)
        for r in db.scalars(select(RecurringItem).where(RecurringItem.user_id == j.user_id, RecurringItem.category_id == cat, RecurringItem.active.is_(True))):
            if r.id not in linked:
                _stop_item(r, ref)


def recalc_hours(db: Session, user_id: int) -> None:
    p = ls.get_profile(db, user_id, create=False)
    if p is None:
        return
    from backend.services import artist_service
    total = sum(j.hours for j in jobs(db, user_id) if j.end_month is None) + artist_service.committed_hours(db, user_id)
    total += sum(e.hours for e in db.scalars(select(Education).where(Education.user_id == user_id, Education.kind == "COURSE", Education.status == "ACTIVE")))
    p.career_hours = total
    db.flush()


def quit_job(db: Session, user_id: int, month: SimMonth, job_id: int) -> None:
    budget_service.require_open(month)
    ensure_jobs(db, user_id, month)
    j = db.get(CareerJob, job_id)
    if j is None or j.user_id != user_id:
        raise NotFoundError("emprego não encontrado")
    if j.end_month is not None and j.end_month < month.ref_month:
        raise ConflictError("você já saiu desse emprego")
    _end_job(db, j, month.ref_month, "QUIT")
    ls.log(db, user_id, month.ref_month, "JOB_QUIT", f"Você pediu demissão de {j.title} ({j.employer})")
    recalc_hours(db, user_id)
    ls.sync_month(db, user_id, month)


# ------------------------------------------------------------------ currículo
def resume_score(db: Session, user_id: int, field: str, ref: date) -> tuple[float, list[dict]]:
    items, s = [], 0.0
    for e in db.scalars(select(Education).where(Education.user_id == user_id, Education.status == "DONE", Education.in_resume.is_(True))):
        if e.kind == "DEGREE":
            base = float(e.points or H.DEGREE_POINTS)            # diploma de faculdade forte vale mais (peso da instituição)
            pts = base if e.field == field else H.OTHER_DEGREE_POINTS * base / H.DEGREE_POINTS
        else:
            pts = float(e.points) if e.field == field else (e.points * 0.5 if e.field == "geral" else 0.0)
        if pts:
            items.append({"kind": "education", "name": e.name, "points": round(pts, 1)})
            s += pts
    for j in jobs(db, user_id):
        if not j.in_resume or j.start_month > ref:
            continue
        months = budget_service.months_between(j.start_month, min(j.end_month or ref, ref)) + 1
        pts = min(30.0, months * 0.5) if j.field == field else min(8.0, months * 0.15)
        items.append({"kind": "job", "name": f"{j.title} — {j.employer}", "points": round(pts, 1)})
        s += pts
    return min(100.0, round(s, 1)), items


def set_resume(db: Session, user_id: int, kind: str, item_id: int, on: bool) -> None:
    row = db.get(CareerJob if kind == "job" else Education, item_id) if kind in ("job", "education") else None
    if row is None or row.user_id != user_id:
        raise NotFoundError("item não encontrado")
    row.in_resume = on
    db.flush()


# ------------------------------------------------------------------ vagas e candidaturas
def _clt_pack(net: int, level: int) -> dict:
    gross = round(H.clt_gross(net), 2)
    return {"net": net, "gross": gross, "vr": [0, 400, 650, 900][level], "health_plan": level >= 1, "fgts_month": round(gross * H.FGTS_RATE, 2),
            "thirteenth": net, "vacation_bonus": round(net / 3, 2)}


def offers(db: Session, user_id: int, month: SimMonth, field: str, country: str = "BR") -> list[dict]:
    """Vagas da área no país escolhido. Cada vaga é PRESENCIAL ou REMOTA (sorteio por área). Quem não mora no país só consegue vagas remotas
    (as presenciais aparecem, mas exigem morar lá). Vagas no exterior pagam na moeda do país (convertida pelo câmbio do mês), com o imposto
    de renda daquele país, e são mais difíceis de conseguir."""
    f = _field(field)
    country = country.upper()
    try:
        c = cr.get(country)
    except ValueError:
        raise FinanceError("país desconhecido") from None
    ref = month.ref_month
    p = ls.get_profile(db, user_id)
    resident = p.country if p is not None else "BR"
    score, _ = resume_score(db, user_id, field, ref)
    n = 1 + int(hash01("vagas", user_id, ref.isoformat(), field, *([] if country == "BR" else [country])) * 3)   # difícil de achar: 1 a 3 vagas por área no mês
    out = []
    for i in range(n):
        key = f"{field}:{ref:%Y-%m}:{i}" if country == "BR" else f"{field}:{country}:{ref:%Y-%m}:{i}"
        level = [0, 0, 1, 1, 2, 3][int(hash01("lvl", user_id, key) * 6)]
        net = H.offer_net(f["start"], level, user_id, key)
        titles = H.LADDER[field][level]
        remote = hash01("remote", user_id, key) < xr.REMOTE_SHARE.get(field, 0.0)
        needs_move = (not remote) and country != resident
        hard = (xr.ABROAD_HARD if country != "BR" else 0.0) + (xr.REMOTE_HARD if remote else 0.0)
        o = {"key": key, "field": field, "field_label": f["label"], "level": level, "level_name": H.LEVEL_NAME[level], "need": H.LEVEL_NEED[level],
             "title": titles[int(hash01("title", user_id, key) * len(titles))], "employer": H.EMPLOYERS[int(hash01("emp", user_id, key) * len(H.EMPLOYERS))],
             "clt": _clt_pack(net, level), "pj": {"net": H.pj_net(net), "hours": H.pj_hours(field, level, user_id, key)}, "chance": H.approval_chance(score, level, hard),
             "country": country, "country_name": c.name, "flag": c.flag, "work_mode": "REMOTE" if remote else "ONSITE", "needs_move": needs_move}
        if country != "BR":
            brl_eq = net * c.wage_index * (1 - c.income_tax / 100) / (1 - 0.12)      # mesmo cargo, salário do país já líquido do imposto de lá
            local = round(brl_eq / c.fx0 * float(ws.price_level(db, user_id, country, ref)), 2)      # salários acompanham a inflação simulada do país
            now = ws.convert(db, user_id, country, local, ref)
            o["intl"] = {"currency": c.currency, "symbol": c.symbol, "net_local": local, "net_brl": str(now), "income_tax": c.income_tax,
                         "rate": str(ws.fx(db, user_id, country, ref))}
        out.append(o)
    return out


def _apps(db: Session, user_id: int, ref: date) -> list[JobApplication]:
    return list(db.scalars(select(JobApplication).where(JobApplication.user_id == user_id, JobApplication.ref_month == ref).order_by(JobApplication.id)))


def apply(db: Session, user_id: int, month: SimMonth, field: str, offer_key: str, country: str = "BR") -> JobApplication:
    budget_service.require_open(month)
    ensure_jobs(db, user_id, month)
    p = _profile(db, user_id)
    offer = next((o for o in offers(db, user_id, month, field, country) if o["key"] == offer_key), None)
    if offer is None:
        raise NotFoundError("essa vaga não existe mais")
    if offer["needs_move"]:
        raise ConflictError(f"vaga presencial em {offer['country_name']}: você precisa morar lá (mude-se na aba Intercâmbio e mundo) ou procure vagas remotas")
    if db.scalar(select(JobApplication.id).where(JobApplication.user_id == user_id, JobApplication.offer_key == offer_key)):
        raise ConflictError("você já se candidatou a essa vaga")
    if len(_apps(db, user_id, month.ref_month)) >= H.MAX_APPLICATIONS:
        raise ConflictError(f"você já fez {H.MAX_APPLICATIONS} candidaturas neste mês: espere o próximo")
    ls.spend_hours(p, H.APPLY_HOURS, "Candidaturas a vagas")
    ok = hash01("apply", user_id, offer_key) * 100 < offer["chance"]
    app = JobApplication(user_id=user_id, ref_month=month.ref_month, offer_key=offer_key, offer=offer, chance=offer["chance"], status="APPROVED" if ok else "REJECTED")
    db.add(app)
    ls.log(db, user_id, month.ref_month, "JOB_APPLY",
           f"Você se candidatou a {offer['title']} ({offer['employer']}): " + ("APROVADO(A)! Você pode aceitar a vaga neste mês." if ok else "não foi dessa vez."))
    if not ok:
        p.satisfaction = ls._clamp(p.satisfaction - 1)
    db.flush()
    return app


def accept(db: Session, user_id: int, month: SimMonth, app_id: int, kind: str, replace_job_id: int | None = None) -> CareerJob:
    budget_service.require_open(month)
    ensure_jobs(db, user_id, month)
    if kind not in ("CLT", "PJ", "INT"):
        raise FinanceError("escolha CLT ou PJ")
    app = db.get(JobApplication, app_id)
    if app is None or app.user_id != user_id:
        raise NotFoundError("candidatura não encontrada")
    ref = month.ref_month
    if app.status != "APPROVED" or app.ref_month != ref:
        raise ConflictError("só dá para aceitar uma vaga aprovada neste mesmo mês")
    p = _profile(db, user_id)
    o = app.offer
    foreign = o.get("country", "BR") != "BR"
    if foreign:
        kind = "INT"                                  # contrato internacional: sem 13º/férias/FGTS do Brasil
    elif kind == "INT":
        raise FinanceError("escolha CLT ou PJ")
    if o.get("work_mode") == "ONSITE" and o.get("country", "BR") != p.country:
        raise ConflictError("vaga presencial em outro país: você precisa morar lá para aceitar")
    start = budget_service.shift_month(ref, 1)
    current = [j for j in jobs(db, user_id) if j.end_month is None]
    replace = db.get(CareerJob, replace_job_id) if replace_job_id else None
    if replace_job_id and (replace is None or replace.user_id != user_id or replace.end_month is not None):
        raise NotFoundError("emprego a substituir não encontrado")
    if kind == "CLT":
        replace = replace or next((j for j in current if j.kind == "CLT"), None)           # só existe um CLT por vez: trocar de emprego
    remaining = [j for j in current if replace is None or j.id != replace.id]
    extra = bool(remaining)
    hours = int(o.get("pj", {}).get("hours") or H.PJ_EXTRA_HOURS) if (kind == "PJ" and extra) else 0
    if hours and ls.free_hours(p) < hours:
        raise ConflictError(f"um trabalho PJ extra consome {hours}h livres por mês e você só tem {ls.free_hours(p)}h")
    net = Decimal(str(o["intl"]["net_brl"] if kind == "INT" else o["clt"]["net"] if kind == "CLT" else o["pj"]["net"]))
    if replace:
        _end_job(db, replace, ref, "REPLACED")
    cat = item_sync.category(db, user_id, FlowKind.INCOME, "Salário")
    acc = finance_ledger.personal_account(db, user_id)
    r = RecurringItem(user_id=user_id, account_id=acc.id, category_id=cat.id, name=f"Salário — {o['title']}"[:80], kind=FlowKind.INCOME, start_month=start)
    db.add(r)
    db.flush()
    db.add(RecurringItemVersion(item_id=r.id, amount=quantize_money(net), effective_from=start))
    clt = kind == "CLT"
    job = CareerJob(user_id=user_id, title=o["title"], employer=o["employer"], field=o["field"], kind=kind, level=o["level"], net=quantize_money(net),
                    vr=D(str(o["clt"]["vr"])) if clt else ZERO, health_plan=bool(o["clt"]["health_plan"]) if clt else foreign, hours=hours,
                    start_month=start, recurring_item_id=r.id, in_resume=True, country=o.get("country", "BR"), work_mode=o.get("work_mode", "ONSITE"),
                    net_local=D(str(o["intl"]["net_local"])) if foreign else None)
    db.add(job)
    app.status = "ACCEPTED"
    p.career_field, p.career_since = o["field"], start
    ls.log(db, user_id, ref, "JOB_START", f"Você aceitou {o['title']} na {o['employer']} ({kind}), com início em {start:%m/%Y}")
    db.flush()
    recalc_hours(db, user_id)
    ls.sync_month(db, user_id, month)
    return job


def reprice_foreign_jobs(db: Session, user_id: int, ref: date) -> int:
    """Abertura do mês: o salário de vagas no exterior é em moeda local; reajusta o contrato pelo câmbio do mês (nova versão do salário)."""
    n = 0
    for j in active_jobs(db, user_id, ref):
        if j.country == "BR" or not j.net_local or not j.recurring_item_id:
            continue
        infl = ws.price_level(db, user_id, j.country, ref) / ws.price_level(db, user_id, j.country, max(j.start_month, ws.EPOCH))
        new = ws.convert(db, user_id, j.country, D(str(j.net_local)) * infl, ref)
        cur = budget_service.version_amount(db, j.recurring_item_id, ref) or ZERO
        if cur and abs(new - cur) / cur > D("0.005"):
            ex = db.scalar(select(RecurringItemVersion).where(RecurringItemVersion.item_id == j.recurring_item_id, RecurringItemVersion.effective_from == ref))
            if ex is not None:
                ex.amount = new
            else:
                db.add(RecurringItemVersion(item_id=j.recurring_item_id, amount=new, effective_from=ref))
            n += 1
    db.flush()
    return n


# ------------------------------------------------------------------ freelas
def gigs(db: Session, user_id: int, month: SimMonth, field: str) -> list[dict]:
    f = _field(field)
    ref = month.ref_month
    score, _ = resume_score(db, user_id, field, ref)
    n = min(4, int(hash01("gigs-n", user_id, ref.isoformat(), field) * (2.0 + score / 30)))
    taken = {g.key for g in db.scalars(select(Gig).where(Gig.user_id == user_id, Gig.ref_month == ref))}
    out = []
    for i in range(n):
        key = f"{field}:{ref:%Y-%m}:{i}"
        titles = H.GIG_TITLES[field] + H.GIG_TITLES["geral"][:1]
        hours = 8 + int(hash01("gig-h", user_id, key) * 22)
        rate = (35 + score * 0.6) * (0.9 + 0.25 * hash01("gig-r", user_id, key))
        out.append({"key": key, "field": field, "field_label": f["label"], "title": titles[int(hash01("gig-t", user_id, key) * len(titles))],
                    "hours": hours, "pay": str(quantize_money(D(str(hours * rate)))), "taken": key in taken})
    return out


def accept_gig(db: Session, user_id: int, month: SimMonth, field: str, key: str) -> Gig:
    budget_service.require_open(month)
    g = next((x for x in gigs(db, user_id, month, field) if x["key"] == key), None)
    if g is None:
        raise NotFoundError("esse freela não está mais disponível")
    if g["taken"]:
        raise ConflictError("você já pegou esse freela")
    p = _profile(db, user_id)
    ls.spend_hours(p, g["hours"], f"Freela: {g['title']}")
    row = Gig(user_id=user_id, ref_month=month.ref_month, key=key, field=field, title=g["title"], hours=g["hours"], pay=D(g["pay"]))
    db.add(row)
    ls.log(db, user_id, month.ref_month, "GIG", f"Você pegou um freela: {g['title']} ({g['hours']}h, R$ {g['pay']})")
    db.flush()
    ls.sync_month(db, user_id, month)
    return row


# ------------------------------------------------------------------ educação
def _degree_row(db: Session, user_id: int, field: str, status: str | None = None) -> Education | None:
    q = select(Education).where(Education.user_id == user_id, Education.kind == "DEGREE", Education.key == field)
    if status:
        q = q.where(Education.status == status)
    return db.scalars(q.order_by(Education.id.desc())).first()


def ensure_degree_rows(db: Session, user_id: int, ref: date) -> None:
    p = ls.get_profile(db, user_id, create=False)
    if p is None:
        return
    for fld in p.degrees or []:
        if _degree_row(db, user_id, fld, "DONE") is None:
            fr = career_rules.FIELDS[fld]
            u = uni_rules.get((p.degree_unis or {}).get(fld, uni_rules.OPEN_KEY))
            db.add(Education(user_id=user_id, key=fld, name=fr["degree"] + (f" — {u.short}" if u.key != uni_rules.OPEN_KEY else ""), field=fld, kind="DEGREE",
                             months_total=fr["months"], progress=fr["months"], cost_month=D(fr["cost"]), hours=0, points=uni_rules.points_for(u, H.DEGREE_POINTS),
                             status="DONE", start_month=ref, end_month=ref))
    if p.degree_field and _degree_row(db, user_id, p.degree_field, "ACTIVE") is None:
        fr = career_rules.FIELDS[p.degree_field]
        u = uni_rules.get(p.degree_uni or uni_rules.OPEN_KEY)
        db.add(Education(user_id=user_id, key=p.degree_field, name=fr["degree"] + (f" — {u.short}" if u.key != uni_rules.OPEN_KEY else ""), field=p.degree_field, kind="DEGREE",
                         months_total=p.degree_total or fr["months"], progress=p.degree_progress, cost_month=D(uni_rules.monthly_cost(u, p.degree_field, fr["cost"])),
                         hours=0, points=uni_rules.points_for(u, H.DEGREE_POINTS), status="ACTIVE", start_month=ref))
    db.flush()


def on_degree_start(db: Session, p: LifeProfile, field: str, ref: date) -> None:
    fr = career_rules.FIELDS[field]
    u = uni_rules.get(p.degree_uni or uni_rules.OPEN_KEY)
    db.add(Education(user_id=p.user_id, key=field, name=fr["degree"] + (f" — {u.short}" if u.key != uni_rules.OPEN_KEY else ""), field=field, kind="DEGREE",
                     months_total=p.degree_total or fr["months"], cost_month=D(uni_rules.monthly_cost(u, field, fr["cost"])), hours=0,
                     points=uni_rules.points_for(u, H.DEGREE_POINTS), status="ACTIVE", start_month=ref))
    db.flush()


def on_degree_end(db: Session, p: LifeProfile, field: str, ref: date, done: bool) -> None:
    row = _degree_row(db, p.user_id, field, "ACTIVE")
    if row:
        row.status, row.end_month = ("DONE", ref) if done else ("DROPPED", ref)
        if done:
            row.progress = row.months_total
    db.flush()


def enroll_course(db: Session, user_id: int, month: SimMonth, key: str) -> Education:
    budget_service.require_open(month)
    c = H.COURSES.get(key)
    if c is None:
        raise NotFoundError("curso não encontrado")
    name, field, months, cost, hours, pts = c
    p = _profile(db, user_id)
    rows = list(db.scalars(select(Education).where(Education.user_id == user_id, Education.kind == "COURSE", Education.key == key)))
    if any(r.status in ("ACTIVE", "DONE") for r in rows):
        raise ConflictError("você já fez ou está fazendo esse curso")
    if sum(1 for e in db.scalars(select(Education).where(Education.user_id == user_id, Education.kind == "COURSE", Education.status == "ACTIVE"))) >= MAX_COURSES:
        raise ConflictError(f"no máximo {MAX_COURSES} cursos ao mesmo tempo")
    if ls.free_hours(p) < hours:
        raise ConflictError(f"este curso pede {hours}h livres por mês e você só tem {ls.free_hours(p)}h")
    e = Education(user_id=user_id, key=key, name=name, field=field, kind="COURSE", months_total=months, cost_month=D(cost), hours=hours, points=pts,
                  status="ACTIVE", start_month=month.ref_month, in_resume=True)
    db.add(e)
    ls.log(db, user_id, month.ref_month, "COURSE_START", f"Você começou o curso {name} ({months} meses, R$ {cost}/mês, {hours}h/mês)")
    db.flush()
    recalc_hours(db, user_id)
    ls.sync_month(db, user_id, month)
    return e


def drop_course(db: Session, user_id: int, month: SimMonth, edu_id: int) -> None:
    budget_service.require_open(month)
    e = db.get(Education, edu_id)
    if e is None or e.user_id != user_id or e.kind != "COURSE" or e.status != "ACTIVE":
        raise NotFoundError("curso em andamento não encontrado")
    e.status, e.end_month = "DROPPED", month.ref_month
    ls.log(db, user_id, month.ref_month, "COURSE_DROP", f"Você desistiu do curso {e.name}")
    db.flush()
    recalc_hours(db, user_id)
    ls.sync_month(db, user_id, month)


# ------------------------------------------------------------------ integração com a vida pessoal (orçamento e fechamento do mês)
def desired_items(db: Session, user_id: int, ref: date, want) -> None:
    for j in active_jobs(db, user_id, ref):
        net = job_net(db, j, ref)
        if j.kind != "CLT" or net <= 0:
            continue
        if j.vr > 0:
            want(f"life:job:{j.id}:vr", f"Vale-refeição — {j.title}", FlowKind.INCOME, "Renda extra", j.vr)
        if ref.month == 12:
            want(f"life:job:{j.id}:13th", f"13º salário — {j.title}", FlowKind.INCOME, "Renda extra", net)
        if ref.month == 7:
            want(f"life:job:{j.id}:vac", f"Adicional de férias (1/3) — {j.title}", FlowKind.INCOME, "Renda extra", net / 3)
    for g in db.scalars(select(Gig).where(Gig.user_id == user_id, Gig.ref_month == ref)):
        want(f"life:gig:{g.id}", f"Freela: {g.title}", FlowKind.INCOME, "Renda extra", g.pay)
    for e in db.scalars(select(Education).where(Education.user_id == user_id, Education.kind == "COURSE", Education.status == "ACTIVE")):
        if e.start_month <= ref:
            want(f"life:course:{e.id}", f"Curso: {e.name}", FlowKind.EXPENSE, "Educação", e.cost_month)
    p = ls.get_profile(db, user_id, create=False)
    if p is not None and p.fgts_release > 0:
        want("life:fgts", "Saque do FGTS", FlowKind.INCOME, "Renda extra", p.fgts_release)


def process_month(db: Session, p: LifeProfile, ref: date) -> None:
    for e in db.scalars(select(Education).where(Education.user_id == p.user_id, Education.kind == "COURSE", Education.status == "ACTIVE")):
        if e.start_month > ref:
            continue
        e.progress += 1
        if e.progress >= e.months_total:
            e.status, e.end_month = "DONE", ref
            p.satisfaction = ls._clamp(p.satisfaction + 3)
            ls.log(db, p.user_id, ref, "COURSE_DONE", f"Você concluiu o curso {e.name}! Ele já pode entrar no seu currículo.")
    plan = False
    for j in active_jobs(db, p.user_id, ref):
        if j.kind == "CLT":
            p.fgts_balance += quantize_money(D(str(H.clt_gross(float(job_net(db, j, ref))) * H.FGTS_RATE)))
            plan = plan or j.health_plan
    if plan:
        p.health = ls._clamp(p.health + 1)                                      # plano de saúde do emprego
    if active_jobs(db, p.user_id, ref):                                         # trabalhar muito gera mérito; trabalhar pouco, não
        add_merit(p, {"INTENSE": 12, "NORMAL": 2, "REDUCED": -4}.get(p.work_level, 0))
    p.fgts_release = ZERO
    recalc_hours(db, p.user_id)


def withdraw_fgts(db: Session, user_id: int, month: SimMonth) -> Decimal:
    budget_service.require_open(month)
    p = _profile(db, user_id)
    ensure_jobs(db, user_id, month)
    if any(j.kind == "CLT" for j in active_jobs(db, user_id, month.ref_month)):
        raise ConflictError("o saque só é liberado quando você não tem um emprego CLT ativo")
    if p.fgts_balance <= 0:
        raise ConflictError("você não tem saldo de FGTS")
    amount = p.fgts_balance
    p.fgts_release, p.fgts_balance = amount, ZERO
    ls.log(db, user_id, month.ref_month, "FGTS", f"Você sacou R$ {amount} do FGTS")
    db.flush()
    ls.sync_month(db, user_id, month)
    return amount


# ------------------------------------------------------------------ aumento por mérito e pedido de aumento
RAISE_COOLDOWN = 6                     # meses entre aumentos / pedidos
MERIT_NEEDED = 60


def _top_job(db: Session, user_id: int, ref: date, kind: str | None = None) -> CareerJob | None:
    act = [j for j in active_jobs(db, user_id, ref) if kind is None or j.kind == kind]
    return max(act, key=lambda j: job_net(db, j, ref), default=None)


def raise_status(j: CareerJob, ref: date) -> tuple[bool, str | None, int]:
    """Pode pedir aumento NESTE emprego agora? (ok, motivo se não, meses até poder). Vale por emprego."""
    if j.start_month > ref or (j.end_month is not None and j.end_month < ref):
        return False, "emprego não está ativo", 0
    if j.kind == "PJ":
        return False, "no PJ você renegocia o contrato ao trocar de cliente: aumento só em emprego CLT", 0
    wait_tenure = max(0, RAISE_COOLDOWN - budget_service.months_between(j.start_month, ref))
    wait_ask = max(0, RAISE_COOLDOWN - budget_service.months_between(j.raise_asked_month, ref)) if j.raise_asked_month else 0
    wait = max(wait_tenure, wait_ask)
    if wait_tenure and wait_tenure >= wait_ask:
        return False, "espere pelo menos 6 meses no emprego antes de pedir aumento", wait
    if wait_ask:
        return False, "você já pediu aumento neste emprego há pouco tempo: espere 6 meses", wait
    return True, None, 0


def raise_salary(db: Session, user_id: int, job: CareerJob, effective: date, pct: float) -> None:
    """Aumento de verdade: nova versão do salário do emprego a partir de `effective` (o histórico fica)."""
    cat = db.scalar(select(BudgetCategory.id).where(BudgetCategory.user_id == user_id, BudgetCategory.kind == FlowKind.INCOME, BudgetCategory.name == "Salário"))
    linked = _linked_ids(db, user_id)
    for r in db.scalars(select(RecurringItem).where(RecurringItem.user_id == user_id, RecurringItem.category_id == cat, RecurringItem.active.is_(True))):
        if (job.recurring_item_id and r.id != job.recurring_item_id) or (not job.recurring_item_id and r.id in linked):
            continue
        cur = budget_service.version_amount(db, r.id, effective)
        if not cur:
            continue
        new = quantize_money(cur * D(str(1 + pct / 100)))
        ex = db.scalar(select(RecurringItemVersion).where(RecurringItemVersion.item_id == r.id, RecurringItemVersion.effective_from == effective))
        if ex:
            ex.amount = new
        else:
            db.add(RecurringItemVersion(item_id=r.id, amount=new, effective_from=effective))
    db.flush()


def add_merit(p: LifeProfile, n: int) -> None:
    p.merit = max(0, min(100, (p.merit or 0) + n))


def months_since_raise(db: Session, p: LifeProfile, ref: date) -> int:
    last = max([d for d in (p.last_raise_month, p.career_since) if d] or [ref])
    return budget_service.months_between(last, ref)


def raise_chance(db: Session, p: LifeProfile, ref: date) -> int:
    ch = 0.12 + (p.merit or 0) * 0.006 + (0.06 if (p.degrees or []) else 0.0) + (0.04 if p.satisfaction >= 60 else 0.0)
    return int(round(max(0.05, min(0.70, ch)) * 100))


def ask_raise(db: Session, user_id: int, month: SimMonth, job_id: int | None = None) -> dict:
    """Pede aumento em UM emprego (`job_id`); sem `job_id`, no CLT de maior salário. Cada emprego tem o seu intervalo de 6 meses."""
    budget_service.require_open(month)
    ensure_jobs(db, user_id, month)
    p = _profile(db, user_id)
    ref = month.ref_month
    if job_id is not None:
        job = next((j for j in active_jobs(db, user_id, ref) if j.id == job_id), None)
        if job is None:
            raise ConflictError("emprego não encontrado entre os seus empregos atuais")
    else:
        job = _top_job(db, user_id, ref, kind="CLT") or _top_job(db, user_id, ref)
        if job is None:
            raise ConflictError("você não tem emprego para pedir aumento")
    ok_ask, why, _wait = raise_status(job, ref)
    if not ok_ask:
        raise ConflictError(why or "não é possível pedir aumento agora")
    chance = raise_chance(db, p, ref)
    p.raise_asked_month = ref
    job.raise_asked_month = ref
    ok = hash01("ask-raise", user_id, job.id, ref.isoformat()) * 100 < chance
    if ok:
        pct = round(5 + 7 * hash01("raise-pct", user_id, job.id, ref.isoformat()), 1)
        raise_salary(db, user_id, job, budget_service.shift_month(ref, 1), pct)
        p.last_raise_month, p.merit = ref, max(0, (p.merit or 0) - 25)
        p.satisfaction = ls._clamp(p.satisfaction + 4)
        text = f"Seu chefe em {job.title} concedeu um aumento de {pct:.1f}% a partir do mês que vem!"
    else:
        pct = 0.0
        add_merit(p, -5)
        ls._hit_mood(p, -2, -3)
        text = f"Seu chefe em {job.title} disse que agora não dá. Mostre mais resultado e tente de novo em 6 meses."
    ls.log(db, user_id, ref, "RAISE_ASK", f"Pedido de aumento ({job.title}): {text}")
    db.flush()
    ls.sync_month(db, user_id, month)
    return {"granted": ok, "pct": pct, "chance": chance, "text": text}


def merit_raise_on_open(db: Session, user_id: int, new_month: SimMonth) -> None:
    """Abertura do mês: quem trabalhou muito e acumulou mérito pode ganhar um aumento espontâneo."""
    p = ls.get_profile(db, user_id, create=False, lock=True)
    if p is None or (p.merit or 0) < MERIT_NEEDED:
        return
    ref = new_month.ref_month
    job = _top_job(db, user_id, ref, kind="CLT")                    # o melhor emprego CLT (um PJ mais bem pago não bloqueia o aumento do CLT)
    if job is None or months_since_raise(db, p, ref) < RAISE_COOLDOWN:
        return
    if hash01("merit-raise", user_id, ref.isoformat()) > 0.45:
        return
    pct = round(4 + 6 * hash01("merit-pct", user_id, ref.isoformat()), 1)
    raise_salary(db, user_id, job, ref, pct)
    p.last_raise_month, p.merit = ref, 15
    p.satisfaction = ls._clamp(p.satisfaction + 5)
    ls.log(db, user_id, ref, "RAISE_MERIT", f"Por todo o seu empenho, a empresa deu um aumento de {pct:.1f}% em {job.title}!")
    db.flush()
