"""Carreira de ARTISTA (ator, músico, pintor e influenciador): catálogos e regras puras. Tudo é simulado e inventado para o jogo
(estilos, temas, plataformas, equipamentos, valores em reais), inspirado em como cada carreira funciona na prática."""
from decimal import Decimal

from backend.services.goods_rules import hash01

D = Decimal

# ------------------------------------------------------------------ gerais
DISCIPLINES = ("music", "acting", "painting", "influencer")
LABEL = {"music": "Música", "acting": "Atuação", "painting": "Pintura", "influencer": "Influenciador"}
MAX_CHANNELS = 3
TRAIN = {  # disciplina -> (aula, custo/mês em R$, horas/mês, pontos de habilidade)
    "music": ("Aulas de instrumento", 450, 16, 3.0), "acting": ("Oficina de teatro", 380, 14, 3.0),
    "painting": ("Ateliê de pintura", 350, 14, 3.0), "influencer": ("Curso de roteiro e edição", 300, 12, 2.5)}


def clamp(v: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, v))


# ------------------------------------------------------------------ música
INSTRUMENTS = {  # chave -> (nome, demanda do mercado 0,5..1,5)
    "vocal": ("Vocal", 1.45), "guitarra": ("Guitarra", 1.30), "bateria": ("Bateria", 1.35), "violao": ("Violão", 1.15), "baixo": ("Baixo", 1.05),
    "teclado": ("Teclado/Piano", 1.10), "dj": ("DJ / Produção eletrônica", 1.00), "sanfona": ("Sanfona", 0.85), "violino": ("Violino", 0.70),
    "saxofone": ("Saxofone", 0.80), "trompete": ("Trompete", 0.60), "percussao": ("Percussão", 1.00), "cavaquinho": ("Cavaquinho", 0.75),
}
STYLES = {  # estilo -> (nome, mercado 0,7..1,6)
    "sertanejo": ("Sertanejo", 1.60), "funk": ("Funk", 1.45), "pop": ("Pop", 1.40), "pagode": ("Pagode", 1.20), "rock": ("Rock", 1.05), "mpb": ("MPB", 0.95),
    "forro": ("Forró", 1.10), "eletronica": ("Eletrônica", 1.15), "gospel": ("Gospel", 1.10), "rap": ("Rap", 1.15), "jazz": ("Jazz", 0.75),
    "metal": ("Metal", 0.80), "samba": ("Samba", 1.00), "classica": ("Clássica", 0.65),
}
THEMES = {"amor": "Amor", "saudade": "Saudade", "festa": "Festa", "superacao": "Superação", "cotidiano": "Cotidiano", "liberdade": "Liberdade",
          "tristeza": "Tristeza", "natureza": "Natureza", "politica": "Política", "fe": "Fé", "viagem": "Viagem"}
VENUES = {  # nível -> (nome, reputação mínima, cachê min, cachê máx)
    "bar": ("Bar", 0, 350, 1200), "restaurante": ("Restaurante", 5, 500, 1800), "casa_show": ("Casa de show", 28, 2500, 9000),
    "festival": ("Festival", 55, 12000, 45000), "evento": ("Evento corporativo / casamento", 15, 1500, 6000)}
BAND_MAX = 6
MUSIC_JOB_KINDS = {  # tipo -> (descrição, mensal?, pagamento min, max, meses, habilidade mínima)
    "banda_bar": ("Banda de bar e restaurante", True, 1400, 3200, (3, 6), 20), "banda_baile": ("Banda de baile e festas", True, 2800, 6500, (3, 8), 35),
    "artista_apoio": ("Músico de apoio de um artista", True, 5000, 14000, (3, 10), 58), "gravacao": ("Sessão de estúdio", False, 400, 2500, (1, 1), 30),
    "show": ("Apresentação avulsa (freela)", False, 300, 3000, (1, 1), 15), "igreja_coral": ("Músico de igreja/coral", True, 900, 2200, (6, 12), 10),
}
BAND_NAMES = ("Os Cometas", "Banda do Porto", "Quarteto Azul", "Trio Elétrico", "Nova Onda", "Sol de Dezembro", "Raízes da Terra", "Fogo Cruzado", "Lua Cheia", "Ponto Cego",
              "Vozes do Norte", "Maré Alta", "Cidade Baixa", "Velvet Rua", "Barão do Samba", "Estrada Real")
FIRST = ("Ana", "Bruno", "Carla", "Diego", "Elisa", "Fábio", "Gisele", "Hugo", "Isabela", "João", "Karina", "Lucas", "Marina", "Nando", "Olívia", "Pedro", "Quésia", "Rafael", "Sofia", "Tiago")
LAST = ("Alves", "Barros", "Cardoso", "Dias", "Esteves", "Farias", "Gomes", "Lima", "Moura", "Nunes", "Ramos", "Silva", "Teixeira", "Vieira")
SONG_PROMO = {  # opção -> (rótulo, custo, descrição)
    "gravadora": ("Oferecer a uma gravadora", 0, "Se aceitar: adiantamento, divulgação profissional e royalties; exige qualidade e reputação."),
    "streaming": ("Lançar por conta própria nas plataformas", 1500, "Distribuição digital e anúncios; retorno modesto, mas é seu."),
    "clipe": ("Gravar um clipe e investir em redes sociais", 4500, "Chance maior de viralizar e de ganhar reputação."),
    "radio": ("Pagar divulgação em rádios", 6000, "Funciona melhor com banda já conhecida."),
    "boca": ("Só divulgar entre amigos e shows", 0, "Sem custo; alcance pequeno."),
}
PAINT_PROMO = {
    "galeria": ("Oferecer a uma galeria", 0, "A galeria fica com 40%, mas vende melhor; exige qualidade."),
    "feira": ("Expor numa feira de arte (R$ 800 de estande)", 800, "Venda direta ao público."),
    "leilao": ("Colocar em leilão (15% de comissão)", 0, "Pode render muito para quem já tem nome."),
    "redes": ("Divulgar nas redes e vender direto", 0, "Alcance depende da sua fama; sem intermediários."),
    "loja": ("Anunciar numa loja online de arte (R$ 300)", 300, "Venda lenta, mas constante."),
    "doacao": ("Doar para um leilão beneficente", 0, "Não rende dinheiro, mas dá fama e reputação."),
}
PAINT_STYLES = {"realismo": ("Realismo", 1.10), "abstrato": ("Abstrato", 1.00), "impressionismo": ("Impressionismo", 1.05), "pop_art": ("Pop art", 1.20),
                "surrealismo": ("Surrealismo", 1.00), "aquarela": ("Aquarela", 0.90), "grafite": ("Grafite / arte urbana", 1.10), "retrato": ("Retratos", 1.00)}
PAINT_SIZES = {"pequeno": ("Pequeno (30x40 cm)", 60, 14, 1200), "medio": ("Médio (60x80 cm)", 180, 28, 3500), "grande": ("Grande (1,2 m)", 520, 48, 11000),
               "mural": ("Mural", 1800, 90, 32000)}      # (nome, material R$, horas, preço-base de venda)
PAINT_THEMES = {"paisagem": "Paisagem", "retrato": "Retrato", "cidade": "Cidade", "abstrato": "Emoções", "natureza_morta": "Natureza-morta", "social": "Tema social",
                "fantasia": "Fantasia", "cultura": "Cultura popular"}
COMMISSION_KINDS = {  # tipo -> (descrição, pagamento min, max, habilidade mínima)
    "retrato": ("Retrato por encomenda", 700, 3500, 20), "mural": ("Mural para comércio", 2500, 9000, 30), "capa": ("Capa de livro/álbum", 900, 4500, 25),
    "decoracao": ("Quadro de decoração", 600, 2800, 15), "restauro": ("Restauro de obra", 1200, 6000, 40), "cenario": ("Cenário de teatro", 1500, 7500, 35)}
# ------------------------------------------------------------------ atuação
ACTING_KINDS = {  # tipo -> (descrição, mensal?, min, max, meses, fama mínima, habilidade mínima)
    "figuracao": ("Figuração em série", False, 450, 1500, (1, 1), 0, 5), "curta": ("Curta-metragem", False, 600, 2500, (1, 1), 0, 10),
    "comercial": ("Comercial de TV/internet", False, 2500, 18000, (1, 1), 8, 18), "dublagem": ("Dublagem", False, 1500, 6000, (1, 1), 5, 25),
    "teatro": ("Peça de teatro", True, 1800, 4800, (3, 6), 0, 20), "serie": ("Papel em série", True, 6000, 22000, (4, 8), 30, 40),
    "novela": ("Novela", True, 14000, 45000, (6, 9), 45, 55), "cinema": ("Filme de cinema", False, 20000, 90000, (1, 1), 55, 62)}
# ------------------------------------------------------------------ influenciador
PLATFORMS = {  # chave -> (nome, meta de monetização em inscritos, CPM por mil views em R$, alcance, retorno fixo)
    "youtube": ("YouTube", 1000, 11.0, 1.0), "instagram": ("Instagram", 3000, 5.5, 1.1), "tiktok": ("TikTok", 5000, 2.5, 1.4),
    "twitch": ("Twitch (lives)", 500, 8.0, 0.8), "podcast": ("Podcast", 800, 14.0, 0.7)}
NICHES = {  # nicho -> (nome, multiplicador de CPM, concorrência 0,4..1,6, patrocínio)
    "games": ("Games", 0.8, 1.5, 1.0), "tecnologia": ("Tecnologia", 1.4, 1.2, 1.4), "financas": ("Finanças", 2.2, 1.1, 1.8), "culinaria": ("Culinária", 1.0, 1.1, 1.1),
    "fitness": ("Fitness", 1.2, 1.3, 1.5), "humor": ("Humor", 0.7, 1.6, 0.9), "viagem": ("Viagem", 1.3, 1.0, 1.4), "beleza": ("Beleza e moda", 1.1, 1.5, 1.6),
    "educacao": ("Educação", 1.2, 0.8, 1.0), "vlog": ("Vlog de rotina", 0.8, 1.4, 0.9), "musica": ("Música", 0.9, 1.3, 0.9), "negocios": ("Negócios", 2.0, 0.9, 1.6)}
GEAR = {  # categoria -> (nome, [preço de cada nível 1..5])
    "camera": ("Câmera", [2500, 6500, 14000, 32000, 80000]), "luz": ("Iluminação", [400, 1500, 4000, 9000, 20000]),
    "audio": ("Microfone e áudio", [300, 1200, 3500, 8000, 18000]), "computador": ("Computador de edição", [3500, 7000, 12000, 22000, 40000]),
    "cenario": ("Cenário/estúdio", [1500, 6000, 15000, 40000, 100000])}
GEAR_LEVEL = ("Celular/improvisado", "Básico", "Intermediário", "Semiprofissional", "Profissional", "Estúdio de ponta")
INVEST = {  # chave -> (nome, tipo, custo, descrição)
    "editor": ("Contratar editor de vídeo", "MONTHLY", 2200, "Qualidade +8 e libera ~40% do seu tempo de edição."),
    "thumbs": ("Designer de capas/thumbnails", "MONTHLY", 900, "Mais cliques: +12% de visualizações."),
    "ads": ("Tráfego pago (anúncios)", "MONTHLY", 1800, "Atrai público novo: mais inscritos todo mês."),
    "curso": ("Curso de roteiro e storytelling", "ONCE", 1800, "+6 de habilidade em criação de conteúdo."),
    "colab": ("Colaboração com outro criador", "ONCE", 1200, "Chance de ganhar uma leva de inscritos do parceiro."),
    "evento": ("Encontro presencial com a comunidade", "ONCE", 4500, "Fideliza o público e aumenta a venda de produtos."),
    "merch": ("Loja de produtos (camisetas, canecas)", "ONCE", 5000, "Receita extra mensal proporcional ao público."),
    "agencia": ("Agência/empresário (15% da receita)", "COMMISSION", 0, "Patrocínios muito melhores; exige 10 mil inscritos."),
    "contador": ("Contador especializado em criadores", "MONTHLY", 450, "Reduz os impostos sobre a receita."),
}
TAX_RATE = 0.06
HOURS_PER_VIDEO = 8
CADENCE = (0, 2, 4, 8, 12)


def gear_score(gear: dict) -> float:
    """0..100: média ponderada do nível dos equipamentos (câmera e áudio pesam mais)."""
    w = {"camera": 0.28, "audio": 0.24, "luz": 0.18, "computador": 0.18, "cenario": 0.12}
    return sum(w[k] * (int(gear.get(k, 0)) / 5) for k in w) * 100


def channel_quality(skill: float, gear: dict, editor: bool, extra: float = 0.0) -> float:
    return clamp(0.42 * skill + 0.50 * gear_score(gear) + (8 if editor else 0) + extra)


def trend(seed, niche: str, ref) -> float:
    """Tendência do nicho no mês (0,7..1,4): altos e baixos que o criador não controla."""
    return round(0.7 + 0.7 * hash01("trend", seed, niche, ref.isoformat()), 3)


def sponsorship(subs: int, niche: str, agency: bool, seed, cid, ref) -> int:
    """Patrocínio do mês (0 se não aparecer). Aparece com mais chance e valor quando o canal cresce."""
    if subs < 3000:
        return 0
    p = min(0.75, 0.10 + subs / 200000) * (1.3 if agency else 1.0)
    if hash01("sponsor", seed, cid, ref.isoformat()) >= p:
        return 0
    base = 400 + subs * 0.045
    return int(base * NICHES[niche][3] * (1.8 if agency else 1.0) * (0.7 + 0.9 * hash01("sponsor-v", seed, cid, ref.isoformat())))


def month_views(subs: int, quality: float, cadence: int, niche: str, platform: str, tr: float, ads: bool, thumbs: bool, luck: float) -> int:
    """Visualizações do mês: base de inscritos + descoberta (qualidade, anúncios), vezes constância, tendência, nicho e sorte."""
    if cadence <= 0:
        return int(subs * 0.01)
    reach = PLATFORMS[platform][3]
    comp = NICHES[niche][2]
    per_video = subs * (0.04 + 0.22 * (quality / 100) ** 1.4) + (40 + 900 * (quality / 100) ** 2) / comp + (700 if ads else 0)
    v = per_video * cadence * reach * tr * (1.12 if thumbs else 1.0) * (0.55 + 0.9 * luck)
    return int(max(0, v))


def sub_gain(views: int, quality: float, niche: str, ads: bool, collab_boost: int = 0) -> int:
    conv = 0.003 + 0.017 * (quality / 100) ** 1.3
    return int(views * conv * (1.25 if ads else 1.0) / NICHES[niche][2] ** 0.5) + collab_boost


def channel_revenue(views: int, subs: int, platform: str, niche: str, merch: bool, community: float) -> tuple[int, int]:
    """(anúncios, produtos) do mês, já zerados se o canal ainda não atingiu a meta de monetização da plataforma."""
    if subs < PLATFORMS[platform][1]:
        return 0, 0
    ads = int(views / 1000 * PLATFORMS[platform][2] * NICHES[niche][1])
    shop = int(subs * 0.0035 * (0.6 + community / 100)) * 30 if merch else 0
    return ads, shop


# ------------------------------------------------------------------ pontuações e sorteios de aceitação
def hire_chance(skill: float, fame: float, need_skill: float, need_fame: float, demand: float = 1.0, extra: float = 0.0) -> float:
    """Chance (0,03..0,92) de ser escolhido: habilidade e fama acima do exigido ajudam; abaixo derrubam. `demand` pesa na procura."""
    x = 0.16 + 0.006 * (skill - need_skill) + 0.004 * (fame - need_fame) + extra
    return round(max(0.03, min(0.92, x * (0.7 + 0.3 * demand) + (0.15 if skill >= need_skill else 0.0))), 3)


def label_accepts(quality: float, reputation: float, style_market: float, roll: float) -> bool:
    return roll < max(0.04, min(0.85, 0.05 + 0.007 * (quality - 40) + 0.006 * reputation + 0.12 * (style_market - 1)))


def draw_musician(seed, ref, i: int, instrument: str) -> dict:
    name = f"{FIRST[int(hash01('bm-f', seed, ref.isoformat(), instrument, i) * len(FIRST))]} {LAST[int(hash01('bm-l', seed, ref.isoformat(), instrument, i) * len(LAST))]}"
    return {"key": f"M{ref:%Y%m}-{instrument}-{i}", "name": name, "instrument": instrument, "skill": int(25 + 60 * hash01("bm-s", seed, ref.isoformat(), instrument, i) ** 1.1),
            "ask": int(8 + 14 * hash01("bm-a", seed, ref.isoformat(), instrument, i))}


# ================================================================== v2: contas, plataformas reais, vídeos temáticos, publi e eventos
# Metas de monetização REAIS (pesquisa: páginas de ajuda do YouTube e do Spotify, TikTok, Instagram/Meta e Twitch; valores de terceiros, que mudam
# com o tempo): YouTube = parceria expandida 500 inscritos + 3 envios em 90 dias + 3.000 h de exibição (só apoio dos fãs) e programa completo 1.000
# inscritos + 4.000 h (anúncios). TikTok Creator Rewards: 10 mil seguidores + 100 mil visualizações em 30 dias. Instagram não divide anúncios:
# parcerias a partir de 1 mil, presentes 5 mil e assinaturas 10 mil seguidores. Twitch Afiliado: 50 seguidores, 8 h transmitidas em 7 dias e média de
# 3 espectadores nos últimos 30 dias. Podcast (Spotify Partner Program): 3 episódios, 1.000 audições e 2.000 h ouvidas em 30 dias.
PLATFORM_RULES = {
    "youtube": [
        {"key": "EXPANDED", "label": "Parceria expandida (apoio dos fãs)", "subs": 500, "watch_12m": 3000, "uploads_90d": 3, "ads": False, "fan": 0.5, "spons": True},
        {"key": "FULL", "label": "Programa de Parcerias (anúncios + apoio)", "subs": 1000, "watch_12m": 4000, "uploads_90d": 0, "ads": True, "fan": 1.0, "spons": True}],
    "instagram": [
        {"key": "BRANDS", "label": "Marketplace de criadores (parcerias)", "subs": 1000, "ads": False, "fan": 0.0, "spons": True},
        {"key": "GIFTS", "label": "Presentes e bônus", "subs": 5000, "ads": False, "fan": 0.4, "spons": True},
        {"key": "SUBS", "label": "Assinaturas de fãs", "subs": 10000, "ads": False, "fan": 1.0, "spons": True}],
    "tiktok": [{"key": "REWARDS", "label": "Creator Rewards Program", "subs": 10000, "views_30d": 100000, "ads": True, "fan": 0.4, "spons": True}],
    "twitch": [{"key": "AFFILIATE", "label": "Afiliado (assinaturas e bits)", "subs": 50, "streams_30d": 7, "avg_viewers": 3, "ads": True, "fan": 1.2, "spons": True}],
    "podcast": [{"key": "SPOTIFY", "label": "Spotify Partner Program", "episodes": 3, "views_30d": 1000, "listen_30d": 2000, "ads": True, "fan": 0.3, "spons": True}],
}
AVG_MIN = {"youtube": 4.5, "instagram": 0.4, "tiktok": 0.35, "twitch": 22.0, "podcast": 26.0}     # minutos assistidos por visualização
FAN_RATE = {"youtube": 4.0, "instagram": 6.0, "tiktok": 1.2, "twitch": 9.0, "podcast": 3.0}      # R$ por mil seguidores/mês de apoio dos fãs
MAX_ACCOUNTS = 4


def tier_status(platform: str, subs: int, *, watch_12m: float = 0, uploads_90d: int = 0, views_30d: int = 0, streams_30d: int = 0,
                avg_viewers: float = 0, episodes: int = 0, listen_30d: float = 0) -> dict:
    """Melhor nível de monetização atingido + o que falta para o próximo (metas reais por plataforma)."""
    got, nxt = None, None
    for t in PLATFORM_RULES[platform]:
        checks = [(subs >= t.get("subs", 0), f"{t.get('subs', 0):,} seguidores/inscritos".replace(",", "."), subs, t.get("subs", 0))]
        if "watch_12m" in t:
            checks.append((watch_12m >= t["watch_12m"], f"{t['watch_12m']:,} h de exibição em 12 meses".replace(",", "."), int(watch_12m), t["watch_12m"]))
        if t.get("uploads_90d"):
            checks.append((uploads_90d >= t["uploads_90d"], f"{t['uploads_90d']} vídeos nos últimos 90 dias", uploads_90d, t["uploads_90d"]))
        if "views_30d" in t:
            checks.append((views_30d >= t["views_30d"], f"{t['views_30d']:,} visualizações em 30 dias".replace(",", "."), views_30d, t["views_30d"]))
        if "streams_30d" in t:
            checks.append((streams_30d >= t["streams_30d"], f"{t['streams_30d']} transmissões em 30 dias", streams_30d, t["streams_30d"]))
            checks.append((avg_viewers >= t["avg_viewers"], f"média de {t['avg_viewers']} espectadores", round(avg_viewers, 1), t["avg_viewers"]))
        if "episodes" in t:
            checks.append((episodes >= t["episodes"], f"{t['episodes']} episódios", episodes, t["episodes"]))
            checks.append((listen_30d >= t["listen_30d"], f"{t['listen_30d']:,} h ouvidas em 30 dias".replace(",", "."), int(listen_30d), t["listen_30d"]))
        if all(c[0] for c in checks):
            got = t
        elif nxt is None:
            nxt = {"key": t["key"], "label": t["label"], "missing": [{"need": c[1], "have": c[2], "goal": c[3]} for c in checks if not c[0]]}
    return {"tier": got, "next": nxt}


def channel_money(platform: str, tier: dict | None, views: int, subs: int, niche: str, community: float, merch: bool) -> tuple[int, int, int]:
    """(anúncios, apoio dos fãs, produtos) do mês, conforme o nível de monetização atingido."""
    if tier is None:
        return 0, 0, 0
    ads = int(views / 1000 * PLATFORMS[platform][2] * NICHES[niche][1]) if tier.get("ads") else 0
    fan = int(subs / 1000 * FAN_RATE[platform] * tier.get("fan", 0) * (0.6 + community / 120))
    shop = int(subs * 0.0035 * (0.6 + community / 100)) * 30 if merch else 0
    return ads, fan, shop


# ------------------------------------------------------------------ vídeos temáticos: o que cada nicho "aceita" vender
TOPICS = {"conteudo": "Conteúdo normal do canal", "painting": "Divulgar/vender um quadro", "song": "Divulgar uma música", "play": "Divulgar uma peça (teatro)",
          "company": "Divulgar uma empresa/produto meu"}
TOPIC_FIT = {  # nicho -> encaixe (0..1,3) por tipo de divulgação
    "painting": {"beleza": .6, "vlog": .7, "educacao": .6, "humor": .3, "tecnologia": .15, "games": .15, "financas": .2, "culinaria": .3, "fitness": .15, "viagem": .5, "musica": .5, "negocios": .35},
    "song": {"musica": 1.2, "vlog": .7, "humor": .6, "games": .4, "viagem": .5, "beleza": .5, "fitness": .5, "tecnologia": .2, "financas": .1, "culinaria": .3, "educacao": .4, "negocios": .2},
    "play": {"vlog": .8, "humor": .9, "educacao": .7, "musica": .6, "beleza": .5, "viagem": .5, "games": .2, "tecnologia": .15, "financas": .15, "culinaria": .3, "fitness": .25, "negocios": .3},
    "company": {"negocios": 1.2, "financas": 1.0, "tecnologia": .9, "culinaria": .9, "beleza": .9, "fitness": .8, "vlog": .7, "viagem": .7, "games": .4, "humor": .4, "educacao": .6, "musica": .3}}


def topic_fit(niche: str, topic: str) -> float:
    return 1.0 if topic == "conteudo" else TOPIC_FIT[topic].get(niche, 0.3)


# ------------------------------------------------------------------ publi (patrocínios)
SPONSORS = [  # (marca, categoria, nicho de encaixe, pagamento-base, risco para a audiência 0..1)
    ("TechMais", "Loja de eletrônicos", "tecnologia", 1.0, 0.05), ("Banco Nuvem", "Banco digital", "financas", 1.2, 0.05), ("Sabor Express", "Aplicativo de delivery", "culinaria", 0.9, 0.05),
    ("Fit Power", "Suplementos", "fitness", 1.0, 0.18), ("Bela Pele", "Cosméticos", "beleza", 1.0, 0.08), ("Game Zone", "Jogo mobile", "games", 1.1, 0.10),
    ("Viaje Já", "Agência de viagens", "viagem", 1.0, 0.05), ("Aprenda+", "Curso online", "educacao", 0.9, 0.12), ("Casa & Cia", "Móveis e decoração", "vlog", 0.8, 0.04),
    ("Bet Faz Fortuna", "Casa de apostas (bet)", "*", 3.0, 0.85), ("Moeda Turbo", "Corretora de criptomoedas", "financas", 2.2, 0.55),
    ("Emagrece Já", "Chá 'milagroso' para emagrecer", "fitness", 2.0, 0.65), ("Rede Street", "Moda urbana", "humor", 0.8, 0.05), ("Som Livre", "Plataforma de música", "musica", 1.0, 0.04)]


# ------------------------------------------------------------------ situações exclusivas (decisões que aparecem na tela)
def _o(key, label, cost, *outs):
    return {"key": key, "label": label, "cost": cost, "outcomes": list(outs)}


def _x(prob, text, **fx):
    return (prob, text, fx)


# fx: money (R$ líquido; positivo entra no mês seguinte), money_k (R$ por mil inscritos somados), subs_pct (% sobre os inscritos de todos os canais),
#     community, fame, skill, rep (reputação da banda), life ({atributo: delta})
EVENTS = {
    # ---------------- influenciador
    "bet_publi": {"disc": "influencer", "need": {"subs": 3000}, "title": "Uma casa de apostas (bet) quer fazer publi com você",
                  "desc": "A proposta paga muito bem, mas parte do seu público critica divulgação de apostas, e o assunto pode virar polêmica.",
                  "options": [_o("aceitar", "Aceitar a publi", 0, _x(1.0, "Você fez a publi e recebeu muito bem, mas perdeu parte do público.", money=12000, money_k=900, subs_pct=-8, community=-15, life={"satisfaction": -3})),
                              _o("recusar", "Recusar", 0, _x(1.0, "Você recusou e a comunidade elogiou a postura.", community=4, subs_pct=1))]},
    "haters": {"disc": "influencer", "need": {"subs": 800}, "title": "Onda de ataques: tentam cancelar você",
               "desc": "Um trecho de um vídeo seu foi tirado de contexto e viralizou. O que fazer?",
               "options": [_o("responder", "Responder com um vídeo", 0, _x(0.5, "O vídeo de resposta viralizou a seu favor.", subs_pct=6, community=6), _x(0.5, "A resposta jogou lenha na fogueira.", subs_pct=-5, community=-6)),
                           _o("desculpas", "Pedir desculpas", 0, _x(1.0, "O pedido de desculpas acalmou parte do público.", subs_pct=-2, community=5)),
                           _o("ignorar", "Ignorar", 0, _x(0.6, "A polêmica passou rápido.", subs_pct=-1), _x(0.4, "O silêncio virou combustível para os ataques.", subs_pct=-5, community=-8))]},
    "algoritmo": {"disc": "influencer", "need": {"subs": 500}, "title": "Mudança no algoritmo derruba o seu alcance",
                  "desc": "As plataformas mudaram a recomendação e seus vídeos pararam de aparecer.",
                  "options": [_o("adaptar", "Fazer um curso de adaptação (R$ 800)", 800, _x(0.7, "Você se adaptou e o alcance voltou.", subs_pct=4, skill=2), _x(0.3, "Você estudou, mas o alcance continuou baixo.", skill=1)),
                              _o("ignorar", "Seguir como está", 0, _x(1.0, "O alcance caiu e levou inscritos junto.", subs_pct=-6))]},
    "collab_famoso": {"disc": "influencer", "need": {"subs": 1500}, "title": "Um criador famoso chama você para uma colaboração",
                      "desc": "Pode abrir portas para um público enorme, mas ele também escolhe o que vai ser mostrado.",
                      "options": [_o("aceitar", "Aceitar", 0, _x(0.6, "A colaboração foi um sucesso e trouxe inscritos.", subs_pct=12, community=4, fame=3), _x(0.4, "A colaboração rendeu pouco.", subs_pct=2)),
                                  _o("recusar", "Recusar", 0, _x(1.0, "Você preferiu crescer no seu ritmo.", community=1))]},
    "copyright": {"disc": "influencer", "need": {"subs": 300}, "title": "Strike de direitos autorais em um vídeo",
                  "desc": "Alguém denunciou uma música usada em um dos seus vídeos.",
                  "options": [_o("contestar", "Contestar com advogado (R$ 600)", 600, _x(0.5, "A contestação foi aceita.", community=2), _x(0.5, "Você perdeu o vídeo e a receita dele.", subs_pct=-3, money=-1500)),
                              _o("remover", "Remover o vídeo", 0, _x(1.0, "Você tirou o vídeo do ar.", subs_pct=-1))]},
    "conta_invadida": {"disc": "influencer", "need": {"subs": 2000}, "title": "Sua conta foi invadida",
                       "desc": "Hackers assumiram um dos seus canais e pedem resgate.",
                       "options": [_o("suporte", "Acionar suporte premium (R$ 1.500)", 1500, _x(0.8, "Você recuperou a conta.", community=-2), _x(0.2, "Demorou semanas e você perdeu audiência.", subs_pct=-8)),
                                   _o("negociar", "Negociar com os hackers", 0, _x(0.3, "Você recuperou a conta.", community=-4), _x(0.7, "Você perdeu a conta e uma parte do público.", subs_pct=-15, community=-10))]},
    "burnout_criativo": {"disc": "influencer", "need": {"subs": 500}, "title": "Esgotamento criativo",
                         "desc": "Você está sem ideias e cansado de postar.",
                         "options": [_o("pausar", "Pausar um mês", 0, _x(1.0, "A pausa fez bem, mas o canal esfriou.", subs_pct=-3, community=-5, life={"wellbeing": 8, "health": 3})),
                                     _o("insistir", "Insistir no ritmo", 0, _x(0.5, "Você segurou o ritmo.", community=1), _x(0.5, "O cansaço apareceu nos vídeos.", subs_pct=-5, life={"wellbeing": -10, "health": -4}))]},
    "comprar_seguidores": {"disc": "influencer", "need": {"subs": 300}, "title": "Oferta: comprar 5 mil seguidores por R$ 1.200",
                           "desc": "Um serviço promete números rápidos. As plataformas punem contas com seguidores falsos.",
                           "options": [_o("comprar", "Comprar", 1200, _x(0.5, "Os números subiram sem ser notados.", subs_pct=10), _x(0.5, "A plataforma detectou: conta penalizada.", subs_pct=-30, community=-20, money=-800)),
                                       _o("recusar", "Recusar", 0, _x(1.0, "Você seguiu no orgânico.", community=2))]},
    "sorteio": {"disc": "influencer", "need": {"subs": 500}, "title": "Fazer um sorteio para a comunidade?",
                "desc": "Um sorteio (R$ 2.000 em prêmios) costuma atrair gente nova.",
                "options": [_o("fazer", "Fazer o sorteio", 2000, _x(0.7, "O sorteio bombou e trouxe seguidores.", subs_pct=10, community=6), _x(0.3, "Veio muita gente que só queria o prêmio.", subs_pct=3)),
                            _o("nao", "Não fazer", 0, _x(1.0, "Você não fez.", community=0))]},
    "tv_convite": {"disc": "influencer", "need": {"subs": 8000}, "title": "Convite para um programa de TV/podcast famoso",
                   "desc": "Exposição enorme, mas ao vivo e sem edição.",
                   "options": [_o("aceitar", "Aceitar", 0, _x(0.7, "Você brilhou e ganhou muitos inscritos.", subs_pct=8, fame=5), _x(0.3, "Você deu uma gafe que viralizou.", subs_pct=-4, community=-4)),
                               _o("recusar", "Recusar", 0, _x(1.0, "Você ficou de fora.", community=0))]},
    "exclusividade": {"disc": "influencer", "need": {"subs": 6000}, "title": "Marca pede exclusividade por 30 dias",
                      "desc": "Você não poderia divulgar concorrentes, mas receberia um valor extra.",
                      "options": [_o("aceitar", "Aceitar a exclusividade", 0, _x(1.0, "Você cumpriu o contrato e recebeu.", money=3000, money_k=300, subs_pct=-1)),
                                  _o("recusar", "Recusar", 0, _x(1.0, "Você manteve a liberdade.", community=1))]},
    "fake_news": {"disc": "influencer", "need": {"subs": 3000}, "title": "Notícia falsa sobre você viraliza",
                  "desc": "Dizem que você aplicou golpe em seguidores.",
                  "options": [_o("desmentir", "Desmentir em vídeo", 0, _x(0.6, "O desmentido funcionou.", subs_pct=2, community=3), _x(0.4, "O desmentido alimentou o boato.", subs_pct=-4, community=-4)),
                              _o("processar", "Processar (R$ 3.000)", 3000, _x(0.5, "Você venceu e recebeu indenização.", money=5000, community=5), _x(0.5, "O processo foi longo e o boato ficou.", subs_pct=-2))]},
    # ---------------- músico
    "fa_na_rua": {"disc": "music", "need": {"fame": 2}, "title": "Um fã parou você na rua e pediu foto",
                  "desc": "Ele conhece suas músicas e quer conversar.",
                  "options": [_o("conversar", "Parar e conversar", 0, _x(1.0, "O fã adorou e divulgou você.", fame=1.5, life={"satisfaction": 3})),
                              _o("seguir", "Seguir andando", 0, _x(1.0, "O fã ficou chateado.", fame=-0.3))]},
    "tocar_na_rua": {"disc": "music", "need": {"instrument": True}, "title": "Estão pedindo para você tocar músicas na rua",
                     "desc": "Um grupo na praça reconheceu você e pede para tocar algumas músicas (o chapéu passa).",
                     "options": [_o("tocar", "Tocar na rua", 0, _x(0.8, "Você tocou, juntou gente e saiu com uns trocados.", money=260, fame=1.0, skill=0.4, life={"satisfaction": 3}), _x(0.2, "A guarda pediu para parar e multou você.", money=-150, life={"wellbeing": -2})),
                                 _o("recusar", "Recusar", 0, _x(1.0, "Você seguiu o seu caminho.", fame=0))]},
    "instrumento_quebrou": {"disc": "music", "need": {"instrument": True}, "title": "O instrumento quebrou antes de um show",
                            "desc": "Faltam algumas horas para o show.",
                            "options": [_o("consertar", "Consertar na hora (R$ 700)", 700, _x(1.0, "O instrumento foi consertado e o show saiu.", rep=1)),
                                        _o("emprestado", "Usar um instrumento emprestado", 0, _x(0.6, "Deu certo, com sacrifício.", skill=-0.3), _x(0.4, "O instrumento desafinou e o show foi ruim.", rep=-4, fame=-1)),
                                        _o("cancelar", "Cancelar o show", 0, _x(1.0, "O contratante ficou furioso.", rep=-6, fame=-2))]},
    "convite_casamento": {"disc": "music", "need": {"instrument": True}, "title": "Convite para tocar em um casamento",
                          "desc": "Um casal quer você na cerimônia e na festa (R$ 2.500).",
                          "options": [_o("aceitar", "Aceitar", 0, _x(0.85, "A festa foi um sucesso e os convidados elogiaram.", money=2500, fame=1.5), _x(0.15, "Problemas de som atrapalharam a festa.", money=1200, fame=-0.5)),
                                      _o("recusar", "Recusar", 0, _x(1.0, "Você recusou a data.", fame=0))]},
    "banda_rival": {"disc": "music", "need": {"band": True}, "title": "Uma banda rival provoca vocês nas redes",
                    "desc": "A provocação está rendendo comentários.",
                    "options": [_o("responder", "Responder à altura", 0, _x(0.4, "A resposta viralizou a favor de vocês.", rep=6, fame=2), _x(0.6, "Virou barraco e queimou a imagem.", rep=-4, fame=-1)),
                                _o("ignorar", "Ignorar", 0, _x(1.0, "A provocação morreu sozinha.", rep=0))]},
    "olheiro": {"disc": "music", "need": {"fame": 8}, "title": "Um olheiro de gravadora assistiu a um show seu",
                "desc": "Ele deixou o cartão e pediu para conversar.",
                "options": [_o("jantar", "Convidar para jantar (R$ 400)", 400, _x(0.4, "Ele gostou e ofereceu um adiantamento.", money=8000, fame=6, rep=6), _x(0.6, "Foi simpático, mas nada saiu.", fame=1)),
                            _o("ignorar", "Não procurar", 0, _x(1.0, "A oportunidade passou.", fame=0))]},
    "plagio": {"disc": "music", "need": {"fame": 10}, "title": "Acusam você de plagiar uma música",
               "desc": "Um compositor diz que uma melodia sua é cópia.",
               "options": [_o("provar", "Reunir provas e responder (R$ 1.200)", 1200, _x(0.65, "Você provou a autoria e saiu fortalecido.", fame=2), _x(0.35, "Houve acordo com pagamento ao compositor.", money=-3000, fame=-2)),
                           _o("acordo", "Fazer acordo na hora", 0, _x(1.0, "Você pagou para encerrar o caso.", money=-2500))]},
    # ---------------- ator
    "agente_papel": {"disc": "acting", "need": {"fame": 2}, "title": "Seu agente consegue um teste de última hora",
                     "desc": "É amanhã e exige preparação.",
                     "options": [_o("ir", "Ir ao teste", 0, _x(0.45, "Você foi aprovado(a) e recebeu o cachê.", money=2200, fame=2), _x(0.55, "Não passou, mas ganhou experiência.", skill=0.8)),
                                 _o("recusar", "Recusar", 0, _x(1.0, "Você não foi.", fame=0))]},
    "oficina_diretor": {"disc": "acting", "need": {"fame": 1}, "title": "Oficina com um diretor renomado",
                        "desc": "Poucas vagas e muita concorrência (R$ 900).",
                        "options": [_o("fazer", "Fazer a oficina", 900, _x(0.7, "Você aprendeu muito e fez contatos.", skill=4, fame=1.5), _x(0.3, "A oficina foi cansativa e rendeu pouco.", skill=1.5)),
                                    _o("nao", "Não ir", 0, _x(1.0, "Você ficou de fora.", fame=0))]},
    "peca_cancelada": {"disc": "acting", "need": {"fame": 3}, "title": "A peça em que você atua corre risco de ser cancelada",
                       "desc": "A bilheteria está fraca.",
                       "options": [_o("divulgar", "Ajudar a divulgar (nas suas redes)", 0, _x(0.55, "A peça se manteve e lotou.", fame=2, money=1500), _x(0.45, "Não adiantou.", fame=-0.5)),
                                   _o("sair", "Pular do barco", 0, _x(1.0, "Você saiu da produção.", fame=-1, money=-600))]},
    # ---------------- pintor
    "colecionador": {"disc": "painting", "need": {"works": 1}, "title": "Um colecionador quer comprar um quadro seu",
                     "desc": "Ele oferece um valor bom, mas quer exclusividade.",
                     "options": [_o("aceitar", "Vender", 0, _x(0.8, "A venda foi fechada e ele divulgou seu nome.", money=4500, fame=2.5), _x(0.2, "Ele pediu desconto depois.", money=2500, fame=1)),
                                 _o("recusar", "Recusar", 0, _x(1.0, "Você manteve a obra.", fame=0))]},
    "critico_arte": {"disc": "painting", "need": {"works": 1}, "title": "Um crítico escreveu sobre a sua obra",
                     "desc": "O texto sai amanhã.",
                     "options": [_o("convidar", "Convidar para o ateliê (R$ 300)", 300, _x(0.6, "A crítica foi elogiosa.", fame=4, skill=0.5), _x(0.4, "A crítica foi dura.", fame=-1, skill=1)),
                                 _o("ignorar", "Deixar sair", 0, _x(0.5, "Saiu uma nota positiva.", fame=2), _x(0.5, "Saiu uma nota fria.", fame=-0.5))]},
    "exposicao_convite": {"disc": "painting", "need": {"works": 2}, "title": "Convite para uma exposição coletiva",
                          "desc": "Estande e transporte custam R$ 1.200.",
                          "options": [_o("expor", "Expor", 1200, _x(0.55, "Você vendeu obras e fez contatos.", money=3800, fame=3), _x(0.45, "Poucas vendas.", money=600, fame=1)),
                                      _o("nao", "Não expor", 0, _x(1.0, "Você ficou de fora.", fame=0))]},
    "falsificacao": {"disc": "painting", "need": {"fame": 5}, "title": "Descobrem cópias falsas de uma obra sua",
                     "desc": "Estão vendendo reproduções como se fossem suas.",
                     "options": [_o("denunciar", "Denunciar (R$ 900)", 900, _x(0.6, "As cópias foram retiradas e a notícia ajudou.", fame=2), _x(0.4, "O caso se arrastou.", fame=0)),
                                 _o("ignorar", "Ignorar", 0, _x(1.0, "As cópias circularam.", fame=-1.5))]},
}
EVENT_P = 0.30      # chance mensal de surgir uma situação (se houver alguma elegível)
