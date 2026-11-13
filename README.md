# Simulador de Investimentos

Simulador **educacional** de investimentos: carteira virtual em reais (BRL) para praticar
compra e venda de ações, ETFs, FIIs, REITs, criptomoedas e renda fixa.
**Nenhuma operação envolve dinheiro real.**

## Stack

| Camada | Tecnologia |
|---|---|
| API | Python 3.12, FastAPI, Pydantic v2 |
| Banco | PostgreSQL 16, SQLAlchemy 2.0, Alembic (migrations) |
| Workers | APScheduler |
| Frontend | React 18 + TypeScript + Vite |

## Estrutura

```text
backend/
  main.py            # app FastAPI, CORS, lifespan (banco + scheduler)
  config.py          # settings via .env
  database.py        # engine / sessão
  dependencies.py    # sessão de banco e usuário autenticado
  core/              # money (Decimal), security (JWT/bcrypt), logging
  models/            # User, Portfolio, Asset, Holding, Transaction, enums
  schemas/           # contratos de entrada/saída da API
  services/          # regras de negócio (ledger, auth, portfolio, ...)
  routers/           # HTTP fino: valida, chama serviço, serializa
  workers/           # APScheduler e jobs periódicos
  alembic/           # migrations
frontend/src/
  services/          # cliente HTTP e contexto de autenticação
  components/        # layout, cards, rota protegida
  pages/             # login/cadastro, dashboard
  lib/               # formatação (apenas exibição)
scripts/
  dev_db.sh          # Postgres local do projeto (sem sudo), porta 5433
  dev.sh             # sobe banco + migrations + backend + frontend
tests/               # pytest (usa o banco simulador_test)
```

## Como rodar

Pré-requisitos: Python 3.12, binários do PostgreSQL 16 (`/usr/lib/postgresql/16/bin`) e Node 20+
(neste ambiente o Node fica em `.tools/node`, fora do Git).

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env            # e troque o JWT_SECRET
(cd frontend && npm install)

scripts/dev.sh                  # Postgres local + migrations + backend + frontend
```

- Frontend: http://localhost:5173
- API (Swagger): http://localhost:8000/docs

Para usar outro PostgreSQL (do sistema, Docker ou nuvem), basta alterar `DATABASE_URL` no `.env`
e rodar `.venv/bin/alembic upgrade head`.

### Testes

```bash
scripts/dev_db.sh start
.venv/bin/pytest -q
(cd frontend && npm run typecheck)
```

## Decisões de arquitetura

- **Precisão financeira.** Tudo é `Decimal` internamente. Colunas: dinheiro `NUMERIC(20,2)`,
  preços/câmbio `NUMERIC(28,10)` e quantidades `NUMERIC(38,18)` (cripto fracionada).
  Dados externos entram por `to_decimal()` (`Decimal(str(x))`). A API serializa Decimal como **string**,
  e o frontend apenas formata, sem fazer cálculos.
- **Livro-razão.** `services/ledger_service.py` é o único lugar que altera `Portfolio.cash_balance`.
  Ele trava a linha da carteira (`SELECT ... FOR UPDATE`), impede saldo negativo e grava uma `Transaction`
  com o saldo resultante. Transações nunca são apagadas, e o saldo pode ser reconstruído com `SUM(cash_amount_brl)`.
- **Idempotência.** `Transaction.idempotency_key` é única. Os workers (stop loss, proventos, renda fixa)
  usarão chaves determinísticas (ex.: `dividend:{evento}:{carteira}`), então reexecutar não duplica nada.
- **Ativos extensíveis.** Uma única tabela `assets`, com `asset_class`, `currency`, `provider_symbol` e `extra` (JSONB).
  Os enums são gravados como `VARCHAR + CHECK`, e não como ENUM nativo, para facilitar novas classes.
  A renda fixa terá modelo próprio (produto + investimento + fluxo de caixa).

## Dados de mercado

`services/market_data.py` é o único módulo que conhece a fonte (hoje o endpoint público de gráficos do Yahoo
Finance, sem chave). Ele tem cache (60 s cotações, 5 min câmbio), tenta de novo em caso de erro e, se a fonte cair,
usa a última cotação em cache. Cotações vêm na moeda do ativo e são convertidas para BRL no momento da operação
(`fx_rate` e preço original ficam gravados na transação). Para trocar de fonte, implemente `MarketDataProvider`.
A fonte é não oficial e pode limitar requisições; os testes usam um provedor falso, sem rede.

## Roadmap

- [x] **Fase 1: Fundação.** Estrutura, banco, migrations, autenticação JWT, carteira, saldo, livro-razão e dashboard
- [x] **Fase 2: Ações e mercado.** `market_data` (camada isolada, Yahoo Finance via HTTP), catálogo + pesquisa sem acentos, cotações, câmbio USD/BRL, compra/venda, preço médio, depósito virtual
- [x] **Fase 3: Gráficos.** Candles/linha (lightweight-charts v5), 7 períodos, 10 indicadores calculados no backend (`services/indicators.py`), painéis separados, layout salvo por usuário e ativo
- [x] **Fase 4: Ferramentas de desenho.** Tendência, raio, horizontal, suporte, resistência e marcação, ancorados em (tempo, preço) via primitivas do gráfico; salvos no banco por usuário e ativo
- [x] **Fase 5: Stop Loss / Take Profit.** Níveis na moeda do ativo, worker a cada 2 min, venda total a mercado, revalidação sob lock + chave idempotente (`sltp:{holding}:{versão}`)
- [ ] Fase 6: Proventos. Descoberta, elegibilidade histórica e pagamentos
- [ ] Fase 7: Cripto, FIIs, REITs e ETFs
- [ ] Fase 8: Renda fixa (Tesouro, CDB, LCI/LCA, CRI/CRA, debêntures) e IR
