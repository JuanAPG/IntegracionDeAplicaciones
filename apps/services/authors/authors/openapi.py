"""
apps/services/authors/authors/openapi.py
Especificacion OpenAPI 3.0.3 del microservicio de autores.
"""
from . import config
from library_common.openapi import build

BOOK_SUMMARY = {
    "type": "object",
    "description": "RESUMEN de la obra. La ficha completa la sirve "
                   "GET /books/<id> del microservicio de libros, que es su dueno.",
    "properties": {
        "id": {"type": "integer"},
        "isbn": {"type": "string", "example": "978-607-11-1111-1"},
        "title": {"type": "string"},
        "publicationYear": {"type": "integer"},
        "price": {"type": "number", "format": "double"},
        "stock": {"type": "integer"},
    },
}

AUTHOR_SCHEMA = {
    "type": "object",
    "properties": {
        "id": {"type": "integer", "example": 1},
        "name": {"type": "string", "example": "Ada Lovelace"},
        "bookCount": {"type": "integer", "example": 3},
        "books": {"type": "array", "items": BOOK_SUMMARY,
                  "description": "Solo en la ficha de un autor."},
    },
}

ID_PARAM = [{"name": "id", "in": "path", "required": True,
             "schema": {"type": "integer"}, "description": "Id del autor."}]
ID_BOOK_PARAMS = ID_PARAM + [
    {"name": "bookId", "in": "path", "required": True,
     "schema": {"type": "integer"}, "description": "Id del libro."}]

API = config.API_PREFIX


def build_spec():
    return build(
        service=config.SERVICE_NAME,
        title="Libreria en Linea — Microservicio de autores",
        description=(
            "Administra el catalogo de autores (`library.authors`) y su "
            "relacion M:N con los libros (`library.book_authors`).\n\n"
            "**Lecturas publicas y cacheadas.** Quien escribio un libro es "
            "informacion de catalogo, la misma que ya publica `GET /books`; "
            "van en Redis con TTL corto y la cabecera `X-Cache` dice si la "
            "respuesta vino de Redis (`HIT`) o de PostgreSQL (`MISS`).\n\n"
            "**Escrituras con token.** Exigen `Authorization: Bearer <JWT>` y "
            "el permiso `authors:write`.\n\n"
            "**Invalidacion cruzada.** Renombrar o borrar un autor cambia "
            "tambien el cuerpo de sus libros, que cachea el microservicio de "
            "libros en `books:*`. Hay un solo Redis, de modo que al escribir "
            "aqui se invalidan las dos familias de claves en lugar de dejar a "
            "la vista un autor con el nombre viejo.\n\n"
            "**Donde acaba este servicio.** No toca los datos del libro "
            "(titulo, precio, stock): eso es del microservicio de libros."),
        version=config.XML_VERSION,
        namespace=config.XML_NAMESPACE,
        port=config.PORT,
        tags=["Servicio", "Autores", "Obras"],
        extra_schemas={"Author": AUTHOR_SCHEMA, "BookSummary": BOOK_SUMMARY},
        paths=[
            {"path": "/", "method": "get", "tag": "Servicio",
             "summary": "Indice del servicio", "auth": None,
             "success": (200, "Indice", {"type": "object"})},
            {"path": "/health", "method": "get", "tag": "Servicio",
             "summary": "Estado del servicio",
             "description": "PostgreSQL caido devuelve 503. Redis caido "
                            "devuelve 200 con `status: degraded`: las lecturas "
                            "siguen sin cache, pero las escrituras daran 503 "
                            "porque no se puede comprobar la revocacion.",
             "auth": None, "success": (200, "Estado", {"type": "object"}),
             "errors": ["Unavailable"]},
            {"path": "/metrics", "method": "get", "tag": "Servicio",
             "summary": "Metricas del proceso y del cache", "auth": None,
             "success": (200, "Metricas", {"type": "object"})},

            {"path": f"{API}/authors", "method": "get", "tag": "Autores",
             "summary": "Catalogo de autores",
             "description": "Publico y cacheado. Admite filtros, orden y "
                            "paginacion.",
             "auth": None, "paginated": True,
             "params": [
                 {"name": "q", "in": "query", "schema": {"type": "string"},
                  "description": "Busca por nombre (parcial, sin distinguir "
                                 "mayusculas)."},
                 {"name": "has_books", "in": "query", "schema": {"type": "boolean"},
                  "description": "true = solo autores con obras; false = solo "
                                 "los que no tienen ninguna."},
                 {"name": "sort", "in": "query",
                  "schema": {"type": "string", "enum": ["id", "name", "books"]}},
                 {"name": "order", "in": "query",
                  "schema": {"type": "string", "enum": ["asc", "desc"]}},
             ],
             "success": (200, "Autores que cumplen los filtros",
                         {"type": "object",
                          "properties": {"total": {"type": "integer"},
                                         "authors": {"type": "array",
                                                     "items": AUTHOR_SCHEMA}}}),
             "errors": ["BadRequest", "Unavailable"]},

            {"path": f"{API}/authors/{{id}}", "method": "get", "tag": "Autores",
             "summary": "Un autor con el resumen de sus obras",
             "auth": None, "params": ID_PARAM,
             "success": (200, "El autor", AUTHOR_SCHEMA),
             "errors": ["NotFound", "Unavailable"]},

            {"path": f"{API}/authors/{{id}}/books", "method": "get", "tag": "Obras",
             "summary": "Obras del autor", "auth": None, "params": ID_PARAM,
             "success": (200, "Obras", {"type": "object",
                                        "properties": {"books": {"type": "array",
                                                                 "items": BOOK_SUMMARY}}}),
             "errors": ["NotFound", "Unavailable"]},

            {"path": f"{API}/authors", "method": "post", "tag": "Autores",
             "summary": "Alta de autor",
             "description": "El nombre es unico en `library.authors`. Se puede "
                            "vincular obras en la misma peticion con `books`.",
             "auth": "authors:write",
             "body": {"type": "object", "required": ["name"],
                      "properties": {"name": {"type": "string", "maxLength": 150},
                                     "books": {"type": "array",
                                               "items": {"type": "integer"},
                                               "description": "Ids de libro a vincular."}}},
             "success": (201, "Autor creado", AUTHOR_SCHEMA),
             "errors": ["BadRequest", "Unauthorized", "Forbidden", "Conflict",
                        "Unavailable"]},

            {"path": f"{API}/authors/{{id}}", "method": "put", "tag": "Autores",
             "summary": "Renombrar autor",
             "description": "PUT y PATCH hacen lo mismo: el autor tiene un solo "
                            "campo editable, de modo que no hay diferencia "
                            "posible entre reemplazo completo y cambio "
                            "parcial. Para sus obras esta "
                            "`PUT /authors/{id}/books`.",
             "auth": "authors:write", "params": ID_PARAM,
             "body": {"type": "object", "required": ["name"],
                      "properties": {"name": {"type": "string", "maxLength": 150}}},
             "success": (200, "Autor renombrado", AUTHOR_SCHEMA),
             "errors": ["BadRequest", "Unauthorized", "Forbidden", "NotFound",
                        "Conflict", "Unavailable"]},

            {"path": f"{API}/authors/{{id}}", "method": "patch", "tag": "Autores",
             "summary": "Renombrar autor (igual que PUT)",
             "auth": "authors:write", "params": ID_PARAM,
             "body": {"type": "object", "required": ["name"],
                      "properties": {"name": {"type": "string"}}},
             "success": (200, "Autor renombrado", AUTHOR_SCHEMA),
             "errors": ["BadRequest", "Unauthorized", "Forbidden", "NotFound",
                        "Conflict", "Unavailable"]},

            {"path": f"{API}/authors/{{id}}", "method": "delete", "tag": "Autores",
             "summary": "Baja de autor",
             "description": "Si tiene obras se RECHAZA con 409 salvo que se "
                            "pida `?force=true`: `book_authors` cae por ON "
                            "DELETE CASCADE, de modo que borrar el autor "
                            "dejaria sus libros sin autoria en silencio.",
             "auth": "authors:write",
             "params": ID_PARAM + [
                 {"name": "force", "in": "query", "schema": {"type": "boolean"},
                  "description": "Confirma el borrado aunque tenga obras."}],
             "success": (200, "Autor borrado", {"type": "object"}),
             "errors": ["Unauthorized", "Forbidden", "NotFound", "Conflict",
                        "Unavailable"]},

            {"path": f"{API}/authors/{{id}}/books", "method": "put", "tag": "Obras",
             "summary": "Fijar las obras del autor",
             "description": "Reemplaza la lista COMPLETA: lo que no venga se "
                            "desvincula. En una sola transaccion, de modo que "
                            "el autor nunca se queda sin obras a medias.",
             "auth": "authors:write", "params": ID_PARAM,
             "body": {"type": "object", "required": ["books"],
                      "properties": {"books": {"type": "array",
                                               "items": {"type": "integer"},
                                               "example": [1, 4, 7]}}},
             "success": (200, "Obras fijadas", AUTHOR_SCHEMA),
             "errors": ["BadRequest", "Unauthorized", "Forbidden", "NotFound",
                        "Unavailable"]},

            {"path": f"{API}/authors/{{id}}/books/{{bookId}}", "method": "post",
             "tag": "Obras", "summary": "Vincular una obra",
             "description": "Idempotente: repetirlo devuelve 200 con "
                            "`alreadyLinked: true` en lugar de un error.",
             "auth": "authors:write", "params": ID_BOOK_PARAMS,
             "success": (201, "Obra vinculada", {"type": "object"}),
             "errors": ["Unauthorized", "Forbidden", "NotFound", "Unavailable"]},

            {"path": f"{API}/authors/{{id}}/books/{{bookId}}", "method": "delete",
             "tag": "Obras", "summary": "Desvincular una obra",
             "description": "Quita solo la autoria; el libro sigue en el catalogo.",
             "auth": "authors:write", "params": ID_BOOK_PARAMS,
             "success": (200, "Obra desvinculada", {"type": "object"}),
             "errors": ["Unauthorized", "Forbidden", "NotFound", "Unavailable"]},
        ])
