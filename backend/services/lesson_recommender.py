"""Do desempenho às aulas: transforma comportamentos observados na carteira em aulas recomendadas, com o motivo.

As regras olham para dados reais (posições, alocação, operações, queda máxima, disciplina) e ordenam por importância.
Aulas que o usuário já concluiu ainda aparecem se o problema continua, mas marcadas como "revisar".
"""
from decimal import Decimal

from backend.content.course import LESSONS


def recommend(*, allocation: list[dict], positions: list[dict], tstats: dict, stats: dict, max_dd: Decimal | None,
              discipline_pct: Decimal | None, insights: list[dict], completed: set[str], limit: int = 5) -> list[dict]:
    picks: list[tuple[int, str, str]] = []                    # (prioridade, aula, motivo)

    def add(prio: int, lesson_id: str, why: str) -> None:
        if lesson_id in LESSONS:
            picks.append((prio, lesson_id, why))

    share = {a["label"]: float(a["pct"] or 0) for a in allocation}
    invested = [p for p in positions]
    for ins in insights:                                       # dicas já geradas com aula associada
        if ins.get("lesson_id") and ins["tone"] == "warn":
            add(10, ins["lesson_id"], ins["text"])
    if not invested:
        add(1, "m1-l4", "Você ainda não investiu: veja como usar o simulador para dar o primeiro passo.")
        add(2, "m1-l1", "Entenda por que investir em vez de deixar o dinheiro parado.")
    if share.get("Caixa", 0) > 60:
        add(8, "m2-l1", "Muito dinheiro parado no caixa: a renda fixa é um bom começo.")
    if share.get("Criptomoedas", 0) > 20:
        add(4, "m5-l2", "Boa parte do seu dinheiro está em criptomoedas, que oscilam muito: aprenda a dimensionar a posição.")
    if invested and share.get("Renda fixa", 0) == 0 and share.get("Caixa", 0) <= 60:
        add(12, "m2-l1", "Você ainda não tem renda fixa: ela dá segurança à carteira.")
    if len([p for p in invested if p["market"]]) == 1:
        add(6, "m7-l1", "Tudo em um único ativo de mercado: diversificar reduz o risco.")
    n_trades = tstats.get("buys", 0) + tstats.get("sells", 0)
    if tstats.get("win_rate_pct") is not None and tstats["win_rate_pct"] < 40 and tstats.get("closed_trades", 0) >= 3:
        add(5, "m7-l3", f"Você acertou só {tstats['win_rate_pct']}% das operações encerradas: veja os vieses que atrapalham.")
    if n_trades >= 12 and (tstats.get("total_realized_brl") or 0) <= 0:
        add(7, "m7-l3", "Muitas operações sem resultado positivo: operar demais costuma custar caro.")
    if discipline_pct is not None and discipline_pct < 50:
        add(9, "m7-l2", "Poucas posições com Stop Loss ou Take Profit: aprenda a proteger o que você investiu.")
    if max_dd is not None and max_dd <= -15:
        add(11, "m7-l3", f"Sua maior queda foi de {max_dd}%: um plano ajuda a não decidir no pânico.")
    if stats.get("vs_cdi_pp") is not None and stats["vs_cdi_pp"] < 0:
        add(13, "m2-l2", "Sua carteira rendeu menos que o CDI: entenda o que é a taxa de referência que você precisa vencer.")
    if any(p["market"] for p in invested) and not tstats.get("income_total_brl"):
        add(20, "m3-l3", "Você ainda não recebeu proventos: veja como dividendos e JCP geram renda.")
    out, seen = [], set()
    for _, lid, why in sorted(picks, key=lambda x: x[0]):
        if lid in seen:
            continue
        seen.add(lid)
        out.append({"lesson_id": lid, "title": LESSONS[lid].title, "reason": why, "review": lid in completed})
    return out[:limit]
