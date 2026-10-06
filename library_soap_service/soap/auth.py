"""
library_soap_service/soap/auth.py
Verificacion de JWT del microservicio de libros.

La implementacion vive ahora en el paquete compartido
packages/library_common (library_common.jwt_auth), para que los seis
microservicios verifiquen los tokens con el MISMO codigo: mismo
algoritmo, mismos claims obligatorios y la misma lista de revocacion en
Redis. Este modulo solo reexpone los decoradores.

CAMBIOS DE COMPORTAMIENTO respecto a la version anterior
--------------------------------------------------------
1. Codigos corregidos. Antes un token invalido o caducado devolvia 403;
   ahora devuelve 401, y el 403 queda reservado para "el token es bueno
   pero tu rol no alcanza". Es lo que pide el enunciado y lo que esperan
   los clientes HTTP: 401 = identificate otra vez, 403 = no insistas.
2. Se comprueba la REVOCACION. Antes bastaba una firma valida y un exp
   en el futuro; ahora se consulta jwt:revoked:<jti> en Redis, de modo
   que un /logout surte efecto en el acto. Si Redis no responde, la
   escritura se rechaza con 503 (fallo seguro) en lugar de aceptar una
   credencial que quiza ya fue retirada.
3. Se verifican el emisor (iss), el algoritmo del encabezado del token y
   la presencia de los claims obligatorios (user_id, role_id, jti).

Uso:
    from .auth import token_required, permission_required

    @app.post("/books")
    @permission_required("books:write")
    def create_book():
        identity = current_identity()      # user_id, role_id, role, email
        ...
"""
from library_common.jwt_auth import bearer_token, current_identity  # noqa: F401

from .shared import (  # noqa: F401
    optional_token,
    permission_required,
    roles_required,
    token_required,
)

__all__ = ["token_required", "permission_required", "roles_required",
           "optional_token", "current_identity", "bearer_token"]
