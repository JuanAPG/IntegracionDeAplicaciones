#!/usr/bin/env bash
# =====================================================================
# apps/services/users/scripts/pruebas.sh
# Bateria de humo del microservicio de USUARIOS contra la VM: PostgreSQL
# y Redis de verdad. Comprueba lo que las pruebas con simulacros no
# pueden comprobar —el SQL real, los disparadores de library.users y la
# autorizacion resuelta contra library.role_permissions— sin repetir lo
# que ya cubre test/test_users_mocked.py.
#
#   ./scripts/pruebas.sh                      # http://localhost:5002
#   BASE=http://192.168.1.50:5002 ./scripts/pruebas.sh
#   JWT=<token> ./scripts/pruebas.sh          # con un token ya emitido
#
# Requiere en la VM: la migracion aplicada (data/roles_migration.sql), el
# microservicio de login en pie (emite el JWT) y psql con las
# credenciales de entorno (PGHOST/PGPORT/PGDATABASE/PGUSER/PGPASSWORD;
# por omision las de la practica: 777).
#
# Deja la base como la encontro: la cuenta de prueba la borra al final.
#
# Convencion: toda asercion sobre cuerpo JSON lleva ?format=json
# explicito, porque el servicio responde XML por omision
# (DEFAULT_FORMAT=xml). Solo la seccion 3 prueba ese XML.
# =====================================================================
set -uo pipefail

BASE="${BASE:-http://localhost:5002}"
# Los recursos cuelgan de la raiz. Si el despliegue usa API_PREFIX, pase
# el mismo valor aqui:  API_PREFIX=/api ./scripts/pruebas.sh
API="$BASE${API_PREFIX:-}"

# El JWT lo emite POST /login del microservicio de login (puerto 5000) y
# dura 30 min. Aqui se obtiene uno real; tambien se puede pasar ya hecho
# con JWT=<token>, igual que en el pruebas.sh de libros.
LOGIN_BASE="${LOGIN_BASE:-http://localhost:5000}"
ADMIN_EMAIL="${ADMIN_EMAIL:-admin@library.local}"
ADMIN_PASSWORD="${ADMIN_PASSWORD:-Admin123!}"

EMAIL_PRUEBA="prueba.users@ejemplo.local"
PASS_PRUEBA="Secreto123"

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
# Insensible a espacios: el JSON sale compacto ("isActive":false) con
# DEBUG=false y con espacios en desarrollo; se normalizan ambos lados.
contiene() {
    local desc="$1" texto="$2"; shift 2
    local plano
    plano=$(printf '%s' "$texto" | tr -d '[:space:]')
    if curl -s "$@" | tr -d '[:space:]' | grep -qF -- "$plano"; then pasa "$desc"
    else falla "$desc (no aparece: $texto)"; fi
}

# no_contiene <descripcion> <texto literal> <curl args...>
# Lo contrario de contiene, sin distinguir mayusculas: sirve para exigir
# que algo NUNCA viaje en la respuesta (aqui, la contrasena).
no_contiene() {
    local desc="$1" texto="$2"; shift 2
    if curl -s "$@" | grep -qiF -- "$texto"; then falla "$desc (aparece: $texto)"
    else pasa "$desc"; fi
}

psql_cmd() {
    psql -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" -d "$PGDATABASE" -tAc "$1"
}

echo "Microservicio: $BASE"
echo

# Gunicorn tarda unos segundos en levantar los workers tras un reinicio;
# sin esta espera, la primera peticion puede dar 000 y ensuciar el reporte.
sleep 3

echo "0. Limpieza previa de la cuenta de prueba"
psql_cmd "DELETE FROM library.users WHERE lower(email) = lower('$EMAIL_PRUEBA');" \
    >/dev/null 2>&1 || falla "psql no disponible (revise PGHOST/PGUSER/PGPASSWORD)"

# Token de administrador. Sin el solo se prueban /health y los 401.
if [ -z "${JWT:-}" ]; then
    JWT=$(curl -s -X POST "$LOGIN_BASE/login?format=json" \
          -H 'Content-Type: application/json' \
          -d "{\"email\": \"$ADMIN_EMAIL\", \"password\": \"$ADMIN_PASSWORD\"}" \
          | sed -n 's/.*"token": *"\([^"]*\)".*/\1/p' | head -1)
fi
AUTH=()
[ -n "${JWT:-}" ] && AUTH=(-H "Authorization: Bearer $JWT")

echo
echo "1. Servicio"
esperado_http "estado del servicio" 200 "$BASE/health"

echo
echo "2. Ninguna lectura es publica"
esperado_http "listado sin token es 401"  401 "$API/users?format=json"
esperado_http "una cuenta sin token es 401" 401 "$API/users/1?format=json"

echo
echo "3. Ciclo de una cuenta de prueba (alta, consulta, baja)"
if [ -z "${JWT:-}" ]; then
    echo "  (sin JWT: no se pudo iniciar sesion en $LOGIN_BASE; pase JWT=<token>)"
else
# El alta la hace un administrador, de modo que puede fijar el rol y
# marcar el correo como verificado: hace falta para iniciar sesion luego.
respuesta=$(curl -s -X POST "$API/users?format=json" \
    -H 'Content-Type: application/json' ${AUTH[@]+"${AUTH[@]}"} -d "{
  \"nombre\": \"Prueba\",
  \"apellidoPaterno\": \"Usuarios\",
  \"apellidoMaterno\": \"VM\",
  \"email\": \"$EMAIL_PRUEBA\",
  \"password\": \"$PASS_PRUEBA\",
  \"role\": \"user\",
  \"emailVerified\": true
}")
NUEVO_ID=$(printf '%s' "$respuesta" | sed -n 's/.*"id": *\([0-9]*\).*/\1/p' | head -1)

if [ -n "$NUEVO_ID" ]; then pasa "alta de la cuenta (id $NUEVO_ID)"
else falla "alta de la cuenta: $respuesta"; fi

if [ -n "$NUEVO_ID" ]; then
    contiene "consulta de la cuenta en JSON" "\"email\": \"$EMAIL_PRUEBA\"" \
        ${AUTH[@]+"${AUTH[@]}"} "$API/users/$NUEVO_ID?format=json"
    contiene "el disparador compuso full_name" '"fullName": "Prueba Usuarios VM"' \
        ${AUTH[@]+"${AUTH[@]}"} "$API/users/$NUEVO_ID?format=json"
    no_contiene "la respuesta NUNCA trae la contrasena" 'password' \
        ${AUTH[@]+"${AUTH[@]}"} "$API/users/$NUEVO_ID?format=json"
    contiene "la misma cuenta en XML por omision" '<user' \
        ${AUTH[@]+"${AUTH[@]}"} "$API/users/$NUEVO_ID"

    # Un token del rol 'user' no tiene users:read: el servicio debe
    # distinguir "no autenticado" (401) de "autenticado sin permiso" (403).
    TOKEN_CLIENTE=$(curl -s -X POST "$LOGIN_BASE/login?format=json" \
        -H 'Content-Type: application/json' \
        -d "{\"email\": \"$EMAIL_PRUEBA\", \"password\": \"$PASS_PRUEBA\"}" \
        | sed -n 's/.*"token": *"\([^"]*\)".*/\1/p' | head -1)
    if [ -n "$TOKEN_CLIENTE" ]; then
        esperado_http "un rol sin users:read recibe 403" 403 \
            -H "Authorization: Bearer $TOKEN_CLIENTE" "$API/users?format=json"
        esperado_http "pero si puede ver su propia cuenta" 200 \
            -H "Authorization: Bearer $TOKEN_CLIENTE" "$API/users/$NUEVO_ID?format=json"
    else
        falla "la cuenta de prueba no pudo iniciar sesion en $LOGIN_BASE"
    fi

    # La baja es LOGICA: la fila se conserva porque library.orders la
    # referencia con ON DELETE RESTRICT.
    contiene "baja logica de la cuenta" '"isActive": false' \
        -X DELETE ${AUTH[@]+"${AUTH[@]}"} "$API/users/$NUEVO_ID?format=json"
    if [ -n "$(psql_cmd "SELECT 1 FROM library.users WHERE id = $NUEVO_ID AND is_active = FALSE;")" ]; then
        pasa "la fila sigue en la base, desactivada"
    else
        falla "la fila sigue en la base, desactivada"
    fi
fi
fi # fin del ciclo con JWT

echo
echo "4. Limpieza: se borra la cuenta de prueba"
psql_cmd "DELETE FROM library.users WHERE lower(email) = lower('$EMAIL_PRUEBA');" >/dev/null
if [ -z "$(psql_cmd "SELECT 1 FROM library.users WHERE lower(email) = lower('$EMAIL_PRUEBA');")" ]; then
    pasa "cuenta de prueba eliminada"
else
    falla "cuenta de prueba eliminada"
fi

echo
echo "---------------------------------------------"
printf 'Pruebas superadas: %d   fallidas: %d\n' "$ok" "$fallos"
[ "$fallos" -eq 0 ] || exit 1
