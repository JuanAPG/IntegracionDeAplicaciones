#!/usr/bin/env bash
# tracking_server/run.sh
# Arranca el servidor de rastreo cargando tracking_server/.env.
#
# Se hace con un script y no exportando a mano para que el secreto no
# quede en el historial del intérprete de órdenes cada vez que se
# arranca: vive en .env, que está en .gitignore y con permisos 600.
set -euo pipefail
cd "$(dirname "$0")"

if [ -f .env ]; then
  set -a; . ./.env; set +a
else
  echo "AVISO: no hay .env. Sin JWT_SECRET_KEY no se autorizara ningun rastreo." >&2
fi

PUERTO="${PORT:-5900}"
if lsof -nP -iTCP:"$PUERTO" -sTCP:LISTEN >/dev/null 2>&1; then
  echo "El puerto $PUERTO ya esta ocupado por:" >&2
  lsof -nP -iTCP:"$PUERTO" -sTCP:LISTEN >&2
  echo "Detenlo, o arranca en otro puerto con  PORT=5901 ./run.sh" >&2
  exit 1
fi

exec ./.venv/bin/python app.py
