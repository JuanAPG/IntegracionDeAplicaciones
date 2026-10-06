"""
packages/library_common/library_common/errors.py
Excepciones de la API. flask_support.register_error_handlers las traduce
a una respuesta (JSON o XML) con el codigo HTTP correspondiente.

Es la misma jerarquia que ya usaban login y books, movida aqui para que
los seis servicios devuelvan errores con la misma forma:

    {"error": {"status": 401, "code": "unauthorized",
               "message": "...", "details": [...]}}
"""


class ApiError(Exception):
    status = 400
    code = "bad_request"

    def __init__(self, message, details=None, status=None, code=None):
        super().__init__(message)
        self.message = message
        self.details = list(details) if details else []
        if status is not None:
            self.status = status
        if code is not None:
            self.code = code


class ValidationError(ApiError):
    status = 400
    code = "validation_error"


class Unauthorized(ApiError):
    """401: falta el token, esta malformado, vencio o fue revocado."""
    status = 401
    code = "unauthorized"


class Forbidden(ApiError):
    """403: el token es valido pero el rol no alcanza para la operacion."""
    status = 403
    code = "forbidden"


class EmailNotVerified(ApiError):
    status = 403
    code = "email_not_verified"


class NotFound(ApiError):
    status = 404
    code = "not_found"


class Conflict(ApiError):
    status = 409
    code = "conflict"


class Gone(ApiError):
    status = 410
    code = "gone"


class UnsupportedMedia(ApiError):
    status = 415
    code = "unsupported_media_type"


class DependencyUnavailable(ApiError):
    """503: una dependencia de la que no se puede prescindir esta caida."""
    status = 503
    code = "dependency_unavailable"


class RedisUnavailable(DependencyUnavailable):
    """
    503: Redis no responde y la operacion NO puede continuar sin el.

    Se usa solo en las operaciones que deben fallar de forma segura:
    sesiones, refresh tokens y consulta de la lista de revocacion. Las
    lecturas cacheadas nunca la lanzan: ahi Redis es opcional y un fallo
    se trata como ausencia de cache.
    """
    code = "redis_unavailable"


class DatabaseUnavailable(DependencyUnavailable):
    code = "database_unavailable"
