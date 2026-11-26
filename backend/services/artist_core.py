"""Utilitários compartilhados da carreira de artista: perfil, itens (JSON), habilidade/fama, gastos e receitas no orçamento."""
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.core.money import quantize_money
from backend.models import ArtistItem, ArtistProfile, FlowKind, Portfolio, SimMonth
from backend.services import artist_rules as AR
from backend.services import life_service as ls
from backend.services.budget_service import shift_month
from backend.services.finance_ledger import FinanceError, NotFoundError
from backend.services.goods_rules import hash01

D = Decimal
ZERO = D("0.00")


# ------------------------------------------------------------------ acesso
def _seed(db: Session, user_id: int) -> int:
    from backend.services import world_service
    return world_service._seed(db, user_id)


def profile(db: Session, user_id: int, lock: bool = False) -> ArtistProfile:
    q = select(ArtistProfile).where(ArtistProfile.user_id == user_id)
    p = db.scalar(q.with_for_update() if lock else q)
    if p is None:
        p = ArtistProfile(user_id=user_id, skills={k: 10.0 for k in AR.DISCIPLINES}, fame={k: 0.0 for k in AR.DISCIPLINES}, data={})
        db.add(p)
        db.flush()
    return p


def items(db: Session, user_id: int, kind: str, status: str | None = None) -> list[ArtistItem]:
    q = select(ArtistItem).where(ArtistItem.user_id == user_id, ArtistItem.kind == kind)
    if status:
        q = q.where(ArtistItem.status == status)
    return list(db.scalars(q.order_by(ArtistItem.id)))


def _add(db: Session, user_id: int, kind: str, name: str, ref: date, status: str = "ACTIVE", **data) -> ArtistItem:
    it = ArtistItem(user_id=user_id, kind=kind, status=status, name=name[:120], created_month=ref, data=data)
    db.add(it)
    db.flush()
    return it


def _upd(it: ArtistItem, **kv) -> None:
    it.data = {**(it.data or {}), **kv}


def _get(db: Session, user_id: int, item_id: int, kind: str) -> ArtistItem:
    it = db.get(ArtistItem, item_id)
    if it is None or it.user_id != user_id or it.kind != kind:
        raise NotFoundError("item não encontrado")
    return it


def skill(p: ArtistProfile, d: str) -> float:
    return float((p.skills or {}).get(d, 10.0))


def fame(p: ArtistProfile, d: str) -> float:
    return float((p.fame or {}).get(d, 0.0))


def _bump(p: ArtistProfile, d: str, skill_d: float = 0.0, fame_d: float = 0.0) -> None:
    p.skills = {**(p.skills or {}), d: round(AR.clamp(skill(p, d) + skill_d), 2)}
    p.fame = {**(p.fame or {}), d: round(AR.clamp(fame(p, d) + fame_d), 2)}


def _life(db: Session, user_id: int):
    return ls.get_profile(db, user_id, lock=True)


def _pay_cash(db: Session, user_id: int, month: SimMonth, amount: float | Decimal, name: str, cat: str = "Lazer") -> None:
    """Gasto à vista (entra no orçamento do mês); exige saldo."""
    amount = quantize_money(D(str(amount)))
    if amount <= 0:
        return
    bal = db.scalar(select(Portfolio.cash_balance).where(Portfolio.user_id == user_id)) or ZERO       # dinheiro pessoal
    if bal < amount:
        raise FinanceError(f"saldo insuficiente: {name} custa {amount} e você tem {bal}")
    lp = _life(db, user_id)
    ls.add_one_off(lp, f"life:artist:cost:{month.ref_month:%Y-%m}:{len(lp.one_offs or {})}", name, amount, cat, month.ref_month, "EXPENSE")


def _income(db: Session, user_id: int, ref: date, name: str, amount: float | Decimal, months_ahead: int = 1) -> None:
    amount = quantize_money(D(str(amount)))
    if amount > 0:
        _add(db, user_id, "PAYOUT", name, ref, status="PENDING", month=shift_month(ref, months_ahead).isoformat(), amount=str(amount))


def _resync(db: Session, user_id: int, month: SimMonth) -> None:
    from backend.services import career_hub
    career_hub.recalc_hours(db, user_id)
    ls.sync_month(db, user_id, month)


