#!/usr/bin/env bash
# =====================================================================
# apps/services/authors/scripts/pruebas.sh
# Bateria de humo del microservicio de AUTORES contra la VM: PostgreSQL
# y Redis de verdad. Comprueba lo que las pruebas con simulacros no
# pueden comprobar —el cache real en Redis (X-Cache: MISS y luego HIT),
# el UNIQUE de library.authors y el CASCADE de library.book_authors— sin
# repetir lo que ya cubre test/test_authors_mocked.py.
#
#   ./scripts/pruebas.sh                      # http://localhost:5003
#   BASE=http://192.168.1.50:5003 ./scripts/pruebas.sh
#   JWT=<token> ./scripts/pruebas.sh          # con un token ya emitido
#
# Requiere en la VM: la migracion aplicada (data/roles_migration.sql), el
# microservicio de login en pie (emite el JWT), Redis escuchando y psql
# con las credenciales de entorno (PGHOST/PGPORT/PGDATABASE/PGUSER/
# PGPASSWORD; por omision las de la practica: 777).
#
# Deja la base como la encontro: el autor de prueba lo borra al final.
#
# Convencion: toda asercion sobre cuerpo JSON lleva ?format=json
# explicito, porque el servicio responde XML por omision
# (DEFAULT_FORMAT=xml).
# =====================================================================
set -uo pipefail

BASE="${BASE:-http://localhost:5003}"
# Los recursos cuelgan de la raiz. Si el despliegue usa API_PREFIX, pase
# el mismo valor aqui:  API_PREFIX=/api ./scripts/pruebas.sh
API="$BASE${API_PREFIX:-}"

# El JWT lo emite POST /login del microservicio de login (puerto 5000) y
# dura 30 min. Aqui se obtiene uno real; tambien se puede pasar ya hecho
# con JWT=<token>, igual que en el pruebas.sh de libros.
LOGIN_BASE="${LOGIN_BASE:-http://localhost:5000}"
ADMIN_EMAIL="${ADMIN_EMAIL:-admin@library.local}"
ADMIN_PASSWORD="${ADMIN_PASSWORD:-Admin123!}"

NOMBRE_PRUEBA="Autor De Prueba Humo"
NOMBRE_RENOMBRADO="Autor De Prueba Humo Renombrado"
# Libro del catalogo sembrado al que se vincula la obra de prueba; se
# usa solo para que el autor tenga obras y el borrado de 409.
LIBRO_PRUEBA="${LIBRO_PRUEBA:-1}"

PGHOST="${PGHOST:-localhost}"
PGPORT="${PGPORT:-5432}"
PGDATABASE="${PGDATABASE:-library_db}"
PGUSER="${PGUSER:-library_user}"
export PGPASSWORD="${PGPASSWORD:-777}"

ok=0
fallos=0

pasa() { printf '  \033[32mOK\033[0m   %s\n' "$1"; ok=$((ok + 1)); }
falla() { printf '  \033[31mFALLA\033[0m %s\n' "$1"; fallos=$((fallos + 1)); }

# esperado_http <descripcion> <codigo esperado> <curl args...>
esperado_http() {
    local desc="$1" esperado="$2"; shift 2
    local codigo
    codigo=$(curl -s -o /dev/null -w '%{http_code}' "$@")
    if [ "$codigo" = "$esperado" ]; then pasa "$desc (HTTP $codigo)"
    else falla "$desc (esperado $esperado, recibido $codigo)"; fi
}

# contiene <descripcion> <texto literal> <curl args...>
# -F: el texto se compara tal cual, sin expresion regular.
# Insensible a espacios: el JSON sale compacto ("name":"...") con
# DEBUG=false y con espacios en desarrollo; se normalizan ambos lados.
# Tambien sirve para las cabeceras, con -D - -o /dev/null.
contiene() {
    local desc="$1" texto="$2"; shift 2
    local plano
    plano=$(printf '%s' "$texto" | tr -d '[:space:]')
    if curl -s "$@" | tr -d '[:space:]' | grep -qF -- "$plano"; then pasa "$desc"
    else falla "$desc (no aparece: $texto)"; fi
}

psql_cmd() {
    psql -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" -d "$PGDATABASE" -tAc "$1"
}

echo "Microservicio: $BASE"
echo

# Gunicorn tarda unos segundos en levantar los workers tras un reinicio;
# sin esta espera, la primera peticion puede dar 000 y ensuciar el reporte.
sleep 3

echo "0. Limpieza previa del autor de prueba"
psql_cmd "DELETE FROM library.authors WHERE name IN ('$NOMBRE_PRUEBA', '$NOMBRE_RENOMBRADO');" \
    >/dev/null 2>&1 || falla "psql no disponible (revise PGHOST/PGUSER/PGPASSWORD)"

# Token de administrador. Sin el solo se prueban las lecturas y el 401.
if [ -z "${JWT:-}" ]; then
    JWT=$(curl -s -X POST "$LOGIN_BASE/login?format=json" \
          -H 'Content-Type: application/json' \
          -d "{\"email\": \"$ADMIN_EMAIL\", \"password\": \"$ADMIN_PASSWORD\"}" \
          | sed -n 's/.*"token": *"\([^"]*\)".*/\1/p' | head -1)
fi
AUTH=()
[ -n "${JWT:-}" ] && AUTH=(-H "Authorization: Bearer $JWT")

echo
echo "1. Servicio y lecturas publicas"
esperado_http "estado del servicio"            200 "$BASE/health"
esperado_http "catalogo de autores sin token"  200 "$API/authors?format=json"

echo
echo "2. Cache de Redis (X-Cache)"
# Filtro unico por corrida: estrena su propia entrada de cache, de modo
# que el primer MISS es deterministico aunque el servicio lleve horas en pie.
CONSULTA="humo$$"
contiene "la primera lectura es MISS" 'X-Cache: MISS' \
    -D - -o /dev/null "$API/authors?format=json&q=$CONSULTA"
contiene "la segunda lectura es HIT"  'X-Cache: HIT' \
    -D - -o /dev/null "$API/authors?format=json&q=$CONSULTA"

echo
echo "3. Las escrituras exigen token"
esperado_http "alta sin token es 401" 401 -X POST "$API/authors?format=json" \
    -H 'Content-Type: application/json' -d "{\"name\": \"$NOMBRE_PRUEBA\"}"

echo
echo "4. Ciclo del autor de prueba (alta, renombrado, baja)"
if [ -z "${JWT:-}" ]; then
    echo "  (sin JWT: no se pudo iniciar sesion en $LOGIN_BASE; pase JWT=<token>)"
else
respuesta=$(curl -s -X POST "$API/authors?format=json" \
    -H 'Content-Type: application/json' ${AUTH[@]+"${AUTH[@]}"} \
    -d "{\"name\": \"$NOMBRE_PRUEBA\"}")
NUEVO_ID=$(printf '%s' "$respuesta" | sed -n 's/.*"id": *\([0-9]*\).*/\1/p' | head -1)

if [ -n "$NUEVO_ID" ]; then pasa "alta del autor (id $NUEVO_ID)"
else falla "alta del autor: $respuesta"; fi

if [ -n "$NUEVO_ID" ]; then
    # library.authors.name es UNIQUE y la comparacion no distingue
    # mayusculas: repetir el nombre tiene que chocar.
    esperado_http "nombre duplicado es 409" 409 -X POST "$API/authors?format=json" \
        -H 'Content-Type: application/json' ${AUTH[@]+"${AUTH[@]}"} \
        -d "{\"name\": \"$NOMBRE_PRUEBA\"}"
    contiene "renombrado (PUT cambia el nombre)" "\"name\": \"$NOMBRE_RENOMBRADO\"" \
        -X PUT "$API/authors/$NUEVO_ID?format=json" \
        -H 'Content-Type: application/json' ${AUTH[@]+"${AUTH[@]}"} \
        -d "{\"name\": \"$NOMBRE_RENOMBRADO\"}"

    # Con una obra vinculada, borrar al autor dejaria ese libro sin
    # autoria (book_authors cae por ON DELETE CASCADE): hace falta
    # confirmarlo con ?force=true.
    esperado_http "vincular una obra" 201 \
        -X POST "$API/authors/$NUEVO_ID/books/$LIBRO_PRUEBA?format=json" \
        ${AUTH[@]+"${AUTH[@]}"}
    esperado_http "borrar un autor con obras es 409" 409 \
        -X DELETE "$API/authors/$NUEVO_ID?format=json" ${AUTH[@]+"${AUTH[@]}"}
    esperado_http "con ?force=true si se borra" 200 \
        -X DELETE "$API/authors/$NUEVO_ID?format=json&force=true" ${AUTH[@]+"${AUTH[@]}"}
    esperado_http "el autor ya no existe" 404 "$API/authors/$NUEVO_ID?format=json"
fi
fi # fin del ciclo con JWT

echo
echo "5. Limpieza: no debe quedar rastro del autor de prueba"
psql_cmd "DELETE FROM library.authors WHERE name IN ('$NOMBRE_PRUEBA', '$NOMBRE_RENOMBRADO');" >/dev/null
if [ -z "$(psql_cmd "SELECT 1 FROM library.authors WHERE name IN ('$NOMBRE_PRUEBA', '$NOMBRE_RENOMBRADO');")" ]; then
    pasa "autor de prueba eliminado"
else
    falla "autor de prueba eliminado"
fi

echo
echo "---------------------------------------------"
printf 'Pruebas superadas: %d   fallidas: %d\n' "$ok" "$fallos"
[ "$fallos" -eq 0 ] || exit 1
