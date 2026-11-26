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
