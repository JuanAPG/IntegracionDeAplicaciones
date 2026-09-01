#!/usr/bin/env bash
# =====================================================================
# soap/scripts/pruebas.sh
# Bateria de humo del microservicio: recorre las operaciones CRUD, la
# busqueda por atributos, los dos formatos de intercambio, CORS y los
# codigos de error.
#
#   ./scripts/pruebas.sh                      # http://localhost:5001
#   BASE=http://192.168.1.50:5001 ./scripts/pruebas.sh
#
# Deja la base como la encontro: el libro que da de alta lo borra al final.
# =====================================================================
set -uo pipefail

BASE="${BASE:-http://localhost:5001}"
API="$BASE/api"
ISBN_PRUEBA="978-9999999999"

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
contiene() {
    local desc="$1" texto="$2"; shift 2
    if curl -s "$@" | grep -qF -- "$texto"; then pasa "$desc"
    else falla "$desc (no aparece: $texto)"; fi
}

echo "Microservicio: $BASE"
echo

echo "1. Servicio y documentacion"
esperado_http "indice"                 200 "$BASE/"
esperado_http "estado de la base"      200 "$BASE/health"
esperado_http "especificacion OpenAPI" 200 "$BASE/openapi.json"
esperado_http "Swagger UI"             200 -L "$BASE/docs"
contiene "el indice anuncia /docs" '"swaggerUi"' "$BASE/"

echo
echo "2. Lectura"
esperado_http "todos los libros"        200 "$API/books"
contiene "la coleccion trae libros"     '"books"'   "$API/books?limit=2"
contiene "la cabecera X-Total-Count"    'X-Total-Count' -D - -o /dev/null "$API/books?limit=1"
esperado_http "un libro por id"         200 "$API/books/1"
esperado_http "un libro por ISBN"       200 "$API/books/isbn/978-0133970777"
esperado_http "libro inexistente"       404 "$API/books/999999"

echo
echo "3. Los dos formatos de intercambio"
contiene "XML por ?output=xml"          '<library xmlns="urn:library:catalog:1.0"' "$API/books?limit=1&output=xml"
contiene "XML por Accept"               '<book '        -H 'Accept: application/xml' "$API/books/1"
contiene "JSON por omision"             '"book"'        "$API/books/1"
contiene "el XML respeta el diseno"     '<publicationYear>' "$API/books/1?output=xml"
contiene "precio con moneda"            '<price currency=' "$API/books/1?output=xml"

echo
echo "4. Busqueda por atributos"
contiene "por titulo"      '"title"' "$API/books/search?title=algoritmos"
contiene "por autor"       'Asimov'  "$API/books/search?author=asimov"
contiene "por genero"      '"books"' "$API/books/search?genre=novela"
contiene "por concepto"    '"books"' "$API/books/search?concept=SOLID"
contiene "por categoria"   '"books"' "$API/books/search?category=Academico"
contiene "por formato"     '"books"' "$API/books/search?format=Digital"
contiene "por rango de precio" '"books"' "$API/books/search?price_min=300&price_max=1000"
contiene "por rango de anos"   '"books"' "$API/books/search?year_min=2000&year_max=2020"
contiene "solo con existencias" '"books"' "$API/books/search?in_stock=true"
contiene "texto libre"     '"books"' "$API/books/search?q=clean"
esperado_http "orden invalido"  400 "$API/books?sort=inexistente"

echo
echo "5. Catalogos"
for catalogo in formats categories genres authors concepts; do
    esperado_http "catalogo $catalogo" 200 "$API/$catalogo"
done

echo
echo "6. Escritura"
# Limpieza previa por si una corrida anterior se interrumpio.
id_previo=$(curl -s "$API/books/isbn/$ISBN_PRUEBA" | sed -n 's/.*"id": *\([0-9]*\).*/\1/p' | head -1)
[ -n "$id_previo" ] && curl -s -o /dev/null -X DELETE "$API/books/$id_previo"

respuesta=$(curl -s -X POST "$API/books" -H 'Content-Type: application/json' -d "{
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
}")
NUEVO_ID=$(printf '%s' "$respuesta" | sed -n 's/.*"id": *\([0-9]*\).*/\1/p' | head -1)

if [ -n "$NUEVO_ID" ]; then pasa "alta de un libro (id $NUEVO_ID)"
else falla "alta de un libro: $respuesta"; fi

if [ -n "$NUEVO_ID" ]; then
    contiene "actualizar (PATCH cambia el precio)" '"price": 175' \
        -X PATCH "$API/books/$NUEVO_ID" -H 'Content-Type: application/json' -d '{"price": 175.00}'
    contiene "modificar (PUT reemplaza el titulo)" 'Libro de prueba reemplazado' \
        -X PUT "$API/books/$NUEVO_ID" -H 'Content-Type: application/json' \
        -d "{\"isbn\":\"$ISBN_PRUEBA\",\"title\":\"Libro de prueba reemplazado\",\"publicationYear\":2026,\"price\":200.00,\"stock\":1,\"format\":\"Fisico\",\"category\":\"Tecnico\",\"authors\":[\"Autor De Prueba\"]}"
    contiene "PUT vacia las colecciones ausentes" '"concepts": []' "$API/books/$NUEVO_ID"
    esperado_http "ISBN duplicado" 409 -X POST "$API/books" -H 'Content-Type: application/json' \
        -d "{\"isbn\":\"$ISBN_PRUEBA\",\"title\":\"Copia\",\"publicationYear\":2026,\"price\":1,\"format\":\"Digital\",\"category\":\"Tecnico\"}"
    esperado_http "baja del libro" 200 -X DELETE "$API/books/$NUEVO_ID"
    esperado_http "el libro ya no existe" 404 "$API/books/$NUEVO_ID"
fi

echo
echo "7. Alta con el cuerpo en XML"
xml_id=$(curl -s -X POST "$API/books" -H 'Content-Type: application/xml' --data-binary "<?xml version=\"1.0\" encoding=\"UTF-8\"?>
<book xmlns=\"urn:library:catalog:1.0\" isbn=\"$ISBN_PRUEBA\">
  <title>Libro de prueba en XML</title>
  <publicationYear>2026</publicationYear>
  <price currency=\"MXN\">150.00</price>
  <stock>1</stock>
  <format>Digital</format>
  <category>Tecnico</category>
  <authors count=\"1\"><author>Autor De Prueba</author></authors>
</book>" | sed -n 's/.*"id": *\([0-9]*\).*/\1/p' | head -1)
if [ -n "$xml_id" ]; then
    pasa "alta con cuerpo XML (id $xml_id)"
    esperado_http "baja del libro creado en XML" 200 -X DELETE "$API/books/$xml_id"
else
    falla "alta con cuerpo XML"
fi

echo
echo "8. Errores"
esperado_http "faltan campos obligatorios" 400 -X POST "$API/books" \
    -H 'Content-Type: application/json' -d '{"title":"Sin ISBN"}'
esperado_http "formato fuera del catalogo" 400 -X POST "$API/books" \
    -H 'Content-Type: application/json' \
    -d '{"isbn":"978-1111111111","title":"X","publicationYear":2020,"price":1,"format":"Papiro","category":"Tecnico"}'
esperado_http "Content-Type no soportado"  415 -X POST "$API/books" \
    -H 'Content-Type: text/plain' -d 'hola'
contiene "el error tambien sale en XML" '<error xmlns=' "$API/books/999999?output=xml"

echo
echo "9. CORS (cliente de otro dominio)"
contiene "cabecera en peticion simple" 'Access-Control-Allow-Origin' \
    -D - -o /dev/null -H 'Origin: https://cliente.otrodominio.com' "$API/books?limit=1"
contiene "preflight de PUT" 'Access-Control-Allow-Methods' \
    -D - -o /dev/null -X OPTIONS -H 'Origin: https://cliente.otrodominio.com' \
    -H 'Access-Control-Request-Method: PUT' -H 'Access-Control-Request-Headers: Content-Type' \
    "$API/books/1"

echo
echo "---------------------------------------------"
printf 'Pruebas superadas: %d   fallidas: %d\n' "$ok" "$fallos"
[ "$fallos" -eq 0 ] || exit 1
