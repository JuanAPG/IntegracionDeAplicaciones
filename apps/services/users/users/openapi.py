"""
apps/services/users/users/openapi.py
Especificacion OpenAPI 3.0.3 del microservicio de usuarios.

Se describe cada ruta de forma compacta y library_common.openapi se
encarga de lo comun a los seis servicios: el esquema Bearer, la
negociacion ?format=, la paginacion y las respuestas de error.
"""
from . import config
from library_common.openapi import build

USER_SCHEMA = {
    "type": "object",
    "properties": {
        "id": {"type": "integer", "example": 7},
        "nombre": {"type": "string", "example": "Ada"},
        "apellidoPaterno": {"type": "string", "example": "Lovelace"},
        "apellidoMaterno": {"type": "string", "nullable": True, "example": "Byron"},
        "fullName": {"type": "string", "example": "Ada Lovelace Byron"},
        "email": {"type": "string", "format": "email"},
        "role": {"type": "string", "enum": ["admin", "staff", "user"]},
        "roleId": {"type": "integer", "example": 2},
        "emailVerified": {"type": "boolean"},
        "isActive": {"type": "boolean"},
        "createdAt": {"type": "string", "format": "date-time"},
        "lastLoginAt": {"type": "string", "format": "date-time", "nullable": True},
    },
    "description": "Nunca incluye password_hash.",
}

ROLE_SCHEMA = {
    "type": "object",
    "properties": {
        "id": {"type": "integer", "example": 3},
        "name": {"type": "string", "example": "staff"},
        "description": {"type": "string"},
        "isAdmin": {"type": "boolean"},
        "permissions": {"type": "array", "items": {"type": "string"},
                        "example": ["books:write", "orders:write"]},
        "userCount": {"type": "integer"},
    },
}

CREATE_BODY = {
    "type": "object",
    "required": ["nombre", "apellidoPaterno", "email", "password"],
    "properties": {
        "nombre": {"type": "string"},
        "apellidoPaterno": {"type": "string"},
        "apellidoMaterno": {"type": "string"},
        "email": {"type": "string", "format": "email"},
        "password": {"type": "string", "minLength": 6,
                     "description": "Se guarda solo su hash bcrypt."},
        "roleId": {"type": "integer", "default": 2,
                   "description": "O 'role' con el nombre del rol."},
        "emailVerified": {"type": "boolean", "default": False},
        "isActive": {"type": "boolean", "default": True},
    },
}

ID_PARAM = [{"name": "id", "in": "path", "required": True,
             "schema": {"type": "integer"}, "description": "Id de la cuenta."}]

API = config.API_PREFIX


def build_spec():
    return build(
        service=config.SERVICE_NAME,
        title="Libreria en Linea — Microservicio de usuarios",
        description=(
            "Administra cuentas, roles, correos y contrasenas de `library_db` "
            "(esquema `library`).\n\n"
            "**Aqui ninguna lectura es publica.** Una lista de cuentas con sus "
            "correos es informacion personal: el propio usuario puede ver y "
            "editar lo suyo con su token, y para operar sobre cuentas ajenas "
            "hacen falta los permisos `users:read` / `users:write` / "
            "`users:roles`.\n\n"
            "**Efecto en Redis.** Cambiar el rol, la contrasena o el correo, y "
            "desactivar una cuenta, CIERRAN todas las sesiones de ese usuario y "
            "REVOCAN sus tokens en el acto (`user:sessions:<id>` -> "
            "`jwt:revoked:<jti>`). Sin eso, un usuario degradado seguiria "
            "operando con su rol anterior hasta 30 minutos."),
        version=config.XML_VERSION,
        namespace=config.XML_NAMESPACE,
        port=config.PORT,
        tags=["Servicio", "Usuarios", "Credenciales", "Roles"],
        extra_schemas={"User": USER_SCHEMA, "Role": ROLE_SCHEMA},
        paths=[
            {"path": "/", "method": "get", "tag": "Servicio",
             "summary": "Indice del servicio",
             "description": "Endpoints, formatos y vocabulario de permisos.",
             "auth": None, "success": (200, "Indice", {"type": "object"})},
            {"path": "/health", "method": "get", "tag": "Servicio",
             "summary": "Estado del servicio",
             "description": "Estado de PostgreSQL y de Redis. Devuelve 503 si "
                            "cualquiera de los dos falla: sin Redis este "
                            "servicio no puede comprobar la revocacion de "
                            "tokens y rechaza toda peticion autenticada.",
             "auth": None,
             "success": (200, "Servicio sano", {"type": "object"}),
             "errors": ["Unavailable"]},
            {"path": "/metrics", "method": "get", "tag": "Servicio",
             "summary": "Metricas del proceso",
             "description": "Contadores agregados y estado del servidor Redis. "
                            "No contiene datos de ningun usuario.",
             "auth": None, "success": (200, "Metricas", {"type": "object"})},

            {"path": f"{API}/users", "method": "get", "tag": "Usuarios",
             "summary": "Listado de cuentas",
             "description": "Lectura administrativa con filtros, orden y "
                            "paginacion. No se cachea en Redis: son datos "
                            "personales y cambian con cada alta.",
             "auth": "users:read", "paginated": True,
             "params": [
                 {"name": "q", "in": "query", "schema": {"type": "string"},
                  "description": "Busca en el nombre completo y en el correo."},
                 {"name": "email", "in": "query", "schema": {"type": "string"}},
                 {"name": "role", "in": "query", "schema": {"type": "string"},
                  "description": "Nombre del rol o su id."},
                 {"name": "active", "in": "query", "schema": {"type": "boolean"}},
                 {"name": "verified", "in": "query", "schema": {"type": "boolean"}},
                 {"name": "sort", "in": "query",
                  "schema": {"type": "string",
                             "enum": ["id", "email", "name", "role", "created", "lastLogin"]}},
                 {"name": "order", "in": "query",
                  "schema": {"type": "string", "enum": ["asc", "desc"]}},
             ],
             "success": (200, "Cuentas que cumplen los filtros",
                         {"type": "object",
                          "properties": {"total": {"type": "integer"},
                                         "users": {"type": "array",
                                                   "items": USER_SCHEMA}}}),
             "errors": ["BadRequest", "Unauthorized", "Forbidden", "Unavailable"]},

            {"path": f"{API}/users/{{id}}", "method": "get", "tag": "Usuarios",
             "summary": "Una cuenta",
             "description": "La PROPIA cuenta siempre; las de otros con "
                            "`users:read`.",
             "auth": True, "params": ID_PARAM,
             "success": (200, "La cuenta", USER_SCHEMA),
             "errors": ["Unauthorized", "Forbidden", "NotFound", "Unavailable"]},

            {"path": f"{API}/users", "method": "post", "tag": "Usuarios",
             "summary": "Alta administrativa de cuenta",
             "description": "A diferencia de POST /register del microservicio "
                            "de login, aqui se puede fijar el rol y marcar el "
                            "correo como verificado.",
             "auth": "users:write", "body": CREATE_BODY,
             "success": (201, "Cuenta creada", USER_SCHEMA),
             "errors": ["BadRequest", "Unauthorized", "Forbidden", "Conflict",
                        "Unavailable"]},

            {"path": f"{API}/users/{{id}}", "method": "put", "tag": "Usuarios",
             "summary": "Reemplazo completo",
             "description": "El cuerpo describe todos los campos editables; lo "
                            "que se omite se vacia. La contrasena es la "
                            "excepcion: si no viene, se conserva.",
             "auth": "users:write", "params": ID_PARAM, "body": CREATE_BODY,
             "success": (200, "Cuenta reemplazada", USER_SCHEMA),
             "errors": ["BadRequest", "Unauthorized", "Forbidden", "NotFound",
                        "Conflict", "Unavailable"]},

            {"path": f"{API}/users/{{id}}", "method": "patch", "tag": "Usuarios",
             "summary": "Cambio parcial",
             "description": "Solo los nombres. El rol, la contrasena y el "
                            "correo tienen su propio endpoint porque cada uno "
                            "tiene consecuencias distintas sobre las sesiones.",
             "auth": True, "params": ID_PARAM,
             "body": {"type": "object",
                      "properties": {"nombre": {"type": "string"},
                                     "apellidoPaterno": {"type": "string"},
                                     "apellidoMaterno": {"type": "string"},
                                     "isActive": {"type": "boolean",
                                                  "description": "Requiere users:write."},
                                     "emailVerified": {"type": "boolean",
                                                       "description": "Requiere users:write."}}},
             "success": (200, "Cuenta actualizada", USER_SCHEMA),
             "errors": ["BadRequest", "Unauthorized", "Forbidden", "NotFound",
                        "Unavailable"]},

            {"path": f"{API}/users/{{id}}", "method": "delete", "tag": "Usuarios",
             "summary": "Baja logica de la cuenta",
             "description": "Pone `is_active = false` y cierra sus sesiones. NO "
                            "borra la fila: `library.orders` la referencia con "
                            "ON DELETE RESTRICT y un pedido historico no puede "
                            "quedarse sin dueno. Tampoco permite dejar el "
                            "sistema sin ningun administrador activo (409).",
             "auth": "users:write", "params": ID_PARAM,
             "success": (200, "Cuenta desactivada", {"type": "object"}),
             "errors": ["Unauthorized", "Forbidden", "NotFound", "Conflict",
                        "Unavailable"]},

            {"path": f"{API}/users/{{id}}/password", "method": "patch",
             "tag": "Credenciales", "summary": "Cambiar contrasena",
             "description": "Si es la PROPIA cuenta hay que enviar "
                            "`currentPassword`: tener el token no basta, porque "
                            "un token robado no debe permitir apropiarse de la "
                            "cuenta. Un rol con `users:write` puede "
                            "restablecerla sin conocer la anterior. En ambos "
                            "casos se cierran TODAS las sesiones del usuario.",
             "auth": True, "params": ID_PARAM,
             "body": {"type": "object", "required": ["password"],
                      "properties": {
                          "password": {"type": "string", "minLength": 6},
                          "currentPassword": {"type": "string",
                                              "description": "Obligatoria si es su propia cuenta."}}},
             "success": (200, "Contrasena cambiada", {"type": "object"}),
             "errors": ["BadRequest", "Unauthorized", "Forbidden", "NotFound",
                        "Unavailable"]},

            {"path": f"{API}/users/{{id}}/email", "method": "patch",
             "tag": "Credenciales", "summary": "Cambiar correo",
             "description": "El correo nuevo queda SIN VERIFICAR, porque el "
                            "microservicio de login exige correo verificado "
                            "para iniciar sesion: la propiedad del correo nuevo "
                            "hay que demostrarla. Un rol con `users:write` "
                            "puede marcarlo verificado con "
                            "`{\"verified\": true}`.",
             "auth": True, "params": ID_PARAM,
             "body": {"type": "object", "required": ["email"],
                      "properties": {"email": {"type": "string", "format": "email"},
                                     "verified": {"type": "boolean",
                                                  "description": "Requiere users:write."}}},
             "success": (200, "Correo cambiado", USER_SCHEMA),
             "errors": ["BadRequest", "Unauthorized", "Forbidden", "NotFound",
                        "Conflict", "Unavailable"]},

            {"path": f"{API}/users/{{id}}/role", "method": "put", "tag": "Roles",
             "summary": "Cambiar el rol de una cuenta",
             "description": "Altera lo que ese usuario puede hacer en los SEIS "
                            "microservicios. Revoca todas sus sesiones (sus "
                            "tokens llevan el `role_id` anterior firmado "
                            "dentro) e invalida `roles:perms:<role_id>` en "
                            "Redis. No permite dejar al sistema sin ningun "
                            "administrador activo (409).",
             "auth": "users:roles", "params": ID_PARAM,
             "body": {"type": "object",
                      "properties": {"roleId": {"type": "integer"},
                                     "role": {"type": "string",
                                              "description": "Alternativa a roleId."}}},
             "success": (200, "Rol cambiado", USER_SCHEMA),
             "errors": ["BadRequest", "Unauthorized", "Forbidden", "NotFound",
                        "Conflict", "Unavailable"]},

            {"path": f"{API}/roles", "method": "get", "tag": "Roles",
             "summary": "Catalogo de roles y permisos",
             "description": "Cada rol con su lista de permisos y cuantas "
                            "cuentas lo tienen. Incluye el vocabulario completo "
                            "de permisos del sistema.",
             "auth": "users:read",
             "success": (200, "Roles", {"type": "object",
                                        "properties": {"roles": {"type": "array",
                                                                 "items": ROLE_SCHEMA}}}),
             "errors": ["Unauthorized", "Forbidden", "Unavailable"]},

            {"path": f"{API}/roles/{{id}}", "method": "get", "tag": "Roles",
             "summary": "Un rol", "auth": "users:read",
             "params": [{"name": "id", "in": "path", "required": True,
                         "schema": {"type": "integer"}}],
             "success": (200, "El rol", ROLE_SCHEMA),
             "errors": ["Unauthorized", "Forbidden", "NotFound", "Unavailable"]},

            {"path": f"{API}/roles", "method": "post", "tag": "Roles",
             "summary": "Crear un rol",
             "description": "El nombre va en minusculas y sin espacios. Ojo: "
                            "`library.users.role` sigue siendo un ENUM por "
                            "compatibilidad con el monolito, de modo que un rol "
                            "cuyo nombre no sea etiqueta del ENUM funciona por "
                            "`role_id` pero no se refleja en esa columna.",
             "auth": "users:roles",
             "body": {"type": "object", "required": ["name"],
                      "properties": {"name": {"type": "string", "example": "almacen"},
                                     "description": {"type": "string"},
                                     "isAdmin": {"type": "boolean"},
                                     "permissions": {"type": "array",
                                                     "items": {"type": "string"}}}},
             "success": (201, "Rol creado", ROLE_SCHEMA),
             "errors": ["BadRequest", "Unauthorized", "Forbidden", "Conflict",
                        "Unavailable"]},

            {"path": f"{API}/roles/{{id}}/permissions", "method": "put",
             "tag": "Roles", "summary": "Fijar los permisos de un rol",
             "description": "Reemplaza la lista COMPLETA (no anade). Tras "
                            "escribirla invalida `roles:perms:<id>` en Redis, de "
                            "modo que los seis microservicios ven el cambio en "
                            "la peticion siguiente y no cuando caduque el "
                            "cache. Al rol `admin` no se le puede quitar `*`.",
             "auth": "users:roles",
             "params": [{"name": "id", "in": "path", "required": True,
                         "schema": {"type": "integer"}}],
             "body": {"type": "object", "required": ["permissions"],
                      "properties": {"permissions": {
                          "type": "array", "items": {"type": "string"},
                          "example": ["books:write", "orders:read", "orders:status"]}}},
             "success": (200, "Permisos fijados", ROLE_SCHEMA),
             "errors": ["BadRequest", "Unauthorized", "Forbidden", "NotFound",
                        "Conflict", "Unavailable"]},
        ])
