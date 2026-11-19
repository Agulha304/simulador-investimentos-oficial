# Simulador de Investimentos

Simulador **educacional** de investimentos: carteira virtual em reais (BRL) para praticar compra e venda de
ações, ETFs, FIIs, REITs, criptomoedas e renda fixa (Tesouro Direto, CDB, LCI, LCA, CRI, CRA e debêntures).
**Nenhuma operação envolve dinheiro real.**

## Funcionalidades

- **Carteira:** saldo, patrimônio, lucro/prejuízo e posições com preço médio, tudo em reais. Cada nova conta recebe
  R$ 100.000,00 virtuais (e pode depositar mais saldo fictício).
- **Mercado:** busca global (sem acentos), navegação por classe/país, cotações em lote. Ativos em dólar são
  convertidos para reais na hora da operação (preço original e câmbio ficam gravados).
- **Negociação:** compra e venda a mercado. Cripto é fracionada e pode ser comprada ou vendida por **valor em reais**
  (quantidade com 18 casas); ações, ETFs, FIIs e REITs só em quantidades inteiras.
- **Gráficos:** candles/linha, 7 períodos, zoom e pan, 10 indicadores calculados no backend (SMA, EMA, Bollinger, VWAP
  sobre o preço; Volume, RSI, MACD, Estocástico, ADX e ATR em painéis).
- **Desenhos:** linha de tendência, raio, horizontal, suporte, resistência e marcação, ancorados em (tempo, preço), então
  acompanham zoom, pan e troca de período. Salvos por usuário e ativo.
- **Stop Loss / Take Profit:** níveis por posição (na moeda do ativo), executados por worker.
- **Proventos:** dividendos, rendimentos de FIIs e distribuições de REITs/ETFs, com direito reconstruído pelas transações.
- **Renda fixa:** Tesouro Direto (dados reais), CDB, LCI, LCA, CRI, CRA e debêntures, com simulação, resgate antecipado,
  cupons, vencimento, IR regressivo e IOF.
- **Aulas:** 7 módulos e 29 aulas (fundamentos, renda fixa, ações, ETFs/FIIs/REITs, cripto, análise técnica, gestão de risco),
  cada uma com exemplos, ligação com as telas do simulador e um quiz corrigido no servidor. Progresso, pontos e nível por usuário.
- **Videoaulas:** cada aula tem uma videoaula de ~3 min no estilo *whiteboard* (uma mão desenhando, voz narrada em pt-BR),
  gerada pelo projeto `livro2video`. Os vídeos formam uma série: abrem com "Aula N de 37" e a ligação com a aula anterior, revisam
  as três perguntas do quiz e terminam apresentando a próxima aula. Tocam com legendas e passam sozinhos para a aula seguinte.
- **Desempenho:** evolução do patrimônio, rentabilidade contra o CDI, queda desde o pico, composição da carteira, resultado por mês,
  estatísticas das operações (acerto, ganho/perda médios, fator de lucro), nota de diversificação, disciplina, conquistas e dicas
  que apontam para a aula certa.
- **Ranking:** "mais ricos" e "maior rentabilidade", no geral, 30 e 7 dias, com apelido e opção de ocultar-se.

## Stack

| Camada | Tecnologia |
|---|---|
| API | Python 3.12, FastAPI, Pydantic v2 |
| Banco | PostgreSQL 16, SQLAlchemy 2.0, Alembic |
| Workers | APScheduler |
| Frontend | React 18 + TypeScript + Vite, lightweight-charts v5 |

## Como rodar

Pré-requisitos: Python 3.12, binários do PostgreSQL 16 (`/usr/lib/postgresql/16/bin`) e Node 20+
(neste ambiente o Node fica em `.tools/node`, fora do Git). A extensão `unaccent` do PostgreSQL é usada na busca.

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env            # e troque o JWT_SECRET
(cd frontend && npm install)

scripts/dev.sh                  # Postgres local (porta 5433) + migrations + backend + frontend
```

- Frontend: http://localhost:5173, API (Swagger): http://localhost:8000/docs
- Outras portas: `BACKEND_PORT=8010 FRONTEND_PORT=5180 scripts/dev.sh` (e ajuste `CORS_ORIGINS` no `.env`).
- Outro PostgreSQL (sistema, Docker, nuvem): altere `DATABASE_URL` no `.env` e rode `.venv/bin/alembic upgrade head`.

### Testes

```bash
scripts/dev_db.sh start
.venv/bin/pytest -q                       # 143 testes, sem rede (fontes de dados falsas)
(cd frontend && npm run typecheck)
```

## Estrutura

```text
backend/
  main.py  config.py  database.py  dependencies.py
  core/        money (Decimal), security (JWT/bcrypt), calendar_br (dias úteis), dates, logging
  models/      users, carteira, ativos, holdings, transações, proventos, renda fixa, layouts de gráfico
  schemas/     contratos da API
  services/    regras de negócio (veja abaixo)
  routers/     HTTP fino: valida, chama serviço, serializa
  workers/     jobs do APScheduler
  alembic/     migrations
frontend/src/  pages, components, services (API/auth), lib (formatação e geometria dos desenhos)
scripts/       dev_db.sh (Postgres local sem sudo), dev.sh
tests/         pytest (banco simulador_test)
```

Serviços principais: `ledger_service` (único ponto que altera o saldo), `trading_service`, `market_data` (fonte isolada),
`indicators`, `risk_service` (SL/TP), `distribution_service`, `tax_service`, `index_data` e `treasury_data` (fontes
isoladas), `fixed_income_math` (contas puras), `fixed_income_catalog`, `fixed_income_service`.

## Videoaulas (como foram feitas)

O gerador de vídeos (`livro2video`, em `~/projetos/videos-de-livros-automacao-oficial`) transforma **PDFs** em videoaulas. Por isso o
curso passa por um PDF:

1. `tools/video_course/build_pdf.py` gera `curso-educacao-financeira.pdf` (37 aulas, 68 páginas, uma aula por trecho, cada uma com
   marcador no sumário) **a partir do próprio conteúdo das aulas do site**, que continua sendo a única fonte do texto. Uma cópia fica em
   `docs/curso-educacao-financeira.pdf`.
2. `tools/video_course/generate_all.py` roda o `livro2video` em fila, uma aula por vez, com: complementos da IA **desligados** (tudo que o
   vídeo diz vem do texto conferido; no piloto a IA chegou a errar uma conta quando podia inventar exemplos), 1,5 min de conteúdo e voz/mão
   padrão do gerador. É retomável e segue em frente se uma aula falhar.
3. `tools/video_course/inject_series.py` insere em cada roteiro as cenas que formam a série (abertura, revisão com as perguntas do quiz,
   próxima aula) e remove frases e elementos repetidos entre cenas. Valores e siglas vão por extenso para a voz (`speech.py`).
4. `tools/video_course/publish.py` corrige o MP4 para streaming (`faststart`), cria a capa, converte as legendas para WebVTT e atualiza
   `media/manifest.json`, que o backend lê para ligar cada aula ao seu vídeo.

Refazer: `PYTHONPATH=. <venv-do-livro2video>/bin/python tools/video_course/build_pdf.py --out <livros>/curso-educacao-financeira.pdf` e
`python tools/video_course/generate_all.py --generator-dir <livro2video> --pdf livros/curso-educacao-financeira.pdf` (opções `--only m0-l3`,
`--force`). Em máquina com RTX 3050 cada vídeo leva cerca de 4 minutos.
Para mudar só as cenas da série (abertura, revisão, próxima aula) sem refazer roteiro nem notas, use `--refresh-series`: reaproveita tudo
que está em cache e leva cerca de 2,5 minutos por aula. As cenas da série seguem uma regra: **o desenho acompanha uma fala longa**. O gerador
estende a cena até a mão terminar de desenhar, então um desenho demorado sob uma fala curta vira silêncio (era 10% do tempo dos vídeos).

## Aulas, Desempenho e Ranking

- **Conteúdo das aulas** fica em `backend/content/` (um arquivo por módulo, texto em blocos tipados). Os quizzes são corrigidos em
  `learn_service`: o gabarito só é revelado depois da tentativa. Testes verificam a integridade do conteúdo (ids, quizzes, links).
- **Snapshots do patrimônio:** uma foto por hora e por carteira (`portfolio_snapshots`), registrada por worker (30 min), no cadastro e
  sob demanda ao abrir Desempenho/Ranking. Se faltar cotação de alguma posição, a foto é adiada para não registrar uma queda falsa.
  O gráfico de evolução começa na data do primeiro registro: **não há reconstrução histórica** do patrimônio.
- **Patrimônio do ranking e do desempenho** = patrimônio − aportes virtuais extras. Depositar mais saldo fictício não vira lucro nem
  sobe no ranking; o ponto de partida é o saldo inicial do cadastro. As estatísticas de operações vêm do livro-razão e existem desde o
  primeiro dia.
- **Privacidade:** o ranking mostra apenas apelido (padrão: primeiro nome + inicial do sobrenome), nunca e-mail ou id. O usuário pode
  mudar o apelido ou sair do ranking.
- **Gráficos** (Recharts) seguem um guia de visualização: cores validadas contra o fundo do app (azul e laranja passam nos testes de
  daltonismo), grade recessiva, composição em barras ordenadas (sem pizza), sinal de ganho/perda também por direção e ▲/▼ (nunca só
  por cor) e uma visão em tabela de cada gráfico.

## Orçamento mensal e ciclo do simulador (etapa 1 da "vida financeira")

Aba **Orçamento** (`/orcamento`). Código: `backend/models/budget.py`, `services/finance_ledger.py`, `budget_service.py`,
`month_service.py`, `routers/budget.py`; frontend em `pages/BudgetPage.tsx`.

- **Tempo mensal controlado pelo usuário.** Não há worker nem cron: o mês só avança em "Fechar mês e avançar", que mostra um resumo e
  exige confirmação. O primeiro mês é o mês real do primeiro acesso à aba (usuários antigos são preparados no primeiro acesso, nada é
  migrado à força).
- **Planejado ≠ realizado.** O valor previsto (`budget_items`) nunca mexe no saldo. Só uma movimentação registrada (`ledger_entries`) ou a
  cobrança de uma recorrente no fechamento altera o caixa. Recorrente que você já registrou à mão no mês não é cobrada de novo.
- **Livro de movimentações imutável.** `LedgerEntry` não é editado nem apagado; correção = estorno (nova linha ligada à original).
  Cada movimentação na conta pessoal gera uma `Transaction` (`BUDGET_INCOME`/`BUDGET_EXPENSE`) pelo `ledger_service.record`, que continua
  sendo o único ponto que altera `cash_balance`. A conta pessoal usa o `cash_balance` existente (sem duplicar saldo); `finance_accounts`
  já tem os tipos `INVESTMENT` e `BUSINESS` para empresas e carteiras futuras. `origin`/`origin_ref` identificam o módulo de origem.
- **Histórico de valores.** Mudar o valor de uma recorrência cria uma versão (`recurring_item_versions`) vigente a partir do mês atual, e cada
  mês guarda seus próprios itens: o aluguel de R$ 1.500 até março continua R$ 1.500 depois de virar R$ 2.000 em abril.
- **Fechamento atômico e idempotente.** Uma única transação trava a carteira, lança as recorrentes pendentes (receitas antes das despesas),
  grava o resumo, fecha o mês e abre o próximo com o saldo transportado. Qualquer erro desfaz tudo. Fechar duas vezes devolve 409 sem
  cobrar de novo; há índice único `(recurring_item_id, ref_month)` para recorrentes e chave de idempotência no caixa. Se faltar saldo para
  as recorrentes, o fechamento é recusado (422) e nada é lançado.
- **Impacto no ranking (decisão):** receitas e despesas do orçamento **contam como patrimônio** (diferente dos aportes virtuais extras).
  Salário aumenta lucro e posição no ranking; despesas diminuem. Para voltar a medir só investimentos, basta incluir os dois tipos novos em
  `portfolio_service.sum_net_deposits`.
- **Investimentos** continuam em Mercado/Renda Fixa. O orçamento só mostra o investido no mês (compras e aplicações) e um valor planejado.

## Decisões de arquitetura

- **Precisão.** Tudo é `Decimal`: dinheiro `NUMERIC(20,2)`, preços/câmbio `NUMERIC(28,10)`, quantidades `NUMERIC(38,18)`.
  Dados externos entram por `Decimal(str(x))`. A API serializa Decimal como **string** e o frontend só formata.
- **Livro-razão.** Só o `ledger_service` altera o saldo: trava a carteira (`SELECT ... FOR UPDATE`), impede saldo negativo
  e grava a `Transaction` (imutável, nunca apagada) com o saldo resultante. O saldo é reconstruível por `SUM(cash_amount_brl)`.
- **Idempotência.** `Transaction.idempotency_key` é única e todo worker usa chaves determinísticas
  (`sltp:{posição}:{versão}`, `dividend:{evento}:{carteira}`, `fi-event:{evento}`, `fi-redeem:{aplicação}`).
  Reexecutar um worker, ou rodar dois ao mesmo tempo, não duplica venda, pagamento nem rendimento.
  Os workers também travam e **releem** o estado antes de agir.
- **Fontes de dados isoladas.** Mercado (`market_data`), índices (`index_data`) e Tesouro (`treasury_data`) ficam atrás de
  protocolos pequenos. Trocar de fonte não toca nas regras.
- **Extensível.** Uma tabela de ativos para todas as classes; renda fixa descrita por colunas (indexador, modo de taxa,
  liquidez, carência, tributação, frequência de juros), então novos produtos são só novas linhas.

## Fontes de dados

| Dado | Fonte | Observação |
|---|---|---|
| Cotações, histórico, dividendos, câmbio USD/BRL | Yahoo Finance (endpoint público de gráficos) | Não oficial; pode limitar requisições. Cache + última cotação em caso de falha. |
| CDI, Selic, IPCA, IGP-M | Banco Central, API SGS (séries 12, 11, 433, 189) | Oficial. Histórico guardado em `index_rates`. |
| Tesouro Direto (preços e taxas) | CSV aberto do Tesouro Transparente | Oficial. Atualizado nos dias úteis. |
| CDB, LCI, LCA, CRI, CRA, debêntures | **Ofertas de exemplo** | Não há fonte pública estruturada. Emissores fictícios; taxas derivadas por regra do CDI, do IPCA e das taxas do Tesouro. Sempre marcadas como "exemplo". |

## Workers (APScheduler)

| Job | Frequência | O que faz |
|---|---|---|
| `stop_loss_take_profit` | 2 min | vende a posição inteira quando o preço toca o nível |
| `distribution_discover` | 6 h | descobre dividendos e reconstrói a elegibilidade |
| `distribution_pay` | 15 min | paga proventos cuja data chegou |
| `fixed_income_sync` | 6 h | índices (BCB), Tesouro Direto, desativa vencidos, reprecifica exemplos |
| `fixed_income_events` | 15 min | paga cupons e vencimentos |
| `performance_snapshot` | 30 min | registra a foto horária do patrimônio de todas as carteiras |

## Renda fixa: regras e simplificações

- **Rendimento:** prefixado e spreads em dias úteis/252; % do CDI/Selic pelo produto diário das taxas; IPCA/IGP-M pela
  correção mensal rateada por dias corridos mais a taxa real. Dia útil pelo calendário de feriados nacionais.
  Datas futuras usam projeção: última taxa diária conhecida, e média dos últimos 12 meses para IPCA/IGP-M.
- **Imposto** (`tax_service`): IR regressivo (22,5% até 180 dias, 20% até 360, 17,5% até 720, 15% depois) sobre o rendimento;
  IOF regressivo nos primeiros 29 dias; LCI, LCA, CRI, CRA e debêntures incentivadas isentos. Dividendos no Brasil isentos,
  proventos dos EUA com 30% retidos. IR sobre ganho de capital em ações **não** é descontado.
- **Resgate antecipado:** cada produto tem liquidez (diária, no vencimento ou em janelas), carência e permissão próprias.
  Tesouro Prefixado e IPCA+ (sem cupom) são vendidos a **preço de mercado** (valor de resgate descontado pela taxa de venda
  atual do mesmo título). CRI, CRA e debêntures permitem venda no secundário com **deságio** configurado no produto.
  Os demais saem pela curva contratada.
- **Cupons:** produtos com juros periódicos pagam, a cada data, os juros do período sobre o valor-base (a inflação
  capitaliza no valor-base) e devolvem o principal no vencimento. É um fluxo simplificado, não os cupons reais de uma NTN-B/NTN-F.
- **Contrato fixo:** a aplicação guarda a taxa contratada. Se a oferta mudar depois, a sua aplicação não muda.
- **Simplificações assumidas:** Renda+ e Educa+ pagam tudo no vencimento (o título real paga renda mensal); resgate apenas total;
  taxa de custódia da B3 não é cobrada; o JCP não é distinguido de dividendo pela fonte.

## Limitações conhecidas

- A data de pagamento de proventos é **estimada** (a fonte só informa a data EX).
- O Yahoo Finance não é oficial; se bloquear, as telas mostram "indisponível" e as operações são recusadas, sem quebrar.
- As videoaulas usam voz sintética e desenhos de um banco de ícones: são claras, mas não substituem o texto da aula. O roteirista é uma IA local (resume, não cria conteúdo novo); a conferência foi por amostragem.
- Edição de desenhos limita-se a selecionar e excluir (não há arrastar de pontos).
- O gráfico de patrimônio só tem pontos a partir do cadastro (ou da primeira visita à aba Desempenho, para contas antigas).
- Interface testada por tipos, build e chamadas reais à API; não há testes automatizados de navegador.

## Roadmap

- [x] Fase 1: Fundação (estrutura, banco, migrations, auth, carteira, livro-razão, dashboard)
- [x] Fase 2: Ações e mercado (pesquisa, cotações, câmbio, compra/venda, preço médio)
- [x] Fase 3: Gráficos e indicadores
- [x] Fase 4: Ferramentas de desenho
- [x] Fase 5: Stop Loss / Take Profit
- [x] Fase 6: Proventos
- [x] Fase 7: Cripto, FIIs, REITs e ETFs
- [x] Fase 8: Renda fixa
- [x] Extra: abas Aulas, Desempenho e Ranking
