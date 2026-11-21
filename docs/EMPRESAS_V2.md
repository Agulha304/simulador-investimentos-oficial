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
   indústria, construtora, transporte só PHYSICAL; restaurante/cafeteria/roupas/supermercado/tecnologia/agência/imobiliária: ambos).
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
3. **Headhunter**: `POST /companies/{id}/headhunter` {role, regime, max_salary, min_level} → cobra honorário (1 salário-teto) e devolve até 3
   candidatos já filtrados pelo briefing (orçamento, proficiência, CLT/PJ); a contratação segue o mesmo fluxo da proposta.
4. **Custo**: CLT custa **2× o salário** (encargos/benefícios/provisões). PJ custa **1× o salário** (sem encargos) — mais barato —,
   mas na demissão tem **chance muito maior de processo trabalhista** (reconhecimento de vínculo).
5. **Obrigatórios**: sem Contador e Advogado (e Auxiliar de limpeza se PHYSICAL) a empresa fica **irregular**: não opera (vendas zero)
   e paga multa no mês. A UI avisa antes de fechar o mês.
6. UI: modal "Contratar" (cargo + regime → lista de candidatos), popup de proposta (salário, horas, escala) com resposta do candidato;
   "Contratar via headhunter" (briefing). Mostrar regime/escala/escolaridade na lista de funcionários e o custo real (2× / 1×).

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
