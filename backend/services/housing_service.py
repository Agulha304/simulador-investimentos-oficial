"""Mercado de aluguel: o jogo decide se existe oferta para o valor que você quer pagar, e em que condições.

Não dá para escolher qualquer preço: abaixo do mínimo de mercado não existe imóvel. Dentro de cada faixa há uma chance de a oferta
existir naquele mês (sorteio determinístico por partida/mês/faixa). Quanto mais barato, pior a condição do lugar — e a moradia mexe
com a saúde, o bem-estar e a satisfação de quem mora nela.
"""
from datetime import date
from decimal import Decimal

from backend.core.money import quantize_money
from backend.services.life_rules import hash01, pick

D = Decimal
MIN_RENT = D("450")
# (aluguel mínimo, qualidade -3..+3, chance de haver oferta, título, descrições possíveis, efeito em palavras)
TIERS = [
    (D("450"), -3, 0.55, "Quarto simples em área afastada", [
        "Um quarto pequeno nos fundos de uma casa, longe do centro, com banheiro compartilhado e pouca ventilação.",
        "Um cômodo em bairro sem infraestrutura, com transporte demorado e barulho constante."],
     "Moradia muito precária: pesa na saúde, no bem-estar e na satisfação."),
    (D("700"), -2, 0.70, "Kitnet antiga em bairro afastado", [
        "Kitnet antiga com sinais de infiltração e mofo nas paredes, num bairro afastado.",
        "Kitnet pequena, escura e úmida, a 1h10 de transporte do centro."],
     "Umidade e pouca luz atrapalham a saúde e o humor."),
    (D("1100"), -1, 0.85, "Apartamento pequeno em bairro simples", [
        "Apartamento pequeno e simples, em prédio sem elevador, num bairro tranquilo mas distante.",
        "Apartamento de 1 quarto bem apertado, mas limpo e com boa vizinhança."],
     "Moradia modesta: pequeno peso na satisfação."),
    (D("1800"), 0, 0.92, "Apartamento de 1 quarto em bairro comum", [
        "Apartamento de 1 quarto em bom estado, perto de comércio e transporte.",
        "Apartamento reformado, silencioso, com portaria e vaga rotativa."],
     "Moradia confortável: sem efeito especial."),
    (D("3000"), 1, 0.95, "Apartamento de 2 quartos bem localizado", [
        "Apartamento claro, de 2 quartos, perto de parques e serviços.",
        "Apartamento moderno, com varanda e lazer no prédio, a poucos minutos do trabalho."],
     "Boa moradia: ajuda a sua satisfação."),
    (D("5000"), 2, 0.95, "Apartamento amplo em bairro nobre", [
        "Apartamento amplo e arejado em bairro nobre, com segurança 24h e academia no prédio.",
        "Apartamento reformado com vista, silêncio e comércio de qualidade na porta."],
     "Ótima moradia: melhora o bem-estar e a satisfação."),
    (D("9000"), 3, 0.97, "Casa ou cobertura de alto padrão", [
        "Cobertura de alto padrão com terraço, segurança reforçada e área verde.",
        "Casa em condomínio fechado, com jardim, piscina e ótima segurança."],
     "Moradia excelente: faz bem à saúde, ao bem-estar e à satisfação."),
]
QUALITY_EFFECT = {-3: (-2, -2, -1), -2: (-1, -1, -1), -1: (0, -1, 0), 0: (0, 0, 0), 1: (0, 1, 0), 2: (1, 1, 0), 3: (2, 2, 1)}   # (bem-estar, satisfação, saúde) por mês


def tier_of(rent: Decimal) -> int | None:
    idx = None
    for i, (lo, *_rest) in enumerate(TIERS):
        if rent >= lo:
            idx = i
    return idx


def quality_of_rent(rent: Decimal) -> tuple[int, str]:
    """Qualidade (−3..+3) e descrição de um aluguel que já existe (cenários e modo livre)."""
    i = tier_of(D(rent))
    if i is None:
        return -3, TIERS[0][3]
    return TIERS[i][1], TIERS[i][3]


def search(seed: int, user_id: int, ref: date, budget: Decimal) -> dict:
    """Há oferta por esse valor? Devolve também a condição do imóvel e o que ele faz com a sua vida."""
    budget = quantize_money(D(budget))
    i = tier_of(budget)
    if i is None:
        return {"available": False, "budget": str(budget), "message": f"Não existe imóvel para alugar por esse valor. O aluguel mais barato da região é de cerca de R$ {MIN_RENT}, e é bem precário."}
    lo, q, prob, title, descs, effect = TIERS[i]
    roll = hash01("rent-offer", seed, user_id, ref.isoformat(), i, int(budget // 50))
    if roll >= prob:
        return {"available": False, "budget": str(budget), "tier": title,
                "message": f"Procuramos “{title.lower()}” por até R$ {budget}, mas não há nenhuma oferta disponível agora. Tente subir um pouco o valor ou procure de novo no mês que vem."}
    rent = quantize_money(max(lo, (budget * D(str(round(0.92 + 0.08 * hash01("rent-price", seed, user_id, ref.isoformat(), i), 3)))).quantize(D("10"))))
    rent = min(rent, budget)
    return {"available": True, "budget": str(budget), "rent": str(rent), "quality": q, "title": title, "description": pick(descs, "rent-desc", seed, user_id, ref.isoformat(), i),
            "effect": effect, "message": f"Encontramos uma oferta de R$ {rent} por mês."}


def monthly_effect(q: int) -> tuple[int, int, int]:
    return QUALITY_EFFECT[max(-3, min(3, q))]
