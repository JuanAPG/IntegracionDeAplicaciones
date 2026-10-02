"""Localstorage de la app: endpoints + sesion del usuario en un JSON local."""
import json
import os

APP_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(APP_DIR, "config.json")

DEFAULTS = {
    "endpoints": {
        "login_base_url": "http://34.51.125.230:5000",
        "books_base_url": "http://34.51.125.230:5001",
        "timeout": 8,
        "poll": 15,
    },
    "session": {"email": None, "user": None, "cookies": None,
                "token": None, "saved_at": None, "login_at": None},
}

# La cookie de Flask es opaca: el servidor no dice cuándo vence.
# Se estima con la vida configurada en el microservicio
# (SESSION_LIFETIME_HOURS, 8 h por omisión) desde el login.
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


def save_session(config, email, user, cookies, token=None, login_at=None):
    from datetime import datetime, timezone
    config["session"] = {
        "email": email,
        "user": user,
        "cookies": cookies or {},
        "token": token,
        "saved_at": datetime.now(timezone.utc).isoformat(),
        "login_at": login_at,
    }
    return save(config)


def clear_session(config):
    config["session"] = {"email": None, "user": None, "cookies": None,
                         "token": None, "saved_at": None, "login_at": None}
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
    ep = config.get("endpoints", {})
    login = str(ep.get("login_base_url", "")).rstrip("/")
    books = str(ep.get("books_base_url", "")).rstrip("/")
    try:
        timeout = int(ep.get("timeout", 8))
    except (TypeError, ValueError):
        timeout = 8
    try:
        poll = int(ep.get("poll", 15))
    except (TypeError, ValueError):
        poll = 15
    return login, books, max(timeout, 2), max(poll, 5)
