from backend.content.schema import Lesson, Module, Q

DISCLAIMER = ("warn", "Conteúdo educacional. Não é recomendação de investimento. Regras e taxas mudam: confirme sempre a legislação vigente.")

MODULE = Module(
    id="m4", title="ETFs, FIIs e REITs", level="Intermediário",
    description="Fundos negociados em bolsa: diversificação em uma só compra, renda mensal com imóveis e investimento imobiliário nos EUA.",
    lessons=(
        Lesson("m4-l1", "ETFs: fundos que replicam índices", 6, "Uma cesta de ativos comprada como se fosse uma ação.", (
            ("p", "Um **ETF** (Exchange Traded Fund) é um fundo negociado em bolsa que **replica um índice**. Com uma única compra você tem uma fatia de dezenas ou centenas de ativos."),
            ("table", ["ETF", "Índice replicado", "Mercado"], [["BOVA11", "Ibovespa", "Brasil"], ["IVVB11", "S&P 500 (em reais)", "Brasil"], ["SPY e VOO", "S&P 500", "EUA"], ["QQQ", "Nasdaq-100", "EUA"]]),
            ("h", "Vantagens"),
            ("ul", ["**Diversificação imediata** com baixo valor.", "**Custo baixo:** taxa de administração pequena.", "**Liquidez:** negocia como ação, durante o pregão.", "**Simplicidade:** acompanha o mercado em vez de tentar vencê-lo."]),
            ("h", "Pontos de atenção"),
            ("ul", ["O ETF **sobe e cai** com o índice: pode cair muito em crises.", "Existe uma pequena diferença entre o desempenho do ETF e o do índice (tracking error).", "No Brasil, o ganho de capital em ETFs de renda variável é tributado em 15%, sem a isenção de R$ 20 mil mensais das ações."]),
            ("tip", "Investir regularmente em um ETF amplo (estratégia chamada de aporte periódico) é um jeito simples de começar na renda variável."),
            ("sim", "/mercado", "Ver ETFs"), DISCLAIMER),
            (Q("O que um ETF de índice faz?", ["Tenta vencer o índice escolhendo ações", "Garante rendimento fixo", "Replica o desempenho de um índice", "Investe só em renda fixa"], 2, "ETFs de índice replicam a carteira de um índice, como o Ibovespa."),
             Q("O ETF IVVB11 replica:", ["O Ibovespa", "O S&P 500, negociado em reais", "O Nasdaq em dólar", "O CDI"], 1, "IVVB11 acompanha o S&P 500 e é negociado na B3."),
             Q("Uma vantagem importante dos ETFs é:", ["Retorno garantido", "Isenção total de impostos", "Diversificação com uma única compra", "Ausência de oscilação"], 2, "Uma cota dá exposição a muitos ativos de uma vez."))),

        Lesson("m4-l2", "Fundos imobiliários (FIIs)", 8, "Renda mensal com imóveis, tijolo e papel.", (
            ("p", "**Fundos de Investimento Imobiliário (FIIs)** reúnem o dinheiro de muitos investidores para aplicar em imóveis ou títulos do setor. As cotas são negociadas na bolsa e o fundo distribui **rendimentos mensais**."),
            ("table", ["Tipo", "O que compra", "Exemplos"], [["Tijolo", "Imóveis: galpões logísticos, shoppings, lajes", "HGLG11 (logística), XPML11 (shoppings)"], ["Papel", "Títulos de crédito imobiliário (CRI)", "KNCR11"], ["Fundo de fundos", "Cotas de outros FIIs", "Vários"]]),
            ("h", "Indicadores"),
            ("ul", ["**Dividend yield:** rendimentos dos últimos 12 meses ÷ preço da cota.", "**P/VP:** preço ÷ valor patrimonial da cota.", "**Vacância:** parcela dos imóveis sem inquilino (tijolo).", "**Inadimplência:** atraso no pagamento (papel)."]),
            ("h", "Tributação (pessoa física)"),
            ("ul", ["**Rendimentos mensais:** em geral isentos, se o fundo atender às regras (cotas negociadas em bolsa, número mínimo de cotistas).", "**Ganho de capital na venda:** 20% sobre o lucro, sem a isenção das ações."]),
            ("warn", "Juros altos tendem a derrubar o preço das cotas, e os rendimentos podem variar mês a mês. Não são renda fixa."),
            ("tip", "No simulador, FIIs geram rendimentos para quem possuía a cota antes da data ex, com pagamento estimado em 14 dias."),
            ("sim", "/mercado", "Ver FIIs"), DISCLAIMER),
            (Q("FIIs de \"tijolo\" investem principalmente em:", ["Títulos de crédito imobiliário", "Ações de construtoras", "Imóveis como galpões e shoppings", "Tesouro Direto"], 2, "Tijolo são imóveis físicos que geram aluguel."),
             Q("Os rendimentos mensais dos FIIs, em geral, para pessoa física:", ["São isentos de IR (se cumpridas as regras)", "Pagam 22,5%", "Pagam 30% na fonte", "São sempre garantidos"], 0, "Em geral são isentos, mas não garantidos."),
             Q("A vacância mede:", ["O dividendo pago", "A dívida do fundo", "A taxa de administração", "A parcela de imóveis desocupados"], 3, "Quanto maior, menor a receita de aluguel do fundo."))),

        Lesson("m4-l3", "REITs: imobiliário nos EUA", 6, "O equivalente americano dos FIIs.", (
            ("p", "**REITs** (Real Estate Investment Trusts) são empresas que possuem ou financiam imóveis geradores de renda nos EUA. A lei exige que distribuam pelo menos **90% do lucro tributável** aos acionistas, por isso costumam pagar dividendos relevantes."),
            ("table", ["REIT", "Setor", "Observação"], [["Realty Income (O)", "Imóveis comerciais", "Pagamento mensal de dividendos"], ["American Tower (AMT)", "Torres de telecomunicações", ""], ["Prologis (PLD)", "Galpões logísticos", ""]]),
            ("h", "Diferenças em relação aos FIIs brasileiros"),
            ("ul", ["Cotados em **dólar**: o câmbio afeta seu resultado.", "Dividendos com **retenção de 30%** na fonte para brasileiros (aplicada no simulador).", "Mercado maior, com mais setores (data centers, torres, saúde).", "Sensíveis aos juros americanos."]),
            ("tip", "Compare no simulador o rendimento líquido de um FII brasileiro (isento) com o de um REIT (30% retidos): o yield bruto do REIT precisa ser bem maior para empatar."),
            ("sim", "/mercado", "Ver REITs"), DISCLAIMER),
            (Q("REITs são obrigados a distribuir ao menos:", ["50% do lucro tributável", "90% do lucro tributável", "10% do lucro", "Nenhum percentual"], 1, "É a regra dos REITs nos EUA."),
             Q("O dividendo de um REIT americano no simulador sofre retenção de:", ["Isento", "15%", "30%", "22,5%"], 2, "A retenção na fonte para brasileiros é de 30%."),
             Q("Além do preço do imóvel, o resultado de um REIT em reais depende de:", ["Do dólar", "Do CDI", "Da inflação brasileira apenas", "Da Selic apenas"], 0, "O ativo é cotado em dólar, então o câmbio entra na conta."))),
    ),
)
