from backend.content.schema import Lesson, Module, Q

DISCLAIMER = ("warn", "Conteúdo educacional. Análise técnica trabalha com probabilidades, não com certezas, e não prevê o futuro. Não é recomendação de investimento.")

MODULE = Module(
    id="m6", title="Análise técnica", level="Avançado",
    description="Candles, médias móveis, osciladores, suporte e resistência, volume e volatilidade: as ferramentas do gráfico do simulador.",
    lessons=(
        Lesson("m6-l1", "Gráficos, candles e tendência", 7, "Como ler um candle e identificar a direção do preço.", (
            ("p", "A **análise técnica** estuda o comportamento do preço e do volume no gráfico, partindo da ideia de que o preço já reflete as informações conhecidas e de que os movimentos tendem a formar padrões."),
            ("h", "Anatomia de um candle"),
            ("p", "Cada candle resume um período (um dia, 15 minutos...) com quatro preços: **abertura, máxima, mínima e fechamento**."),
            ("ul", ["**Corpo:** vai da abertura ao fechamento. Verde: fechou acima da abertura (alta). Vermelho: fechou abaixo (baixa).", "**Pavios (sombras):** mostram a máxima e a mínima. Um pavio longo indica que o preço foi rejeitado naquela região.", "**Doji:** abertura quase igual ao fechamento, sinal de indecisão."]),
            ("h", "Tendência"),
            ("table", ["Tendência", "Como identificar"], [["Alta", "Topos e fundos cada vez mais altos"], ["Baixa", "Topos e fundos cada vez mais baixos"], ["Lateral", "Preço oscilando em uma faixa"]]),
            ("tip", "No gráfico do simulador, troque entre candles e linha, escolha períodos de 1 dia a máximo e use a roda do mouse para o zoom. Tendências aparecem melhor em períodos mais longos."),
            ("sim", "/mercado", "Abrir um gráfico"), DISCLAIMER),
            (Q("Um candle de alta (verde) é aquele em que:", ["O fechamento ficou acima da abertura", "A abertura ficou acima do fechamento", "O volume foi maior que ontem", "A máxima foi igual à mínima"], 0, "Fechar acima da abertura forma o corpo de alta."),
             Q("Uma tendência de alta é caracterizada por:", ["Topos e fundos cada vez mais baixos", "Preço sem nenhum movimento", "Topos e fundos cada vez mais altos", "Volume nulo"], 2, "Topos e fundos ascendentes indicam tendência de alta."),
             Q("O pavio superior de um candle mostra:", ["O preço de abertura", "O volume negociado", "O preço médio do dia", "O preço máximo atingido além do corpo"], 3, "É o ponto mais alto atingido no período."))),

        Lesson("m6-l2", "Médias móveis e Bandas de Bollinger", 7, "Suavizando o preço para enxergar a tendência.", (
            ("p", "Uma **média móvel** calcula a média dos últimos N fechamentos, atualizada a cada candle. Ela suaviza o ruído e mostra a direção da tendência."),
            ("table", ["Tipo", "Como calcula", "Característica"], [["SMA (simples)", "Média aritmética dos N últimos fechamentos", "Mais lenta"], ["EMA (exponencial)", "Dá mais peso aos preços recentes", "Reage mais rápido"]]),
            ("ul", ["As médias de **20, 50 e 200** períodos são as mais usadas.", "**Cruzamento:** quando a média curta cruza para cima da longa, costuma-se ver força de alta (\"cruz dourada\" com 50 e 200); para baixo, fraqueza (\"cruz da morte\").", "Médias **atrasam**: confirmam o movimento depois que ele começou."]),
            ("h", "Bandas de Bollinger"),
            ("p", "Formadas por uma média de 20 períodos e duas bandas a **2 desvios-padrão** acima e abaixo. Quando a volatilidade aumenta, as bandas se afastam; quando diminui, se aproximam (\"aperto\" que costuma anteceder um movimento forte)."),
            ("warn", "Preço encostando na banda não é, sozinho, um sinal de compra ou venda: em tendências fortes ele pode \"andar\" na banda por muito tempo."),
            ("tip", "No simulador: Indicadores → Sobre o gráfico. Adicione SMA 20, SMA 50 e Bollinger e observe como reagem."),
            ("sim", "/mercado", "Testar no gráfico"), DISCLAIMER),
            (Q("Qual média dá mais peso aos preços recentes?", ["SMA", "Mediana", "EMA", "Média geométrica"], 2, "A exponencial pondera mais os últimos preços."),
             Q("A média curta cruzando para cima da longa costuma ser lida como:", ["Possível força de alta", "Garantia de lucro", "Sinal de baixa", "Erro de cálculo"], 0, "É interpretado como início de força compradora, mas sem garantia."),
             Q("As Bandas de Bollinger padrão usam:", ["Média de 5 períodos ± 1 desvio", "Máximas e mínimas do ano", "Média de 20 períodos ± 2 desvios-padrão", "Volume e preço"], 2, "Média de 20 períodos com bandas a 2 desvios-padrão."))),

        Lesson("m6-l3", "RSI, MACD e Estocástico", 8, "Osciladores: medindo força e momento.", (
            ("p", "**Osciladores** mostram a força do movimento recente em um painel abaixo do preço. Ajudam a notar exageros e perda de força."),
            ("h", "RSI (Índice de Força Relativa)"),
            ("p", "Varia de 0 a 100 e compara ganhos e perdas dos últimos 14 períodos. Acima de **70** indica **sobrecompra** (subiu rápido demais); abaixo de **30**, **sobrevenda**."),
            ("h", "MACD"),
            ("formula", "MACD = EMA de 12 − EMA de 26 | Sinal = EMA de 9 do MACD | Histograma = MACD − Sinal"),
            ("p", "Quando o MACD cruza acima da linha de sinal, o momentum melhora; abaixo, piora. O histograma mostra a distância entre as duas linhas."),
            ("h", "Estocástico"),
            ("p", "Compara o fechamento com a faixa de preços dos últimos 14 períodos. Acima de 80 sinaliza região alta; abaixo de 20, região baixa. Tem duas linhas: %K (mais rápida) e %D (média do %K)."),
            ("warn", "Em tendências fortes, os osciladores ficam \"sobrecomprados\" por muito tempo. Use-os para confirmar o contexto, nunca como único motivo para operar."),
            ("sim", "/mercado", "Adicionar RSI e MACD ao gráfico"), DISCLAIMER),
            (Q("Um RSI acima de 70 costuma indicar:", ["Sobrevenda", "Volume baixo", "Sobrecompra", "Queda garantida"], 2, "Sinaliza que o ativo subiu rápido, mas não garante reversão."),
             Q("O MACD é calculado como:", ["SMA 50 − SMA 200", "RSI ÷ 2", "Volume − preço", "EMA de 12 − EMA de 26"], 3, "É a diferença entre duas médias exponenciais."),
             Q("Em uma tendência de alta forte, o RSI:", ["Pode ficar acima de 70 por bastante tempo", "Nunca passa de 50", "Fica sempre em 30", "Deixa de funcionar e some"], 0, "Sobrecompra pode persistir em tendências fortes."))),

        Lesson("m6-l4", "Suporte, resistência e linhas de tendência", 7, "Desenhando no gráfico as regiões onde o preço reage.", (
            ("p", "**Suporte** é uma região onde o preço costuma parar de cair e voltar a subir (compradores entram). **Resistência** é uma região onde o preço costuma parar de subir (vendedores aparecem). Quanto mais vezes o preço reage numa região, mais relevante ela é."),
            ("ul", ["**Rompimento:** o preço atravessa a região. Para confiar, observe se vem acompanhado de volume.", "**Troca de papel:** um suporte rompido para baixo tende a virar resistência, e uma resistência rompida para cima tende a virar suporte.", "**Falso rompimento:** o preço passa da linha e volta logo em seguida."]),
            ("h", "Linhas de tendência"),
            ("p", "Uma **linha de tendência** liga fundos (em tendência de alta) ou topos (em tendência de baixa). São necessários 2 pontos para traçar e um terceiro toque para confirmar que a linha é respeitada."),
            ("h", "No simulador"),
            ("p", "Na página do ativo, use as ferramentas **Desenhar**: linha de tendência, raio, linha horizontal, suporte, resistência e marcação. Os desenhos ficam ancorados em tempo e preço (acompanham zoom e movimento) e são **salvos** por ativo."),
            ("tip", "Selecione um desenho clicando nele e apague com a tecla Delete. Esc cancela a ferramenta."),
            ("sim", "/mercado", "Praticar no gráfico"), DISCLAIMER),
            (Q("Um suporte rompido para baixo costuma passar a funcionar como:", ["Média móvel", "Resistência", "Volume", "Dividendo"], 1, "É a chamada troca de papel entre suporte e resistência."),
             Q("Uma linha de tendência de alta liga:", ["Os topos mais baixos", "Os preços de abertura", "Apenas os pavios superiores", "Os fundos mais altos"], 3, "Em tendência de alta, a linha acompanha os fundos ascendentes."),
             Q("Um falso rompimento acontece quando:", ["O preço passa da linha e volta em seguida", "O volume é zero", "A ação paga dividendos", "O gráfico é semanal"], 0, "O preço atravessa a região mas não se sustenta do outro lado."))),

        Lesson("m6-l5", "Volume, VWAP, ATR e ADX", 8, "Participação, preço médio, volatilidade e força da tendência.", (
            ("ul", ["**Volume:** quantidade negociada. Movimentos de preço com volume alto têm mais credibilidade; rompimentos com volume baixo desconfiam-se.", "**VWAP:** preço médio do dia ponderado pelo volume. Serve como referência de \"preço justo\" intradiário: acima dele, compradores dominam o dia."]),
            ("formula", "VWAP = Σ(preço típico × volume) ÷ Σ volume   (preço típico = (máx + mín + fechamento) ÷ 3)"),
            ("h", "ATR (volatilidade)"),
            ("p", "O **ATR** é a média do **True Range** (maior valor entre máxima − mínima, |máxima − fechamento anterior| e |mínima − fechamento anterior|) em 14 períodos. Mede o quanto o ativo costuma se mover, em unidades de preço."),
            ("p", "Uso prático: posicionar o Stop Loss fora do ruído normal. Preço R$ 40 e ATR R$ 1,50: um stop a 2 × ATR fica em 40 − 3 = **R$ 37**."),
            ("h", "ADX (força da tendência)"),
            ("p", "O **ADX** mede a **força** da tendência, **sem indicar a direção**. Acima de 25 sugere tendência forte; abaixo de 20, mercado sem tendência (lateral). As linhas +DI e −DI mostram quem domina, compradores ou vendedores."),
            ("tip", "No simulador, adicione Volume, ATR e ADX em painéis separados e compare como se comportam em tendências e em movimentos laterais."),
            ("sim", "/mercado", "Abrir um gráfico"), DISCLAIMER),
            (Q("O ADX indica:", ["A direção da tendência", "O dividendo esperado", "O preço médio ponderado", "A força da tendência, não a direção"], 3, "A direção vem de +DI e −DI; o ADX mede intensidade."),
             Q("O ATR é útil principalmente para:", ["Medir a volatilidade e dimensionar o Stop Loss", "Calcular dividendos", "Medir o volume do dia", "Prever o preço de amanhã"], 0, "Mostra o movimento típico do ativo, ajudando a posicionar stops."),
             Q("O VWAP representa:", ["O maior preço do dia", "O preço médio do dia ponderado pelo volume", "A média de 200 períodos", "O fechamento anterior"], 1, "Cada preço é ponderado pela quantidade negociada nele."))),
    ),
)
