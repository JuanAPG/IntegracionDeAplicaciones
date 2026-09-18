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
  POST /login     verifica credenciales y crea la sesion Flask
  POST /logout    cierra la sesion
  GET  /session   dice si hay sesion autenticada y quien es
  GET  /health    estado del servicio y de PostgreSQL
"""
import logging
from datetime import datetime, timezone
from xml.etree import ElementTree

from flasgger import Swagger
from flask import Flask, Response, jsonify, request, session
from flask_cors import CORS
from werkzeug.exceptions import HTTPException

import config
import db
import mailer as mail_sender
import openapi
import serializers
import tokens as token_box
import users_repository as repo
import validators
from errors import ApiError, Conflict, EmailNotVerified, Gone, NotFound, Unauthorized, ValidationError
from mailer import MailerError  # noqa: F401  (se documenta el 503 en openapi.py)
from security import hash_password, verify_password

logging.basicConfig(
    level=logging.DEBUG if config.DEBUG else logging.INFO,
    format="%(asctime)s %(levelname)-7s %(message)s")
log = logging.getLogger("library.login")

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
    allow_headers=["Content-Type", "Accept", "Origin", "X-Requested-With"],
    expose_headers=["Content-Type", "Content-Length", "Location"],
    supports_credentials=True,
    max_age=config.CORS_MAX_AGE,
)


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


def _current_user():
    user_id = session.get("user_id")
    if not user_id:
        return None
    try:
        row = repo.get_by_id(int(user_id))
    except (TypeError, ValueError):
        row = None
    if row is None:
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
            {"method": "POST", "path": "/login", "description": "Autenticar e iniciar sesion"},
            {"method": "POST", "path": "/logout", "description": "Cerrar la sesion"},
            {"method": "GET", "path": "/session", "description": "Consultar la sesion autenticada"},
            {"method": "GET", "path": "/health", "description": "Estado del servicio y de la base de datos"},
            {"method": "GET", "path": "/docs", "description": "Documentacion interactiva (Swagger UI)"},
        ],
    }
    return respond(payload, serializers.dict_element("service", payload))


@app.get("/health")
def health():
    warnings = []
    if not config.SECRET_KEY:
        warnings.append("SECRET_KEY sin fijar: las sesiones no son seguras.")
    try:
        info = db.ping()
        payload = {"status": "ok", "database": info["db"], "user": info["usr"],
                   "schema": config.PGSCHEMA,
                   "server": info["version"].split(" on ")[0],
                   "sessionSigning": "ok" if config.SECRET_KEY else "missing_secret",
                   "mailer": f"{config.SMTP_HOST}:{config.SMTP_PORT}"}
        status = 200
    except Exception as exc:                       # noqa: BLE001 - se reporta al cliente
        payload = {"status": "error", "database": config.PGDATABASE,
                   "message": str(exc).strip()}
        status = 503
    if warnings:
        payload["warnings"] = warnings
    return respond(payload, serializers.dict_element("health", payload), status=status)


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

    session.clear()
    session.permanent = True
    session["user_id"] = row["id"]
    session["login_at"] = datetime.now(timezone.utc).isoformat()
    repo.set_last_login(row["id"])

    payload = {"authenticated": True, "user": repo.public_user(repo.get_by_id(row["id"]))}
    return respond(payload, serializers.dict_element("session", payload))


@app.post("/logout")
def logout():
    """Cierra la sesion (funciona aunque no haya sesion abierta)."""
    session.clear()
    payload = {"authenticated": False, "message": "Sesion cerrada."}
    return respond(payload, serializers.dict_element("session", payload))


@app.get("/session")
def get_session():
    """Dice si hay sesion autenticada y, en ese caso, quien es."""
    row = _current_user()
    if row is None:
        payload = {"authenticated": False}
    else:
        payload = {"authenticated": True, "user": repo.public_user(row)}
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


@app.errorhandler(db.DatabaseUnavailable)
def handle_db_down(exc):
    log.error("PostgreSQL no disponible: %s", exc)
    return _error_response(
        503, "database_unavailable",
        "No hay conexion con PostgreSQL.",
        [str(exc).strip(),
         f"Revise PGHOST/PGPORT/PGUSER/PGPASSWORD en login/.env "
         f"(destino actual: {config.PGUSER}@{config.PGHOST}:{config.PGPORT}/{config.PGDATABASE})."])


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
    log.info("CORS origins -> %s", ", ".join(config.CORS_ORIGINS))
    # load_dotenv=False: config.py ya cargo el .env por ruta absoluta; el
    # autoload de Flask resuelve desde el cwd y falla si este fue borrado.
    app.run(host=config.HOST, port=config.PORT, debug=config.DEBUG,
            load_dotenv=False)
