from backend.content.schema import Lesson, Module, Q

DISCLAIMER = ("warn", "Conteúdo educacional. Não é recomendação de investimento. Os exemplos de alocação são ilustrativos, não personalizados.")

MODULE = Module(
    id="m7", title="Gestão de risco e estratégia", level="Avançado",
    description="Diversificação, Stop Loss e tamanho de posição, vieses do comportamento e como montar o seu plano.",
    lessons=(
        Lesson("m7-l1", "Diversificação e alocação de ativos", 7, "Não coloque todos os ovos na mesma cesta, mas faça isso com método.", (
            ("p", "**Diversificar** é distribuir o dinheiro entre ativos que não se movem exatamente juntos, para que a queda de um seja amenizada pelos outros. Não elimina o risco do mercado, mas reduz o risco de um único erro ser fatal."),
            ("h", "Em que diversificar"),
            ("ul", ["**Classes de ativos:** renda fixa, ações, FIIs, ETFs, criptomoedas.", "**Emissores e setores:** não concentre em uma empresa ou banco.", "**Geografia e moeda:** parte da carteira em dólar protege contra choques locais.", "**Prazo:** vencimentos escalonados na renda fixa."]),
            ("h", "A nota de diversificação do simulador"),
            ("formula", "Nota = (1 − Σ peso²) × 100, onde peso = parte de cada posição no total investido"),
            ("p", "Uma posição única dá nota 0. Quatro posições iguais dão 75; dez posições iguais, 90. Posições muito desiguais reduzem a nota, porque a carteira depende de poucas."),
            ("warn", "Diversificar não é ter dezenas de ativos parecidos. Dez ações do mesmo setor se comportam quase como uma só."),
            ("tip", "Veja sua nota e a maior posição na aba Desempenho."),
            ("sim", "/desempenho", "Ver minha diversificação"), DISCLAIMER),
            (Q("Quatro posições de valores iguais dão, pela nota do simulador:", ["25", "75", "90", "100"], 1, "(1 − 4 × 0,25²) × 100 = 75."),
             Q("Diversificar significa:", ["Comprar muitas ações do mesmo setor", "Eliminar totalmente o risco", "Distribuir entre ativos que não se movem juntos", "Investir só no que subiu"], 2, "O objetivo é reduzir a dependência de um único ativo."),
             Q("Qual alternativa aumenta a diversificação geográfica?", ["Comprar mais uma ação brasileira", "Aumentar o caixa", "Investir mais em um único banco", "Incluir ativos dos EUA"], 3, "Ativos no exterior reduzem a dependência da economia local."))),

        Lesson("m7-l2", "Stop Loss, Take Profit e tamanho da posição", 9, "Como limitar perdas e dimensionar cada operação.", (
            ("p", "**Stop Loss** vende automaticamente se o preço cair até um nível definido por você, limitando a perda. **Take Profit** vende quando o preço atinge uma meta de ganho."),
            ("h", "Tamanho da posição pelo risco"),
            ("p", "Em vez de decidir \"quanto comprar\" por impulso, decida **quanto aceita perder** (muitos usam de 1% a 2% do patrimônio por operação) e calcule a quantidade:"),
            ("formula", "Quantidade = (patrimônio × risco aceito) ÷ (preço de entrada − preço do stop)"),
            ("p", "Exemplo: patrimônio de R$ 100.000, risco de 1% (R$ 1.000). Compra a R$ 40 com stop em R$ 36: risco de R$ 4 por ação. Quantidade = 1.000 ÷ 4 = **250 ações** (R$ 10.000, ou 10% do patrimônio)."),
            ("h", "Relação risco/retorno"),
            ("p", "Se você arrisca R$ 4 por ação com um alvo de R$ 8 de ganho, a relação é de 2 para 1: acertando só 40% das vezes, ainda pode sair no positivo."),
            ("h", "No simulador"),
            ("ul", ["Os níveis são definidos na **moeda do ativo** (US$ para uma ação americana).", "O stop precisa estar **abaixo** do preço atual e o take, **acima**.", "O sistema confere a cada 2 minutos e vende a posição inteira a mercado.", "Em saltos de preço (gaps), a venda pode ocorrer **pior** que o nível: o stop não é garantia de preço."]),
            ("sim", "/carteira", "Ver minhas posições e níveis"), DISCLAIMER),
            (Q("Patrimônio de R$ 50.000, risco de 2% por operação, entrada a R$ 20 e stop a R$ 18. Quantas ações?", ["250", "500", "1.000", "100"], 1, "Risco = R$ 1.000; por ação R$ 2; 1.000 ÷ 2 = 500 ações."),
             Q("Um Stop Loss garante que a venda ocorra exatamente no preço definido?", ["Sim, sempre", "Sim, se for dia útil", "Não: em saltos de preço a execução pode ser pior", "Sim, nos ativos dos EUA"], 2, "Gaps podem fazer a execução sair abaixo do nível."),
             Q("Com relação risco/retorno de 2 para 1, quem acerta 40% das operações:", ["Sempre perde dinheiro", "Pode ter resultado positivo", "Não paga imposto", "Garante 40% ao ano"], 1, "Ganhos maiores que as perdas compensam uma taxa de acerto menor."))),

        Lesson("m7-l3", "Vieses de comportamento", 7, "Os erros que a nossa cabeça comete quando o dinheiro está em jogo.", (
            ("p", "Investir bem é mais **comportamento** do que cálculo. Alguns vieses prejudicam quase todos os investidores:"),
            ("table", ["Viés", "Como aparece", "Antídoto"], [
                ["FOMO (medo de ficar de fora)", "Comprar depois de grande alta, por euforia", "Ter plano e valor de entrada definidos"],
                ["Aversão à perda", "Segurar o que caiu esperando \"voltar\" e vender cedo o que subiu", "Stop Loss e metas de saída definidas antes"],
                ["Excesso de confiança", "Achar que acerta mais do que acerta, e operar demais", "Registrar suas operações e medir o resultado"],
                ["Ancoragem", "Fixar-se no preço de compra", "Perguntar: compraria hoje, a este preço?"],
                ["Viés de confirmação", "Buscar só notícias que confirmam sua ideia", "Procurar argumentos contrários"]]),
            ("p", "Cada custo de operação (impostos, spreads, taxas) soma. **Operar demais** costuma piorar o resultado."),
            ("tip", "Use o Histórico e a aba Desempenho como um diário: revise seus acertos e erros, a relação ganho/perda e o que fez em momentos de queda."),
            ("sim", "/historico", "Revisar minhas operações"), DISCLAIMER),
            (Q("O efeito de segurar perdedoras esperando \"voltar\" e vender cedo as vencedoras é:", ["Ancoragem apenas", "Diversificação", "Aversão à perda", "Marcação a mercado"], 2, "Dói mais perder do que ganhar, o que distorce as decisões."),
             Q("O FOMO leva o investidor a:", ["Vender tudo na queda", "Evitar qualquer risco", "Diversificar demais", "Comprar por euforia depois de uma alta forte"], 3, "O medo de ficar de fora faz comprar tarde."),
             Q("Uma boa defesa contra vieses é:", ["Seguir um plano escrito e registrar as operações", "Operar mais vezes", "Seguir só o que a maioria faz", "Ignorar as perdas"], 0, "Regras definidas antes reduzem decisões emocionais."))),

        Lesson("m7-l4", "Montando o seu plano", 8, "Objetivo, perfil, alocação, aportes e rebalanceamento.", (
            ("p", "Um plano transforma sorte em processo. Em ordem:"),
            ("ul", ["**1. Objetivo e prazo:** para que e para quando é o dinheiro.", "**2. Reserva de emergência:** de 3 a 12 meses de despesas em liquidez diária (por exemplo, Tesouro Selic).", "**3. Perfil:** quanto de oscilação você suporta sem desistir.", "**4. Alocação-alvo:** quanto vai para cada classe.", "**5. Aportes regulares:** o hábito vale mais que acertar o momento.", "**6. Rebalanceamento:** ajustar a carteira uma ou duas vezes por ano para voltar à alocação-alvo."]),
            ("h", "Exemplos ilustrativos de alocação"),
            ("table", ["Classe", "Conservador", "Moderado", "Arrojado"], [["Renda fixa", "80%", "50%", "25%"], ["Ações e ETFs", "10%", "30%", "50%"], ["FIIs e REITs", "10%", "15%", "15%"], ["Criptomoedas", "0%", "5%", "10%"]]),
            ("p", "Esses números são apenas ilustrações educacionais. Seu plano deve refletir seu objetivo, prazo e tolerância ao risco."),
            ("h", "Rebalancear, na prática"),
            ("p", "Se ações subiram e passaram a ser 40% de uma carteira-alvo de 30%, você vende o excesso e reforça o que ficou abaixo. Isso disciplina a compra do que ficou barato e a venda do que subiu."),
            ("tip", "Use a aba Desempenho para ver a composição atual e a aba Ranking apenas como motivação: o que importa é o seu plano, não o placar."),
            ("sim", "/desempenho", "Ver a composição da minha carteira"), DISCLAIMER),
            (Q("Qual deve vir primeiro no plano de investimentos?", ["Comprar criptomoedas", "Reserva de emergência e objetivos definidos", "Escolher o ativo da moda", "Operar diariamente"], 1, "Sem reserva, qualquer imprevisto força vendas na hora errada."),
             Q("O rebalanceamento serve para:", ["Garantir lucro", "Eliminar impostos", "Voltar à alocação-alvo quando as classes se afastam dela", "Trocar todos os ativos"], 2, "Ajusta a carteira para manter o risco planejado."),
             Q("O que costuma importar mais no longo prazo?", ["Acertar o melhor dia para comprar", "Aportes regulares e disciplina", "Mudar de estratégia sempre que o mercado cai", "Seguir apenas dicas de terceiros"], 1, "Constância e disciplina superam tentar adivinhar o momento."))),
    ),
)
