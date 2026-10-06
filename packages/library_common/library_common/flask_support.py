"""
packages/library_common/library_common/flask_support.py
Piezas de Flask que los seis microservicios comparten: CORS, manejo de
errores, metricas por peticion y el endpoint /metrics.

No hay blueprints: cada servicio registra sus rutas con @app.get/@app.post
sobre su propia instancia `app`, como exige la practica. Lo que se comparte
aqui son funciones que RECIBEN la app, no una app propia.
"""
import logging
import time

from flask import g, request
from werkzeug.exceptions import HTTPException

from . import metrics
from .errors import ApiError, DependencyUnavailable

log = logging.getLogger("library.http")


# ---------------------------------------------------------------------
# CORS
# ---------------------------------------------------------------------
def configure_cors(app, origins, *, methods=None, with_credentials=False,
                   max_age=86400, service=""):
    """
    Habilita CORS enumerando los origenes de las aplicaciones cliente.

    En produccion CORS_ORIGINS debe listar los dominios: "*" se admite
    solo para el desarrollo local y se advierte en el arranque y en
    /health. Con cookies de sesion (with_credentials=True) el navegador
    rechaza "*" directamente, de modo que ahi la lista es obligatoria.
    """
    from flask_cors import CORS

    wildcard = "*" in origins
    if wildcard and with_credentials:
        log.warning(
            "CORS_ORIGINS='*' no es compatible con cookies de sesion: "
            "enumere los origenes de las aplicaciones cliente en el .env")
    elif wildcard:
        log.warning(
            "CORS_ORIGINS='*' deja el servicio %s abierto a cualquier origen: "
            "en produccion enumere los origenes de las aplicaciones cliente",
            service or app.name)

    CORS(
        app,
        resources={r"/*": {"origins": origins}},
        methods=methods or ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "Accept", "Origin", "X-Requested-With",
                       "Authorization"],
        expose_headers=["Content-Type", "Content-Length", "X-Total-Count",
                        "X-Cache", "Location"],
        supports_credentials=with_credentials,
        max_age=max_age,
    )
    return wildcard


# ---------------------------------------------------------------------
# Cabeceras de seguridad
# ---------------------------------------------------------------------
def install_security_headers(app):
    """
    Cabeceras minimas para una API que viaja por HTTP (el proyecto no
    tiene certificado, de modo que no se emite HSTS: anunciar HTTPS sin
    tenerlo solo rompe el acceso).
    """
    @app.after_request
    def _headers(response):                            # noqa: ANN202
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        # Las respuestas con datos del usuario no deben quedar en cache
        # de proxys intermedios; el cache de verdad es el de Redis, del
        # lado del servidor, donde se puede invalidar.
        if response.headers.get("X-Cache") is None:
            response.headers.setdefault("Cache-Control", "no-store")
        return response


# ---------------------------------------------------------------------
# Metricas por peticion
# ---------------------------------------------------------------------
def register_request_metrics(app, service):
    """Cuenta peticiones, codigos de respuesta y latencia por metodo."""

    @app.before_request
    def _start_timer():                                # noqa: ANN202
        g._started_at = time.perf_counter()

    @app.after_request
    def _record(response):                             # noqa: ANN202
        started = getattr(g, "_started_at", None)
        if started is not None:
            metrics.observe(f"http.{request.method.lower()}",
                            (time.perf_counter() - started) * 1000.0)
        metrics.incr("http.requests")
        metrics.incr(f"http.status.{response.status_code // 100}xx")
        if response.status_code in (401, 403, 503):
            metrics.incr(f"http.status.{response.status_code}")
        return response


# ---------------------------------------------------------------------
# Manejo de errores: una sola forma de responder, en JSON o en XML
# ---------------------------------------------------------------------
def register_error_handlers(app, negotiator, *, debug=False, service=""):
    """
    Traduce las excepciones a la respuesta de error comun.

    Importante: los 500 nunca filtran el detalle interno salvo con
    DEBUG=true, para no revelar nombres de tablas ni rutas del servidor.
    """
    service_log = logging.getLogger(f"library.{service or 'service'}")

    @app.errorhandler(ApiError)
    def _api_error(exc):                               # noqa: ANN202
        if exc.status >= 500:
            service_log.error("%s: %s", exc.code, exc.message)
        return negotiator.error_response(exc.status, exc.code, exc.message, exc.details)

    @app.errorhandler(DependencyUnavailable)
    def _dependency(exc):                              # noqa: ANN202
        service_log.error("Dependencia no disponible (%s): %s", exc.code, exc.message)
        return negotiator.error_response(exc.status, exc.code, exc.message, exc.details)

    @app.errorhandler(HTTPException)
    def _http(exc):                                    # noqa: ANN202
        code = {400: "bad_request", 404: "not_found", 405: "method_not_allowed",
                413: "payload_too_large", 415: "unsupported_media_type",
                429: "too_many_requests"}.get(exc.code, "http_error")
        return negotiator.error_response(exc.code, code,
                                         exc.description or exc.name)

    @app.errorhandler(Exception)
    def _unexpected(exc):                              # noqa: ANN202
        service_log.exception("Error no controlado")
        metrics.incr("http.unhandled")
        details = [f"{type(exc).__name__}: {exc}"] if debug else []
        return negotiator.error_response(500, "internal_error",
                                         "Error interno del microservicio.", details)


# ---------------------------------------------------------------------
# /metrics
# ---------------------------------------------------------------------
def metrics_payload(service, store=None, extra=None):
    """
    Cuerpo del endpoint /metrics: contadores del proceso mas, si Redis
    responde, el estado del servidor Redis compartido.
    """
    payload = {"service": service}
    payload.update(metrics.snapshot())
    if store is not None:
        info = store.server_info()
        payload["redis"] = info or {"status": "unreachable",
                                    "lastError": store.last_error}
    if extra:
        payload.update(extra)
    return payload


def register_metrics_endpoint(app, negotiator, service, store=None, extra=None):
    """Publica GET /metrics en el servicio. Lectura publica: no lleva datos
    de usuarios, solo contadores agregados."""

    @app.get("/metrics")
    def _metrics():                                    # noqa: ANN202
        payload = metrics_payload(service, store,
                                  extra() if callable(extra) else extra)
        return negotiator.dict_response("metrics", payload)

    return _metrics
