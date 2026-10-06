"""
library_soap_service/soap/shared.py
Piezas compartidas del servicio de libros, creadas una sola vez: cliente
de Redis, verificador de JWT y resolutor de roles.

Este servicio NO emite tokens; solo los verifica. El emisor es el
microservicio de login, con el mismo JWT_SECRET_KEY.
"""
from . import _bootstrap  # noqa: F401
from . import config
from . import db
from library_common.jwt_auth import JwtCodec, make_auth
from library_common.redis_store import RedisStore
from library_common.roles import RoleResolver


class _DatabaseAdapter:
    """
    Adaptador para que RoleResolver use el pool de este servicio.

    soap/db.py expone cursor() a nivel de modulo (y usa psycopg2, no
    psycopg3 como login): el resolutor solo necesita poder abrir un
    cursor de diccionarios, de modo que basta con reexponerlo.
    """
    cursor = staticmethod(db.cursor)


store = RedisStore(
    config.REDIS_URL,
    connect_timeout=config.SHARED.redis_connect_timeout,
    socket_timeout=config.SHARED.redis_socket_timeout,
    key_prefix=config.SHARED.redis_key_prefix,
    retry_cooldown=config.SHARED.redis_retry_cooldown,
    max_connections=config.SHARED.redis_max_connections,
    service="library-books")

codec = JwtCodec(
    config.JWT_SECRET,
    config.JWT_ALGORITHM,
    issuer=config.JWT_ISSUER,
    access_ttl_seconds=config.SHARED.jwt_access_ttl,
    leeway_seconds=config.SHARED.jwt_leeway,
    store=store)

resolver = RoleResolver(_DatabaseAdapter(), store,
                        ttl_seconds=config.SHARED.role_cache_ttl)

# token_required          cualquier token valido
# permission_required(p)  token valido + permiso del rol (403 si no)
token_required, permission_required, roles_required, optional_token = make_auth(
    codec, resolver.as_callable())
