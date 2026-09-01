"""
soap/errors.py
Excepciones de la API. app.py las traduce a una respuesta (JSON o XML)
con el codigo HTTP correspondiente.
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


class NotFound(ApiError):
    status = 404
    code = "not_found"


class Conflict(ApiError):
    status = 409
    code = "conflict"


class UnsupportedMedia(ApiError):
    status = 415
    code = "unsupported_media_type"
