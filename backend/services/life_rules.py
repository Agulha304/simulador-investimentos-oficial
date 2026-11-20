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
    "cinema": dict(label="Cinema", cost=60, hours=4, social=+1, wellbeing=+2, meets=0.10, interest="cultura"),
    "museum": dict(label="Museu e exposições", cost=30, hours=5, social=+1, wellbeing=+1, quality=+1, meets=0.18, interest="cultura"),
    "concert": dict(label="Show ao vivo", cost=200, hours=6, social=+2, wellbeing=+3, meets=0.28, interest="música"),
    "team_sport": dict(label="Esporte em grupo (futebol, vôlei)", cost=20, hours=8, social=+2, health=+2, wellbeing=+1, meets=0.30, interest="esporte"),
    "language_class": dict(label="Aula de idiomas", cost=180, hours=12, social=+1, quality=+1, meets=0.22, interest="estudos"),
    "book_club": dict(label="Clube do livro", cost=0, hours=6, social=+2, wellbeing=+1, meets=0.26, interest="cultura"),
    "board_games": dict(label="Noite de jogos de tabuleiro", cost=25, hours=5, social=+2, wellbeing=+2, meets=0.24, interest="jogos"),
    "cooking_class": dict(label="Oficina de culinária", cost=140, hours=7, social=+2, wellbeing=+1, meets=0.26, interest="gastronomia"),
    "hiking": dict(label="Trilha na natureza", cost=15, hours=10, social=+1, health=+2, wellbeing=+3, meets=0.20, interest="natureza"),
    "fair": dict(label="Feira de bairro", cost=40, hours=3, social=+1, wellbeing=+1, meets=0.16, interest="gastronomia"),
    "networking": dict(label="Encontro de profissionais (networking)", cost=50, hours=5, social=+2, quality=+1, meets=0.30, interest="tecnologia"),
    "coworking": dict(label="Dia no coworking", cost=60, hours=8, social=+1, meets=0.18, interest="tecnologia"),
    "dance_class": dict(label="Aula de dança", cost=120, hours=8, social=+3, health=+1, wellbeing=+2, meets=0.32, interest="música"),
    "community_garden": dict(label="Horta comunitária", cost=0, hours=7, social=+2, wellbeing=+2, meets=0.22, interest="natureza"),
    "games_night": dict(label="Campeonato de videogame", cost=35, hours=6, social=+2, wellbeing=+1, meets=0.24, interest="jogos"),
    "charity_event": dict(label="Mutirão solidário", cost=0, hours=9, social=+2, wellbeing=+3, satisfaction=+1, meets=0.30, interest="causas"),
    "picnic": dict(label="Piquenique no parque", cost=45, hours=5, social=+2, wellbeing=+2, meets=0.18, interest="natureza"),
}
# interações com uma pessoa já conhecida
INTERACTIONS = {
    "chat": dict(label="Conversar", cost=0, hours=4, gain=3),
    "walk": dict(label="Passeio gratuito", cost=0, hours=8, gain=4, interest="natureza"),
    "cook": dict(label="Cozinhar juntos", cost=40, hours=6, gain=5, interest="gastronomia"),
    "outing": dict(label="Programa a dois", cost=160, hours=8, gain=5),
    "trip": dict(label="Viagem a dois", cost=1500, hours=30, gain=8, interest="viagens"),
    "movie": dict(label="Cinema ou série juntos", cost=50, hours=4, gain=4, interest="cultura"),
    "game": dict(label="Jogar juntos", cost=10, hours=5, gain=4, interest="jogos"),
    "sport": dict(label="Fazer esporte juntos", cost=15, hours=7, gain=5, interest="esporte"),
    "study": dict(label="Estudar juntos", cost=0, hours=6, gain=4, interest="estudos"),
    "music": dict(label="Ouvir música ou ir a um show", cost=90, hours=6, gain=5, interest="música"),
    "help": dict(label="Ajudar em uma causa juntos", cost=0, hours=7, gain=5, interest="causas"),
    "tech": dict(label="Projeto ou curso de tecnologia juntos", cost=30, hours=6, gain=4, interest="tecnologia"),
}
COMPAT_BONUS_BASE, COMPAT_BONUS_MATCH, COMPAT_BONUS_CAP = 1, 2, 30      # convivência aproxima: cada atividade soma; tema em comum soma mais

STAGES = ("ACQUAINTANCE", "FRIEND", "DATING", "COHABITING", "MARRIED", "ENDED")
PARTNER_STAGES = ("DATING", "COHABITING", "MARRIED")
HOUSEHOLD_STAGES = ("COHABITING", "MARRIED")

# ---------------------------------------------------------------- personagens
NAMES = {
    "M": ["Bruno", "Diego", "Fábio", "Hugo", "João", "Lucas", "Nelson", "Paulo", "Sérgio", "Vitor", "Caio", "Enzo", "Rafael", "Thiago", "Gustavo",
          "Matheus", "André", "Felipe", "Rodrigo", "Marcelo", "Leonardo", "Pedro", "Daniel", "Henrique", "Gabriel", "Eduardo", "Renato", "Otávio",
          "Murilo", "Leandro", "Davi", "Arthur", "Samuel", "Igor", "Ícaro", "Jonas", "Davi", "Wagner", "Cauã", "Benício", "Emanuel", "Ramon", "Tiago",
          "Alexandre", "Fernando", "Ricardo", "Marcos", "Roberto", "Joaquim", "Teodoro", "Lauro", "Ismael", "Cláudio", "Breno", "Yuri", "Dante"],
    "F": ["Ana", "Carla", "Elisa", "Gabriela", "Isabela", "Karina", "Mariana", "Olívia", "Rafaela", "Tatiana", "Yara", "Débora", "Beatriz", "Camila",
          "Fernanda", "Juliana", "Larissa", "Letícia", "Natália", "Patrícia", "Renata", "Sabrina", "Vanessa", "Amanda", "Bianca", "Cecília", "Daniela",
          "Eduarda", "Flávia", "Helena", "Ingrid", "Jéssica", "Lívia", "Manuela", "Nicole", "Priscila", "Raquel", "Sofia", "Thaís", "Valentina",
          "Aline", "Bruna", "Clara", "Diana", "Estela", "Fabiana", "Giovana", "Heloísa", "Irene", "Joana", "Luana", "Marta", "Noemi", "Paloma", "Rita", "Sandra"],
}
FIRST_NAMES = NAMES["M"] + NAMES["F"]
LAST_NAMES = ["Silva", "Santos", "Oliveira", "Souza", "Pereira", "Costa", "Rodrigues", "Almeida", "Nascimento", "Lima", "Araújo", "Fernandes", "Carvalho",
              "Gomes", "Martins", "Rocha", "Ribeiro", "Alves", "Monteiro", "Mendes", "Barros", "Freitas", "Barbosa", "Pinto", "Moreira", "Cavalcanti",
              "Dias", "Castro", "Campos", "Cardoso", "Teixeira", "Correia", "Machado", "Nunes", "Vieira", "Moura", "Duarte", "Azevedo", "Lopes", "Ramos",
              "Reis", "Farias", "Batista", "Xavier", "Tavares", "Siqueira", "Prado", "Medeiros", "Brandão", "Guimarães", "Peixoto", "Coelho", "Bittencourt",
              "Nogueira", "Andrade", "Pacheco", "Sampaio", "Bezerra", "Borges", "Toledo", "Fonseca", "Lacerda", "Amaral", "Viana", "Matos", "Cunha"]
CHILD_NAMES = ["Alice", "Miguel", "Helena", "Arthur", "Laura", "Theo", "Valentina", "Davi", "Sofia", "Lorenzo", "Cecília", "Gael", "Heitor", "Maria", "Bernardo",
               "Manuela", "Samuel", "Isis", "Benício", "Lívia", "Ravi", "Aurora", "Nicolas", "Luna", "Henrique", "Maitê", "Enzo", "Antônia", "Joaquim", "Clara"]
PERSONALITIES = ["extrovertido", "reservado", "aventureiro", "caseiro", "ambicioso", "tranquilo", "criativo", "metódico"]
# afinidade entre personalidades (0..1), simétrica; omitido = 0.5
PERSONALITY_AFFINITY = {
    ("extrovertido", "reservado"): 0.7, ("extrovertido", "extrovertido"): 0.6, ("aventureiro", "caseiro"): 0.35,
    ("aventureiro", "aventureiro"): 0.8, ("caseiro", "caseiro"): 0.8, ("ambicioso", "tranquilo"): 0.65,
    ("ambicioso", "ambicioso"): 0.45, ("criativo", "metódico"): 0.7, ("reservado", "reservado"): 0.6,
    ("tranquilo", "tranquilo"): 0.75, ("metódico", "metódico"): 0.7, ("aventureiro", "metódico"): 0.4,
}
INTERESTS = ["esporte", "música", "viagens", "gastronomia", "estudos", "cultura", "causas", "tecnologia", "natureza", "jogos"]
# (masculino, feminino, salário-base mensal de referência)
OCCUPATIONS = [("Professor", "Professora", 4200), ("Enfermeiro", "Enfermeira", 5200), ("Designer", "Designer", 5800), ("Analista de sistemas", "Analista de sistemas", 7200),
               ("Autônomo", "Autônoma", 3500), ("Engenheiro civil", "Engenheira civil", 11000), ("Cozinheiro", "Cozinheira", 3200), ("Médico", "Médica", 18000),
               ("Estagiário", "Estagiária", 1600), ("Comerciante", "Comerciante", 6500), ("Motorista de aplicativo", "Motorista de aplicativo", 3800),
               ("Contador", "Contadora", 8200), ("Advogado", "Advogada", 9500), ("Dentista", "Dentista", 10500), ("Arquiteto", "Arquiteta", 8800),
               ("Programador", "Programadora", 9000), ("Jornalista", "Jornalista", 5200), ("Fotógrafo", "Fotógrafa", 4300), ("Músico", "Música", 3600),
               ("Eletricista", "Eletricista", 4200), ("Padeiro", "Padeira", 3000), ("Policial", "Policial", 5600), ("Bombeiro", "Bombeira", 6200),
               ("Veterinário", "Veterinária", 6800), ("Fisioterapeuta", "Fisioterapeuta", 5600), ("Psicólogo", "Psicóloga", 5400), ("Personal trainer", "Personal trainer", 4400),
               ("Gerente de loja", "Gerente de loja", 6700), ("Vendedor", "Vendedora", 3300), ("Mecânico", "Mecânica", 4100), ("Agricultor", "Agricultora", 4000),
               ("Piloto", "Piloto", 16000), ("Cientista de dados", "Cientista de dados", 12500), ("Bibliotecário", "Bibliotecária", 4300), ("Farmacêutico", "Farmacêutica", 6900),
               ("Chef de cozinha", "Chef de cozinha", 7400), ("Influenciador digital", "Influenciadora digital", 5000), ("Marceneiro", "Marceneira", 3900),
               ("Tradutor", "Tradutora", 5100), ("Pesquisador", "Pesquisadora", 7800), ("Empresário", "Empresária", 13000), ("Entregador", "Entregadora", 2900),
               ("Barista", "Barista", 2800), ("Professor de idiomas", "Professora de idiomas", 4600), ("Artista plástico", "Artista plástica", 3700)]


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


# ---------------------------------------------------------------- histórias (aparecem em um aviso temporário depois de cada convivência)
STORIES = {
    "chat": ["Vocês passaram a tarde conversando sobre sonhos e planos para o futuro.", "{name} contou uma história engraçada da infância e vocês riram muito.",
             "Vocês tiveram uma conversa sincera e se conheceram melhor."],
    "walk": ["Vocês fizeram uma caminhada até um mirante e viram o pôr do sol.", "Vocês passearam pelo parque e descobriram uma cachoeira escondida.",
             "Vocês andaram pela cidade e acharam uma livraria charmosa."],
    "cook": ["Vocês cozinharam uma lasanha juntos — a cozinha ficou uma bagunça, mas estava deliciosa!", "Vocês testaram uma receita nova e {name} virou o chef da noite.",
             "Vocês fizeram pães caseiros e a casa ficou com cheiro de padaria."],
    "outing": ["Vocês jantaram em um restaurante aconchegante e brindaram ao acaso que uniu vocês.", "Vocês foram a uma sorveteria artesanal e provaram sabores malucos.",
               "Vocês passaram uma noite especial num lugar novo da cidade."],
    "trip": ["Vocês viajaram para uma praia tranquila e acordaram vendo o nascer do sol.", "Vocês exploraram uma cidadezinha histórica de mãos dadas.",
             "Vocês acamparam sob as estrelas e conversaram até tarde."],
    "movie": ["Vocês assistiram a um filme de aventura e discutiram o final por horas.", "Vocês viram uma série juntos e já combinaram o próximo episódio.",
              "Vocês foram ao cinema e dividiram a pipoca com {name}."],
    "game": ["Vocês jogaram um jogo cooperativo e salvaram o mundo juntos!", "{name} ganhou três partidas seguidas e pediu revanche.",
             "Vocês participaram de um torneio de jogos de tabuleiro e quase brigaram pela vitória."],
    "sport": ["Vocês jogaram vôlei de praia e terminaram exaustos e felizes.", "Vocês correram juntos no parque e fizeram uma pequena competição.",
              "Vocês foram a uma aula de escalada e {name} se superou."],
    "study": ["Vocês estudaram juntos para uma prova e se ajudaram a entender a matéria.", "Vocês montaram um plano de estudos e combinaram revisões semanais.",
              "Vocês passaram a tarde na biblioteca, cada um com seu livro."],
    "music": ["Vocês foram a um show ao vivo e cantaram todas as músicas.", "Vocês descobriram uma banda nova e já fizeram uma playlist juntos.",
              "Vocês tocaram violão juntos e {name} arriscou cantar."],
    "help": ["Vocês ajudaram uma ONG que salva baleias a organizar uma campanha.", "Vocês fizeram um mutirão para plantar mudas de árvores na cidade.",
             "Vocês serviram refeições em um abrigo e foram aplaudidos pelos voluntários.", "Vocês arrecadaram agasalhos para famílias que precisavam."],
    "tech": ["Vocês montaram um pequeno projeto de programação e viram o primeiro resultado funcionar.", "Vocês fizeram um curso online de tecnologia juntos.",
             "Vocês consertaram um computador antigo e deram a ele nova vida."],
}
