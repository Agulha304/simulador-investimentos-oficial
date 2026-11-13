"""Schemas das abas Desempenho, Ranking e Aulas."""
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, Field


# ------------------------------------------------------------------ desempenho
class SeriesPoint(BaseModel):
    t: datetime
    equity: Decimal
    wealth: Decimal
    cash: Decimal
    assets: Decimal
    fixed_income: Decimal
    net_deposits: Decimal
    return_pct: Decimal
    cdi_pct: Decimal
    drawdown_pct: Decimal


class SeriesStats(BaseModel):
    period_return_pct: Decimal | None
    cdi_pct: Decimal | None
    vs_cdi_pp: Decimal | None
    max_drawdown_pct: Decimal | None
    best_day_pct: Decimal | None
    worst_day_pct: Decimal | None


class TopPosition(BaseModel):
    name: str
    pct: Decimal


class PerfSummary(BaseModel):
    equity_brl: Decimal
    wealth_brl: Decimal
    initial_brl: Decimal
    pnl_brl: Decimal
    total_return_pct: Decimal | None
    diversification_score: int | None
    top_position: TopPosition | None
    discipline_pct: Decimal | None
    positions: int
    days_tracked: int


class TradeStats(BaseModel):
    buys: int
    sells: int
    fixed_income_applications: int
    closed_trades: int
    wins: int
    losses: int
    win_rate_pct: Decimal | None
    avg_win_brl: Decimal | None
    avg_loss_brl: Decimal | None
    payoff_ratio: Decimal | None
    profit_factor: Decimal | None
    total_realized_brl: Decimal
    income_total_brl: Decimal
    best_trade_brl: Decimal | None
    best_trade_label: str | None
    worst_trade_brl: Decimal | None
    worst_trade_label: str | None


class AllocationItem(BaseModel):
    label: str
    value: Decimal
    pct: Decimal


class MonthlyItem(BaseModel):
    month: str
    realized: Decimal
    income: Decimal
    trades: int


class CumulativePoint(BaseModel):
    date: date
    cumulative: Decimal


class Achievement(BaseModel):
    id: str
    title: str
    description: str
    unlocked: bool
    current: int
    target: int
    detail: str


class Insight(BaseModel):
    tone: str                     # good | warn | info
    text: str
    lesson_id: str | None = None


class PerformanceOut(BaseModel):
    range: str
    series: list[SeriesPoint]
    series_stats: SeriesStats
    summary: PerfSummary
    trades: TradeStats
    allocation: list[AllocationItem]
    monthly: list[MonthlyItem]
    realized_cumulative: list[CumulativePoint]
    achievements: list[Achievement]
    insights: list[Insight]


# ------------------------------------------------------------------ ranking
class RankEntry(BaseModel):
    rank: int
    nickname: str
    wealth_brl: Decimal
    gain_brl: Decimal
    return_pct: Decimal
    is_me: bool = False


class RankingOut(BaseModel):
    board: str
    period: str
    participants: int
    entries: list[RankEntry]
    me: RankEntry | None
    me_hidden: bool
    note: str


class RankingSettings(BaseModel):
    show_in_ranking: bool
    nickname: str | None = Field(default=None, min_length=2, max_length=24)
    default_nickname: str | None = None


# ------------------------------------------------------------------ aulas
class LessonBrief(BaseModel):
    id: str
    title: str
    minutes: int
    summary: str
    completed: bool
    best_score: int | None


class ModuleOut(BaseModel):
    id: str
    title: str
    description: str
    level: str
    lessons: list[LessonBrief]
    completed: int
    total: int


class LearnOverview(BaseModel):
    modules: list[ModuleOut]
    completed: int
    total: int
    percent: int
    points: int
    level: str
    next_lesson_id: str | None


class QuestionOut(BaseModel):
    text: str
    options: list[str]


class LessonOut(BaseModel):
    id: str
    module_id: str
    module_title: str
    title: str
    minutes: int
    blocks: list[list]
    quiz: list[QuestionOut]
    completed: bool
    best_score: int | None
    prev_id: str | None
    next_id: str | None


class QuizSubmit(BaseModel):
    answers: list[int] = Field(max_length=20)


class QuestionResult(BaseModel):
    correct: bool
    correct_index: int
    explanation: str


class QuizResult(BaseModel):
    score: int
    passed: bool
    pass_score: int
    results: list[QuestionResult]
    completed: bool
    next_lesson_id: str | None
    overview: LearnOverview
