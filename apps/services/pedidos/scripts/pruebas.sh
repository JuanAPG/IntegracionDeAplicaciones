#!/usr/bin/env bash
# =====================================================================
# apps/services/pedidos/scripts/pruebas.sh
# Bateria de humo del microservicio de PEDIDOS contra PostgreSQL y Redis
# de verdad. Prueba lo que las pruebas con simulacion NO pueden: el SQL
# real (sp_crear_pedido / sp_cancelar_pedido) y la reserva de stock sobre
# library.books.
#
#   ./scripts/pruebas.sh                      # http://localhost:5004
#   BASE=http://192.168.1.50:5004 ./scripts/pruebas.sh
#   JWT=<token> ./scripts/pruebas.sh          # con un token ya emitido
#
# Requiere en la VM: las migraciones aplicadas (roles, pedidos, pagos),
# el microservicio de login en pie (puerto 5000) para emitir el JWT,
# Redis, y psql con las credenciales de entorno (PGHOST/PGPORT/
# PGDATABASE/PGUSER/PGPASSWORD; por omision las de la practica: 777).
#
# Deja la base como la encontro: el pedido y el usuario de prueba se
# borran al final y el stock se devuelve al catalogo.
#
# Convencion: toda asercion sobre cuerpo JSON lleva ?format=json
# explicito, porque el servicio responde XML por omision
# (DEFAULT_FORMAT=xml). La seccion 4 es la que prueba esa omision.
# =====================================================================
set -uo pipefail

BASE="${BASE:-http://localhost:5004}"
# Los recursos cuelgan de la raiz. Si el despliegue usa API_PREFIX, pase
# el mismo valor aqui:  API_PREFIX=/api ./scripts/pruebas.sh
API="$BASE${API_PREFIX:-}"
# El JWT lo emite POST /login del microservicio de login.
LOGIN_BASE="${LOGIN_BASE:-http://localhost:5000}"

PGHOST="${PGHOST:-localhost}"
PGPORT="${PGPORT:-5432}"
PGDATABASE="${PGDATABASE:-library_db}"
PGUSER="${PGUSER:-library_user}"
export PGPASSWORD="${PGPASSWORD:-777}"

EMAIL_PRUEBA="prueba.pedidos@ejemplo.local"
CLAVE_PRUEBA="Secreto123"
UNIDADES=2
# Se rellena en cuanto el pedido de prueba existe; la limpieza lo mira
# para poder borrarlo aunque el dueno sea el de un JWT externo.
PEDIDO_ID=0

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
# Insensible a espacios: el JSON sale compacto con DEBUG=false y con
# espacios en desarrollo; se normalizan ambos lados.
contiene() {
    local desc="$1" texto="$2"; shift 2
    local plano cuerpo
    plano=$(printf '%s' "$texto" | tr -d '[:space:]')
    # Primero se lee la respuesta entera y luego se busca: con pipefail,
    # "curl | grep -q" falla al azar (grep sale al primer acierto y curl
    # muere por SIGPIPE), y un no_contiene daria un OK falso.
    cuerpo=$(curl -s "$@" | tr -d '[:space:]')
    if grep -qF -- "$plano" <<<"$cuerpo"; then pasa "$desc"
    else falla "$desc (no aparece: $texto)"; fi
}

# no_contiene <descripcion> <texto literal> <curl args...>
# Lo contrario: la prueba pasa cuando el texto NO esta en el cuerpo. Es
# lo que hace falta para comprobar que el rastreo publico no filtra nada.
no_contiene() {
    local desc="$1" texto="$2"; shift 2
    local plano cuerpo
    plano=$(printf '%s' "$texto" | tr -d '[:space:]')
    cuerpo=$(curl -s "$@" | tr -d '[:space:]')
    if grep -qiF -- "$plano" <<<"$cuerpo"; then
        falla "$desc (aparece: $texto)"
    else pasa "$desc"; fi
}

psql_cmd() {
    psql -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" -d "$PGDATABASE" -tAc "$1"
}

# igual <descripcion> <esperado> <obtenido>
igual() {
    if [ "$2" = "$3" ]; then pasa "$1"
    else falla "$1 (esperado $2, obtenido $3)"; fi
}

# valor_num / valor_txt <json> <clave>: primer valor de esa clave.
# Se parte por comas y llaves para que el primer "id" sea el del pedido
# y no el de una linea; con el JSON compacto una sola linea haria que la
# expresion glotona se quedara con el ultimo.
valor_num() {
    printf '%s' "$1" | tr ',{}[]' '\n\n\n\n\n' \
        | sed -n "s/.*\"$2\": *\([0-9][0-9.]*\).*/\1/p" | head -1
}
valor_txt() {
    printf '%s' "$1" | tr ',{}[]' '\n\n\n\n\n' \
        | sed -n "s/.*\"$2\": *\"\([^\"]*\)\".*/\1/p" | head -1
}

# Borra el rastro de la prueba devolviendo al catalogo lo que siguiera
# reservado. Alcanza al pedido de esta corrida ($PEDIDO_ID) y a todo lo
# que haya quedado del usuario de prueba, por si una corrida anterior se
# interrumpio. Se llama al principio y al final.
limpiar_rastro() {
    psql_cmd "
        UPDATE library.books b SET stock = b.stock + l.quantity
          FROM library.order_lines l
          JOIN library.orders o ON o.id = l.order_id
          JOIN library.users  u ON u.id = o.user_id
         WHERE b.id = l.book_id
           AND o.status <> 'cancelado'
           AND (o.id = $PEDIDO_ID OR lower(u.email) = lower('$EMAIL_PRUEBA'));
        DELETE FROM library.payments p USING library.orders o
         WHERE p.order_id = o.id
           AND (o.id = $PEDIDO_ID OR o.user_id IN
                (SELECT id FROM library.users
                  WHERE lower(email) = lower('$EMAIL_PRUEBA')));
        DELETE FROM library.orders o
         WHERE o.id = $PEDIDO_ID OR o.user_id IN
               (SELECT id FROM library.users
                 WHERE lower(email) = lower('$EMAIL_PRUEBA'));
        DELETE FROM library.users WHERE lower(email) = lower('$EMAIL_PRUEBA');
    " >/dev/null 2>&1
}

echo "Microservicio: $BASE"
echo

# Gunicorn tarda unos segundos en levantar los workers tras un reinicio;
# sin esta espera, la primera peticion puede dar 000 y ensuciar el reporte.
sleep 3

echo "0. Preparacion"
psql_cmd "SELECT 1;" >/dev/null 2>&1 \
    || { echo "  psql no disponible (revise PGHOST/PGUSER/PGPASSWORD)"; exit 1; }
limpiar_rastro

# Token real. Si no lo pasaron por entorno, se da de alta un usuario de
# prueba en el microservicio de login, se activa por operador (equivale
# al clic del correo de verificacion) y se inicia sesion.
TOKEN="${JWT:-}"
if [ -z "$TOKEN" ]; then
    curl -s -o /dev/null -X POST "$LOGIN_BASE/register?format=json" \
        -H 'Content-Type: application/json' \
        -d "{\"nombre\": \"Prueba\", \"apellidoPaterno\": \"Pedidos\",
             \"email\": \"$EMAIL_PRUEBA\", \"password\": \"$CLAVE_PRUEBA\"}"
    psql_cmd "UPDATE library.users SET email_verified = TRUE
               WHERE lower(email) = lower('$EMAIL_PRUEBA');" >/dev/null
    psql_cmd "INSERT INTO library.verified_emails (email, user_id, source)
              SELECT lower(email), id, 'token' FROM library.users
               WHERE lower(email) = lower('$EMAIL_PRUEBA')
              ON CONFLICT (email) DO UPDATE SET verified_at = now();" >/dev/null
    sesion=$(curl -s -X POST "$LOGIN_BASE/login?format=json" \
        -H 'Content-Type: application/json' \
        -d "{\"email\": \"$EMAIL_PRUEBA\", \"password\": \"$CLAVE_PRUEBA\"}")
    TOKEN=$(valor_txt "$sesion" "token")
fi
if [ -z "$TOKEN" ]; then
    echo "  No se pudo obtener un JWT (login en $LOGIN_BASE)."
    echo "  Pase uno ya emitido:  JWT=<token> ./scripts/pruebas.sh"
    limpiar_rastro
    exit 1
fi
echo "  token obtenido"

# Libro de la prueba: con existencias suficientes para reservar, pero no
# tantas como para que pedir "una mas de las que hay" supere el maximo de
# 100 unidades por linea. Solo caracteres ASCII en el titulo, para que la
# asercion del 409 no dependa de como se escapen los acentos en JSON.
LIBRO=$(psql_cmd "SELECT id FROM library.books
                   WHERE stock BETWEEN $UNIDADES AND 90
                     AND title ~ '^[ -~]+\$' ORDER BY id LIMIT 1")
if [ -z "$LIBRO" ]; then
    echo "  No hay ningun libro con existencias para la prueba."
    limpiar_rastro
    exit 1
fi
TITULO=$(psql_cmd "SELECT title FROM library.books WHERE id = $LIBRO")
STOCK_INICIAL=$(psql_cmd "SELECT stock FROM library.books WHERE id = $LIBRO")
echo "  libro de prueba: $LIBRO \"$TITULO\" (stock $STOCK_INICIAL)"

echo
echo "1. Servicio"
esperado_http "estado del servicio, PostgreSQL y Redis" 200 "$BASE/health"

echo
echo "2. Lo que exige token"
esperado_http "el pedido completo por numero es 401 sin token" 401 \
    "$API/pedidos/numero/PED-000001?format=json"

echo
echo "3. Alta: la reserva de stock la hace sp_crear_pedido"
respuesta=$(curl -s -X POST "$API/pedidos?format=json" \
    -H 'Content-Type: application/json' -H "Authorization: Bearer $TOKEN" \
    -d "{\"lines\": [{\"bookId\": $LIBRO, \"quantity\": $UNIDADES}]}")
PEDIDO_ID=$(valor_num "$respuesta" "id")
PEDIDO_NUM=$(valor_txt "$respuesta" "orderNumber")
[ -n "$PEDIDO_ID" ] || PEDIDO_ID=0          # la limpieza necesita un numero
if [ "$PEDIDO_ID" != "0" ] && [ -n "$PEDIDO_NUM" ]; then
    pasa "alta del pedido ($PEDIDO_NUM, id $PEDIDO_ID)"
else
    falla "alta del pedido: $respuesta"
    limpiar_rastro
    echo; echo "Resultado: $ok OK, $fallos fallos"
    exit 1
fi
igual "library.books.stock bajo las $UNIDADES unidades pedidas" \
    "$((STOCK_INICIAL - UNIDADES))" \
    "$(psql_cmd "SELECT stock FROM library.books WHERE id = $LIBRO")"

# El stock que queda ya es menor; pedir una unidad mas de las que habia
# al principio no se puede surtir de ninguna manera.
esperado_http "pedir mas unidades de las que hay es 409" 409 \
    -X POST "$API/pedidos?format=json" -H 'Content-Type: application/json' \
    -H "Authorization: Bearer $TOKEN" \
    -d "{\"lines\": [{\"bookId\": $LIBRO, \"quantity\": $((STOCK_INICIAL + 1))}]}"
contiene "el 409 dice de que libro se trata" "$TITULO" \
    -X POST "$API/pedidos?format=json" -H 'Content-Type: application/json' \
    -H "Authorization: Bearer $TOKEN" \
    -d "{\"lines\": [{\"bookId\": $LIBRO, \"quantity\": $((STOCK_INICIAL + 1))}]}"

echo
echo "4. RASTREO PUBLICO (lo unico sin token)"
esperado_http "el rastreo responde sin token" 200 "$API/envios/$PEDIDO_NUM"
contiene "XML por omision" '<shipment' "$API/envios/$PEDIDO_NUM"
contiene "JSON con ?format=json" '"orderNumber"' "$API/envios/$PEDIDO_NUM?format=json"
no_contiene "el rastreo no filtra el correo del dueno" "$EMAIL_PRUEBA" \
    "$API/envios/$PEDIDO_NUM?format=json"
no_contiene "el rastreo no filtra importes" "total" \
    "$API/envios/$PEDIDO_NUM?format=json"

echo
echo "5. Cancelacion: sp_cancelar_pedido devuelve el stock"
esperado_http "cancelar el pedido" 200 -X DELETE "$API/pedidos/$PEDIDO_ID?format=json" \
    -H "Authorization: Bearer $TOKEN"
igual "library.books.stock volvio a su valor original" "$STOCK_INICIAL" \
    "$(psql_cmd "SELECT stock FROM library.books WHERE id = $LIBRO")"

echo
echo "6. Limpieza: se borran el pedido y el usuario de prueba"
limpiar_rastro
if [ -z "$(psql_cmd "SELECT 1 FROM library.orders WHERE id = $PEDIDO_ID;")" ]; then
    pasa "el pedido de prueba ya no existe"
else
    falla "el pedido de prueba ya no existe"
fi

echo
echo "---------------------------------------------"
printf 'Pruebas superadas: %d   fallidas: %d\n' "$ok" "$fallos"
[ "$fallos" -eq 0 ] || exit 1
