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
