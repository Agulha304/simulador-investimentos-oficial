"""Regras do mercado de trabalho: vagas por área e nível, currículo, cursos, CLT x PJ e freelas."""
from decimal import Decimal

from backend.services.life_rules import hash01

D = Decimal
LEVEL_NEED = (0, 20, 45, 75)                         # pontos de currículo (na área) esperados por nível da vaga
LEVEL_NAME = ("Entrada", "Júnior", "Pleno", "Sênior")
LEVEL_NET = (1800, 3300, 5900, 10500)               # salário líquido CLT de referência por nível
CLT_GROSS_FACTOR = 0.80                              # líquido ≈ 80% do bruto (INSS + IR)
FGTS_RATE = 0.08
PJ_PREMIUM = 1.25                                    # PJ cobra ~25% a mais que o líquido CLT...
PJ_TAX = 0.06                                        # ...e paga imposto do próprio bolso (sem 13º, férias, FGTS e benefícios)
PJ_EXTRA_HOURS = 60                                  # referência mínima (padrão) de horas/mês que um PJ extra consome do tempo livre
PJ_MIN_HOURS = 48                                    # nenhum PJ extra pede menos que ~11 h/semana
PJ_MAX_HOURS = 140                                   # e os mais puxados chegam a ~32 h/semana
PJ_LEVEL_HOURS = (56, 72, 92, 112)                   # base por nível da vaga (entrada, júnior, pleno, sênior): mais responsabilidade = mais horas
PJ_FIELD_FACTOR = {"saude": 1.25, "direito": 1.15, "tecnologia": 1.05, "engenharia": 1.10, "financas": 1.05, "industria": 1.10, "logistica": 1.10,
                   "agro": 1.10, "gastronomia": 1.15, "seguranca": 1.10, "educacao": 0.90, "artes": 0.90, "comercio": 1.00, "ciencia": 1.00}
APPLY_HOURS = 6
MAX_APPLICATIONS = 4
START_HOURS_WARN = 0

LADDER = {
    "tecnologia": (("Estagiário de suporte de TI", "Auxiliar de informática", "Assistente de help desk"),
                   ("Desenvolvedor(a) júnior", "Analista de suporte", "Analista de dados júnior"),
                   ("Desenvolvedor(a) pleno", "Analista de sistemas", "Engenheiro(a) de dados"),
                   ("Desenvolvedor(a) sênior", "Arquiteto(a) de software", "Líder técnico")),
    "saude": (("Auxiliar de enfermagem", "Recepcionista de clínica", "Atendente de farmácia"),
              ("Técnico(a) de enfermagem", "Assistente de consultório", "Fisioterapeuta júnior"),
              ("Enfermeiro(a)", "Fisioterapeuta", "Nutricionista clínico(a)"),
              ("Médico(a) especialista", "Enfermeiro(a)-chefe", "Coordenador(a) de clínica")),
    "engenharia": (("Auxiliar de obras", "Desenhista técnico(a)", "Almoxarife"),
                   ("Técnico(a) de segurança", "Engenheiro(a) trainee", "Assistente de projetos"),
                   ("Engenheiro(a) pleno", "Coordenador(a) de obra", "Projetista"),
                   ("Engenheiro(a) sênior", "Gerente de obras", "Especialista em projetos")),
    "financas": (("Auxiliar administrativo", "Assistente financeiro", "Atendente bancário"),
                 ("Analista financeiro júnior", "Assistente contábil", "Analista de RH júnior"),
                 ("Analista financeiro pleno", "Contador(a)", "Analista de planejamento"),
                 ("Gerente financeiro", "Controller", "Gestor(a) de investimentos")),
    "direito": (("Auxiliar de escritório jurídico", "Estagiário(a) de direito", "Recepcionista de escritório"),
                ("Assistente jurídico", "Paralegal", "Advogado(a) júnior"),
                ("Advogado(a) pleno", "Analista jurídico", "Consultor(a) de compliance"),
                ("Advogado(a) sênior", "Sócio(a) associado(a)", "Gerente jurídico")),
    "educacao": (("Auxiliar de sala", "Monitor(a) escolar", "Auxiliar de biblioteca"),
                 ("Professor(a) de reforço", "Assistente pedagógico", "Professor(a) substituto(a)"),
                 ("Professor(a) do ensino fundamental", "Coordenador(a) de projetos educacionais", "Tutor(a)"),
                 ("Coordenador(a) pedagógico(a)", "Diretor(a) de escola", "Consultor(a) educacional")),
    "comercio": (("Operador(a) de caixa", "Repositor(a) de mercadorias", "Atendente de loja"),
                 ("Vendedor(a) de loja", "Atendente de call center", "Assistente de estoque"),
                 ("Supervisor(a) de vendas", "Representante comercial", "Comprador(a)"),
                 ("Gerente de loja", "Gerente comercial", "Diretor(a) de vendas")),
    "artes": (("Auxiliar de produção", "Assistente de estúdio", "Auxiliar de gráfica"),
              ("Designer júnior", "Social media", "Editor(a) de vídeo júnior"),
              ("Designer pleno", "Redator(a)", "Produtor(a) de conteúdo"),
              ("Diretor(a) de arte", "Editor(a)-chefe", "Gerente de comunicação")),
    "agro": (("Auxiliar agrícola", "Operador(a) de campo", "Auxiliar de viveiro"),
             ("Técnico(a) agrícola", "Assistente ambiental", "Inspetor(a) de qualidade rural"),
             ("Agrônomo(a)", "Engenheiro(a) ambiental", "Gestor(a) de fazenda"),
             ("Agrônomo(a) sênior", "Gerente de produção rural", "Consultor(a) ambiental")),
    "gastronomia": (("Auxiliar de cozinha", "Garçom/Garçonete", "Recepcionista de hotel"),
                    ("Cozinheiro(a)", "Barista", "Atendente de turismo"),
                    ("Chef de partida", "Supervisor(a) de salão", "Guia de turismo"),
                    ("Chef executivo(a)", "Gerente de restaurante", "Gerente de hotel")),
    "logistica": (("Ajudante de carga", "Auxiliar de expedição", "Separador(a) de pedidos"),
                  ("Motorista", "Conferente", "Assistente de logística"),
                  ("Analista de logística", "Supervisor(a) de transporte", "Planejador(a) de rotas"),
                  ("Gerente de logística", "Coordenador(a) de frota", "Gerente de supply chain")),
    "seguranca": (("Vigilante", "Auxiliar administrativo público", "Porteiro(a)"),
                  ("Agente de segurança", "Agente administrativo", "Guarda municipal"),
                  ("Analista de segurança", "Técnico(a) judiciário(a)", "Fiscal"),
                  ("Delegado(a) / Oficial", "Auditor(a) fiscal", "Gestor(a) público(a)")),
    "industria": (("Auxiliar de produção", "Operador(a) de máquina", "Ajudante de manutenção"),
                  ("Técnico(a) de manutenção", "Soldador(a)", "Eletricista industrial"),
                  ("Engenheiro(a) de produção", "Supervisor(a) de manutenção", "Técnico(a) de automação"),
                  ("Gerente de fábrica", "Engenheiro(a) de processos sênior", "Coordenador(a) de manutenção")),
    "ciencia": (("Auxiliar de laboratório", "Técnico(a) de coleta", "Monitor(a) de pesquisa"),
                ("Analista de laboratório", "Assistente de pesquisa", "Bolsista de iniciação"),
                ("Pesquisador(a)", "Químico(a)", "Biólogo(a)"),
                ("Pesquisador(a) sênior", "Coordenador(a) de laboratório", "Cientista-chefe")),
}
EMPLOYERS = ("Grupo Horizonte", "Casa Nova", "Mercado Bom Preço", "Rede Vida", "Clínica Aurora", "TecnoSul", "Construtora Alicerce", "Banco Meridional",
             "Escritório Almeida & Costa", "Colégio Saber", "Studio Cor", "Atacado Brasil", "Hospital São Lucas", "Inova Sistemas", "Prime Consultoria",
             "Loja do Bairro", "Supermercados Estrela", "Agência Pixel", "Instituto Futuro", "Ótica Visão")

# cursos: key -> (nome, área, meses, custo/mês, horas/mês, pontos no currículo)
COURSES = {
    "ingles": ("Inglês intermediário", "geral", 8, 220, 12, 8),
    "excel": ("Excel e planilhas", "geral", 2, 180, 10, 5),
    "comunicacao": ("Comunicação e oratória", "geral", 3, 160, 8, 5),
    "informatica": ("Informática básica", "geral", 2, 90, 8, 4),
    "gestao_tempo": ("Gestão do tempo e produtividade", "geral", 1, 120, 6, 3),
    "python": ("Programação em Python", "tecnologia", 6, 260, 16, 14),
    "web": ("Desenvolvimento web", "tecnologia", 8, 280, 18, 16),
    "dados": ("Análise de dados", "tecnologia", 6, 300, 16, 15),
    "primeiros_socorros": ("Primeiros socorros", "saude", 2, 130, 8, 8),
    "tec_enfermagem": ("Técnico em enfermagem", "saude", 18, 350, 20, 22),
    "cuidador": ("Cuidador de idosos", "saude", 4, 200, 12, 10),
    "autocad": ("AutoCAD e projetos", "engenharia", 5, 270, 14, 14),
    "seguranca_trabalho": ("Técnico em segurança do trabalho", "engenharia", 12, 320, 18, 18),
    "gestao_obras": ("Gestão de obras", "engenharia", 6, 300, 14, 14),
    "contabilidade": ("Contabilidade básica", "financas", 6, 230, 12, 13),
    "mercado_financeiro": ("Mercado financeiro", "financas", 4, 260, 10, 12),
    "rh": ("Rotinas de RH", "financas", 4, 210, 10, 10),
    "pratica_juridica": ("Prática jurídica e contratos", "direito", 6, 300, 14, 14),
    "oab": ("Preparatório para a OAB", "direito", 8, 380, 18, 20),
    "didatica": ("Didática e planejamento de aulas", "educacao", 5, 170, 10, 12),
    "libras": ("Libras", "educacao", 8, 190, 10, 11),
    "psicopedagogia": ("Psicopedagogia", "educacao", 10, 250, 12, 15),
    "vendas": ("Técnicas de vendas", "comercio", 3, 170, 10, 11),
    "atendimento": ("Excelência em atendimento", "comercio", 2, 120, 8, 8),
    "gestao_estoque": ("Gestão de estoque", "comercio", 4, 190, 10, 11),
    "design_grafico": ("Design gráfico", "artes", 8, 260, 14, 15),
    "edicao_video": ("Edição de vídeo", "artes", 6, 240, 14, 13),
    "redacao": ("Redação publicitária", "artes", 4, 190, 10, 10),
    "espanhol": ("Espanhol", "geral", 8, 210, 12, 7),
    "lideranca": ("Liderança e gestão de equipes", "geral", 4, 260, 10, 8),
    "agronegocio": ("Gestão do agronegócio", "agro", 6, 280, 14, 14),
    "manejo_ambiental": ("Manejo ambiental e licenciamento", "agro", 5, 240, 12, 12),
    "culinaria": ("Culinária profissional", "gastronomia", 8, 300, 16, 15),
    "hotelaria": ("Hotelaria e eventos", "gastronomia", 6, 230, 12, 12),
    "cnh_profissional": ("CNH profissional (C/D/E)", "logistica", 3, 320, 10, 12),
    "gestao_frota": ("Gestão de frotas e rotas", "logistica", 5, 260, 12, 13),
    "concurso": ("Preparatório para concursos", "seguranca", 10, 240, 18, 17),
    "defesa_pessoal": ("Segurança patrimonial", "seguranca", 4, 210, 12, 11),
    "soldagem": ("Soldagem industrial", "industria", 6, 290, 16, 14),
    "automacao": ("Automação e CLP", "industria", 8, 330, 16, 16),
    "metodos_pesquisa": ("Métodos de pesquisa científica", "ciencia", 5, 220, 12, 13),
    "analise_laboratorial": ("Análises laboratoriais", "ciencia", 8, 310, 16, 15),
}
DEGREE_POINTS = 35
OTHER_DEGREE_POINTS = 8

GIG_TITLES = {
    "geral": ("Bico de entregas", "Ajuda em evento", "Serviço de montagem", "Digitação e organização de documentos"),
    "tecnologia": ("Site para pequena empresa", "Conserto e suporte de computadores", "Automação de planilhas"),
    "saude": ("Plantão de cuidador(a)", "Acompanhamento de paciente", "Aplicação de vacinas em evento"),
    "engenharia": ("Projeto de reforma", "Laudo técnico", "Levantamento de medidas"),
    "financas": ("Organização financeira de MEI", "Declaração de imposto de renda", "Consultoria de orçamento"),
    "direito": ("Revisão de contrato", "Parecer jurídico", "Atendimento em mutirão jurídico"),
    "educacao": ("Aulas particulares", "Reforço escolar", "Oficina para crianças"),
    "comercio": ("Vendas em feira", "Promotor(a) de loja", "Atendimento em evento"),
    "artes": ("Logotipo para cliente", "Edição de vídeo para evento", "Posts para redes sociais"),
    "agro": ("Laudo de solo", "Consultoria de plantio", "Mutirão de colheita"),
    "gastronomia": ("Buffet de festa", "Garçom em evento", "Aulas de culinária"),
    "logistica": ("Frete avulso", "Mudança residencial", "Entregas por aplicativo"),
    "seguranca": ("Segurança de evento", "Ronda noturna avulsa", "Controle de acesso em show"),
    "industria": ("Conserto de máquina", "Instalação elétrica", "Soldagem de portão"),
    "ciencia": ("Análise de amostras", "Revisão de artigo científico", "Aulas de ciências"),
}


def pj_hours(field: str, level: int, user_id: int, key: str) -> int:
    """Horas/mês que um PJ EXTRA consome: cresce com o nível e muda por área e por contrato (nunca abaixo de ~11 h/semana)."""
    base = PJ_LEVEL_HOURS[level] * PJ_FIELD_FACTOR.get(field, 1.0) * (0.85 + 0.35 * hash01("pj-hours", user_id, key))
    return int(max(PJ_MIN_HOURS, min(PJ_MAX_HOURS, round(base / 4) * 4)))


def clt_gross(net: float) -> float:
    return net / CLT_GROSS_FACTOR


def pj_net(clt_net: float) -> float:
    return round(clt_net * PJ_PREMIUM * (1 - PJ_TAX), 2)


def approval_chance(field_score: float, level: int, hard: float = 0.0) -> int:
    """Chance (%) de ser aprovado: depende do quanto o seu currículo na área cobre o que a vaga pede."""
    x = field_score - LEVEL_NEED[level]
    p = 0.30 + 0.015 * x - hard
    return int(round(max(0.03, min(0.92, p)) * 100))


def offer_net(field_start: float, level: int, user_id: int, key: str) -> int:
    wiggle = 0.92 + 0.16 * hash01("offer-net", user_id, key)
    return int(round(LEVEL_NET[level] * field_start * wiggle, -1))
