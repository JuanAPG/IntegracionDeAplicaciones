"""
apps/services/login/login/config.py
Configuracion del microservicio, leida exclusivamente de variables de
entorno (.env). Ninguna credencial esta escrita en el codigo.

La parte COMPARTIDA con los otros cinco microservicios (secreto del JWT,
URL de Redis, credenciales de PostgreSQL, tiempos de expiracion) la lee
library_common.settings desde el .env de la RAIZ del repo; lo propio del
servicio (correo, bcrypt, sesion) se lee aqui.

Precedencia: entorno real > .env de la raiz > .env del servicio.
"""
import os

from . import _bootstrap  # noqa: F401  (deja library_common importable)
from library_common import env
from library_common.settings import CommonSettings

SHARED = CommonSettings(__file__, depth=4, service="login",
                        default_port=5000,
                        namespace="urn:library:auth:1.0")

# ---------------------------------------------------------------------
# Servidor
# ---------------------------------------------------------------------
HOST = SHARED.host
PORT = SHARED.port
DEBUG = SHARED.debug

# Firma las cookies de sesion de Flask. Es DISTINTA del secreto del JWT:
# una firma la cookie que identifica la sesion, el otro firma los tokens
# que verifican los demas microservicios.
SECRET_KEY = env.get("SECRET_KEY", "")

# ---------------------------------------------------------------------
# JWT — este servicio es el UNICO EMISOR; los demas solo verifican.
#
# JWT_SECRET_KEY debe ser identico en los seis servicios. Se acepta el
# nombre anterior JWT_SECRET para no romper los despliegues que ya
# existen. Generelo con:
#     python3 -c "import secrets; print(secrets.token_urlsafe(64))"
# ---------------------------------------------------------------------
JWT_SECRET = SHARED.jwt_secret
JWT_ALGORITHM = SHARED.jwt_algorithm
JWT_ISSUER = SHARED.jwt_issuer
# 30 minutos, como fija el enunciado. El cliente debe renovar ANTES de
# que caduque con POST /refresh (ver JWT_RENEW_BEFORE_SECONDS).
JWT_ACCESS_TTL = SHARED.jwt_access_ttl            # segundos
JWT_REFRESH_TTL = SHARED.jwt_refresh_ttl          # segundos
JWT_RENEW_BEFORE = SHARED.jwt_renew_before        # segundos
# Compatibilidad: algunos scripts informan las horas del token de acceso.
JWT_EXPIRATION_HOURS = JWT_ACCESS_TTL / 3600.0


def jwt_configured():
    """True si hay un secreto JWT real (no vacio ni valor de ejemplo)."""
    return SHARED.jwt_configured


# ---------------------------------------------------------------------
# Redis (capa compartida: sesiones, refresh tokens, revocacion)
# ---------------------------------------------------------------------
REDIS_URL = SHARED.redis_url
SESSION_TTL = SHARED.session_ttl                  # segundos


def redis_configured():
    return SHARED.redis_configured


# ---------------------------------------------------------------------
# PostgreSQL (misma base library_db del proyecto)
# ---------------------------------------------------------------------
PGHOST = SHARED.pg["host"]
PGPORT = SHARED.pg["port"]
PGDATABASE = SHARED.pg["dbname"]
PGUSER = SHARED.pg["user"]
PGPASSWORD = SHARED.pg["password"]
PGSCHEMA = SHARED.pg["schema"]

DB_POOL_MIN = SHARED.pg["pool_min"]
DB_POOL_MAX = SHARED.pg["pool_max"]
DB_CONNECT_TIMEOUT = SHARED.pg["connect_timeout"]

# ---------------------------------------------------------------------
# Sesion Flask
# La cookie ya NO lleva el estado de la sesion, solo su identificador
# (sid): el estado vive en Redis y por eso se puede cerrar del lado del
# servidor. La vida de la cookie se alinea con el TTL de Redis.
# ---------------------------------------------------------------------
from datetime import timedelta  # noqa: E402  (se usa justo abajo)

SESSION_LIFETIME = timedelta(seconds=SESSION_TTL)
SESSION_COOKIE_SECURE = env.get_bool("SESSION_COOKIE_SECURE", False)

# ---------------------------------------------------------------------
# CORS (con cookies de sesion: supports_credentials=true)
# El navegador rechaza "*" combinado con credenciales, de modo que en
# produccion CORS_ORIGINS debe enumerar los origenes de los clientes.
# ---------------------------------------------------------------------
CORS_ORIGINS = SHARED.cors_origins
CORS_MAX_AGE = SHARED.cors_max_age

# ---------------------------------------------------------------------
# Representacion (XML por omision, segun el enunciado)
# ---------------------------------------------------------------------
DEFAULT_FORMAT = SHARED.default_format
XML_NAMESPACE = SHARED.namespace
XML_VERSION = SHARED.xml_version

# ---------------------------------------------------------------------
# Correo: sendmail alojado en la instancia (SMTP local, sin POP/IMAP)
# ---------------------------------------------------------------------
SMTP_HOST = env.get("SMTP_HOST", "localhost")
SMTP_PORT = env.get_int("SMTP_PORT", 25)
SMTP_TIMEOUT = env.get_int("SMTP_TIMEOUT", 10)
SMTP_FROM = env.get("SMTP_FROM", "noreply@libreria.local")
MAIL_SERVICE_NAME = env.get("MAIL_SERVICE_NAME", "Libreria en Linea")
MAIL_VERIFY_BASE_URL = env.get("MAIL_VERIFY_BASE_URL", "").rstrip("/")
TOKEN_TTL_HOURS = env.get_int("TOKEN_TTL_HOURS", 48)

# ---------------------------------------------------------------------
# Contrasenas
# ---------------------------------------------------------------------
BCRYPT_ROUNDS = env.get_int("BCRYPT_ROUNDS", 12)
PASSWORD_MIN_LENGTH = env.get_int("PASSWORD_MIN_LENGTH", 6)


def warnings():
    """Avisos de configuracion que /health publica tal cual."""
    items = []
    if not SECRET_KEY:
        items.append("SECRET_KEY sin fijar: las sesiones no son seguras.")
    items.extend(SHARED.warnings())
    return items


# Compatibilidad con el codigo anterior: os sigue importado porque algunos
# despliegues anaden lecturas puntuales de os.getenv en este archivo.
__all__ = [name for name in dir() if name.isupper() or name.islower()]
_ = os
