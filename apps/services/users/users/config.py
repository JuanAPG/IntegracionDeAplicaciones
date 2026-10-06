"""
apps/services/users/users/config.py
Configuracion del microservicio de usuarios, roles, correos y contrasenas.

Se lee EXCLUSIVAMENTE de variables de entorno. Ninguna credencial esta
escrita en el codigo.

Lo COMPARTIDO con los otros cinco servicios (JWT_SECRET_KEY, REDIS_URL,
credenciales de PostgreSQL, tiempos de expiracion) lo lee
library_common.settings desde el .env de la RAIZ del repo; lo propio del
servicio, desde su propio .env.

Precedencia: entorno real > .env de la raiz > .env del servicio.
"""
from . import _bootstrap  # noqa: F401  (deja library_common importable)
from library_common import env
from library_common.settings import CommonSettings

SHARED = CommonSettings(__file__, depth=4, service="users",
                        default_port=5002,
                        namespace="urn:library:users:1.0")

SERVICE_NAME = "library-users-service"

# ---------------------------------------------------------------------
# Servidor
# ---------------------------------------------------------------------
HOST = SHARED.host
PORT = SHARED.port
DEBUG = SHARED.debug
API_PREFIX = SHARED.api_prefix

# ---------------------------------------------------------------------
# JWT: este servicio solo VERIFICA. El emisor es el microservicio login.
# ---------------------------------------------------------------------
JWT_SECRET = SHARED.jwt_secret
JWT_ALGORITHM = SHARED.jwt_algorithm
JWT_ISSUER = SHARED.jwt_issuer
JWT_ACCESS_TTL = SHARED.jwt_access_ttl


def jwt_configured():
    return SHARED.jwt_configured


# ---------------------------------------------------------------------
# Redis: lista de revocacion de JWT, cache de permisos y de lecturas
# publicas, y cerrojos de tareas temporales.
# ---------------------------------------------------------------------
REDIS_URL = SHARED.redis_url
CACHE_TTL = SHARED.cache_ttl
CACHE_DETAIL_TTL = SHARED.cache_detail_ttl
CACHE_ENABLED = env.get_bool("CACHE_ENABLED", True)


def redis_configured():
    return SHARED.redis_configured


# ---------------------------------------------------------------------
# PostgreSQL (fuente principal de datos: library_db / esquema library)
# ---------------------------------------------------------------------
PGHOST = SHARED.pg["host"]
PGPORT = SHARED.pg["port"]
PGDATABASE = SHARED.pg["dbname"]
PGUSER = SHARED.pg["user"]
PGSCHEMA = SHARED.pg["schema"]

# ---------------------------------------------------------------------
# CORS: en produccion enumere los origenes de las aplicaciones cliente
# ---------------------------------------------------------------------
CORS_ORIGINS = SHARED.cors_origins
CORS_MAX_AGE = SHARED.cors_max_age

# ---------------------------------------------------------------------
# Representacion (XML por omision, como el resto del proyecto)
# ---------------------------------------------------------------------
DEFAULT_FORMAT = SHARED.default_format
XML_NAMESPACE = SHARED.namespace
XML_VERSION = SHARED.xml_version

# ---------------------------------------------------------------------
# Paginacion
# ---------------------------------------------------------------------
DEFAULT_LIMIT = SHARED.default_limit
MAX_LIMIT = SHARED.max_limit


def warnings():
    """Avisos de configuracion que /health publica tal cual."""
    return SHARED.warnings()
