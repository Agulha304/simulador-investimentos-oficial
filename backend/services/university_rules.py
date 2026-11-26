"""Faculdades reais do Brasil como opções de graduação.

Fontes da pesquisa (RUF 2025 da Folha, QS e páginas oficiais): USP lidera o RUF 2025, seguida de Unicamp, UFRGS, UFMG, UFRJ, Unesp, UFSC, UnB,
UFPR e UFSCar (top 10); PUCRS é a 1ª privada do ranking geral (22ª); Mackenzie é a melhor privada de SP; PUC-SP é a melhor privada em
qualidade de ensino; ITA e IME dominam engenharia e computação; FGV e Insper são referências em negócios (mensalidade do Insper Economia:
R$ 8.300; FGV-SP Direito ~R$ 8.000; Medicina em particular, média ~R$ 12.700).

Cada faculdade tem:
  * `courses`: só as ÁREAS (chaves de `career_rules.FIELDS`) que ela oferece na vida real;
  * `weight`: peso no currículo e no prêmio salarial (relevância e carga horária reais); a faculdade "aberta" (qualquer particular) vale 1,0;
  * `demand`: concorrência (0 a 1): quanto maior, menor a chance de passar no vestibular; faculdades abertas aceitam todos;
  * `fee`: mensalidade em R$ (0 nas públicas; só custos de material e transporte, `extra`);
  * `load`: fator da carga horária (1,0 = padrão do curso; ITA/IME/USP exigem mais) sobre as horas livres que o curso consome.
Os números de ranking e mensalidade são aproximados e servem ao jogo; os dados de cursos oferecidos seguem o catálogo real de cada instituição.
"""
from dataclasses import dataclass, field
from decimal import Decimal

D = Decimal
OPEN_KEY = "aberta"


@dataclass(frozen=True)
class University:
    key: str
    name: str
    short: str
    state: str
    kind: str                       # PUBLICA | PRIVADA
    ranking: int                    # posição aproximada no RUF/QS entre as listadas (1 = melhor)
    weight: float
    demand: float
    fee: int
    extra: int                      # material, transporte e alimentação mensais nas públicas
    load: float
    courses: tuple[str, ...]
    months: dict = field(default_factory=dict)       # duração específica por área (meses)
    fees: dict = field(default_factory=dict)         # mensalidade específica por área (R$)


ALL = ("tecnologia", "saude", "engenharia", "financas", "direito", "educacao", "comercio", "artes", "agro", "gastronomia", "logistica", "seguranca",
       "industria", "ciencia")

UNIVERSITIES: dict[str, University] = {u.key: u for u in [
    University("usp", "Universidade de São Paulo (USP)", "USP", "SP", "PUBLICA", 1, 1.35, 0.93, 0, 450, 1.15,
               ("tecnologia", "saude", "engenharia", "financas", "direito", "educacao", "artes", "agro", "industria", "ciencia", "seguranca", "comercio"),
               months={"saude": 72, "engenharia": 60, "direito": 60}),
    University("unicamp", "Universidade Estadual de Campinas (Unicamp)", "Unicamp", "SP", "PUBLICA", 2, 1.32, 0.91, 0, 450, 1.15,
               ("tecnologia", "saude", "engenharia", "financas", "educacao", "artes", "agro", "industria", "ciencia"), months={"saude": 72}),
    University("ufrgs", "Universidade Federal do Rio Grande do Sul (UFRGS)", "UFRGS", "RS", "PUBLICA", 3, 1.25, 0.82, 0, 380, 1.10,
               ("tecnologia", "saude", "engenharia", "financas", "direito", "educacao", "artes", "agro", "industria", "ciencia", "seguranca"), months={"saude": 72}),
    University("ufmg", "Universidade Federal de Minas Gerais (UFMG)", "UFMG", "MG", "PUBLICA", 4, 1.25, 0.82, 0, 380, 1.10,
               ("tecnologia", "saude", "engenharia", "financas", "direito", "educacao", "artes", "agro", "industria", "ciencia", "logistica"), months={"saude": 72}),
    University("ufrj", "Universidade Federal do Rio de Janeiro (UFRJ)", "UFRJ", "RJ", "PUBLICA", 5, 1.22, 0.80, 0, 420, 1.10,
               ("tecnologia", "saude", "engenharia", "financas", "direito", "educacao", "artes", "industria", "ciencia"), months={"saude": 72}),
    University("unesp", "Universidade Estadual Paulista (Unesp)", "Unesp", "SP", "PUBLICA", 6, 1.18, 0.75, 0, 350, 1.05,
               ("tecnologia", "saude", "engenharia", "direito", "educacao", "artes", "agro", "ciencia", "comercio"), months={"saude": 72}),
    University("ufsc", "Universidade Federal de Santa Catarina (UFSC)", "UFSC", "SC", "PUBLICA", 7, 1.15, 0.74, 0, 380, 1.05,
               ("tecnologia", "saude", "engenharia", "financas", "direito", "educacao", "artes", "agro", "industria", "ciencia", "gastronomia"), months={"saude": 72}),
    University("unb", "Universidade de Brasília (UnB)", "UnB", "DF", "PUBLICA", 8, 1.12, 0.72, 0, 350, 1.05,
               ("tecnologia", "saude", "engenharia", "financas", "direito", "educacao", "artes", "agro", "ciencia", "seguranca"), months={"saude": 72}),
    University("ufpr", "Universidade Federal do Paraná (UFPR)", "UFPR", "PR", "PUBLICA", 9, 1.10, 0.70, 0, 350, 1.05,
               ("tecnologia", "saude", "engenharia", "financas", "direito", "educacao", "artes", "agro", "ciencia", "logistica"), months={"saude": 72}),
    University("ufscar", "Universidade Federal de São Carlos (UFSCar)", "UFSCar", "SP", "PUBLICA", 10, 1.10, 0.68, 0, 330, 1.05,
               ("tecnologia", "saude", "engenharia", "educacao", "agro", "industria", "ciencia")),
    University("ufpe", "Universidade Federal de Pernambuco (UFPE)", "UFPE", "PE", "PUBLICA", 11, 1.02, 0.66, 0, 320, 1.0,
               ("tecnologia", "saude", "engenharia", "financas", "direito", "educacao", "artes", "ciencia"), months={"saude": 72}),
    University("ufc", "Universidade Federal do Ceará (UFC)", "UFC", "CE", "PUBLICA", 12, 1.00, 0.64, 0, 320, 1.0,
               ("tecnologia", "saude", "engenharia", "financas", "direito", "educacao", "artes", "agro", "ciencia"), months={"saude": 72}),
    University("ita", "Instituto Tecnológico de Aeronáutica (ITA)", "ITA", "SP", "PUBLICA", 2, 1.45, 0.99, 0, 500, 1.30,
               ("engenharia", "tecnologia", "industria"), months={"engenharia": 60, "tecnologia": 60, "industria": 60}),
    University("ime", "Instituto Militar de Engenharia (IME)", "IME", "RJ", "PUBLICA", 3, 1.38, 0.97, 0, 500, 1.25,
               ("engenharia", "tecnologia", "industria", "ciencia"), months={"engenharia": 60, "tecnologia": 60}),
    University("fgv", "Fundação Getulio Vargas (FGV)", "FGV", "SP", "PRIVADA", 5, 1.30, 0.90, 7900, 0, 1.05,
               ("financas", "direito", "tecnologia", "comercio"), fees={"direito": 8000, "financas": 7900, "tecnologia": 7600, "comercio": 7200}),
    University("insper", "Insper", "Insper", "SP", "PRIVADA", 6, 1.25, 0.88, 8300, 0, 1.05,
               ("financas", "direito", "engenharia", "tecnologia"), fees={"financas": 8300, "direito": 7800, "engenharia": 9600, "tecnologia": 8800}),
    University("puc-rio", "Pontifícia Universidade Católica do Rio de Janeiro (PUC-Rio)", "PUC-Rio", "RJ", "PRIVADA", 8, 1.18, 0.78, 5600, 0, 1.05,
               ("tecnologia", "engenharia", "financas", "direito", "artes", "educacao", "industria", "ciencia"), months={"engenharia": 60},
               fees={"engenharia": 6600, "direito": 5900}),
    University("pucrs", "Pontifícia Universidade Católica do Rio Grande do Sul (PUCRS)", "PUCRS", "RS", "PRIVADA", 7, 1.12, 0.70, 4800, 0, 1.05,
               ("tecnologia", "saude", "engenharia", "financas", "direito", "educacao", "artes", "comercio", "gastronomia", "ciencia"),
               months={"saude": 72}, fees={"saude": 11800}),
    University("puc-sp", "Pontifícia Universidade Católica de São Paulo (PUC-SP)", "PUC-SP", "SP", "PRIVADA", 9, 1.10, 0.68, 4600, 0, 1.0,
               ("direito", "educacao", "artes", "financas", "tecnologia", "saude", "ciencia", "seguranca"), months={"saude": 72}, fees={"saude": 11000}),
    University("mackenzie", "Universidade Presbiteriana Mackenzie", "Mackenzie", "SP", "PRIVADA", 10, 1.08, 0.60, 3900, 0, 1.0,
               ("tecnologia", "engenharia", "direito", "financas", "artes", "educacao", "comercio", "saude", "gastronomia", "logistica"),
               months={"saude": 72}, fees={"saude": 10500}),
    University(OPEN_KEY, "Faculdade particular (vestibular aberto)", "Particular", "—", "PRIVADA", 99, 1.0, 0.0, 0, 0, 1.0, ALL),
]}
DEFAULT_PRIVATE_FEE_FACTOR = 1.0     # a faculdade aberta usa o custo da área (`career_rules.FIELDS[...]["cost"]`)
REAPPLY_MONTHS = 12                  # o vestibular é anual: depois de reprovado, só tenta de novo daqui a 12 meses
BASE_PREP = 30.0                     # "preparo" mínimo (0 a 100) de quem nunca estudou/trabalhou: entra na conta da aprovação


def get(key: str) -> University:
    try:
        return UNIVERSITIES[key]
    except KeyError:
        raise ValueError("faculdade desconhecida") from None


def offers_field(uni: University, field_key: str) -> bool:
    return field_key in uni.courses


def months_for(uni: University, field_key: str, default: int) -> int:
    return int(uni.months.get(field_key, default))


def monthly_cost(uni: University, field_key: str, default_cost: int) -> int:
    if uni.key == OPEN_KEY:
        return int(default_cost)
    if uni.kind == "PUBLICA":
        return uni.extra
    return int(uni.fees.get(field_key, uni.fee))


def admission_chance(uni: University, prep: float) -> float:
    """Chance de passar (0 a 1): cai com a concorrência e sobe com o preparo (currículo geral, 0 a 100). Faculdade aberta: 1."""
    if uni.demand <= 0:
        return 1.0
    return round(max(0.03, min(0.95, 0.97 - 0.95 * uni.demand + 0.004 * (prep - BASE_PREP) * (1 - 0.3 * uni.demand))), 3)


def points_for(uni: University, base: int) -> int:
    """Pontos de currículo do diploma (padrão 35 x peso da faculdade)."""
    return int(round(base * uni.weight))


def premium_factor(uni: University) -> float:
    """Multiplicador do prêmio salarial da formação (peso da faculdade, limitado para não distorcer a economia)."""
    return 1 + (uni.weight - 1.0) * 0.8


def catalog_for(field_key: str) -> list[University]:
    return sorted((u for u in UNIVERSITIES.values() if offers_field(u, field_key)), key=lambda u: (u.key == OPEN_KEY, u.ranking))
