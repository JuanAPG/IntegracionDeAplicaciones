"""
apps/services/users/users/shared.py
Piezas compartidas del servicio, creadas una sola vez: PostgreSQL, Redis,
verificador de JWT, resolutor de roles, negociador XML/JSON y los
decoradores de autorizacion.

Se construyen aqui (y no en app.py) para que las pruebas puedan
sustituirlas —un Redis simulado, un repositorio simulado— sin levantar la
aplicacion completa.
"""
from . import _bootstrap  # noqa: F401
from . import config
from library_common.jwt_auth import make_auth

store, database, codec, negotiator, resolver = config.SHARED.bootstrap()

# token_required           cualquier JWT valido (firma, algoritmo, exp,
#                          claims obligatorios, y jti no revocado)
# permission_required(p)   lo anterior + que el rol tenga el permiso p
#                          (401 si el token no sirve, 403 si el rol no alcanza)
# roles_required(n)        lo anterior, decidiendo por nombre de rol
# optional_token           acepta con o sin token; si viene, se verifica
#                          de verdad y queda en current_identity()
token_required, permission_required, roles_required, optional_token = make_auth(
    codec, resolver.as_callable())
