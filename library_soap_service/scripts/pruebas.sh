#!/usr/bin/env bash
# =====================================================================
# library_soap_service/scripts/pruebas.sh
# Bateria de humo del microservicio: recorre las operaciones CRUD, la
# busqueda por atributos, los dos formatos de intercambio, CORS y los
# codigos de error.
#
#   ./scripts/pruebas.sh                      # http://localhost:5001
#   BASE=http://192.168.1.50:5001 ./scripts/pruebas.sh
#
# Deja la base como la encontro: el libro que da de alta lo borra al final.
#
# Convencion: toda asercion sobre cuerpo JSON lleva ?output=json explicito
# (el servicio responde XML por omision con DEFAULT_FORMAT=xml). Solo la
# seccion 3 prueba el XML y la negociacion; el resto no depende del default.
# =====================================================================
set -uo pipefail

BASE="${BASE:-http://localhost:5001}"
# Los recursos cuelgan de la raiz. Si el despliegue usa API_PREFIX, pase el
# mismo valor aqui:  API_PREFIX=/api ./scripts/pruebas.sh
API="$BASE${API_PREFIX:-}"
ISBN_PRUEBA="978-9999999999"
# JWT Bearer para las escrituras (lo emite POST /login del microservicio
# login). Sin el solo se prueban los 401; con el, el ciclo completo:
#   JWT=<token> ./scripts/pruebas.sh
AUTH=()
[ -n "${JWT:-}" ] && AUTH=(-H "Authorization: Bearer $JWT")

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
# -F: el texto se compara tal cual, sin interpretarlo como expresion regular
# (patrones como '"concepts": []' llevan corchetes).
# Insensible a espacios: el JSON sale compacto ("price":175.0) con
# DEBUG=false y con espacios en desarrollo; se normalizan ambos lados.
contiene() {
    local desc="$1" texto="$2"; shift 2
    local plano cuerpo
    plano=$(printf '%s' "$texto" | tr -d '[:space:]')
    # Primero se lee la respuesta entera y luego se busca: con pipefail,
    # "curl | grep -q" puede fallar al azar: grep sale al primer acierto y
    # curl recibe SIGPIPE al seguir escribiendo.
    cuerpo=$(curl -s "$@" | tr -d '[:space:]')
    if grep -qF -- "$plano" <<<"$cuerpo"; then pasa "$desc"
    else falla "$desc (no aparece: $texto)"; fi
}

# cabecera <descripcion> <nombre de cabecera> <curl args...>
# Busca la cabecera en la respuesta SIN distinguir mayusculas: los nombres
# de cabecera HTTP no las distinguen y un servidor o proxy puede mandarlos
# en minusculas (access-control-allow-origin).
cabecera() {
    local desc="$1" nombre="$2"; shift 2
    local cabeceras
    cabeceras=$(curl -s -D - -o /dev/null "$@")
    if grep -qiF -- "$nombre:" <<<"$cabeceras"; then pasa "$desc"
    else falla "$desc (no aparece la cabecera $nombre)"; fi
}

# alta <curl args...>
# Hace un POST de alta. Deja el cuerpo en ALTA_CUERPO y el id del libro
# creado en ALTA_ID, leido de la cabecera Location (/books/<id>). No se
# saca del cuerpo: la respuesta trae otros "id" anidados (autores,
# imagenes, conceptos) y un patron sobre el JSON puede tomar el que no es.
alta() {
    local cabeceras
    cabeceras=$(mktemp)
    ALTA_CUERPO=$(curl -s -D "$cabeceras" "$@")
    ALTA_ID=$(grep -i '^location:' "$cabeceras" | tr -d '\r' \
        | sed -n 's|.*/books/\([0-9][0-9]*\).*|\1|p' | head -1)
    rm -f "$cabeceras"
}

echo "Microservicio: $BASE"
echo

echo "1. Servicio y documentacion"
esperado_http "indice"                 200 "$BASE/"
esperado_http "estado de la base"      200 "$BASE/health"
esperado_http "especificacion OpenAPI" 200 "$BASE/openapi.json"
esperado_http "Swagger UI"             200 -L "$BASE/docs"
contiene "el indice anuncia /docs" '"swaggerUi"' "$BASE/?output=json"

echo
echo "2. Lectura"
esperado_http "todos los libros"        200 "$API/books"
contiene "la coleccion trae libros"     '"books"'   "$API/books?limit=2&output=json"
cabecera "la cabecera X-Total-Count"    'X-Total-Count' "$API/books?limit=1"
esperado_http "un libro por id"         200 "$API/books/1"
esperado_http "un libro por ISBN"       200 "$API/books/isbn/978-0133970777"
esperado_http "libro inexistente"       404 "$API/books/999999"

echo
echo "3. Los dos formatos de intercambio"
contiene "XML por ?output=xml"          '<library xmlns="urn:library:catalog:1.0"' "$API/books?limit=1&output=xml"
contiene "XML por Accept"               '<book '        -H 'Accept: application/xml' "$API/books/1"
contiene "JSON con ?output=json"          '"book"'        "$API/books/1?output=json"
contiene "el XML respeta el diseno"     '<publicationYear>' "$API/books/1?output=xml"
contiene "precio con moneda"            '<price currency=' "$API/books/1?output=xml"

echo
echo "4. Busqueda por atributos"
contiene "por titulo"      '"title"' "$API/books/search?title=algoritmos&output=json"
contiene "por autor"       'Asimov'  "$API/books/search?author=asimov&output=json"
contiene "por genero"      '"books"' "$API/books/search?genre=novela&output=json"
contiene "por concepto"    '"books"' "$API/books/search?concept=SOLID&output=json"
contiene "por categoria"   '"books"' "$API/books/search?category=Academico&output=json"
contiene "por formato"     '"books"' "$API/books/search?format=Digital&output=json"
contiene "por rango de precio" '"books"' "$API/books/search?price_min=300&price_max=1000&output=json"
contiene "por rango de anos"   '"books"' "$API/books/search?year_min=2000&year_max=2020&output=json"
contiene "solo con existencias" '"books"' "$API/books/search?in_stock=true&output=json"
contiene "texto libre"     '"books"' "$API/books/search?q=clean&output=json"
esperado_http "orden invalido"  400 "$API/books?sort=inexistente"

echo
echo "5. Catalogos"
for catalogo in formats categories genres authors concepts; do
    esperado_http "catalogo $catalogo" 200 "$API/$catalogo"
done

echo
echo "5b. Autorizacion JWT (escrituras protegidas)"
esperado_http "POST sin token es 401" 401 -X POST "$API/books" \
    -H 'Content-Type: application/json' -d '{"title":"X"}'
esperado_http "Bearer malformado es 401" 401 -X POST "$API/books" \
    -H 'Content-Type: application/json' -H 'Authorization: Token abc' -d '{"title":"X"}'
# Token invalido (firma, formato, caducado, revocado) -> 401. El 403 queda
# para un token VALIDO cuyo rol no alcanza para la operacion.
esperado_http "token falso es 401" 401 -X POST "$API/books" \
    -H 'Content-Type: application/json' -H 'Authorization: Bearer falso123' -d '{"title":"X"}'
contiene "el 401 tambien sale en XML" '<error xmlns=' -X POST "$API/books?output=xml" \
    -H 'Content-Type: application/json' -d '{"title":"X"}'

echo
echo "6. Escritura"
if [ -z "${JWT:-}" ]; then
    echo "  (sin JWT: se omite el ciclo de alta/modificacion/baja; pase JWT=<token> para probarlo)"
else
# Limpieza previa por si una corrida anterior se interrumpio.
# El primer "id" del cuerpo es el del libro (los anidados van despues).
id_previo=$(curl -s "$API/books/isbn/$ISBN_PRUEBA?output=json" | grep -o '"id": *[0-9]*' \
    | head -1 | tr -dc '0-9')
[ -n "$id_previo" ] && curl -s -o /dev/null -X DELETE "$API/books/$id_previo" ${AUTH[@]+"${AUTH[@]}"}

alta -X POST "$API/books?output=json" -H 'Content-Type: application/json' ${AUTH[@]+"${AUTH[@]}"} -d "{
  \"isbn\": \"$ISBN_PRUEBA\",
  \"title\": \"Libro de prueba automatizada\",
  \"publicationYear\": 2026,
  \"price\": 100.00,
  \"stock\": 2,
  \"format\": \"Digital\",
  \"category\": \"Tecnico\",
  \"authors\": [\"Autor De Prueba\"],
  \"genres\": [\"Genero De Prueba\"],
  \"concepts\": [{\"name\": \"Concepto De Prueba\", \"definition\": \"Definicion de prueba.\"}],
  \"images\": [{\"url\": \"https://example.org/portada.jpg\", \"isCover\": true}]
}"
NUEVO_ID="$ALTA_ID"

if [ -n "$NUEVO_ID" ]; then pasa "alta de un libro (id $NUEVO_ID)"
else falla "alta de un libro: $ALTA_CUERPO"; fi

if [ -n "$NUEVO_ID" ]; then
    contiene "actualizar (PATCH cambia el precio)" '"price": 175' \
        -X PATCH "$API/books/$NUEVO_ID?output=json" -H 'Content-Type: application/json' ${AUTH[@]+"${AUTH[@]}"} -d '{"price": 175.00}'
    contiene "modificar (PUT reemplaza el titulo)" 'Libro de prueba reemplazado' \
        -X PUT "$API/books/$NUEVO_ID?output=json" -H 'Content-Type: application/json' ${AUTH[@]+"${AUTH[@]}"} \
        -d "{\"isbn\":\"$ISBN_PRUEBA\",\"title\":\"Libro de prueba reemplazado\",\"publicationYear\":2026,\"price\":200.00,\"stock\":1,\"format\":\"Fisico\",\"category\":\"Tecnico\",\"authors\":[\"Autor De Prueba\"]}"
    contiene "PUT vacia las colecciones ausentes" '"concepts": []' "$API/books/$NUEVO_ID?output=json"
    esperado_http "ISBN duplicado" 409 -X POST "$API/books?output=json" -H 'Content-Type: application/json' ${AUTH[@]+"${AUTH[@]}"} \
        -d "{\"isbn\":\"$ISBN_PRUEBA\",\"title\":\"Copia\",\"publicationYear\":2026,\"price\":1,\"format\":\"Digital\",\"category\":\"Tecnico\"}"
    esperado_http "baja del libro" 200 -X DELETE "$API/books/$NUEVO_ID" ${AUTH[@]+"${AUTH[@]}"}
    esperado_http "el libro ya no existe" 404 "$API/books/$NUEVO_ID"
fi

echo
echo "7. Alta con el cuerpo en XML (respuesta pedida en JSON)"
alta -X POST "$API/books?output=json" -H 'Content-Type: application/xml' ${AUTH[@]+"${AUTH[@]}"} --data-binary "<?xml version=\"1.0\" encoding=\"UTF-8\"?>
<book xmlns=\"urn:library:catalog:1.0\" isbn=\"$ISBN_PRUEBA\">
  <title>Libro de prueba en XML</title>
  <publicationYear>2026</publicationYear>
  <price currency=\"MXN\">150.00</price>
  <stock>1</stock>
  <format>Digital</format>
  <category>Tecnico</category>
  <authors count=\"1\"><author>Autor De Prueba</author></authors>
</book>"
xml_id="$ALTA_ID"
if [ -n "$xml_id" ]; then
    pasa "alta con cuerpo XML (id $xml_id)"
    esperado_http "baja del libro creado en XML" 200 -X DELETE "$API/books/$xml_id" ${AUTH[@]+"${AUTH[@]}"}
else
    falla "alta con cuerpo XML: $ALTA_CUERPO"
fi
fi # fin del ciclo de escritura (requiere JWT)

echo
echo "8. Errores"
if [ -n "${JWT:-}" ]; then
esperado_http "faltan campos obligatorios" 400 -X POST "$API/books" ${AUTH[@]+"${AUTH[@]}"} \
    -H 'Content-Type: application/json' -d '{"title":"Sin ISBN"}'
esperado_http "formato fuera del catalogo" 400 -X POST "$API/books" ${AUTH[@]+"${AUTH[@]}"} \
    -H 'Content-Type: application/json' \
    -d '{"isbn":"978-1111111111","title":"X","publicationYear":2020,"price":1,"format":"Papiro","category":"Tecnico"}'
esperado_http "Content-Type no soportado"  415 -X POST "$API/books" ${AUTH[@]+"${AUTH[@]}"} \
    -H 'Content-Type: text/plain' -d 'hola'
else
    echo "  (sin JWT: validaciones de escritura omitidas; pase JWT=<token>)"
fi
contiene "el error tambien sale en XML" '<error xmlns=' "$API/books/999999?output=xml"

echo
echo "9. CORS (cliente de otro dominio)"
cabecera "cabecera en peticion simple" 'Access-Control-Allow-Origin' \
    -H 'Origin: https://cliente.otrodominio.com' "$API/books?limit=1"
cabecera "preflight de PUT" 'Access-Control-Allow-Methods' \
    -X OPTIONS -H 'Origin: https://cliente.otrodominio.com' \
    -H 'Access-Control-Request-Method: PUT' -H 'Access-Control-Request-Headers: Content-Type' \
    "$API/books/1"

echo
echo "---------------------------------------------"
printf 'Pruebas superadas: %d   fallidas: %d\n' "$ok" "$fallos"
[ "$fallos" -eq 0 ] || exit 1
