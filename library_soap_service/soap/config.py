"""
library_soap_service/soap/config.py
Configuracion del microservicio, leida exclusivamente de variables de
entorno (archivo .env). Ninguna credencial esta escrita en el codigo.
"""
import os

from . import _bootstrap  # noqa: F401  (deja library_common importable)
from library_common import env
from library_common.settings import CommonSettings

# La configuracion COMPARTIDA con los otros cinco microservicios (secreto
# del JWT, URL de Redis, PostgreSQL, TTL) la lee library_common desde el
# .env de la RAIZ; lo propio del servicio se lee aqui. Precedencia:
# entorno real > .env de la raiz > .env del servicio.
SHARED = CommonSettings(__file__, depth=2, service="books",
                        default_port=5001,
                        namespace="urn:library:catalog:1.0")


def _int(name, default):
    return env.get_int(name, default)


def _bool(name, default=False):
    return env.get_bool(name, default)


# ---------------------------------------------------------------------
# Servidor
# ---------------------------------------------------------------------
HOST = os.getenv("HOST", "0.0.0.0")
PORT = _int("PORT", 5001)
DEBUG = _bool("DEBUG", False)

# Prefijo bajo el que se montan todos los endpoints de datos. Vacio por
# omision: los recursos cuelgan de la raiz (/books, /formats, ...). Si un
# despliegue necesita agruparlos, basta con poner API_PREFIX=/api en el
# .env; app.py y openapi.py derivan todas sus rutas de este valor.
API_PREFIX = os.getenv("API_PREFIX", "").rstrip("/")

# ---------------------------------------------------------------------
# JWT (verificacion — el emisor es el microservicio login)
# El mismo JWT_SECRET_KEY del .env de la raiz debe usarse en los seis
# servicios. Se acepta JWT_SECRET como nombre anterior.
# ---------------------------------------------------------------------
JWT_SECRET = SHARED.jwt_secret
JWT_ALGORITHM = SHARED.jwt_algorithm
JWT_ISSUER = SHARED.jwt_issuer


def jwt_configured():
    """True si hay un secreto JWT real (no vacio ni valor de ejemplo)."""
    return SHARED.jwt_configured


# ---------------------------------------------------------------------
# Redis: cache del catalogo y lista de revocacion de JWT
#
# DOS POLITICAS DISTINTAS, a proposito:
#   * El CACHE de lecturas es opcional. Si Redis no responde, la peticion
#     sigue contra PostgreSQL y el cliente no se entera.
#   * La REVOCACION de tokens no lo es. Si no se puede comprobar si un
#     token fue revocado, la escritura se rechaza con 503 en lugar de
#     aceptar una credencial posiblemente revocada.
# ---------------------------------------------------------------------
REDIS_URL = SHARED.redis_url
# TTL CORTO: el catalogo cambia poco, pero cuando cambia se invalida de
# inmediato (ver soap/cache.py). El TTL es la red de seguridad por si una
# invalidacion se pierde con Redis caido, no el mecanismo principal.
CACHE_TTL = SHARED.cache_ttl                  # listados
CACHE_DETAIL_TTL = SHARED.cache_detail_ttl    # un libro por ISBN o id
CACHE_ENABLED = env.get_bool("CACHE_ENABLED", True)


def redis_configured():
    return SHARED.redis_configured


def warnings():
    """Avisos de configuracion que /health publica tal cual."""
    return SHARED.warnings()

# ---------------------------------------------------------------------
# PostgreSQL
# ---------------------------------------------------------------------
PGHOST = os.getenv("PGHOST", "localhost")
PGPORT = _int("PGPORT", 5432)
PGDATABASE = os.getenv("PGDATABASE", "library_db")
PGUSER = os.getenv("PGUSER", "library_user")
PGPASSWORD = os.getenv("PGPASSWORD", "")
PGSCHEMA = os.getenv("PGSCHEMA", "library")

DB_POOL_MIN = _int("DB_POOL_MIN", 1)
DB_POOL_MAX = _int("DB_POOL_MAX", 10)
DB_CONNECT_TIMEOUT = _int("DB_CONNECT_TIMEOUT", 5)

# ---------------------------------------------------------------------
# CORS  (el servicio se consume desde clientes de otro dominio)
# ---------------------------------------------------------------------
# Lista separada por comas, o "*" para permitir cualquier origen.
CORS_ORIGINS = [o.strip() for o in os.getenv("CORS_ORIGINS", "*").split(",") if o.strip()]
CORS_MAX_AGE = _int("CORS_MAX_AGE", 86400)

# ---------------------------------------------------------------------
# Representacion
# ---------------------------------------------------------------------
# Formato de salida cuando el cliente no pide ninguno (?format= / Accept).
DEFAULT_FORMAT = os.getenv("DEFAULT_FORMAT", "xml").lower()
# Moneda que se anota en el atributo currency de <price>.
CURRENCY = os.getenv("CURRENCY", "MXN")
# Espacio de nombres del XML: el mismo de apps/services/soap/library.xml
XML_NAMESPACE = os.getenv("XML_NAMESPACE", "urn:library:catalog:1.0")
XML_VERSION = os.getenv("XML_VERSION", "1.0")

# Paginacion
DEFAULT_LIMIT = _int("DEFAULT_LIMIT", 50)
MAX_LIMIT = _int("MAX_LIMIT", 200)

# ---------------------------------------------------------------------
# Modulo SOAP de clasificacion (ver wsdl/library-classiffier.wsdl y
# sql/soap_module.sql). Namespace y ruta configurables por si el
# despliegue necesita moverlos, igual que el resto del servicio.
# ---------------------------------------------------------------------
CLASIFICACION_NAMESPACE = os.getenv("CLASIFICACION_NAMESPACE", "urn:library:clasificacion:1.0")
SOAP_ENDPOINT_PATH = os.getenv("SOAP_ENDPOINT_PATH", "/soap/clasificacion")
CLASIFICACION_DEFAULT_LIMIT = _int("CLASIFICACION_DEFAULT_LIMIT", 10)
CLASIFICACION_MAX_LIMIT = _int("CLASIFICACION_MAX_LIMIT", 100)
