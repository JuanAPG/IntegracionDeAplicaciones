"""
library_soap_service/soap/config.py
Configuracion del microservicio, leida exclusivamente de variables de
entorno (archivo .env). Ninguna credencial esta escrita en el codigo.
"""
import os

from dotenv import load_dotenv

# .env compartido en la raiz del proyecto (library/), mas .env local del
# servicio como respaldo para despliegues en /opt/library (systemd).
# Orden de precedencia: entorno real > .env raiz > .env local.
# Asi se escala a mas micros: todos leen el mismo JWT_SECRET sin duplicarlo.
_PROJECT_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
load_dotenv(os.path.join(_PROJECT_ROOT, ".env"), override=False)
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                         ".env"), override=False)


def _int(name, default):
    try:
        return int(os.getenv(name, default))
    except (TypeError, ValueError):
        return int(default)


def _bool(name, default=False):
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on", "si")


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
# El mismo JWT_SECRET del .env raiz debe usarse en todos los servicios.
# ---------------------------------------------------------------------
JWT_SECRET = os.getenv("JWT_SECRET", "")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")


def jwt_configured():
    """True si hay un secreto JWT real (no vacio ni valor de ejemplo)."""
    return bool(JWT_SECRET and JWT_SECRET not in ("", "change-me",
                                                  "CAMBIEME_secreto_jwt_compartido"))

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
