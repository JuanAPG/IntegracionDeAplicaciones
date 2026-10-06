"""
packages/library_common/library_common/openapi.py
Constructor de la especificacion OpenAPI 3.0.3 que publican los
servicios en /openapi.json y muestra Swagger UI en /docs.

Los microservicios de login y de libros escriben su especificacion a
mano, endpoint por endpoint. Para los cuatro nuevos se describe cada
ruta de forma COMPACTA y este modulo se encarga de lo que es igual en
todos:

  * el esquema de seguridad Bearer (JWT HS256 emitido por login);
  * los parametros de negociacion (?format=/?output=) y de paginacion;
  * las respuestas de error 400/401/403/404/409/503 con su esquema;
  * los dos tipos de contenido, application/json y application/xml.

Asi la documentacion no se desincroniza entre servicios: si se arregla
la descripcion de un 401, se arregla en los cuatro a la vez.
"""

ERROR_SCHEMA = {
    "type": "object",
    "properties": {
        "error": {
            "type": "object",
            "properties": {
                "status": {"type": "integer", "example": 401},
                "code": {"type": "string", "example": "unauthorized"},
                "message": {"type": "string"},
                "details": {"type": "array", "items": {"type": "string"}},
            },
        }
    },
}

# Respuestas que puede devolver cualquier endpoint del sistema.
COMMON_RESPONSES = {
    "BadRequest": (400, "Cuerpo o parametros invalidos."),
    "Unauthorized": (401, "Token ausente, malformado, invalido, caducado o "
                          "REVOCADO (se cerro la sesion). Vuelva a "
                          "autenticarse en el microservicio de login."),
    "Forbidden": (403, "El token es valido pero el rol no tiene el permiso "
                       "necesario para esta operacion."),
    "NotFound": (404, "El recurso no existe."),
    "Conflict": (409, "Choca con una regla de negocio o con un valor unico."),
    "Unavailable": (503, "PostgreSQL o Redis no estan disponibles. Las "
                         "operaciones de autorizacion fallan de forma segura: "
                         "si no se puede comprobar la lista de revocacion, el "
                         "token no se acepta."),
}

FORMAT_PARAM = {
    "name": "format",
    "in": "query",
    "required": False,
    "description": "Representacion de la respuesta. Sin este parametro se "
                   "devuelve XML, que es el formato por omision del proyecto. "
                   "Tambien se admite ?output= y la cabecera Accept.",
    "schema": {"type": "string", "enum": ["xml", "json"]},
}

PAGINATION_PARAMS = [
    {"name": "limit", "in": "query", "required": False,
     "description": "Maximo de elementos por pagina.",
     "schema": {"type": "integer", "minimum": 1, "default": 50}},
    {"name": "offset", "in": "query", "required": False,
     "description": "Elementos que se omiten desde el principio.",
     "schema": {"type": "integer", "minimum": 0, "default": 0}},
]


def _responses(entries, success=None):
    """Traduce ('Unauthorized', 'Forbidden', ...) al bloque responses."""
    block = {}
    if success:
        status, description, schema = success
        content = {
            "application/json": {"schema": schema or {"type": "object"}},
            "application/xml": {"schema": {"type": "string",
                                           "description": "El mismo recurso en XML."}},
        }
        block[str(status)] = {"description": description, "content": content}
    for name in entries or ():
        status, description = COMMON_RESPONSES[name]
        block[str(status)] = {
            "description": description,
            "content": {"application/json": {"schema": ERROR_SCHEMA},
                        "application/xml": {"schema": {"type": "string"}}},
        }
    return block


def build(*, service, title, description, version="1.0", namespace,
          paths, port=None, extra_schemas=None, tags=None):
    """
    Construye la especificacion completa.

    `paths` es una lista de diccionarios compactos:

        {"path": "/users/{id}", "method": "get", "summary": "...",
         "description": "...", "tag": "Usuarios",
         "auth": "users:read" | True | None,
         "params": [...], "paginated": True,
         "body": {...esquema...},
         "success": (200, "descripcion", {...esquema...}),
         "errors": ["Unauthorized", "Forbidden", "NotFound"]}

    `auth`:
        None      endpoint publico (no exige token)
        True      exige un JWT valido, sin permiso concreto
        "a:b"     exige un JWT valido Y el permiso "a:b" del rol
    """
    documento = {
        "openapi": "3.0.3",
        "info": {
            "title": title,
            "version": version,
            "description": description,
        },
        "servers": ([{"url": f"http://localhost:{port}",
                      "description": "Servicio local"}] if port else []),
        "tags": [{"name": t} for t in (tags or [])],
        "components": {
            "securitySchemes": {
                "bearerAuth": {
                    "type": "http",
                    "scheme": "bearer",
                    "bearerFormat": "JWT",
                    "description": (
                        "JWT firmado con HS256 y el secreto compartido "
                        "JWT_SECRET_KEY. Lo emite POST /login del "
                        "microservicio de autenticacion y dura 30 minutos; "
                        "renuevelo con POST /refresh antes de que caduque. "
                        "Claims: sub, user_id, role_id, role, email, sid, jti. "
                        "Antes de aceptarlo, este servicio comprueba firma, "
                        "algoritmo, vencimiento, emisor, claims obligatorios y "
                        "que el jti no este en la lista de revocacion de Redis."),
                }
            },
            "schemas": {"Error": ERROR_SCHEMA, **(extra_schemas or {})},
        },
        "paths": {},
    }

    for entry in paths:
        ruta = entry["path"]
        metodo = entry["method"].lower()
        operacion = {
            "summary": entry.get("summary", ""),
            "description": entry.get("description", ""),
            "tags": [entry["tag"]] if entry.get("tag") else [],
            "parameters": [FORMAT_PARAM] + list(entry.get("params") or []),
            "responses": _responses(entry.get("errors"), entry.get("success")),
        }
        if entry.get("paginated"):
            operacion["parameters"].extend(PAGINATION_PARAMS)

        auth = entry.get("auth")
        if auth:
            operacion["security"] = [{"bearerAuth": []}]
            if isinstance(auth, str):
                operacion["description"] = (
                    (operacion["description"] or "")
                    + f"\n\n**Permiso requerido:** `{auth}`.")
        else:
            operacion["security"] = []

        if entry.get("body"):
            operacion["requestBody"] = {
                "required": entry.get("body_required", True),
                "content": {
                    "application/json": {"schema": entry["body"]},
                    "application/xml": {"schema": {
                        "type": "string",
                        "description": "Los mismos campos como elementos XML.",
                    }},
                },
            }

        documento["paths"].setdefault(ruta, {})[metodo] = operacion

    documento["info"]["description"] += (
        f"\n\nEspacio de nombres del XML: `{namespace}`."
        f"\n\nServicio: `{service}`."
        "\n\nLos errores siguen la misma forma en los seis microservicios: "
        "`{\"error\": {\"status\", \"code\", \"message\", \"details\"}}`.")
    return documento
