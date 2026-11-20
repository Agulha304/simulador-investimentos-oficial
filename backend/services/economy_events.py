"""Catálogo de eventos (dados). Para criar um evento novo basta acrescentar uma `EventDef`: sem tocar no motor.

Campos:
  prob        probabilidade-base por mês (multiplicada pelo retorno de `cond`; 0 = impossível)
  cond        função (macro: dict, ctx: dict) -> float em [0, +inf) — coerência: crise é mais provável com confiança baixa...
  effects     modificadores enquanto o evento está ativo (somas simples, nunca acumulam em cascata):
                inflation/interest/unemployment/growth/demand/confidence (offsets sobre o estado latente)
                prices {categoria: pp ao mês} · assets_pct (%/mês nos imóveis) · assets_all_pct (%/mês em todos os bens)
                company_demand_pct · supplier_pct (empresas do escopo) · income_pct (sobre o salário do usuário)
                life {health, wellbeing, satisfaction} (aplicado uma vez, ao ativar)
                oneoff [{kind, amount, price_cat, label, target}] (despesas/receitas únicas no mês de início)
  options     eventos com decisão: cada opção tem `hint` (o que o usuário vê) e `outcomes` (resultados incertos, ocultos).
"""
from dataclasses import dataclass, field
from typing import Callable


@dataclass(frozen=True)
class Outcome:
    prob: float
    text: str
    effects: dict
    duration: int = 1


@dataclass(frozen=True)
class Option:
    key: str
    label: str
    hint: str
    outcomes: tuple[Outcome, ...]
    cost: int = 0                     # R$ de referência cobrados do usuário (pessoal) ao escolher
    default: bool = False             # aplicada automaticamente se o mês virar sem decisão


@dataclass(frozen=True)
class EventDef:
    key: str
    name: str
    description: str
    category: str                     # ECONOMIC | PERSONAL | BUSINESS
    scope: str                        # WORLD | SECTOR | USER | COMPANY
    positive: bool
    intensity: int
    duration: tuple[int, int]
    prob: float
    cond: Callable[[dict, dict], float] = lambda m, c: 1.0
    effects: dict = field(default_factory=dict)
    options: tuple[Option, ...] = ()
    sectors: tuple[str, ...] = ()     # segmentos possíveis (SECTOR); vazio = todos
    company_needs: str = ""           # COMPANY: só empresas com 'employees' ou 'partners'


def _lo_conf(m, c): return 2.5 if m["confidence"] < 40 else 1.0 if m["confidence"] < 55 else 0.2
def _hi_conf(m, c): return 2.0 if m["confidence"] > 60 and m["growth"] < 3.5 else 0.6 if m["confidence"] > 45 else 0.1
def _hi_infl(m, c): return 3.0 if m["inflation"] > 7 else 1.5 if m["inflation"] > 5 else 0.2
def _hi_unemp(m, c): return 3.0 if m["unemployment"] > 11 else 1.0 if m["unemployment"] > 8 else 0.15
def _has_company(m, c): return 1.0 if c["companies"] else 0.0
def _sick(m, c): return 3.0 if c["health"] < 50 else 1.0 if c["health"] < 70 else 0.5
def _employed(m, c): return 1.0 if c["salary"] > 0 else 0.0
def _stable(m, c): return 1.0 if c["salary"] > 0 and c["months"] >= 6 and c["work_level"] != "REDUCED" else 0.0
def _family(m, c): return 1.5 if c["children"] or c["partner"] else 0.6
def _renting(m, c): return 1.0 if c["housing_kind"] in ("RENT", "SHARED") else 0.0


CATALOG: tuple[EventDef, ...] = (
    EventDef("processo_trabalhista", "Funcionário processa a empresa", "Um funcionário entrou com um processo trabalhista pedindo verbas. Como reagir?",
             "BUSINESS", "COMPANY", False, 2, (1, 1), 0.012, lambda m, c: _has_employees(m, c) * (1.6 if m["unemployment"] > 10 else 1.0), company_needs="employees",
             options=(Option("acordo", "Fazer um acordo", "Paga agora e encerra o assunto.", (Outcome(1.0, "Acordo fechado: o processo foi encerrado.", {"company_oneoff": {"payroll_mult": 2.0, "label": "Acordo trabalhista"}}, 1),)),
                      Option("contestar", "Contestar na justiça", "Advogado custa; você pode ganhar ou perder feio.",
                             (Outcome(0.5, "Você ganhou o processo e só pagou o advogado.", {"company_oneoff": {"payroll_mult": 0.5, "label": "Advogado (processo trabalhista)"}}, 1),
                              Outcome(0.5, "Você perdeu: indenização maior e advogado.", {"company_oneoff": {"payroll_mult": 3.5, "label": "Condenação trabalhista e advogado"}}, 1))),
                      Option("ignorar", "Deixar correr", "Sem resposta, o risco é maior.", (Outcome(1.0, "Sem defesa, a empresa foi condenada à revelia.", {"company_oneoff": {"payroll_mult": 4.0, "label": "Condenação trabalhista (revelia)"}}, 1),), default=True))),
    EventDef("calote_socio", "Sócio dá um calote na sociedade", "Um sócio retirou dinheiro da empresa e sumiu com a sua parte. O que fazer?",
             "BUSINESS", "COMPANY", False, 3, (1, 1), 0.010, lambda m, c: _has_partners(m, c) * 1.0, effects={"on_spawn": "partner_default"}, company_needs="partners",
             options=(Option("negociar", "Negociar a devolução", "Recupera só uma parte, sem briga.", (Outcome(0.7, "O ex-sócio devolveu uma parte do dinheiro.", {"company_income": {"loss_mult": 0.4, "label": "Devolução negociada do ex-sócio"}}, 1),
                                                                                                    Outcome(0.3, "O ex-sócio não respondeu mais.", {}, 1))),
                      Option("processar", "Processar o ex-sócio", "Advogado custa e demora; pode recuperar quase tudo.",
                             (Outcome(0.55, "A justiça determinou o ressarcimento: você recuperou a maior parte.", {"company_oneoff": {"amount": 3000, "label": "Advogado (ação contra sócio)"},
                                                                                                                  "company_income": {"loss_mult": 0.8, "label": "Ressarcimento judicial"}}, 1),
                              Outcome(0.45, "O processo foi perdido e ele não tinha bens para pagar.", {"company_oneoff": {"amount": 3000, "label": "Advogado (ação contra sócio)"}}, 1))),
                      Option("aceitar", "Aceitar o prejuízo", "Segue em frente sem gastar mais.", (Outcome(1.0, "Você aceitou o prejuízo e reorganizou a empresa.", {}, 1),), default=True))),
    # ------------------------------------------------------------ macroeconomia / mundo
    EventDef("crescimento", "Crescimento econômico acelerado", "A economia aquece: mais consumo, emprego e confiança.",
             "ECONOMIC", "WORLD", True, 2, (6, 10), 0.07, _hi_conf,
             {"growth": 1.6, "demand": 7, "confidence": 8, "unemployment": -1.2, "assets_pct": 0.15}),
    EventDef("crise", "Crise econômica", "Recessão: queda de atividade, desemprego em alta e confiança em baixa.",
             "ECONOMIC", "WORLD", False, 3, (8, 14), 0.045, _lo_conf,
             {"growth": -3.5, "demand": -14, "confidence": -22, "unemployment": 3.5, "assets_pct": -0.3, "assets_all_pct": -0.15}),
    EventDef("alta_juros", "Alta de juros", "O banco central eleva os juros para conter a inflação: crédito mais caro.",
             "ECONOMIC", "WORLD", False, 2, (5, 9), 0.07, _hi_infl,
             {"interest": 3.5, "demand": -3, "assets_pct": -0.2}),
    EventDef("queda_juros", "Queda de juros", "Juros menores barateiam o crédito e estimulam o consumo.",
             "ECONOMIC", "WORLD", True, 2, (5, 9), 0.05, lambda m, c: 2.0 if m["inflation"] < 4 and m["interest"] > 9 else 0.1,
             {"interest": -2.8, "demand": 3, "assets_pct": 0.2}),
    EventDef("alta_alimentos", "Alta no preço dos alimentos", "Safra ruim e frete caro pressionam supermercados e restaurantes.",
             "ECONOMIC", "WORLD", False, 2, (3, 6), 0.08, lambda m, c: 1.5 if m["inflation"] > 5 else 1.0,
             {"prices": {"alimentacao": 1.1}, "inflation": 1.0, "confidence": -3}),
    EventDef("alta_energia", "Alta da energia", "Bandeira tarifária vermelha encarece energia e transporte.",
             "ECONOMIC", "WORLD", False, 2, (3, 6), 0.05, lambda m, c: 1.0,
             {"prices": {"energia": 1.6, "transporte": 0.4}, "inflation": 0.8}),
    EventDef("queda_insumos", "Queda no custo de insumos", "Cadeias de fornecimento normalizadas reduzem custos.",
             "ECONOMIC", "WORLD", True, 1, (3, 6), 0.06, lambda m, c: 1.0,
             {"prices": {"insumos": -0.7, "materiais_construcao": -0.5}, "inflation": -0.5}),
    EventDef("valorizacao_imoveis", "Valorização dos imóveis", "Demanda por moradia aquece o mercado imobiliário.",
             "ECONOMIC", "WORLD", True, 2, (6, 12), 0.05, lambda m, c: 1.8 if m["interest"] < 9.5 else 0.7,
             {"assets_pct": 0.55, "prices": {"moradia": 0.3}}),
    EventDef("desvalorizacao_ativos", "Desvalorização de ativos", "Aversão a risco derruba o preço de bens e imóveis.",
             "ECONOMIC", "WORLD", False, 2, (4, 8), 0.04, _lo_conf,
             {"assets_all_pct": -0.55, "assets_pct": -0.3, "confidence": -4}),
    EventDef("queda_demanda", "Queda geral da demanda", "Os consumidores seguram os gastos.",
             "ECONOMIC", "WORLD", False, 2, (3, 6), 0.05, _lo_conf,
             {"demand": -9, "confidence": -5}),
    EventDef("alta_setor", "Aumento da demanda no setor", "Uma tendência de consumo aquece um segmento.",
             "ECONOMIC", "SECTOR", True, 2, (3, 6), 0.07, lambda m, c: 1.0,
             {"company_demand_pct": 14}),
    EventDef("crise_setor", "Crise no setor", "Um segmento específico enfrenta queda de vendas.",
             "ECONOMIC", "SECTOR", False, 2, (3, 6), 0.045, lambda m, c: 1.0,
             {"company_demand_pct": -13}),
    EventDef("alta_educacao_saude", "Reajuste de mensalidades e planos", "Escolas e planos de saúde reajustam acima da inflação.",
             "ECONOMIC", "WORLD", False, 1, (2, 4), 0.05, _hi_infl,
             {"prices": {"educacao": 0.9, "saude": 0.9}}),
    EventDef("petroleo", "Descoberta de grande reserva de petróleo", "Mais oferta de energia: combustíveis e energia ficam mais baratos.",
             "ECONOMIC", "WORLD", True, 2, (6, 12), 0.015, lambda m, c: 1.0,
             {"prices": {"combustiveis": -0.9, "energia": -0.4}, "growth": 0.6, "confidence": 3, "assets_all_pct": 0.1}),
    EventDef("avanco_tecnologico", "Avanço tecnológico", "Uma nova tecnologia reduz custos de produção em vários setores.",
             "ECONOMIC", "WORLD", True, 1, (8, 14), 0.015, lambda m, c: 1.0,
             {"prices": {"insumos": -0.3, "servicos": -0.1}, "growth": 0.5, "confidence": 2}),
    EventDef("safra_recorde", "Safra agrícola excepcional", "Boa colheita derruba o preço dos alimentos.",
             "ECONOMIC", "WORLD", True, 1, (4, 8), 0.025, lambda m, c: 1.0, {"prices": {"alimentacao": -0.7}, "inflation": -0.4}),
    EventDef("quebra_safra", "Quebra de safra", "Clima adverso destrói parte da colheita e os alimentos sobem.",
             "ECONOMIC", "WORLD", False, 2, (4, 8), 0.022, lambda m, c: 1.0, {"prices": {"alimentacao": 1.2}, "inflation": 0.6, "confidence": -2}),
    EventDef("conflito_internacional", "Conflito internacional", "Tensão geopolítica sacode mercados e preços de energia.",
             "ECONOMIC", "WORLD", False, 2, (4, 9), 0.012, lambda m, c: 1.0,
             {"prices": {"energia": 0.9, "combustiveis": 1.3}, "confidence": -4, "assets_all_pct": -0.5, "inflation": 0.5}),
    EventDef("guerra_comercial", "Mudança nas relações comerciais", "Novas tarifas encarecem produtos importados.",
             "ECONOMIC", "WORLD", False, 1, (6, 12), 0.012, lambda m, c: 1.0,
             {"prices": {"importados": 0.9, "insumos": 0.3}, "growth": -0.3}),
    EventDef("infraestrutura", "Grande investimento em infraestrutura", "Obras públicas aquecem a construção e o emprego.",
             "ECONOMIC", "WORLD", True, 1, (8, 16), 0.012, lambda m, c: 1.0,
             {"growth": 0.5, "unemployment": -0.5, "prices": {"materiais_construcao": 0.3}, "assets_pct": 0.1}),
    EventDef("nova_regulamentacao", "Nova regulamentação", "Regras novas elevam custos de conformidade para serviços.",
             "ECONOMIC", "WORLD", False, 1, (6, 12), 0.015, lambda m, c: 1.0, {"prices": {"servicos": 0.25, "saude": 0.15}}),
    # ------------------------------------------------------------ pessoais
    EventDef("despesa_medica", "Despesa médica inesperada", "Consultas, exames e um tratamento fora do orçamento.",
             "PERSONAL", "USER", False, 2, (1, 1), 0.05, _sick,
             {"oneoff": [{"kind": "EXPENSE", "amount": 1800, "price_cat": "saude", "label": "Despesa médica inesperada"}],
              "life": {"health": 4, "wellbeing": -3}}),
    EventDef("promocao", "Promoção no trabalho", "Seu desempenho foi reconhecido com um reajuste.",
             "PERSONAL", "USER", True, 2, (12, 24), 0.035, _stable,
             {"income_pct": 12, "life": {"satisfaction": 4, "wellbeing": 3}}),
    EventDef("oportunidade_profissional", "Oportunidade profissional", "Um recrutador oferece uma vaga com maior salário.",
             "PERSONAL", "USER", True, 1, (1, 1), 0.04, _employed,
             options=(
                 Option("aceitar", "Aceitar a vaga", "Salário maior, mas adaptação e risco de a empresa não ser o que parece.",
                        (Outcome(0.65, "A nova empresa se mostrou ótima: salário maior.", {"income_pct": 18}, 12),
                         Outcome(0.35, "A vaga era pior do que parecia: período de adaptação difícil.",
                                 {"income_pct": 5, "life": {"wellbeing": -4}}, 6)), cost=0),
                 Option("recusar", "Recusar", "Mantém a estabilidade atual.", (Outcome(1.0, "Você ficou onde está.", {}, 1),), default=True))),
    EventDef("mudanca_emprego", "Mudança de emprego", "Sua empresa passa por reestruturação e propõe um novo cargo.",
             "PERSONAL", "USER", False, 2, (1, 1), 0.03, lambda m, c: _employed(m, c) * (2.0 if m["unemployment"] > 10 else 0.6),
             options=(
                 Option("aceitar", "Aceitar o novo cargo", "Mantém o emprego; a remuneração pode mudar.",
                        (Outcome(0.5, "O novo cargo paga um pouco menos, mas é estável.", {"income_pct": -6}, 12),
                         Outcome(0.5, "O novo cargo trouxe responsabilidades e um reajuste.", {"income_pct": 8}, 12)), default=True),
                 Option("buscar", "Buscar recolocação", "Arriscado: pode demorar, mas pode render mais.",
                        (Outcome(0.45, "Você se recolocou rápido e ganhando mais.", {"income_pct": 15}, 12),
                         Outcome(0.55, "A busca demorou: meses de renda reduzida.", {"income_pct": -35, "life": {"wellbeing": -5}}, 4)), cost=400))),
    EventDef("acontecimento_familiar", "Acontecimento familiar", "Um familiar próximo precisa de ajuda financeira.",
             "PERSONAL", "USER", False, 1, (1, 1), 0.05, _family,
             options=(
                 Option("ajudar", "Ajudar", "Custa dinheiro, mas fortalece os laços.",
                        (Outcome(1.0, "A ajuda foi bem recebida.", {"life": {"satisfaction": 4, "wellbeing": 2}}, 1),), cost=1500),
                 Option("recusar", "Não poder ajudar agora", "Preserva o caixa.",
                        (Outcome(1.0, "Você explicou a situação; o clima ficou tenso.", {"life": {"satisfaction": -3}}, 1),), default=True))),
    EventDef("demissao", "Demissão", "A empresa em que você trabalha cortou vagas: a renda do salário some por alguns meses.",
             "PERSONAL", "USER", False, 3, (3, 6), 0.012,
             lambda m, c: _employed(m, c) * (4.0 if m["unemployment"] > 11.5 else 2.0 if m["unemployment"] > 9.5 else 0.3),
             {"income_pct": -100, "life": {"wellbeing": -6, "satisfaction": -4}}),
    EventDef("reajuste_aluguel", "Reajuste de aluguel", "O contrato de locação foi renovado com aumento.",
             "PERSONAL", "USER", False, 1, (6, 12), 0.04, _renting,
             {"prices": {"moradia": 0.4}}),
    # ------------------------------------------------------------ empresariais
    EventDef("fornecedor_sobe", "Fornecedor aumenta preços", "Seu principal fornecedor reajusta a tabela.",
             "BUSINESS", "COMPANY", False, 2, (3, 5), 0.07, _has_company, {"supplier_pct": 12}),
    EventDef("equipamento_quebra", "Equipamento quebrou", "Um equipamento essencial precisou de conserto urgente.",
             "BUSINESS", "COMPANY", False, 2, (1, 1), 0.05, _has_company,
             {"company_oneoff": {"amount": 4500, "price_cat": "insumos", "label": "Conserto de equipamento"}}),
    EventDef("concorrente", "Concorrente entra no mercado", "Um novo concorrente abre perto do seu negócio.",
             "BUSINESS", "COMPANY", False, 2, (1, 1), 0.05, _has_company,
             options=(
                 Option("preco", "Baixar os preços", "Segura clientes, mas encolhe a margem.",
                        (Outcome(0.7, "Os clientes ficaram; margem menor.", {"company_demand_pct": -2}, 5),
                         Outcome(0.3, "A guerra de preços não segurou todos os clientes.", {"company_demand_pct": -7}, 5))),
                 Option("marketing", "Investir em divulgação", "Custa agora; pode compensar.",
                        (Outcome(0.55, "A campanha funcionou e fidelizou clientes.", {"company_demand_pct": 3}, 5),
                         Outcome(0.45, "A campanha rendeu pouco.", {"company_demand_pct": -8}, 5)), cost=3000),
                 Option("ignorar", "Ignorar", "Sem custo, sem proteção.",
                        (Outcome(1.0, "O concorrente levou parte da clientela.", {"company_demand_pct": -9}, 5),), default=True))),
    EventDef("demanda_empresa", "Aumento de demanda", "Seu negócio virou assunto na região.",
             "BUSINESS", "COMPANY", True, 2, (2, 4), 0.06, _has_company, {"company_demand_pct": 16}),
    EventDef("perda_clientes", "Perda de clientes", "Reclamações e uma mudança na vizinhança afastam clientes.",
             "BUSINESS", "COMPANY", False, 2, (2, 4), 0.05, _has_company, {"company_demand_pct": -12}),
    EventDef("oportunidade_expansao", "Oportunidade de expansão", "Um ponto comercial excelente ficou disponível.",
             "BUSINESS", "COMPANY", True, 2, (1, 1), 0.04, lambda m, c: 1.0 if c["companies"] and m["confidence"] > 40 else 0.0,
             options=(
                 Option("investir", "Investir na expansão", "Alto potencial, mas incerto.",
                        (Outcome(0.6, "A expansão atraiu mais clientes.", {"company_demand_pct": 20}, 8),
                         Outcome(0.4, "O ponto não rendeu o esperado.", {"company_demand_pct": 2}, 8)), cost=15000),
                 Option("passar", "Deixar passar", "Sem risco.", (Outcome(1.0, "Você deixou a oportunidade passar.", {}, 1),), default=True))),
)
CATALOG_BY_KEY = {e.key: e for e in CATALOG}

PRICE_CATEGORIES = ("alimentacao", "moradia", "energia", "combustiveis", "transporte", "saude", "educacao", "vestuario", "lazer",
                    "servicos", "importados", "insumos", "materiais_construcao", "salarios")
CATEGORY_LABEL = {"alimentacao": "Alimentação", "moradia": "Moradia", "transporte": "Transporte", "saude": "Saúde",
                  "educacao": "Educação", "energia": "Energia", "insumos": "Insumos empresariais", "combustiveis": "Combustíveis",
                  "materiais_construcao": "Materiais de construção", "lazer": "Lazer", "vestuario": "Vestuário",
                  "servicos": "Serviços", "importados": "Produtos importados", "salarios": "Salários (mercado)"}
# sensibilidade de cada categoria à inflação geral e volatilidade própria
BETA = {"alimentacao": (1.3, 1.2), "moradia": (0.9, 0.5), "transporte": (1.0, 0.8), "saude": (1.2, 0.5),
        "educacao": (0.9, 0.3), "energia": (1.1, 1.4), "insumos": (1.0, 1.0), "materiais_construcao": (1.1, 0.9),
        "lazer": (0.8, 0.6), "vestuario": (0.7, 0.6)}
FOOD_SEGMENTS = ("RESTAURANT", "CAFE", "SUPERMARKET")
INITIAL = {"inflation": 4.5, "interest": 10.5, "unemployment": 8.0, "growth": 2.0, "demand": 100.0, "confidence": 55.0}


# ----------------------------------------------------------------------------------------------------------
# Decisões do mês: uma por mês, ANTES do resumo financeiro do fechamento. Financeiras ou pessoais, com resultado incerto.
# cond(macro, ctx) -> 0 impede; > 0 é o peso do sorteio.
def _o(key, label, hint, *outcomes, cost=0, default=False):
    return Option(key, label, hint, tuple(outcomes), cost=cost, default=default)


def _oc(prob, text, effects=None, duration=1):
    return Outcome(prob, text, effects or {}, duration)


def _in(amount, label, price_cat="lazer"):
    return {"kind": "INCOME", "amount": amount, "price_cat": price_cat, "label": label}


def _out(amount, label, price_cat="lazer"):
    return {"kind": "EXPENSE", "amount": amount, "price_cat": price_cat, "label": label}


_has_rel = lambda m, c: 1.0 if c.get("relationships") else 0.0               # noqa: E731
_has_friends = lambda m, c: 1.0 if c.get("friends", 0) > 0 else 0.0                # noqa: E731  — "um amigo te chamou" só com amigos de verdade
_has_salary = lambda m, c: 1.0 if c["salary"] > 0 else 0.0                    # noqa: E731
_always = lambda m, c: 1.0                                                    # noqa: E731

MONTHLY: tuple[EventDef, ...] = (
    # ------------------------------------------------------------ financeiras
    EventDef("d_bonus", "Você recebeu um bônus!", "A empresa pagou um bônus de R$ 1.200. O que fazer com o dinheiro?", "FINANCIAL", "USER", True, 1, (1, 1), 1.0, _has_salary,
             options=(_o("guardar", "Guardar tudo", "Segurança para o futuro.", _oc(1.0, "Você guardou o bônus e ficou mais tranquilo.", {"oneoff": [_in(1200, "Bônus recebido")], "life": {"satisfaction": 1}}), default=True),
                      _o("presente", "Comprar algo especial", "Gasta uma parte, mas traz alegria.", _oc(1.0, "Você se presenteou: valeu a pena!", {"oneoff": [_in(1200, "Bônus recebido"), _out(700, "Presente para você")], "life": {"wellbeing": 4, "satisfaction": 3}})))),
    EventDef("d_aumento", "Pedir um aumento?", "Você sente que está na hora de conversar com o chefe sobre o salário.", "FINANCIAL", "USER", True, 1, (1, 1), 0.8,
             lambda m, c: _has_salary(m, c) * (1.0 if c["months"] >= 6 else 0.0),
             options=(_o("pedir", "Pedir o aumento", "Pode dar certo... ou não.", _oc(0.4, "Seu chefe aprovou: salário maior por um ano!", {"raise_pct": 8, "life": {"satisfaction": 3}}),
                         _oc(0.6, "Dessa vez não deu, mas você mostrou iniciativa.", {"life": {"wellbeing": -2}})),
                      _o("esperar", "Esperar mais um pouco", "Sem risco.", _oc(1.0, "Você decidiu esperar.", {}), default=True))),
    EventDef("d_bico", "Bico de fim de semana", "Um conhecido ofereceu um trabalho extra por R$ 900.", "FINANCIAL", "USER", True, 1, (1, 1), 1.0, _always,
             options=(_o("aceitar", "Aceitar o bico", "Dinheiro a mais, mas cansa.", _oc(0.8, "Deu tudo certo e o dinheiro entrou.", {"oneoff": [_in(900, "Bico de fim de semana")], "life": {"wellbeing": -2}}),
                         _oc(0.2, "O cliente atrasou o pagamento e deu dor de cabeça.", {"oneoff": [_in(450, "Bico (pago pela metade)")], "life": {"wellbeing": -4}})),
                      _o("recusar", "Recusar", "Descanso garantido.", _oc(1.0, "Você descansou no fim de semana.", {"life": {"wellbeing": 2}}), default=True))),
    EventDef("d_eletro", "A geladeira quebrou", "Os alimentos estragaram. Consertar ou trocar?", "FINANCIAL", "USER", False, 1, (1, 1), 0.8, _always,
             options=(_o("consertar", "Consertar", "Mais barato agora, pode quebrar de novo.", _oc(0.7, "O conserto resolveu.", {"oneoff": [_out(450, "Conserto da geladeira", "moradia")]}),
                         _oc(0.3, "Quebrou de novo depois de um tempo.", {"oneoff": [_out(450, "Conserto da geladeira", "moradia"), _out(450, "Novo conserto", "moradia")]})),
                      _o("trocar", "Comprar uma nova", "Mais caro, mas é para durar.", _oc(1.0, "Geladeira nova funcionando.", {"oneoff": [_out(2300, "Geladeira nova", "moradia")], "life": {"satisfaction": 2}}), default=False),
                      _o("reaproveitar", "Esperar e ver", "Pode piorar.", _oc(1.0, "Você ficou sem geladeira por uns dias.", {"oneoff": [_out(900, "Comida perdida e delivery", "alimentacao")], "life": {"wellbeing": -3}}), default=True))),
    EventDef("d_restituicao", "Restituição do imposto de renda", "Chegou uma restituição de R$ 800.", "FINANCIAL", "USER", True, 1, (1, 1), 0.6, _always,
             options=(_o("reserva", "Colocar na reserva", "Boa decisão de longo prazo.", _oc(1.0, "Você reforçou a reserva de emergência.", {"oneoff": [_in(800, "Restituição do IR")], "life": {"satisfaction": 2}}), default=True),
                      _o("passeio", "Fazer um passeio", "Dinheiro curtido hoje.", _oc(1.0, "Passeio ótimo!", {"oneoff": [_in(800, "Restituição do IR"), _out(650, "Passeio")], "life": {"wellbeing": 4}})))),
    EventDef("d_curso_fin", "Curso de finanças pessoais", "Um curso online promete ensinar a controlar melhor o dinheiro (R$ 300).", "FINANCIAL", "USER", True, 1, (1, 1), 0.8, _has_salary,
             options=(_o("fazer", "Fazer o curso", "Investir em conhecimento.", _oc(0.65, "Você aprendeu a negociar e o salário subiu um pouco.", {"income_pct": 3, "life": {"quality": 2}}, 12),
                         _oc(0.35, "O curso foi fraco, mas ensinou algumas coisas.", {"life": {"quality": 1}}), cost=300),
                      _o("pular", "Pular", "Sem custo.", _oc(1.0, "Você deixou o curso passar.", {}), default=True))),
    EventDef("d_amigo_emprestimo", "Amigo pede dinheiro emprestado", "Um amigo pede R$ 500 emprestados para uma emergência.", "FINANCIAL", "USER", False, 1, (1, 1), 0.7, _has_friends,
             options=(_o("emprestar", "Emprestar", "Pode voltar, pode não voltar.", _oc(0.55, "Ele devolveu direitinho!", {"life": {"satisfaction": 2}}),
                         _oc(0.45, "Ele não devolveu o dinheiro.", {"oneoff": [_out(500, "Empréstimo não devolvido")], "life": {"satisfaction": -2}})),
                      _o("negar", "Dizer que não pode", "Preserva o caixa.", _oc(1.0, "O amigo entendeu, mas ficou chateado.", {"life": {"satisfaction": -1}}), default=True))),
    EventDef("d_promocao_mercado", "Liquidação de tecnologia", "Um notebook novo está com 30% de desconto (R$ 3.200).", "FINANCIAL", "USER", True, 1, (1, 1), 0.7, _always,
             options=(_o("comprar", "Comprar", "Ferramenta de trabalho e diversão.", _oc(0.7, "O notebook ajudou muito nos estudos e no trabalho.", {"oneoff": [_out(3200, "Notebook novo")], "life": {"quality": 3, "satisfaction": 2}}),
                         _oc(0.3, "Você mal usou o notebook novo.", {"oneoff": [_out(3200, "Notebook novo")], "life": {"satisfaction": 1}})),
                      _o("passar", "Deixar passar", "Sem gasto.", _oc(1.0, "Você resistiu à promoção.", {}), default=True))),
    EventDef("d_plano_saude", "Plano de saúde mais barato", "Há uma oferta de plano de saúde mais barato, mas com menos cobertura.", "FINANCIAL", "USER", True, 1, (1, 1), 0.6, _always,
             options=(_o("trocar", "Trocar de plano", "Economiza, mas é mais arriscado.", _oc(0.6, "Economia boa e nenhum problema.", {"oneoff": [_in(250, "Economia no plano de saúde", "saude")]}),
                         _oc(0.4, "Precisou de um atendimento fora da cobertura.", {"oneoff": [_out(700, "Atendimento fora da cobertura", "saude")]})),
                      _o("manter", "Manter o plano", "Segurança.", _oc(1.0, "Você manteve o plano.", {}), default=True))),
    EventDef("d_investir_dica", "Dica quente de investimento", "Um colega de trabalho jura que uma aplicação vai dobrar o dinheiro (R$ 1.000).", "FINANCIAL", "USER", False, 1, (1, 1), 0.7, _has_salary,
             options=(_o("entrar", "Entrar com R$ 1.000", "Alto risco: pode perder tudo.", _oc(0.2, "Deu certo! O dinheiro dobrou.", {"oneoff": [_in(1000, "Lucro da aplicação")]}),
                         _oc(0.8, "A promessa era exagerada e você perdeu o dinheiro.", {"oneoff": [_out(1000, "Prejuízo na aplicação")], "life": {"wellbeing": -3}})),
                      _o("ignorar", "Ignorar a dica", "Promessa fácil costuma ser perigosa.", _oc(1.0, "Você ignorou e dormiu tranquilo.", {"life": {"quality": 1}}), default=True))),
    # ------------------------------------------------------------ pessoais
    EventDef("d_checkup", "Hora do check-up", "Já faz tempo que você não vai ao médico (R$ 250).", "PERSONAL", "USER", True, 1, (1, 1), 1.0, _always,
             options=(_o("fazer", "Fazer os exames", "Cuidar da saúde.", _oc(1.0, "Está tudo bem e você descobriu pontos para melhorar.", {"life": {"health": 4}}), cost=250),
                      _o("adiar", "Adiar", "Sem custo, mas arriscado.", _oc(1.0, "Você adiou o check-up.", {"life": {"health": -1}}), default=True))),
    EventDef("d_viagem", "Convite para uma viagem", "Amigos convidam você para um fim de semana na praia (R$ 900).", "PERSONAL", "USER", True, 1, (1, 1), 0.9, _has_friends,
             options=(_o("ir", "Viajar", "Diversão e novas amizades.", _oc(0.8, "Foi incrível!", {"life": {"wellbeing": 5, "satisfaction": 3, "social": 4}}), _oc(0.2, "Choveu o tempo todo, mas foi divertido mesmo assim.", {"life": {"wellbeing": 2, "social": 3}}), cost=900),
                      _o("ficar", "Ficar em casa", "Economiza.", _oc(1.0, "Você ficou em casa.", {"life": {"social": -1}}), default=True))),
    EventDef("d_pet", "Adotar um pet?", "Um cachorrinho precisa de um lar (R$ 600 para começar).", "PERSONAL", "USER", True, 1, (1, 1), 0.6, _always,
             options=(_o("adotar", "Adotar", "Companhia e responsabilidade.", _oc(1.0, "O pet trouxe alegria para a casa!", {"life": {"wellbeing": 5, "health": 1}}, 1), cost=600),
                      _o("nao", "Agora não", "Talvez mais tarde.", _oc(1.0, "Você decidiu esperar.", {}), default=True))),
    EventDef("d_academia", "Matrícula na academia", "Uma academia perto de casa está com matrícula grátis (R$ 120/mês no começo).", "PERSONAL", "USER", True, 1, (1, 1), 0.8, _always,
             options=(_o("matricular", "Matricular-se", "Mais saúde, se você for mesmo.", _oc(0.6, "Você foi com frequência e se sente ótimo.", {"life": {"health": 4, "wellbeing": 2}}), _oc(0.4, "Foi só nas primeiras semanas.", {"life": {"health": 1}}), cost=120),
                      _o("nao", "Deixar para lá", "Sem custo.", _oc(1.0, "Você ficou sem academia.", {}), default=True))),
    EventDef("d_turma", "Reunir a turma", "Que tal chamar as pessoas que você conhece para um encontro (R$ 150)?", "PERSONAL", "USER", True, 1, (1, 1), 1.0, _has_friends,
             options=(_o("chamar", "Organizar o encontro", "Fortalece os laços.", _oc(0.85, "Todos vieram e foi ótimo!", {"relationship_affinity": 4, "life": {"social": 4, "wellbeing": 2}}), _oc(0.15, "Poucos puderam ir.", {"relationship_affinity": 1, "life": {"social": 1}}), cost=150),
                      _o("nao", "Deixar quieto", "As relações esfriam sem contato.", _oc(1.0, "Passou o mês sem encontro.", {"relationship_affinity": -1}), default=True))),
    EventDef("d_casamento_amigo", "Casamento de um amigo", "Você foi convidado para o casamento de um amigo querido (R$ 400 entre roupa e presente).", "PERSONAL", "USER", True, 1, (1, 1), 0.7, _has_friends,
             options=(_o("ir", "Ir à festa", "Um dia especial.", _oc(1.0, "Festa linda, você reviu muita gente.", {"life": {"social": 4, "wellbeing": 3}}), cost=400),
                      _o("nao", "Mandar um abraço", "Economiza.", _oc(1.0, "Seu amigo entendeu.", {"life": {"social": -1}}), default=True))),
    EventDef("d_descanso", "Um mês puxado", "O trabalho tem estado pesado. Tirar uns dias de descanso?", "PERSONAL", "USER", True, 1, (1, 1), 0.8,
             lambda m, c: 1.0 if c.get("work_level") != "REDUCED" else 0.2,
             options=(_o("descansar", "Descansar", "Recarregar as energias.", _oc(1.0, "Você voltou renovado.", {"life": {"wellbeing": 5, "health": 2}}), cost=200),
                      _o("seguir", "Seguir trabalhando", "Mais produtivo hoje, mais cansado depois.", _oc(0.5, "Aguentou firme.", {}), _oc(0.5, "O cansaço pesou.", {"life": {"wellbeing": -4, "health": -2}}), default=True))),
    EventDef("d_festa_surpresa", "Festa surpresa", "Amigos querem fazer uma festa de aniversário para você. Aceitar a ajuda ou preferir algo simples?", "PERSONAL", "USER", True, 1, (1, 1), 0.7, _has_friends,
             options=(_o("festa", "Fazer a festa", "Mais alegria e mais gasto.", _oc(1.0, "A festa foi inesquecível!", {"life": {"social": 5, "wellbeing": 4, "satisfaction": 3}}), cost=350),
                      _o("simples", "Algo simples em casa", "Barato e acolhedor.", _oc(1.0, "Um jantar tranquilo foi suficiente.", {"life": {"wellbeing": 2}}), default=True))),
    EventDef("d_voluntariado", "Convite para ser voluntário", "Uma ONG da sua cidade precisa de ajuda no próximo mês.", "PERSONAL", "USER", True, 1, (1, 1), 0.7, _always,
             options=(_o("aceitar", "Ajudar", "Faz bem para você e para os outros.", _oc(1.0, "Você se sentiu muito realizado e conheceu gente nova.", {"life": {"satisfaction": 4, "social": 3, "wellbeing": 3}})),
                      _o("recusar", "Dessa vez não", "Falta de tempo.", _oc(1.0, "Você não pôde ajudar agora.", {}), default=True))),
)
_has_employees = lambda m, c: 1.0 if any(v > 0 for v in c.get("co_employees", {}).values()) else 0.0     # noqa: E731
_has_partners = lambda m, c: 1.0 if any(v > 0 for v in c.get("co_partners", {}).values()) else 0.0       # noqa: E731
_has_vehicle = lambda m, c: 1.0 if c.get("has_vehicle") else 0.0                                        # noqa: E731
_has_rented = lambda m, c: 1.0 if c.get("has_rented") else 0.0                                          # noqa: E731

MONTHLY = MONTHLY + (
    # ------------------------------------------------------------ processos jurídicos nas decisões do mês
    EventDef("d_multa", "Multa de trânsito", "Você recebeu uma multa de R$ 195 (R$ 130 se pagar logo). Pagar ou recorrer?", "FINANCIAL", "USER", False, 1, (1, 1), 0.9, _has_vehicle,
             options=(_o("pagar", "Pagar com desconto", "Resolve na hora.", _oc(1.0, "Multa paga com desconto.", {"oneoff": [_out(130, "Multa de trânsito", "transporte")]}), default=True),
                      _o("recorrer", "Recorrer (com advogado)", "O advogado custa R$ 400 e o resultado é incerto.",
                         _oc(0.4, "O recurso foi aceito: a multa foi cancelada.", {"oneoff": [_out(400, "Advogado (recurso de multa)", "transporte")]}),
                         _oc(0.6, "O recurso foi negado: você pagou a multa e o advogado.", {"oneoff": [_out(400, "Advogado (recurso de multa)", "transporte"), _out(195, "Multa de trânsito", "transporte")], "life": {"wellbeing": -2}})))),
    EventDef("d_inquilino", "Inquilino atrasou o aluguel", "O inquilino de um dos seus imóveis está com o aluguel atrasado. Negociar ou entrar na justiça?", "FINANCIAL", "USER", False, 1, (1, 1), 1.2, _has_rented,
             options=(_o("negociar", "Negociar um parcelamento", "Perde parte do valor, evita briga.", _oc(1.0, "Vocês chegaram a um acordo e você perdoou parte da dívida.", {"oneoff": [_out(600, "Aluguel perdoado", "moradia")]}), default=True),
                      _o("processar", "Entrar com ação de despejo", "Advogado de R$ 1.200; pode demorar e dar errado.",
                         _oc(0.65, "A justiça decidiu a seu favor e o inquilino quitou o atraso.", {"oneoff": [_out(1200, "Advogado (ação de despejo)", "moradia"), _in(1500, "Aluguéis atrasados recebidos")]}),
                         _oc(0.35, "O processo se arrastou e o inquilino não pagou.", {"oneoff": [_out(1200, "Advogado (ação de despejo)", "moradia")], "life": {"wellbeing": -3}})))),
    EventDef("d_acidente", "Batida leve no trânsito", "Você bateu de leve no carro de outra pessoa. Acordo amigável ou acionar o seguro?", "PERSONAL", "USER", False, 1, (1, 1), 0.8, _has_vehicle,
             options=(_o("acordo", "Acordo amigável", "Você paga o conserto dele(a).", _oc(1.0, "Vocês resolveram na hora.", {"oneoff": [_out(900, "Conserto no acordo amigável", "transporte")]}), default=True),
                      _o("seguro", "Acionar o seguro", "Franquia de R$ 700; a outra parte pode ir à justiça.",
                         _oc(0.6, "O seguro cobriu tudo.", {"oneoff": [_out(700, "Franquia do seguro", "transporte")]}),
                         _oc(0.4, "A outra parte processou e você teve gastos extras.", {"oneoff": [_out(700, "Franquia do seguro", "transporte"), _out(1500, "Custas e indenização", "transporte")], "life": {"wellbeing": -4}})))),
    EventDef("d_vizinho", "Vizinho ameaça processar", "Um vizinho reclama do barulho de uma reforma e ameaça ir à justiça.", "PERSONAL", "USER", False, 1, (1, 1), 0.7, _always,
             options=(_o("acordo", "Fazer um acordo", "Paga uma compensação e encerra.", _oc(1.0, "Você fez as pazes com o vizinho.", {"oneoff": [_out(500, "Acordo com o vizinho", "moradia")]}), default=True),
                      _o("enfrentar", "Enfrentar na justiça", "Advogado de R$ 500; pode ganhar ou perder.",
                         _oc(0.5, "A justiça deu razão a você.", {"oneoff": [_out(500, "Advogado", "moradia")]}),
                         _oc(0.5, "Você perdeu e teve que indenizar.", {"oneoff": [_out(500, "Advogado", "moradia"), _out(1800, "Indenização ao vizinho", "moradia")], "life": {"wellbeing": -3}})))),
)
MONTHLY_BY_KEY = {e.key: e for e in MONTHLY}
CATALOG_BY_KEY.update(MONTHLY_BY_KEY)


# ----------------------------------------------------------------------------------------------------------
# Conhecer gente nova através das decisões: efeito {"meet": {"prob", "where", "interest"}} aplicado aos resultados da opção indicada
import dataclasses as _dc

_MEET = {  # decisão: (opção, probabilidade, onde, interesse, resultados afetados (None = todos))
    "d_viagem": ("ir", 0.55, "durante a viagem", "viagens", None), "d_casamento_amigo": ("ir", 0.65, "no casamento do seu amigo", "música", None),
    "d_academia": ("matricular", 0.50, "na academia", "esporte", None), "d_voluntariado": ("aceitar", 0.75, "no trabalho voluntário", "causas", None),
    "d_curso_fin": ("fazer", 0.35, "no curso de finanças", "finanças", None), "d_festa_surpresa": ("festa", 0.55, "na sua festa de aniversário", None, None),
    "d_bico": ("aceitar", 0.20, "no bico de fim de semana", None, (0,)), "d_pet": ("adotar", 0.45, "passeando com o pet", "animais", None),
    "d_turma": ("chamar", 0.40, "no encontro (um amigo levou alguém)", None, (0,)),
}


def _with_meet(d: EventDef) -> EventDef:
    spec = _MEET.get(d.key)
    if spec is None:
        return d
    opt_key, prob, where, interest, which = spec
    opts = []
    for o in d.options:
        if o.key == opt_key:
            outs = tuple(_dc.replace(x, effects={**x.effects, "meet": {"prob": prob, "where": where, "interest": interest}}) if (which is None or i in which) else x
                         for i, x in enumerate(o.outcomes))
            o = _dc.replace(o, outcomes=outs)
        opts.append(o)
    return _dc.replace(d, options=tuple(opts))


# ------------------------------------------------------------ trabalho e decisões com várias escolhas (3 ou 4 opções)
_has_job = lambda m, c: 1.0 if c["salary"] > 0 and c["months"] >= 3 else 0.0       # noqa: E731
MONTHLY = MONTHLY + (
    EventDef("d_trab_projeto", "Projeto importante na empresa", "Sua equipe precisa entregar um projeto grande. O que você faz?", "FINANCIAL", "USER", True, 1, (1, 1), 1.0, _has_job,
             options=(_o("extra", "Assumir e fazer hora extra", "Cansa, mas a chefia nota.", _oc(0.4, "A entrega foi um sucesso e você foi reconhecido(a): aumento!", {"merit": 20, "raise_pct": 6, "life": {"health": -1, "wellbeing": -1, "satisfaction": 3}}),
                                                          _oc(0.6, "Você se esforçou muito e a diretoria percebeu.", {"merit": 20, "life": {"health": -1, "wellbeing": -2}})),
                      _o("combinado", "Fazer só o combinado", "Sem sobrecarga.", _oc(1.0, "Você cumpriu o que foi pedido.", {"merit": 3})),
                      _o("melhoria", "Propor um jeito de economizar para a empresa", "Exige pensar fora da caixa.", _oc(0.35, "A ideia economizou muito dinheiro para a empresa e rendeu um aumento!", {"merit": 14, "raise_pct": 5, "life": {"satisfaction": 3}}),
                         _oc(0.65, "A ideia foi elogiada e anotada.", {"merit": 12, "life": {"satisfaction": 1}})),
                      _o("recusar", "Dizer que não dá", "Preserva o seu tempo.", _oc(1.0, "A chefia ficou desapontada.", {"merit": -6, "life": {"wellbeing": 1}}), default=True))),
    EventDef("d_trab_cliente", "Cliente difícil", "Um cliente importante está insatisfeito e ameaça cancelar o contrato com a empresa.", "FINANCIAL", "USER", False, 1, (1, 1), 0.9, _has_job,
             options=(_o("resolver", "Ficar até resolver o problema", "Desgasta, mas salva o cliente.", _oc(0.6, "O cliente ficou e a empresa agradeceu muito.", {"merit": 18, "life": {"wellbeing": -1, "satisfaction": 2}}),
                         _oc(0.4, "Mesmo com esforço, o cliente saiu. Mas viram sua dedicação.", {"merit": 9, "life": {"wellbeing": -2}})),
                      _o("equipe", "Chamar a equipe para dividir o problema", "Mais seguro e divide o mérito.", _oc(1.0, "Em equipe, o problema foi resolvido.", {"merit": 8, "life": {"satisfaction": 1}})),
                      _o("passar", "Passar o caso para o chefe", "Sem risco para você.", _oc(1.0, "O chefe resolveu, mas notou a sua omissão.", {"merit": -4}), default=True))),
    EventDef("d_trab_proposta", "Outra empresa quer contratar você", "Um recrutador ofereceu uma vaga parecida na concorrência, pagando mais.", "FINANCIAL", "USER", True, 1, (1, 1), 0.6,
             lambda m, c: _has_job(m, c) * (1.0 if c["months"] >= 8 else 0.0),
             options=(_o("negociar", "Usar a proposta para negociar um aumento", "Arriscado: o chefe pode se irritar.", _oc(0.4, "Para não perder você, a empresa cobriu a oferta!", {"raise_pct": 10, "merit": 4, "life": {"satisfaction": 3}}),
                         _oc(0.35, "O chefe não gostou da chantagem.", {"merit": -12, "life": {"wellbeing": -2}}), _oc(0.25, "Nada mudou, mas ficou combinado conversar depois.", {})),
                      _o("agradecer", "Agradecer e ficar onde está", "Lealdade vale pontos.", _oc(1.0, "A chefia soube da sua lealdade.", {"merit": 6, "life": {"satisfaction": 1}}), default=True),
                      _o("conversar", "Pedir mais responsabilidades à empresa", "Mostra ambição sem ameaçar.", _oc(0.5, "Você ganhou um cargo maior e um aumento!", {"raise_pct": 7, "merit": 8, "life": {"satisfaction": 3}}),
                         _oc(0.5, "Você ganhou novas tarefas, por enquanto sem reajuste.", {"merit": 10, "life": {"wellbeing": -1}})))),
    EventDef("d_fim_de_semana", "Como usar o seu fim de semana?", "Você tem um fim de semana livre pela frente.", "PERSONAL", "USER", True, 1, (1, 1), 1.0, _always,
             options=(_o("descansar", "Descansar em casa", "Recupera as energias.", _oc(1.0, "Você descansou e voltou renovado(a).", {"life": {"health": 2, "wellbeing": 3}}), default=True),
                      _o("passear", "Passear com quem você gosta (R$ 200)", "Diversão e convivência.", _oc(1.0, "O passeio foi ótimo.", {"oneoff": [_out(200, "Passeio de fim de semana")], "life": {"satisfaction": 3, "social": 2}}), cost=200),
                      _o("estudar", "Estudar algo novo", "Investe em você.", _oc(1.0, "Você aprendeu bastante.", {"life": {"quality": 2, "wellbeing": -1}, "merit": 3})),
                      _o("bico", "Fazer um bico (R$ 300)", "Dinheiro extra, menos descanso.", _oc(1.0, "O bico rendeu um dinheirinho.", {"oneoff": [_in(300, "Bico de fim de semana", "outros")], "life": {"wellbeing": -2}})))),
    EventDef("d_dinheiro_sobrando", "Sobrou um dinheiro", "No fim do mês sobraram R$ 1.500. O que fazer?", "FINANCIAL", "USER", True, 1, (1, 1), 0.9, _has_salary,
             options=(_o("reserva", "Reforçar a reserva de emergência", "Mais segurança.", _oc(1.0, "Você ficou mais tranquilo(a) com a reserva maior.", {"life": {"satisfaction": 2}}), default=True),
                      _o("curso", "Pagar um curso (R$ 600)", "Investe na carreira.", _oc(1.0, "O curso abriu portas no trabalho.", {"oneoff": [_out(600, "Curso de aperfeiçoamento", "educacao")], "life": {"quality": 2}, "merit": 6}), cost=600),
                      _o("viagem", "Fazer uma viagem (R$ 1.200)", "Memórias e descanso.", _oc(1.0, "A viagem foi inesquecível!", {"oneoff": [_out(1200, "Viagem")], "life": {"satisfaction": 4, "wellbeing": 3}}), cost=1200),
                      _o("dividas", "Antecipar o pagamento de dívidas", "Menos juros no futuro.", _oc(1.0, "Você se sentiu mais leve sem tantas parcelas.", {"life": {"satisfaction": 2, "wellbeing": 1}})))),
)

MONTHLY = tuple(_with_meet(d) for d in MONTHLY)
MONTHLY_BY_KEY = {e.key: e for e in MONTHLY}
CATALOG_BY_KEY.update(MONTHLY_BY_KEY)
