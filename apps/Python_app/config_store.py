"""Localstorage de la app: endpoints + sesion del usuario en un JSON local."""
import json
import os

APP_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(APP_DIR, "config.json")

# Los seis microservicios. Cambiar la IP de la VM se hace en un solo
# sitio: Ajustes ⚙ de la aplicación (que escribe aquí).
VM_POR_OMISION = "34.51.14.158"

DEFAULTS = {
    "endpoints": {
        "login_base_url": f"http://{VM_POR_OMISION}:5000",
        "books_base_url": f"http://{VM_POR_OMISION}:5001",
        "users_base_url": f"http://{VM_POR_OMISION}:5002",
        "authors_base_url": f"http://{VM_POR_OMISION}:5003",
        "pedidos_base_url": f"http://{VM_POR_OMISION}:5004",
        "pagos_base_url": f"http://{VM_POR_OMISION}:5005",
        "timeout": 8,
        "poll": 15,
    },
    "session": {"email": None, "user": None, "cookies": None,
                "token": None, "refresh_token": None,
                "saved_at": None, "login_at": None},
}

SERVICIOS = ("login", "books", "users", "authors", "pedidos", "pagos")

# La sesión vive en Redis con TTL de 8 h (ventana deslizante) y el token
# de acceso dura 30 min, renovable con /refresh. Esto es solo la
# estimación local para avisar al usuario; la verdad la tiene el
# servidor y se comprueba con GET /session.
SESSION_LIFETIME_HOURS = 8
WARN_BEFORE_MINUTES = 30


def _deep_merge(base, override):
    out = dict(base)
    for k, v in (override or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def load():
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        return _deep_merge(DEFAULTS, data)
    except (FileNotFoundError, json.JSONDecodeError):
        return _deep_merge(DEFAULTS, {})


def save(config):
    tmp = CONFIG_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(config, fh, ensure_ascii=False, indent=2)
    os.replace(tmp, CONFIG_PATH)
    return config


def save_session(config, email, user, cookies, token=None, login_at=None,
                 refresh_token=None):
    """
    Guarda la sesión en el JSON local.

    NUNCA se guarda la contraseña: solo la cookie de sesión, el token de
    acceso (30 min) y el refresh (8 h), que son revocables desde el
    servidor. Si alguien copia este archivo, un /logout o una baja de la
    cuenta dejan esos tokens inservibles al instante.
    """
    from datetime import datetime, timezone
    config["session"] = {
        "email": email,
        "user": user,
        "cookies": cookies or {},
        "token": token,
        "refresh_token": refresh_token,
        "saved_at": datetime.now(timezone.utc).isoformat(),
        "login_at": login_at,
    }
    return save(config)


def save_tokens(config, token, refresh_token):
    """Actualiza solo los tokens, tras una renovación con /refresh."""
    sesion = config.get("session") or {}
    sesion["token"] = token
    sesion["refresh_token"] = refresh_token
    config["session"] = sesion
    return save(config)


def clear_session(config):
    config["session"] = {"email": None, "user": None, "cookies": None,
                         "token": None, "refresh_token": None,
                         "saved_at": None, "login_at": None}
    return save(config)


def session_expiry_info(session):
    """Devuelve (state, minutes_left) con state en
    expired/expiring_soon/valid/none según la vida estimada de 8 h."""
    from datetime import datetime, timezone
    if not session or not session.get("cookies"):
        return "none", None
    raw = session.get("login_at") or session.get("saved_at")
    if not raw:
        return "valid", None
    try:
        start = datetime.fromisoformat(raw)
        if start.tzinfo is None:
            start = start.replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return "valid", None
    from datetime import timedelta
    elapsed = datetime.now(timezone.utc) - start
    left = timedelta(hours=SESSION_LIFETIME_HOURS) - elapsed
    minutes = int(left.total_seconds() // 60)
    if minutes <= 0:
        return "expired", 0
    if minutes <= WARN_BEFORE_MINUTES:
        return "expiring_soon", minutes
    return "valid", minutes


def endpoints(config):
    """(login, books, timeout, poll) — forma antigua, para no romper nada."""
    urls = service_urls(config)
    timeout, poll = timings(config)
    return urls["login"], urls["books"], timeout, poll


def service_urls(config):
    """Diccionario servicio -> URL base, con la de fábrica como respaldo."""
    ep = config.get("endpoints", {}) or {}
    urls = {}
    for nombre in SERVICIOS:
        clave = f"{nombre}_base_url"
        valor = str(ep.get(clave) or DEFAULTS["endpoints"][clave]).rstrip("/")
        urls[nombre] = valor
    return urls


def timings(config):
    ep = config.get("endpoints", {}) or {}
    try:
        timeout = int(ep.get("timeout", 8))
    except (TypeError, ValueError):
        timeout = 8
    try:
        poll = int(ep.get("poll", 15))
    except (TypeError, ValueError):
        poll = 15
    return max(timeout, 2), max(poll, 5)


def set_vm_host(config, host):
    """
    Apunta los SEIS servicios a una IP, conservando los puertos.

    La IP de la VM es efímera y cambia a menudo: esto evita tener que
    editar seis campos a mano cada vez.
    """
    host = (host or "").strip().rstrip("/")
    if not host:
        return config
    if "://" not in host:
        host = "http://" + host
    puertos = {"login": 5000, "books": 5001, "users": 5002,
               "authors": 5003, "pedidos": 5004, "pagos": 5005}
    ep = config.setdefault("endpoints", {})
    for nombre, puerto in puertos.items():
        ep[f"{nombre}_base_url"] = f"{host}:{puerto}"
    return save(config)
