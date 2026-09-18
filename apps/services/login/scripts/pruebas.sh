#!/usr/bin/env bash
# =====================================================================
# apps/services/login/scripts/pruebas.sh
# Bateria de humo del microservicio de autenticacion: recorre registro,
# verificacion, sesion y los dos formatos de intercambio (XML por omision,
# JSON con ?format=json), ademas de CORS y los codigos de error.
#
#   ./scripts/pruebas.sh                      # http://localhost:5000
#   BASE=http://192.168.1.50:5000 ./scripts/pruebas.sh
#
# Requiere en la VM: la migracion aplicada (data/login_migration.sql), sendmail
# local y psql con las credenciales de entorno (PGHOST/PGPORT/PGDATABASE/
# PGUSER/PGPASSWORD; por omision las de la practica: 777).
#
# Deja la base como la encontro: el usuario de prueba lo borra al final.
# El canje REAL del token se hace con el correo que llega por sendmail; aqui
# se verifica el endpoint con un token falso (404) y el flujo continua con
# una activacion por operador, documentada en el README.
# =====================================================================
set -uo pipefail

BASE="${BASE:-http://localhost:5000}"
JAR="$(mktemp -t login-jar.XXXXXX)"
trap 'rm -f "$JAR"' EXIT

PGHOST="${PGHOST:-localhost}"
PGPORT="${PGPORT:-5432}"
PGDATABASE="${PGDATABASE:-library_db}"
PGUSER="${PGUSER:-library_user}"
export PGPASSWORD="${PGPASSWORD:-777}"

EMAIL_PRUEBA="prueba.login@ejemplo.local"

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
# Insensible a espacios: el JSON sale compacto ("valid":false) con
# DEBUG=false y con espacios en desarrollo; se normalizan ambos lados.
contiene() {
    local desc="$1" texto="$2"; shift 2
    local plano
    plano=$(printf '%s' "$texto" | tr -d '[:space:]')
    if curl -s "$@" | tr -d '[:space:]' | grep -qF -- "$plano"; then pasa "$desc"
    else falla "$desc (no aparece: $texto)"; fi
}

# contiene_psql <descripcion> <texto literal> <sql>
contiene_psql() {
    local desc="$1" texto="$2" sql="$3"
    if psql_cmd "$sql" | grep -qF -- "$texto"; then pasa "$desc"
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

echo "0. Limpieza previa del usuario de prueba"
psql_cmd "DELETE FROM library.users WHERE lower(email) = lower('$EMAIL_PRUEBA');" \
    >/dev/null 2>&1 || falla "psql no disponible (revise PGHOST/PGUSER/PGPASSWORD)"

echo
echo "1. Servicio y documentacion"
esperado_http "indice"                 200 "$BASE/"
esperado_http "estado de la base"      200 "$BASE/health"
esperado_http "especificacion OpenAPI" 200 "$BASE/openapi.json"
esperado_http "Swagger UI"             200 -L "$BASE/docs"
contiene "el indice anuncia /docs" '"swaggerUi"' "$BASE/?format=json"

echo
echo "2. Validacion previa del correo"
contiene "sintaxis invalida se reporta" '"valid": false' \
    "$BASE/validate-email?email=no-es-correo&format=json"
contiene "correo nuevo disponible" '"available": true' \
    "$BASE/validate-email?email=$EMAIL_PRUEBA&format=json"
esperado_http "validacion en XML por omision" 200 "$BASE/validate-email?email=$EMAIL_PRUEBA"
contiene "el XML trae <validation" '<validation' "$BASE/validate-email?email=$EMAIL_PRUEBA"

echo
echo "3. Registro"
esperado_http "registro incompleto es 400" 400 -X POST "$BASE/register?format=json" \
    -H "Content-Type: application/json" -d '{"email": "x@y.zz"}'
esperado_http "registro JSON es 201" 201 -X POST "$BASE/register?format=json" \
    -H "Content-Type: application/json" \
    -d "{\"nombre\": \"Prueba\", \"apellidoPaterno\": \"Login\",
         \"apellidoMaterno\": \"VM\", \"email\": \"$EMAIL_PRUEBA\",
         \"password\": \"Secreto123\"}"
contiene "el registro pide verificar" '"required": true' -X POST "$BASE/register?format=json" \
    -H "Content-Type: application/json" \
    -d '{"nombre": "Otro", "email": "otro@ejemplo.local", "password": "Secreto123"}' \
    || true
psql_cmd "DELETE FROM library.users WHERE lower(email) = 'otro@ejemplo.local';" >/dev/null 2>&1 || true
contiene "el registro por omision es XML" '<registration' -X POST "$BASE/register" \
    -H "Content-Type: application/json" \
    -d "{\"nombre\": \"Xml\", \"apellidoPaterno\": \"Omision\",
         \"email\": \"xml.omision@ejemplo.local\", \"password\": \"Secreto123\"}"
psql_cmd "DELETE FROM library.users WHERE lower(email) = 'xml.omision@ejemplo.local';" >/dev/null 2>&1 || true
esperado_http "correo duplicado es 409" 409 -X POST "$BASE/register?format=json" \
    -H "Content-Type: application/json" \
    -d "{\"nombre\": \"Prueba\", \"apellidoPaterno\": \"Login\",
         \"email\": \"$EMAIL_PRUEBA\", \"password\": \"Secreto123\"}"
contiene_psql "nombre normalizado en la base" 'Prueba' \
    "SELECT first_name || ' ' || last_name_paternal FROM library.users WHERE lower(email) = lower('$EMAIL_PRUEBA');"

echo
echo "4. Verificacion"
esperado_http "token falso es 404" 404 "$BASE/verify?token=falso&format=json"
esperado_http "login sin verificar es 403" 403 -c "$JAR" -X POST "$BASE/login?format=json" \
    -H "Content-Type: application/json" \
    -d "{\"email\": \"$EMAIL_PRUEBA\", \"password\": \"Secreto123\"}"
echo "  -- activacion por operador (equivale al clic del correo) --"
psql_cmd "UPDATE library.users SET email_verified = TRUE WHERE lower(email) = lower('$EMAIL_PRUEBA');" >/dev/null
psql_cmd "INSERT INTO library.verified_emails (email, user_id, source) SELECT lower(email), id, 'token' FROM library.users WHERE lower(email) = lower('$EMAIL_PRUEBA') ON CONFLICT (email) DO UPDATE SET verified_at = now();" >/dev/null
contiene "correo ya verificado" '"verified": true' \
    "$BASE/validate-email?email=$EMAIL_PRUEBA&format=json"

echo
echo "5. Sesion Flask"
esperado_http "credencial mala es 401" 401 -c "$JAR" -X POST "$BASE/login?format=json" \
    -H "Content-Type: application/json" \
    -d "{\"email\": \"$EMAIL_PRUEBA\", \"password\": \"OtraClave\"}"
contiene "login correcto" '"authenticated": true' -c "$JAR" -X POST "$BASE/login?format=json" \
    -H "Content-Type: application/json" \
    -d "{\"email\": \"$EMAIL_PRUEBA\", \"password\": \"Secreto123\"}"
contiene "sesion autenticada" '"authenticated": true' -b "$JAR" "$BASE/session?format=json"
contiene "sesion en XML por omision" '<session' -b "$JAR" "$BASE/session"
contiene "logout" '"authenticated": false' -b "$JAR" -c "$JAR" -X POST "$BASE/logout?format=json"
contiene "sesion cerrada" '"authenticated": false' -b "$JAR" "$BASE/session?format=json"

echo
echo "6. CORS"
contiene "origen permitido" 'Access-Control-Allow-Origin' -D - -o /dev/null \
    -H "Origin: http://localhost:3000" "$BASE/session?format=json"

echo
echo "7. Limpieza: se borra el usuario de prueba"
psql_cmd "DELETE FROM library.users WHERE lower(email) = lower('$EMAIL_PRUEBA');" >/dev/null
if [ -z "$(psql_cmd "SELECT 1 FROM library.users WHERE lower(email) = lower('$EMAIL_PRUEBA');")" ]; then
    pasa "usuario de prueba eliminado"
else
    falla "usuario de prueba eliminado"
fi

echo
echo "Resultado: $ok OK, $fallos fallos"
[ "$fallos" -eq 0 ]
