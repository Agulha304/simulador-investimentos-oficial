"""Catálogo (dados) das opções de expansão da fase 5: o jogador escolhe o tipo e o nível e o servidor sorteia 3 destas opções por
(empresa, semente, mês, tipo, nível). Para acrescentar uma opção basta incluir uma linha `o(...)` na lista da família.

Cada opção: `cost` = multiplicador sobre o custo do nível; `power` = multiplicador do efeito; `risk` = soma à chance de fracasso
(negativo = aposta segura, positivo = aposta alta); `fx` = efeitos colaterais anunciados:
    storage (+x no teto de estoque) · fixed (+x% nos custos fixos recorrentes) · manager (contrata um gerente) · quit (chance de cada
    funcionário produtivo pedir demissão) · hours (+h/semana nos produtivos) · salary (+x% de salário por hora extra) ·
    rent (NEW_UNIT: multiplicador do aluguel) · viab (NEW_UNIT: viés da viabilidade) · relfrac (NEW_UNIT: + na fração de relevância)
"""
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Opt:
    key: str
    title: str
    desc: str
    cost: float = 1.0
    power: float = 1.0
    risk: float = 0.0
    note: str = ""
    fx: dict = field(default_factory=dict)


def o(key, title, desc, cost=1.0, power=1.0, risk=0.0, note="", **fx) -> Opt:
    return Opt(key, title, desc, cost, power, risk, note, fx)


FAMILIES = ("PRODUCTION", "RETAIL", "SERVICE")

# ------------------------------------------------------------------ AMPLIAR CAPACIDADE (>= 8 por família)
CAPACITY: dict[str, tuple[Opt, ...]] = {
    "PRODUCTION": (
        o("ampliar_deposito", "Ampliar o estoque/depósito", "Mais espaço para guardar insumos e produtos prontos: sobe o teto de estoque e ajuda a produzir mais.",
          1.0, 0.7, 0.0, "Energia, manutenção e instalações ficam mais caras todo mês.", storage=0.30, fixed=0.06),
        o("gerente_produtividade", "Contratar gerente que cobra produtividade", "Um gerente passa a cobrar metas da equipe e contrata mais ritmo.",
          0.9, 1.3, 0.08, "Pode render muito, mas parte da equipe pode pedir demissão.", manager=True, quit=0.12),
        o("novo_equipamento", "Comprar um novo equipamento", "Máquina ou equipamento mais rápido para o gargalo da produção.",
          1.1, 1.0, 0.0, "Manutenção do equipamento soma aos custos fixos.", fixed=0.03),
        o("turno_extra", "Criar um turno extra", "Mais horas de produção com a mesma estrutura.",
          0.6, 1.0, 0.05, "Equipe cansada: salários e risco de processo trabalhista sobem.", hours=6, salary=0.10),
        o("automatizar", "Automatizar parte do processo", "Automação do trecho mais repetitivo da produção.",
          1.5, 1.5, 0.12, "Aposta alta: pode dar muito ganho ou não se adaptar ao seu processo.", fixed=0.05),
        o("reorganizar_fluxo", "Reorganizar o layout e o fluxo de produção", "Sem obra pesada: tira gargalos e desperdício de movimentação.",
          0.5, 0.6, -0.05, "Aposta segura, ganho pequeno."),
        o("treinar_equipe", "Treinar a equipe para produzir mais", "Cursos e acompanhamento de quem já está na casa.",
          0.45, 0.5, -0.08, "Ganho pequeno, mas raramente dá errado."),
        o("segunda_linha", "Instalar uma segunda linha de produção", "Duplica o trecho que mais limita: cozinha, forno, linha ou frente de obra.",
          1.3, 1.2, 0.03, "Exige espaço e energia a mais.", fixed=0.08),
        o("terceirizar_parte", "Terceirizar parte da produção", "Um parceiro externo assume os picos de demanda.",
          0.8, 0.9, 0.10, "Qualidade e prazo do parceiro podem falhar.", fixed=0.02),
    ),
    "RETAIL": (
        o("ampliar_estoque", "Ampliar o estoque/depósito", "Mais prateleiras e depósito: sobe o teto de estoque e a capacidade de atender.",
          1.0, 0.7, 0.0, "Energia, manutenção e instalações ficam mais caras todo mês.", storage=0.30, fixed=0.06),
        o("gerente_vendas", "Contratar gerente que cobra produtividade", "Um gerente cobra metas e organiza a operação de venda.",
          0.9, 1.3, 0.08, "Pode render muito, mas parte da equipe pode pedir demissão.", manager=True, quit=0.12),
        o("novos_expositores", "Comprar novos expositores e equipamentos", "Gôndolas, frios, caixas e sistema para atender mais gente ao mesmo tempo.",
          1.1, 1.0, 0.0, "Manutenção soma aos custos fixos.", fixed=0.03),
        o("turno_extra", "Estender o horário de atendimento", "Abrir mais horas por dia com turnos adicionais.",
          0.6, 1.0, 0.05, "Equipe cansada: salários e risco de processo trabalhista sobem.", hours=6, salary=0.10),
        o("sistema_estoque", "Automatizar o controle de estoque e caixa", "Sistema integrado de reposição e autoatendimento.",
          1.5, 1.5, 0.12, "Aposta alta: pode destravar muito ou ficar subutilizado.", fixed=0.05),
        o("reorganizar_loja", "Reorganizar a loja e o fluxo de clientes", "Layout novo para reduzir filas e perdas.",
          0.5, 0.6, -0.05, "Aposta segura, ganho pequeno."),
        o("treinar_vendedores", "Treinar a equipe de vendas e reposição", "Treinamento prático e metas por turno.",
          0.45, 0.5, -0.08, "Ganho pequeno, mas raramente dá errado."),
        o("mezanino", "Construir um mezanino de vendas", "Mais área de venda sobre o espaço que já existe.",
          1.3, 1.2, 0.03, "Obra e área extra encarecem os custos fixos.", fixed=0.08, storage=0.10),
        o("parceria_logistica", "Fechar parceria logística de entrega", "Um parceiro cuida da entrega e libera a equipe do balcão.",
          0.8, 0.9, 0.10, "O parceiro pode atrasar ou cobrar mais caro.", fixed=0.02),
    ),
    "SERVICE": (
        o("gerente_operacoes", "Contratar gerente que cobra produtividade", "Um gerente de operações passa a cobrar metas e prazos.",
          0.9, 1.3, 0.08, "Pode render muito, mas parte da equipe pode pedir demissão.", manager=True, quit=0.12),
        o("novas_ferramentas", "Comprar novos equipamentos e ferramentas", "Ferramental, licenças ou veículos que aumentam o que a equipe entrega.",
          1.1, 1.0, 0.0, "Licenças e manutenção somam aos custos fixos.", fixed=0.03),
        o("plantao_extra", "Criar um turno ou plantão extra", "Mais horas de atendimento com a mesma equipe.",
          0.6, 1.0, 0.05, "Equipe cansada: salários e risco de processo trabalhista sobem.", hours=6, salary=0.10),
        o("automatizar_processos", "Automatizar processos", "Automação de tarefas repetitivas e de acompanhamento.",
          1.5, 1.5, 0.12, "Aposta alta: pode destravar muito ou não pegar na equipe.", fixed=0.05),
        o("reorganizar_agenda", "Reorganizar agenda e processos", "Metodologia nova de priorização, sem investimento pesado.",
          0.5, 0.6, -0.05, "Aposta segura, ganho pequeno."),
        o("treinar_equipe", "Treinar e certificar a equipe", "Cursos que aceleram entregas e reduzem retrabalho.",
          0.45, 0.5, -0.08, "Ganho pequeno, mas raramente dá errado."),
        o("escritorio_maior", "Ampliar o espaço de trabalho", "Mais estações e áreas de atendimento.",
          1.3, 1.2, 0.03, "O espaço maior encarece os custos fixos.", fixed=0.08),
        o("terceirizar_picos", "Terceirizar os picos com freelancers e parceiros", "Parceiros absorvem a demanda que passa da capacidade.",
          0.8, 0.9, 0.10, "A qualidade do parceiro pode oscilar.", fixed=0.02),
        o("sistema_gestao", "Implantar um sistema de gestão do serviço", "Controle de chamados, projetos ou rotas em um só lugar.",
          1.0, 0.9, 0.0, "Licença mensal soma aos custos fixos.", fixed=0.04),
    ),
}

# ------------------------------------------------------------------ NOVA UNIDADE (>= 8 por família). `rent` e `viab` são ajustes.
NEW_UNIT: dict[str, tuple[Opt, ...]] = {
    "PRODUCTION": (
        o("filial_rua", "Filial de rua tradicional", "Uma segunda casa nos mesmos moldes da matriz.", 1.0, 1.0, 0.0, "O desempenho depende do ponto e da força da marca."),
        o("quiosque", "Ponto compacto (quiosque)", "Estrutura enxuta, barata de abrir e de manter.", 0.7, 1.0, 0.0, "Vende menos por ser pequeno.", rent=0.6, viab=-0.08),
        o("shopping", "Unidade em ponto de alto fluxo", "Operação num local movimentado, com aluguel e exigências maiores.", 1.3, 1.0, 0.05, "Pode vender muito ou não cobrir o aluguel.", rent=1.4, viab=0.10),
        o("conceito", "Unidade-conceito premium", "Ponto de vitrine da marca: decoração e experiência de ponta.", 1.5, 1.0, 0.08, "Aposta alta com chance de brilhar.", rent=1.2, viab=0.15, relfrac=0.05),
        o("delivery", "Unidade focada em entregas", "Estrutura simples voltada a pedidos para viagem e entrega.", 0.8, 1.0, 0.04, "Depende de quem pede online.", rent=0.7, viab=0.0),
        o("flagship", "Unidade grande (carro-chefe)", "Ponto amplo para concentrar a produção e a marca.", 1.6, 1.0, 0.06, "Custo alto: exige muita venda.", rent=1.5, viab=0.12, relfrac=0.05),
        o("sociedade_local", "Unidade com gerente-sócio local", "Um gerente com participação toca o dia a dia.", 0.9, 1.0, -0.03, "Mais estável, mas dividir o comando limita o potencial.", viab=-0.02, relfrac=0.03),
        o("reaproveitar_ponto", "Assumir o ponto de um negócio que fechou", "Imóvel pronto, clientela de passagem e reformas leves.", 0.75, 1.0, 0.02, "Barato, mas o ponto pode ter fechado por um motivo.", rent=0.85, viab=-0.05),
        o("parceria_empresa", "Unidade dentro de uma empresa parceira", "Operação dentro de um condomínio comercial ou empresa.", 0.8, 1.0, -0.02, "Público garantido, porém limitado.", rent=0.5, viab=-0.10, relfrac=0.05),
    ),
    "RETAIL": (
        o("filial_rua", "Loja de rua tradicional", "Uma segunda loja nos mesmos moldes da matriz.", 1.0, 1.0, 0.0, "O desempenho depende do ponto e da força da marca."),
        o("quiosque", "Loja compacta ou quiosque", "Estrutura enxuta, barata de abrir e de manter.", 0.7, 1.0, 0.0, "Vende menos por ser pequena.", rent=0.6, viab=-0.08),
        o("shopping", "Loja em ponto de alto fluxo", "Operação num local movimentado, com aluguel e exigências maiores.", 1.3, 1.0, 0.05, "Pode vender muito ou não cobrir o aluguel.", rent=1.4, viab=0.10),
        o("conceito", "Loja-conceito premium", "Ponto de vitrine da marca: ambientação e experiência de ponta.", 1.5, 1.0, 0.08, "Aposta alta com chance de brilhar.", rent=1.2, viab=0.15, relfrac=0.05),
        o("pop_up", "Loja temporária que vira fixa se der certo", "Começa com contrato curto e estoque reduzido.", 0.65, 1.0, 0.03, "Barata, mas ainda sem clientela.", rent=0.7, viab=-0.05),
        o("grande_formato", "Loja de grande formato", "Mais área e variedade para atrair mais clientes por visita.", 1.6, 1.0, 0.06, "Custo alto: exige muita venda.", rent=1.5, viab=0.12, relfrac=0.05),
        o("gerente_socio", "Loja com gerente-sócio local", "Um gerente com participação toca o dia a dia.", 0.9, 1.0, -0.03, "Mais estável, mas dividir o comando limita o potencial.", viab=-0.02, relfrac=0.03),
        o("reaproveitar_ponto", "Assumir o ponto de uma loja que fechou", "Imóvel pronto, clientela de passagem e reformas leves.", 0.75, 1.0, 0.02, "Barato, mas o ponto pode ter fechado por um motivo.", rent=0.85, viab=-0.05),
        o("ilha_parceira", "Ilha ou corner dentro de outra loja", "Espaço pequeno em loja âncora com fluxo garantido.", 0.6, 1.0, -0.02, "Público garantido, porém limitado.", rent=0.5, viab=-0.10, relfrac=0.05),
    ),
    "SERVICE": (
        o("escritorio_filial", "Escritório ou base filial", "Uma segunda base nos mesmos moldes da matriz.", 1.0, 1.0, 0.0, "O desempenho depende do mercado local e da força da marca."),
        o("coworking", "Posição em espaço de coworking", "Estrutura enxuta e flexível, barata de abrir.", 0.65, 1.0, 0.0, "Menos presença de marca no local.", rent=0.6, viab=-0.08),
        o("centro_negocios", "Base em região de negócios", "Perto de grandes clientes, com aluguel e exigências maiores.", 1.3, 1.0, 0.05, "Pode abrir muitos contratos ou não cobrir o aluguel.", rent=1.4, viab=0.10),
        o("unidade_premium", "Unidade premium de relacionamento", "Sede de vitrine para clientes de maior valor.", 1.5, 1.0, 0.08, "Aposta alta com chance de brilhar.", rent=1.2, viab=0.15, relfrac=0.05),
        o("equipe_remota", "Unidade enxuta com equipe remota", "Poucos custos fixos, equipe distribuída.", 0.7, 1.0, 0.03, "Difícil criar vínculo com clientes locais.", rent=0.4, viab=-0.10),
        o("polo_regional", "Polo regional de atendimento", "Estrutura maior para atender várias cidades.", 1.6, 1.0, 0.06, "Custo alto: exige muita venda.", rent=1.5, viab=0.12, relfrac=0.05),
        o("socio_local", "Unidade com sócio local", "Um profissional da região toca a unidade.", 0.9, 1.0, -0.03, "Mais estável, mas dividir o comando limita o potencial.", viab=-0.02, relfrac=0.03),
        o("assumir_carteira", "Assumir a carteira de um concorrente local", "Clientes já existentes, mas fidelidade incerta.", 0.8, 1.0, 0.04, "Parte dos clientes pode não ficar.", rent=0.9, viab=0.02),
        o("parceria_regional", "Base dentro de um parceiro regional", "Compartilha estrutura de uma empresa parceira.", 0.8, 1.0, -0.02, "Público indicado pelo parceiro, porém limitado.", rent=0.5, viab=-0.08, relfrac=0.05),
    ),
}

# ------------------------------------------------------------------ QUALIDADE DOS PRODUTOS (>= 8 por família)
QUALITY: dict[str, tuple[Opt, ...]] = {
    "PRODUCTION": (
        o("materia_prima_premium", "Matéria-prima premium", "Insumos de fornecedores selecionados: sabor, durabilidade e acabamento melhores.", 1.1, 1.1, 0.0, "O custo dos insumos sobe junto com a qualidade."),
        o("treinamento_equipe", "Treinamento da equipe", "Cursos técnicos e padronização de receitas e processos.", 0.7, 0.8, -0.05, "Ganho moderado e seguro."),
        o("certificacao", "Certificação de qualidade", "Processo formal de certificação reconhecido pelo mercado.", 1.3, 1.2, 0.05, "Pode ser reprovada na auditoria.", fixed=0.02),
        o("controle_qualidade", "Controle de qualidade rigoroso", "Inspeção em cada etapa para reduzir defeitos.", 0.9, 0.9, -0.03, "Pequenas perdas e retrabalho no início."),
        o("consultoria", "Consultoria especializada", "Um especialista reformula padrões e fornecedores.", 1.2, 1.2, 0.06, "Depende do consultor acertar o diagnóstico."),
        o("embalagem_apresentacao", "Apresentação e embalagem melhores", "O cliente percebe mais valor no produto.", 0.6, 0.6, -0.04, "Efeito pequeno, mas barato."),
        o("auditoria_externa", "Auditoria externa e melhoria contínua", "Apontamentos independentes e plano de ação.", 0.8, 1.0, 0.0, "Resultado depende do que for achado."),
        o("reformulacao", "Reformulação completa do produto", "Reinventar o produto para um padrão superior.", 1.5, 1.5, 0.14, "Aposta alta: pode encantar ou desagradar a clientela."),
        o("pesquisa_clientes", "Pesquisa com clientes e ajustes", "Ouvir o público e corrigir o que mais incomoda.", 0.5, 0.7, -0.06, "Seguro, ganho modesto."),
    ),
    "RETAIL": (
        o("fornecedores_premium", "Linhas e fornecedores premium", "Marcas e lotes de maior qualidade nas prateleiras.", 1.1, 1.1, 0.0, "O custo das mercadorias sobe junto com a qualidade."),
        o("treinamento_equipe", "Treinamento da equipe de atendimento", "Atendimento consultivo e conhecimento de produto.", 0.7, 0.8, -0.05, "Ganho moderado e seguro."),
        o("certificacao", "Selo e certificação de procedência", "Reconhecimento formal de qualidade e origem.", 1.3, 1.2, 0.05, "Pode ser reprovada na auditoria.", fixed=0.02),
        o("curadoria", "Curadoria rigorosa do sortimento", "Cortar o que não vende bem e reforçar o que encanta.", 0.9, 0.9, -0.03, "Pequenas perdas na liquidação do que sai."),
        o("consultoria", "Consultoria de varejo", "Um especialista reformula mix, exposição e padrão de qualidade.", 1.2, 1.2, 0.06, "Depende do consultor acertar o diagnóstico."),
        o("embalagem_apresentacao", "Embalagem e apresentação melhores", "O cliente percebe mais valor na compra.", 0.6, 0.6, -0.04, "Efeito pequeno, mas barato."),
        o("auditoria_externa", "Auditoria externa e melhoria contínua", "Cliente oculto e plano de ação.", 0.8, 1.0, 0.0, "Resultado depende do que for achado."),
        o("marca_propria", "Lançar linha de marca própria", "Produtos com a sua assinatura e padrão superior.", 1.5, 1.5, 0.14, "Aposta alta: pode encantar ou encalhar."),
        o("pesquisa_clientes", "Pesquisa com clientes e ajustes", "Ouvir o público e corrigir o que mais incomoda.", 0.5, 0.7, -0.06, "Seguro, ganho modesto."),
    ),
    "SERVICE": (
        o("pecas_premium", "Componentes, peças e ferramentas premium", "Material de primeira linha nas entregas.", 1.1, 1.1, 0.0, "Os custos variáveis sobem junto com a qualidade."),
        o("treinamento_equipe", "Treinamento e reciclagem da equipe", "Cursos técnicos e padronização de procedimentos.", 0.7, 0.8, -0.05, "Ganho moderado e seguro."),
        o("certificacao", "Certificação de qualidade (ISO ou equivalente)", "Processo formal reconhecido pelo mercado.", 1.3, 1.2, 0.05, "Pode ser reprovada na auditoria.", fixed=0.02),
        o("revisao_entregas", "Revisão rigorosa de cada entrega", "Segunda checagem antes de entregar ao cliente.", 0.9, 0.9, -0.03, "Prazos ficam um pouco mais longos no início."),
        o("consultoria", "Consultoria especializada", "Um especialista reformula padrões e processos.", 1.2, 1.2, 0.06, "Depende do consultor acertar o diagnóstico."),
        o("pos_venda", "Programa de pós-venda e garantia", "Acompanhamento do cliente depois da entrega.", 0.6, 0.7, -0.04, "Efeito moderado, custo recorrente baixo."),
        o("auditoria_externa", "Auditoria externa e melhoria contínua", "Apontamentos independentes e plano de ação.", 0.8, 1.0, 0.0, "Resultado depende do que for achado."),
        o("novo_padrao", "Novo padrão de serviço premium", "Reposicionar a entrega para um nível superior.", 1.5, 1.5, 0.14, "Aposta alta: pode encantar ou desagradar a clientela."),
        o("pesquisa_clientes", "Pesquisa de satisfação e ajustes", "Ouvir os clientes e corrigir o que mais incomoda.", 0.5, 0.7, -0.06, "Seguro, ganho modesto."),
    ),
}

# ------------------------------------------------------------------ INSTALAÇÕES MAIORES (>= 8, todas as famílias)
LARGER: tuple[Opt, ...] = (
    o("reforma_ampliacao", "Reforma e ampliação do imóvel atual", "Obra no próprio ponto para ganhar área.", 1.0, 1.0, 0.0, "Obras podem atrasar e estourar o orçamento."),
    o("mudar_mesmo_bairro", "Mudar para um imóvel maior no mesmo bairro", "Mantém a clientela e muda só de espaço.", 1.1, 1.0, 0.0, "Há custo de mudança e de adaptação."),
    o("anexo", "Construir um anexo", "Novo bloco ligado ao atual.", 1.2, 1.0, 0.04, "Depende de licença e de terreno livre."),
    o("alugar_vizinho", "Alugar o imóvel ao lado e abrir a parede", "Rápido e pouco burocrático.", 0.8, 0.9, 0.02, "O vizinho pode não aceitar ou encarecer."),
    o("mezanino", "Construir um mezanino", "Dobra a área útil sem ocupar mais chão.", 0.9, 0.9, 0.03, "Exige cálculo estrutural e aprovação."),
    o("empreitada", "Obra por empreitada (mais barata)", "Preço fechado com um empreiteiro pequeno.", 0.7, 1.0, 0.10, "Barata, mas qualidade e prazo variam."),
    o("projeto_arquiteto", "Obra com projeto de arquiteto", "Planejamento completo, execução controlada.", 1.3, 1.0, -0.06, "Cara, porém previsível."),
    o("turn_key", "Obra completa com empresa especializada", "Chave na mão, com garantia.", 1.5, 1.0, -0.08, "A mais cara e a mais segura."),
    o("galpao_modular", "Estrutura modular pré-fabricada", "Montagem rápida de módulos adicionais.", 0.85, 0.9, 0.05, "Rápida, mas pode limitar o acabamento."),
)

# ------------------------------------------------------------------ CAMPANHAS DE PUBLICIDADE (>= 6 por segmento)
CAMPAIGNS: dict[str, tuple[Opt, ...]] = {
    "RESTAURANT": (
        o("amostras_escola", "Levar amostras da comida a uma escola", "Pratos-teste para alunos, famílias e professores.", 0.7, 0.9, 0.02, "Barata, mas depende de aceitação."),
        o("app_entrega", "Parceria com aplicativo de entrega", "Destaque no app com taxa promocional.", 1.2, 1.2, 0.04, "Pode lotar os pedidos ou só reduzir sua margem."),
        o("degustacao_gratis", "Dia de degustação gratuita", "Cardápio reduzido de graça por um dia.", 0.9, 1.0, 0.0, "Atrai gente, nem sempre converte em clientes."),
        o("influenciador", "Influenciador gastronômico local", "Visita e vídeos de um criador da cidade.", 1.3, 1.4, 0.10, "Pode viralizar ou passar despercebido."),
        o("promocao_almoco", "Promoção de almoço executivo", "Prato do dia com desconto para empresas próximas.", 0.8, 0.9, -0.02, "Público fiel, alcance limitado."),
        o("evento_chef", "Noite com chef convidado", "Evento especial com divulgação em jornais e redes.", 1.4, 1.3, 0.08, "Pode virar assunto na cidade."),
        o("outdoor_bairro", "Anúncio em rádio e outdoor do bairro", "Presença na vizinhança por algumas semanas.", 1.0, 0.8, -0.04, "Retorno estável, sem grandes surpresas."),
    ),
    "CAFE": (
        o("cafe_cortesia", "Café de cortesia para empresas vizinhas", "Entrega de cafés e folhetos nos escritórios próximos.", 0.8, 0.9, 0.0, "Retorno gradual."),
        o("cartao_fidelidade", "Cartão fidelidade com café grátis", "Ao completar 10 compras o cliente ganha um café.", 0.9, 0.9, -0.03, "Fideliza, mas alcança poucos novos clientes."),
        o("influenciador_cafe", "Influenciador de cafés especiais", "Resenha em vídeo com foco em grãos e ambiente.", 1.3, 1.4, 0.10, "Pode viralizar ou passar despercebido."),
        o("degustacao_cafe", "Tarde de degustação de grãos", "Evento para apresentar métodos e origens.", 1.0, 1.0, 0.02, "Atrai curiosos e entusiastas."),
        o("parceria_coworking", "Parceria com coworkings e universidades", "Combos para quem estuda e trabalha por perto.", 1.1, 1.1, 0.03, "Público grande, ticket menor."),
        o("promocao_manha", "Promoção do café da manhã", "Combo com pão e café em horário de menor movimento.", 0.7, 0.8, -0.04, "Segura, ganho pequeno."),
        o("decoracao_instagram", "Cantinho fotogênico para redes sociais", "Ambiente pensado para fotos e marcações.", 1.2, 1.2, 0.06, "Pode bombar ou virar só decoração."),
    ),
    "CLOTHING": (
        o("liquidacao", "Liquidação de fim de estação", "Descontos fortes para girar o estoque.", 0.8, 1.0, -0.02, "Vende, mas pode corroer a margem."),
        o("influenciador_moda", "Parceria com influenciador de moda", "Looks com as peças da loja nas redes dele.", 1.4, 1.4, 0.10, "Pode viralizar ou passar despercebido."),
        o("desfile_vitrine", "Desfile na vitrine", "Evento na loja com modelos e convidados.", 1.2, 1.2, 0.06, "Chama atenção da vizinhança."),
        o("cupom_primeira_compra", "Cupom de primeira compra", "Desconto para quem nunca comprou.", 0.7, 0.9, -0.03, "Barato e previsível."),
        o("parceria_salao", "Parceria com salões e estúdios", "Indicação cruzada com negócios de beleza.", 0.9, 0.9, 0.0, "Retorno gradual."),
        o("anuncio_segmentado", "Anúncios segmentados nas redes", "Campanha para o público da região.", 1.0, 1.0, 0.0, "Resultado depende da criatividade."),
        o("lookbook", "Lançamento de coleção com lookbook", "Fotos profissionais e lançamento com convidados.", 1.5, 1.3, 0.08, "Alto investimento, chance de brilhar."),
    ),
    "SUPERMARKET": (
        o("encarte_ofertas", "Encarte de ofertas da semana", "Folheto e cartaz com itens de entrada.", 0.8, 0.9, -0.03, "Funciona, sem grandes surpresas."),
        o("carro_som", "Divulgação em carro de som e rádio local", "Campanha na região por duas semanas.", 0.9, 0.9, -0.02, "Alcance geográfico bom."),
        o("clube_vantagens", "Clube de vantagens com pontos", "Pontos que viram desconto nas compras.", 1.1, 1.1, 0.03, "Fideliza, mas demora a dar retorno."),
        o("dia_ofertao", "Dia do ofertão (preços de custo)", "Itens-chave com preço de gancho.", 1.2, 1.3, 0.08, "Enche o mercado ou só custa margem."),
        o("parceria_condominios", "Parceria com condomínios da região", "Compras coletivas com entrega.", 1.0, 1.0, 0.0, "Retorno estável."),
        o("degustacao_corredor", "Degustação de produtos nos corredores", "Fornecedores patrocinam amostras.", 0.7, 0.8, 0.0, "Barata, efeito pequeno."),
        o("app_compras", "Aplicativo de compras com entrega", "Entrega em até 2 horas no bairro.", 1.5, 1.4, 0.10, "Pode virar hábito ou ficar subutilizado."),
    ),
    "WORKSHOP": (
        o("revisao_gratis", "Revisão gratuita de 10 itens", "Checklist de segurança sem custo para novos clientes.", 0.9, 1.0, 0.0, "Traz clientes e orçamentos."),
        o("parceria_seguradora", "Parceria com seguradoras e frotas", "Indicação para clientes de apólices e frotas.", 1.3, 1.3, 0.06, "Contrato grande ou nada."),
        o("flyer_semaforo", "Panfletagem em semáforos e postos", "Divulgação na região da oficina.", 0.6, 0.7, -0.03, "Barato, retorno modesto."),
        o("influenciador_carros", "Canal de carros e motos local", "Vídeos de manutenção com a oficina.", 1.3, 1.4, 0.10, "Pode viralizar ou passar despercebido."),
        o("promocao_alinhamento", "Promoção de alinhamento e balanceamento", "Combo por tempo limitado.", 0.8, 0.9, -0.02, "Atrai gente, mas margem menor."),
        o("clube_motoristas", "Clube do motorista com desconto recorrente", "Assinatura de revisões e lavagens.", 1.1, 1.1, 0.03, "Fideliza com o tempo."),
        o("indicacao_amigo", "Programa de indicação com desconto", "Quem indica e quem chega ganham desconto.", 0.7, 0.9, -0.02, "Seguro e barato."),
    ),
    "TECH": (
        o("webinar", "Webinar gratuito para potenciais clientes", "Demonstração técnica ao vivo e material rico.", 0.8, 1.0, 0.0, "Gera leads, nem todos convertem."),
        o("evento_setor", "Patrocínio de evento do setor", "Estande e palestra num congresso de tecnologia.", 1.4, 1.3, 0.08, "Pode render grandes contratos."),
        o("case_sucesso", "Estudo de caso com cliente satisfeito", "Material comercial com resultados reais.", 0.8, 1.0, -0.03, "Reputação sólida, retorno moderado."),
        o("conteudo_tecnico", "Série de conteúdo técnico", "Artigos e vídeos de autoridade.", 0.7, 0.9, -0.02, "Efeito lento e cumulativo."),
        o("parceria_integradora", "Parceria com integradoras", "Revendedores indicam a empresa.", 1.1, 1.1, 0.03, "Funil novo, depende do parceiro."),
        o("trial_gratis", "Período de teste gratuito", "Cliente testa antes de contratar.", 1.0, 1.1, 0.04, "Pode converter muito ou atrair curiosos."),
        o("anuncio_b2b", "Anúncios segmentados B2B", "Campanha para decisores em empresas-alvo.", 1.2, 1.2, 0.05, "Custa por clique, resultado variável."),
    ),
    "AGENCY": (
        o("portfolio_gratis", "Diagnóstico gratuito de marketing", "Auditoria de presença digital para prospects.", 0.8, 1.0, 0.0, "Gera conversas, nem todas viram contratos."),
        o("premio_setor", "Inscrição em prêmio do setor", "Casos inscritos em premiações.", 1.2, 1.2, 0.08, "Se premiar, o impacto é grande."),
        o("evento_networking", "Evento de networking com empresários", "Café da manhã com palestra.", 1.0, 1.0, 0.02, "Contatos qualificados, retorno gradual."),
        o("case_video", "Vídeo-case de cliente", "Produção audiovisual de um caso.", 0.9, 1.0, -0.02, "Ferramenta de venda duradoura."),
        o("parceria_contadores", "Parceria com contadores e consultores", "Indicações mútuas.", 0.7, 0.9, -0.03, "Barato e estável."),
        o("conteudo_autoridade", "Série de conteúdo de autoridade", "Artigos, podcasts e palestras.", 0.8, 0.9, -0.02, "Efeito lento."),
        o("ads_proprios", "Campanha paga para a própria agência", "Anúncios segmentados por setor.", 1.3, 1.3, 0.08, "Depende da criatividade e da concorrência."),
    ),
    "INDUSTRY": (
        o("feira_setorial", "Estande em feira setorial", "Mostra de produtos para compradores do setor.", 1.4, 1.3, 0.08, "Pode render grandes pedidos."),
        o("catalogo_tecnico", "Catálogo técnico e amostras para compradores", "Material e amostras para engenheiros e compradores.", 0.8, 0.9, -0.02, "Estável, retorno gradual."),
        o("visita_fabrica", "Programa de visitas à fábrica", "Clientes conhecem o processo.", 0.9, 1.0, 0.0, "Constrói confiança."),
        o("representantes", "Rede de representantes comerciais", "Comissionados em outras regiões.", 1.2, 1.2, 0.05, "Amplia o alcance, mas depende do desempenho deles."),
        o("anuncio_revista", "Anúncios em revista e portais do setor", "Mídia especializada.", 1.0, 0.9, -0.03, "Retorno previsível."),
        o("certificacao_marca", "Selo de qualidade divulgado ao mercado", "Campanha sobre a certificação da empresa.", 1.1, 1.1, 0.02, "Reforça a marca."),
        o("licitacoes", "Participar de licitações e rodadas de negócios", "Dedica equipe a rodadas de compras.", 1.3, 1.3, 0.09, "Pode fechar contrato grande ou nada."),
    ),
    "CONSTRUCTION": (
        o("casa_modelo", "Casa-modelo aberta ao público", "Visita guiada em uma obra entregue.", 1.4, 1.3, 0.06, "Atrai interessados de qualidade."),
        o("parceria_corretores", "Parceria com corretores e imobiliárias", "Indicações de clientes que querem construir.", 1.0, 1.1, 0.02, "Funil estável."),
        o("placa_obra", "Placas e faixas nas obras em andamento", "Visibilidade no entorno.", 0.6, 0.7, -0.04, "Barata, efeito pequeno."),
        o("portfolio_video", "Vídeo-portfólio de obras entregues", "Material comercial com antes e depois.", 0.9, 1.0, 0.0, "Ferramenta durável."),
        o("feira_imoveis", "Estande em feira de imóveis", "Exposição com plantas e maquetes.", 1.5, 1.4, 0.10, "Pode render contratos grandes."),
        o("ads_regional", "Campanha digital na região", "Anúncios para quem pesquisa reformas e construção.", 1.0, 1.0, 0.0, "Resultado depende da concorrência."),
        o("indicacao_clientes", "Programa de indicação de clientes", "Bônus para quem indicar uma obra.", 0.8, 0.9, -0.02, "Seguro e barato."),
    ),
    "TRANSPORT": (
        o("parceria_ecommerces", "Parceria com lojas virtuais da região", "Contratos de entrega com pequenos varejistas.", 1.2, 1.2, 0.05, "Volume recorrente se der certo."),
        o("frete_inaugural", "Frete promocional para novos clientes", "Desconto na primeira carga.", 0.8, 0.9, -0.02, "Atrai empresas, margem menor."),
        o("adesivo_frota", "Adesivagem da frota", "Marca em todos os veículos.", 0.7, 0.8, -0.03, "Visibilidade contínua."),
        o("feira_logistica", "Estande em feira de logística", "Contato com grandes embarcadores.", 1.4, 1.3, 0.08, "Pode render contrato grande."),
        o("rastreamento_clientes", "Painel de rastreamento para clientes", "Clientes acompanham a carga em tempo real.", 1.0, 1.0, 0.02, "Diferencial moderno."),
        o("representantes", "Representantes comerciais em polos", "Prospecção ativa em polos industriais.", 1.1, 1.1, 0.04, "Amplia o alcance."),
        o("indicacao_motoristas", "Programa de indicação entre empresas", "Descontos para quem indicar embarcadores.", 0.7, 0.9, -0.02, "Barato e estável."),
    ),
    "REAL_ESTATE_AGENCY": (
        o("open_house", "Open house de fim de semana", "Imóveis abertos com corretores.", 0.9, 1.0, 0.0, "Atrai curiosos e compradores."),
        o("fotos_profissionais", "Fotos e vídeos profissionais dos imóveis", "Melhora o anúncio nos portais.", 0.8, 0.9, -0.03, "Retorno moderado."),
        o("portal_destaque", "Destaque pago nos portais", "Anúncios patrocinados.", 1.2, 1.2, 0.05, "Aumenta visibilidade, mas é disputado."),
        o("influenciador_imoveis", "Influenciador de decoração e imóveis", "Tour em vídeo pelos imóveis.", 1.3, 1.4, 0.10, "Pode viralizar ou passar despercebido."),
        o("parceria_construtoras", "Parceria com construtoras e incorporadoras", "Carteira de lançamentos para vender.", 1.1, 1.2, 0.04, "Funil grande, mas disputado."),
        o("evento_investidores", "Evento para investidores", "Palestra sobre mercado imobiliário.", 1.0, 1.0, 0.02, "Contatos qualificados."),
        o("indicacao_proprietarios", "Programa de indicação a proprietários", "Bônus para quem indicar um imóvel.", 0.7, 0.9, -0.02, "Seguro e barato."),
    ),
    "ECOMMERCE": (
        o("cupom_novos", "Cupom de primeira compra", "Desconto para novos clientes.", 0.7, 0.9, -0.02, "Barato e previsível."),
        o("influenciador_digital", "Parceria com influenciador digital", "Divulgação com link de afiliado.", 1.3, 1.4, 0.10, "Pode viralizar ou passar despercebido."),
        o("ads_busca", "Anúncios em buscadores", "Campanha por palavras-chave.", 1.1, 1.0, 0.0, "Resultado depende da concorrência."),
        o("frete_gratis", "Semana de frete grátis", "Promoção para elevar a conversão.", 1.2, 1.2, 0.04, "Pode vender muito ou só custar frete."),
        o("email_remarketing", "Campanha de e-mail e remarketing", "Recuperar carrinhos e clientes antigos.", 0.6, 0.8, -0.04, "Barata, ganho moderado."),
        o("marketplace_destaque", "Destaque em marketplaces", "Patrocínio de produtos nas plataformas.", 1.4, 1.3, 0.07, "Pode multiplicar as vendas ou não."),
        o("programa_afiliados", "Programa de afiliados", "Comissão para quem indicar vendas.", 0.9, 1.0, 0.02, "Retorno gradual."),
    ),
}


def family_of(metrics_kind: str) -> str:
    return metrics_kind if metrics_kind in FAMILIES else "SERVICE"


def pool(kind: str, *, family: str, segment: str) -> tuple[Opt, ...]:
    if kind == "CAPACITY":
        return CAPACITY[family]
    if kind == "NEW_UNIT":
        return NEW_UNIT[family]
    if kind == "QUALITY":
        return QUALITY[family]
    if kind == "LARGER_PREMISES":
        return LARGER
    if kind == "MARKETING":
        return CAMPAIGNS[segment]
    raise KeyError(kind)
