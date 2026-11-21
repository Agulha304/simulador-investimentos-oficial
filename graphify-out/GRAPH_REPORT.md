# Graph Report - simulador-investimentos  (2026-11-18)

## Corpus Check
- 148 files · ~71,763 words
- Verdict: corpus is large enough that graph structure adds value.
- Unclassified: 8 file(s) not represented in the graph (top: (none) 3, .example 1, .ini 1)

## Summary
- 1809 nodes · 4461 edges · 96 communities (87 shown, 9 thin omitted)
- Extraction: 97% EXTRACTED · 3% INFERRED · 0% AMBIGUOUS · INFERRED: 119 edges (avg confidence: 0.9)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- Calendário e datas BR
- Ferramentas de vídeo
- Carteira e snapshots
- Engajamento e aulas
- Gráficos e ativos
- Dividendos
- Workers e renda fixa
- Dinheiro e ativos
- Indicadores técnicos
- Provedores de índices
- ChartPanel (frontend)
- Enums do domínio
- Desempenho (frontend)
- Datas e Tesouro
- Community 14
- Community 15
- Community 16
- Community 17
- Community 18
- Community 19
- Community 20
- Community 21
- Community 22
- Community 23
- Community 24
- Community 25
- Community 26
- Community 27
- Community 28
- Community 29
- Community 30
- Community 31
- Community 32
- Community 33
- Community 34
- Community 35
- Community 36
- Community 37
- Community 38
- Community 39
- Community 40
- Community 41
- Community 42
- Community 43
- Community 44
- Community 45
- Community 46
- Community 47
- Community 48
- Community 49
- Community 50
- Community 51
- Community 52
- Community 53
- Community 54
- Community 55
- Community 56
- Community 57
- Community 58
- Community 59
- Community 60
- Community 61
- Community 62
- Community 63
- Community 64
- Community 65
- Community 66
- Community 67
- Community 68
- Community 69
- Community 70
- Community 71
- Community 72
- Community 73
- Community 74
- Community 75
- Community 76
- Community 77
- Community 78
- Community 79
- Community 80
- Community 81
- Community 82
- Community 83
- Community 84
- Community 85
- Community 86
- Community 87
- Community 88
- Community 89
- Community 90
- Community 91
- Community 94

## God Nodes (most connected - your core abstractions)
1. `lessons` - 38 edges
2. `Simulador de Investimentos` - 37 edges
3. `quantize_money()` - 36 edges
4. `IndexData` - 31 edges
5. `fmtBRL()` - 28 edges
6. `Base` - 27 edges
7. `load()` - 26 edges
8. `build_performance()` - 24 edges
9. `IndexName` - 23 edges
10. `Portfolio` - 22 edges

## Surprising Connections (you probably didn't know these)
- `Backend FastAPI + workers (host sempre ligado)` --semantically_similar_to--> `FastAPI + Pydantic v2 (API)`  [INFERRED] [semantically similar]
  docs/DEPLOY.md → README.md
- `Instancia unica com SCHEDULER_ENABLED` --references--> `APScheduler workers`  [INFERRED]
  docs/DEPLOY.md → README.md
- `lifespan()` --indirect_call--> `db()`  [INFERRED]
  backend/main.py → tests/conftest.py
- `buy()` --indirect_call--> `pid()`  [INFERRED]
  backend/routers/trades.py → tests/test_fixed_income.py
- `sell()` --indirect_call--> `pid()`  [INFERRED]
  backend/routers/trades.py → tests/test_fixed_income.py

## Import Cycles
- None detected.

## Hyperedges (group relationships)
- **APScheduler background workers** — readme_job_stop_loss_take_profit, readme_job_distribution_discover, readme_job_distribution_pay, readme_job_fixed_income_sync, readme_job_fixed_income_events, readme_job_performance_snapshot [EXTRACTED 1.00]
- **Deploy flow: backend then Cloudflare** — docs_deploy_backend, docs_deploy_cloudflare, docs_deploy_backend_url, docs_deploy_postgres [EXTRACTED 1.00]
- **Video course generation flow** — readme_video_pipeline, readme_livro2video, media_manifest, readme_videoaulas [INFERRED 0.85]

## Communities (96 total, 9 thin omitted)

### Community 0 - "Calendário e datas BR"
Cohesion: 0.05
Nodes (48): add_months(), business_days_between(), easter(), holidays(), is_business_day(), iter_business_days(), next_business_day(), IndexName (+40 more)

### Community 1 - "Ferramentas de vídeo"
Cohesion: 0.05
Nodes (46): _el(), _sc(), test_dedupe_drops_scenes_left_empty_and_duplicate_elements(), test_dedupe_is_conservative_with_short_or_different_sentences(), test_dedupe_removes_repeated_sentences_and_keeps_their_actions(), test_no_digits_or_symbols_survive_in_any_review_narration(), test_number_words(), test_speak_pt() (+38 more)

### Community 2 - "Carteira e snapshots"
Cohesion: 0.06
Nodes (59): quantize_money(), PortfolioSnapshot, Portfolio, achievements(), allocation_and_positions(), build_performance(), build_series(), diversification() (+51 more)

### Community 3 - "Engajamento e aulas"
Cohesion: 0.07
Nodes (44): LessonProgress, get_performance(), get_ranking(), get_settings(), learn_lesson(), learn_overview(), learn_quiz(), put_settings() (+36 more)

### Community 4 - "Gráficos e ativos"
Cohesion: 0.07
Nodes (31): ChartLayout, get_asset(), _get_asset(), get_asset_quote(), get_chart(), get_layout(), get_quotes(), one() (+23 more)

### Community 5 - "Dividendos"
Cohesion: 0.08
Nodes (41): DividendEligibility, discover(), estimate_pay_date(), _generate_eligibilities(), local_date(), pay_due(), quantities_at(), clear_cache() (+33 more)

### Community 6 - "Workers e renda fixa"
Cohesion: 0.08
Nodes (38): process_due_events(), load(), sync(), heartbeat(), shutdown_scheduler(), start_scheduler(), test_scheduler_registers_distribution_jobs(), cash() (+30 more)

### Community 7 - "Dinheiro e ativos"
Cohesion: 0.09
Nodes (15): quantize_price(), Asset, AssetClass, Currency, TransactionSource, TransactionType, Holding, Transaction (+7 more)

### Community 8 - "Indicadores técnicos"
Cohesion: 0.09
Nodes (30): adx(), atr(), bollinger(), compute(), ema(), IndicatorError, macd(), _one() (+22 more)

### Community 9 - "Provedores de índices"
Cohesion: 0.05
Nodes (28): IndexDataUnavailable, IndexProvider, set_provider(), _day(), fetch_latest(), _num(), parse_latest(), set_provider() (+20 more)

### Community 10 - "ChartPanel (frontend)"
Cohesion: 0.10
Nodes (28): ChartPanel(), DrawingsPrimitive, css(), line(), LinePoint, num(), PALETTE, paneCount() (+20 more)

### Community 11 - "Enums do domínio"
Cohesion: 0.17
Nodes (25): DistributionKind, EligibilityStatus, EventKind, EventStatus, FixedIncomeType, Indexer, InvestmentStatus, Liquidity (+17 more)

### Community 12 - "Desempenho (frontend)"
Cohesion: 0.15
Nodes (30): ChartCard(), TableView, TipBox(), AllocationChart(), arrow(), AXIS, CumulativeChart(), dayLabel() (+22 more)

### Community 13 - "Datas e Tesouro"
Cohesion: 0.11
Nodes (15): today_br(), get_indexes(), get_product(), invest(), investment_out(), list_investments(), list_products(), redeem() (+7 more)

### Community 14 - "Community 14"
Cohesion: 0.14
Nodes (12): Lesson, Module, Q(), Question, right(), submit(), test_failing_then_passing_a_lesson(), test_no_leftover_placeholders() (+4 more)

### Community 15 - "Community 15"
Cohesion: 0.13
Nodes (22): App(), AssetPage, PerformancePage, Layout(), NAV, ProtectedRoute(), SearchBar(), fmtPct() (+14 more)

### Community 16 - "Community 16"
Cohesion: 0.20
Nodes (8): Base, Dividend, DividendPayment, IndexRate, Money(), Price(), Quantity(), StrEnumType()

### Community 17 - "Community 17"
Cohesion: 0.17
Nodes (20): check_all(), _evaluate(), _execute(), RiskError, set_levels(), buy(), cash(), reprice() (+12 more)

### Community 18 - "Community 18"
Cohesion: 0.13
Nodes (12): list_dividends(), sync_dividends(), deposit(), get_portfolio(), get_transactions(), AssetBrief, DividendItemOut, DividendSyncOut (+4 more)

### Community 19 - "Community 19"
Cohesion: 0.10
Nodes (24): brl, CLASS_LABEL, COUNTRY_LABEL, dt, FI_STATUS_LABEL, FI_TYPE_LABEL, fmtQtyRaw(), FREQ_LABEL (+16 more)

### Community 20 - "Community 20"
Cohesion: 0.10
Nodes (7): upgrade(), upgrade(), upgrade(), upgrade(), upgrade(), upgrade(), upgrade()

### Community 21 - "Community 21"
Cohesion: 0.17
Nodes (16): FixedIncomeInvestment, _close(), describe(), FixedIncomeError, invest(), InvestmentView, list_investments(), market_rate_for() (+8 more)

### Community 22 - "Community 22"
Cohesion: 0.09
Nodes (22): GROUPS, arrow(), BOARDS, PERIODS, Settings(), ApiError, Asset, AssetBrief (+14 more)

### Community 23 - "Community 23"
Cohesion: 0.11
Nodes (9): setup_logging(), check_connection(), lifespan(), health(), seed_assets(), deactivate_expired(), seed_samples(), sync_treasury() (+1 more)

### Community 24 - "Community 24"
Cohesion: 0.20
Nodes (18): RiskPanel(), fmtBRL(), fmtDate(), fmtDay(), fmtMoney(), fmtQty(), trend(), AssetPage() (+10 more)

### Community 25 - "Community 25"
Cohesion: 0.10
Nodes (22): Aulas e quizzes, Banco Central SGS (CDI, Selic, IPCA, IGP-M), Carteira virtual (R$100.000 inicial), Ferramentas de desenho, scripts/dev.sh e dev_db.sh, React 18 + TypeScript + Vite + lightweight-charts, Graficos e indicadores, index_data (+14 more)

### Community 26 - "Community 26"
Cohesion: 0.11
Nodes (22): devDependencies, @types/node@^22.10.2, @types/react@^18.3.12, @types/react-dom@^18.3.1, typescript@^5.7.2, vite@^6.0.7, @vitejs/plugin-react@^4.3.4, name (+14 more)

### Community 27 - "Community 27"
Cohesion: 0.11
Nodes (21): dependencies, lightweight-charts@^5.0.0, react@^18.3.1, react-dom@^18.3.1, react-router-dom@^6.28.0, recharts@^2.15.0, fmtDuration(), LearnPage() (+13 more)

### Community 28 - "Community 28"
Cohesion: 0.13
Nodes (3): Settings, test_database_url_gets_the_psycopg_driver(), test_production_refuses_weak_configuration()

### Community 29 - "Community 29"
Cohesion: 0.18
Nodes (3): MarketDataUnavailable, YahooProvider, FakeProvider

### Community 30 - "Community 30"
Cohesion: 0.22
Nodes (9): serve_media(), _external(), _manifest(), media_dir(), media_type(), resolve(), seconds_for(), _url() (+1 more)

### Community 31 - "Community 31"
Cohesion: 0.14
Nodes (15): PostgreSQL 14+ com unaccent, FastAPI + Pydantic v2 (API), PostgreSQL 16 + SQLAlchemy 2.0 + Alembic, Testes (143, pytest, sem rede), alembic 1.14.0, bcrypt 4.2.1, email-validator 2.2.0, fastapi 0.115.6 (+7 more)

### Community 32 - "Community 32"
Cohesion: 0.17
Nodes (10): lesson(), _load_tool(), media(), test_corrupted_manifest_does_not_break_lessons(), test_external_media_origin_trusts_the_manifest(), test_lesson_exposes_its_video(), test_manifest_roundtrip_is_atomic_and_keeps_other_lessons(), test_media_endpoint_never_leaks_other_files() (+2 more)

### Community 33 - "Community 33"
Cohesion: 0.19
Nodes (3): get_settings(), create_access_token(), decode_access_token()

### Community 34 - "Community 34"
Cohesion: 0.26
Nodes (8): hash_password(), verify_password(), User, authenticate(), EmailAlreadyRegisteredError, get_user_by_email(), normalize_email(), register_user()

### Community 35 - "Community 35"
Cohesion: 0.24
Nodes (9): pay_one(), _pay_event(), CashMovement, deposit(), DuplicateTransactionError, InsufficientFundsError, lock_portfolio(), record() (+1 more)

### Community 36 - "Community 36"
Cohesion: 0.13
Nodes (14): compilerOptions, isolatedModules, jsx, lib, module, moduleResolution, noEmit, noUnusedLocals (+6 more)

### Community 37 - "Community 37"
Cohesion: 0.29
Nodes (7): login(), me(), register(), LoginRequest, RegisterRequest, TokenResponse, UserOut

### Community 38 - "Community 38"
Cohesion: 0.19
Nodes (7): _cached_quote(), get_fx_rate(), get_history(), get_priced_quote(), get_quote(), PricedQuote, Quote

### Community 39 - "Community 39"
Cohesion: 0.24
Nodes (5): buy(), _get_holding(), _key(), sell(), TradeError

### Community 40 - "Community 40"
Cohesion: 0.18
Nodes (11): description, devDependencies, wrangler@^4.162.0, name, private, scripts, build, cf:dev (+3 more)

### Community 41 - "Community 41"
Cohesion: 0.24
Nodes (9): Publicar o simulador (DEPLOY), Backend FastAPI + workers (host sempre ligado), BACKEND_URL (Worker variable), Cloudflare Worker + site React, Dominio proprio, Variaveis de ambiente do backend, GET /api/health, Instancia unica com SCHEDULER_ENABLED (+1 more)

### Community 42 - "Community 42"
Cohesion: 0.20
Nodes (10): lessons, m3-l3, captions, created_at, duration_s, poster, size_bytes, source (+2 more)

### Community 43 - "Community 43"
Cohesion: 0.22
Nodes (10): Resgate antecipado (preco de mercado/desagio), fixed_income_catalog, fixed_income_math, fixed_income_service, Worker fixed_income_events, Worker fixed_income_sync, Ofertas de exemplo (CDB, LCI, LCA, CRI, CRA, debentures), Renda fixa (+2 more)

### Community 44 - "Community 44"
Cohesion: 0.22
Nodes (9): m0-l1, captions, created_at, duration_s, poster, size_bytes, source, title (+1 more)

### Community 45 - "Community 45"
Cohesion: 0.22
Nodes (9): m0-l2, captions, created_at, duration_s, poster, size_bytes, source, title (+1 more)

### Community 46 - "Community 46"
Cohesion: 0.22
Nodes (9): m0-l3, captions, created_at, duration_s, poster, size_bytes, source, title (+1 more)

### Community 47 - "Community 47"
Cohesion: 0.22
Nodes (9): m0-l4, captions, created_at, duration_s, poster, size_bytes, source, title (+1 more)

### Community 48 - "Community 48"
Cohesion: 0.22
Nodes (9): m0-l5, captions, created_at, duration_s, poster, size_bytes, source, title (+1 more)

### Community 49 - "Community 49"
Cohesion: 0.22
Nodes (9): m0-l6, captions, created_at, duration_s, poster, size_bytes, source, title (+1 more)

### Community 50 - "Community 50"
Cohesion: 0.22
Nodes (9): m0-l7, captions, created_at, duration_s, poster, size_bytes, source, title (+1 more)

### Community 51 - "Community 51"
Cohesion: 0.22
Nodes (9): m0-l8, captions, created_at, duration_s, poster, size_bytes, source, title (+1 more)

### Community 52 - "Community 52"
Cohesion: 0.22
Nodes (9): m1-l1, captions, created_at, duration_s, poster, size_bytes, source, title (+1 more)

### Community 53 - "Community 53"
Cohesion: 0.22
Nodes (9): m1-l2, captions, created_at, duration_s, poster, size_bytes, source, title (+1 more)

### Community 54 - "Community 54"
Cohesion: 0.22
Nodes (9): m1-l3, captions, created_at, duration_s, poster, size_bytes, source, title (+1 more)

### Community 55 - "Community 55"
Cohesion: 0.22
Nodes (9): m1-l4, captions, created_at, duration_s, poster, size_bytes, source, title (+1 more)

### Community 56 - "Community 56"
Cohesion: 0.22
Nodes (9): m2-l1, captions, created_at, duration_s, poster, size_bytes, source, title (+1 more)

### Community 57 - "Community 57"
Cohesion: 0.22
Nodes (9): m2-l2, captions, created_at, duration_s, poster, size_bytes, source, title (+1 more)

### Community 58 - "Community 58"
Cohesion: 0.22
Nodes (9): m2-l3, captions, created_at, duration_s, poster, size_bytes, source, title (+1 more)

### Community 59 - "Community 59"
Cohesion: 0.22
Nodes (9): m2-l4, captions, created_at, duration_s, poster, size_bytes, source, title (+1 more)

### Community 60 - "Community 60"
Cohesion: 0.22
Nodes (9): m2-l5, captions, created_at, duration_s, poster, size_bytes, source, title (+1 more)

### Community 61 - "Community 61"
Cohesion: 0.22
Nodes (9): m2-l6, captions, created_at, duration_s, poster, size_bytes, source, title (+1 more)

### Community 62 - "Community 62"
Cohesion: 0.22
Nodes (9): m3-l1, captions, created_at, duration_s, poster, size_bytes, source, title (+1 more)

### Community 63 - "Community 63"
Cohesion: 0.22
Nodes (9): m3-l2, captions, created_at, duration_s, poster, size_bytes, source, title (+1 more)

### Community 64 - "Community 64"
Cohesion: 0.22
Nodes (9): m3-l4, captions, created_at, duration_s, poster, size_bytes, source, title (+1 more)

### Community 65 - "Community 65"
Cohesion: 0.22
Nodes (9): m3-l5, captions, created_at, duration_s, poster, size_bytes, source, title (+1 more)

### Community 66 - "Community 66"
Cohesion: 0.22
Nodes (9): m4-l1, captions, created_at, duration_s, poster, size_bytes, source, title (+1 more)

### Community 67 - "Community 67"
Cohesion: 0.22
Nodes (9): m4-l2, captions, created_at, duration_s, poster, size_bytes, source, title (+1 more)

### Community 68 - "Community 68"
Cohesion: 0.22
Nodes (9): m4-l3, captions, created_at, duration_s, poster, size_bytes, source, title (+1 more)

### Community 69 - "Community 69"
Cohesion: 0.22
Nodes (9): m5-l1, captions, created_at, duration_s, poster, size_bytes, source, title (+1 more)

### Community 70 - "Community 70"
Cohesion: 0.22
Nodes (9): m5-l2, captions, created_at, duration_s, poster, size_bytes, source, title (+1 more)

### Community 71 - "Community 71"
Cohesion: 0.22
Nodes (9): m6-l1, captions, created_at, duration_s, poster, size_bytes, source, title (+1 more)

### Community 72 - "Community 72"
Cohesion: 0.22
Nodes (9): m6-l2, captions, created_at, duration_s, poster, size_bytes, source, title (+1 more)

### Community 73 - "Community 73"
Cohesion: 0.22
Nodes (9): m6-l3, captions, created_at, duration_s, poster, size_bytes, source, title (+1 more)

### Community 74 - "Community 74"
Cohesion: 0.22
Nodes (9): m6-l4, captions, created_at, duration_s, poster, size_bytes, source, title (+1 more)

### Community 75 - "Community 75"
Cohesion: 0.22
Nodes (9): m6-l5, captions, created_at, duration_s, poster, size_bytes, source, title (+1 more)

### Community 76 - "Community 76"
Cohesion: 0.22
Nodes (9): m7-l1, captions, created_at, duration_s, poster, size_bytes, source, title (+1 more)

### Community 77 - "Community 77"
Cohesion: 0.22
Nodes (9): m7-l2, captions, created_at, duration_s, poster, size_bytes, source, title (+1 more)

### Community 78 - "Community 78"
Cohesion: 0.22
Nodes (9): m7-l3, captions, created_at, duration_s, poster, size_bytes, source, title (+1 more)

### Community 79 - "Community 79"
Cohesion: 0.22
Nodes (9): m7-l4, captions, created_at, duration_s, poster, size_bytes, source, title (+1 more)

### Community 80 - "Community 80"
Cohesion: 0.25
Nodes (4): DividendEvent, get_dividends(), MarketDataProvider, set_provider()

### Community 81 - "Community 81"
Cohesion: 0.38
Nodes (4): MoneyError, quantize_quantity(), to_decimal(), test_money_helpers()

### Community 82 - "Community 82"
Cohesion: 0.33
Nodes (6): APScheduler workers, distribution_service, Worker distribution_discover, Worker distribution_pay, Proventos, APScheduler 3.11.0

### Community 83 - "Community 83"
Cohesion: 0.29
Nodes (5): Guia de visualizacao dos graficos (Recharts), Desempenho, Worker performance_snapshot, Ranking, Snapshots do patrimonio (portfolio_snapshots)

### Community 86 - "Community 86"
Cohesion: 0.53
Nodes (5): Videos: backend ou bucket R2 (MEDIA_BASE_URL), version, livro2video (gerador de videos), Pipeline videoaulas (build_pdf, generate_all, inject_series, publish), Videoaulas whiteboard

### Community 87 - "Community 87"
Cohesion: 0.40
Nodes (4): BACKEND_PORT, FRONTEND_PORT, PATH, dev.sh script

### Community 88 - "Community 88"
Cohesion: 0.67
Nodes (3): market_data (isolated source), Yahoo Finance (nao oficial), httpx 0.28.1

## Knowledge Gaps
- **27 isolated node(s):** `PATH`, `BACKEND_PORT`, `FRONTEND_PORT`, `Simulador de Investimentos (README)`, `Carteira virtual (R$100.000 inicial)` (+22 more)
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 688 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **9 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `lessons` connect `Community 42` to `Community 44`, `Community 45`, `Community 46`, `Community 47`, `Community 48`, `Community 49`, `Community 50`, `Community 51`, `Community 52`, `Community 53`, `Community 54`, `Community 55`, `Community 56`, `Community 57`, `Community 58`, `Community 59`, `Community 60`, `Community 61`, `Community 62`, `Community 63`, `Community 64`, `Community 65`, `Community 66`, `Community 67`, `Community 68`, `Community 69`, `Community 70`, `Community 71`, `Community 72`, `Community 73`, `Community 74`, `Community 75`, `Community 76`, `Community 77`, `Community 78`, `Community 79`, `Community 86`?**
  _High betweenness centrality (0.048) - this node is a cross-community bridge._
- **What connects `PATH`, `BACKEND_PORT`, `FRONTEND_PORT` to the rest of the system?**
  _27 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `Calendário e datas BR` be split into smaller, more focused modules?**
  _Cohesion score 0.05154639175257732 - nodes in this community are weakly interconnected._
- **Why does `quantize_money()` connect `Carteira e snapshots` to `Calendário e datas BR`, `Community 35`, `Dinheiro e ativos`, `Community 39`, `Enums do domínio`, `Community 81`, `Community 21`, `Community 23`, `Community 28`?**
  _High betweenness centrality (0.015) - this node is a cross-community bridge._
- **Should `Ferramentas de vídeo` be split into smaller, more focused modules?**
  _Cohesion score 0.05034199726402189 - nodes in this community are weakly interconnected._
- **Why does `Simulador de Investimentos` connect `Community 25` to `Community 43`, `Community 82`, `Community 83`, `Community 86`, `Community 88`, `Community 31`?**
  _High betweenness centrality (0.015) - this node is a cross-community bridge._
- **Should `Carteira e snapshots` be split into smaller, more focused modules?**
  _Cohesion score 0.057455540355677154 - nodes in this community are weakly interconnected._