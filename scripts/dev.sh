#!/usr/bin/env bash
# Sobe tudo para desenvolvimento: Postgres local, migrations, backend e frontend.
# Ctrl+C encerra backend e frontend (o Postgres continua; pare com scripts/dev_db.sh stop).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
export PATH="$ROOT/.tools/node/bin:$PATH"
# Portas configuráveis: BACKEND_PORT=8010 FRONTEND_PORT=5180 scripts/dev.sh
export BACKEND_PORT="${BACKEND_PORT:-8000}" FRONTEND_PORT="${FRONTEND_PORT:-5173}"

[ -f .env ] || { echo "Crie o .env a partir do .env.example"; exit 1; }
scripts/dev_db.sh start
.venv/bin/alembic upgrade head

.venv/bin/uvicorn backend.main:app --reload --reload-dir backend --port "$BACKEND_PORT" &
BACK=$!
(cd frontend && npm run dev -- --host localhost --strictPort) &
FRONT=$!
trap 'kill $BACK $FRONT 2>/dev/null' INT TERM EXIT
echo ">> Backend: http://localhost:$BACKEND_PORT/docs   Frontend: http://localhost:$FRONTEND_PORT"
wait
