"""Carreira política e concursos públicos: cargos reais do Brasil (idade mínima, salário, ciclo eleitoral), partidos FICTÍCIOS, propostas,
postura com a mídia e concursos. Tudo simulado."""
from decimal import Decimal

D = Decimal

# cargo -> (nome, esfera, ciclo, idade mínima, salário bruto mensal R$, custo de campanha competitiva R$, força dos adversários 0..1, lugares na disputa)
OFFICES = {
    "vereador": ("Vereador(a)", "Municipal", "municipal", 18, 14000, 80_000, 0.45, 12),
    "prefeito": ("Prefeito(a)", "Municipal", "municipal", 21, 28000, 900_000, 0.66, 1),
    "dep_estadual": ("Deputado(a) estadual", "Estadual", "geral", 21, 34000, 700_000, 0.70, 40),
    "dep_federal": ("Deputado(a) federal", "Federal", "geral", 21, 46400, 2_500_000, 0.78, 25),
    "senador": ("Senador(a)", "Federal", "geral", 35, 46400, 5_000_000, 0.82, 1),
    "governador": ("Governador(a)", "Estadual", "geral", 30, 41000, 6_500_000, 0.86, 1),
    "presidente": ("Presidente da República", "Federal", "geral", 35, 46400, 22_000_000, 0.92, 1),
}
ELECTION_MONTH = 10                      # eleições em outubro
AFFILIATION_MONTHS = 6                   # filiação ao partido pelo menos 6 meses antes da eleição
TERM_YEARS = 4
CAMPAIGN_MONTHS = 3                      # ago, set, out: campanha oficial
MARKETERS = {"LOW": ("Marqueteiro iniciante", 5000, 0.35), "MID": ("Marqueteiro experiente", 16000, 0.65), "HIGH": ("Marqueteiro de grandes campanhas", 42000, 0.92)}
RALLIES = {"comicio": ("Comício", 6000, 7), "caminhada": ("Caminhada e corpo a corpo", 1500, 4), "entrevista": ("Entrevistas em rádios e TVs locais", 3000, 6),
           "redes": ("Campanha nas redes sociais", 4500, 8), "debate": ("Preparar-se para o debate", 800, 5)}
# ideologia -2 (esquerda) .. +2 (direita)
IDEOLOGIES = {"esquerda": -2, "centro_esquerda": -1, "centro": 0, "centro_direita": 1, "direita": 2}
IDEOLOGY_LABEL = {"esquerda": "Esquerda", "centro_esquerda": "Centro-esquerda", "centro": "Centro", "centro_direita": "Centro-direita", "direita": "Direita"}
PARTIES = {  # partido fictício -> (nome, ideologia, força 0..1)
    "pdt": ("Partido Democrático Trabalhista Popular (PDTP)", -2, 0.62), "psl": ("Partido Social Liberal Progressista (PSLP)", -1, 0.55), "pmc": ("Partido do Movimento Cívico (PMC)", 0, 0.70),
    "pnr": ("Partido Nacional Republicano (PNR)", 1, 0.58), "pdl": ("Partido da Direita Liberal (PDL)", 2, 0.60), "pvs": ("Partido Verde Solidário (PVS)", -1, 0.35),
    "pen": ("Partido Empreendedor Nacional (PEN)", 1, 0.40)}
PROPOSALS = {  # área: (nome, inclinação ideológica -2..2)
    "saude": ("Ampliar postos de saúde e filas de exames", -1), "educacao": ("Escola em tempo integral e valorização de professores", -1), "seguranca": ("Mais policiamento e tecnologia contra o crime", 1),
    "economia": ("Reduzir impostos e burocracia para empresas", 2), "social": ("Ampliar programas de renda e moradia popular", -2), "ambiente": ("Proteger florestas e investir em energia limpa", -1),
    "transporte": ("Mobilidade urbana e obras de infraestrutura", 0), "anticorrupcao": ("Transparência total e combate à corrupção", 0), "privatizacao": ("Concessões e privatizações para atrair investimento", 2),
    "cultura": ("Incentivo à cultura e ao esporte", -1), "agro": ("Apoio ao agronegócio e ao produtor rural", 1), "familia": ("Políticas de família e valores tradicionais", 2)}
MAX_PROPOSALS = 3
MEDIA = {  # postura: (nome, descrição, variância nas polêmicas, ganho de aprovação a longo prazo)
    "transparente": ("Transparente", "Responde tudo e assume erros: perde menos nas crises e constrói confiança.", 0.6, 0.35),
    "combativo": ("Combativo", "Enfrenta a imprensa e adversários: polariza, ganha e perde muito mais.", 1.7, 0.0),
    "populista": ("Populista", "Fala direto ao povo e promete muito: sobe rápido, mas cai feio nas contradições.", 1.4, -0.05),
    "evasivo": ("Evasivo", "Evita jornalistas: poucos riscos e pouca visibilidade.", 0.45, -0.15),
    "tecnico": ("Técnico", "Fala de dados e planos: agrada eleitor escolarizado, menos carisma.", 0.8, 0.15)}
# ------------------------------------------------------------------ concursos públicos
EXAMS = {  # tipo -> (órgão, cargo, salário líquido R$, candidatos por vaga, requisito de formação (campo ou None), inscrição R$, campo do emprego, nível)
    "tribunal": ("Tribunal de Justiça", "Analista judiciário", 9800, 190, "direito", 250, "direito", 2),
    "pf": ("Polícia Federal", "Agente de polícia federal", 11500, 320, None, 280, "seguranca", 2),
    "banco": ("Banco público", "Escriturário", 4600, 140, None, 140, "financas", 1),
    "professor": ("Secretaria Estadual de Educação", "Professor(a) concursado(a)", 4100, 60, "educacao", 120, "educacao", 1),
    "auditor": ("Receita Estadual", "Auditor(a) fiscal", 17500, 410, "financas", 330, "financas", 3),
    "diplomata": ("Instituto Rio Branco (Itamaraty)", "Diplomata", 16500, 520, "relacoes", 300, "relacoes", 3),
    "saude": ("Hospital universitário público", "Enfermeiro(a) concursado(a)", 4300, 45, "saude", 110, "saude", 1),
    "inss": ("INSS", "Técnico do seguro social", 5200, 160, None, 160, "financas", 1),
    "estatistico": ("Instituto de pesquisa federal", "Analista de dados/estatístico(a)", 10500, 130, "matematica", 220, "matematica", 2),
    "prefeitura": ("Prefeitura municipal", "Agente administrativo", 3200, 70, None, 90, "financas", 0),
}
EXAM_DELAY_MONTHS = 2


def exam_difficulty(competition: int, level: int) -> float:
    import math
    return 33 + 12 * math.log10(max(competition, 2)) + 4 * level


def exam_chance(study: float, synergy: float, field_match: bool, competition: int, level: int, hours_day: float) -> float:
    """Chance de passar: estudo + diplomas que ajudam + formação exigida; a concorrência e o nível do cargo elevam a régua."""
    strength = study + 1.2 * synergy + (14 if field_match else 0) + 2.0 * hours_day
    return round(max(0.02, min(0.90, 0.5 + (strength - exam_difficulty(competition, level)) / 60)), 3)
