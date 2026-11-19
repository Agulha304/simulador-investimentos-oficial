"""Regras (dados) da vida pessoal: níveis de estilo de vida, atividades, personagens e custos dos filhos.

Tudo aqui é configuração: novos personagens, atividades ou faixas etárias entram sem mexer no serviço.
Valores monetários são de referência (índice de preços = 1) e são corrigidos pelo `pricing` do mês.
"""
import hashlib
from decimal import Decimal

D = Decimal


def hash01(*parts) -> float:
    """Sorteio determinístico em [0,1) a partir dos argumentos (reproduzível entre execuções)."""
    h = hashlib.sha256("|".join(str(p) for p in parts).encode()).digest()
    return int.from_bytes(h[:8], "big") / 2**64


def pick(seq, *parts):
    return seq[int(hash01(*parts) * len(seq)) % len(seq)]


# ---------------------------------------------------------------- níveis de estilo de vida
# horas livres por mês conforme a jornada
FREE_HOURS = {"REDUCED": 140, "NORMAL": 100, "INTENSE": 60}
# efeito mensal nos atributos: (saúde, bem-estar, qualidade, satisfação); renda: multiplicador sobre o planejado
LEVELS = {
    "work_level": {
        "REDUCED": dict(health=+1, wellbeing=+1, quality=0, satisfaction=0, income_pct=-15),
        "NORMAL": dict(health=0, wellbeing=0, quality=0, satisfaction=0, income_pct=0),
        "INTENSE": dict(health=-1, wellbeing=-2, quality=-1, satisfaction=+1, income_pct=+20),
    },
    "food_level": {
        "BASIC": dict(health=-1, wellbeing=0, quality=-1, satisfaction=0, extra=0),
        "NORMAL": dict(health=0, wellbeing=0, quality=0, satisfaction=0, extra=0),
        "PREMIUM": dict(health=+1, wellbeing=+1, quality=+1, satisfaction=0, extra=600),
    },
    "health_level": {
        "NONE": dict(health=-2, wellbeing=0, quality=0, satisfaction=0, extra=0),
        "BASIC": dict(health=0, wellbeing=0, quality=0, satisfaction=0, extra=120),
        "PLUS": dict(health=+2, wellbeing=+1, quality=+1, satisfaction=0, extra=450),
    },
    "leisure_level": {
        "LOW": dict(health=0, wellbeing=-1, quality=-1, satisfaction=-1, extra=0),
        "NORMAL": dict(health=0, wellbeing=0, quality=0, satisfaction=0, extra=200),
        "HIGH": dict(health=0, wellbeing=+2, quality=+1, satisfaction=+1, extra=650),
    },
    "family_time": {
        "LOW": dict(health=0, wellbeing=-1, quality=0, satisfaction=-1, extra=0),
        "NORMAL": dict(health=0, wellbeing=0, quality=0, satisfaction=0, extra=0),
        "HIGH": dict(health=0, wellbeing=+1, quality=0, satisfaction=+2, extra=0),
    },
}
# "extra" abaixo do nível-base já está no orçamento do usuário: só cobramos o que passa dele.
BASELINE_EXTRA = {"food_level": 0, "health_level": 120, "leisure_level": 200}
FAMILY_TIME_HOURS = {"LOW": 0, "NORMAL": 20, "HIGH": 45}

HOUSING_KINDS = ("EXISTING", "RENT", "SHARED", "FAMILY_HOME")

# ---------------------------------------------------------------- atividades
# cost: R$ de referência; hours: horas livres; effects: atributos; meets: chance base de conhecer alguém
ACTIVITIES = {
    "park_walk": dict(label="Caminhada no parque", cost=0, hours=8, social=+1, health=+1, wellbeing=+1, meets=0.15, interest="esporte"),
    "volunteer": dict(label="Voluntariado", cost=0, hours=12, social=+2, wellbeing=+2, meets=0.30, interest="causas"),
    "community_event": dict(label="Evento comunitário", cost=0, hours=10, social=+2, wellbeing=+1, meets=0.30, interest="cultura"),
    "course": dict(label="Curso/oficina", cost=250, hours=16, social=+1, wellbeing=+1, quality=+1, meets=0.25, interest="estudos"),
    "gym_class": dict(label="Aula coletiva na academia", cost=90, hours=10, social=+1, health=+2, meets=0.20, interest="esporte"),
    "restaurant": dict(label="Jantar fora", cost=180, hours=6, social=+1, wellbeing=+2, satisfaction=+1, meets=0.12, interest="gastronomia"),
    "party": dict(label="Festa/balada", cost=220, hours=8, social=+3, wellbeing=+1, health=-1, meets=0.35, interest="música"),
    "trip": dict(label="Viagem de fim de semana", cost=1400, hours=30, social=+2, wellbeing=+4, quality=+2, satisfaction=+3, meets=0.18, interest="viagens"),
}
# interações com uma pessoa já conhecida
INTERACTIONS = {
    "chat": dict(label="Conversar", cost=0, hours=4, gain=3),
    "walk": dict(label="Passeio gratuito", cost=0, hours=8, gain=4),
    "cook": dict(label="Cozinhar juntos", cost=40, hours=6, gain=5),
    "outing": dict(label="Programa a dois", cost=160, hours=8, gain=5),
    "trip": dict(label="Viagem a dois", cost=1500, hours=30, gain=8),
}

STAGES = ("ACQUAINTANCE", "FRIEND", "DATING", "COHABITING", "MARRIED", "ENDED")
PARTNER_STAGES = ("DATING", "COHABITING", "MARRIED")
HOUSEHOLD_STAGES = ("COHABITING", "MARRIED")

# ---------------------------------------------------------------- personagens
FIRST_NAMES = ["Ana", "Bruno", "Carla", "Diego", "Elisa", "Fábio", "Gabriela", "Hugo", "Isabela", "João", "Karina", "Lucas",
               "Mariana", "Nelson", "Olívia", "Paulo", "Rafaela", "Sérgio", "Tatiana", "Vitor", "Yara", "Caio", "Débora", "Enzo"]
CHILD_NAMES = ["Alice", "Miguel", "Helena", "Arthur", "Laura", "Theo", "Valentina", "Davi", "Sofia", "Lorenzo", "Cecília", "Gael"]
PERSONALITIES = ["extrovertido", "reservado", "aventureiro", "caseiro", "ambicioso", "tranquilo", "criativo", "metódico"]
# afinidade entre personalidades (0..1), simétrica; omitido = 0.5
PERSONALITY_AFFINITY = {
    ("extrovertido", "reservado"): 0.7, ("extrovertido", "extrovertido"): 0.6, ("aventureiro", "caseiro"): 0.35,
    ("aventureiro", "aventureiro"): 0.8, ("caseiro", "caseiro"): 0.8, ("ambicioso", "tranquilo"): 0.65,
    ("ambicioso", "ambicioso"): 0.45, ("criativo", "metódico"): 0.7, ("reservado", "reservado"): 0.6,
    ("tranquilo", "tranquilo"): 0.75, ("metódico", "metódico"): 0.7, ("aventureiro", "metódico"): 0.4,
}
INTERESTS = ["esporte", "música", "viagens", "gastronomia", "estudos", "cultura", "causas", "tecnologia", "natureza", "jogos"]
OCCUPATIONS = [("Professor(a)", 4200), ("Enfermeiro(a)", 5200), ("Designer", 5800), ("Analista", 7200), ("Autônomo(a)", 3500),
               ("Engenheiro(a)", 11000), ("Cozinheiro(a)", 3200), ("Médico(a)", 18000), ("Estudante e estagiário(a)", 1600),
               ("Comerciante", 6500), ("Motorista de aplicativo", 3800), ("Contador(a)", 8200)]


def person_affinity(a: str, b: str) -> float:
    return PERSONALITY_AFFINITY.get((a, b), PERSONALITY_AFFINITY.get((b, a), 0.5))


# ---------------------------------------------------------------- filhos
# faixas etárias (anos): custos mensais de referência por linha → (categoria do orçamento, categoria de preço)
LINE_CATEGORY = {
    "food": ("Alimentação", "alimentacao"), "health": ("Saúde", "saude"), "education": ("Educação", "educacao"),
    "clothing": ("Vestuário", "vestuario"), "leisure": ("Lazer", "lazer"), "housing": ("Moradia", "moradia"),
    "transport": ("Transporte", "transporte"),
}
LINE_LABEL = {"food": "Alimentação", "health": "Saúde", "education": "Educação", "clothing": "Vestuário",
              "leisure": "Lazer", "housing": "Moradia", "transport": "Transporte"}
# (idade máxima inclusive, custos)
CHILD_BANDS = [
    (2, dict(name="bebê", food=350, health=250, clothing=120, leisure=80, housing=150, transport=0)),
    (5, dict(name="primeira infância", food=400, health=200, clothing=120, leisure=120, housing=150, transport=100)),
    (11, dict(name="ensino fundamental I", food=500, health=180, clothing=150, leisure=150, housing=180, transport=150)),
    (17, dict(name="adolescência", food=650, health=200, clothing=220, leisure=200, housing=220, transport=200)),
]
EDUCATION = {  # (faixa mínima de idade, PUBLIC, PRIVATE)
    "daycare": (0, 2, 900, 900), "pre": (3, 5, 80, 1200), "fundamental": (6, 11, 150, 1500), "medio": (12, 17, 200, 1800),
}
ACTIVITIES_COST = {"min_age": 4, "cost": 280}
BIRTH_COST = 3500
MEDICAL_CRISIS_COST = 900
PREGNANCY_MONTHS = 9
MIN_MONTHS_TO_MARRY = 6
MIN_MONTHS_TO_COHABIT = 4
