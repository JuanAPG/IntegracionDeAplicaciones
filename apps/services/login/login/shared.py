"""
apps/services/login/login/shared.py
Las piezas compartidas del servicio, creadas una sola vez: cliente de
Redis, emisor/verificador de JWT, resolutor de roles y negociador de
formato.

Se crean aqui y no en app.py para que las pruebas puedan sustituirlas
(por ejemplo, un Redis simulado) sin levantar la aplicacion completa.
"""
from . import _bootstrap  # noqa: F401
from . import config
from . import db
from library_common.jwt_auth import JwtCodec, make_auth
from library_common.negotiation import Negotiator
from library_common.redis_store import RedisStore
from library_common.roles import RoleResolver


class _DatabaseAdapter:
    """
    Adaptador minimo para que RoleResolver use el pool que ya tiene este
    servicio (login/db.py expone cursor() a nivel de modulo, no una clase).
    """
    cursor = staticmethod(db.cursor)


store = RedisStore(
    config.REDIS_URL,
    connect_timeout=config.SHARED.redis_connect_timeout,
    socket_timeout=config.SHARED.redis_socket_timeout,
    key_prefix=config.SHARED.redis_key_prefix,
    retry_cooldown=config.SHARED.redis_retry_cooldown,
    max_connections=config.SHARED.redis_max_connections,
    service="library-login")

codec = JwtCodec(
    config.JWT_SECRET,
    config.JWT_ALGORITHM,
    issuer=config.JWT_ISSUER,
    access_ttl_seconds=config.JWT_ACCESS_TTL,
    leeway_seconds=config.SHARED.jwt_leeway,
    store=store)

resolver = RoleResolver(_DatabaseAdapter(), store,
                        ttl_seconds=config.SHARED.role_cache_ttl)

negotiator = Negotiator(config.XML_NAMESPACE, config.DEFAULT_FORMAT)

# Decoradores de autorizacion. En login solo se usa token_required (para
# /logout con Bearer) y permission_required no hace falta: la
# administracion de cuentas vive en el microservicio de usuarios.
token_required, permission_required, roles_required, optional_token = make_auth(
    codec, resolver.as_callable())
