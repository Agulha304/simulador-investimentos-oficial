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
.venv/bin/pytest -q                       # 103 testes, sem rede (fontes de dados falsas)
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
- Edição de desenhos limita-se a selecionar e excluir (não há arrastar de pontos).
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
