#!/usr/bin/env bash
# Roda o site completo (Postgres, migrations, API e frontend) com um comando.
# Uso:  ./rodar.sh            -> site em http://localhost:7000 (API na 8010)
#       ./rodar.sh parar      -> encerra o Postgres local
# Portas diferentes: SITE_PORT=5173 API_PORT=8000 ./rodar.sh
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

if [ "${1:-}" = "parar" ]; then
  exec scripts/dev_db.sh stop
fi

SITE_PORT="${SITE_PORT:-7000}"
API_PORT="${API_PORT:-8010}"

echo ">> Site:  http://localhost:$SITE_PORT"
echo ">> API:   http://localhost:$API_PORT/docs"
echo ">> Login de demonstração: demo@simulador.dev / demo12345"
echo ">> Ctrl+C encerra o site (o Postgres continua; ./rodar.sh parar)"
echo

BACKEND_PORT="$API_PORT" FRONTEND_PORT="$SITE_PORT" \
CORS_ORIGINS="http://localhost:$SITE_PORT" \
exec scripts/dev.sh
