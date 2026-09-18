"""
apps/services/login/login/config.py
Configuracion del microservicio, leida exclusivamente de variables de
entorno (archivo .env). Ninguna credencial esta escrita en el codigo.
"""
import os
from datetime import timedelta

from dotenv import load_dotenv

# .env vive en apps/services/login/ (un nivel arriba de login/, donde estan
# tambien requirements.txt y el .venv); override=False respeta las variables
# que ya vengan del entorno real (systemd, contenedor, CI).
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"),
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
PORT = _int("PORT", 5000)
DEBUG = _bool("DEBUG", False)

# Firma las cookies de sesion. Sin valor real, Flask no debe operar en
# produccion: app.py lo advierte y /health lo reporta como degradado.
SECRET_KEY = os.getenv("SECRET_KEY", "")

# ---------------------------------------------------------------------
# PostgreSQL (misma base library_db del proyecto)
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
# Sesion Flask
# ---------------------------------------------------------------------
SESSION_LIFETIME = timedelta(hours=_int("SESSION_LIFETIME_HOURS", 8))
SESSION_COOKIE_SECURE = _bool("SESSION_COOKIE_SECURE", False)

# ---------------------------------------------------------------------
# CORS (con cookies de sesion: supports_credentials=true)
# ---------------------------------------------------------------------
CORS_ORIGINS = [o.strip() for o in os.getenv("CORS_ORIGINS", "*").split(",") if o.strip()]
CORS_MAX_AGE = _int("CORS_MAX_AGE", 86400)

# ---------------------------------------------------------------------
# Representacion (XML por omision, segun el enunciado)
# ---------------------------------------------------------------------
DEFAULT_FORMAT = os.getenv("DEFAULT_FORMAT", "xml").lower()
XML_NAMESPACE = os.getenv("XML_NAMESPACE", "urn:library:auth:1.0")
XML_VERSION = os.getenv("XML_VERSION", "1.0")

# ---------------------------------------------------------------------
# Correo: sendmail alojado en la instancia (SMTP local, sin POP/IMAP)
# ---------------------------------------------------------------------
SMTP_HOST = os.getenv("SMTP_HOST", "localhost")
SMTP_PORT = _int("SMTP_PORT", 25)
SMTP_TIMEOUT = _int("SMTP_TIMEOUT", 10)
SMTP_FROM = os.getenv("SMTP_FROM", "noreply@libreria.local")
MAIL_SERVICE_NAME = os.getenv("MAIL_SERVICE_NAME", "Libreria en Linea")
MAIL_VERIFY_BASE_URL = os.getenv("MAIL_VERIFY_BASE_URL", "").rstrip("/")
TOKEN_TTL_HOURS = _int("TOKEN_TTL_HOURS", 48)

# ---------------------------------------------------------------------
# Contrasenas
# ---------------------------------------------------------------------
BCRYPT_ROUNDS = _int("BCRYPT_ROUNDS", 12)
PASSWORD_MIN_LENGTH = _int("PASSWORD_MIN_LENGTH", 6)
