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
}
DEFAULT_FIELD = "comercio"
NO_DEGREE_SWITCH = 0.85           # mudar de área sem diploma = recomeçar com 15% a menos
MAX_DEGREES = 3
