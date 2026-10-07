#!/usr/bin/env bash
# =====================================================================
# apps/services/pagos/scripts/pruebas.sh
# Bateria de humo del microservicio de PAGOS contra PostgreSQL y Redis
# de verdad. Prueba lo que las pruebas con simulacion NO pueden: el SQL
# real (sp_registrar_pago, el indice unico de idempotencia) y el
# DISPARADOR que pasa el pedido a 'pagado' cuando lo aplicado alcanza el
# total.
#
#   ./scripts/pruebas.sh                      # http://localhost:5005
#   BASE=http://192.168.1.50:5005 ./scripts/pruebas.sh
#   JWT=<token> ./scripts/pruebas.sh          # con un token ya emitido
#
# El pedido que se paga es del usuario de prueba, de modo que un JWT
# pasado por entorno solo sirve si lleva payments:write (admin o staff);
# sin JWT, el script emite el del propio usuario de prueba, que es el
# dueno y no necesita ningun permiso especial.
#
# Requiere en la VM: las migraciones aplicadas (roles, pedidos, pagos),
# el microservicio de login en pie (puerto 5000) para emitir el JWT,
# Redis, y psql con las credenciales de entorno (PGHOST/PGPORT/
# PGDATABASE/PGUSER/PGPASSWORD; por omision las de la practica: 777).
#
# Deja la base como la encontro: los pagos, el pedido y el usuario de
# prueba se borran al final y el stock se devuelve al catalogo.
#
# Convencion: toda asercion sobre cuerpo JSON lleva ?format=json
# explicito, porque el servicio responde XML por omision
# (DEFAULT_FORMAT=xml).
# =====================================================================
set -uo pipefail

BASE="${BASE:-http://localhost:5005}"
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

EMAIL_PRUEBA="prueba.pagos@ejemplo.local"
CLAVE_PRUEBA="Secreto123"
UNIDADES=2
CLAVE_IDEM="pruebas-pagos-$$"
# Se rellena en cuanto el pedido de prueba existe; la limpieza lo mira
# para borrarlo pase lo que pase.
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

psql_cmd() {
    psql -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" -d "$PGDATABASE" -tAc "$1"
}

# igual <descripcion> <esperado> <obtenido>
igual() {
    if [ "$2" = "$3" ]; then pasa "$1"
    else falla "$1 (esperado $2, obtenido $3)"; fi
}

# valor_num / valor_txt <json> <clave>: primer valor de esa clave.
# Se parte por comas y llaves para que el primer "id" sea el del pago y
# no el del metodo o el del pedido; con el JSON compacto en una sola
# linea la expresion glotona se quedaria con el ultimo.
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
# interrumpio. Los pagos van primero: payments referencia orders con
# ON DELETE RESTRICT.
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

# El usuario de prueba se da de alta siempre: es el DUENO del pedido que
# se va a pagar. Se activa por operador (equivale al clic del correo de
# verificacion). El token sale de su propio login, salvo que ya lo hayan
# pasado por entorno.
TOKEN="${JWT:-}"
curl -s -o /dev/null -X POST "$LOGIN_BASE/register?format=json" \
    -H 'Content-Type: application/json' \
    -d "{\"nombre\": \"Prueba\", \"apellidoPaterno\": \"Pagos\",
         \"email\": \"$EMAIL_PRUEBA\", \"password\": \"$CLAVE_PRUEBA\"}"
psql_cmd "UPDATE library.users SET email_verified = TRUE
           WHERE lower(email) = lower('$EMAIL_PRUEBA');" >/dev/null
psql_cmd "INSERT INTO library.verified_emails (email, user_id, source)
          SELECT lower(email), id, 'token' FROM library.users
           WHERE lower(email) = lower('$EMAIL_PRUEBA')
          ON CONFLICT (email) DO UPDATE SET verified_at = now();" >/dev/null
if [ -z "$TOKEN" ]; then
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

# El pedido que se va a pagar se crea con el procedimiento almacenado:
# asi esta prueba no depende de que el microservicio de pedidos este en
# pie. Dos unidades del mismo libro, de modo que el total sea
# exactamente dos veces el precio congelado de la linea y se pueda
# cubrir con dos pagos iguales.
USUARIO_ID=$(psql_cmd "SELECT id FROM library.users
                        WHERE lower(email) = lower('$EMAIL_PRUEBA')")
LIBRO=$(psql_cmd "SELECT id FROM library.books
                   WHERE stock >= $UNIDADES ORDER BY id LIMIT 1")
if [ -z "$USUARIO_ID" ] || [ -z "$LIBRO" ]; then
    echo "  No hay usuario de prueba o ningun libro con existencias."
    limpiar_rastro
    exit 1
fi
PEDIDO_ID=$(psql_cmd "SELECT library.sp_crear_pedido($USUARIO_ID,
    '[{\"bookId\": $LIBRO, \"quantity\": $UNIDADES}]'::jsonb)")
[ -n "$PEDIDO_ID" ] || PEDIDO_ID=0          # la limpieza necesita un numero
if [ "$PEDIDO_ID" = "0" ]; then
    echo "  sp_crear_pedido no devolvio ningun pedido."
    limpiar_rastro
    exit 1
fi
MITAD=$(psql_cmd "SELECT unit_price FROM library.order_lines
                   WHERE order_id = $PEDIDO_ID")
TOTAL=$(psql_cmd "SELECT total FROM library.orders WHERE id = $PEDIDO_ID")
echo "  pedido de prueba: id $PEDIDO_ID (total $TOTAL, dos pagos de $MITAD)"

echo
echo "1. Servicio"
esperado_http "estado del servicio, PostgreSQL y Redis" 200 "$BASE/health"

echo
echo "2. Aqui no hay ninguna lectura publica"
esperado_http "el catalogo de metodos es 401 sin token" 401 "$API/metodos?format=json"
contiene "con token si se ven los metodos" '"efectivo"' \
    -H "Authorization: Bearer $TOKEN" "$API/metodos?format=json"

echo
echo "3. Datos de tarjeta: ni se guardan ni se aceptan"
esperado_http "mandar cardNumber es 400" 400 -X POST "$API/pagos?format=json" \
    -H 'Content-Type: application/json' -H "Authorization: Bearer $TOKEN" \
    -d "{\"orderId\": $PEDIDO_ID, \"amount\": $MITAD, \"method\": \"efectivo\",
         \"cardNumber\": \"4111111111111111\", \"cvv\": \"123\"}"

echo
echo "4. Pago en efectivo: nace ya aplicado"
primero=$(curl -s -X POST "$API/pagos?format=json" \
    -H 'Content-Type: application/json' -H "Authorization: Bearer $TOKEN" \
    -d "{\"orderId\": $PEDIDO_ID, \"amount\": $MITAD, \"method\": \"efectivo\",
         \"idempotencyKey\": \"$CLAVE_IDEM\"}")
REFERENCIA=$(valor_txt "$primero" "reference")
if [ -n "$REFERENCIA" ]; then pasa "alta del pago ($REFERENCIA)"
else
    falla "alta del pago: $primero"
    limpiar_rastro
    echo; echo "Resultado: $ok OK, $fallos fallos"
    exit 1
fi
igual "el metodo efectivo no requiere autorizacion: nace 'aplicado'" \
    "aplicado" "$(valor_txt "$primero" "status")"

echo
echo "5. idempotencyKey: el reintento no cobra dos veces"
repetido=$(curl -s -X POST "$API/pagos?format=json" \
    -H 'Content-Type: application/json' -H "Authorization: Bearer $TOKEN" \
    -d "{\"orderId\": $PEDIDO_ID, \"amount\": $MITAD, \"method\": \"efectivo\",
         \"idempotencyKey\": \"$CLAVE_IDEM\"}")
igual "el segundo POST devuelve el MISMO pago" \
    "$REFERENCIA" "$(valor_txt "$repetido" "reference")"
igual "en la base hay una sola fila con esa clave" "1" \
    "$(psql_cmd "SELECT count(*) FROM library.payments
                  WHERE idempotency_key = '$CLAVE_IDEM'")"

echo
echo "6. Al cubrir el total, el disparador pasa el pedido a 'pagado'"
esperado_http "segundo pago, el que completa el total" 201 \
    -X POST "$API/pagos?format=json" -H 'Content-Type: application/json' \
    -H "Authorization: Bearer $TOKEN" \
    -d "{\"orderId\": $PEDIDO_ID, \"amount\": $MITAD, \"method\": \"efectivo\"}"
igual "library.orders quedo en 'pagado' sin que lo tocara la aplicacion" \
    "pagado" "$(psql_cmd "SELECT status FROM library.orders WHERE id = $PEDIDO_ID")"

echo
echo "7. No se puede cobrar de mas"
esperado_http "un importe que excede el saldo es 409" 409 \
    -X POST "$API/pagos?format=json" -H 'Content-Type: application/json' \
    -H "Authorization: Bearer $TOKEN" \
    -d "{\"orderId\": $PEDIDO_ID, \"amount\": 1.00, \"method\": \"efectivo\"}"

echo
echo "8. Limpieza: se borran los pagos, el pedido y el usuario de prueba"
limpiar_rastro
if [ "$(psql_cmd "SELECT count(*) FROM library.payments
                   WHERE order_id = $PEDIDO_ID")" = "0" ]; then
    pasa "no quedan pagos de prueba en la base"
else
    falla "no quedan pagos de prueba en la base"
fi

echo
echo "---------------------------------------------"
printf 'Pruebas superadas: %d   fallidas: %d\n' "$ok" "$fallos"
[ "$fallos" -eq 0 ] || exit 1
