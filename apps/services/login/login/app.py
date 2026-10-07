"""
apps/services/login/login/app.py
Microservicio Flask de autenticacion y gestion basica de usuarios
(library_db / esquema library).

Restricciones de la practica:
  * Flask SIN blueprints: todas las rutas se registran sobre la misma
    instancia `app` que se crea en este archivo.
  * Psycopg 3 para PostgreSQL; credenciales solo por variables de
    entorno (.env), nunca en el codigo.
  * CORS habilitado: el servicio se consume desde clientes de otro dominio.
  * Respuestas en XML y JSON: ?format=xml | ?format=json; sin parametro,
    XML. La sesion viaja en cookie firmada de Flask.

Endpoints:
  POST /register  alta (nombre, apellido paterno/materno, email, password)
  GET  /verify    canje del token enviado por sendmail (?token=...)
  GET  /validate-email  validacion previa: sintaxis, unicidad y registro
  POST /login     verifica credenciales, abre sesion y emite los tokens
  POST /refresh   canjea el refresh token por un par nuevo (rotacion)
  POST /logout    cierra la sesion y REVOCA el token de acceso
  GET  /session   dice si hay sesion autenticada y quien es
  GET  /health    estado del servicio, de PostgreSQL y de Redis
  GET  /metrics   contadores del proceso y estado del servidor Redis

ESTE SERVICIO ES EL UNICO EMISOR DE JWT
  Firma HS256 con JWT_SECRET_KEY (el mismo secreto en los seis
  microservicios, siempre por variable de entorno). El token de acceso
  dura 30 minutos y lleva user_id, role_id, sid y jti; los demas
  servicios lo verifican y consultan jwt:revoked:<jti> en Redis antes de
  aceptarlo.

REDIS ES OBLIGATORIO PARA /login, /refresh, /logout y /session
  Son operaciones de sesion y revocacion: si Redis no responde se
  devuelve 503 en lugar de emitir una credencial que despues no se
  podria retirar. Es un fallo seguro, no una degradacion.
"""
import logging
from datetime import datetime, timezone
from xml.etree import ElementTree

from flasgger import Swagger
from flask import Flask, Response, jsonify, request, session
from flask_cors import CORS
from werkzeug.exceptions import HTTPException

from . import _bootstrap  # noqa: F401  (deja library_common importable)
from . import config
from . import db
from . import jwt_utils  # noqa: F401  (compatibilidad; el flujo usa sessions)
from . import mailer as mail_sender
from . import openapi
from . import serializers
from . import sessions as session_box
from . import tokens as token_box
from . import users_repository as repo
from . import validators
from .errors import ApiError, Conflict, EmailNotVerified, Gone, NotFound, Unauthorized, ValidationError
from .mailer import MailerError  # noqa: F401  (se documenta el 503 en openapi.py)
from .security import hash_password, verify_password
from .shared import codec, negotiator, store
from library_common import logging_support, metrics
from library_common.errors import ApiError as SharedApiError
from library_common.errors import DependencyUnavailable
from library_common.flask_support import metrics_payload
from library_common.jwt_auth import bearer_token

# El filtro de secretos se instala en el logger raiz: ni contrasenas, ni
# tokens, ni la URL de Redis con su clave acaban en los registros.
log = logging_support.configure(
    logging.DEBUG if config.DEBUG else logging.INFO, service="login")

app = Flask(__name__)
# Mantiene el orden en que se construye el diccionario en lugar del
# alfabetico, para que el JSON se lea igual que el XML.
app.json.sort_keys = False
app.secret_key = config.SECRET_KEY or "solo-desarrollo-cambieme"
app.permanent_session_lifetime = config.SESSION_LIFETIME
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=config.SESSION_COOKIE_SECURE,
)
if not config.SECRET_KEY:
    log.warning("SECRET_KEY vacio: las sesiones no son seguras; fije SECRET_KEY en login/.env")

# ---------------------------------------------------------------------
# CORS con credenciales (la sesion viaja en cookie): el navegador rechaza
# "*" combinado con credenciales, de modo que en produccion CORS_ORIGINS
# debe enumerar los dominios (ver .env.example).
# ---------------------------------------------------------------------
CORS(
    app,
    resources={r"/*": {"origins": config.CORS_ORIGINS}},
    methods=["GET", "POST", "OPTIONS"],
    # Authorization: /logout acepta el token por encabezado Bearer, no
    # solo por cookie, para que lo puedan cerrar los clientes de
    # escritorio que no guardan cookies.
    allow_headers=["Content-Type", "Accept", "Origin", "X-Requested-With",
                   "Authorization"],
    expose_headers=["Content-Type", "Content-Length", "Location"],
    supports_credentials=True,
    max_age=config.CORS_MAX_AGE,
)
if config.SHARED.cors_wildcard:
    log.warning("CORS_ORIGINS='*' con cookies de sesion: el navegador lo "
                "rechazara. Enumere los origenes de los clientes en el .env")

# Metricas por peticion (las publica GET /metrics).
@app.before_request
def _metrics_start():
    request.environ["library.started_at"] = __import__("time").perf_counter()


@app.after_request
def _metrics_end(response):
    started = request.environ.get("library.started_at")
    if started is not None:
        metrics.observe(f"http.{request.method.lower()}",
                        (__import__("time").perf_counter() - started) * 1000.0)
    metrics.incr("http.requests")
    metrics.incr(f"http.status.{response.status_code // 100}xx")
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    response.headers.setdefault("Cache-Control", "no-store")
    return response


# ---------------------------------------------------------------------
# Documentacion Swagger / OpenAPI (igual que el microservicio de libros)
# ---------------------------------------------------------------------
SWAGGER_CONFIG = {
    "openapi": "3.0.3",
    "uiversion": 3,
    "headers": [],
    "title": "Libreria en Linea — Microservicio de autenticacion",
    "specs": [{
        "endpoint": "openapi",
        "route": "/openapi.json",
        "rule_filter": lambda rule: False,
        "model_filter": lambda tag: True,
    }],
    "static_url_path": "/docs/static",
    "swagger_ui": True,
    "specs_route": "/docs/",
}

swagger = Swagger(app, template=openapi.build_spec(), config=SWAGGER_CONFIG, merge=False)


# =====================================================================
# Negociacion de contenido (?format= tiene prioridad, XML por omision)
# =====================================================================
REPRESENTATIONS = {
    "xml": True, "application/xml": True, "text/xml": True,
    "json": False, "application/json": False,
}


def wants_xml():
    for name in ("format", "output", "_format"):
        value = (request.args.get(name) or "").strip().lower()
        if value in REPRESENTATIONS:
            return REPRESENTATIONS[value]
    accept = request.headers.get("Accept", "")
    if accept and "*/*" not in accept:
        xml_pos = min((accept.find(t) for t in ("application/xml", "text/xml")
                       if t in accept), default=-1)
        json_pos = accept.find("application/json")
        if xml_pos >= 0 and (json_pos < 0 or xml_pos < json_pos):
            return True
        if json_pos >= 0:
            return False
    return config.DEFAULT_FORMAT == "xml"


def respond(payload, element, status=200, headers=None):
    """Emite el mismo recurso como XML o como JSON, segun lo pedido."""
    if wants_xml():
        response = Response(serializers.to_xml_bytes(element),
                            status=status, mimetype="application/xml")
    else:
        response = jsonify(payload)
        response.status_code = status
    for key, value in (headers or {}).items():
        response.headers[key] = value
    return response


# =====================================================================
# Lectura del cuerpo (JSON, XML o formulario)
# =====================================================================
def _local(tag):
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def _xml_dict(text):
    try:
        root = ElementTree.fromstring(text)
    except ElementTree.ParseError as exc:
        raise ValidationError("El cuerpo XML no se pudo interpretar.",
                              [str(exc).strip()]) from exc
    data = {}
    for child in root:
        data[_local(child.tag)] = (child.text or "").strip()
    if not data and root.text and root.text.strip():
        data["token"] = root.text.strip()
    return data


def read_payload():
    ctype = (request.content_type or "").lower()
    if "json" in ctype:
        data = request.get_json(silent=True)
        if data is None:
            raise ValidationError("El cuerpo JSON no se pudo interpretar.")
        if not isinstance(data, dict):
            raise ValidationError("El cuerpo JSON debe ser un objeto.")
        return {str(k): (v if not isinstance(v, str) else v) for k, v in data.items()}
    if "xml" in ctype or (request.data or b"").lstrip().startswith(b"<"):
        return _xml_dict(request.get_data(as_text=True))
    if request.form:
        return dict(request.form)
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else {}


def _pick(data, *names):
    for name in names:
        if name in data and data[name] not in (None, ""):
            value = data[name]
            return value if not isinstance(value, str) else value.strip()
        lowered = name.lower()
        for key, value in data.items():
            if str(key).lower() == lowered and value not in (None, ""):
                return value if not isinstance(value, str) else value.strip()
    return ""


def _verify_url(token):
    base = config.MAIL_VERIFY_BASE_URL or request.host_url.rstrip("/")
    return f"{base}/verify?token={token}"


def _current_sid():
    """
    El identificador de sesion, de la cookie o del token Bearer.

    La cookie ya no lleva el estado de la sesion, solo el sid; el estado
    vive en Redis (ver login/sessions.py) y por eso una sesion se puede
    cerrar del lado del servidor.
    """
    sid = session.get("sid")
    if sid:
        return sid
    # Cliente sin cookies (escritorio): el sid viaja dentro del JWT.
    token = bearer_token(required=False)
    if not token:
        return None
    try:
        return codec.decode(token).get("sid")
    except DependencyUnavailable:
        # Redis caido: no se puede saber si el token esta revocado. Se
        # responde 503 (fallo seguro), no "sin sesion".
        raise
    except (SharedApiError, Unauthorized):
        return None


def _current_user():
    """
    La cuenta de la sesion vigente, o None.

    Dos comprobaciones, no una: la sesion debe seguir viva en Redis Y la
    cuenta debe seguir existiendo y activa en PostgreSQL. Una cuenta
    desactivada deja de tener sesion en el acto.
    """
    sid = _current_sid()
    if not sid:
        return None
    record = session_box.read_session(sid)
    if not isinstance(record, dict):
        session.clear()
        return None
    try:
        row = repo.get_by_id(int(record.get("user_id")))
    except (TypeError, ValueError):
        row = None
    if row is None or not row.get("is_active", True):
        session_box.close_session(sid)
        session.clear()
        return None
    return row


# =====================================================================
# Rutas: servicio
# =====================================================================
@app.get("/")
def index():
    payload = {
        "service": "library-login-service",
        "description": "Microservicio Flask de autenticacion y usuarios "
                       "de library_db (esquema library).",
        "version": config.XML_VERSION,
        "formats": ["application/xml", "application/json"],
        "defaultFormat": "xml",
        "xmlNamespace": config.XML_NAMESPACE,
        "documentation": {"swaggerUi": "/docs", "openapi": "/openapi.json"},
        "endpoints": [
            {"method": "POST", "path": "/register", "description": "Registrar un nuevo usuario"},
            {"method": "GET", "path": "/verify", "description": "Verificar el correo con el token del sendmail"},
            {"method": "GET", "path": "/validate-email", "description": "Validacion previa del correo"},
            {"method": "POST", "path": "/login", "description": "Autenticar, abrir sesion y emitir los tokens"},
            {"method": "POST", "path": "/refresh", "description": "Canjear el refresh token por un par nuevo (rotacion)"},
            {"method": "POST", "path": "/logout", "description": "Cerrar la sesion y revocar el token de acceso"},
            {"method": "GET", "path": "/session", "description": "Consultar la sesion autenticada"},
            {"method": "GET", "path": "/health", "description": "Estado del servicio, de PostgreSQL y de Redis"},
            {"method": "GET", "path": "/metrics", "description": "Contadores del proceso y estado de Redis"},
            {"method": "GET", "path": "/docs", "description": "Documentacion interactiva (Swagger UI)"},
        ],
    }
    return respond(payload, serializers.dict_element("service", payload))


@app.get("/health")
def health():
    """
    Estado del servicio y de sus dos dependencias.

    PostgreSQL y Redis son AMBOS indispensables aqui: sin base no hay
    credenciales que verificar y sin Redis no hay sesion ni revocacion.
    Por eso cualquiera de los dos caido devuelve 503 y los semaforos de
    las aplicaciones de escritorio lo pintan en rojo.
    """
    warnings = config.warnings()
    redis_block = store.health()
    redis_ok = redis_block.get("status") == "ok"
    try:
        info = db.ping()
        payload = {"status": "ok" if redis_ok else "degraded",
                   "database": info["db"], "user": info["usr"],
                   "schema": config.PGSCHEMA,
                   "server": info["version"].split(" on ")[0],
                   "sessionSigning": "ok" if config.SECRET_KEY else "missing_secret",
                   "jwt": "ok" if config.jwt_configured() else "missing_secret",
                   "jwtAccessTtl": config.JWT_ACCESS_TTL,
                   "jwtRefreshTtl": config.JWT_REFRESH_TTL,
                   "redis": redis_block,
                   "mailer": f"{config.SMTP_HOST}:{config.SMTP_PORT}"}
        status = 200 if redis_ok else 503
        if not redis_ok:
            warnings.append("Redis no responde: /login, /refresh, /logout y "
                            "/session devolveran 503 (fallo seguro).")
    except Exception as exc:                       # noqa: BLE001 - se reporta al cliente
        payload = {"status": "error", "database": config.PGDATABASE,
                   "message": str(exc).strip(), "redis": redis_block}
        status = 503
    if warnings:
        payload["warnings"] = warnings
    return respond(payload, serializers.dict_element("health", payload), status=status)


@app.get("/metrics")
def service_metrics():
    """
    Contadores del proceso y estado del servidor Redis compartido.

    No lleva datos de ningun usuario: solo agregados (peticiones por
    codigo, aciertos y fallos de cache, tokens emitidos, rechazados y
    revocados, latencias). Con gunicorn --workers N los contadores son
    del trabajador que atendio la peticion; el bloque "redis" si es
    global, porque viene del servidor.
    """
    payload = metrics_payload("library-login-service", store, {
        "jwtAccessTtl": config.JWT_ACCESS_TTL,
        "jwtRefreshTtl": config.JWT_REFRESH_TTL,
        "sessionTtl": config.SESSION_TTL,
    })
    return respond(payload, serializers.dict_element("metrics", payload))


# =====================================================================
# Rutas: registro y verificacion del correo
# =====================================================================
@app.get("/validate-email")
def validate_email():
    """Validacion previa: sintaxis, unicidad y registro interno."""
    raw = (request.args.get("email") or "").strip()
    try:
        email = validators.normalize_email(raw)
    except ValueError as exc:
        payload = {"email": raw, "valid": False, "available": False,
                   "registered": False, "verified": False,
                   "previouslyVerified": False, "reason": str(exc)}
        return respond(payload, serializers.dict_element("validation", payload))
    state = repo.verification_status(email)
    payload = {"email": email, "valid": True,
               "available": not state["registered"],
               "registered": state["registered"],
               "verified": state["verified"],
               "previouslyVerified": state["previouslyVerified"]}
    return respond(payload, serializers.dict_element("validation", payload))


@app.post("/register")
def register():
    """Alta de usuario: valida, guarda solo el hash y envia el token por sendmail."""
    data = read_payload()
    errors = []
    try:
        first = validators.validate_name(
            _pick(data, "nombre", "firstName", "first_name", "name"), "nombre")
    except ValueError as exc:
        errors.append(str(exc))
        first = ""
    try:
        paternal = validators.validate_name(
            _pick(data, "apellidoPaterno", "apellido_paterno",
                  "lastNamePaternal", "paternalSurname"), "apellido paterno")
    except ValueError as exc:
        errors.append(str(exc))
        paternal = ""
    try:
        maternal = validators.validate_name(
            _pick(data, "apellidoMaterno", "apellido_materno",
                  "lastNameMaternal", "maternalSurname"), "apellido materno",
            required=False)
    except ValueError as exc:
        errors.append(str(exc))
        maternal = ""
    try:
        email = validators.normalize_email(_pick(data, "email", "correo", "e-mail"))
    except ValueError as exc:
        errors.append(str(exc))
        email = ""
    try:
        password = validators.validate_password(_pick(data, "password", "contrasena"))
    except ValueError as exc:
        errors.append(str(exc))
        password = ""
    if errors:
        raise ValidationError("El registro tiene campos invalidos.", errors)

    if repo.email_taken(email):
        state = repo.verification_status(email)
        raise Conflict(
            "Ese correo ya esta registrado.",
            ["Use /login si es su cuenta."
             if state["verified"]
             else "La cuenta existe pero el correo sigue sin verificarse: "
                  "revise su buzon o solicite un nuevo registro cuando expire el token."])

    full_name = validators.compose_full_name(first, paternal, maternal)
    try:
        user = repo.create_user(first, paternal, maternal, full_name, email,
                                hash_password(password))
    except Exception as exc:  # noqa: BLE001 - carrera contra el UNIQUE de email
        if "unique" in str(exc).lower() or "duplicate" in str(exc).lower():
            raise Conflict("Ese correo ya esta registrado.",
                           ["Use /login si es su cuenta."]) from exc
        raise

    raw_token, digest, expires_at = token_box.issue_token()
    repo.create_verification_token(user["id"], digest, expires_at)

    verify_url = _verify_url(raw_token)
    try:
        mail_sender.send_verification_email(email, full_name, verify_url)
        sent, warning = True, None
    except MailerError as exc:
        log.error("Registro %s creado pero el correo no salio: %s", email, exc.message)
        sent, warning = False, exc.message

    payload = {"created": True, "user": repo.public_user(user),
               "emailVerification": {"required": True, "sent": sent,
                                     "expiresAt": expires_at.isoformat(),
                                     "verifyUrl": verify_url if not sent else None,
                                     "warning": warning}}
    element = serializers.dict_element("registration", {
        "created": True, "user": repo.public_user(user),
        "emailVerification": {"required": True, "sent": sent,
                              "expiresAt": expires_at.isoformat()}})
    return respond(payload, element, status=201)


@app.get("/verify")
@app.post("/verify")
def verify():
    """Canjea el token del correo y marca el email como verificado."""
    data = read_payload() if request.method == "POST" else {}
    raw = (request.args.get("token") or _pick(data, "token") or "").strip()
    if not raw:
        raise ValidationError("Falta el token de verificacion (parametro ?token=).")
    user = repo.consume_verification_token(token_box.hash_token(raw))
    if user is not None:
        payload = {"verified": True, "user": repo.public_user(user)}
        return respond(payload, serializers.dict_element("verification", payload))
    state = repo.token_state(token_box.hash_token(raw))
    if state is None:
        raise NotFound("El token no existe o ya fue reemplazado por uno nuevo.")
    if state["used_at"] is not None:
        raise Gone("Ese token ya fue utilizado; el correo quedo verificado.")
    raise Gone("Ese token expiro; registre de nuevo para recibir otro.")


# =====================================================================
# Rutas: sesion Flask
# =====================================================================
@app.post("/login")
def login():
    """Verifica las credenciales contra PostgreSQL y abre la sesion."""
    data = read_payload()
    try:
        email = validators.normalize_email(_pick(data, "email", "correo", "e-mail"))
    except ValueError as exc:
        raise ValidationError(str(exc)) from exc
    password = _pick(data, "password", "contrasena")
    if not password:
        raise ValidationError("La contrasena es obligatoria.")

    row = repo.get_by_email(email)
    if row is None or not verify_password(password, row.get("password_hash") or ""):
        raise Unauthorized("Credenciales invalidas.")
    if not row.get("is_active", True):
        raise Unauthorized("La cuenta esta desactivada.")
    if not row.get("email_verified"):
        raise EmailNotVerified(
            "El correo aun no esta verificado.",
            ["Abra el enlace que se envio por correo (GET /verify?token=...)."])

    # La sesion y el refresh token viven en Redis; el token de acceso
    # (30 min) lo firma este servicio. Si Redis no responde, open_session
    # lanza 503: no se emite una credencial que no se pudiera revocar.
    sid, access_token, refresh_token, claims = session_box.open_session(row)

    session.clear()
    session.permanent = True
    session["sid"] = sid                       # la cookie solo lleva el sid
    session["login_at"] = datetime.now(timezone.utc).isoformat()
    repo.set_last_login(row["id"])
    metrics.incr("auth.login")

    payload = {
        "authenticated": True,
        "user": repo.public_user(repo.get_by_id(row["id"])),
        "token": access_token,
        "tokenType": "Bearer",
        "expiresIn": session_box.expires_in(claims),
        "refreshToken": refresh_token,
        "refreshExpiresIn": config.JWT_REFRESH_TTL,
        # El cliente deberia renovar cuando falte menos de esto, para no
        # quedarse nunca con un token caducado en la mano.
        "renewBefore": config.JWT_RENEW_BEFORE,
    }
    # El XML no publica los tokens: un XML suele quedarse en archivos y
    # registros intermedios. Quien quiera los tokens pide ?format=json.
    element = serializers.dict_element("session", {
        "authenticated": True,
        "user": repo.public_user(repo.get_by_id(row["id"])),
        "tokenType": "Bearer",
        "expiresIn": session_box.expires_in(claims),
        "refreshExpiresIn": config.JWT_REFRESH_TTL,
        "renewBefore": config.JWT_RENEW_BEFORE,
        "note": "Pida ?format=json para recibir el token y el refreshToken.",
    })
    return respond(payload, element)


@app.post("/refresh")
def refresh():
    """
    Canjea el refresh token por un par nuevo (ROTACION).

    El token de acceso dura 30 minutos y debe renovarse ANTES de caducar.
    El refresh es de UN SOLO USO: al canjearlo se borra y se entrega otro.
    El token de acceso anterior queda revocado en el acto, de modo que no
    siguen vivos dos tokens del mismo usuario.

    Respuestas: 200 par nuevo · 400 falta el token · 401 refresh invalido,
    ya usado o caducado · 403 cuenta desactivada · 503 Redis caido.
    """
    data = read_payload()
    raw = _pick(data, "refreshToken", "refresh_token", "token") or \
        (request.args.get("refreshToken") or "").strip()
    if not raw:
        raise ValidationError(
            "Falta el refresh token.",
            ["Envie {\"refreshToken\": \"...\"} en el cuerpo."])

    # De quien es el refresh lo dice Redis; la cuenta se relee de
    # PostgreSQL para que un usuario desactivado o con el rol cambiado no
    # pueda seguir renovando con los datos de antes.
    record = store.strict_get(store.refresh_key(raw))
    if not isinstance(record, dict):
        metrics.incr("auth.refresh.rejected")
        raise Unauthorized(
            "El refresh token no es valido, ya se uso o caduco.",
            ["Inicie sesion de nuevo."])

    row = repo.get_by_id(int(record.get("user_id", 0)))
    if row is None:
        store.drop_refresh(raw)
        raise Unauthorized("La cuenta del refresh token ya no existe.")
    if not row.get("is_active", True):
        store.drop_refresh(raw)
        raise Unauthorized("La cuenta esta desactivada.")

    rotated = session_box.rotate(raw, row)
    if rotated is None:
        metrics.incr("auth.refresh.rejected")
        raise Unauthorized(
            "El refresh token no es valido, ya se uso o caduco.",
            ["Inicie sesion de nuevo."])

    sid, access_token, refresh_token, claims = rotated
    session["sid"] = sid
    session.permanent = True
    metrics.incr("auth.refresh")

    payload = {
        "authenticated": True,
        "user": repo.public_user(row),
        "token": access_token,
        "tokenType": "Bearer",
        "expiresIn": session_box.expires_in(claims),
        "refreshToken": refresh_token,
        "refreshExpiresIn": config.JWT_REFRESH_TTL,
        "renewBefore": config.JWT_RENEW_BEFORE,
    }
    element = serializers.dict_element("session", {
        "authenticated": True,
        "user": repo.public_user(row),
        "tokenType": "Bearer",
        "expiresIn": session_box.expires_in(claims),
        "note": "Pida ?format=json para recibir el token y el refreshToken.",
    })
    return respond(payload, element)


@app.post("/logout")
def logout():
    """
    Cierra la sesion y REVOCA el token de acceso.

    Es idempotente: sin sesion abierta responde 200 igual. Lo importante
    es lo que ocurre cuando si la hay: el jti del token entra en
    jwt:revoked:<jti> y los SEIS microservicios lo rechazan de inmediato,
    sin esperar los 30 minutos de su vencimiento.

    Acepta el token por cookie de sesion o por Authorization: Bearer.
    """
    sid = _current_sid()
    claims = None
    token = bearer_token(required=False)
    if token:
        try:
            claims = codec.decode(token)
        except DependencyUnavailable:
            # Con Redis caido no se puede revocar nada: 503, nunca un 200
            # que haga creer al cliente que su token quedo anulado.
            raise
        except (SharedApiError, Unauthorized):
            # Un token ya invalido no impide cerrar la sesion de la cookie.
            claims = None

    done = session_box.close_session(sid, claims) if (sid or claims) else {
        "sessionRemoved": False, "accessRevoked": False, "refreshRemoved": False}
    session.clear()
    metrics.incr("auth.logout")

    payload = {"authenticated": False, "message": "Sesion cerrada.", **done}
    return respond(payload, serializers.dict_element("session", payload))


@app.get("/session")
def get_session():
    """
    Dice si hay sesion autenticada y, en ese caso, quien es.

    Consultarla RENUEVA el TTL de la sesion en Redis (ventana
    deslizante): la sesion vive mientras se use y caduca sola a las 8 h
    de inactividad.

    Contrato:
      sin credencial (ni cookie de sesion ni Authorization) -> 200
          {"authenticated": false}
      credencial presente pero invalida, caducada o revocada -> 401
      Redis caido -> 503 (no se puede comprobar la sesion)
    """
    con_credencial = bool(session.get("sid")) or bool(request.headers.get("Authorization"))
    row = _current_user()
    if row is None and con_credencial:
        raise Unauthorized("La sesion no es valida: caduco, se cerro o fue revocada.",
                           ["Inicie sesion de nuevo (POST /login)."])
    if row is None:
        payload = {"authenticated": False}
    else:
        payload = {"authenticated": True, "user": repo.public_user(row),
                   "sessionTtl": config.SESSION_TTL}
    return respond(payload, serializers.dict_element("session", payload))


# =====================================================================
# Manejo de errores: una sola forma de responder, en JSON o en XML
# =====================================================================
def _error_response(status, code, message, details=None):
    payload = {"error": {"status": status, "code": code, "message": message,
                         "details": details or []}}
    element = serializers.error_element(status, code, message, details)
    return respond(payload, element, status=status)


@app.errorhandler(ApiError)
def handle_api_error(exc):
    return _error_response(exc.status, exc.code, exc.message, exc.details)


@app.errorhandler(SharedApiError)
def handle_shared_api_error(exc):
    """
    Errores que levanta el paquete compartido: 401 de token ausente,
    invalido, caducado o revocado; 403 de rol insuficiente; 503 de Redis.
    Misma forma de respuesta que los propios del servicio.
    """
    if exc.status >= 500:
        log.error("%s: %s", exc.code, exc.message)
    return _error_response(exc.status, exc.code, exc.message, exc.details)


@app.errorhandler(DependencyUnavailable)
def handle_dependency_down(exc):
    """
    Redis caido en una operacion de sesion o revocacion. Es un fallo
    SEGURO y deliberado: antes que emitir o aceptar una credencial que no
    se pueda revocar, se responde 503.
    """
    log.error("Dependencia no disponible (%s): %s", exc.code, exc.message)
    return _error_response(exc.status, exc.code, exc.message, exc.details)


@app.errorhandler(db.DatabaseUnavailable)
def handle_db_down(exc):
    # El texto de psycopg y usuario@host:puerto/db van al registro, no al
    # cliente: ahi es donde los busca quien opera el servicio.
    log.error("PostgreSQL no disponible (%s@%s:%s/%s): %s - revise PGHOST/PGPORT/"
              "PGUSER/PGPASSWORD en login/.env", config.PGUSER, config.PGHOST,
              config.PGPORT, config.PGDATABASE, exc)
    return _error_response(
        503, "database_unavailable",
        "No hay conexion con PostgreSQL.",
        ["La base de datos no responde. Reintente en unos segundos; "
         "el detalle tecnico queda en el registro del servicio."])


@app.errorhandler(HTTPException)
def handle_http_error(exc):
    code = {404: "not_found", 405: "method_not_allowed",
            415: "unsupported_media_type"}.get(exc.code, "http_error")
    return _error_response(exc.code, code, exc.description or exc.name)


@app.errorhandler(Exception)
def handle_unexpected(exc):
    log.exception("Error no controlado")
    details = [f"{type(exc).__name__}: {exc}"] if config.DEBUG else []
    return _error_response(500, "internal_error",
                           "Error interno del microservicio.", details)


if __name__ == "__main__":
    log.info("Login -> http://%s:%s/login  (sesion Flask, XML por omision)", config.HOST, config.PORT)
    log.info("Swagger UI -> http://%s:%s/docs", config.HOST, config.PORT)
    log.info("PostgreSQL -> %s@%s:%s/%s (esquema %s)",
             config.PGUSER, config.PGHOST, config.PGPORT, config.PGDATABASE, config.PGSCHEMA)
    log.info("sendmail -> %s:%s (remitente %s)", config.SMTP_HOST, config.SMTP_PORT, config.SMTP_FROM)
    # Se registra la URL REDACTADA: la contrasena de Redis no va al log.
    from library_common.env import redacted
    log.info("Redis -> %s (sesiones %ss, acceso %ss, refresh %ss)",
             redacted(config.REDIS_URL) or "SIN CONFIGURAR",
             config.SESSION_TTL, config.JWT_ACCESS_TTL, config.JWT_REFRESH_TTL)
    log.info("CORS origins -> %s", ", ".join(config.CORS_ORIGINS))
    for item in config.warnings():
        log.warning(item)
    # load_dotenv=False: config.py ya cargo el .env por ruta absoluta; el
    # autoload de Flask resuelve desde el cwd y falla si este fue borrado.
    app.run(host=config.HOST, port=config.PORT, debug=config.DEBUG,
            load_dotenv=False)
