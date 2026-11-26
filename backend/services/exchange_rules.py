"""Programas de intercâmbio baseados em oportunidades reais por país (idiomas, graduação-sanduíche, cursos técnicos, bolsas e estágios).

Cada programa tem duração, mensalidade/curso em MOEDA LOCAL (valores aproximados de escolas e universidades reais), eventual bolsa/estágio
remunerado e o que rende no currículo: pontos em uma ÁREA ou pontos GERAIS ("geral"). O custo total soma: passagem, visto e seguro iniciais
(reais), instalação (2 aluguéis de caução) e, todo mês, curso + aluguel, comida, contas (energia/água/internet), transporte e saúde do país,
convertidos pelo câmbio do mês (com IOF/spread). Quem mora fora precisa largar o emprego presencial no Brasil; o remoto continua.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class Program:
    key: str
    country: str
    name: str
    kind: str                # IDIOMA | ACADEMICO | TECNICO | BOLSA | ESTAGIO
    months: int
    tuition: float           # por mês, moeda local
    stipend: float           # bolsa/estágio por mês, moeda local (renda)
    field: str               # área do currículo ou "geral"
    points: int
    note: str = ""


PROGRAMS: dict[str, Program] = {p.key: p for p in [
    Program("ca-esl", "CA", "Curso de inglês (ESL) em Vancouver/Toronto", "IDIOMA", 6, 1300, 0, "geral", 10, "escolas de idiomas cobram ~CAD 300 por semana"),
    Program("ca-college", "CA", "Diploma técnico em college canadense (TI)", "TECNICO", 12, 1250, 0, "tecnologia", 20, "colleges públicos para estudantes internacionais"),
    Program("us-cc", "US", "Community college com inglês acadêmico", "ACADEMICO", 6, 1800, 0, "geral", 12, "créditos transferíveis"),
    Program("us-business", "US", "Certificado em negócios (extension de universidade)", "ACADEMICO", 6, 2400, 0, "financas", 18, "programas de extensão"),
    Program("gb-english", "GB", "Inglês intensivo em Londres", "IDIOMA", 3, 1400, 0, "geral", 6, "visto de curta duração"),
    Program("ie-english", "IE", "Inglês em Dublin (com trabalho de 20h/semana)", "IDIOMA", 6, 1100, 700, "geral", 9, "estudantes podem trabalhar meio período"),
    Program("de-daad", "DE", "Semestre em universidade alemã (DAAD, engenharia)", "BOLSA", 6, 50, 934, "engenharia", 22, "universidades públicas quase sem mensalidade; bolsa DAAD ~€934"),
    Program("de-german", "DE", "Curso intensivo de alemão (Goethe-Institut)", "IDIOMA", 4, 1100, 0, "geral", 8, ""),
    Program("fr-francais", "FR", "Francês em Paris (Alliance Française)", "IDIOMA", 4, 900, 0, "geral", 8, ""),
    Program("es-espanhol", "ES", "Espanhol em Madri/Salamanca", "IDIOMA", 3, 900, 0, "geral", 6, ""),
    Program("it-design", "IT", "Design e moda em Milão", "ACADEMICO", 6, 1500, 0, "artes", 18, "escolas de design italianas"),
    Program("pt-mobilidade", "PT", "Mobilidade acadêmica em universidade portuguesa", "ACADEMICO", 6, 150, 0, "direito", 14, "convênios entre universidades"),
    Program("pt-estagio", "PT", "Estágio profissional remunerado em Lisboa", "ESTAGIO", 6, 0, 800, "financas", 16, "estágios para estudantes e recém-formados"),
    Program("nl-delft", "NL", "Semestre em universidade técnica (engenharia)", "ACADEMICO", 6, 1250, 0, "engenharia", 20, "mensalidade de estudante não europeu ~€15 mil/ano"),
    Program("ch-eth", "CH", "Semestre em ETH/EPFL (ciências)", "ACADEMICO", 6, 125, 0, "ciencia", 24, "mensalidade baixa, custo de vida altíssimo"),
    Program("au-vet", "AU", "Curso técnico de gastronomia (VET)", "TECNICO", 12, 1800, 0, "gastronomia", 18, ""),
    Program("nz-agri", "NZ", "Agronegócio e manejo (Lincoln)", "ACADEMICO", 6, 2500, 0, "agro", 18, ""),
    Program("jp-nihongo", "JP", "Escola de japonês + cultura em Tóquio", "IDIOMA", 6, 120000, 0, "geral", 12, "escolas de idioma para estudantes"),
    Program("kr-kgsp", "KR", "Bolsa do governo coreano (KGSP): coreano + TI", "BOLSA", 12, 0, 1000000, "tecnologia", 22, "bolsa cobre curso e dá mesada"),
    Program("ar-uba", "AR", "Semestre na UBA (Universidade de Buenos Aires)", "ACADEMICO", 6, 0, 0, "direito", 12, "universidade pública gratuita"),
    Program("cl-uchile", "CL", "Semestre na Universidade do Chile", "ACADEMICO", 6, 180000, 0, "ciencia", 12, ""),
    Program("mx-unam", "MX", "Semestre na UNAM (artes e comunicação)", "ACADEMICO", 6, 0, 0, "artes", 12, "universidade pública"),
]}

# Chance de a VAGA ser remota por área (empregos no Brasil e no exterior). Quem mora fora só consegue vagas remotas (ou presenciais no país onde mora).
REMOTE_SHARE = {"tecnologia": 0.55, "artes": 0.40, "financas": 0.35, "direito": 0.20, "educacao": 0.15, "comercio": 0.10, "ciencia": 0.15,
                "engenharia": 0.10, "logistica": 0.05, "agro": 0.0, "saude": 0.0, "gastronomia": 0.0, "seguranca": 0.0, "industria": 0.0}
ABROAD_HARD = 0.15            # procurar emprego no exterior é mais difícil (idioma, visto)
REMOTE_HARD = 0.08            # vagas remotas atraem muita gente
RESIDENT_FLIGHT_BACK = 0.8    # a volta custa 80% da passagem de ida e volta


def for_country(code: str) -> list[Program]:
    return [p for p in PROGRAMS.values() if p.country == code]
