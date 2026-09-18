"""
apps/services/login/login/openapi.py
Especificacion OpenAPI 3.0.3 escrita a mano (igual que el microservicio
de libros): describe los dos formatos de intercambio, todos los endpoints
y los codigos de error. Flasgger la sirve en /openapi.json y /docs.
"""


def _fmt_desc():
    return ("Todos los endpoints responden XML o JSON. ?format=xml | "
            "?format=json tiene prioridad; sin parametro, XML.")


def _responses(extra_post_ok=None, with_201=False):
    ok_body = extra_post_ok or {"$ref": "#/components/schemas/User"}
    responses = {
        "200": {
            "description": "Exito. " + _fmt_desc(),
            "content": {
                "application/json": {"schema": ok_body},
                "application/xml": {"schema": {"type": "string"}},
            },
        },
        "400": {"$ref": "#/components/responses/BadRequest"},
        "401": {"$ref": "#/components/responses/Unauthorized"},
        "403": {"$ref": "#/components/responses/Forbidden"},
        "404": {"$ref": "#/components/responses/NotFound"},
        "409": {"$ref": "#/components/responses/Conflict"},
        "410": {"$ref": "#/components/responses/Gone"},
        "503": {"$ref": "#/components/responses/Unavailable"},
    }
    if with_201:
        responses["201"] = responses.pop("200")
        responses["201"]["description"] = "Creado. " + _fmt_desc()
    return responses


def _format_param():
    return {
        "name": "format",
        "in": "query",
        "required": False,
        "schema": {"type": "string", "enum": ["xml", "json"], "default": "xml"},
        "description": "Formato de respuesta. Sin parametro, XML.",
    }


def _json_xml_body(schema, example):
    return {
        "required": True,
        "content": {
            "application/json": {"schema": schema, "example": example},
            "application/xml": {"schema": {"type": "string"}},
        },
    }


def build_spec():
    register_example = {
        "nombre": "Ada",
        "apellidoPaterno": "Lovelace",
        "apellidoMaterno": "Byron",
        "email": "ada@ejemplo.mx",
        "password": "Secreto123",
    }
    return {
        "openapi": "3.0.3",
        "info": {
            "title": "Libreria en Linea — Microservicio de autenticacion",
            "version": "1.0.0",
            "description": (
                "Autenticacion y usuarios de library_db (esquema library) con "
                "Flask + Psycopg 3. Registro con nombre normalizado "
                "(nombre, apellido paterno, apellido materno), verificacion "
                "del correo por sendmail local (sin POP/IMAP) y sesion del "
                "lado de Flask. " + _fmt_desc()
            ),
        },
        "servers": [{"url": "/", "description": "Mismo origen que esta pagina"}],
        "paths": {
            "/": {
                "get": {
                    "summary": "Indice del servicio",
                    "parameters": [_format_param()],
                    "responses": _responses({"type": "object"}),
                }
            },
            "/health": {
                "get": {
                    "summary": "Estado del microservicio y PostgreSQL",
                    "parameters": [_format_param()],
                    "responses": _responses({"type": "object"}),
                }
            },
            "/validate-email": {
                "get": {
                    "summary": "Validacion previa del correo",
                    "description": ("Sintaxis, unicidad y registro interno de "
                                    "correos ya verificados, antes de registrarse."),
                    "parameters": [
                        _format_param(),
                        {"name": "email", "in": "query", "required": True,
                         "schema": {"type": "string", "format": "email"},
                         "description": "Correo a validar."},
                    ],
                    "responses": _responses({"type": "object"}),
                }
            },
            "/register": {
                "post": {
                    "summary": "Registrar un nuevo usuario",
                    "description": ("Valida los campos y la unicidad del correo, "
                                    "guarda solo el hash bcrypt y envia el token "
                                    "de verificacion por sendmail."),
                    "parameters": [_format_param()],
                    "requestBody": _json_xml_body(
                        {"$ref": "#/components/schemas/Register"},
                        register_example),
                    "responses": _responses(
                        {"$ref": "#/components/schemas/Registration"}, with_201=True),
                }
            },
            "/verify": {
                "get": {
                    "summary": "Verificar el correo con el token",
                    "parameters": [
                        _format_param(),
                        {"name": "token", "in": "query", "required": True,
                         "schema": {"type": "string"},
                         "description": "Token del enlace enviado por correo."},
                    ],
                    "responses": _responses({"type": "object"}),
                },
                "post": {
                    "summary": "Verificar el correo (token en el cuerpo)",
                    "parameters": [_format_param()],
                    "requestBody": _json_xml_body(
                        {"type": "object",
                         "properties": {"token": {"type": "string"}}},
                        {"token": "abc123..."}),
                    "responses": _responses({"type": "object"}),
                },
            },
            "/login": {
                "post": {
                    "summary": "Autenticar e iniciar sesion",
                    "description": ("Verifica las credenciales contra PostgreSQL "
                                    "y crea la sesion Flask (cookie). Exige correo "
                                    "verificado y cuenta activa."),
                    "parameters": [_format_param()],
                    "requestBody": _json_xml_body(
                        {"$ref": "#/components/schemas/Credentials"},
                        {"email": "ada@ejemplo.mx", "password": "Secreto123"}),
                    "responses": _responses({"type": "object"}),
                }
            },
            "/logout": {
                "post": {
                    "summary": "Cerrar la sesion",
                    "parameters": [_format_param()],
                    "responses": _responses({"type": "object"}),
                }
            },
            "/session": {
                "get": {
                    "summary": "Consultar la sesion autenticada",
                    "parameters": [_format_param()],
                    "responses": _responses({"type": "object"}),
                }
            },
        },
        "components": {
            "schemas": {
                "Register": {
                    "type": "object",
                    "required": ["nombre", "apellidoPaterno", "email", "password"],
                    "properties": {
                        "nombre": {"type": "string", "example": "Ada"},
                        "apellidoPaterno": {"type": "string", "example": "Lovelace"},
                        "apellidoMaterno": {"type": "string", "example": "Byron"},
                        "email": {"type": "string", "format": "email"},
                        "password": {"type": "string", "minLength": 6},
                    },
                },
                "Credentials": {
                    "type": "object",
                    "required": ["email", "password"],
                    "properties": {
                        "email": {"type": "string", "format": "email"},
                        "password": {"type": "string"},
                    },
                },
                "User": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "integer"},
                        "nombre": {"type": "string"},
                        "apellidoPaterno": {"type": "string"},
                        "apellidoMaterno": {"type": "string"},
                        "fullName": {"type": "string"},
                        "email": {"type": "string", "format": "email"},
                        "role": {"type": "string", "enum": ["admin", "user"]},
                        "emailVerified": {"type": "boolean"},
                        "isActive": {"type": "boolean"},
                    },
                },
                "Registration": {
                    "type": "object",
                    "properties": {
                        "created": {"type": "boolean"},
                        "user": {"$ref": "#/components/schemas/User"},
                        "emailVerification": {
                            "type": "object",
                            "properties": {
                                "required": {"type": "boolean"},
                                "sent": {"type": "boolean"},
                                "expiresAt": {"type": "string", "format": "date-time"},
                            },
                        },
                    },
                },
                "Error": {
                    "type": "object",
                    "properties": {
                        "error": {
                            "type": "object",
                            "properties": {
                                "status": {"type": "integer"},
                                "code": {"type": "string"},
                                "message": {"type": "string"},
                                "details": {"type": "array",
                                            "items": {"type": "string"}},
                            },
                        }
                    },
                },
            },
            "responses": {
                name: {
                    "description": desc,
                    "content": {
                        "application/json": {"schema": {"$ref": "#/components/schemas/Error"}},
                        "application/xml": {"schema": {"type": "string"}},
                    },
                }
                for name, desc in [
                    ("BadRequest", "Campos invalidos (400)."),
                    ("Unauthorized", "Credenciales invalidas o cuenta desactivada (401)."),
                    ("Forbidden", "Correo sin verificar (403, codigo email_not_verified)."),
                    ("NotFound", "Recurso o token inexistente (404)."),
                    ("Conflict", "Correo ya registrado (409)."),
                    ("Gone", "Token usado o expirado (410)."),
                    ("Unavailable", "PostgreSQL o sendmail no disponibles (503)."),
                ]
            },
        },
    }
