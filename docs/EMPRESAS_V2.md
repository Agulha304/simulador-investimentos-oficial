# Empresas v2 — especificação de design

Pedido do usuário (resumo fiel) e as decisões de design tomadas para implementá-lo. Cada fase é entregue com backend + testes +
frontend e `pytest` completo verde. Código de referência: `backend/services/company_service.py`, `company_rules.py`,
`backend/models/company.py`, `backend/routers/companies.py`, `frontend/src/pages/Compan*.tsx`, `components/CompanyModals.tsx`.

## Princípios
- Determinismo: tudo que for "sorteio" usa `hash01(...)` com a SEMENTE DA PARTIDA (user/world seed), nunca `random`.
- Idempotência: operações novas que mexem em dinheiro aceitam `idempotency_key` (padrão das existentes).
- Dinheiro sempre via `_post`/ledger (como hoje); o orçamento pessoal só vê o lado pessoal.
- Texto da interface em português do Brasil. Valores monetários: `Decimal`, 2 casas.
- Não quebrar o resto do jogo: ajustar os testes existentes quando a regra mudar de propósito; nunca apagar cobertura.

## Fase 1 — Criação, canal, terreno, localização, tipos de empresa
1. **Remover `business_type`** (modelo, schema, serviço, UI, migration que dropa a coluna). O tipo é o `segment`.
2. **Capital**: `minimum_capital` = capital mínimo para abrir (como `required_capital`, agora dependente também de canal e terreno).
   O dono paga `owner_share_pct% × minimum_capital + extra_capital`. Os sócios pagam a parte deles do mínimo (lógica atual de sócios).
   O caixa de abertura da empresa = `minimum_capital` + `extra_capital`... descontados setup/estoque/etc. como hoje.
   Campo de entrada `extra_capital` (substitui `capital`), rótulo exato na UI:
   **"Capital adicional a aportar (R$) — dinheiro a mais além do mínimo para abrir que você investirá na empresa"**.
   `POST /companies/quote` devolve `minimum_capital`, `owner_cost` (= parte do dono do mínimo), `extra_capital` e `total_owner_cost`.
3. **Canal**: `channel` = `ONLINE` | `PHYSICAL`. Cada segmento define `channels` permitidos (ex.: e-commerce só ONLINE; oficina,
   indústria, construtora, transporte só PHYSICAL; roupas/tecnologia/agência/imobiliária: ambos; **restaurante, cafeteria e supermercado: só PHYSICAL** — decisão posterior). Empresas existentes não mudam; a validação vale na criação (400).
   ONLINE: sem terreno, sem aluguel de ponto, custos fixos menores, demanda local não se aplica (usa alcance digital).
4. **Terreno** (só PHYSICAL): `site_mode` = `BUY` | `RENT`. BUY: paga o valor do terreno/ponto na abertura (entra no capital mínimo;
   vira ativo da empresa no patrimônio, sem aluguel). RENT: aluguel mensal (como hoje) + risco de despejo (fase 5).
5. **Localização por segmento**: cada segmento tem a sua lista de localizações com sentido para o negócio (restaurante: "Rua gastronômica",
   "Centro", "Shopping", "Bairro residencial", "Beira-mar"…; indústria: "Distrito industrial", "Zona rural"…; oficina: "Avenida de grande
   fluxo", "Bairro"…). Cada local tem `demand`, `rent` e `land_price` próprios. A API do catálogo devolve as localizações por segmento.
6. **Métricas por tipo de empresa** (`metrics_kind` no segmento): `PRODUCTION` (restaurante, cafeteria, indústria, construtora),
   `RETAIL` (roupas, supermercado), `SERVICE` (oficina, transporte, tecnologia, agência, imobiliária, e-commerce).
   SERVICE e e-commerce/agência/imobiliária NÃO têm estoque nem "produtos produzidos"; a UI mostra métricas próprias do tipo
   (ex.: "clientes atendidos", "projetos", "negócios fechados", "pedidos").
7. **Cargos por segmento**: ≥ 4 cargos específicos por segmento, com salário e produtividade. Cargos obrigatórios em TODA empresa
   (fase 2): Contador, Advogado e, se PHYSICAL, Auxiliar de limpeza.

## Fase 2 — Equipe
1. Empresa nasce SEM funcionários (nem estoque inicial automático além do que a Fase 4 definir).
2. **Contratação direta**: `POST /companies/{id}/candidates` {role, regime: CLT|PJ} → lista de candidatos (nome, escolaridade,
   anos de experiência, nível derivado, pretensão salarial, jornada pretendida), determinística por (empresa, mês, cargo, regime, seed).
   `POST /companies/{id}/hire` {candidate_id, salary, hours_week, schedule} → aceita ou recusa conforme as condições: salário vs
   pretensão, jornada (> 44 h exige prêmio), escala (6x1 / 5x2 / 12x36 / 4x3), regime e a "concorrência" do candidato; pode
   devolver contraproposta. Registrar `regime`, `schedule`, `education`, `experience_years` no `Employee`.
3. ~~Headhunter por consulta~~ (REMOVIDO): substituído pelo **Contratador** opcional (seção "Contratador" abaixo).
4. **Custo**: CLT custa **2× o salário** (encargos/benefícios/provisões). PJ custa **1× o salário** (sem encargos) — mais barato —,
   mas na demissão tem **chance muito maior de processo trabalhista** (reconhecimento de vínculo).
5. **Obrigatórios**: sem Contador e Advogado (e Auxiliar de limpeza se PHYSICAL) a empresa fica **irregular**: não opera (vendas zero)
   e paga multa no mês. A UI avisa antes de fechar o mês.
6. UI: modal "Contratar" (cargo + regime → lista de candidatos), popup de proposta (salário, horas, escala) com resposta do candidato;
   "Contratar via contratador" (cartão Contratador). Mostrar regime/escala/escolaridade na lista de funcionários e o custo real (2× / 1×).

## Fase 3 — Mercado, relevância, produção, impostos reais, crises
1. **Relevância** (0–100, começa em 0): `Company.relevance`. Sobe devagar (bom atendimento, qualidade, marketing, meses de venda), cai
   se a empresa ficar parada. Fator de demanda `0.05 + 0.95·(relevance/100)^1.4` (com relevância 0 vende quase nada; com 100 vende pleno).
2. **Vendas difíceis**: demanda base reduzida e muito sensível ao preço; meses com ZERO venda são possíveis (probabilidade alta com
   relevância baixa ou preço acima do mercado). Preço menor → vende mais, mas não "fácil".
3. **Tetos de produção**: por porte (`SMALL/MEDIUM/LARGE`) e por unidade: teto de funcionários, teto de capacidade de estoque e teto de
   produção. Ao atingir o teto: ampliar estoque/instalação (custo) ou **mudar de endereço** (custo de mudança = meses de aluguel +
   reinstalação; empresa fica sem operar parte do mês).
4. Métricas de produção só nos segmentos `PRODUCTION`/`RETAIL`; SERVICE usa capacidade de atendimento própria.
5. **Crises econômicas** reduzem as vendas (conferir `economy_service.company_demand_mult` e garantir efeito claro e testado).
6. **Impostos reais do Brasil** (ver `docs/IMPOSTOS_EMPRESAS.md`, pesquisado): mesmos nomes e alíquotas (Simples Nacional/DAS por anexo e
   faixa, MEI, e Lucro Presumido: IRPJ, CSLL, PIS, COFINS, ISS, ICMS, IPI…), regime escolhido automaticamente pelo faturamento
   (RBT12), demonstrativo mensal com cada tributo em linha própria (`tax_breakdown`).

## Fase 4 — Fornecedores
1. Cada segmento define `supply_categories` (ex.: restaurante: Carnes e peixes, Hortifrúti, Bebidas, Embalagens; indústria: matéria-prima,
   energia/insumos…); SERVICE/agência/imobiliária/e-commerce/tecnologia: nenhuma (não precisam de fornecedor).
2. **Procurar fornecedores** por categoria: `POST /companies/{id}/suppliers/search` {category} → candidatos (nome, preço por unidade vs referência,
   pedido mínimo, confiabilidade, prazo). **Propor preço**: `POST /companies/{id}/suppliers/negotiate` {supplier_id, unit_price}: o fornecedor
   aceita, recusa ou contrapõe (piso por fornecedor/mês). Contrato ativo = `CompanySupplier` (categoria, preço, pedido mínimo).
3. Para produzir é preciso ter contrato ativo para CADA categoria necessária; sem fornecedor a produção/estoque não repõe.
4. Cada fornecedor/categoria aparece no **orçamento** da empresa (linha própria, valor previsto do mês) e no pessoal só como impacto agregado.
5. Ampliar produção exige comprar mais dos fornecedores (pedidos maiores; fornecedor pode não aguentar o volume).

## Fase 5 — Expansão e imprevistos
1. Todo aporte de expansão tem **3 níveis de investimento** (barato / médio / caro) com valores DIFERENTES por tipo de aporte e resultados
   probabilísticos (nível maior = chance maior, nunca garantida).
2. **Ampliar capacidade**: depois do nível, escolher entre **3 opções sorteadas** de um conjunto maior por tipo de empresa (ex.: ampliar
   estoque — aumenta energia/manutenção/instalações; contratar gerente que cobra produtividade — pode levar funcionários a pedir demissão;
   novo equipamento; turno extra; automação…). Varia por mês/semente. Pode ou não aumentar a produção; produzir mais ≠ vender mais.
3. **Abrir nova unidade**: nível + escolher terreno (comprar/alugar). A filial é como uma empresa nova com ajuda parcial da relevância da
   marca: vende MENOS que a matriz em média (mais difícil se a marca for pouco relevante), pode vender mais que a matriz (sorte), pode
   FALIR (fecha e perde o investimento).
4. **Qualidade dos produtos**: aporte (3 níveis) que sobe `quality` (mais relevância/tolerância a preço, custo maior).
5. **Campanha de publicidade**: nível + escolher entre 3 campanhas (ex.: restaurante — "Levar amostras da comida a uma escola"…),
   variam por tipo de empresa e por mês; efeito incerto.
6. **Imprevistos** decididos ao passar o mês (sistema de eventos com opções existente): **despejo** (terreno alugado), **processo
   trabalhista** (jornada longa; sobretudo PJ alegando vínculo), **quebra de equipamento** (custo extra, decisão de como consertar).

### Fase 4 — decisões de implementação (fornecedores)
- Categorias por segmento em `company_rules.SEGMENTS[..].supply_categories` (peso, unidade, consumo por venda, preço de referência derivado do
  custo de referência por venda; pesos somam 1,0). Segmentos com estoque: **1 `InventoryItem` por categoria** (campo `category`).
  Serviços (oficina, transporte): sem estoque; o custo variável é `vendas × Σ consumo × preço contratado` (linha `SUPPLIES`, no lugar de `VARIABLE`).
  Tecnologia, agência, imobiliária e e-commerce: nenhuma categoria.
- `CompanySupplier`: 1 contrato ATIVO por (empresa, categoria) (índice parcial único); volume = `max_units_month` do contrato (para mais volume,
  encerre e contrate outro). Pedido mínimo = unidades por compra. Encerrar antes de 3 meses: multa de 2 pedidos mínimos (linha FEES); depois, sem multa.
- Busca determinística (3–5 ofertas; token `AAAAMM-categoria-i` recalculado no servidor); piso de negociação 85–100% da lista, até −5 pts com
  relevância 100 e −3 pts com volume cheio (mín. 80%); contraproposta se a proposta for ≥ 92% do piso; recusa bloqueia o fornecedor no mês
  (reusa `company_candidate_blocks`). Proposta acima da lista fecha na lista.
- Falha de entrega: prob. (1 − confiabilidade) por (semente, contrato, mês); entrega 30–70% do pedido (estoque: paga só o entregue) ou reduz a
  capacidade do mês (serviços). Capacidade efetiva = `min_categorias(max_units_month / (consumo × (1 + perda)))`.
- Sem contrato: estoque não é reposto (ruptura); serviços ficam bloqueados (vendas 0, evento). Empresas antigas: contratos "Fornecedor padrão"
  ao preço de referência, volume ilimitado, confiabilidade 100% (migration `b8c9d0e1f2a3`); empresas novas nascem sem contratos nem estoque; o
  capital mínimo mantém a reserva da 1ª compra em caixa.

### Fase 5 — decisões de implementação (expansão e imprevistos)
- **Níveis** (`company_rules.TIER_COST`; API `BARATO|MEDIO|CARO`): CAPACITY 10/22/45% e NEW_UNIT 60/100/170% e QUALITY 5/12/28% de `setup x porte`;
  LARGER_PREMISES 40/60/100% de `setup x porte seguinte`; MARKETING 0,5x/1,5x/4x de `marketing_cost x fator fixo do porte`. A opção sorteada
  multiplica o custo do nível (0,45x a 1,6x). Chances (efeito completo/parcial; o resto é fracasso): CAPACITY 35/30, 55/28, 72/20 %; QUALITY
  40/30, 58/27, 75/18 %; LARGER_PREMISES 45/25, 70/18, 88/9 %; o `risk` da opção soma/subtrai da chance de efeito completo. Efeito completo:
  capacidade +0,4/0,8/1,4 níveis (1 nível = +25%), qualidade +5/10/20 pontos (parcial = metade). Nunca garantido.
- **Opções**: `POST /companies/{id}/expansion/options` sorteia 3 opções por `hash01(semente, empresa, mês, tipo, nível, opção)` de um conjunto por
  família (`metrics_kind`: 9 opções/família em CAPACITY, NEW_UNIT e QUALITY; 9 em LARGER_PREMISES; 7 campanhas por segmento) em
  `company_expansion_data.py`. `POST .../expansion/execute` RECALCULA as 3 e recusa qualquer outra; resultado = `hash01(semente, empresa, mês, tipo,
  nível, opção, nº de aportes anteriores do tipo)`; idempotente por `idempotency_key` (tabela `company_expansions`). `/expand` foi removido.
- **Capacidade**: `Company.capacity_boost` (níveis efetivos, fracionário; `capacity_level` = nº de aportes que funcionaram). Teto de 4 níveis. Efeitos
  colaterais: custo fixo recorrente (`CompanyCost`), `storage_boost` (teto de estoque), gerente (Employee `production_manager`, não conta como
  capacidade), pedidos de demissão determinísticos (só produtivos, no máx. 40%), turno extra (+6 h e +10% de salário: sobe o risco de processo).
  A capacidade efetiva continua `min(equipe, teto, fornecedores)`: a resposta avisa que é preciso comprar mais dos fornecedores.
- **Filiais** (`CompanyUnit`; a matriz é a própria empresa): relevância inicial = 25/40/60% da relevância da marca (+ ajuste da opção); viabilidade
  = 0,3 + 1,1 x u^forma (forma 1,25/1,0/0,8 por nível) em [0,3; 1,4]; chance de nem abrir 12/7/3% (perde metade do custo). Cada unidade tem
  demanda própria (`demand_units(units=1)` x viabilidade); a equipe produtiva global é repartida pela demanda de cada unidade (`people_share`);
  fornecedores e estoque limitam o TOTAL (rateio proporcional). Folha rateada pela fatia de equipe, custo variável pelas vendas, fixos da filial =
  aluguel + custos por unidade; a matriz fica com o resto, então `units_detail` soma o total do mês. Fecha se resultado acumulado < -60% do
  investimento (>= 3 meses) ou se o caixa da empresa está negativo e a filial no vermelho: encerra o aluguel, vende o terreno a 92%, perde o investimento.
- **Qualidade** (50 inicial): preço de mercado efetivo = preço x (1 + 0,20 (q-50)/50); ganho de relevância +0,4 (q-50)/50 ao mês; compra de
  insumos e custo variável x (1 + 0,25 (q-50)/50).
- **Campanha**: chance de nenhum efeito 30/18/10%, viral 10/17/28% (+-risco); efeito: demanda +8/14/25% por 2/3/4 meses e relevância +0,8/2,0/4,5
  (x poder da opção; viral = 1,8x a demanda, +1 mês, 2x a relevância). `marketing_until` segue valendo; `marketing_boost` (padrão 12%) guarda a alta.
- **Imprevistos** (`company_incidents.py`, eventos com decisão; no máx. 2 por mês na carteira, mesmo tipo/empresa só a cada 6 meses): despejo
  (1,0%/mês x contrato antigo 1-2x x aluguel atrasado 3x x relevância 1,3x..0,5x; só PHYSICAL+RENT; opções negociar = 3 aluguéis, 85% renova;
  mudar = relocate automático para ponto equivalente; justiça = exige advogado ativo, 50%, 1,5 aluguel de custas; ignorar = sem operar 2 meses ou
  até relocar), processo trabalhista (0,4% + jornada média > 48 h (1,5% + 0,4 pt/h) + 0,5% x (1 + tempo de casa/36) por PJ, teto 12%; valor =
  folha real x (2,0 / 0,5-3,5 / 4,0) x multiplicador da causa 1,0-1,75) e quebra de equipamento (3%/mês x capacidade ampliada x turno extra; conserto
  barato 4,5% do setup, médio 8%, premium 16% + 12 meses sem quebra, adiar = -30% de vendas e 40% de piorar). Custo esperado entra em
  `company_balance` (`incidents_on`); virada continua entre os meses 12 e 16.

## Contratador (headhunter) opcional, histórico trabalhista e limites de fornecedor
Pedido: o headhunter por consulta foi removido; no lugar entra um **serviço opcional por empresa** que contrata sozinho (obrigatórios, equipe por
área e fornecedores) a partir de um briefing. Restaurante, cafeteria e supermercado deixam de poder ser online.

### Decisões de implementação
- **Histórico trabalhista**: `lawsuit_history` (0 a 3 processos anteriores) gerado por `hash01` em cada candidato (`company_team.build_candidate`): ~9% (CLT)
  e ~17% (PJ) têm >= 1, +3 pontos em cargos de jornada >= 44 h (≈12-15% na média); entre quem tem, 70% têm 1, 22% têm 2 e 8% têm 3. Gravado em
  `employees.lawsuit_history` (default 0; os antigos ficam em 0). Chance de processo na demissão x `(1 + 0,6 x histórico)` (teto de 90% mantido).
- **Contratador** (`company_recruiters`, 1 por empresa, reaproveitada ao recontratar): níveis BASIC/PRO/ELITE. Taxa mensal cobrada no fechamento (linha
  `FEES`, entra em `monthly_obligations` e no runway), SMALL 900 / 2.200 / 4.800, x1,6 (MÉDIA) e x2,6 (GRANDE). Dispensa a qualquer momento, sem multa
  (não cobra mais a partir do fechamento seguinte). Trocar de nível vale a partir do fechamento corrente. A **comissão** por contratação (0,25x / 0,20x /
  0,15x o salário, linha `HIRING`) SUBSTITUI o custo de recrutamento de meio salário do fluxo manual (o contratador é quem recruta).
- **Qualidade do nível** (`company_recruiter.TIERS`): pessoas avaliadas por vaga 6/12/24, ofertas por categoria de fornecedor 6/12/24, chance de CADA
  pessoa/oferta ser encontrada 0,60/0,80/0,95 (sorteio `hash01(semente, empresa, mês, nível, pessoa)`), desconto de negociação 0/3/6% e taxa de sucesso da
  negociação 0,80/0,90/0,97. As pessoas do contratador são um universo próprio (token `AAAAMM-cargo-CLT-rN`), sem regime definido: ele escolhe o regime.
- **Desconto na função de avaliação**: `team.evaluate_offer(..., extra_flex)` soma o desconto à folga do próprio candidato (só baixa o MÍNIMO aceito) e
  `supply.evaluate(..., extra_discount)` multiplica o piso do fornecedor por `(1 - desconto)`. Recusa, contraproposta, jornada > 52 h e concorrência
  seguem as regras do fluxo manual; o contratador propõe exatamente `team.min_acceptable` (menor valor que `evaluate_offer` aceita; no PJ considera também
  a regra "cobriu a pretensão") e a proposta é revalidada pela mesma função.
- **Custo-benefício** do funcionário = produtividade (nível x min(1, jornada/40)) / custo mensal real (CLT 2x, PJ 1x, sobre o salário proposto). Cargos
  obrigatórios: menor custo mensal (aceita 20 h, que conta como preenchido, se custar menos). Equipe: do maior custo-benefício para o menor; contrata os
  que cabem no salário máximo, no teto de funcionários (por unidade), no teto de folha extra da operação (`max_monthly_payroll`) e no caixa (não contrata
  se o caixa pós-contratação cobrir < 2 meses de obrigações; vale para a equipe, não para os obrigatórios, que só exigem caixa para a comissão).
- **Regime BOTH**: com histórico de processos => CLT; sem histórico => PJ (mais barato) e, se o PJ não couber no salário máximo ou no orçamento de folha
  restante, cai para CLT. Nenhum cargo exige CLT (sem regra por cargo). CLT_ONLY/PJ_ONLY são respeitados sempre.
- **Briefing** (`settings` JSON, PUT substitui tudo): `max_salary`, `schedule`, `hours_week` (20 a 44; padrão da escala: 6x1=44, 5x2=40, 12x36=36, 4x3=40),
  `regime_policy`, `max_monthly_payroll`, fornecedores gerais (`supplier_max_total_spend`, `_min_reliability`, `_max_lead_days`, `_volume_cap`) e
  `supplier_overrides[categoria]` (`max_spend`, `min_reliability`, `max_lead_days`, `volume_cap`), que prevalecem campo a campo sobre o geral. Fora de
  intervalo => 400. Contratar sem `max_salary` => 400.
- **Fornecedores via contratador**: para cada categoria (padrão: as sem contrato) avalia as ofertas do universo do nível (as primeiras do universo são as
  da lista manual), filtra por confiabilidade mínima, prazo máximo, volume (contrato = min(volume do fornecedor, `volume_cap`), >= pedido mínimo) e gasto
  máximo da categoria; gasto previsto = min(demanda esperada x consumo x (1 + perda), volume do contrato) x preço negociado; respeita o gasto total no
  conjunto (categorias em ordem do segmento); escolhe o menor preço efetivo `preço x (1 + 2 x (1 - confiabilidade))` e negocia o menor preço aceito (com o
  desconto do nível). Os limites ficam gravados no contrato.
- **Limites por contrato** (`company_suppliers.max_monthly_spend/volume_cap/min_reliability/max_lead_days`, `PUT .../suppliers/{id}/limits`): gasto e
  volume valem em TODA compra: a compra manual recebe 409 explicando (gasto do mês em `spend_used`, zerado a cada mês junto com `volume_used`) e a
  reposição automática compra só o que cabe e registra um evento "Reposição travada pelo limite do contrato". O volume efetivo (menor entre o contrato e o
  `volume_cap`) também limita a capacidade pelos fornecedores. Confiabilidade/prazo por contrato são critérios do contratador (renovar/trocar). Nos
  serviços (sem compra de estoque) o gasto é consumo por venda e não é travado; só o volume efetivo limita a capacidade. O orçamento mostra previsto x limite
  por categoria e o total contra `supplier_max_total_spend`.
- **Idempotência**: contratar/trocar usa `last_key`; as três operações guardam o relatório em `company_recruiter_runs` e a mesma chave devolve o mesmo
  relatório (`replayed: true`) sem cobrar nem contratar de novo.
- API: `POST/DELETE /companies/{id}/recruiter`, `PUT .../recruiter/settings`, `POST .../recruiter/hire-mandatory | hire-team | contract-suppliers` (409
  sem contratador ativo), `PUT .../suppliers/{id}/limits`; o estado vem em `recruiter` e `recruiter_tiers` do detalhe. Migration `e1f2a3b4c5d6` (aditiva,
  com defaults e reaplicável).

## Agronegócio (AGRIBUSINESS) e fornecedores opcionais

- **Agronegócio**: 13º segmento (`PRODUCTION`, só canal físico). Venda em "tonelada colhida" (R$ 1.800), demanda base 300, elasticidade 1,5
  (commodity) e sazonalidade de safra (`SEASON_CURVE`: pico mar-jun, entressafra out-dez, média 1,0) somada ao sorteio mensal.
  Cargos: agrônomo, operador de máquinas agrícolas, trabalhador rural, técnico agrícola, veterinário/zootecnista, gerente de fazenda.
  Fornecimento: sementes e mudas (20%), fertilizantes e defensivos (35%), combustível e manutenção de máquinas (20%), ração e insumos pecuários (25%).
  Impostos: Simples Anexo I, presunção de comércio, ICMS 18% (sem ISS/IPI); simplificação registrada em `SIMPLIFICACOES`.
  Crises: SUPPLY -12, DEBT -9, INFLATION -7, RECESSION -7, GLOBAL -8, FINANCIAL -6, BANKING -5; CURRENCY +6 (exportação).
  Balanceamento (porte pequeno, preço de lista): virada no mês 13; com fornecedores 7% acima da lista, mês 16.
- **Fornecedores opcionais**: no briefing do contratador e nos contratos, TODOS os critérios/limites (gasto total e por categoria,
  confiabilidade mínima, prazo máximo, volume máximo) são opcionais: vazio/`null`/`""` = sem restrição. Override de categoria sem nenhum
  campo preenchido não é guardado; campo vazio no override herda apenas o valor geral. Briefings antigos com campo de fornecedor
  inválido mantêm o resto e tratam só o campo inválido como "sem limite".
