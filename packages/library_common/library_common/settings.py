"""
packages/library_common/library_common/settings.py
Configuracion comun de los microservicios, leida SOLO de variables de
entorno. Ninguna credencial esta escrita en el codigo.

Cada servicio hace, en su propio config.py:

    from library_common.settings import CommonSettings
    S = CommonSettings(__file__, depth=4, service="users",
                       default_port=5002, namespace="urn:library:users:1.0")

y despues agrega lo suyo. Asi los seis servicios comparten, sin copiarlo:
el secreto del JWT, la URL de Redis, las credenciales de PostgreSQL y los
tiempos de expiracion.

Nombres de los secretos compartidos
-----------------------------------
    JWT_SECRET_KEY   secreto de firma HS256, IGUAL en los seis servicios.
                     Se acepta JWT_SECRET como nombre anterior para no
                     romper los despliegues que ya existen.
    REDIS_URL        redis://:password@host:6379/0
    PG*              credenciales de PostgreSQL

Tiempos de expiracion coherentes
--------------------------------
    JWT_ACCESS_TTL_MINUTES   30   token de acceso (lo fija el enunciado)
    JWT_REFRESH_TTL_HOURS     8   refresh token en Redis, un solo uso
    SESSION_TTL_HOURS         8   sesion en Redis, ventana deslizante
    CACHE_TTL_SECONDS        30   cache de listados del catalogo
    CACHE_DETAIL_TTL_SECONDS 60   cache de un recurso por clave
"""
from . import env


class CommonSettings:
    def __init__(self, service_file, depth, *, service, default_port,
                 namespace, issuer="library-login-service"):
        self.project_root, self.service_root = env.load_dotenvs(service_file, depth)
        self.service = service
        self.namespace = env.get("XML_NAMESPACE", namespace)

        # -------------------------------------------------------------
        # Servidor
        # -------------------------------------------------------------
        self.host = env.get("HOST", "0.0.0.0")
        self.port = env.get_int("PORT", default_port)
        self.debug = env.get_bool("DEBUG", False)
        self.api_prefix = env.get("API_PREFIX", "").rstrip("/")
        self.xml_version = env.get("XML_VERSION", "1.0")
        self.default_format = env.get("DEFAULT_FORMAT", "xml").lower()

        # -------------------------------------------------------------
        # JWT  (el emisor es solo login; los demas verifican)
        # -------------------------------------------------------------
        self.jwt_secret = env.get("JWT_SECRET_KEY") or env.get("JWT_SECRET", "")
        self.jwt_algorithm = env.get("JWT_ALGORITHM", "HS256")
        self.jwt_issuer = env.get("JWT_ISSUER", issuer)
        self.jwt_access_ttl = env.get_int("JWT_ACCESS_TTL_MINUTES", 30) * 60
        self.jwt_refresh_ttl = env.get_int("JWT_REFRESH_TTL_HOURS", 8) * 3600
        self.jwt_leeway = env.get_int("JWT_LEEWAY_SECONDS", 10)
        # Margen con el que un cliente deberia renovar antes de caducar.
        self.jwt_renew_before = env.get_int("JWT_RENEW_BEFORE_SECONDS", 300)

        # -------------------------------------------------------------
        # Redis (capa compartida)
        # -------------------------------------------------------------
        self.redis_url = env.get("REDIS_URL", "")
        self.redis_connect_timeout = env.get_float("REDIS_CONNECT_TIMEOUT", 2.0)
        self.redis_socket_timeout = env.get_float("REDIS_SOCKET_TIMEOUT", 2.0)
        self.redis_retry_cooldown = env.get_float("REDIS_RETRY_COOLDOWN", 5.0)
        self.redis_max_connections = env.get_int("REDIS_MAX_CONNECTIONS", 20)
        self.redis_key_prefix = env.get("REDIS_KEY_PREFIX", "")
        self.session_ttl = env.get_int("SESSION_TTL_HOURS", 8) * 3600
        self.cache_ttl = env.get_int("CACHE_TTL_SECONDS", 30)
        self.cache_detail_ttl = env.get_int("CACHE_DETAIL_TTL_SECONDS", 60)
        self.role_cache_ttl = env.get_int("ROLE_CACHE_TTL_SECONDS", 300)

        # -------------------------------------------------------------
        # PostgreSQL (fuente principal de datos)
        # -------------------------------------------------------------
        self.pg = {
            "host": env.get("PGHOST", "localhost"),
            "port": env.get_int("PGPORT", 5432),
            "dbname": env.get("PGDATABASE", "library_db"),
            "user": env.get("PGUSER", "library_user"),
            "password": env.get("PGPASSWORD", ""),
            "schema": env.get("PGSCHEMA", "library"),
            "pool_min": env.get_int("DB_POOL_MIN", 1),
            "pool_max": env.get_int("DB_POOL_MAX", 10),
            "connect_timeout": env.get_int("DB_CONNECT_TIMEOUT", 5),
            "application_name": f"library-{service}-service",
        }

        # -------------------------------------------------------------
        # CORS: en produccion enumere los origenes de los clientes
        # -------------------------------------------------------------
        self.cors_origins = env.get_list("CORS_ORIGINS", "*")
        self.cors_max_age = env.get_int("CORS_MAX_AGE", 86400)

        # -------------------------------------------------------------
        # Paginacion
        # -------------------------------------------------------------
        self.default_limit = env.get_int("DEFAULT_LIMIT", 50)
        self.max_limit = env.get_int("MAX_LIMIT", 200)

    # -----------------------------------------------------------------
    # Estado de los secretos (lo reporta /health, nunca su valor)
    # -----------------------------------------------------------------
    @property
    def jwt_configured(self):
        return env.is_real(self.jwt_secret)

    @property
    def redis_configured(self):
        return bool(self.redis_url)

    @property
    def cors_wildcard(self):
        return "*" in self.cors_origins

    def warnings(self):
        """Avisos de configuracion que /health publica tal cual."""
        items = []
        if not self.jwt_configured:
            items.append("JWT_SECRET_KEY sin fijar: el servicio no puede "
                         "verificar tokens y rechazara toda escritura.")
        if not self.redis_configured:
            items.append("REDIS_URL sin fijar: sesiones, revocacion de JWT y "
                         "cache no estan disponibles.")
        if self.cors_wildcard:
            items.append("CORS_ORIGINS='*': en produccion enumere los origenes "
                         "de las aplicaciones cliente.")
        if self.debug:
            items.append("DEBUG=true: los errores 500 devuelven detalle interno.")
        return items

    # -----------------------------------------------------------------
    # Fabricas de los objetos compartidos
    # -----------------------------------------------------------------
    def build_store(self):
        from .redis_store import RedisStore

        return RedisStore(
            self.redis_url,
            connect_timeout=self.redis_connect_timeout,
            socket_timeout=self.redis_socket_timeout,
            key_prefix=self.redis_key_prefix,
            retry_cooldown=self.redis_retry_cooldown,
            max_connections=self.redis_max_connections,
            service=f"library-{self.service}")

    def build_database(self):
        from .db import Database

        return Database(**self.pg)

    def build_codec(self, store):
        from .jwt_auth import JwtCodec

        return JwtCodec(self.jwt_secret, self.jwt_algorithm,
                        issuer=self.jwt_issuer,
                        access_ttl_seconds=self.jwt_access_ttl,
                        leeway_seconds=self.jwt_leeway,
                        store=store)

    def build_negotiator(self):
        from .negotiation import Negotiator

        return Negotiator(self.namespace, self.default_format)

    def build_resolver(self, database, store):
        from .roles import RoleResolver

        return RoleResolver(database, store, ttl_seconds=self.role_cache_ttl)

    def bootstrap(self):
        """
        Crea de una vez las cinco piezas compartidas que usa un servicio:
        (store, database, codec, negotiator, resolver).
        """
        store = self.build_store()
        database = self.build_database()
        codec = self.build_codec(store)
        negotiator = self.build_negotiator()
        resolver = self.build_resolver(database, store)
        return store, database, codec, negotiator, resolver
