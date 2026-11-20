"""Ranking de usuários. Usa a foto mais recente do patrimônio de cada carteira.

Patrimônio do ranking = patrimônio − aportes virtuais EXTRAS (wealth_brl): depositar mais dinheiro
fictício não sobe no ranking. Rentabilidade = ganho / ponto de partida (saldo inicial ou, nos
períodos de 7/30 dias, o último registro antes do início da janela)."""
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.models import Game, Portfolio, PortfolioSnapshot, User

D = Decimal
PERIOD_DAYS = {"all": None, "30d": 30, "7d": 7}
BOARDS = ("wealth", "return")
NOTE = ("Aportes virtuais extras não contam: o ranking mede o saldo inicial mais os seus resultados. "
        "Atualizado a cada hora.")


def default_nickname(name: str) -> str:
    parts = name.strip().split()
    if not parts:
        return "Investidor"
    first = parts[0][:14]
    return f"{first} {parts[-1][0].upper()}." if len(parts) > 1 else first


def nickname_of(user: User) -> str:
    return user.ranking_nickname or default_nickname(user.name)


@dataclass
class Row:
    user: User
    wealth: Decimal
    gain: Decimal
    ret: Decimal


def _latest(db: Session) -> dict[int, PortfolioSnapshot]:
    q = (select(PortfolioSnapshot).distinct(PortfolioSnapshot.portfolio_id)
         .order_by(PortfolioSnapshot.portfolio_id, PortfolioSnapshot.taken_at.desc()))
    return {s.portfolio_id: s for s in db.scalars(q)}


def _baseline(db: Session, cutoff: datetime) -> dict[int, Decimal]:
    """Patrimônio de partida da janela: último registro antes do corte, ou o primeiro depois dele."""
    before = (select(PortfolioSnapshot).distinct(PortfolioSnapshot.portfolio_id)
              .where(PortfolioSnapshot.taken_at < cutoff)
              .order_by(PortfolioSnapshot.portfolio_id, PortfolioSnapshot.taken_at.desc()))
    after = (select(PortfolioSnapshot).distinct(PortfolioSnapshot.portfolio_id)
             .where(PortfolioSnapshot.taken_at >= cutoff)
             .order_by(PortfolioSnapshot.portfolio_id, PortfolioSnapshot.taken_at))
    base = {s.portfolio_id: s.wealth_brl for s in db.scalars(after)}
    base.update({s.portfolio_id: s.wealth_brl for s in db.scalars(before)})     # "antes" tem prioridade
    return base


def compute(db: Session, board: str, period: str, me_user_id: int, limit: int = 50, now: datetime | None = None) -> dict:
    now = now or datetime.now(UTC)
    latest = _latest(db)
    days = PERIOD_DAYS[period]
    baseline = _baseline(db, now - timedelta(days=days)) if days else {}
    users = {p.id: u for p, u in db.execute(select(Portfolio, User).join(User, User.id == Portfolio.user_id)).all()}
    # mundos de partida contam para a CONTA dona: vida completa no ranking de patrimônio, treino no de rentabilidade
    worlds = {g.world_user_id: g for g in db.scalars(select(Game).where(Game.status == "ACTIVE"))}
    owners = {u.id: u for u in db.scalars(select(User).where(User.id.in_({g.account_id for g in worlds.values()})))} if worlds else {}
    has_games = {g.account_id for g in worlds.values()}
    want = "LIFE" if board == "wealth" else "TRAINING"

    rows: list[Row] = []
    for pid, snap in latest.items():
        user = users.get(pid)
        if user is None:
            continue
        if user.is_game_world:
            g = worlds.get(user.id)
            if g is None or g.kind != want:
                continue
            owner = owners[g.account_id]
        else:
            if user.id in has_games:          # quem joga partidas é ranqueado por elas, não pela carteira antiga
                continue
            owner = user
        start = baseline.get(pid, snap.initial_brl) if days else snap.initial_brl
        gain = snap.wealth_brl - start
        rows.append(Row(owner, snap.wealth_brl, gain, (gain / start * 100).quantize(D("0.01")) if start else D("0.00")))
    best: dict[int, Row] = {}                  # um resultado por conta: o melhor
    for r in rows:
        cur = best.get(r.user.id)
        if cur is None or (r.wealth if board == "wealth" else r.ret) > (cur.wealth if board == "wealth" else cur.ret):
            best[r.user.id] = r
    rows = list(best.values())

    visible = [r for r in rows if r.user.show_in_ranking]
    key = (lambda r: (-r.wealth, r.user.id)) if board == "wealth" else (lambda r: (-r.ret, -r.wealth, r.user.id))
    visible.sort(key=key)

    def entry(rank: int, r: Row) -> dict:
        return {"rank": rank, "nickname": nickname_of(r.user), "wealth_brl": r.wealth, "gain_brl": r.gain.quantize(D("0.01")),
                "return_pct": r.ret, "is_me": r.user.id == me_user_id}

    entries = [entry(i, r) for i, r in enumerate(visible[:limit], start=1)]
    me = next((entry(i, r) for i, r in enumerate(visible, start=1) if r.user.id == me_user_id), None)
    me_hidden = any(r.user.id == me_user_id for r in rows) and me is None
    return {"board": board, "period": period, "participants": len(visible), "entries": entries,
            "me": me, "me_hidden": me_hidden, "note": NOTE}
