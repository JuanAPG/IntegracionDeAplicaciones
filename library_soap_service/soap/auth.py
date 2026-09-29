"""
library_soap_service/soap/auth.py
Middleware de verificacion JWT para el microservicio de libros.

Disenado para ser copiado directamente en futuros microservicios:
  1. Copiar este archivo
  2. Asegurar que JWT_SECRET este en el .env raiz
  3. Aplicar @token_required a las rutas protegidas

Uso:
    from auth import token_required

    @app.post("/books")
    @token_required
    def create_book():
        # request.jwt_payload contiene los claims verificados
        ...
"""
import functools

import jwt
from flask import jsonify, request

from . import config


def _error_response(status, code, message):
    """Respuesta de error JSON consistente."""
    response = jsonify({"error": {"status": status, "code": code, "message": message}})
    response.status_code = status
    return response


def token_required(f):
    """Decorador que exige un token JWT valido en el encabezado Authorization.

    Encabezado esperado:  Authorization: Bearer <token>

    Respuestas de error:
        401 — Token ausente o malformado
        403 — Token invalido o expirado

    En caso exitoso, inyecta los claims decodificados en request.jwt_payload
    para que la ruta protegida pueda acceder a sub, email, role, etc.
    """
    @functools.wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get("Authorization", "")

        # Verificar que el encabezado exista y tenga el formato "Bearer <token>"
        if not auth_header or not auth_header.startswith("Bearer "):
            return _error_response(
                401, "unauthorized",
                "Encabezado Authorization ausente o malformado. "
                "Formato esperado: 'Bearer <token>'.")

        token = auth_header[7:].strip()  # Extraer el token despues de "Bearer "
        if not token:
            return _error_response(
                401, "unauthorized",
                "Token vacio en el encabezado Authorization.")

        # Verificar firma y expiracion
        try:
            payload = jwt.decode(
                token,
                config.JWT_SECRET,
                algorithms=[config.JWT_ALGORITHM],
            )
        except jwt.ExpiredSignatureError:
            return _error_response(
                403, "forbidden", "El token ha expirado.")
        except jwt.InvalidTokenError as exc:
            return _error_response(
                403, "forbidden", f"Token invalido: {exc}")

        # Inyectar claims para uso de la ruta protegida
        request.jwt_payload = payload
        return f(*args, **kwargs)

    return decorated
