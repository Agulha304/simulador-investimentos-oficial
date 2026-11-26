"""Vida no exterior: intercâmbio, morar fora, voltar, reações dos relacionamentos, custo de vida convertido pelo câmbio e salário de vagas
internacionais. Nenhuma função daqui faz commit.

Regras:
  * Intercâmbio e mudança de país exigem largar os empregos PRESENCIAIS no Brasil (os remotos continuam e pagam em reais).
  * Custos: passagem + visto + instalação (2 aluguéis) no 1º mês e, todo mês, curso + custo de vida do país (convertidos pelo câmbio do mês,
    com IOF e spread). Todos os valores vêm de `country_rules`/`exchange_rules`.
  * Relacionamentos podem esfriar ou terminar (parceiros mais que amigos; família nunca termina).
"""
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.core.money import quantize_money
from backend.models import Education, Exchange, Person, Relationship, SimMonth
from backend.services import budget_service
from backend.services import country_rules as cr
from backend.services import exchange_rules as xr
from backend.services import life_service as ls
from backend.services import world_service as ws
from backend.services.finance_ledger import ConflictError, FinanceError, NotFoundError
from backend.services.life_rules import hash01

D = Decimal
ZERO = D("0.00")
CUT_P = {"ACQUAINTANCE": 0.20, "FRIEND": 0.12, "DATING": 0.35, "COHABITING": 0.45, "MARRIED": 0.22}
STRAIN = {"ACQUAINTANCE": 3, "FRIEND": 8, "DATING": 12, "COHABITING": 15, "MARRIED": 12, "FAMILY": 10}
TEMP_MULT = 0.6                      # intercâmbio (temporário) assusta menos que mudar de vez


# ------------------------------------------------------------------ custos
def upfront_brl(db: Session, user_id: int, code: str, ref: date) -> dict:
    """Passagem, visto/seguro e instalação (2 aluguéis de caução), em reais ao câmbio do mês."""
    c = cr.get(code)
    deposit = ws.convert(db, user_id, code, c.living["rent"] * 2 * float(ws.price_level(db, user_id, code, ref)), ref, friction=True)
    out = {"flight": D(c.flight), "visa": D(c.visa), "deposit": deposit}
    out["total"] = quantize_money(sum(out.values(), ZERO))
    return {k: str(quantize_money(v)) for k, v in out.items()}


def monthly_brl(db: Session, user_id: int, code: str, ref: date, lifestyle: str = "NORMAL") -> Decimal:
    return D(ws.living_brl(db, user_id, code, ref, lifestyle)["total"])


def preview(db: Session, user_id: int, ref: date, program_key: str | None = None, country: str | None = None) -> dict:
    p = xr.PROGRAMS.get(program_key) if program_key else None
    code = p.country if p else country
    c = cr.get(code)
    lifestyle = "NORMAL"
    up = upfront_brl(db, user_id, code, ref)
    pl = float(ws.price_level(db, user_id, code, ref))
    tuition = ws.convert(db, user_id, code, p.tuition * pl, ref, friction=True) if p else ZERO
    stipend = ws.convert(db, user_id, code, p.stipend * pl, ref) if p else ZERO
    living = ws.living_brl(db, user_id, code, ref, lifestyle)
    month_net = D(living["total"]) + tuition - stipend
    months = p.months if p else 0
    return {"country": code, "country_name": c.name, "currency": c.currency, "rate": str(ws.fx(db, user_id, code, ref)), "upfront": up,
            "tuition_month": str(tuition), "stipend_month": str(stipend), "living_month": living, "month_total": str(quantize_money(month_net)),
            "months": months, "total": str(quantize_money(D(up["total"]) + month_net * months)) if months else None}


# ------------------------------------------------------------------ reações dos relacionamentos
def reactions(db: Session, user_id: int, ref: date, *, temporary: bool, where: str) -> list[str]:
    p = ls.get_profile(db, user_id)
    out = []
    rels = list(db.scalars(select(Relationship).where(Relationship.user_id == user_id, Relationship.stage != "ENDED").order_by(Relationship.id)))
    for r in rels:
        person = db.get(Person, r.person_id)
        if person is None or not person.alive:
            continue
        cut = CUT_P.get(r.stage, 0.0) * (TEMP_MULT if temporary else 1.0) * (1.25 if r.affinity < 40 else 0.7 if r.affinity >= 75 else 1.0)
        if cut and hash01("abroad-cut", user_id, r.id, ref.isoformat()) < cut:
            r.stage, r.ended_month = "ENDED", ref
            ls._hit_mood(p, -4, -3)
            ls.log(db, user_id, ref, "ABROAD_BREAKUP", f"{person.name} não aguentou a distância ({where}) e cortou relações com você")
            out.append(f"{person.name} cortou relações")
        else:
            drop = int(STRAIN.get(r.stage, 5) * (TEMP_MULT if temporary else 1.0)) or 1
            r.affinity = max(0, r.affinity - drop)
            r.trust = max(0, r.trust - drop // 2)
            if r.stage != "FAMILY":
                out.append(f"{person.name} ficou chateado(a) (afinidade −{drop})")
            ls.log(db, user_id, ref, "ABROAD_STRAIN", f"{person.name} sentiu a sua ida para o exterior ({where}): a relação esfriou um pouco")
    db.flush()
    return out


def _leave_brazil_jobs(db: Session, user_id: int, ref: date) -> list[str]:
    """Quem vai morar fora larga os empregos presenciais do Brasil; os remotos (e os do país de destino) continuam."""
    from backend.services import career_hub
    ended = []
    for j in career_hub.active_jobs(db, user_id, ref):
        if j.country == "BR" and j.work_mode != "REMOTE":
            career_hub._end_job(db, j, ref, "ABROAD")
            ended.append(f"{j.title} ({j.employer})")
    career_hub.recalc_hours(db, user_id)
    return ended


def _require_can_leave(p) -> None:
    if p.country != "BR":
        raise ConflictError("você já mora fora do Brasil")
    if p.degree_field:
        raise ConflictError("tranque a faculdade antes de ir para o exterior")


# ------------------------------------------------------------------ intercâmbio
def active_exchange(db: Session, user_id: int) -> Exchange | None:
    return db.scalar(select(Exchange).where(Exchange.user_id == user_id, Exchange.status == "ACTIVE"))


def start_exchange(db: Session, user_id: int, month: SimMonth, program_key: str) -> Exchange:
    budget_service.require_open(month)
    prog = xr.PROGRAMS.get(program_key)
    if prog is None:
        raise NotFoundError("programa de intercâmbio não encontrado")
    p = ls.get_profile(db, user_id, lock=True)
    _require_can_leave(p)
    if active_exchange(db, user_id):
        raise ConflictError("você já está em um intercâmbio")
    ref = month.ref_month
    ended = _leave_brazil_jobs(db, user_id, ref)
    pre = preview(db, user_id, ref, program_key=program_key)
    ex = Exchange(user_id=user_id, program_key=prog.key, country=prog.country, field=prog.field, months_total=prog.months, points=prog.points,
                  start_month=ref, upfront_brl=D(pre["upfront"]["total"]), detail={"upfront": pre["upfront"], "name": prog.name})
    db.add(ex)
    p.country, p.abroad_since = prog.country, ref
    p.satisfaction = ls._clamp(p.satisfaction + 4)
    c = cr.get(prog.country)
    ls.log(db, user_id, ref, "EXCHANGE_START", f"Você foi para {c.name} ({prog.name}, {prog.months} meses)" + (f"; largou: {', '.join(ended)}" if ended else ""))
    reactions(db, user_id, ref, temporary=True, where=f"intercâmbio em {c.name}")
    db.flush()
    ls.sync_month(db, user_id, month)
    return ex


def cancel_exchange(db: Session, user_id: int, month: SimMonth) -> Exchange:
    budget_service.require_open(month)
    ex = active_exchange(db, user_id)
    if ex is None:
        raise ConflictError("você não está em intercâmbio")
    p = ls.get_profile(db, user_id, lock=True)
    ex.status, ex.end_month = "CANCELED", month.ref_month
    p.country, p.abroad_since = "BR", None
    ls.log(db, user_id, month.ref_month, "EXCHANGE_CANCEL", "Você interrompeu o intercâmbio e voltou ao Brasil (sem pontos no currículo)")
    db.flush()
    ls.sync_month(db, user_id, month)
    return ex


def _finish_exchange(db: Session, p, ex: Exchange, ref: date) -> None:
    prog = xr.PROGRAMS[ex.program_key]
    ex.status, ex.end_month, ex.progress = "DONE", ref, ex.months_total
    p.country, p.abroad_since = "BR", None
    db.add(Education(user_id=p.user_id, key=f"intercambio:{ex.id}", name=f"Intercâmbio — {prog.name}"[:80], field=ex.field, kind="COURSE", months_total=ex.months_total,
                     progress=ex.months_total, cost_month=ZERO, hours=0, points=ex.points, status="DONE", start_month=ex.start_month, end_month=ref, in_resume=True))
    p.satisfaction = ls._clamp(p.satisfaction + 6)
    ls.log(db, p.user_id, ref, "EXCHANGE_DONE", f"Você concluiu o intercâmbio ({prog.name}) e voltou ao Brasil: +{ex.points} pontos "
           f"{'gerais' if ex.field == 'geral' else 'na área de ' + ex.field} no currículo")


# ------------------------------------------------------------------ morar fora
def move_abroad(db: Session, user_id: int, month: SimMonth, code: str) -> dict:
    budget_service.require_open(month)
    code = code.upper()
    if code == cr.HOME:
        raise FinanceError("escolha um país diferente do Brasil")
    try:
        c = cr.get(code)
    except ValueError as e:
        raise FinanceError(str(e)) from None
    p = ls.get_profile(db, user_id, lock=True)
    _require_can_leave(p)
    if active_exchange(db, user_id):
        raise ConflictError("termine o intercâmbio antes de mudar de país")
    ref = month.ref_month
    ended = _leave_brazil_jobs(db, user_id, ref)
    pre = upfront_brl(db, user_id, code, ref)
    p.country, p.abroad_since = code, ref
    ls.log(db, user_id, ref, "MOVE_ABROAD", f"Você se mudou para {c.name}" + (f"; largou os empregos presenciais: {', '.join(ended)}" if ended else ""))
    out = reactions(db, user_id, ref, temporary=False, where=f"mudança para {c.name}")
    db.flush()
    ls.sync_month(db, user_id, month)
    return {"country": code, "upfront": pre, "ended_jobs": ended, "reactions": out}


def return_home(db: Session, user_id: int, month: SimMonth) -> dict:
    budget_service.require_open(month)
    p = ls.get_profile(db, user_id, lock=True)
    if p.country == "BR":
        raise ConflictError("você já mora no Brasil")
    if active_exchange(db, user_id):
        raise ConflictError("você está em intercâmbio: interrompa-o ou espere terminar")
    from backend.services import career_hub
    ref = month.ref_month
    old = p.country
    for j in career_hub.active_jobs(db, user_id, ref):
        if j.country != "BR" and j.work_mode != "REMOTE":
            career_hub._end_job(db, j, ref, "ABROAD")
    p.country, p.abroad_since = "BR", None
    back = quantize_money(D(cr.get(old).flight) * D(str(xr.RESIDENT_FLIGHT_BACK)))
    p.one_offs = {**(p.one_offs or {}), f"life:return:{ref:%Y-%m}": {"name": f"Passagem de volta de {cr.get(old).name}", "amount": str(back), "cat": "Moradia", "month": ref.isoformat()}}
    ls.log(db, user_id, ref, "RETURN_HOME", f"Você voltou para o Brasil (saiu de {cr.get(old).name})")
    db.flush()
    ls.sync_month(db, user_id, month)
    return {"country": "BR", "flight_brl": str(back)}


# ------------------------------------------------------------------ orçamento e fechamento
def desired_items(db: Session, user_id: int, ref: date, want) -> None:
    p = ls.get_profile(db, user_id, create=False)
    if p is None:
        return
    for k, v in (p.one_offs or {}).items():                       # despesas pontuais (ex.: passagem de volta) do mês
        if v.get("month") == ref.isoformat():
            want(k, v["name"], ls.FlowKind.EXPENSE, v.get("cat", "Moradia"), D(v["amount"]))
    if p.country == "BR":
        return
    ex = active_exchange(db, user_id)
    code = p.country
    c = cr.get(code)
    living = ws.living_brl(db, user_id, code, ref, "NORMAL")
    want(f"life:abroad:{code}", f"Vida em {c.name} (aluguel, comida, contas e transporte)", ls.FlowKind.EXPENSE, "Moradia", D(living["total"]))
    if ex is not None:
        prog = xr.PROGRAMS[ex.program_key]
        if prog.tuition:
            want(f"life:exchange:{ex.id}:tuition", f"Curso: {prog.name}", ls.FlowKind.EXPENSE, "Educação", ws.convert(db, user_id, code, prog.tuition * float(ws.price_level(db, user_id, code, ref)), ref, friction=True))
        if prog.stipend:
            want(f"life:exchange:{ex.id}:stipend", f"Bolsa/estágio: {prog.name}", ls.FlowKind.INCOME, "Renda extra", ws.convert(db, user_id, code, prog.stipend * float(ws.price_level(db, user_id, code, ref)), ref))
        if ref == ex.start_month:
            want(f"life:exchange:{ex.id}:start", "Intercâmbio: passagem, visto e instalação", ls.FlowKind.EXPENSE, "Educação", ex.upfront_brl)
    elif p.abroad_since == ref:
        want(f"life:abroad:{code}:start", f"Mudança para {c.name}: passagem, visto e instalação", ls.FlowKind.EXPENSE, "Moradia", D(upfront_brl(db, user_id, code, ref)["total"]))


def process_month(db: Session, p, ref: date) -> None:
    ex = active_exchange(db, p.user_id)
    if ex is None:
        return
    ex.progress += 1
    if ex.progress >= ex.months_total:
        _finish_exchange(db, p, ex, ref)


def view(db: Session, user_id: int, ref: date) -> dict:
    p = ls.get_profile(db, user_id)
    ex = active_exchange(db, user_id)
    c = cr.get(p.country or "BR")
    return {
        "country": c.code, "country_name": c.name, "flag": c.flag, "currency": c.currency, "since": p.abroad_since,
        "rate": str(ws.fx(db, user_id, c.code, ref)),
        "living_month": ws.living_brl(db, user_id, c.code, ref) if c.code != "BR" else None,
        "exchange": ({"id": ex.id, "program": ex.program_key, "name": xr.PROGRAMS[ex.program_key].name, "country": ex.country, "progress": ex.progress,
                      "months": ex.months_total, "points": ex.points, "field": ex.field} if ex else None),
        "programs": [{"key": q.key, "country": q.country, "country_name": cr.get(q.country).name, "flag": cr.get(q.country).flag, "name": q.name, "kind": q.kind,
                      "months": q.months, "field": q.field, "points": q.points, "note": q.note, "language": cr.get(q.country).language,
                      "cost": preview(db, user_id, ref, program_key=q.key)} for q in xr.PROGRAMS.values()],
        "countries": [{"code": x.code, "name": x.name, "flag": x.flag, "currency": x.currency, "language": x.language,
                       "cost": preview(db, user_id, ref, country=x.code)} for x in cr.COUNTRIES.values() if x.code != "BR"],
        "done": [{"id": e.id, "name": e.detail.get("name"), "country": e.country, "months": e.months_total, "points": e.points, "field": e.field, "status": e.status}
                 for e in db.scalars(select(Exchange).where(Exchange.user_id == user_id, Exchange.status != "ACTIVE").order_by(Exchange.id.desc()))],
    }
