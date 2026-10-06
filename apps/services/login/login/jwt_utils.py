"""
apps/services/login/login/jwt_utils.py
Compatibilidad: la emision y verificacion de JWT vive ahora en el paquete
compartido packages/library_common (library_common.jwt_auth), para que los
seis microservicios usen EXACTAMENTE el mismo codigo de firma, los mismos
claims y la misma lista de revocacion.

Este modulo se conserva porque habia codigo y documentacion apuntando a
sus dos funciones. Lo nuevo deberia usar login/sessions.py, que ademas de
emitir el token abre la sesion en Redis y entrega el refresh token.
"""
from .shared import codec


def generate_jwt(user_id, email, role, role_id=2, sid=None):
    """
    Emite un token de acceso (30 minutos) y devuelve solo la cadena.

    Nota: un token emitido por aqui NO tiene sesion ni refresh asociados.
    Para el flujo completo de /login use sessions.open_session.
    """
    token, _claims = codec.issue_access_token(
        user_id=user_id, email=email, role=role, role_id=role_id, sid=sid)
    return token


def verify_jwt(token):
    """
    Verifica firma, algoritmo, vencimiento, emisor, claims obligatorios y
    lista de revocacion. Devuelve los claims.

    Lanza library_common.errors.Unauthorized (401) si el token no sirve y
    RedisUnavailable (503) si no se pudo consultar la revocacion.
    """
    return codec.decode(token)
