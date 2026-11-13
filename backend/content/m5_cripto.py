from backend.content.schema import Lesson, Module, Q

DISCLAIMER = ("warn", "Conteúdo educacional. Não é recomendação de investimento. Regras e taxas mudam: confirme sempre a legislação vigente.")

MODULE = Module(
    id="m5", title="Criptomoedas", level="Intermediário",
    description="O que são, como funcionam, por que oscilam tanto e como dimensionar uma posição.",
    lessons=(
        Lesson("m5-l1", "O que são criptomoedas", 6, "Bitcoin, Ethereum, blockchain e custódia.", (
            ("p", "**Criptomoedas** são ativos digitais registrados em uma **blockchain**, um livro de registros distribuído e protegido por criptografia, sem um banco central por trás. O **Bitcoin** surgiu em 2009; o **Ethereum** acrescentou contratos inteligentes, que permitem programar aplicações."),
            ("h", "Características"),
            ("ul", ["**Negociação 24 horas, 7 dias por semana.**", "**Fracionamento:** você pode comprar uma fração (o Bitcoin é divisível até 8 casas decimais). No simulador, compre por valor em reais.", "**Sem lastro nem FGC:** o valor depende da oferta e da demanda.", "**Custódia:** na corretora (mais simples, depende dela) ou em carteira própria (você guarda as chaves e a responsabilidade)."]),
            ("h", "Regras no Brasil"),
            ("p", "O marco legal dos ativos virtuais (Lei 14.478/2022) regulamentou a atividade. Há obrigação de declarar e, em geral, ganhos na venda de valores mensais acima de R$ 35 mil são tributados. As regras mudam com frequência: consulte a Receita Federal."),
            ("warn", "Criptomoedas são ativos de **risco muito alto**. Já houve quedas de mais de 70%. Invista apenas o que você pode ver oscilar muito sem alterar seus planos."),
            ("sim", "/mercado", "Ver criptomoedas"), DISCLAIMER),
            (Q("Em um simulador, a compra de criptomoedas por valor em reais permite:", ["Comprar apenas unidades inteiras", "Comprar uma fração do ativo", "Comprar só em dólar", "Garantir lucro"], 1, "O valor investido é dividido pelo preço, resultando em uma quantidade fracionada."),
             Q("Qual é uma característica do mercado de criptomoedas?", ["Funciona só em horário comercial", "Tem cobertura do FGC", "Funciona 24 horas por dia", "É isento de oscilação"], 2, "O mercado cripto negocia continuamente."),
             Q("Custódia própria significa que:", ["A corretora guarda tudo por você", "O governo guarda as chaves", "O Tesouro garante o valor", "Você é responsável por guardar suas chaves"], 3, "Com carteira própria, a segurança das chaves é sua."))),

        Lesson("m5-l2", "Volatilidade e tamanho da posição", 7, "Como incluir cripto na carteira sem colocar o patrimônio em risco.", (
            ("p", "**Volatilidade** é o quanto o preço oscila. Criptomoedas costumam variar muito mais que ações ou renda fixa, por isso o **tamanho da posição** é a principal ferramenta de proteção."),
            ("h", "A conta que importa"),
            ("formula", "Perda no patrimônio = % da carteira na posição × queda do ativo"),
            ("p", "Com patrimônio de R$ 100.000, uma posição de 5% (R$ 5.000) que cai 60% custa R$ 3.000, ou **3% do patrimônio**. A mesma queda numa posição de 50% custaria 30% de tudo."),
            ("table", ["% do patrimônio em cripto", "Se cair 60%", "Impacto no patrimônio"], [["2%", "−R$ 1.200", "−1,2%"], ["5%", "−R$ 3.000", "−3,0%"], ["20%", "−R$ 12.000", "−12,0%"], ["50%", "−R$ 30.000", "−30,0%"]]),
            ("h", "Boas práticas"),
            ("ul", ["Defina antes de comprar **quanto** da carteira será cripto (muitos planos usam entre 1% e 5%).", "Prefira **aportes periódicos** a uma entrada única em um dia de euforia.", "Use **Stop Loss** para treinar a disciplina de limitar a perda.", "Evite alavancagem e aposte só em ativos que você entende."]),
            ("sim", "/mercado", "Experimentar uma posição pequena"), DISCLAIMER),
            (Q("Uma posição de 5% do patrimônio que cai 60% reduz o patrimônio em:", ["60%", "5%", "12%", "3%"], 3, "5% × 60% = 3% do patrimônio."),
             Q("O que reduz o impacto de uma queda forte em um ativo muito volátil?", ["Comprar mais após a queda sem plano", "Manter uma posição pequena em relação ao patrimônio", "Apostar tudo em um único ativo", "Ignorar o risco"], 1, "Posição pequena limita a perda máxima no conjunto."),
             Q("Aportes periódicos em vez de uma compra única ajudam a:", ["Eliminar o risco", "Garantir o menor preço", "Suavizar o preço médio de entrada", "Evitar impostos"], 2, "Comprar em datas diferentes reduz o peso de acertar o momento."))),
    ),
)
