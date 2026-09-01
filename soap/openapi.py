"""
soap/openapi.py
Especificacion OpenAPI 3.0.3 del microservicio, escrita a mano.

Se mantiene fuera de app.py para que las rutas conserven sus docstrings en
prosa y la documentacion pueda describir con detalle lo que no se deduce
de la firma de la funcion: los dos formatos de intercambio (JSON y XML),
los filtros de busqueda y la forma exacta del XML de
apps/services/soap/library.xml.

app.py se la entrega a Flasgger, que publica:
    /openapi.json   el documento
    /docs           la interfaz Swagger UI
"""
import config

SERVER_URL = f"http://localhost:{config.PORT}"
API = config.API_PREFIX
NS = config.XML_NAMESPACE

DESCRIPTION = f"""
Microservicio **Flask + PostgreSQL** para las operaciones CRUD sobre los libros
de `library_db` (esquema `{config.PGSCHEMA}`).

### Dos formatos de intercambio

El mismo recurso se entrega en JSON o en XML. El XML reproduce el diseno de
`apps/services/soap/library.xml`: orientado a libros, con `<book>` como raiz
agregada y las dependencias multivaluadas en envoltorios repetidos
(`<authors>`, `<genres>`, `<concepts>`, `<images>`).

Como pedir cada formato, en orden de prioridad:

1. `?output=xml` o `?output=json`
2. cabecera `Accept: application/xml` / `Accept: application/json`
3. el valor de `DEFAULT_FORMAT` en `.env` (actualmente `{config.DEFAULT_FORMAT}`)

`?format=xml` tambien funciona, pero **`format` es ademas un filtro de
busqueda** (el catalogo de formatos: Fisico, Digital, Audiolibro, Pasta dura).
Solo se interpreta como representacion cuando su valor es `xml` o `json`; con
cualquier otro valor filtra libros. Use `output` para evitar la ambiguedad.

El cuerpo de las peticiones de escritura se acepta igualmente en JSON o en
XML: una respuesta del servicio puede reenviarse tal cual como peticion.

### Modelo de datos

Un libro es el agregado completo. Las dependencias funcionales
(`ISBN -> titulo, ano, precio, stock, formato, categoria`) son campos simples;
las multivaluadas (`libro ->> autor`, `libro ->> genero`, `libro ->> imagen`,
`libro ->> (concepto, definicion)`) son colecciones. La definicion pertenece
al **par** libro-concepto: un mismo concepto tiene definiciones distintas en
libros distintos.

`formats` y `categories` son catalogos cerrados: el valor enviado debe existir
(por `ref` o por nombre) o la peticion falla con 400. `authors`, `genres` y
`concepts` son abiertos: si el nombre no existe se da de alta.

### CORS

Habilitado para los origenes de `CORS_ORIGINS` (actualmente
`{', '.join(config.CORS_ORIGINS)}`), con `OPTIONS` de preflight para
`PUT`, `PATCH` y `DELETE`. El servicio no usa cookies ni sesiones.
""".strip()


# ---------------------------------------------------------------------
# Ejemplos
# ---------------------------------------------------------------------
BOOK_JSON_EXAMPLE = {
    "id": 1,
    "isbn": "978-0133970777",
    "title": "Fundamentos de Sistemas de Bases de Datos",
    "publicationYear": 2016,
    "price": 1250.00,
    "currency": "MXN",
    "stock": 12,
    "format": {"ref": 4, "name": "Pasta dura"},
    "category": {"ref": 5, "name": "Academico"},
    "authors": [{"ref": 1, "name": "Ramez Elmasri"}, {"ref": 2, "name": "Shamkant Navathe"}],
    "genres": [{"ref": 1, "name": "Bases de datos"}],
    "concepts": [{"ref": 1, "name": "Normalizacion",
                  "definition": "Proceso de descomposicion de relaciones para eliminar "
                                "redundancia y anomalias de actualizacion."}],
    "images": [{"id": 1, "url": "https://covers.openlibrary.org/b/isbn/9780133970777-L.jpg",
                "isCover": True}],
    "createdAt": "2026-08-28T12:00:00+00:00",
    "updatedAt": "2026-08-28T12:00:00+00:00",
}

BOOK_INPUT_EXAMPLE = {
    "isbn": "978-1491950357",
    "title": "Building Microservices",
    "publicationYear": 2015,
    "price": 899.90,
    "stock": 5,
    "format": "Digital",
    "category": "Tecnico",
    "authors": ["Sam Newman"],
    "genres": ["Arquitectura de software"],
    "concepts": [{"name": "Microservicio",
                  "definition": "Servicio pequeno, autonomo y desplegable de forma independiente."}],
    "images": [{"url": "https://covers.openlibrary.org/b/isbn/9781491950357-L.jpg",
                "isCover": True}],
}

BOOK_XML_EXAMPLE = f"""<?xml version="1.0" encoding="UTF-8"?>
<book xmlns="{NS}" isbn="978-1491950357">
  <title>Building Microservices</title>
  <publicationYear>2015</publicationYear>
  <price currency="MXN">899.90</price>
  <stock>5</stock>
  <format ref="2">Digital</format>
  <category>Tecnico</category>
  <authors count="1">
    <author>Sam Newman</author>
  </authors>
  <genres count="1">
    <genre ref="9">Arquitectura de software</genre>
  </genres>
  <concepts count="1">
    <concept>
      <name>Microservicio</name>
      <definition>Servicio pequeno, autonomo y desplegable de forma independiente.</definition>
    </concept>
  </concepts>
  <images count="1">
    <image isCover="true">https://covers.openlibrary.org/b/isbn/9781491950357-L.jpg</image>
  </images>
</book>
"""

LIBRARY_XML_EXAMPLE = f"""<?xml version="1.0" encoding="UTF-8"?>
<library xmlns="{NS}" version="1.0" generatedAt="2026-08-28T00:00:00Z"
         source="library_db" schema="library">
  <books count="1" total="13" limit="50" offset="0">
    <book id="1" isbn="978-0133970777">
      <title>Fundamentos de Sistemas de Bases de Datos</title>
      <publicationYear>2016</publicationYear>
      <price currency="MXN">1250.00</price>
      <stock>12</stock>
      <format ref="4">Pasta dura</format>
      <category ref="5">Academico</category>
      <authors count="2">
        <author ref="1">Ramez Elmasri</author>
        <author ref="2">Shamkant Navathe</author>
      </authors>
      <genres count="1">
        <genre ref="1">Bases de datos</genre>
      </genres>
      <concepts count="1">
        <concept ref="1">
          <name>Normalizacion</name>
          <definition>Proceso de descomposicion de relaciones para eliminar redundancia.</definition>
        </concept>
      </concepts>
      <images count="1">
        <image id="1" isCover="true">https://covers.openlibrary.org/b/isbn/9780133970777-L.jpg</image>
      </images>
    </book>
  </books>
</library>
"""


# ---------------------------------------------------------------------
# Esquemas
# ---------------------------------------------------------------------
def _schemas():
    catalog_ref = {
        "type": "object",
        "description": "Entrada de catalogo. 'ref' es el id en la tabla normalizada.",
        "properties": {
            "ref": {"type": "integer", "example": 4, "xml": {"attribute": True}},
            "name": {"type": "string", "example": "Pasta dura"},
        },
    }

    return {
        "CatalogRef": catalog_ref,
        "Concept": {
            "type": "object",
            "description": "Concepto definido por el libro. La definicion pertenece al "
                           "par (libro, concepto): el mismo concepto puede definirse de "
                           "otra forma en otro libro.",
            "required": ["definition"],
            "properties": {
                "ref": {"type": "integer", "example": 1, "xml": {"attribute": True}},
                "name": {"type": "string", "example": "Normalizacion"},
                "definition": {"type": "string",
                               "example": "Proceso de descomposicion de relaciones."},
            },
        },
        "Image": {
            "type": "object",
            "required": ["url"],
            "properties": {
                "id": {"type": "integer", "readOnly": True, "xml": {"attribute": True}},
                "url": {"type": "string", "maxLength": 500,
                        "example": "https://covers.openlibrary.org/b/isbn/9780133970777-L.jpg"},
                "isCover": {"type": "boolean", "default": False, "xml": {"attribute": True},
                            "description": "Como maximo una portada por libro "
                                           "(indice ux_book_images_one_cover)."},
            },
        },
        "Book": {
            "type": "object",
            "description": "Libro completo tal como lo devuelve el servicio.",
            "xml": {"name": "book", "namespace": NS},
            "properties": {
                "id": {"type": "integer", "readOnly": True, "xml": {"attribute": True}},
                "isbn": {"type": "string", "maxLength": 20, "xml": {"attribute": True}},
                "title": {"type": "string", "maxLength": 255},
                "publicationYear": {"type": "integer", "minimum": 1, "maximum": 2999},
                "price": {"type": "number", "format": "double", "minimum": 0},
                "currency": {"type": "string", "example": config.CURRENCY, "readOnly": True},
                "stock": {"type": "integer", "minimum": 0},
                "format": {"$ref": "#/components/schemas/CatalogRef"},
                "category": {"$ref": "#/components/schemas/CatalogRef"},
                "authors": {"type": "array", "items": {"$ref": "#/components/schemas/CatalogRef"},
                            "xml": {"wrapped": True, "name": "authors"}},
                "genres": {"type": "array", "items": {"$ref": "#/components/schemas/CatalogRef"},
                           "xml": {"wrapped": True, "name": "genres"}},
                "concepts": {"type": "array", "items": {"$ref": "#/components/schemas/Concept"},
                             "xml": {"wrapped": True, "name": "concepts"}},
                "images": {"type": "array", "items": {"$ref": "#/components/schemas/Image"},
                           "xml": {"wrapped": True, "name": "images"}},
                "createdAt": {"type": "string", "format": "date-time", "readOnly": True},
                "updatedAt": {"type": "string", "format": "date-time", "readOnly": True},
            },
            "example": BOOK_JSON_EXAMPLE,
        },
        "BookInput": {
            "type": "object",
            "description": (
                "Cuerpo de POST/PUT/PATCH.\n\n"
                "* `format` y `category` admiten el id (`4`) o el nombre (`\"Pasta dura\"`) "
                "y deben existir en el catalogo.\n"
                "* `authors` y `genres` admiten `[\"Nombre\"]`, `[{\"name\": \"...\"}]` o "
                "`[{\"ref\": 3}]`; si el nombre no existe se da de alta.\n"
                "* En **PUT** el cuerpo describe el libro completo: una coleccion ausente "
                "se vacia. En **PATCH** solo cambia lo enviado."),
            "xml": {"name": "book", "namespace": NS},
            "required": ["isbn", "title", "publicationYear", "price", "format", "category"],
            "properties": {
                "isbn": {"type": "string", "maxLength": 20, "example": "978-1491950357"},
                "title": {"type": "string", "maxLength": 255, "example": "Building Microservices"},
                "publicationYear": {"type": "integer", "example": 2015},
                "price": {"type": "number", "format": "double", "example": 899.90},
                "stock": {"type": "integer", "default": 0, "example": 5},
                "format": {"oneOf": [{"type": "string"}, {"type": "integer"}],
                           "example": "Digital"},
                "category": {"oneOf": [{"type": "string"}, {"type": "integer"}],
                             "example": "Tecnico"},
                "authors": {"type": "array", "items": {"oneOf": [
                    {"type": "string"}, {"$ref": "#/components/schemas/CatalogRef"}]}},
                "genres": {"type": "array", "items": {"oneOf": [
                    {"type": "string"}, {"$ref": "#/components/schemas/CatalogRef"}]}},
                "concepts": {"type": "array", "items": {"$ref": "#/components/schemas/Concept"}},
                "images": {"type": "array", "items": {"$ref": "#/components/schemas/Image"}},
            },
            "example": BOOK_INPUT_EXAMPLE,
        },
        "BookEnvelope": {
            "type": "object",
            "properties": {"book": {"$ref": "#/components/schemas/Book"}},
        },
        "BookCollection": {
            "type": "object",
            "description": "Listado paginado. La cabecera `X-Total-Count` repite `total`.",
            "xml": {"name": "library", "namespace": NS},
            "properties": {
                "library": {
                    "type": "object",
                    "properties": {
                        "version": {"type": "string", "example": "1.0"},
                        "generatedAt": {"type": "string", "format": "date-time"},
                        "source": {"type": "string", "example": "library_db"},
                        "schema": {"type": "string", "example": "library"},
                    },
                },
                "count": {"type": "integer", "description": "Libros en esta pagina."},
                "total": {"type": "integer", "description": "Libros que cumplen el filtro."},
                "limit": {"type": "integer"},
                "offset": {"type": "integer"},
                "filters": {"type": "object", "additionalProperties": {"type": "string"},
                            "description": "Filtros aplicados, tal como llegaron."},
                "books": {"type": "array", "items": {"$ref": "#/components/schemas/Book"}},
            },
        },
        "DeleteResult": {
            "type": "object",
            "xml": {"name": "deleted", "namespace": NS},
            "properties": {
                "deleted": {"type": "boolean", "example": True},
                "id": {"type": "integer", "example": 14},
                "isbn": {"type": "string", "example": "978-1491950357"},
                "title": {"type": "string", "example": "Building Microservices"},
            },
        },
        "CatalogList": {
            "type": "object",
            "properties": {
                "count": {"type": "integer", "example": 4},
                "formats": {"type": "array", "items": {"$ref": "#/components/schemas/CatalogRef"},
                            "description": "El nombre de la coleccion coincide con el catalogo "
                                           "consultado: formats, categories, genres, authors "
                                           "o concepts."},
            },
        },
        "Health": {
            "type": "object",
            "xml": {"name": "health", "namespace": NS},
            "properties": {
                "status": {"type": "string", "enum": ["ok", "error"]},
                "database": {"type": "string", "example": "library_db"},
                "user": {"type": "string", "example": "library_user"},
                "schema": {"type": "string", "example": "library"},
                "server": {"type": "string", "example": "PostgreSQL 16.15"},
                "message": {"type": "string", "description": "Solo cuando status = error."},
            },
        },
        "Error": {
            "type": "object",
            "xml": {"name": "error", "namespace": NS},
            "properties": {
                "error": {
                    "type": "object",
                    "properties": {
                        "status": {"type": "integer", "example": 404},
                        "code": {"type": "string", "example": "not_found",
                                 "enum": ["validation_error", "not_found", "conflict",
                                          "unsupported_media_type", "method_not_allowed",
                                          "database_unavailable", "internal_error",
                                          "http_error"]},
                        "message": {"type": "string"},
                        "details": {"type": "array", "items": {"type": "string"},
                                    "description": "Motivos concretos: campos faltantes, "
                                                   "valores validos de un catalogo, "
                                                   "restriccion violada."},
                    },
                },
            },
        },
    }


# ---------------------------------------------------------------------
# Parametros reutilizables
# ---------------------------------------------------------------------
def _query(name, description, schema, example=None):
    param = {"name": name, "in": "query", "required": False,
             "description": description, "schema": schema}
    if example is not None:
        param["example"] = example
    return param


def _parameters():
    return {
        "Output": _query(
            "output", "Formato de la respuesta. Tiene prioridad sobre la cabecera Accept.",
            {"type": "string", "enum": ["json", "xml"]}),
        "Limit": _query("limit", f"Libros por pagina (maximo {config.MAX_LIMIT}).",
                        {"type": "integer", "default": config.DEFAULT_LIMIT,
                         "minimum": 1, "maximum": config.MAX_LIMIT}),
        "Offset": _query("offset", "Libros que se saltan antes de empezar la pagina.",
                         {"type": "integer", "default": 0, "minimum": 0}),
        "Sort": _query("sort", "Campo de ordenamiento.",
                       {"type": "string", "default": "id",
                        "enum": ["id", "isbn", "title", "year", "publication_year",
                                 "price", "stock", "created_at", "updated_at"]}),
        "Order": _query("order", "Sentido del ordenamiento.",
                        {"type": "string", "default": "asc", "enum": ["asc", "desc"]}),
        "BookId": {"name": "book_id", "in": "path", "required": True,
                   "description": "Identificador del libro (books.id).",
                   "schema": {"type": "integer"}, "example": 1},
        "Isbn": {"name": "isbn", "in": "path", "required": True,
                 "description": "ISBN exacto del libro.",
                 "schema": {"type": "string"}, "example": "978-0133970777"},
    }


FILTER_PARAMS = [
    ("q", "Texto libre en titulo, ISBN o nombre de autor.", "clean"),
    ("title", "Parte del titulo (sin distinguir mayusculas ni parciales).", "algoritmos"),
    ("isbn", "Parte del ISBN.", "978-013"),
    ("author", "Parte del nombre de un autor.", "asimov"),
    ("genre", "Parte del nombre de un genero.", "novela"),
    ("concept", "Parte del nombre de un concepto definido en el libro.", "SOLID"),
    ("category", "Categoria por id o por nombre.", "Academico"),
    ("format", "Formato por id o por nombre. Los valores 'xml' y 'json' se "
               "interpretan como representacion, no como filtro.", "Digital"),
]

FILTER_NUMBERS = [
    ("year", "integer", "Ano de publicacion exacto.", 2016),
    ("year_min", "integer", "Ano de publicacion minimo.", 2000),
    ("year_max", "integer", "Ano de publicacion maximo.", 2020),
    ("price_min", "number", "Precio minimo.", 300),
    ("price_max", "number", "Precio maximo.", 1000),
    ("stock_min", "integer", "Existencias minimas.", 1),
    ("stock_max", "integer", "Existencias maximas.", 20),
]


def _filter_parameters():
    params = [_query(name, desc, {"type": "string"}, example)
              for name, desc, example in FILTER_PARAMS]
    params += [_query(name, desc, {"type": kind}, example)
               for name, kind, desc, example in FILTER_NUMBERS]
    params.append(_query("in_stock", "true devuelve solo libros con stock > 0.",
                         {"type": "boolean"}, True))
    return params


LIST_PARAMS = ([{"$ref": "#/components/parameters/Output"}]
               + _filter_parameters()
               + [{"$ref": f"#/components/parameters/{p}"}
                  for p in ("Sort", "Order", "Limit", "Offset")])


# ---------------------------------------------------------------------
# Respuestas reutilizables
# ---------------------------------------------------------------------
def _both(schema_ref, xml_example):
    """Cuerpo disponible en los dos formatos del servicio."""
    return {
        "application/json": {"schema": {"$ref": schema_ref}},
        "application/xml": {"schema": {"$ref": schema_ref}, "example": xml_example},
    }


def _error(description, example_status, example_code, example_message, details=None):
    return {
        "description": description,
        "content": {
            "application/json": {
                "schema": {"$ref": "#/components/schemas/Error"},
                "example": {"error": {"status": example_status, "code": example_code,
                                      "message": example_message, "details": details or []}},
            },
            "application/xml": {"schema": {"$ref": "#/components/schemas/Error"}},
        },
    }


def _responses():
    return {
        "NotFound": _error("El libro no existe.", 404, "not_found",
                           "No existe un libro con id 999."),
        "ValidationError": _error(
            "Datos invalidos o parametro de consulta mal formado.", 400, "validation_error",
            "El formato 'Papiro' no existe en el catalogo.",
            ["Valores disponibles: 1=Fisico, 2=Digital, 3=Audiolibro, 4=Pasta dura."]),
        "Conflict": _error(
            "Restriccion de unicidad violada (ISBN repetido o segunda portada).",
            409, "conflict", "Ya existe un libro con el ISBN 978-0441013593.",
            ["Key (isbn)=(978-0441013593) already exists."]),
        "UnsupportedMedia": _error(
            "Content-Type no soportado.", 415, "unsupported_media_type",
            "Content-Type 'text/plain' no soportado. Use application/json o application/xml."),
        "DatabaseUnavailable": _error(
            "No hay conexion con PostgreSQL.", 503, "database_unavailable",
            "No hay conexion con PostgreSQL.",
            ["Revise PGHOST/PGPORT/PGUSER/PGPASSWORD en soap/.env."]),
    }


BOOK_REQUEST_BODY = {
    "required": True,
    "description": "El libro, en JSON o en XML (mismo diseno que library.xml).",
    "content": {
        "application/json": {
            "schema": {"$ref": "#/components/schemas/BookInput"},
            "example": BOOK_INPUT_EXAMPLE,
        },
        "application/xml": {
            "schema": {"$ref": "#/components/schemas/BookInput"},
            "example": BOOK_XML_EXAMPLE,
        },
    },
}

BOOK_OK = {
    "description": "El libro completo.",
    "content": _both("#/components/schemas/BookEnvelope", BOOK_XML_EXAMPLE),
}


def _paths():
    collection_response = {
        "description": "Libros que cumplen el filtro.",
        "headers": {"X-Total-Count": {"description": "Total de libros que cumplen el filtro.",
                                      "schema": {"type": "integer"}}},
        "content": _both("#/components/schemas/BookCollection", LIBRARY_XML_EXAMPLE),
    }

    def catalog_path(name, tag_name):
        return {
            "get": {
                "tags": ["Catalogos"],
                "summary": f"Catalogo de {tag_name}",
                "description": f"Valores disponibles de {tag_name}, con su `ref` "
                               "para usarlo en las peticiones de escritura.",
                "parameters": [{"$ref": "#/components/parameters/Output"}],
                "responses": {
                    "200": {"description": f"Lista de {tag_name}.",
                            "content": _both("#/components/schemas/CatalogList", None)},
                    "503": {"$ref": "#/components/responses/DatabaseUnavailable"},
                },
            }
        }

    paths = {
        "/": {"get": {
            "tags": ["Servicio"],
            "summary": "Indice del servicio",
            "description": "Lista los endpoints, los filtros y los campos de ordenamiento.",
            "parameters": [{"$ref": "#/components/parameters/Output"}],
            "responses": {"200": {"description": "Descripcion del servicio."}},
        }},
        "/health": {"get": {
            "tags": ["Servicio"],
            "summary": "Estado del servicio y de la base de datos",
            "description": "Abre una conexion real contra PostgreSQL. Devuelve 503 si falla.",
            "parameters": [{"$ref": "#/components/parameters/Output"}],
            "responses": {
                "200": {"description": "El servicio responde y la base contesta.",
                        "content": _both("#/components/schemas/Health", None)},
                "503": {"description": "PostgreSQL no responde.",
                        "content": _both("#/components/schemas/Health", None)},
            },
        }},
        f"{API}/books": {
            "get": {
                "tags": ["Libros"],
                "summary": "Todos los libros",
                "description": "Devuelve el catalogo completo. Acepta los mismos filtros "
                               "que `/books/search`, mas orden y paginacion.",
                "parameters": LIST_PARAMS,
                "responses": {
                    "200": collection_response,
                    "400": {"$ref": "#/components/responses/ValidationError"},
                    "503": {"$ref": "#/components/responses/DatabaseUnavailable"},
                },
            },
            "post": {
                "tags": ["Libros"],
                "summary": "Alta de un libro",
                "description": "Crea el libro y sus relaciones en una sola transaccion. "
                               "Devuelve 201 con la cabecera `Location`.",
                "parameters": [{"$ref": "#/components/parameters/Output"}],
                "requestBody": BOOK_REQUEST_BODY,
                "responses": {
                    "201": {**BOOK_OK, "description": "Libro creado.",
                            "headers": {"Location": {"description": "Ruta del libro creado.",
                                                     "schema": {"type": "string"}}}},
                    "400": {"$ref": "#/components/responses/ValidationError"},
                    "409": {"$ref": "#/components/responses/Conflict"},
                    "415": {"$ref": "#/components/responses/UnsupportedMedia"},
                    "503": {"$ref": "#/components/responses/DatabaseUnavailable"},
                },
            },
        },
        f"{API}/books/search": {"get": {
            "tags": ["Libros"],
            "summary": "Buscar por atributos",
            "description": "Combina cualquier filtro con AND. Los filtros de texto son "
                           "parciales y no distinguen mayusculas (ILIKE). `author`, "
                           "`genre` y `concept` cruzan las tablas de relacion.",
            "parameters": LIST_PARAMS,
            "responses": {
                "200": collection_response,
                "400": {"$ref": "#/components/responses/ValidationError"},
                "503": {"$ref": "#/components/responses/DatabaseUnavailable"},
            },
        }},
        f"{API}/books/{{book_id}}": {
            "get": {
                "tags": ["Libros"],
                "summary": "Un libro por id",
                "description": "Devuelve el libro con sus autores, generos, conceptos "
                               "e imagenes.",
                "parameters": [{"$ref": "#/components/parameters/BookId"},
                               {"$ref": "#/components/parameters/Output"}],
                "responses": {
                    "200": BOOK_OK,
                    "404": {"$ref": "#/components/responses/NotFound"},
                    "503": {"$ref": "#/components/responses/DatabaseUnavailable"},
                },
            },
            "put": {
                "tags": ["Libros"],
                "summary": "Modificar un libro (reemplazo completo)",
                "description": "El cuerpo describe el libro entero. Las cuatro colecciones "
                               "se sustituyen: la que no venga queda vacia.",
                "parameters": [{"$ref": "#/components/parameters/BookId"},
                               {"$ref": "#/components/parameters/Output"}],
                "requestBody": BOOK_REQUEST_BODY,
                "responses": {
                    "200": BOOK_OK,
                    "400": {"$ref": "#/components/responses/ValidationError"},
                    "404": {"$ref": "#/components/responses/NotFound"},
                    "409": {"$ref": "#/components/responses/Conflict"},
                    "415": {"$ref": "#/components/responses/UnsupportedMedia"},
                    "503": {"$ref": "#/components/responses/DatabaseUnavailable"},
                },
            },
            "patch": {
                "tags": ["Libros"],
                "summary": "Actualizar un libro (cambio parcial)",
                "description": "Solo cambia lo enviado. Una coleccion presente se "
                               "reemplaza por completo; una ausente no se toca.",
                "parameters": [{"$ref": "#/components/parameters/BookId"},
                               {"$ref": "#/components/parameters/Output"}],
                "requestBody": {
                    "required": True,
                    "description": "Subconjunto de los campos del libro.",
                    "content": {
                        "application/json": {
                            "schema": {"$ref": "#/components/schemas/BookInput"},
                            "example": {"price": 950.00, "stock": 3},
                        },
                        "application/xml": {
                            "schema": {"$ref": "#/components/schemas/BookInput"},
                            "example": f'<book xmlns="{NS}">\n'
                                       '  <price currency="MXN">950.00</price>\n'
                                       "  <stock>3</stock>\n</book>\n",
                        },
                    },
                },
                "responses": {
                    "200": BOOK_OK,
                    "400": {"$ref": "#/components/responses/ValidationError"},
                    "404": {"$ref": "#/components/responses/NotFound"},
                    "409": {"$ref": "#/components/responses/Conflict"},
                    "415": {"$ref": "#/components/responses/UnsupportedMedia"},
                    "503": {"$ref": "#/components/responses/DatabaseUnavailable"},
                },
            },
            "delete": {
                "tags": ["Libros"],
                "summary": "Borrar un libro",
                "description": "Elimina el libro. Sus autores, generos, conceptos e "
                               "imagenes caen con el por `ON DELETE CASCADE`; los "
                               "catalogos no se tocan.",
                "parameters": [{"$ref": "#/components/parameters/BookId"},
                               {"$ref": "#/components/parameters/Output"}],
                "responses": {
                    "200": {"description": "Libro borrado.",
                            "content": _both("#/components/schemas/DeleteResult", None)},
                    "404": {"$ref": "#/components/responses/NotFound"},
                    "503": {"$ref": "#/components/responses/DatabaseUnavailable"},
                },
            },
        },
        f"{API}/books/isbn/{{isbn}}": {"get": {
            "tags": ["Libros"],
            "summary": "Un libro por ISBN",
            "description": "El ISBN identifica al libro igual que el id "
                           "(dependencia funcional ISBN -> libro).",
            "parameters": [{"$ref": "#/components/parameters/Isbn"},
                           {"$ref": "#/components/parameters/Output"}],
            "responses": {
                "200": BOOK_OK,
                "404": {"$ref": "#/components/responses/NotFound"},
                "503": {"$ref": "#/components/responses/DatabaseUnavailable"},
            },
        }},
        f"{API}/formats": catalog_path("formats", "formatos"),
        f"{API}/categories": catalog_path("categories", "categorias"),
        f"{API}/genres": catalog_path("genres", "generos"),
        f"{API}/authors": catalog_path("authors", "autores"),
        f"{API}/concepts": catalog_path("concepts", "conceptos"),
    }
    return paths


def build_spec():
    """Documento OpenAPI 3.0.3 completo."""
    return {
        "openapi": "3.0.3",
        "info": {
            "title": "Libreria en Linea — Microservicio de libros",
            "version": "1.0.0",
            "description": DESCRIPTION,
            "contact": {"name": "Practica de Integracion de Sistemas — UDEM"},
        },
        "servers": [
            {"url": SERVER_URL, "description": "Entorno local"},
            {"url": "/", "description": "Mismo origen que esta pagina"},
        ],
        "tags": [
            {"name": "Libros", "description": "Operaciones CRUD y busqueda por atributos."},
            {"name": "Catalogos", "description": "Valores validos de formato, categoria, "
                                                 "genero, autor y concepto."},
            {"name": "Servicio", "description": "Indice y estado."},
        ],
        "paths": _paths(),
        "components": {
            "schemas": _schemas(),
            "parameters": _parameters(),
            "responses": _responses(),
        },
    }
