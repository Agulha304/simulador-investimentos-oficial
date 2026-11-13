#!/usr/bin/env bash
# Postgres local do projeto (não precisa de sudo). Dados em .pgdata/, porta 5433.
# Uso: scripts/dev_db.sh start|stop|status
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PGBIN="${PGBIN:-/usr/lib/postgresql/16/bin}"
PGDATA="$ROOT/.pgdata"
PORT="${DEV_DB_PORT:-5433}"
SOCKDIR="$PGDATA/run"

init() {
  [ -f "$PGDATA/PG_VERSION" ] && return
  echo ">> Inicializando cluster em $PGDATA"
  "$PGBIN/initdb" -D "$PGDATA" -U simulador --auth=trust -E UTF8 --locale=C.UTF-8 >/dev/null
  mkdir -p "$SOCKDIR"
}

case "${1:-start}" in
  start)
    init
    mkdir -p "$SOCKDIR"
    if "$PGBIN/pg_ctl" -D "$PGDATA" status >/dev/null 2>&1; then echo ">> Postgres já está rodando (porta $PORT)"; else
      "$PGBIN/pg_ctl" -D "$PGDATA" -l "$PGDATA/server.log" -w \
        -o "-p $PORT -k $SOCKDIR -c listen_addresses=localhost" start >/dev/null
      echo ">> Postgres iniciado na porta $PORT"
    fi
    for db in simulador simulador_test; do
      "$PGBIN/psql" -h localhost -p "$PORT" -U simulador -d postgres -tAc "SELECT 1 FROM pg_database WHERE datname='$db'" | grep -q 1 \
        || { "$PGBIN/createdb" -h localhost -p "$PORT" -U simulador "$db"; echo ">> banco $db criado"; }
    done ;;
  stop)   "$PGBIN/pg_ctl" -D "$PGDATA" -m fast stop ;;
  status) "$PGBIN/pg_ctl" -D "$PGDATA" status ;;
  *) echo "uso: $0 start|stop|status"; exit 1 ;;
esac
