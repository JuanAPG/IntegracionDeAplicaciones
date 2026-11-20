"""Traduce rutas de servicios al espacio del gateway sin duplicar el recurso."""
from urllib.parse import urlsplit

def service_url(base, path):
    base = base.rstrip("/")
    suffix = urlsplit(base).path.rstrip("/")
    service = suffix.rsplit("/", 1)[-1]
    if suffix.endswith("/api/" + service) and service in {"login", "books", "users", "authors", "pedidos", "pagos"}:
        if path == "/" + service or path.startswith("/" + service + "/") or path.startswith("/" + service + "?"):
            path = path[len(service) + 1:]
    return base + path
