from backend.content.schema import Lesson, Module, Q

DISCLAIMER = ("warn", "Conteúdo educacional. Não é recomendação de investimento. Regras e taxas mudam: confirme sempre a legislação vigente.")

MODULE = Module(
    id="m3", title="Ações", level="Intermediário",
    description="O que é uma ação, como ler uma cotação, dividendos, análise fundamentalista e investimentos no exterior.",
    lessons=(
        Lesson("m3-l1", "O que é uma ação", 6, "Ser sócio de uma empresa e como funciona a bolsa.", (
            ("p", "Uma **ação** é uma pequena fração do capital de uma empresa. Quem compra se torna sócio: participa dos lucros (por meio de **dividendos**) e se beneficia, ou sofre, com a valorização da empresa."),
            ("p", "As ações são negociadas na **bolsa de valores** (no Brasil, a B3). Os preços sobem e descem conforme compradores e vendedores se encontram e conforme as expectativas sobre a empresa e a economia."),
            ("h", "Tipos e códigos"),
            ("table", ["Final do código", "Tipo", "Exemplo"], [["3", "Ordinária (ON): dá direito a voto", "VALE3"], ["4", "Preferencial (PN): prioridade nos dividendos", "PETR4"], ["11", "Units: pacote de ações", "KLBN11"]]),
            ("h", "Como se ganha com ações"),
            ("ul", ["**Valorização:** vender por um preço maior que o de compra.", "**Proventos:** dividendos e juros sobre capital próprio (JCP).", "Ambos podem ser negativos: o preço pode cair e a empresa pode cortar proventos."]),
            ("warn", "Diferente da renda fixa, não há valor garantido. O preço pode cair mesmo que a empresa continue lucrativa."),
            ("tip", "No simulador, compre ações por quantidade inteira. Para acompanhar o resultado, use o preço médio e o lucro mostrados na Carteira."),
            ("sim", "/mercado", "Ver ações brasileiras e americanas"), DISCLAIMER),
            (Q("Ao comprar uma ação você se torna:", ["Credor da empresa", "Sócio da empresa", "Cliente do banco", "Fiador da empresa"], 1, "A ação é uma fração do capital, ou seja, você é sócio."),
             Q("Em geral, qual código é de uma ação preferencial (PN)?", ["Terminado em 3", "Terminado em 11", "Terminado em 4", "Terminado em 0"], 2, "O final 4 indica ação preferencial."),
             Q("Uma ação pode gerar ganho por:", ["Apenas valorização", "Valorização e proventos", "Apenas proventos garantidos", "Somente juros fixos"], 1, "Há ganho de capital (valorização) e proventos (dividendos e JCP)."))),

        Lesson("m3-l2", "Como ler uma cotação", 6, "Preço, variação, volume, liquidez e a diferença entre compra e venda.", (
            ("p", "A **cotação** é o preço da última negociação. A variação do dia compara esse preço com o fechamento anterior."),
            ("ul", ["**Variação (%):** (preço atual − fechamento anterior) ÷ fechamento anterior.", "**Volume:** quantidade ou valor negociado. Volume alto indica interesse e liquidez.", "**Máxima e mínima do dia:** os extremos de preço no pregão."]),
            ("h", "Compra, venda e spread"),
            ("p", "Em qualquer mercado existe um preço que compradores aceitam pagar (**bid**) e um preço que vendedores aceitam receber (**ask**). A diferença é o **spread**. Em ativos muito líquidos o spread é mínimo; em ativos pouco negociados pode ser grande, e você paga esse custo ao entrar e sair."),
            ("h", "Liquidez"),
            ("p", "Ativos líquidos podem ser comprados e vendidos rapidamente sem mexer no preço. Ações de empresas pequenas ou pouco negociadas podem ser difíceis de vender no momento que você quiser."),
            ("tip", "No simulador, as ordens são executadas ao preço atual, sem corretagem e sem spread. Na vida real, considere custos e liquidez."),
            ("sim", "/mercado", "Ver preço e variação do dia"), DISCLAIMER),
            (Q("O spread é:", ["O imposto da operação", "A diferença entre o preço de compra e o de venda", "O volume do dia", "O rendimento da ação"], 1, "É a diferença entre o que compradores pagam (bid) e o que vendedores pedem (ask)."),
             Q("Ativos com liquidez alta:", ["São difíceis de vender", "Têm spread mínimo e são negociados com facilidade", "Não oscilam", "Não pagam dividendos"], 1, "Liquidez é a facilidade de negociar sem mover o preço."),
             Q("Uma ação fechou a R$ 40 e agora vale R$ 42. A variação do dia é de:", ["2%", "10%", "5%", "4,2%"], 2, "(42 − 40) ÷ 40 = 5%."))),

        Lesson("m3-l3", "Dividendos e JCP", 7, "Data com, data ex, dividend yield e tributação.", (
            ("p", "Quando uma empresa lucra, pode distribuir parte aos sócios. As duas formas mais comuns no Brasil são os **dividendos** e os **juros sobre capital próprio (JCP)**."),
            ("h", "Quem tem direito: data com e data ex"),
            ("ul", ["**Data com:** último dia para comprar a ação e ter direito ao provento.", "**Data ex:** a partir dela, quem compra não recebe aquele provento. O preço costuma cair aproximadamente o valor do provento.", "**Data de pagamento:** quando o dinheiro cai na conta, geralmente dias depois."]),
            ("p", "No simulador, ter direito significa possuir o ativo **antes** da data ex. O sistema reconstrói a sua quantidade pelas transações e credita o provento na data de pagamento (estimada, pois a fonte informa só a data ex)."),
            ("formula", "Dividend yield = proventos dos últimos 12 meses ÷ preço da ação"),
            ("h", "Tributação"),
            ("ul", ["**Dividendos de ações brasileiras:** em geral isentos para pessoa física. A partir de 2026, valores mensais muito altos pagos por uma mesma empresa passam a sofrer retenção; confira a regra vigente.", "**JCP:** 15% retidos na fonte.", "**Rendimentos de FIIs:** em geral isentos para pessoa física (se atendidas as condições).", "**Dividendos de ações dos EUA:** 30% retidos na fonte (valor usado no simulador)."]),
            ("warn", "Um dividend yield muito alto pode ser um alerta: o preço pode ter caído por problemas na empresa, e o provento pode não se repetir."),
            ("sim", "/historico", "Ver seus proventos recebidos"), DISCLAIMER),
            (Q("Para ter direito a um dividendo, você precisa possuir a ação:", ["Depois da data ex", "Antes da data ex", "Somente na data de pagamento", "Por pelo menos 1 ano"], 1, "Quem compra a partir da data ex não recebe aquele provento."),
             Q("O dividend yield é:", ["O lucro da empresa", "A variação do preço no dia", "Proventos de 12 meses ÷ preço da ação", "O volume negociado"], 2, "Mede quanto a ação pagou em proventos em relação ao seu preço."),
             Q("Qual provento tem 15% de IR retido na fonte?", ["Dividendos de ações brasileiras", "JCP", "Rendimentos de LCI", "Rendimentos de FIIs"], 1, "O JCP sofre retenção de 15% na fonte."))),

        Lesson("m3-l4", "Análise fundamentalista básica", 8, "P/L, P/VP, ROE, dívida e margens: como avaliar uma empresa.", (
            ("p", "A **análise fundamentalista** estuda a saúde e o valor de uma empresa: lucros, dívidas, crescimento e qualidade da gestão. O objetivo é saber se o preço é razoável para o que a empresa entrega."),
            ("table", ["Indicador", "O que mostra", "Leitura"], [
                ["P/L (Preço/Lucro)", "Quantos anos de lucro o preço representa", "Alto: caro ou crescimento esperado. Baixo: barato ou problemas"],
                ["P/VP (Preço/Valor patrimonial)", "Preço comparado ao patrimônio contábil", "Abaixo de 1 pode indicar desconto, mas verifique o motivo"],
                ["ROE (Retorno sobre patrimônio)", "Lucro gerado pelo capital dos sócios", "Quanto maior e mais estável, melhor"],
                ["Dívida líquida / EBITDA", "Quantos anos de geração de caixa para pagar a dívida", "Alto aumenta o risco"],
                ["Margem líquida", "Quanto do faturamento vira lucro", "Compare com concorrentes"]]),
            ("h", "Como usar"),
            ("ul", ["Compare empresas do **mesmo setor**: bancos e mineradoras têm padrões diferentes.", "Olhe a **evolução** ao longo de anos, não um número isolado.", "Cuidado com lucros extraordinários, que distorcem o P/L.", "Leia os resultados trimestrais e as notícias da empresa."]),
            ("formula", "P/L = preço da ação ÷ lucro por ação"),
            ("warn", "Indicadores sozinhos não decidem uma compra. O mercado já conhece os números públicos: o que importa é a história por trás deles."),
            DISCLAIMER),
            (Q("Um P/L de 10 significa, aproximadamente:", ["Que a ação sobe 10% ao ano", "Que a empresa paga 10% de dividendos", "Que o preço equivale a 10 anos de lucro atual", "Que a dívida é 10 vezes o caixa"], 2, "P/L é o preço dividido pelo lucro por ação: anos de lucro para \"pagar\" o preço."),
             Q("O ROE mede:", ["A liquidez da ação", "O endividamento", "O dividendo pago", "O lucro gerado pelo capital dos sócios"], 3, "Retorno sobre o patrimônio líquido."),
             Q("A melhor forma de comparar o P/L de duas empresas é:", ["Compará-las dentro do mesmo setor", "Comparar bancos com mineradoras", "Olhar apenas um trimestre", "Ignorar a dívida"], 0, "Cada setor tem padrões diferentes de margem, dívida e múltiplos."))),

        Lesson("m3-l5", "Ações internacionais e câmbio", 7, "Como o dólar entra na conta quando você investe no exterior.", (
            ("p", "Ações como Apple, Microsoft e Nvidia são negociadas em **dólares**. Ao investir nelas pelo simulador, o valor é convertido em reais na hora da operação, e o seu resultado em reais depende de **duas coisas**: o preço do ativo em dólar **e** a cotação do dólar."),
            ("formula", "Preço em reais = preço em US$ × cotação do dólar (R$/US$)"),
            ("h", "Exemplo"),
            ("p", "Você compra 1 ação por US$ 300 com o dólar a R$ 5,20: paga R$ 1.560. Depois, a ação sobe 10% para US$ 330, mas o dólar cai para R$ 4,80: sua ação vale R$ 1.584, ganho de apenas **1,5%**. Se o dólar tivesse subido, o ganho seria maior."),
            ("h", "Pontos de atenção"),
            ("ul", ["**Risco cambial:** o dólar pode ajudar ou atrapalhar.", "**Diversificação:** ter parte da carteira em dólar protege contra crises locais.", "**Dividendos americanos:** têm retenção de 30% na fonte (aplicada no simulador).", "**Impostos:** ganhos em ativos no exterior têm tributação própria e exigem declaração."]),
            ("tip", "A página de cada ativo mostra o preço em dólar, o câmbio usado e o preço convertido em reais."),
            ("sim", "/mercado", "Ver ações dos EUA"), DISCLAIMER),
            (Q("Você comprou uma ação a US$ 100 com o dólar a R$ 5. O preço continua US$ 100, mas o dólar vai a R$ 6. Seu investimento em reais:", ["Valoriza 20%", "Fica igual", "Perde 20%", "Perde 10%"], 0, "100 × 6 = R$ 600 contra R$ 500 pagos: alta de 20%."),
             Q("Qual imposto é retido nos dividendos de ações americanas no simulador?", ["15%", "30%", "Isento", "22,5%"], 1, "Os EUA retêm 30% na fonte para investidores brasileiros."),
             Q("Investir no exterior ajuda a:", ["Eliminar todo o risco", "Garantir lucro em dólar", "Eliminar impostos", "Diversificar a carteira fora da economia local"], 3, "É uma forma de diversificar geograficamente e em moeda."))),
    ),
)
