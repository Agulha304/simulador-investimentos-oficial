"""Carreiras: áreas de atuação, perspectiva de crescimento e faculdades.

No início todas as áreas pagam praticamente o mesmo (`start` entre 0,97 e 1,02): o que muda é a PERSPECTIVA — o reajuste
anual (`growth`) e o ganho extra de quem se forma (`premium`). Quem estuda pode mudar de área e passar a ganhar mais.
"""
FIELDS = {
    "tecnologia": dict(label="Tecnologia", emoji="💻", start=1.00, growth=6.5, outlook="reajustes altos e muita procura",
                       degree="Ciência da Computação", months=48, cost=1100, premium=34, hours=20),
    "saude": dict(label="Saúde", emoji="🩺", start=0.99, growth=5.2, outlook="estável, com ótimo ganho para quem se forma",
                  degree="Medicina / Enfermagem", months=60, cost=1500, premium=55, hours=24),
    "engenharia": dict(label="Engenharia", emoji="🏗️", start=1.01, growth=5.8, outlook="bons reajustes e grandes projetos",
                       degree="Engenharia", months=60, cost=1300, premium=38, hours=22),
    "financas": dict(label="Finanças e negócios", emoji="📊", start=1.00, growth=5.5, outlook="cresce com promoções e cargos de gestão",
                     degree="Administração / Economia", months=48, cost=1000, premium=32, hours=18),
    "direito": dict(label="Direito", emoji="⚖️", start=0.99, growth=5.0, outlook="começo igual, mas paga muito bem depois da formação",
                    degree="Direito", months=60, cost=1200, premium=42, hours=22),
    "educacao": dict(label="Educação", emoji="📚", start=0.98, growth=3.8, outlook="reajustes menores, muito significado",
                     degree="Licenciatura / Pedagogia", months=36, cost=700, premium=16, hours=16),
    "comercio": dict(label="Comércio e vendas", emoji="🛍️", start=1.02, growth=4.4, outlook="comissões e crescimento moderado",
                     degree="Gestão comercial", months=36, cost=800, premium=20, hours=16),
    "artes": dict(label="Artes e comunicação", emoji="🎨", start=0.97, growth=4.0, outlook="mais criativo, ganho irregular",
                  degree="Design / Comunicação", months=36, cost=750, premium=18, hours=16),
    "agro": dict(label="Agro e meio ambiente", emoji="🌾", start=0.99, growth=4.8, outlook="demanda firme no campo; ganha mais quem se forma",
                 degree="Agronomia / Engenharia Ambiental", months=60, cost=1250, premium=36, hours=22),
    "gastronomia": dict(label="Gastronomia e turismo", emoji="🍽️", start=0.98, growth=4.1, outlook="muito movimento, salário base baixo e gorjetas",
                        degree="Gastronomia / Turismo", months=36, cost=800, premium=19, hours=16),
    "logistica": dict(label="Logística e transporte", emoji="🚚", start=1.01, growth=4.6, outlook="cresce com o comércio online",
                      degree="Logística", months=36, cost=850, premium=24, hours=16),
    "seguranca": dict(label="Segurança e serviço público", emoji="🛡️", start=1.00, growth=4.3, outlook="estabilidade e plano de carreira",
                      degree="Gestão pública / Segurança", months=36, cost=800, premium=22, hours=16),
    "industria": dict(label="Indústria e manutenção", emoji="🏭", start=1.02, growth=4.9, outlook="turnos, adicionais e bons técnicos",
                      degree="Engenharia de Produção / Mecatrônica", months=60, cost=1250, premium=35, hours=22),
    "ciencia": dict(label="Ciência e pesquisa", emoji="🔬", start=0.97, growth=5.4, outlook="começa baixo, cresce com mestrado e doutorado",
                    degree="Química / Física / Biologia", months=60, cost=1200, premium=44, hours=24),
    "musica": dict(label="Música", emoji="🎼", start=0.97, growth=3.9, outlook="mercado irregular; aulas, orquestras e produção",
                   degree="Música (bacharelado/licenciatura)", months=48, cost=900, premium=17, hours=18),
    "matematica": dict(label="Matemática e estatística", emoji="➗", start=1.00, growth=5.6, outlook="muito valorizada em finanças, dados e ensino",
                       degree="Matemática / Estatística", months=48, cost=1000, premium=30, hours=20),
    "relacoes": dict(label="Relações internacionais e diplomacia", emoji="🌐", start=0.98, growth=4.7, outlook="abre portas em diplomacia, política e comércio exterior",
                     degree="Relações Internacionais", months=48, cost=1150, premium=28, hours=18),
}
# Quanto o diploma em uma área AJUDA o currículo em OUTRAS áreas (pontos extras na área de destino; "politica" e "concurso" valem para carreira política e concursos).
SYNERGY = {
    ("matematica", "financas"): 12, ("matematica", "engenharia"): 12, ("matematica", "educacao"): 10, ("matematica", "tecnologia"): 11, ("matematica", "ciencia"): 9,
    ("matematica", "industria"): 6, ("matematica", "logistica"): 5, ("matematica", "concurso"): 6,
    ("relacoes", "direito"): 8, ("relacoes", "financas"): 6, ("relacoes", "seguranca"): 9, ("relacoes", "comercio"): 7, ("relacoes", "politica"): 14, ("relacoes", "concurso"): 8,
    ("direito", "politica"): 11, ("direito", "seguranca"): 9, ("direito", "relacoes"): 8, ("direito", "concurso"): 10,
    ("financas", "politica"): 9, ("financas", "comercio"): 8, ("financas", "matematica"): 5, ("financas", "concurso"): 8, ("financas", "relacoes"): 5,
    ("educacao", "politica"): 6, ("educacao", "musica"): 5, ("educacao", "concurso"): 6, ("artes", "musica"): 7, ("musica", "artes"): 7, ("musica", "educacao"): 7,
    ("engenharia", "industria"): 9, ("engenharia", "matematica"): 6, ("tecnologia", "matematica"): 6, ("ciencia", "matematica"): 7, ("comercio", "politica"): 4,
}
DEFAULT_FIELD = "comercio"
NO_DEGREE_SWITCH = 0.85           # mudar de área sem diploma = recomeçar com 15% a menos
MAX_DEGREES = 3
