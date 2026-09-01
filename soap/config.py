"""
soap/config.py
Configuracion del microservicio, leida exclusivamente de variables de
entorno (archivo .env). Ninguna credencial esta escrita en el codigo.
"""
import os

from dotenv import load_dotenv

# .env vive junto a este archivo; override=False respeta las variables que
# ya vengan del entorno real (systemd, contenedor, CI).
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"),
            override=False)


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

# Prefijo bajo el que se montan todos los endpoints de datos.
API_PREFIX = os.getenv("API_PREFIX", "/api").rstrip("/")

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
DEFAULT_FORMAT = os.getenv("DEFAULT_FORMAT", "json").lower()
# Moneda que se anota en el atributo currency de <price>.
CURRENCY = os.getenv("CURRENCY", "MXN")
# Espacio de nombres del XML: el mismo de apps/services/soap/library.xml
XML_NAMESPACE = os.getenv("XML_NAMESPACE", "urn:library:catalog:1.0")
XML_VERSION = os.getenv("XML_VERSION", "1.0")

# Paginacion
DEFAULT_LIMIT = _int("DEFAULT_LIMIT", 50)
MAX_LIMIT = _int("MAX_LIMIT", 200)
