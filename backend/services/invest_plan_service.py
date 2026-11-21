"""Orçamento da carteira de investimentos: quanto investir por mês (recomendado) e em quê (carteira-alvo por perfil de investidor).

* O valor recomendado vem da sobra do orçamento do mês e do perfil; enquanto a reserva de emergência é menor que 3 meses, a
  recomendação vai toda para renda fixa (formar a reserva primeiro).
* A carteira-alvo muda com o perfil (conservador, moderado, arrojado) e com o que o jogador QUER investir; pode ser editada à mão.
* O progresso mostra, por tipo de investimento, quanto já tem, o objetivo em R$ e quanto falta; a divisão sugerida do mês
  prioriza o que está mais atrasado.
"""
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.core.money import quantize_money
from backend.models import Asset, AssetClass, InvestorProfile, MonthStatus, SimMonth, Transaction, TransactionType
from backend.services import budget_service, portfolio_service, progression_service
from backend.services.finance_ledger import FinanceError
from backend.models import Portfolio

D = Decimal
ZERO = D("0.00")
CLASSES = ("FIXED", "STOCKS", "ETF", "FII", "CRYPTO")
LABEL = {"FIXED": "Renda fixa", "STOCKS": "Ações", "ETF": "ETFs", "FII": "Fundos imobiliários", "CRYPTO": "Criptomoedas"}
PROFILE_ALLOC = {
    "CONSERVATIVE": {"FIXED": 70, "FII": 10, "ETF": 10, "STOCKS": 8, "CRYPTO": 2},
    "MODERATE": {"FIXED": 40, "FII": 15, "ETF": 15, "STOCKS": 25, "CRYPTO": 5},
    "AGGRESSIVE": {"FIXED": 15, "FII": 10, "ETF": 15, "STOCKS": 45, "CRYPTO": 15},
}
PROFILE_LABEL = {"CONSERVATIVE": "Conservador", "MODERATE": "Moderado", "AGGRESSIVE": "Arrojado"}
PROFILE_TEXT = {"CONSERVATIVE": "Prefere segurança: aceita render menos para quase não ver o dinheiro oscilar.",
                "MODERATE": "Equilibra segurança e crescimento: aceita algumas oscilações em troca de render mais.",
                "AGGRESSIVE": "Topa grandes oscilações em busca de maior retorno no longo prazo."}
SHARE_OF_SURPLUS = {"CONSERVATIVE": D("0.40"), "MODERATE": D("0.60"), "AGGRESSIVE": D("0.80")}
# Rendimento de RENDA (juros, cupons, dividendos, aluguéis) esperado por classe, % ao ano. Premissa SIMPLIFICADA e conservadora
# para estimar quanto patrimônio gera uma renda passiva; não é promessa de retorno (cripto não gera renda periódica).
YIELD_PCT = {"FIXED": D("10.0"), "FII": D("9.0"), "STOCKS": D("5.0"), "ETF": D("4.0"), "CRYPTO": D("0.0")}
CLASS_OF = {AssetClass.STOCK: "STOCKS", AssetClass.BDR: "STOCKS", AssetClass.ETF: "ETF", AssetClass.FII: "FII", AssetClass.REIT: "FII", AssetClass.CRYPTO: "CRYPTO"}

QUIZ = [
    ("Por quanto tempo você pretende deixar o dinheiro investido?", ["Menos de 1 ano", "De 1 a 3 anos", "De 3 a 10 anos", "Mais de 10 anos"]),
    ("Se o seu investimento caísse 20% em um mês, o que você faria?", ["Venderia tudo para não perder mais", "Venderia uma parte", "Manteria e esperaria", "Compraria mais, está barato"]),
    ("O que é mais importante para você?", ["Nunca perder dinheiro", "Render um pouco mais que a poupança", "Equilíbrio entre segurança e ganho", "Ganhar muito, mesmo com risco"]),
    ("Você já tem uma reserva de emergência?", ["Não tenho", "Tenho um pouco", "Tenho de 3 a 6 meses de despesas", "Tenho mais de 6 meses"]),
    ("Quanto da sua renda você consegue guardar sem aperto?", ["Menos de 5%", "De 5% a 10%", "De 10% a 20%", "Mais de 20%"]),
    ("Quanto você entende de investimentos?", ["Nada", "Um pouco", "Razoavelmente", "Bastante"]),
    ("Qual é a sua principal meta?", ["Comprar algo em breve", "Proteger o que já tenho", "Fazer o patrimônio crescer", "Ficar rico ou me aposentar cedo"]),
    ("Como você se sente quando os preços oscilam muito?", ["Muito ansioso(a)", "Um pouco preocupado(a)", "Tranquilo(a)", "Gosto da emoção"]),
]


def profile_from_score(score: int) -> str:
    return "CONSERVATIVE" if score <= 15 else "MODERATE" if score <= 24 else "AGGRESSIVE"


def alloc_for(profile: str, wanted: list[str]) -> dict[str, int]:
    """Carteira do perfil, só com as classes desejadas (renda fixa sempre entra), reponderada para somar 100."""
    base = {k: v for k, v in PROFILE_ALLOC[profile].items() if k == "FIXED" or k in wanted}
    total = sum(base.values())
    out = {k: int(round(v * 100 / total)) for k, v in base.items()}
    out["FIXED"] += 100 - sum(out.values())                              # ajuste de arredondamento
    return {k: out.get(k, 0) for k in CLASSES}


def get_profile(db: Session, user_id: int) -> InvestorProfile:
    ip = db.scalar(select(InvestorProfile).where(InvestorProfile.user_id == user_id))
    if ip is None:
        ip = InvestorProfile(user_id=user_id, profile="MODERATE", wanted=list(CLASSES), target_alloc=alloc_for("MODERATE", list(CLASSES)))
        db.add(ip)
        db.flush()
    return ip


def submit_quiz(db: Session, user_id: int, answers: list[int]) -> InvestorProfile:
    if len(answers) != len(QUIZ) or any(not 0 <= a < 4 for a in answers):
        raise FinanceError("responda todas as perguntas")
    score = sum(a + 1 for a in answers)
    ip = get_profile(db, user_id)
    ip.quiz_score, ip.profile = score, profile_from_score(score)
    ip.target_alloc, ip.customized = alloc_for(ip.profile, ip.wanted or list(CLASSES)), False
    db.flush()
    return ip


def update_settings(db: Session, user_id: int, *, profile: str | None = None, wanted: list[str] | None = None, alloc: dict | None = None,
                    goal_total: Decimal | None = None, passive_goal: Decimal | None = None) -> InvestorProfile:
    ip = get_profile(db, user_id)
    if profile is not None:
        if profile not in PROFILE_ALLOC:
            raise FinanceError("perfil inválido")
        ip.profile = profile
    if wanted is not None:
        if any(w not in CLASSES for w in wanted):
            raise FinanceError("tipo de investimento inválido")
        ip.wanted = sorted(set(wanted) | {"FIXED"})
    if alloc is not None:
        if set(alloc) - set(CLASSES) or any(float(v) < 0 for v in alloc.values()):
            raise FinanceError("carteira inválida")
        total = sum(float(v) for v in alloc.values())
        if abs(total - 100) > 0.01:
            raise FinanceError(f"a carteira precisa somar 100% (soma atual: {total:g}%)")
        ip.target_alloc, ip.customized = {k: float(alloc.get(k, 0)) for k in CLASSES}, True
    elif profile is not None or wanted is not None:
        ip.target_alloc, ip.customized = alloc_for(ip.profile, ip.wanted or list(CLASSES)), False        # o perfil e o que você quer mudam a carteira
    if goal_total is not None:
        if goal_total < 0:
            raise FinanceError("o objetivo não pode ser negativo")
        ip.goal_total = quantize_money(goal_total) if goal_total > 0 else None
    if passive_goal is not None:
        if passive_goal < 0:
            raise FinanceError("a renda passiva desejada não pode ser negativa")
        ip.passive_goal = quantize_money(passive_goal) if passive_goal > 0 else None
    db.flush()
    return ip


def current_amounts(db: Session, user_id: int) -> dict[str, Decimal]:
    pf = db.scalar(select(Portfolio).where(Portfolio.user_id == user_id))
    s = portfolio_service.build_summary(db, pf)
    out = {k: ZERO for k in CLASSES}
    for v in s.holdings:
        out[CLASS_OF.get(v.holding.asset.asset_class, "STOCKS")] += v.market_value_brl
    out["FIXED"] += s.fixed_income_value_brl
    return {k: quantize_money(v) for k, v in out.items()}


def recommend_monthly(db: Session, user_id: int, month: SimMonth, ip: InvestorProfile) -> dict:
    summ = budget_service.summarize(db, user_id, month)
    surplus = quantize_money(summ.planned_income - summ.planned_expense)
    m = progression_service.metrics(db, user_id, month.ref_month)
    reserve_mode = m["emergency_months"] < 3
    if surplus <= 0:
        return {"amount": ZERO, "surplus": surplus, "share_pct": 0, "reserve_mode": reserve_mode,
                "reason": "O seu orçamento do mês não tem sobra: reduza despesas ou aumente a renda antes de investir."}
    share = D("0.70") if reserve_mode else SHARE_OF_SURPLUS[ip.profile]
    amount = quantize_money(surplus * share)
    reason = (f"Sua reserva de emergência cobre só {m['emergency_months']:.1f} mês(es): primeiro forme 3 a 6 meses de despesas, em renda fixa. Recomendamos {int(share * 100)}% da sobra."
              if reserve_mode else f"Para o perfil {PROFILE_LABEL[ip.profile].lower()} recomendamos investir {int(share * 100)}% da sobra do mês e manter o resto como folga.")
    return {"amount": amount, "surplus": surplus, "share_pct": int(share * 100), "reserve_mode": reserve_mode, "reason": reason}


def blended_yield_pct(alloc: dict[str, Decimal]) -> Decimal:
    """Rendimento de renda médio da carteira-alvo (% ao ano), ponderado pela alocação."""
    return sum((alloc[k] / 100 * YIELD_PCT[k] for k in CLASSES), D(0))


def required_capital(passive_goal: Decimal, yield_pct: Decimal) -> Decimal | None:
    """Patrimônio que gera `passive_goal` por mês com o rendimento de renda `yield_pct` ao ano."""
    if yield_pct <= 0 or passive_goal <= 0:
        return None
    return quantize_money(passive_goal * 12 / (yield_pct / 100))


def months_to_reach(current: Decimal, goal: Decimal, monthly: Decimal, yield_pct: Decimal, cap: int = 1200) -> int | None:
    """Meses até o patrimônio chegar a `goal` aportando `monthly` e reinvestindo a renda (estimativa)."""
    if current >= goal:
        return 0
    r = float(yield_pct) / 100 / 12
    bal, p = float(current), float(monthly)
    if p <= 0 and r <= 0:
        return None
    for n in range(1, cap + 1):
        bal = bal * (1 + r) + p
        if bal >= float(goal):
            return n
    return None


def invested_by_class(db: Session, user_id: int, month: SimMonth) -> dict[str, Decimal]:
    """Quanto foi APORTADO neste mês, por classe do plano (mesma base de `budget_service._invested_since`: desde a abertura
    do mês). Renda fixa vem das aplicações (FIXED_INCOME_APPLY); o resto, das compras (BUY) pela classe do ativo."""
    out = {k: ZERO for k in CLASSES}
    if month.status != MonthStatus.OPEN:
        return out
    pid = db.scalar(select(Portfolio.id).where(Portfolio.user_id == user_id))
    for cls, total in db.execute(
        select(Asset.asset_class, func.coalesce(func.sum(Transaction.gross_amount_brl), 0))
        .join(Asset, Asset.id == Transaction.asset_id)
        .where(Transaction.portfolio_id == pid, Transaction.type == TransactionType.BUY, Transaction.created_at >= month.opened_at)
        .group_by(Asset.asset_class)
    ):
        out[CLASS_OF.get(cls, "STOCKS")] += total
    out["FIXED"] += db.scalar(select(func.coalesce(func.sum(Transaction.gross_amount_brl), 0)).where(
        Transaction.portfolio_id == pid, Transaction.type == TransactionType.FIXED_INCOME_APPLY, Transaction.created_at >= month.opened_at))
    return {k: quantize_money(v) for k, v in out.items()}


def plan(db: Session, user_id: int, month: SimMonth) -> dict:
    ip = get_profile(db, user_id)
    rec = recommend_monthly(db, user_id, month, ip)
    cur = current_amounts(db, user_id)
    invested = sum(cur.values(), ZERO)
    alloc = {k: D(str(ip.target_alloc.get(k, 0))) for k in CLASSES}
    yield_pct = blended_yield_pct(alloc)
    needed = required_capital(ip.passive_goal, yield_pct) if ip.passive_goal else None
    if needed is not None:                                          # renda passiva desejada => patrimônio necessário vira o objetivo
        goal = needed
    else:
        goal = ip.goal_total or max(quantize_money(invested + rec["amount"] * 12), quantize_money(rec["amount"] * 12))
    month_invested = invested_by_class(db, user_id, month)
    if rec["reserve_mode"]:                                         # reserva primeiro: este mês vai tudo para renda fixa
        month_alloc = {k: (D(100) if k == "FIXED" else ZERO) for k in CLASSES}
    else:
        # a divisão do mês parte da carteira do INÍCIO do mês (descontando o que já foi aportado nele): assim ela não "anda"
        # a cada compra e o quanto falta por classe só diminui conforme você investe
        gaps = {k: max(ZERO, goal * alloc[k] / 100 - max(ZERO, cur[k] - month_invested[k])) for k in CLASSES}   # o mais atrasado recebe mais
        tg = sum(gaps.values(), ZERO)
        month_alloc = {k: (gaps[k] / tg * 100 if tg > 0 else alloc[k]) for k in CLASSES}
    amount = rec["amount"]
    rows = []
    for k in CLASSES:
        target_amount = quantize_money(goal * alloc[k] / 100)
        rows.append({"key": k, "label": LABEL[k], "target_pct": float(alloc[k]), "target_amount": str(target_amount), "current": str(cur[k]),
                     "missing": str(max(ZERO, quantize_money(target_amount - cur[k]))), "filled_pct": round(min(100.0, float(cur[k] / target_amount * 100)) if target_amount > 0 else 100.0, 1),
                     "month_pct": round(float(month_alloc[k]), 1), "month_amount": str(quantize_money(amount * month_alloc[k] / 100))})
    # ---- planejado do mês x já aportado (alimenta o aviso das telas de investir e o "após investir" do orçamento)
    planned = month.planned_investment or ZERO
    by_class = month_invested
    invested_month = sum(by_class.values(), ZERO)
    remaining_total = max(ZERO, quantize_money(planned - invested_month)) if month.status == MonthStatus.OPEN else ZERO
    nudge_rows = []
    for k in CLASSES:
        target_k = quantize_money(planned * month_alloc[k] / 100)
        rem_k = min(max(ZERO, target_k - by_class[k]), remaining_total)
        nudge_rows.append({"key": k, "label": LABEL[k], "target": str(target_k), "invested": str(by_class[k]), "remaining": str(quantize_money(rem_k))})
    nudge = {"planned": str(planned), "invested": str(invested_month), "remaining": str(remaining_total),
             "done": bool(planned > 0 and month.status == MonthStatus.OPEN and remaining_total == 0),
             "active": bool(planned > 0 and month.status == MonthStatus.OPEN and remaining_total > 0),
             "reserve_mode": rec["reserve_mode"], "month": month.ref_month.isoformat(), "rows": nudge_rows}
    # ---- renda passiva desejada -> patrimônio necessário e prazo estimado
    contribution = planned if planned > 0 else rec["amount"]
    passive = {"goal": str(ip.passive_goal) if ip.passive_goal else None, "yield_pct": float(round(yield_pct, 2)),
               "required_capital": str(needed) if needed is not None else None,
               "income_now": str(quantize_money(invested * yield_pct / 100 / 12)),          # renda mensal estimada do que já está investido
               "missing_capital": str(max(ZERO, quantize_money(goal - invested))) if needed is not None else None,
               "months_to_goal": months_to_reach(invested, goal, contribution, yield_pct) if needed is not None else None,
               "monthly_contribution": str(contribution),
               "assumptions": {k: float(YIELD_PCT[k]) for k in CLASSES}}
    return {"profile": ip.profile, "profile_label": PROFILE_LABEL[ip.profile], "profile_text": PROFILE_TEXT[ip.profile], "quiz_score": ip.quiz_score,
            "wanted": ip.wanted or list(CLASSES), "customized": ip.customized, "goal_total": str(goal), "goal_is_custom": ip.goal_total is not None and needed is None,
            "goal_from_passive": needed is not None, "passive": passive, "nudge": nudge,
            "invested_now": str(invested), "recommended": {**{k: (str(v) if isinstance(v, Decimal) else v) for k, v in rec.items()}},
            "planned_investment": str(month.planned_investment), "rows": rows, "classes": [{"key": k, "label": LABEL[k]} for k in CLASSES],
            "profiles": [{"key": k, "label": PROFILE_LABEL[k], "text": PROFILE_TEXT[k], "alloc": PROFILE_ALLOC[k]} for k in PROFILE_ALLOC]}


def apply_recommendation(db: Session, user_id: int, month: SimMonth) -> dict:
    budget_service.require_open(month)
    rec = recommend_monthly(db, user_id, month, get_profile(db, user_id))
    month.planned_investment = rec["amount"]
    db.flush()
    return plan(db, user_id, month)
