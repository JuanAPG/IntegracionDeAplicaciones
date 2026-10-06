#!/usr/bin/env bash
# =====================================================================
# scripts/run_tests.sh
# Corre las baterias de pruebas MOCKEADAS de los seis microservicios:
# sin PostgreSQL y sin servidor Redis (ambos se simulan).
#
#   ./scripts/run_tests.sh
#
# Cada servicio usa su propio .venv si existe; si no, el python del
# entorno actual. Para instalar un venv de servicio:
#
#   cd apps/services/<servicio>
#   python3 -m venv .venv && ./.venv/bin/pip install -r requirements.txt
#   ./.venv/bin/pip install -e ../../../packages/library_common
#
# Las pruebas LIVE (contra la VM, con PostgreSQL y Redis de verdad) son
# los scripts/pruebas.sh de cada servicio.
# =====================================================================
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TOTAL_OK=0; TOTAL_FALLOS=0; SUITES_MAL=0; OMITIDAS=0

# Interprete de un servicio: su propio .venv, o el que se indique con la
# variable PYTHON (util para correr las siete baterias con un unico venv
# de pruebas), o python3 a secas como ultimo recurso.
python_de() {
    local dir="$1"
    if [ -x "$dir/.venv/bin/python" ]; then echo "$dir/.venv/bin/python"
    elif [ -n "${PYTHON:-}" ] && [ -x "${PYTHON}" ]; then echo "$PYTHON"
    else command -v python3; fi
}

# Comprueba que el interprete tenga lo imprescindible ANTES de correr la
# bateria: un ModuleNotFoundError a media pantalla no dice que hacer.
faltan_dependencias() {
    local py="$1"
    "$py" - <<'EOP' 2>/dev/null
import importlib, sys
faltan = [m for m in ("flask", "jwt", "redis", "flasgger", "flask_cors")
          if importlib.util.find_spec(m) is None]
print(",".join(faltan))
sys.exit(0)
EOP
}

corre() {
    local nombre="$1" dir="$2" archivo="$3"
    if [ ! -f "$dir/$archivo" ]; then
        printf "  %-28s (sin pruebas)\n" "$nombre"; return
    fi
    local py salida linea ok fallos faltan
    py="$(python_de "$dir")"
    faltan="$(faltan_dependencias "$py")"
    if [ -n "$faltan" ]; then
        printf "  %-28s OMITIDA — faltan: %s\n" "$nombre" "$faltan"
        echo "      interprete: $py"
        echo "      arregla con:  cd $(basename "$dir") && python3 -m venv .venv \\"
        echo "                    && ./.venv/bin/pip install -r requirements.txt \\"
        echo "                    && ./.venv/bin/pip install -e packages/library_common"
        echo "      o reutiliza un venv ya armado:  PYTHON=/ruta/a/python ./scripts/run_tests.sh"
        OMITIDAS=$((OMITIDAS + 1)); return
    fi
    salida=$(cd "$dir" && "$py" "$archivo" 2>&1 | grep -vE "^20[0-9]{2}-")
    linea=$(echo "$salida" | grep -E "^Resultado:" | tail -1)
    if [ -z "$linea" ]; then
        echo "  ERROR  $nombre -> la bateria no termino"
        echo "$salida" | tail -8
        SUITES_MAL=$((SUITES_MAL + 1)); return
    fi
    ok=$(echo "$linea" | sed -E 's/Resultado: ([0-9]+) OK.*/\1/')
    fallos=$(echo "$linea" | sed -E 's/.*, ([0-9]+) fallos/\1/')
    TOTAL_OK=$((TOTAL_OK + ok)); TOTAL_FALLOS=$((TOTAL_FALLOS + fallos))
    if [ "$fallos" != "0" ]; then
        SUITES_MAL=$((SUITES_MAL + 1))
        printf "  %-28s %3s OK  %s FALLOS\n" "$nombre" "$ok" "$fallos"
        echo "$salida" | grep "FALLA" | head -8
    else
        printf "  %-28s %3s OK\n" "$nombre" "$ok"
    fi
}

echo "=== Pruebas mockeadas (sin PostgreSQL ni Redis) ==="
corre "login (flujo completo)" "$ROOT/apps/services/login"   test/test_login_mocked.py
corre "login (Redis/JWT)"      "$ROOT/apps/services/login"   test/test_redis_auth.py
corre "books (cache/authz)"    "$ROOT/library_soap_service"  test/test_books_cache.py
corre "users"                  "$ROOT/apps/services/users"   test/test_users_mocked.py
corre "authors"                "$ROOT/apps/services/authors" test/test_authors_mocked.py
corre "pedidos"                "$ROOT/apps/services/pedidos" test/test_pedidos_mocked.py
corre "pagos"                  "$ROOT/apps/services/pagos"   test/test_pagos_mocked.py
echo "---------------------------------------------------"
if [ "$SUITES_MAL" -eq 0 ]; then
    printf "  TODO EN VERDE: %s aserciones\n" "$TOTAL_OK"
else
    printf "  %s aserciones OK, %s fallos en %s bateria(s)\n" \
        "$TOTAL_OK" "$TOTAL_FALLOS" "$SUITES_MAL"
fi
if [ "$OMITIDAS" -gt 0 ]; then
    printf "  %s bateria(s) OMITIDAS por falta de dependencias (ver arriba).\n" \
        "$OMITIDAS"
fi
# Una bateria omitida no es un fallo, pero tampoco es un aprobado: se
# devuelve 2 para que un CI lo note sin confundirlo con una prueba rota.
if [ "$SUITES_MAL" -gt 0 ]; then exit 1; fi
if [ "$OMITIDAS" -gt 0 ]; then exit 2; fi
exit 0
