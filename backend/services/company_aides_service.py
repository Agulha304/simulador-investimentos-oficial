"""Marketeiro e gerente opcionais: contratar/trocar de nível, dispensar e briefing. Regras em `company_aides`; efeitos mensais em
`company_service` (fechamento). Nenhuma função aqui faz commit."""
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.models import Company, CompanyAide, CompanyEventType, SimMonth
from backend.services import company_aides as aides
from backend.services import company_service as cs
from backend.services.budget_service import require_open
from backend.services.finance_ledger import ConflictError, FinanceError


def _row(db: Session, c: Company, kind: str) -> CompanyAide | None:
    return db.scalar(select(CompanyAide).where(CompanyAide.company_id == c.id, CompanyAide.kind == kind))


def _kind(kind: str) -> str:
    kind = kind.upper()
    if kind not in aides.KINDS:
        raise FinanceError("tipo inexistente (MARKETER ou MANAGER)")
    return kind


def hire(db: Session, user_id: int, month: SimMonth, company_id: int, kind: str, level: str) -> CompanyAide:
    """Contrata o profissional no nível pedido ou TROCA o nível se já houver um ativo. Sem custo imediato: taxa mensal no fechamento."""
    require_open(month)
    kind = _kind(kind)
    c = cs.get_company(db, user_id, company_id, lock=True)
    cs._active(c)
    try:
        aides.check_level(level)
    except ValueError as e:
        raise FinanceError(str(e)) from None
    fee, ref, label = aides.monthly_fee(kind, level, c.size), month.ref_month, aides.KIND_LABEL[kind]
    row = _row(db, c, kind)
    if row is None:
        row = CompanyAide(company_id=c.id, kind=kind, level=level, status="ACTIVE", hired_month=ref, settings=dict(aides.BRIEFING_DEFAULT[kind]))
        db.add(row)
        text = f"{label} contratado ({aides.LEVEL_LABEL[level]}): taxa mensal de {fee}"
    elif row.status == "ACTIVE":
        if row.level == level:
            return row
        text = f"{label} trocado de {aides.LEVEL_LABEL[row.level]} para {aides.LEVEL_LABEL[level]}: taxa mensal de {fee}"
        row.level = level
    else:
        row.status, row.level, row.hired_month, row.ended_month = "ACTIVE", level, ref, None
        row.settings = dict(aides.BRIEFING_DEFAULT[kind])
        text = f"{label} contratado novamente ({aides.LEVEL_LABEL[level]}): taxa mensal de {fee}"
    db.flush()
    cs._event(db, c, ref, CompanyEventType.HIRE, text, fee)
    return row


def dismiss(db: Session, user_id: int, month: SimMonth, company_id: int, kind: str) -> CompanyAide:
    require_open(month)
    kind = _kind(kind)
    c = cs.get_company(db, user_id, company_id, lock=True)
    cs._active(c)
    row = _row(db, c, kind)
    if row is None or row.status != "ACTIVE":
        raise ConflictError(f"a empresa não tem {aides.KIND_LABEL[kind].lower()} ativo")
    row.status, row.ended_month = "ENDED", month.ref_month
    db.flush()
    cs._event(db, c, month.ref_month, CompanyEventType.HIRE, f"{aides.KIND_LABEL[kind]} dispensado (sem multa)")
    return row


def update_briefing(db: Session, user_id: int, month: SimMonth, company_id: int, kind: str, raw: dict) -> CompanyAide:
    require_open(month)
    kind = _kind(kind)
    c = cs.get_company(db, user_id, company_id, lock=True)
    cs._active(c)
    row = _row(db, c, kind)
    if row is None or row.status != "ACTIVE":
        raise ConflictError(f"Contrate {'um marketeiro' if kind == 'MARKETER' else 'um gerente'} antes de definir o briefing")
    try:
        row.settings = aides.build_briefing(kind, raw)
    except ValueError as e:
        raise FinanceError(str(e)) from None
    db.flush()
    cs._event(db, c, month.ref_month, CompanyEventType.SETTINGS,
              f"Briefing do marketeiro: orçamento mensal {row.settings['monthly_budget']}" if kind == "MARKETER"
              else f"Briefing do gerente: rigidez {row.settings['rigor']}/100"
                   + (" (alta: risco de pedidos de demissão)" if row.settings["rigor"] >= 70 else ""))
    return row


def view(db: Session, c: Company) -> dict:
    out = {}
    for kind in aides.KINDS:
        row = _row(db, c, kind)
        if row is None or row.status != "ACTIVE":
            out[kind.lower()] = None
            continue
        d = {"kind": kind, "level": row.level, "label": aides.LEVEL_LABEL[row.level], "fee": str(aides.monthly_fee(kind, row.level, c.size)),
             "settings": row.settings, "hired_month": row.hired_month}
        if kind == "MANAGER":
            rigor = int(row.settings.get("rigor", 40))
            d["productivity_pct"] = round((aides.productivity_boost(row.level, rigor) - 1) * 100, 1)
            d["quit_chance_pct"] = round(aides.quit_probability(row.level, rigor) * 100, 2)
        out[kind.lower()] = d
    return out


def options(c: Company) -> dict:
    return {k.lower(): [{"level": lv, "label": aides.LEVEL_LABEL[lv], "fee": str(aides.monthly_fee(k, lv, c.size))} for lv in aides.LEVELS]
            for k in aides.KINDS}
