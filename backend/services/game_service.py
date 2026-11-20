"""Partidas: criação de mundos isolados, treino com mercado histórico e listagem para o menu inicial."""
import secrets
import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.config import get_settings
from backend.core.clock import use_clock
from backend.core.money import quantize_money
from backend.models import Game, Portfolio, TransactionSource, User
from backend.services import historical_market, ledger_service
from backend.services.budget_service import shift_month
from backend.services.finance_ledger import ConflictError, FinanceError, NotFoundError

KINDS = ("LIFE", "TRAINING")
MAX_GAMES = 30


def first_of_month(d: date) -> date:
    return date(d.year, d.month, 1)


def _today() -> date:
    from backend.core.dates import today_br
    return today_br()


def get_game(db: Session, account_id: int, game_id: int) -> Game:
    g = db.get(Game, game_id)
    if g is None or g.account_id != account_id:
        raise NotFoundError("partida não encontrada")
    return g


def create_game(db: Session, account: User, *, kind: str, name: str, start_date: date | None = None) -> Game:
    if kind not in KINDS:
        raise FinanceError("tipo de partida inválido (LIFE ou TRAINING)")
    name = (name or "").strip()
    if not name:
        raise FinanceError("dê um nome à partida")
    if len(db.scalars(select(Game.id).where(Game.account_id == account.id, Game.status == "ACTIVE")).all()) >= MAX_GAMES:
        raise ConflictError("limite de partidas ativas atingido: arquive alguma antes")
    config: dict = {}
    if kind == "TRAINING":
        start = first_of_month(start_date or shift_month(first_of_month(_today()), -24))
        if start < historical_market.MIN_DATE or start > first_of_month(_today()):
            raise FinanceError(f"a data de início deve estar entre {historical_market.MIN_DATE:%m/%Y} e o mês atual")
        config = {"market_date": start.isoformat(), "start_date": start.isoformat()}
    world = User(email=f"mundo-{uuid.uuid4().hex}@partidas.invalid", name=account.name, password_hash="!" + secrets.token_hex(16),
                 show_in_ranking=account.show_in_ranking, ranking_nickname=account.ranking_nickname, is_game_world=True)
    db.add(world)
    db.flush()
    portfolio = Portfolio(user_id=world.id)
    db.add(portfolio)
    db.flush()
    ledger_service.deposit(db, portfolio.id, get_settings().initial_balance, source=TransactionSource.SYSTEM,
                           idempotency_key=f"initial-deposit:portfolio:{portfolio.id}", note="Saldo virtual inicial")
    game = Game(account_id=account.id, world_user_id=world.id, kind=kind, name=name[:60], config=config)
    db.add(game)
    db.flush()
    _snapshot(db, game)
    return game


def clock_of(game: Game, db: Session | None = None):
    """Relógio da partida: treino = data histórica; vida completa com economia dinâmica = mês simulado."""
    if game.kind == "TRAINING":
        return historical_market.clock_for(date.fromisoformat(game.config["market_date"]))
    if db is None:
        return None
    from backend.models import GameProfile, SimMonth
    prof = db.scalar(select(GameProfile).where(GameProfile.user_id == game.world_user_id))
    if prof is None or prof.economy_mode != "DYNAMIC":
        return None
    month = db.scalar(select(SimMonth.ref_month).where(SimMonth.user_id == game.world_user_id, SimMonth.status == "OPEN"))
    from backend.models import EconomyState
    st = db.scalar(select(EconomyState).where(EconomyState.user_id == game.world_user_id, EconomyState.ref_month <= month)
                   .order_by(EconomyState.ref_month.desc()).limit(1)) if month else None
    if st is None:
        return None
    from backend.services import sim_market
    fx = Decimal(str(((st.engine or {}).get("macro") or {}).get("fx", 5.2)))
    clock, _ = sim_market.clock_for(game.world_user_id, month, fx.quantize(Decimal("0.0001")))
    return clock


def _snapshot(db: Session, game: Game) -> None:
    """Foto do patrimônio na data da partida (a série do desempenho usa o tempo da partida)."""
    from backend.services import performance_service, portfolio_service
    pid = db.scalar(select(Portfolio.id).where(Portfolio.user_id == game.world_user_id))
    clock = clock_of(game, db)
    now = datetime.combine(clock.today, datetime.min.time(), tzinfo=UTC) if clock else None
    try:
        with use_clock(clock):
            performance_service.take_snapshot(db, portfolio_service.load_portfolio(db, pid), now)
    except Exception:           # snapshot é auxiliar: nunca derruba a operação principal
        pass


def touch(game: Game) -> None:
    game.last_played_at = datetime.now(UTC)


def rename(db: Session, game: Game, name: str) -> Game:
    if not name.strip():
        raise FinanceError("dê um nome à partida")
    game.name = name.strip()[:60]
    return game


def archive(game: Game) -> Game:
    game.status = "ARCHIVED"
    return game


# ------------------------------------------------------------------ treino
def _training(game: Game) -> date:
    if game.kind != "TRAINING":
        raise ConflictError("esta ação só existe no modo treino")
    return date.fromisoformat(game.config["market_date"])


def set_market_date(db: Session, game: Game, target: date) -> Game:
    """Viagem no tempo: qualquer mês entre 2015 e o mês atual. O que você comprou continua com você e passa a valer o preço da nova data."""
    _training(game)
    t = first_of_month(target)
    if t < historical_market.MIN_DATE or t > first_of_month(_today()):
        raise FinanceError(f"escolha uma data entre {historical_market.MIN_DATE:%m/%Y} e o mês atual")
    game.config = {**game.config, "market_date": t.isoformat()}
    _snapshot(db, game)
    return game


def advance_months(db: Session, game: Game, months: int) -> Game:
    cur = _training(game)
    if not 1 <= months <= 24:
        raise FinanceError("avance de 1 a 24 meses por vez")
    target = shift_month(cur, months)
    if target > first_of_month(_today()):
        raise ConflictError("você chegou ao presente: não há dados reais depois de hoje (o modo vida completa simula o futuro)")
    return set_market_date(db, game, target)


def add_fake_money(db: Session, game: Game, amount) -> None:
    _training(game)
    amount = quantize_money(amount)
    if not 0 < amount <= 10_000_000:
        raise FinanceError("informe um valor entre 0,01 e 10.000.000")
    pid = db.scalar(select(Portfolio.id).where(Portfolio.user_id == game.world_user_id))
    ledger_service.deposit(db, pid, amount, source=TransactionSource.USER, note="Dinheiro fictício de treino")
    _snapshot(db, game)
