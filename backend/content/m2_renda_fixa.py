from backend.content.schema import Lesson, Module, Q

DISCLAIMER = ("warn", "Conteúdo educacional. Não é recomendação de investimento. Regras e taxas mudam: confirme sempre a legislação vigente.")

MODULE = Module(
    id="m2", title="Renda fixa", level="Iniciante",
    description="Tesouro Direto, CDB, LCI, LCA, CRI, CRA e debêntures: como rendem, quais os riscos e como são tributados.",
    lessons=(
        Lesson("m2-l1", "O que é renda fixa", 6, "Prefixado, pós-fixado e híbrido; emissores e o FGC.", (
            ("p", "Em **renda fixa**, você empresta dinheiro a um emissor (governo, banco ou empresa) e recebe de volta o valor mais juros, seguindo uma **regra de remuneração definida na contratação**. \"Fixa\" refere-se à regra, não a um rendimento garantido: o preço pode oscilar antes do vencimento e o emissor pode falhar."),
            ("h", "Três formas de remuneração"),
            ("table", ["Tipo", "Como rende", "Exemplo"], [
                ["Prefixado", "Taxa fixa conhecida na compra", "14% ao ano"],
                ["Pós-fixado", "Acompanha um índice (CDI ou Selic)", "110% do CDI"],
                ["Híbrido", "Inflação + taxa fixa", "IPCA + 7% ao ano"]]),
            ("h", "Quem emite"),
            ("ul", ["**Governo:** Tesouro Direto, com garantia do Tesouro Nacional.",
                    "**Bancos:** CDB, LCI, LCA, protegidos pelo FGC dentro do limite.",
                    "**Empresas e securitizadoras:** debêntures, CRI, CRA, sem FGC e com risco de crédito maior."]),
            ("h", "FGC"),
            ("p", "O Fundo Garantidor de Créditos protege depósitos e alguns títulos bancários (CDB, LCI, LCA) até **R$ 250 mil por CPF em cada instituição**, com limite global de R$ 1 milhão a cada 4 anos. Não cobre Tesouro (que tem garantia do governo), debêntures, CRI, CRA nem fundos."),
            ("tip", "Quanto maior a taxa oferecida, mais você deve perguntar: por que esse emissor paga tanto? Normalmente é porque o risco é maior."),
            ("sim", "/renda-fixa", "Ver os produtos disponíveis"), DISCLAIMER),
            (Q("Um investimento que paga 110% do CDI é classificado como:", ["Prefixado", "Híbrido", "Pós-fixado", "Variável"], 2, "Acompanha um índice (CDI), então é pós-fixado."),
             Q("O FGC cobre, no limite de R$ 250 mil por CPF por instituição:", ["Debêntures", "CDB, LCI e LCA", "Ações", "CRI e CRA"], 1, "O FGC protege depósitos e títulos bancários como CDB, LCI e LCA."),
             Q("Renda fixa significa que o rendimento é garantido?", ["Sim, sempre", "Sim, se for de banco grande", "Não: a regra é definida, mas há risco de preço e de crédito", "Sim, se for acima do CDI"], 2, "A regra de remuneração é conhecida, mas o emissor pode falhar e o preço pode oscilar antes do vencimento."))),

        Lesson("m2-l2", "Selic, CDI e IPCA", 6, "Os índices que movem a renda fixa brasileira.", (
            ("p", "Quase toda a renda fixa brasileira é referenciada em três índices. Entender cada um é entender como seu dinheiro rende."),
            ("h", "Selic"),
            ("p", "A **taxa Selic** é a taxa básica de juros da economia. Quem define a meta é o **Copom**, do Banco Central, em reuniões ao longo do ano. Quando a Selic sobe, a renda fixa pós-fixada rende mais, e o crédito fica mais caro."),
            ("h", "CDI"),
            ("p", "O **CDI** é a taxa média dos empréstimos entre bancos. Anda muito próximo da Selic (um pouco abaixo) e é o principal **benchmark** da renda fixa. \"CDB de 100% do CDI\" rende o mesmo que o CDI; 110% rende 10% a mais."),
            ("h", "IPCA"),
            ("p", "O **IPCA** é a inflação oficial. Títulos \"IPCA +\" pagam a inflação do período mais uma **taxa real** fixa, protegendo o poder de compra."),
            ("table", ["Índice", "O que mede", "Quem usa"], [
                ["Selic", "Juros básicos da economia", "Tesouro Selic"],
                ["CDI", "Juros entre bancos (referência)", "CDB, LCI, LCA, debêntures"],
                ["IPCA", "Inflação ao consumidor", "Tesouro IPCA+, CRI, debêntures incentivadas"]]),
            ("tip", "O simulador busca CDI, Selic, IPCA e IGP-M diretamente do **Banco Central** (série SGS). Para datas futuras ele projeta: mantém a última taxa diária do CDI e usa a média dos últimos 12 meses para a inflação."),
            ("sim", "/renda-fixa", "Ver CDI, Selic e IPCA atuais"), DISCLAIMER),
            (Q("Quem define a meta da taxa Selic?", ["O Tesouro Nacional", "O IBGE", "A B3", "O Copom do Banco Central"], 3, "O Comitê de Política Monetária (Copom) fixa a meta da Selic."),
             Q("Um CDB que paga 120% do CDI rende:", ["20% a mais que o CDI", "20% ao ano", "Igual ao CDI", "O CDI menos 20%"], 0, "120% do CDI é 1,2 vez o CDI, ou seja, 20% a mais."),
             Q("Um título \"IPCA + 7%\" paga:", ["7% ao ano fixos", "A inflação do período mais 7% ao ano", "O CDI mais 7%", "A Selic menos 7%"], 1, "Inflação (IPCA) mais uma taxa real de 7% ao ano."))),

        Lesson("m2-l3", "Tesouro Direto", 8, "Selic, Prefixado, IPCA+ e a marcação a mercado.", (
            ("p", "O **Tesouro Direto** é o programa em que você empresta dinheiro ao governo federal. É considerado o investimento de menor risco de crédito do país. Pelo simulador, você acompanha os títulos reais publicados pelo Tesouro Nacional."),
            ("table", ["Título", "Rendimento", "Para quem"], [
                ["Tesouro Selic", "Selic (+ pequeno ágio/deságio)", "Reserva de emergência, curto prazo"],
                ["Tesouro Prefixado", "Taxa fixa conhecida na compra", "Quem acredita que os juros vão cair"],
                ["Tesouro IPCA+", "Inflação + taxa real", "Longo prazo, proteção contra inflação"],
                ["Com juros semestrais", "Paga os juros a cada 6 meses", "Quem quer renda periódica"]]),
            ("h", "Marcação a mercado"),
            ("p", "Antes do vencimento, o preço dos títulos Prefixado e IPCA+ **oscila** conforme os juros de mercado. Se os juros sobem, o preço cai; se caem, o preço sobe. Se você segurar até o vencimento, recebe exatamente o contratado; se vender antes, recebe o **preço de mercado** do dia, que pode ser menor que o aplicado."),
            ("p", "É por isso que, ao comprar e vender o mesmo título no mesmo dia, você perde um pouco: a taxa de compra é menor que a de venda (o spread)."),
            ("tip", "O Tesouro Selic tem oscilação muito baixa, por isso costuma ser usado na reserva de emergência. A liquidez é diária (resgate no próximo dia útil)."),
            ("warn", "A B3 cobra taxa de custódia sobre títulos do Tesouro (0,20% ao ano, com isenções). O simulador não cobra essa taxa."),
            ("sim", "/renda-fixa", "Ver títulos do Tesouro"), DISCLAIMER),
            (Q("O que acontece com o preço de um Tesouro Prefixado quando os juros de mercado sobem?", ["Sobe", "Cai", "Não muda", "Vira pós-fixado"], 1, "Taxas maiores descontam mais o valor futuro: o preço de venda antecipada cai."),
             Q("Qual título costuma ser usado em reserva de emergência por ter baixa oscilação?", ["Tesouro IPCA+ longo", "Tesouro Prefixado longo", "Tesouro Selic", "Debênture"], 2, "O Tesouro Selic rende a Selic e quase não oscila."),
             Q("Se você mantém um Tesouro Prefixado até o vencimento, recebe:", ["O preço de mercado do dia da venda", "Sempre menos que o aplicado", "O que for a Selic na época", "O valor contratado na compra"], 3, "Mantido até o vencimento, vale a taxa contratada."))),

        Lesson("m2-l4", "CDB, LCI e LCA", 8, "Títulos bancários: liquidez, carência, FGC e isenção de IR.", (
            ("p", "**CDB** é um empréstimo que você faz ao banco. **LCI** e **LCA** são letras de crédito lastreadas em crédito imobiliário e do agronegócio. Os três têm a proteção do FGC (até o limite) e podem ser pré, pós ou híbridos."),
            ("h", "Liquidez e carência"),
            ("ul", ["**Liquidez diária:** você resgata quando quiser (pode ter carência no início).",
                    "**No vencimento:** só recebe ao final do prazo.",
                    "**Janelas de resgate:** datas específicas para sacar."]),
            ("p", "LCI e LCA têm prazo mínimo de carência (em geral 90 dias) e **não pagam imposto de renda** para pessoa física. O CDB paga IR pela tabela regressiva."),
            ("h", "CDB ou LCI? Compare o rendimento líquido"),
            ("p", "Uma LCI de 92% do CDI equivale, depois do imposto, a um CDB com percentual maior:"),
            ("table", ["Prazo do CDB", "IR", "CDB que empata com LCI de 92% do CDI"], [
                ["Até 180 dias", "22,5%", "≈ 118,7% do CDI"], ["181 a 360 dias", "20%", "≈ 115,0% do CDI"],
                ["361 a 720 dias", "17,5%", "≈ 111,5% do CDI"], ["Acima de 720 dias", "15%", "≈ 108,2% do CDI"]]),
            ("tip", "Compare sempre pelo **rendimento líquido**. Com o CDI a 13,65% ao ano, um CDB de 110% rende bruto 15,0% ao ano; após 15% de IR, 12,8%. Uma LCI de 92% rende 12,6% isenta."),
            ("sim", "/renda-fixa", "Comparar CDB, LCI e LCA"), DISCLAIMER),
            (Q("Qual dos produtos é isento de imposto de renda para pessoa física?", ["CDB", "LCI", "Tesouro Selic", "Tesouro Prefixado"], 1, "LCI e LCA são isentas de IR para pessoa física."),
             Q("O que significa um CDB com liquidez \"no vencimento\"?", ["Você pode resgatar a qualquer dia", "Só pode resgatar no fim do prazo", "Não paga juros", "É coberto pelo Tesouro"], 1, "Resgate antecipado normalmente não é permitido nesse tipo."),
             Q("Para comparar um CDB com uma LCI, o correto é:", ["Comparar só a taxa bruta", "Olhar só o prazo", "Escolher o maior percentual do CDI", "Comparar o rendimento líquido, depois do imposto"], 3, "O imposto muda o resultado: por isso a comparação é pelo líquido."))),

        Lesson("m2-l5", "CRI, CRA e debêntures", 7, "Crédito privado: mais retorno, mais risco.", (
            ("p", "**Debêntures** são dívidas emitidas por empresas. **CRI** e **CRA** são certificados de recebíveis imobiliários e do agronegócio, emitidos por securitizadoras com lastro em recebíveis. Costumam pagar mais que a renda fixa bancária, porque o risco é maior."),
            ("table", ["Produto", "Garantia", "Imposto de renda (pessoa física)", "Liquidez"], [
                ["Debênture comum", "Sem FGC", "Tabela regressiva", "Baixa"],
                ["Debênture incentivada (infraestrutura)", "Sem FGC", "Isenta", "Baixa"],
                ["CRI e CRA", "Sem FGC", "Isentos", "Baixa"]]),
            ("h", "Cuidados"),
            ("ul", ["**Risco de crédito:** se o devedor não pagar, você pode perder parte do investimento. Avalie a nota de risco (rating) e o lastro.",
                    "**Liquidez baixa:** vender antes do vencimento depende do mercado secundário, geralmente com deságio. No simulador, esse deságio aparece no produto.",
                    "**Juros periódicos:** muitos pagam juros mensais, semestrais ou anuais, e o principal volta no vencimento.",
                    "**Concentração:** não coloque grande parte do patrimônio em um único emissor."]),
            ("tip", "Os CRI, CRA e debêntures do simulador são **ofertas de exemplo**, com emissores fictícios e taxas derivadas do CDI e do IPCA. Servem para praticar, não são ofertas reais."),
            ("sim", "/renda-fixa", "Ver ofertas de crédito privado"), DISCLAIMER),
            (Q("Qual proteção do FGC cobre CRI e CRA?", ["Até R$ 250 mil", "Até R$ 1 milhão", "Metade do valor", "Nenhuma: CRI e CRA não têm FGC"], 3, "CRI, CRA e debêntures não têm cobertura do FGC."),
             Q("Por que esses produtos costumam pagar mais que um CDB?", ["Porque são do governo", "Porque o risco de crédito e a baixa liquidez são maiores", "Porque são isentos de risco", "Porque têm liquidez diária"], 1, "Mais risco e menos liquidez exigem uma remuneração maior."),
             Q("Vender um CRI antes do vencimento normalmente envolve:", ["Resgate imediato sem custo", "Perda total do capital", "Mercado secundário, possivelmente com deságio", "Cobertura do Tesouro"], 2, "A liquidez depende do mercado secundário e o preço pode vir com desconto."))),

        Lesson("m2-l6", "Imposto de renda e IOF", 6, "Tabela regressiva, IOF nos primeiros 30 dias e produtos isentos.", (
            ("p", "Na renda fixa, o imposto de renda incide **só sobre o rendimento** (não sobre o valor aplicado) e é retido na fonte, na hora do resgate ou do pagamento de juros. Quanto mais tempo o dinheiro fica aplicado, menor a alíquota."),
            ("table", ["Prazo da aplicação", "Alíquota de IR"], [["Até 180 dias", "22,5%"], ["De 181 a 360 dias", "20%"], ["De 361 a 720 dias", "17,5%"], ["Acima de 720 dias", "15%"]]),
            ("h", "IOF"),
            ("p", "Resgates em **menos de 30 dias** pagam também IOF sobre o rendimento, em percentual regressivo: 96% no 1º dia, caindo até 3% no 29º. A partir do 30º dia, não há IOF. Quando existe IOF, ele é descontado antes do cálculo do IR."),
            ("p", "Exemplo: rendimento de R$ 100 resgatado no 10º dia. IOF de 66% = R$ 66. IR de 22,5% sobre os R$ 34 restantes = R$ 7,65. Você fica com R$ 26,35 do rendimento."),
            ("h", "Quem é isento"),
            ("ul", ["LCI, LCA, CRI, CRA e debêntures incentivadas, para pessoa física.", "Poupança também é isenta, mas costuma render menos que as alternativas."]),
            ("tip", "O simulador aplica a tabela regressiva e o IOF nos resgates, cupons e vencimentos, e mostra o imposto estimado antes de você resgatar."),
            ("sim", "/renda-fixa", "Ver o imposto estimado nas suas aplicações"), DISCLAIMER),
            (Q("O imposto de renda da renda fixa incide sobre:", ["Todo o valor resgatado", "Apenas o rendimento", "Apenas o valor aplicado", "O valor aplicado mais a inflação"], 1, "A base de cálculo é o rendimento, não o principal."),
             Q("Qual a alíquota de IR para uma aplicação resgatada com mais de 720 dias?", ["22,5%", "20%", "15%", "17,5%"], 2, "Acima de 720 dias a alíquota é de 15%."),
             Q("O IOF na renda fixa se aplica a resgates com:", ["Qualquer prazo", "Mais de 2 anos", "Menos de 30 dias", "Entre 6 e 12 meses"], 2, "O IOF só cobra nos primeiros 29 dias."))),
    ),
)
