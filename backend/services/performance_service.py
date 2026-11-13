"""Desempenho do usuário: evolução do patrimônio, comparação com o CDI, estatísticas das
operações, composição da carteira, conquistas e dicas.

Evolução: um snapshot por hora (worker + sob demanda). Estatísticas de operações vêm do livro-razão
(Transaction), então existem desde o primeiro dia mesmo com poucos snapshots.
"""
import logging
from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session, selectinload

from backend.core.dates import TZ, today_br
from backend.core.money import quantize_money
from backend.models import (
    AssetClass, IndexName, InvestmentStatus, LessonProgress, Portfolio, PortfolioSnapshot, Transaction,
    TransactionSource, TransactionType,
)
from backend.services import fixed_income_service, index_data, portfolio_service

log = logging.getLogger(__name__)
D = Decimal
RANGES: dict[str, int | None] = {"1d": 1, "7d": 7, "30d": 30, "90d": 90, "all": None}
CLOSING_TYPES = (TransactionType.SELL, TransactionType.FIXED_INCOME_REDEEM, TransactionType.FIXED_INCOME_MATURITY)
INCOME_TYPES = (TransactionType.DIVIDEND, TransactionType.FIXED_INCOME_COUPON)


def _q2(x) -> Decimal:
    return D(x).quantize(D("0.01"))


def _pct(part: Decimal, whole: Decimal) -> Decimal:
    return _q2(part / whole * 100) if whole else D("0.00")


# ------------------------------------------------------------------ snapshots

def initial_deposit(db: Session, portfolio_id: int) -> Decimal:
    v = db.scalar(select(func.coalesce(func.sum(Transaction.cash_amount_brl), 0)).where(
        Transaction.portfolio_id == portfolio_id, Transaction.type == TransactionType.DEPOSIT,
        Transaction.source == TransactionSource.SYSTEM))
    return quantize_money(v)


def take_snapshot(db: Session, portfolio: Portfolio, now: datetime | None = None) -> PortfolioSnapshot | None:
    """Grava (ou atualiza) a foto da hora corrente. Pula se faltar cotação de alguma posição,
    para não registrar uma queda falsa causada por preço indisponível."""
    now = now or datetime.now(UTC)
    s = portfolio_service.build_summary(db, portfolio)
    if any(v.current_price_brl is None for v in s.holdings):
        log.warning("snapshot adiado (carteira %s): cotação indisponível", portfolio.id)
        return None
    initial = initial_deposit(db, portfolio.id)
    extra = s.total_deposits_brl - initial
    bucket = now.replace(minute=0, second=0, microsecond=0)
    values = dict(
        portfolio_id=portfolio.id, bucket=bucket, taken_at=now, cash_brl=s.cash_balance, assets_brl=s.market_value_brl,
        fixed_income_brl=s.fixed_income_value_brl, equity_brl=s.total_equity_brl, net_deposits_brl=s.total_deposits_brl,
        initial_brl=initial, wealth_brl=quantize_money(s.total_equity_brl - extra),
    )
    stmt = pg_insert(PortfolioSnapshot).values(**values)
    stmt = stmt.on_conflict_do_update(constraint="uq_snapshot_portfolio_bucket",
                                      set_={k: stmt.excluded[k] for k in values if k not in ("portfolio_id", "bucket")})
    db.execute(stmt)
    db.commit()
    return db.scalar(select(PortfolioSnapshot).where(PortfolioSnapshot.portfolio_id == portfolio.id,
                                                     PortfolioSnapshot.bucket == bucket))


def ensure_recent_snapshot(db: Session, portfolio: Portfolio, max_age: timedelta = timedelta(minutes=10)) -> None:
    last = db.scalar(select(func.max(PortfolioSnapshot.taken_at)).where(PortfolioSnapshot.portfolio_id == portfolio.id))
    if last is None or datetime.now(UTC) - last > max_age:
        take_snapshot(db, portfolio)


def snapshot_all(db: Session) -> int:
    n = 0
    for pid in db.scalars(select(Portfolio.id)).all():
        try:
            if take_snapshot(db, portfolio_service.load_portfolio(db, pid)):
                n += 1
        except Exception:
            db.rollback()
            log.exception("falha ao registrar snapshot da carteira %s", pid)
    return n


# ------------------------------------------------------------------ série

def _local_date(dt: datetime) -> date:
    return dt.astimezone(TZ).date()


def load_snapshots(db: Session, portfolio_id: int, range_key: str, now: datetime) -> list[PortfolioSnapshot]:
    q = select(PortfolioSnapshot).where(PortfolioSnapshot.portfolio_id == portfolio_id).order_by(PortfolioSnapshot.taken_at)
    days = RANGES[range_key]
    if days is not None:
        q = q.where(PortfolioSnapshot.taken_at >= now - timedelta(days=days))
    return list(db.scalars(q))


def downsample(rows: list[PortfolioSnapshot], hourly: bool) -> list[PortfolioSnapshot]:
    if hourly:
        return rows
    last_of_day: dict[date, PortfolioSnapshot] = {}
    for r in rows:
        last_of_day[_local_date(r.taken_at)] = r
    return list(last_of_day.values())


def build_series(rows: list[PortfolioSnapshot], idx: index_data.IndexData) -> list[dict]:
    if not rows:
        return []
    w0, d0 = rows[0].wealth_brl, _local_date(rows[0].taken_at)
    cdi_cache: dict[date, Decimal] = {}
    peak = rows[0].wealth_brl
    out = []
    for r in rows:
        d = _local_date(r.taken_at)
        if d not in cdi_cache:
            cdi_cache[d] = _q2((idx.daily_factor(IndexName.CDI, d0, d) - 1) * 100)
        peak = max(peak, r.wealth_brl)
        out.append({
            "t": r.taken_at, "equity": r.equity_brl, "wealth": r.wealth_brl, "cash": r.cash_brl, "assets": r.assets_brl,
            "fixed_income": r.fixed_income_brl, "net_deposits": r.net_deposits_brl,
            "return_pct": _pct(r.wealth_brl - w0, w0), "cdi_pct": cdi_cache[d],
            "drawdown_pct": _pct(r.wealth_brl - peak, peak),
        })
    return out


def series_stats(series: list[dict]) -> dict:
    if len(series) < 2:
        return {"period_return_pct": None, "cdi_pct": None, "vs_cdi_pp": None, "max_drawdown_pct": None,
                "best_day_pct": None, "worst_day_pct": None}
    last = series[-1]
    daily: dict[date, Decimal] = {}
    for p in series:
        daily[_local_date(p["t"])] = p["wealth"]
    days = list(daily.values())
    moves = [_pct(b - a, a) for a, b in zip(days, days[1:])]
    return {
        "period_return_pct": last["return_pct"], "cdi_pct": last["cdi_pct"], "vs_cdi_pp": _q2(last["return_pct"] - last["cdi_pct"]),
        "max_drawdown_pct": min(p["drawdown_pct"] for p in series),
        "best_day_pct": max(moves) if moves else None, "worst_day_pct": min(moves) if moves else None,
    }


# ------------------------------------------------------------------ operações

def load_transactions(db: Session, portfolio_id: int) -> list[Transaction]:
    return list(db.scalars(select(Transaction).where(Transaction.portfolio_id == portfolio_id)
                           .options(selectinload(Transaction.asset)).order_by(Transaction.created_at, Transaction.id)))


def _label(t: Transaction) -> str:
    return t.asset.symbol if t.asset else (t.note or "Renda fixa").split(":")[-1].strip()


def trade_stats(txs: list[Transaction]) -> dict:
    closings = [t for t in txs if t.type in CLOSING_TYPES and t.realized_pnl_brl is not None]
    wins = [t for t in closings if t.realized_pnl_brl > 0]
    losses = [t for t in closings if t.realized_pnl_brl < 0]
    sum_w = sum((t.realized_pnl_brl for t in wins), D(0))
    sum_l = sum((t.realized_pnl_brl for t in losses), D(0))
    decided = len(wins) + len(losses)
    avg_win = _q2(sum_w / len(wins)) if wins else None
    avg_loss = _q2(sum_l / len(losses)) if losses else None
    best = max(closings, key=lambda t: t.realized_pnl_brl, default=None)
    worst = min(closings, key=lambda t: t.realized_pnl_brl, default=None)
    return {
        "buys": sum(1 for t in txs if t.type == TransactionType.BUY),
        "sells": sum(1 for t in txs if t.type == TransactionType.SELL),
        "fixed_income_applications": sum(1 for t in txs if t.type == TransactionType.FIXED_INCOME_APPLY),
        "closed_trades": len(closings), "wins": len(wins), "losses": len(losses),
        "win_rate_pct": _pct(D(len(wins)), D(decided)) if decided else None,
        "avg_win_brl": avg_win, "avg_loss_brl": avg_loss,
        "payoff_ratio": _q2(avg_win / abs(avg_loss)) if avg_win and avg_loss else None,
        "profit_factor": _q2(sum_w / abs(sum_l)) if sum_l else None,
        "total_realized_brl": quantize_money(sum_w + sum_l),
        "income_total_brl": quantize_money(sum((t.cash_amount_brl for t in txs if t.type in INCOME_TYPES), D(0))),
        "best_trade_brl": best.realized_pnl_brl if best and best.realized_pnl_brl > 0 else None,
        "best_trade_label": _label(best) if best and best.realized_pnl_brl > 0 else None,
        "worst_trade_brl": worst.realized_pnl_brl if worst and worst.realized_pnl_brl < 0 else None,
        "worst_trade_label": _label(worst) if worst and worst.realized_pnl_brl < 0 else None,
    }


def monthly_and_cumulative(txs: list[Transaction]) -> tuple[list[dict], list[dict]]:
    months: dict[str, dict] = defaultdict(lambda: {"realized": D(0), "income": D(0), "trades": 0})
    daily: dict[date, Decimal] = defaultdict(lambda: D(0))
    for t in txs:
        d = _local_date(t.created_at)
        key = f"{d:%Y-%m}"
        if t.type in CLOSING_TYPES and t.realized_pnl_brl is not None:
            months[key]["realized"] += t.realized_pnl_brl
            daily[d] += t.realized_pnl_brl
        if t.type in INCOME_TYPES:
            months[key]["income"] += t.cash_amount_brl
            daily[d] += t.cash_amount_brl
        if t.type in (TransactionType.BUY, TransactionType.SELL, TransactionType.FIXED_INCOME_APPLY,
                      TransactionType.FIXED_INCOME_REDEEM):
            months[key]["trades"] += 1
    monthly = [{"month": k, "realized": quantize_money(v["realized"]), "income": quantize_money(v["income"]),
                "trades": v["trades"]} for k, v in sorted(months.items())]
    cum, total = [], D(0)
    for d in sorted(daily):
        total += daily[d]
        cum.append({"date": d, "cumulative": quantize_money(total)})
    return monthly, cum


# ------------------------------------------------------------------ composição

def allocation_and_positions(db: Session, summary: portfolio_service.PortfolioSummary, idx: index_data.IndexData,
                             today: date) -> tuple[list[dict], list[dict]]:
    buckets: dict[str, Decimal] = defaultdict(lambda: D(0))
    positions: list[dict] = []
    for v in summary.holdings:
        a = v.holding.asset
        if a.asset_class in (AssetClass.STOCK, AssetClass.BDR):
            label = "Ações Brasil" if a.country == "BR" else "Ações EUA"
        else:
            label = {AssetClass.ETF: "ETFs", AssetClass.FII: "FIIs", AssetClass.REIT: "REITs",
                     AssetClass.CRYPTO: "Criptomoedas"}[a.asset_class]
        buckets[label] += v.market_value_brl
        positions.append({"name": a.symbol, "value": v.market_value_brl, "protected":
                          v.holding.stop_loss is not None or v.holding.take_profit is not None, "market": True})
    for inv in fixed_income_service.list_investments(db, summary.portfolio.id):
        if inv.status != InvestmentStatus.ACTIVE:
            continue
        net = fixed_income_service.quote_redemption(inv, idx, today, apply_discount=False).net
        buckets["Renda fixa"] += net
        positions.append({"name": inv.product.name, "value": net, "protected": False, "market": False})
    buckets["Caixa"] += summary.cash_balance
    total = sum(buckets.values(), D(0))
    allocation = [{"label": k, "value": quantize_money(v), "pct": _pct(v, total)}
                  for k, v in sorted(buckets.items(), key=lambda kv: kv[1], reverse=True) if v > 0]
    return allocation, positions


def diversification(positions: list[dict]) -> tuple[int | None, dict | None]:
    """Nota 0-100 = (1 − HHI) × 100 sobre os pesos das posições investidas (sem o caixa)."""
    total = sum((p["value"] for p in positions), D(0))
    if total <= 0:
        return None, None
    weights = [(p["value"] / total, p["name"]) for p in positions]
    hhi = sum((w * w for w, _ in weights), D(0))
    top_w, top_name = max(weights)
    return int(((1 - hhi) * 100).quantize(D("1"))), {"name": top_name, "pct": _q2(top_w * 100)}


# ------------------------------------------------------------------ conquistas e dicas

def achievements(db: Session, user_id: int, portfolio: Portfolio, txs: list[Transaction], positions: list[dict],
                 invested_classes: int, total_return_pct: Decimal | None, beat_cdi: bool | None) -> list[dict]:
    from backend.content.course import TOTAL_LESSONS
    done = db.scalar(select(func.count()).select_from(LessonProgress).where(
        LessonProgress.user_id == user_id, LessonProgress.completed_at.is_not(None))) or 0
    t = lambda *types: [x for x in txs if x.type in types]  # noqa: E731
    sells = t(TransactionType.SELL)
    bought_assets = [x.asset for x in t(TransactionType.BUY) if x.asset]
    n_pos = len(positions)
    ret = total_return_pct or D(0)

    def a(id_, title, desc, current, target, detail=None):
        cur = int(min(current, target))
        return {"id": id_, "title": title, "description": desc, "unlocked": current >= target,
                "current": cur, "target": int(target), "detail": detail or f"{cur}/{int(target)}"}

    return [
        a("first_buy", "Primeira compra", "Faça sua primeira compra de um ativo.", len(t(TransactionType.BUY)), 1),
        a("first_profit", "Lucro realizado", "Venda um ativo com lucro.", sum(1 for x in sells if (x.realized_pnl_brl or 0) > 0), 1),
        a("first_income", "Renda passiva", "Receba seu primeiro provento (dividendo, rendimento ou juros).",
          len(t(TransactionType.DIVIDEND, TransactionType.FIXED_INCOME_COUPON)), 1),
        a("first_fixed_income", "Renda fixa", "Faça sua primeira aplicação em renda fixa.", len(t(TransactionType.FIXED_INCOME_APPLY)), 1),
        a("risk_manager", "Gestor de risco", "Defina um Stop Loss ou Take Profit.", sum(1 for h in portfolio.holdings if h.risk_version > 0), 1),
        a("crypto", "Cripto", "Compre uma criptomoeda.", sum(1 for x in bought_assets if x.asset_class == AssetClass.CRYPTO), 1),
        a("international", "Investidor global", "Compre um ativo dos EUA.", sum(1 for x in bought_assets if x.country == "US"), 1),
        a("diversified", "Carteira diversificada", "Tenha 5 posições em pelo menos 3 classes de ativos.",
          n_pos if invested_classes >= 3 else min(n_pos, 4), 5,
          f"{n_pos} posições em {invested_classes} classes"),
        a("ten_trades", "Operador", "Realize 10 operações de compra, venda ou aplicação.",
          len(t(TransactionType.BUY, TransactionType.SELL, TransactionType.FIXED_INCOME_APPLY)), 10),
        a("green", "No azul", "Tenha rentabilidade total positiva.", 1 if ret > 0 else 0, 1),
        a("plus_five", "+5%", "Alcance 5% de rentabilidade total.", int(max(min(ret, D(5)), D(0)) * 100), 500,
          f"{max(ret, D(0)):.2f}% de 5%".replace(".", ",")),
        a("beat_cdi", "Melhor que o CDI", "Supere o CDI no período registrado.", 1 if beat_cdi else 0, 1),
        a("student", "Estudante", "Conclua 5 aulas.", done, 5),
        a("graduate", "Formado", "Conclua todas as aulas.", done, TOTAL_LESSONS),
    ]


def insights(stats: dict, tstats: dict, series_n: int, allocation: list[dict], top: dict | None,
             positions: list[dict], max_dd: Decimal | None) -> list[dict]:
    def num(x: Decimal, sign=False) -> str:
        return (f"{x:+.2f}" if sign else f"{x:.2f}").replace(".", ",")

    out: list[dict] = []
    if series_n >= 2 and stats["period_return_pct"] is not None:
        diff = stats["vs_cdi_pp"]
        out.append({"tone": "good" if diff >= 0 else "warn", "lesson_id": "m2-l2" if diff < 0 else None,
                    "text": f"No período, sua carteira variou {num(stats['period_return_pct'], True)}% e o CDI {num(stats['cdi_pct'], True)}%: "
                            f"{num(abs(diff))} p.p. {'acima' if diff >= 0 else 'abaixo'} do CDI."})
    else:
        out.append({"tone": "info", "lesson_id": None,
                    "text": "Estamos registrando sua evolução a cada hora. Volte nos próximos dias para ver o gráfico ganhar forma."})
    n = tstats["wins"] + tstats["losses"]
    if n >= 3:
        out.append({"tone": "info", "lesson_id": None,
                    "text": f"Você acertou {tstats['wins']} de {n} operações encerradas ({num(tstats['win_rate_pct'])}%)."})
        po = tstats["payoff_ratio"]
        if po is not None and po < 1 and tstats["win_rate_pct"] < 60:
            out.append({"tone": "warn", "lesson_id": "m7-l2",
                        "text": f"Suas perdas médias são maiores que seus ganhos médios (relação {num(po)}). Cortar perdas cedo ajuda: veja Stop Loss."})
        elif po is not None and po >= 1.5:
            out.append({"tone": "good", "lesson_id": None,
                        "text": f"Bom controle de risco: seus ganhos médios são {num(po)}× as perdas médias."})
    if top and len(positions) >= 1 and top["pct"] > 50:
        out.append({"tone": "warn", "lesson_id": "m7-l1",
                    "text": f"{num(top['pct'])}% do que você tem investido está em {top['name']}. Concentração aumenta o risco: veja diversificação."})
    market = [p for p in positions if p["market"]]
    if market and sum(1 for p in market if p["protected"]) < len(market):
        out.append({"tone": "warn", "lesson_id": "m7-l2",
                    "text": f"Só {sum(1 for p in market if p['protected'])} de {len(market)} posições têm Stop Loss ou Take Profit."})
    cash = next((x for x in allocation if x["label"] == "Caixa"), None)
    if cash and cash["pct"] > 60:
        out.append({"tone": "info", "lesson_id": "m1-l1",
                    "text": f"{num(cash['pct'])}% do seu patrimônio está parado em caixa, sem render. Veja opções na aba Renda Fixa."})
    if tstats["income_total_brl"] > 0:
        out.append({"tone": "good", "lesson_id": None,
                    "text": f"Você já recebeu R$ {num(tstats['income_total_brl'])} em proventos e juros: renda passiva."})
    if max_dd is not None and max_dd <= -10:
        out.append({"tone": "info", "lesson_id": "m7-l3",
                    "text": f"Sua maior queda desde o pico foi de {num(max_dd)}%. Oscilações fazem parte; um plano evita decisões por impulso."})
    return out


# ------------------------------------------------------------------ resposta completa

def build_performance(db: Session, user_id: int, portfolio_id: int, range_key: str, now: datetime | None = None) -> dict:
    now = now or datetime.now(UTC)
    portfolio = portfolio_service.load_portfolio(db, portfolio_id)
    ensure_recent_snapshot(db, portfolio)
    idx, today = index_data.load(db), today_br()

    rows = load_snapshots(db, portfolio_id, range_key, now)
    series = build_series(downsample(rows, hourly=range_key in ("1d", "7d")), idx)
    sstats = series_stats(series)

    summary = portfolio_service.build_summary(db, portfolio)
    txs = load_transactions(db, portfolio_id)
    tstats = trade_stats(txs)
    monthly, cumulative = monthly_and_cumulative(txs)
    alloc, positions = allocation_and_positions(db, summary, idx, today)
    score, top = diversification(positions)

    initial = initial_deposit(db, portfolio_id)
    extra = summary.total_deposits_brl - initial
    wealth = quantize_money(summary.total_equity_brl - extra)
    total_return = _pct(wealth - initial, initial) if initial else None

    all_rows = rows if range_key == "all" else load_snapshots(db, portfolio_id, "all", now)
    all_series = series if range_key == "all" else build_series(downsample(all_rows, hourly=False), idx)
    all_stats = series_stats(all_series)
    beat = (all_stats["vs_cdi_pp"] >= 0) if all_stats["vs_cdi_pp"] is not None else None

    market = [p for p in positions if p["market"]]
    discipline = _pct(D(sum(1 for p in market if p["protected"])), D(len(market))) if market else None
    return {
        "range": range_key, "series": series, "series_stats": sstats,
        "summary": {
            "equity_brl": summary.total_equity_brl, "wealth_brl": wealth, "initial_brl": initial,
            "pnl_brl": quantize_money(wealth - initial), "total_return_pct": total_return,
            "diversification_score": score, "top_position": top, "discipline_pct": discipline,
            "positions": len(positions), "days_tracked": len({_local_date(r.taken_at) for r in all_rows}),
        },
        "trades": tstats, "allocation": alloc, "monthly": monthly, "realized_cumulative": cumulative,
        "achievements": achievements(db, user_id, portfolio, txs, positions,
                                     sum(1 for x in alloc if x["label"] != "Caixa"), total_return, beat),
        "insights": insights(sstats, tstats, len(series), alloc, top, positions, sstats["max_drawdown_pct"]),
    }
