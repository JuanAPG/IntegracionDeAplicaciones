"""
packages/library_common/library_common/roles.py
Resolucion de los permisos de un rol.

La autoridad es PostgreSQL (library.roles + library.role_permissions, ver
data/roles_migration.sql). Redis solo CACHEA el resultado, porque esta
consulta se repite en cada peticion autenticada y cambia muy poco:

    roles:perms:<role_id>  ->  ["books:write", "orders:write", ...]

Aqui el cache es OPCIONAL de verdad: si Redis no responde, se consulta
PostgreSQL y la peticion sigue. Lo que nunca se cachea es la decision de
autorizacion en si, solo la lista de permisos del rol.

El permiso "*" es un comodin y lo tiene el rol admin.
"""
import logging

from . import metrics

log = logging.getLogger("library.roles")

# Vocabulario de permisos del sistema. Se documenta aqui para que los seis
# servicios usen los mismos nombres y la migracion los siembre igual.
PERMISSIONS = (
    "users:read",        # ver cualquier cuenta (lectura administrativa)
    "users:write",       # crear, modificar, desactivar cuentas
    "users:roles",       # cambiar el rol de una cuenta
    "books:write",       # alta/baja/modificacion del catalogo
    "authors:write",     # alta/baja/modificacion de autores y sus libros
    "orders:read",       # ver cualquier pedido (lectura administrativa)
    "orders:write",      # crear pedidos a nombre de cualquier usuario
    "orders:status",     # mover el estado de un pedido (envio, entrega)
    "payments:read",     # ver cualquier pago
    "payments:write",    # registrar y aplicar pagos
)


class RoleResolver:
    """
    Convierte un role_id en su conjunto de permisos.

    database  Database compartido (PostgreSQL es la autoridad).
    store     RedisStore para el cache. Puede ser None.
    ttl       vigencia del cache, en segundos.
    """

    def __init__(self, database, store=None, ttl_seconds=300):
        self.database = database
        self.store = store
        self.ttl = int(ttl_seconds)

    def _key(self, role_id):
        return self.store.key("roles", "perms", role_id)

    def _from_database(self, role_id):
        with self.database.cursor() as cur:
            cur.execute(
                "SELECT permission FROM role_permissions WHERE role_id = %s "
                "ORDER BY permission",
                (role_id,))
            return [row["permission"] for row in cur.fetchall()]

    def permissions_of(self, role_id):
        """Conjunto de permisos del rol. Nunca lanza por culpa de Redis."""
        try:
            role_id = int(role_id)
        except (TypeError, ValueError):
            return frozenset()

        if self.store is not None:
            cached = self.store.cache_get(self._key(role_id))
            if isinstance(cached, list):
                metrics.incr("roles.cache.hit")
                return frozenset(cached)

        try:
            permissions = self._from_database(role_id)
        except Exception as exc:                       # noqa: BLE001
            # Sin permisos: la peticion se denegara con 403 en lugar de
            # concederse por error. Fallo seguro tambien aqui.
            log.error("No se pudieron leer los permisos del rol %s: %s", role_id, exc)
            metrics.incr("roles.error")
            raise

        if self.store is not None:
            self.store.cache_set(self._key(role_id), permissions, self.ttl)
        metrics.incr("roles.cache.miss")
        return frozenset(permissions)

    def invalidate(self, role_id=None):
        """
        Olvida el cache de un rol (o de todos). Lo llama el microservicio
        de usuarios cuando cambian los permisos de un rol.
        """
        if self.store is None:
            return 0
        pattern = self._key(role_id) if role_id is not None else self.store.key("roles", "perms", "*")
        return self.store.invalidate(pattern)

    def as_callable(self):
        """
        Funcion role_id -> permisos, lista para jwt_auth.make_auth.

        Devuelve un envoltorio y NO el metodo ligado directamente, para
        que la resolucion ocurra en cada llamada. Asi se puede sustituir
        permissions_of despues de construir los decoradores: las pruebas
        lo aprovechan para simular los permisos sin PostgreSQL, y un
        servicio podria cambiar de resolutor sin reconstruir sus rutas.
        """
        return lambda role_id: self.permissions_of(role_id)
