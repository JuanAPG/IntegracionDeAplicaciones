"""
apps/services/users/users/app.py
Microservicio Flask de USUARIOS: cuentas, roles, correos y contrasenas
(library_db / esquema library).

Restricciones de la practica
  * Flask SIN blueprints: todas las rutas se registran con @app.get /
    @app.post sobre la unica instancia `app` de este archivo.
  * Psycopg 3; credenciales solo por variables de entorno.
  * Respuestas en XML y JSON (?format=xml | ?format=json). Sin
    parametro, XML, como el resto del proyecto.
  * CORS enumerando los origenes de las aplicaciones cliente.

AUTORIZACION
  Escrituras (POST/PUT/PATCH/DELETE): SIEMPRE Authorization: Bearer <JWT>.
  Lecturas: aqui NO hay lecturas publicas. Una lista de cuentas con sus
  correos es informacion personal, de modo que incluso los GET exigen
  token: el propio usuario puede ver su cuenta, y para ver las de otros
  hace falta el permiso users:read.

      401  token ausente, invalido, caducado o revocado
      403  token valido pero el rol no tiene el permiso necesario
      503  Redis o PostgreSQL caidos

PERMISOS QUE USA (library.role_permissions)
      users:read    ver cuentas ajenas y el catalogo de roles
      users:write   crear, modificar y desactivar cuentas
      users:roles   cambiar el rol de una cuenta y editar los permisos
                    de un rol

EFECTO EN REDIS
  Cambiar el rol, la contrasena o desactivar una cuenta REVOCA todas las
  sesiones y tokens de ese usuario en el acto (user:sessions:<id> ->
  jwt:revoked:<jti>). Sin eso, un usuario degradado seguiria operando
  con su rol anterior hasta 30 minutos.
"""
import logging

from flasgger import Swagger
from flask import Flask, request
from werkzeug.exceptions import HTTPException

from . import _bootstrap  # noqa: F401
from . import config
from . import openapi
from . import repository as repo
from . import validators
from .security import hash_password, verify_password
from .shared import (
    database,
    negotiator,
    permission_required,
    resolver,
    store,
    token_required,
)
from library_common import logging_support, metrics
from library_common.errors import (
    Conflict,
    Forbidden,
    NotFound,
    Unauthorized,
    ValidationError,
)
from library_common.flask_support import (
    configure_cors,
    install_security_headers,
    metrics_payload,
    register_error_handlers,
    register_request_metrics,
)
from library_common.jwt_auth import current_identity
from library_common.roles import PERMISSIONS

log = logging_support.configure(
    logging.DEBUG if config.DEBUG else logging.INFO, service="users")

app = Flask(__name__)
# Mantiene el orden en que se construye el diccionario en lugar del
# alfabetico, para que el JSON se lea igual que el XML.
app.json.sort_keys = False
API = config.API_PREFIX

# Este servicio no usa cookies: la identidad viaja en el JWT, de modo que
# supports_credentials queda en False y "*" no rompe nada en desarrollo.
configure_cors(app, config.CORS_ORIGINS, with_credentials=False,
               max_age=config.CORS_MAX_AGE, service="users")
install_security_headers(app)
register_request_metrics(app, "users")

SWAGGER_CONFIG = {
    "openapi": "3.0.3",
    "uiversion": 3,
    "headers": [],
    "title": "Libreria en Linea — Microservicio de usuarios",
    "specs": [{"endpoint": "openapi", "route": "/openapi.json",
               "rule_filter": lambda rule: False,
               "model_filter": lambda tag: True}],
    "static_url_path": "/docs/static",
    "swagger_ui": True,
    "specs_route": "/docs/",
}
swagger = Swagger(app, template=openapi.build_spec(), config=SWAGGER_CONFIG, merge=False)


# =====================================================================
# Lectura del cuerpo (JSON, XML o formulario) — mismo criterio que login
# =====================================================================
def _local(tag):
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def _xml_dict(text):
    from xml.etree import ElementTree
    try:
        root = ElementTree.fromstring(text)
    except ElementTree.ParseError as exc:
        raise ValidationError("El cuerpo XML no se pudo interpretar.",
                              [str(exc).strip()]) from exc
    data = {}
    for child in root:
        if len(child):           # lista: <permissions><permission>..</permission></permissions>
            data[_local(child.tag)] = [(g.text or "").strip() for g in child]
        else:
            data[_local(child.tag)] = (child.text or "").strip()
    return data


def read_payload():
    ctype = (request.content_type or "").lower()
    if "json" in ctype:
        data = request.get_json(silent=True)
        if data is None:
            raise ValidationError("El cuerpo JSON no se pudo interpretar.")
        if not isinstance(data, dict):
            raise ValidationError("El cuerpo JSON debe ser un objeto.")
        return data
    if "xml" in ctype or (request.data or b"").lstrip().startswith(b"<"):
        return _xml_dict(request.get_data(as_text=True))
    if request.form:
        return dict(request.form)
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else {}


def _pick(data, *names, default=""):
    for name in names:
        if name in data and data[name] not in (None, ""):
            value = data[name]
            return value.strip() if isinstance(value, str) else value
        lowered = name.lower()
        for key, value in data.items():
            if str(key).lower() == lowered and value not in (None, ""):
                return value.strip() if isinstance(value, str) else value
    return default


def _pagination():
    def positive(name, default, maximum=None):
        raw = request.args.get(name)
        if raw in (None, ""):
            return default
        try:
            value = int(raw)
        except ValueError:
            raise ValidationError(f"El parametro '{name}' debe ser un entero.")
        if value < 0:
            raise ValidationError(f"El parametro '{name}' no puede ser negativo.")
        return min(value, maximum) if maximum else value

    limit = positive("limit", config.DEFAULT_LIMIT, config.MAX_LIMIT)
    return max(limit, 1), positive("offset", 0)


# =====================================================================
# Autorizacion de grano fino
# =====================================================================
def _require_self_or(permission, user_id):
    """
    Deja pasar si la peticion es sobre la PROPIA cuenta, o si el rol
    tiene el permiso indicado. Es el patron que evita que un cliente
    necesite permisos administrativos para ver o editar lo suyo.
    """
    identity = current_identity()
    if identity is None:                       # el decorador ya lo garantiza
        raise Unauthorized("Se requiere un token valido.")
    if identity.is_self(user_id) or identity.has(permission):
        return identity
    metrics.incr("authz.denied")
    raise Forbidden(
        "Solo puede operar sobre su propia cuenta.",
        [f"Para operar sobre otras cuentas hace falta el permiso '{permission}'.",
         f"Rol actual: {identity.role or identity.role_id}."])


def _revoke_sessions(user_id, reason):
    """
    Cierra las sesiones del usuario y revoca sus tokens.

    Se llama tras cambiar rol, contrasena, correo o estado. Si Redis no
    responde, strict_* lanza 503 y la operacion COMPLETA se rechaza: no
    se cambia un rol sin poder retirar el token que llevaba el rol
    anterior.
    """
    closed = store.revoke_user_sessions(user_id, config.JWT_ACCESS_TTL, reason=reason)
    log.info("user_id=%s: %s sesion(es) cerradas por %s", user_id, closed, reason)
    return closed


# =====================================================================
# Rutas: servicio
# =====================================================================
@app.get("/")
def index():
    payload = {
        "service": config.SERVICE_NAME,
        "description": "Microservicio Flask de usuarios, roles, correos y "
                       "contrasenas de library_db (esquema library).",
        "version": config.XML_VERSION,
        "formats": ["application/xml", "application/json"],
        "defaultFormat": config.DEFAULT_FORMAT,
        "xmlNamespace": config.XML_NAMESPACE,
        "documentation": {"swaggerUi": "/docs", "openapi": "/openapi.json"},
        "authentication": {
            "scheme": "Bearer",
            "issuer": config.JWT_ISSUER,
            "note": "Aqui NINGUNA lectura es publica: una lista de cuentas con "
                    "sus correos es informacion personal.",
        },
        "permissions": list(PERMISSIONS),
        "endpoints": [
            {"method": "GET", "path": f"{API}/users", "description": "Listado de cuentas (users:read)"},
            {"method": "GET", "path": f"{API}/users/<id>", "description": "Una cuenta (propia, o users:read)"},
            {"method": "POST", "path": f"{API}/users", "description": "Alta de cuenta (users:write)"},
            {"method": "PUT", "path": f"{API}/users/<id>", "description": "Reemplazo completo (users:write)"},
            {"method": "PATCH", "path": f"{API}/users/<id>", "description": "Cambio parcial (propia, o users:write)"},
            {"method": "DELETE", "path": f"{API}/users/<id>", "description": "Baja logica (users:write)"},
            {"method": "PATCH", "path": f"{API}/users/<id>/password", "description": "Cambiar contrasena (propia, o users:write)"},
            {"method": "PATCH", "path": f"{API}/users/<id>/email", "description": "Cambiar correo (propia, o users:write)"},
            {"method": "PUT", "path": f"{API}/users/<id>/role", "description": "Cambiar rol (users:roles)"},
            {"method": "GET", "path": f"{API}/roles", "description": "Catalogo de roles y permisos (users:read)"},
            {"method": "POST", "path": f"{API}/roles", "description": "Crear rol (users:roles)"},
            {"method": "PUT", "path": f"{API}/roles/<id>/permissions", "description": "Fijar permisos del rol (users:roles)"},
            {"method": "GET", "path": "/health", "description": "Estado del servicio, PostgreSQL y Redis"},
            {"method": "GET", "path": "/metrics", "description": "Contadores del proceso y estado de Redis"},
        ],
    }
    return negotiator.dict_response("service", payload)


@app.get("/health")
def health():
    """
    Estado del servicio y de sus dependencias.

    PostgreSQL caido -> 503: sin base no hay cuentas.
    Redis caido -> 503 tambien: sin poder consultar la revocacion, este
    servicio no acepta ningun token, de modo que no puede hacer nada
    util. Mejor decirlo que fingir que esta sano.
    """
    warnings = config.warnings()
    redis_block = store.health()
    redis_ok = redis_block.get("status") == "ok"
    db_ok, db_block = database.health()

    payload = dict(db_block)
    payload["redis"] = redis_block
    payload["jwt"] = "ok" if config.jwt_configured() else "missing_secret"
    if db_ok and redis_ok:
        payload["status"] = "ok"
        status = 200
    else:
        payload["status"] = "error" if not db_ok else "degraded"
        status = 503
        if not redis_ok and config.redis_configured():
            warnings.append("Redis no responde: no se puede comprobar la "
                            "revocacion de tokens, de modo que el servicio "
                            "rechazara toda peticion autenticada (fallo seguro).")
    if warnings:
        payload["warnings"] = warnings
    return negotiator.dict_response("health", payload, status=status)


@app.get("/metrics")
def service_metrics():
    """Contadores del proceso y estado del servidor Redis. Sin datos personales."""
    payload = metrics_payload(config.SERVICE_NAME, store)
    return negotiator.dict_response("metrics", payload)


# =====================================================================
# Rutas: cuentas
# =====================================================================
@app.get(f"{API}/users")
@permission_required("users:read")
def list_users():
    """
    Listado de cuentas con filtros, orden y paginacion.

    Lectura ADMINISTRATIVA: exige users:read. No se cachea en Redis a
    proposito —son datos personales y cambian con cada alta—, y ninguna
    respuesta incluye password_hash.
    """
    limit, offset = _pagination()
    filters = {}
    for name in ("q", "email", "role"):
        if request.args.get(name):
            filters[name] = request.args[name].strip()
    for name in ("active", "verified"):
        if request.args.get(name) not in (None, ""):
            try:
                filters[name] = validators.as_bool(request.args[name], name)
            except ValueError as exc:
                raise ValidationError(str(exc)) from exc

    rows, total = repo.list_users(filters, sort=request.args.get("sort", "id"),
                                  order=request.args.get("order", "asc"),
                                  limit=limit, offset=offset)
    users = [repo.public_user(row) for row in rows]
    payload = {"count": len(users), "total": total, "limit": limit,
               "offset": offset, "filters": filters, "users": users}
    return negotiator.collection_response(
        "users", "user", users, payload,
        total=total, limit=limit, offset=offset,
        headers={"X-Total-Count": str(total)})


@app.get(f"{API}/users/<int:user_id>")
@token_required
def get_user(user_id):
    """Una cuenta. La propia siempre; las de otros con users:read."""
    _require_self_or("users:read", user_id)
    row = repo.get_by_id(user_id)
    if row is None:
        raise NotFound(f"No existe la cuenta {user_id}.")
    return negotiator.dict_response("user", repo.public_user(row))


@app.post(f"{API}/users")
@permission_required("users:write")
def create_user():
    """
    Alta administrativa de una cuenta.

    A diferencia del /register del microservicio de login, aqui se puede
    fijar el rol y marcar el correo como verificado: lo hace un
    administrador, no el propio interesado.
    """
    data = read_payload()
    errors = []
    try:
        first = validators.validate_name(
            _pick(data, "nombre", "firstName", "first_name", "name"), "nombre")
    except ValueError as exc:
        errors.append(str(exc)); first = ""
    try:
        paternal = validators.validate_name(
            _pick(data, "apellidoPaterno", "apellido_paterno", "lastNamePaternal"),
            "apellido paterno")
    except ValueError as exc:
        errors.append(str(exc)); paternal = ""
    try:
        maternal = validators.validate_name(
            _pick(data, "apellidoMaterno", "apellido_materno", "lastNameMaternal"),
            "apellido materno", required=False)
    except ValueError as exc:
        errors.append(str(exc)); maternal = ""
    try:
        email = validators.normalize_email(_pick(data, "email", "correo"))
    except ValueError as exc:
        errors.append(str(exc)); email = ""
    try:
        password = validators.validate_password(_pick(data, "password", "contrasena"))
    except ValueError as exc:
        errors.append(str(exc)); password = ""
    if errors:
        raise ValidationError("El alta tiene campos invalidos.", errors)

    role_id = _resolve_role(data, default=2)
    verified = _optional_bool(data, "emailVerified", "email_verified", default=False)
    active = _optional_bool(data, "isActive", "is_active", default=True)

    if repo.email_taken(email):
        raise Conflict("Ese correo ya esta registrado.",
                       ["Use PATCH /users/<id>/email si quiere reasignarlo."])

    full_name = validators.compose_full_name(first, paternal, maternal)
    try:
        row = repo.create_user(first=first, paternal=paternal, maternal=maternal,
                               full_name=full_name, email=email,
                               password_hash=hash_password(password),
                               role_id=role_id, email_verified=verified,
                               is_active=active)
    except Exception as exc:                           # noqa: BLE001
        from library_common.db import is_unique_violation
        if is_unique_violation(exc):
            raise Conflict("Ese correo ya esta registrado.") from exc
        raise
    # Sin el correo completo en el log: basta el id para auditar.
    log.info("Cuenta creada id=%s role_id=%s por user_id=%s",
             row["id"], role_id, current_identity().user_id)
    metrics.incr("users.created")
    payload = repo.public_user(row)
    return negotiator.dict_response("user", payload, status=201,
                                    headers={"Location": f"{API}/users/{row['id']}"})


def _resolve_role(data, default=None):
    """Acepta roleId numerico o role por nombre; comprueba que exista."""
    raw_id = _pick(data, "roleId", "role_id", default=None)
    raw_name = _pick(data, "role", "rol", default=None)
    if raw_id in (None, ""):
        if raw_name in (None, ""):
            if default is None:
                raise ValidationError("Falta el rol (roleId o role).")
            return default
        role = repo.get_role_by_name(str(raw_name))
        if role is None:
            raise ValidationError(f"El rol '{raw_name}' no existe.",
                                  ["Consulte GET /roles."])
        return role["id"]
    try:
        role_id = int(raw_id)
    except (TypeError, ValueError):
        raise ValidationError("roleId debe ser un entero.")
    if repo.get_role(role_id) is None:
        raise ValidationError(f"El rol {role_id} no existe.", ["Consulte GET /roles."])
    return role_id


def _optional_bool(data, *names, default=None):
    raw = _pick(data, *names, default=None)
    if raw in (None, ""):
        return default
    try:
        return validators.as_bool(raw, names[0])
    except ValueError as exc:
        raise ValidationError(str(exc)) from exc


@app.put(f"{API}/users/<int:user_id>")
@permission_required("users:write")
def replace_user(user_id):
    """
    Reemplazo COMPLETO de la cuenta: el cuerpo describe todos sus campos
    editables, y lo que se omite se vacia (los apellidos maternos, por
    ejemplo). La contrasena es la excepcion: si no viene, se conserva,
    porque un PUT no deberia obligar a reescribir una credencial.
    """
    if repo.get_by_id(user_id) is None:
        raise NotFound(f"No existe la cuenta {user_id}.")
    data = read_payload()
    errors = []
    try:
        first = validators.validate_name(
            _pick(data, "nombre", "firstName", "first_name"), "nombre")
    except ValueError as exc:
        errors.append(str(exc)); first = ""
    try:
        paternal = validators.validate_name(
            _pick(data, "apellidoPaterno", "lastNamePaternal"), "apellido paterno")
    except ValueError as exc:
        errors.append(str(exc)); paternal = ""
    try:
        maternal = validators.validate_name(
            _pick(data, "apellidoMaterno", "lastNameMaternal"),
            "apellido materno", required=False)
    except ValueError as exc:
        errors.append(str(exc)); maternal = ""
    try:
        email = validators.normalize_email(_pick(data, "email", "correo"))
    except ValueError as exc:
        errors.append(str(exc)); email = ""
    if errors:
        raise ValidationError("El reemplazo tiene campos invalidos.", errors)

    if repo.email_taken(email, exclude_id=user_id):
        raise Conflict("Ese correo ya lo usa otra cuenta.")

    role_id = _resolve_role(data, default=None)
    changes = {
        "first": first, "paternal": paternal, "maternal": maternal or None,
        "full_name": validators.compose_full_name(first, paternal, maternal),
        "email": email, "role_id": role_id,
        "email_verified": _optional_bool(data, "emailVerified", default=False),
        "is_active": _optional_bool(data, "isActive", default=True),
    }
    password = _pick(data, "password", "contrasena", default=None)
    if password:
        try:
            changes["password_hash"] = hash_password(
                validators.validate_password(password))
        except ValueError as exc:
            raise ValidationError(str(exc)) from exc

    _guard_last_admin(user_id, role_id, changes["is_active"])
    row = repo.update_user(user_id, changes)
    # El rol, el correo o el estado cambiaron: los tokens que ya existen
    # llevan datos viejos y deben dejar de servir.
    _revoke_sessions(user_id, "PUT /users")
    resolver.invalidate(role_id)
    metrics.incr("users.replaced")
    return negotiator.dict_response("user", repo.public_user(row))


@app.patch(f"{API}/users/<int:user_id>")
@token_required
def update_user(user_id):
    """
    Cambio PARCIAL: solo se modifica lo que venga en el cuerpo.

    El propio usuario puede cambiar sus nombres. Cambiar el rol, el
    estado o la marca de verificacion del correo es administrativo y
    exige users:write (el rol, ademas, users:roles por PUT .../role).
    """
    if repo.get_by_id(user_id) is None:
        raise NotFound(f"No existe la cuenta {user_id}.")
    identity = _require_self_or("users:write", user_id)
    data = read_payload()

    changes = {}
    for key, campo, requerido in (("nombre", "first", True),
                                  ("apellidoPaterno", "paternal", True),
                                  ("apellidoMaterno", "maternal", False)):
        raw = _pick(data, key, default=None)
        if raw is None:
            continue
        try:
            changes[campo] = validators.validate_name(raw, key, required=requerido) or None
        except ValueError as exc:
            raise ValidationError(str(exc)) from exc

    administrativos = []
    for key, campo in (("isActive", "is_active"), ("emailVerified", "email_verified")):
        raw = _pick(data, key, default=None)
        if raw is None:
            continue
        if not identity.has("users:write"):
            administrativos.append(key)
            continue
        changes[campo] = _optional_bool(data, key)

    if _pick(data, "roleId", "role", default=None) is not None:
        raise ValidationError(
            "El rol no se cambia por aqui.",
            ["Use PUT /users/<id>/role, que exige el permiso users:roles."])
    if _pick(data, "password", default=None) is not None:
        raise ValidationError(
            "La contrasena no se cambia por aqui.",
            ["Use PATCH /users/<id>/password."])
    if _pick(data, "email", default=None) is not None:
        raise ValidationError(
            "El correo no se cambia por aqui.",
            ["Use PATCH /users/<id>/email, que reinicia la verificacion."])
    if administrativos:
        raise Forbidden(
            "Su rol no puede cambiar esos campos.",
            [f"Campos administrativos: {', '.join(administrativos)}.",
             "Hace falta el permiso users:write."])
    if not changes:
        raise ValidationError("No hay nada que cambiar.",
                             ["Envie al menos uno de: nombre, apellidoPaterno, "
                              "apellidoMaterno."])

    if {"first", "paternal", "maternal"} & set(changes):
        actual = repo.get_by_id(user_id)
        changes["full_name"] = validators.compose_full_name(
            changes.get("first", actual.get("first_name")) or "",
            changes.get("paternal", actual.get("last_name_paternal")) or "",
            changes.get("maternal", actual.get("last_name_maternal")) or "")

    if "is_active" in changes:
        _guard_last_admin(user_id, None, changes["is_active"])

    row = repo.update_user(user_id, changes)
    if "is_active" in changes and not changes["is_active"]:
        _revoke_sessions(user_id, "cuenta desactivada")
    metrics.incr("users.updated")
    return negotiator.dict_response("user", repo.public_user(row))


@app.delete(f"{API}/users/<int:user_id>")
@permission_required("users:write")
def deactivate_user(user_id):
    """
    BAJA LOGICA de la cuenta (is_active = false).

    No se borra la fila a proposito: library.orders referencia a
    library.users con ON DELETE RESTRICT, y un pedido historico no puede
    quedarse sin dueno. Desactivar conserva la historia y cierra el
    acceso, que es lo que de verdad se quiere.
    """
    row = repo.get_by_id(user_id)
    if row is None:
        raise NotFound(f"No existe la cuenta {user_id}.")
    if not row.get("is_active", True):
        payload = {"deactivated": True, "id": user_id, "alreadyInactive": True,
                   "sessionsClosed": 0}
        return negotiator.dict_response("user", payload)

    _guard_last_admin(user_id, None, False)
    repo.set_active(user_id, False)
    closed = _revoke_sessions(user_id, "baja de la cuenta")
    log.info("Cuenta %s desactivada por user_id=%s", user_id,
             current_identity().user_id)
    metrics.incr("users.deactivated")
    payload = {"deactivated": True, "id": user_id, "email": row["email"],
               "isActive": False, "sessionsClosed": closed,
               "note": "Baja logica: la fila se conserva porque los pedidos "
                       "historicos la referencian."}
    return negotiator.dict_response("user", payload)


def _guard_last_admin(user_id, new_role_id, new_active):
    """
    Impide quedarse sin ningun administrador activo.

    La migracion retiro el indice que permitia UN SOLO admin (hacia
    imposible administrar roles), pero quedarse con CERO deja el sistema
    sin nadie que pueda arreglarlo. Esa si es una regla que vale la pena.
    """
    row = repo.get_by_id(user_id)
    if row is None:
        return
    era_admin = (row.get("role") == "admin")
    if not era_admin:
        return
    sigue_admin = (new_role_id is None or new_role_id == row.get("role_id"))
    sigue_activo = True if new_active is None else bool(new_active)
    if sigue_admin and sigue_activo:
        return
    if repo.count_active_admins(exclude_id=user_id) == 0:
        raise Conflict(
            "Es el unico administrador activo.",
            ["Asigne el rol admin a otra cuenta antes de desactivar o "
             "degradar esta."])


# =====================================================================
# Rutas: contrasena y correo
# =====================================================================
@app.patch(f"{API}/users/<int:user_id>/password")
@token_required
def change_password(user_id):
    """
    Cambia la contrasena.

    Si es la PROPIA cuenta, hay que enviar la contrasena actual: tener el
    token no basta para poder cambiarla, porque un token robado no debe
    permitir apropiarse de la cuenta. Un administrador con users:write
    puede restablecerla sin conocer la anterior.

    En ambos casos se CIERRAN todas las sesiones del usuario: cambiar la
    contrasena tiene que expulsar a quien estuviera dentro.
    """
    if repo.get_by_id(user_id) is None:
        raise NotFound(f"No existe la cuenta {user_id}.")
    identity = _require_self_or("users:write", user_id)
    data = read_payload()

    try:
        nueva = validators.validate_password(
            _pick(data, "password", "newPassword", "nuevaContrasena"))
    except ValueError as exc:
        raise ValidationError(str(exc)) from exc

    es_propia = identity.is_self(user_id)
    if es_propia:
        actual = _pick(data, "currentPassword", "contrasenaActual", "oldPassword")
        if not actual:
            raise ValidationError(
                "Falta la contrasena actual.",
                ["Para cambiar su propia contrasena debe enviar "
                 "currentPassword."])
        fila = repo.get_credentials(user_id)
        if not verify_password(actual, (fila or {}).get("password_hash") or ""):
            metrics.incr("users.password.rejected")
            raise Unauthorized("La contrasena actual no es correcta.")

    repo.update_user(user_id, {"password_hash": hash_password(nueva)})
    closed = _revoke_sessions(user_id, "cambio de contrasena")
    metrics.incr("users.password.changed")
    # Ni la contrasena nueva ni la anterior se registran en el log.
    log.info("Contrasena cambiada para user_id=%s (propia=%s)", user_id, es_propia)
    payload = {"updated": True, "id": user_id, "field": "password",
               "sessionsClosed": closed,
               "note": "Todas las sesiones se cerraron: vuelva a iniciar sesion."}
    return negotiator.dict_response("user", payload)


@app.patch(f"{API}/users/<int:user_id>/email")
@token_required
def change_email(user_id):
    """
    Cambia el correo de la cuenta.

    El correo nuevo queda SIN VERIFICAR (email_verified = false): el
    microservicio de login exige correo verificado para iniciar sesion,
    de modo que la propiedad del correo nuevo hay que demostrarla con el
    token que llega por sendmail (POST /register o GET /verify en login).

    Un administrador con users:write puede marcarlo como verificado de
    entrada con {"verified": true}, para los casos en que el correo se
    cambia a mano por una peticion comprobada.
    """
    row = repo.get_by_id(user_id)
    if row is None:
        raise NotFound(f"No existe la cuenta {user_id}.")
    identity = _require_self_or("users:write", user_id)
    data = read_payload()

    try:
        email = validators.normalize_email(_pick(data, "email", "correo"))
    except ValueError as exc:
        raise ValidationError(str(exc)) from exc
    if email == (row.get("email") or "").lower():
        raise ValidationError("El correo nuevo es el mismo que el actual.")
    if repo.email_taken(email, exclude_id=user_id):
        raise Conflict("Ese correo ya lo usa otra cuenta.")

    verificado = False
    if _pick(data, "verified", "emailVerified", default=None) is not None:
        if not identity.has("users:write"):
            raise Forbidden("Solo un rol con users:write puede marcar un "
                            "correo como verificado.")
        verificado = _optional_bool(data, "verified", "emailVerified", default=False)

    repo.update_user(user_id, {"email": email, "email_verified": verificado})
    closed = _revoke_sessions(user_id, "cambio de correo")
    metrics.incr("users.email.changed")
    log.info("Correo cambiado para user_id=%s (verificado=%s)", user_id, verificado)
    fila = repo.get_by_id(user_id)
    payload = repo.public_user(fila)
    payload["sessionsClosed"] = closed
    if not verificado:
        payload["note"] = ("El correo quedo sin verificar: use el flujo de "
                           "verificacion del microservicio de login antes de "
                           "volver a iniciar sesion.")
    return negotiator.dict_response("user", payload)


@app.put(f"{API}/users/<int:user_id>/role")
@permission_required("users:roles")
def change_role(user_id):
    """
    Cambia el rol de una cuenta.

    Es la operacion mas delicada del servicio: altera lo que ese usuario
    puede hacer en los SEIS microservicios. Por eso:
      * exige el permiso users:roles, mas estrecho que users:write;
      * revoca todas las sesiones del usuario, porque sus tokens llevan
        el role_id anterior dentro de la firma y seguirian valiendo;
      * invalida el cache de permisos del rol en Redis.
    """
    row = repo.get_by_id(user_id)
    if row is None:
        raise NotFound(f"No existe la cuenta {user_id}.")
    data = read_payload()
    role_id = _resolve_role(data, default=None)
    anterior = row.get("role_id")

    if role_id == anterior:
        payload = {"updated": False, "id": user_id, "roleId": role_id,
                   "message": "La cuenta ya tenia ese rol."}
        return negotiator.dict_response("user", payload)

    _guard_last_admin(user_id, role_id, None)
    actualizado = repo.update_user(user_id, {"role_id": role_id})
    closed = _revoke_sessions(user_id, "cambio de rol")
    resolver.invalidate(role_id)
    resolver.invalidate(anterior)
    metrics.incr("users.role.changed")
    log.info("Rol de user_id=%s: %s -> %s (por user_id=%s)",
             user_id, anterior, role_id, current_identity().user_id)
    payload = repo.public_user(actualizado)
    payload["previousRoleId"] = anterior
    payload["sessionsClosed"] = closed
    payload["note"] = ("Las sesiones se cerraron: los tokens anteriores "
                       "llevaban el rol viejo y ya fueron revocados.")
    return negotiator.dict_response("user", payload)


# =====================================================================
# Rutas: roles y permisos
# =====================================================================
@app.get(f"{API}/roles")
@permission_required("users:read")
def list_roles():
    """Catalogo de roles con sus permisos y cuantas cuentas tiene cada uno."""
    roles = [repo.role_to_dict(row) for row in repo.list_roles()]
    payload = {"count": len(roles), "vocabulary": list(PERMISSIONS), "roles": roles}
    return negotiator.collection_response("roles", "role", roles, payload,
                                          total=len(roles))


@app.get(f"{API}/roles/<int:role_id>")
@permission_required("users:read")
def get_role(role_id):
    row = repo.get_role(role_id)
    if row is None:
        raise NotFound(f"No existe el rol {role_id}.")
    return negotiator.dict_response("role", repo.role_to_dict(row))


@app.post(f"{API}/roles")
@permission_required("users:roles")
def create_role():
    """
    Crea un rol con sus permisos.

    El nombre es minusculas sin espacios (por ejemplo 'almacen'). Ojo: la
    columna library.users.role sigue siendo un ENUM por compatibilidad
    con el monolito, de modo que un rol cuyo nombre no sea una etiqueta
    del ENUM funciona por role_id pero no se refleja en esa columna (lo
    explica data/roles_migration.sql).
    """
    data = read_payload()
    try:
        name = validators.validate_role_name(_pick(data, "name", "nombre"))
    except ValueError as exc:
        raise ValidationError(str(exc)) from exc
    if repo.get_role_by_name(name) is not None:
        raise Conflict(f"Ya existe el rol '{name}'.")

    permisos = _read_permissions(data)
    descripcion = str(_pick(data, "description", "descripcion", default=""))[:200]
    is_admin = _optional_bool(data, "isAdmin", "is_admin", default=False)

    role_id = repo.create_role(name, descripcion, is_admin)
    if permisos:
        repo.set_role_permissions(role_id, permisos)
    resolver.invalidate(role_id)
    metrics.incr("roles.created")
    log.info("Rol creado id=%s name=%s por user_id=%s", role_id, name,
             current_identity().user_id)
    return negotiator.dict_response("role", repo.role_to_dict(repo.get_role(role_id)),
                                    status=201,
                                    headers={"Location": f"{API}/roles/{role_id}"})


@app.put(f"{API}/roles/<int:role_id>/permissions")
@permission_required("users:roles")
def set_role_permissions(role_id):
    """
    Fija la lista COMPLETA de permisos del rol (reemplaza, no anade).

    Tras escribirla se invalida roles:perms:<role_id> en Redis, de modo
    que los seis microservicios ven el cambio en la siguiente peticion y
    no cuando caduque el cache.
    """
    row = repo.get_role(role_id)
    if row is None:
        raise NotFound(f"No existe el rol {role_id}.")
    data = read_payload()
    permisos = _read_permissions(data)

    if row["name"] == "admin" and "*" not in permisos:
        raise Conflict(
            "Al rol admin no se le puede quitar el comodin '*'.",
            ["Dejaria el sistema sin ningun rol capaz de administrarlo."])

    repo.set_role_permissions(role_id, permisos)
    invalidated = resolver.invalidate(role_id)
    metrics.incr("roles.permissions.changed")
    log.info("Permisos del rol %s fijados a %s por user_id=%s",
             role_id, sorted(permisos), current_identity().user_id)
    payload = repo.role_to_dict(repo.get_role(role_id))
    payload["cacheKeysInvalidated"] = invalidated
    return negotiator.dict_response("role", payload)


def _read_permissions(data):
    raw = data.get("permissions") or data.get("permisos") or []
    if isinstance(raw, str):
        raw = [p for p in raw.replace(",", " ").split() if p]
    if not isinstance(raw, (list, tuple)):
        raise ValidationError("'permissions' debe ser una lista.")
    permisos = []
    errores = []
    for item in raw:
        try:
            permiso = validators.validate_permission(item)
        except ValueError as exc:
            errores.append(str(exc))
            continue
        if permiso != "*" and permiso not in PERMISSIONS:
            errores.append(
                f"El permiso '{permiso}' no esta en el vocabulario del sistema.")
            continue
        permisos.append(permiso)
    if errores:
        raise ValidationError("Hay permisos invalidos.",
                              errores + [f"Vocabulario: {', '.join(PERMISSIONS)}."])
    return permisos


# =====================================================================
# Manejo de errores: una sola forma de responder, en XML o en JSON
# =====================================================================
register_error_handlers(app, negotiator, debug=config.DEBUG, service="users")


@app.errorhandler(HTTPException)
def handle_http_error(exc):
    code = {400: "bad_request", 404: "not_found", 405: "method_not_allowed",
            415: "unsupported_media_type"}.get(exc.code, "http_error")
    return negotiator.error_response(exc.code, code, exc.description or exc.name)


if __name__ == "__main__":
    from library_common.env import redacted

    log.info("Usuarios -> http://%s:%s%s/users", config.HOST, config.PORT, API)
    log.info("Swagger UI -> http://%s:%s/docs", config.HOST, config.PORT)
    log.info("PostgreSQL -> %s (esquema %s)", database.target, config.PGSCHEMA)
    log.info("Redis -> %s", redacted(config.REDIS_URL) or "SIN CONFIGURAR")
    log.info("CORS origins -> %s", ", ".join(config.CORS_ORIGINS))
    for item in config.warnings():
        log.warning(item)
    app.run(host=config.HOST, port=config.PORT, debug=config.DEBUG, load_dotenv=False)
