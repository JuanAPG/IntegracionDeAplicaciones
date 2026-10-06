"""
packages/library_common/library_common/env.py
Lectura de la configuracion desde variables de entorno.

Todos los servicios siguen la misma precedencia:

    entorno real  >  .env de la raiz del repo  >  .env del propio servicio

El .env de la raiz guarda lo COMPARTIDO (JWT_SECRET, REDIS_URL, credenciales
de PostgreSQL); el del servicio, lo propio (HOST, PORT, CORS_ORIGINS). Asi
un secreto se escribe una vez y lo leen los seis microservicios.

override=False en los dos load_dotenv: lo que ya venga del entorno real
(systemd, contenedor, CI) manda, y el .env solo rellena huecos.
"""
import os

from dotenv import load_dotenv

# Valores de ejemplo que NO cuentan como configuracion real: si un secreto
# tiene uno de estos, el servicio lo reporta como ausente en /health.
PLACEHOLDERS = frozenset({
    "", "change-me", "cambieme",
    "CAMBIEME_secreto_jwt_compartido",
    "CAMBIEME_secreto_de_sesion_flask",
    "CAMBIEME_contrasena_de_postgres",
    "CAMBIEME_contrasena_de_redis",
})


def load_dotenvs(service_file, depth):
    """
    Carga el .env de la raiz del repo y el del servicio.

    service_file  __file__ del modulo de configuracion que llama.
    depth         cuantos directorios hay que subir desde ese archivo para
                  llegar a la raiz del repo (library/).

    Ejemplo: apps/services/users/users/config.py esta a 4 niveles de la
    raiz (users/ -> users/ -> services/ -> apps/ -> library/), luego
    depth=4. El .env del servicio se busca dos niveles arriba del modulo
    (apps/services/users/.env), que es donde lo pone el despliegue.
    """
    path = os.path.abspath(service_file)
    root = path
    for _ in range(depth + 1):
        root = os.path.dirname(root)
    load_dotenv(os.path.join(root, ".env"), override=False)
    service_root = os.path.dirname(os.path.dirname(path))
    load_dotenv(os.path.join(service_root, ".env"), override=False)
    return root, service_root


def get(name, default=""):
    value = os.getenv(name)
    return default if value is None else value


def get_int(name, default):
    try:
        return int(os.getenv(name, default))
    except (TypeError, ValueError):
        return int(default)


def get_float(name, default):
    try:
        return float(os.getenv(name, default))
    except (TypeError, ValueError):
        return float(default)


def get_bool(name, default=False):
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on", "si")


def get_list(name, default=""):
    return [item.strip() for item in get(name, default).split(",") if item.strip()]


def is_real(value):
    """True si el valor es configuracion de verdad y no un marcador de ejemplo."""
    return bool(value) and value not in PLACEHOLDERS


def redacted(url):
    """
    Oculta la contrasena de una URL para poder registrarla en el log.

    redis://:secreto@10.0.0.4:6379/0  ->  redis://:***@10.0.0.4:6379/0

    Nunca se escribe un secreto en los registros: ni contrasenas, ni
    tokens, ni la URL completa de Redis.
    """
    if not url:
        return ""
    try:
        scheme, rest = url.split("://", 1)
    except ValueError:
        return "***"
    if "@" not in rest:
        return url
    credentials, host = rest.rsplit("@", 1)
    user = credentials.split(":", 1)[0]
    return f"{scheme}://{user}:***@{host}"
