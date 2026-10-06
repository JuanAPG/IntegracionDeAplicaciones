"""
packages/library_common/library_common/redis_store.py
Capa compartida de Redis: sesiones, refresh tokens, revocacion de JWT,
cache del catalogo y coordinacion de tareas temporales.

PostgreSQL sigue siendo la fuente principal de datos. Redis guarda solo
estado efimero y con TTL:

    session:<sid>            sesion del usuario            8 h (renovable)
    refresh:<sha256>         refresh token, un solo uso    8 h
    jwt:revoked:<jti>        lista de revocacion           lo que le quede al token
    books:list:<filtros>     listado del catalogo          TTL corto
    books:<isbn>             un libro por ISBN             TTL corto
    roles:perms:<role_id>    permisos del rol              TTL medio
    lock:<nombre>            cerrojo de tarea temporal     TTL corto

DOS POLITICAS DE FALLO, a proposito distintas
---------------------------------------------
1. Cache (cache_get / cache_set / invalidate): Redis es OPCIONAL. Si no
   responde, un fallo se trata como ausencia de cache y la peticion sigue
   contra PostgreSQL. El cliente no se entera.
2. Sesiones, refresh y revocacion (todo lo que lleva "strict"): Redis es
   OBLIGATORIO y el fallo es SEGURO. Si no se puede comprobar si un token
   fue revocado, el token NO se acepta: se responde 503 en lugar de
   arriesgarse a honrar una credencial revocada.

Nunca se escribe en el log la URL con contrasena, ni tokens, ni
contrasenas: se registra solo la forma redactada (env.redacted).
"""
import hashlib
import json
import logging
import random
import threading
import time
from contextlib import contextmanager

from . import env, metrics
from .errors import RedisUnavailable

log = logging.getLogger("library.redis")

# Devuelve el valor previo y borra la clave en un solo paso atomico. Se
# usa para que un refresh token sea de un solo uso incluso si dos
# peticiones llegan a la vez (GETDEL existe desde Redis 6.2; este script
# funciona tambien en versiones anteriores).
_LUA_GETDEL = """
local value = redis.call('GET', KEYS[1])
if value then redis.call('DEL', KEYS[1]) end
return value
"""

# Renueva el TTL solo si la clave existe, para que una sesion viva
# mientras se use y caduque sola cuando se deje de usar.
_LUA_TOUCH = """
if redis.call('EXISTS', KEYS[1]) == 1 then
  return redis.call('EXPIRE', KEYS[1], ARGV[1])
end
return 0
"""


class RedisStore:
    """
    Cliente de Redis con reconexion, tiempos de espera y metricas.

    La conexion se crea de forma perezosa: el servicio arranca aunque
    Redis todavia no este disponible, igual que hace db.py con
    PostgreSQL, para que /health pueda informar el fallo en lugar de
    morir al importar.
    """

    def __init__(self, url, *, connect_timeout=2.0, socket_timeout=2.0,
                 key_prefix="", retry_cooldown=5.0, max_connections=20,
                 service="library"):
        self.url = url or ""
        self.connect_timeout = connect_timeout
        self.socket_timeout = socket_timeout
        self.key_prefix = key_prefix or ""
        self.retry_cooldown = retry_cooldown
        self.max_connections = max_connections
        self.service = service

        self._client = None
        self._lock = threading.Lock()
        # Interruptor: tras un fallo no se vuelve a intentar durante
        # retry_cooldown segundos en las operaciones de cache, para no
        # pagar el tiempo de espera en cada peticion mientras Redis esta
        # caido. Las operaciones estrictas siempre lo intentan.
        self._down_until = 0.0
        self._last_error = None

    # -----------------------------------------------------------------
    # Conexion
    # -----------------------------------------------------------------
    @property
    def configured(self):
        return bool(self.url)

    def _connect(self):
        import redis

        return redis.Redis.from_url(
            self.url,
            decode_responses=True,
            socket_timeout=self.socket_timeout,
            socket_connect_timeout=self.connect_timeout,
            # Si la conexion lleva tiempo ociosa, redis-py la comprueba
            # con un PING antes de reutilizarla: evita el primer error
            # tras un reinicio del servidor o un corte de NAT.
            health_check_interval=30,
            retry_on_timeout=True,
            max_connections=self.max_connections,
            client_name=f"{self.service}",
        )

    def client(self):
        """Cliente de Redis, creado en el primer uso. Lanza si no se puede."""
        if not self.configured:
            raise RedisUnavailable(
                "Redis no esta configurado.",
                ["Fije REDIS_URL en el .env de la raiz "
                 "(formato redis://:password@host:6379/0)."])
        if self._client is None:
            with self._lock:
                if self._client is None:
                    try:
                        self._client = self._connect()
                    except Exception as exc:          # noqa: BLE001
                        self._note_failure(exc)
                        raise RedisUnavailable(
                            "No se pudo crear el cliente de Redis.",
                            [str(exc).strip()]) from exc
        return self._client

    def _note_failure(self, exc):
        self._last_error = str(exc).strip()
        self._down_until = time.time() + self.retry_cooldown
        metrics.incr("redis.error")
        log.warning("Redis no responde (%s): %s",
                    env.redacted(self.url), self._last_error)

    def _note_success(self):
        if self._down_until:
            log.info("Redis respondio de nuevo (%s)", env.redacted(self.url))
            metrics.incr("redis.recovered")
        self._down_until = 0.0
        self._last_error = None

    @property
    def probably_down(self):
        """True mientras dure el enfriamiento tras un fallo."""
        return time.time() < self._down_until

    def ping(self):
        """(ok, detalle). Lo usa /health; nunca lanza."""
        if not self.configured:
            return False, "REDIS_URL sin fijar"
        try:
            with metrics.timed("redis.ping"):
                self.client().ping()
            self._note_success()
            return True, "ok"
        except Exception as exc:                       # noqa: BLE001
            self._note_failure(exc)
            return False, str(exc).strip()

    def server_info(self):
        """Datos del servidor Redis para /metrics. Devuelve {} si no responde."""
        try:
            info = self.client().info()
        except Exception:                              # noqa: BLE001
            return {}
        hits = info.get("keyspace_hits", 0)
        misses = info.get("keyspace_misses", 0)
        total = hits + misses
        return {
            "version": info.get("redis_version"),
            "uptimeSeconds": info.get("uptime_in_seconds"),
            "connectedClients": info.get("connected_clients"),
            "usedMemoryHuman": info.get("used_memory_human"),
            "keyspaceHits": hits,
            "keyspaceMisses": misses,
            "hitRate": round(hits / total, 4) if total else None,
            "evictedKeys": info.get("evicted_keys"),
            "expiredKeys": info.get("expired_keys"),
        }

    @property
    def last_error(self):
        return self._last_error

    # -----------------------------------------------------------------
    # Claves
    # -----------------------------------------------------------------
    def key(self, *parts):
        """Compone una clave con el prefijo opcional del entorno."""
        tail = ":".join(str(p) for p in parts)
        return f"{self.key_prefix}{tail}" if self.key_prefix else tail

    # -----------------------------------------------------------------
    # Operaciones ESTRICTAS: fallan de forma segura (503), nunca en silencio
    # -----------------------------------------------------------------
    def _strict(self, operation, name):
        try:
            with metrics.timed(f"redis.{name}"):
                result = operation(self.client())
            self._note_success()
            return result
        except RedisUnavailable:
            raise
        except Exception as exc:                       # noqa: BLE001
            self._note_failure(exc)
            raise RedisUnavailable(
                "Redis no esta disponible y la operacion no puede continuar sin el.",
                [str(exc).strip(),
                 f"Destino: {env.redacted(self.url)}",
                 "Sesiones, refresh tokens y revocacion de JWT dependen de Redis."
                 ]) from exc

    def strict_set(self, key, value, ttl_seconds, only_if_absent=False):
        payload = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
        return self._strict(
            lambda c: c.set(key, payload, ex=int(ttl_seconds), nx=only_if_absent),
            "set")

    def strict_get(self, key, as_json=True):
        raw = self._strict(lambda c: c.get(key), "get")
        if raw is None or not as_json:
            return raw
        try:
            return json.loads(raw)
        except (TypeError, ValueError):
            return raw

    def strict_delete(self, *keys):
        if not keys:
            return 0
        return self._strict(lambda c: c.delete(*keys), "delete")

    def strict_exists(self, key):
        return bool(self._strict(lambda c: c.exists(key), "exists"))

    def strict_getdel(self, key, as_json=True):
        """Lee y borra en un solo paso atomico (refresh de un solo uso)."""
        raw = self._strict(lambda c: c.eval(_LUA_GETDEL, 1, key), "getdel")
        if raw is None or not as_json:
            return raw
        try:
            return json.loads(raw)
        except (TypeError, ValueError):
            return raw

    def strict_touch(self, key, ttl_seconds):
        """Renueva el TTL solo si la clave sigue viva."""
        return bool(self._strict(
            lambda c: c.eval(_LUA_TOUCH, 1, key, int(ttl_seconds)), "touch"))

    # -----------------------------------------------------------------
    # Cache: Redis es OPCIONAL. Un fallo se trata como ausencia de cache.
    # -----------------------------------------------------------------
    def cache_get(self, key):
        if not self.configured or self.probably_down:
            metrics.incr("redis.cache.skipped")
            return None
        try:
            with metrics.timed("redis.cache.get"):
                raw = self.client().get(key)
            self._note_success()
        except Exception as exc:                       # noqa: BLE001
            self._note_failure(exc)
            metrics.incr("redis.cache.degraded")
            return None
        if raw is None:
            metrics.incr("redis.cache.miss")
            return None
        try:
            value = json.loads(raw)
        except (TypeError, ValueError):
            metrics.incr("redis.cache.miss")
            return None
        metrics.incr("redis.cache.hit")
        return value

    def cache_set(self, key, value, ttl_seconds, jitter=0.1):
        """
        Guarda una entrada de cache. Nunca lanza.

        El TTL recibe una variacion aleatoria de +-10 % para que muchas
        claves creadas a la vez no expiren todas en el mismo segundo
        (estampida de cache contra PostgreSQL).
        """
        if not self.configured or self.probably_down:
            metrics.incr("redis.cache.skipped")
            return False
        ttl = int(ttl_seconds)
        if jitter:
            spread = max(1, int(ttl * jitter))
            ttl = max(1, ttl + random.randint(-spread, spread))
        try:
            with metrics.timed("redis.cache.set"):
                self.client().set(key, json.dumps(value, ensure_ascii=False,
                                                  default=str), ex=ttl)
            self._note_success()
            metrics.incr("redis.cache.set")
            return True
        except Exception as exc:                       # noqa: BLE001
            self._note_failure(exc)
            metrics.incr("redis.cache.degraded")
            return False

    def invalidate(self, *patterns):
        """
        Borra por patron (SCAN + UNLINK, nunca KEYS, que bloquea el
        servidor). Se llama despues de cada POST/PUT/PATCH/DELETE.

        Devuelve cuantas claves se borraron. Nunca lanza: si Redis no
        responde, las claves caducaran solas por su TTL corto.
        """
        if not self.configured or not patterns:
            return 0
        removed = 0
        try:
            client = self.client()
            for pattern in patterns:
                batch = []
                for found in client.scan_iter(match=pattern, count=500):
                    batch.append(found)
                    if len(batch) >= 500:
                        removed += self._unlink(client, batch)
                        batch = []
                if batch:
                    removed += self._unlink(client, batch)
            self._note_success()
        except Exception as exc:                       # noqa: BLE001
            self._note_failure(exc)
            metrics.incr("redis.cache.degraded")
            log.warning("No se pudo invalidar %s: las claves caducaran por TTL",
                        ", ".join(patterns))
            return removed
        if removed:
            metrics.incr("redis.cache.invalidated", removed)
            log.info("Cache invalidado: %s clave(s) por %s", removed, ", ".join(patterns))
        return removed

    @staticmethod
    def _unlink(client, keys):
        try:
            return client.unlink(*keys)       # no bloquea: libera en segundo plano
        except Exception:                                  # noqa: BLE001 - Redis < 4
            return client.delete(*keys)

    # -----------------------------------------------------------------
    # Sesiones  (estrictas)
    # -----------------------------------------------------------------
    def session_key(self, sid):
        return self.key("session", sid)

    def save_session(self, sid, data, ttl_seconds):
        return self.strict_set(self.session_key(sid), data, ttl_seconds)

    def load_session(self, sid, ttl_seconds=None):
        """
        Devuelve la sesion o None. Si se pasa ttl_seconds, renueva la
        vigencia (ventana deslizante: la sesion vive mientras se use).
        """
        data = self.strict_get(self.session_key(sid))
        if data is not None and ttl_seconds:
            self.strict_touch(self.session_key(sid), ttl_seconds)
        return data

    def drop_session(self, sid):
        return self.strict_delete(self.session_key(sid))

    # -----------------------------------------------------------------
    # Indice de sesiones por usuario
    #
    # session:<sid> se busca por sid, pero hace falta la pregunta
    # inversa: "cuales son las sesiones de este usuario". La necesita el
    # microservicio de USUARIOS, para que al desactivar una cuenta o
    # cambiarle el rol sus tokens dejen de servir en el acto, sin esperar
    # los 30 minutos del vencimiento.
    #
    #     user:sessions:<user_id>  ->  conjunto de sid
    #
    # El conjunto caduca junto con la sesion mas larga que contenga, de
    # modo que no crece para siempre.
    # -----------------------------------------------------------------
    def user_sessions_key(self, user_id):
        return self.key("user", "sessions", user_id)

    def track_session(self, user_id, sid, ttl_seconds):
        """Apunta el sid en el indice del usuario."""
        key = self.user_sessions_key(user_id)

        def operation(client):
            pipe = client.pipeline()
            pipe.sadd(key, sid)
            pipe.expire(key, int(ttl_seconds))
            return pipe.execute()

        return self._strict(operation, "track_session")

    def untrack_session(self, user_id, sid):
        return self._strict(
            lambda c: c.srem(self.user_sessions_key(user_id), sid), "untrack_session")

    def sessions_of(self, user_id):
        """Los sid vivos del usuario (los caducados se limpian al pasar)."""
        sids = self._strict(
            lambda c: c.smembers(self.user_sessions_key(user_id)), "sessions_of") or set()
        vivos = []
        caducados = []
        for sid in sids:
            if self.strict_exists(self.session_key(sid)):
                vivos.append(sid)
            else:
                caducados.append(sid)
        if caducados:
            self._strict(
                lambda c: c.srem(self.user_sessions_key(user_id), *caducados),
                "untrack_session")
        return vivos

    def revoke_user_sessions(self, user_id, access_ttl, reason="account_changed"):
        """
        Cierra TODAS las sesiones de un usuario y revoca sus tokens de
        acceso. Lo usa el microservicio de usuarios al desactivar una
        cuenta, cambiarle el rol o cambiarle la contrasena.

        Devuelve cuantas sesiones se cerraron.
        """
        cerradas = 0
        for sid in self.sessions_of(user_id):
            record = self.strict_get(self.session_key(sid))
            if isinstance(record, dict):
                jti = record.get("access_jti")
                if jti:
                    self.revoke_jti(jti, access_ttl, reason=reason)
                refresh_hash = record.get("refresh_hash")
                if refresh_hash:
                    self.strict_delete(self.refresh_key(refresh_hash, hashed=True))
            self.strict_delete(self.session_key(sid))
            self.untrack_session(user_id, sid)
            cerradas += 1
        if cerradas:
            log.info("Revocadas %s sesion(es) de user_id=%s (%s)",
                     cerradas, user_id, reason)
        return cerradas

    # -----------------------------------------------------------------
    # Refresh tokens  (estrictos, de un solo uso)
    # -----------------------------------------------------------------
    @staticmethod
    def hash_token(raw):
        """En Redis vive solo el SHA-256: leer la base no da tokens usables."""
        return hashlib.sha256((raw or "").encode("utf-8")).hexdigest()

    def refresh_key(self, raw_or_hash, hashed=False):
        digest = raw_or_hash if hashed else self.hash_token(raw_or_hash)
        return self.key("refresh", digest)

    def save_refresh(self, raw_token, data, ttl_seconds):
        return self.strict_set(self.refresh_key(raw_token), data, ttl_seconds)

    def consume_refresh(self, raw_token):
        """
        Canjea un refresh token: lo devuelve y lo borra en el mismo paso
        atomico, de modo que un token solo sirve una vez (rotacion). Un
        segundo intento con el mismo token devuelve None.
        """
        return self.strict_getdel(self.refresh_key(raw_token))

    def drop_refresh(self, raw_token):
        return self.strict_delete(self.refresh_key(raw_token))

    # -----------------------------------------------------------------
    # Revocacion de JWT  (estricta: sin Redis no se acepta ningun token)
    # -----------------------------------------------------------------
    def revoked_key(self, jti):
        return self.key("jwt", "revoked", jti)

    def revoke_jti(self, jti, ttl_seconds, reason="logout"):
        """
        Anota un jti en la lista de revocacion. El TTL es lo que le
        quedaba de vida al token: una vez vencido, la firma ya no vale y
        la entrada deja de hacer falta, asi que Redis la limpia sola.
        """
        if not jti:
            return False
        ttl = max(int(ttl_seconds), 1)
        metrics.incr("jwt.revoked")
        return self.strict_set(self.revoked_key(jti),
                               {"reason": reason, "at": int(time.time())}, ttl)

    def is_revoked(self, jti):
        """
        True si el jti esta revocado. Lanza RedisUnavailable si no se
        puede comprobar: ante la duda, el token no se acepta.
        """
        if not jti:
            return False
        return self.strict_exists(self.revoked_key(jti))

    # -----------------------------------------------------------------
    # Coordinacion de tareas temporales
    # -----------------------------------------------------------------
    @contextmanager
    def lock(self, name, ttl_seconds=10, owner=None):
        """
        Cerrojo con TTL (SET NX EX): evita que dos peticiones hagan la
        misma tarea a la vez — por ejemplo cobrar dos veces el mismo
        pedido. El TTL garantiza que un proceso que muera no deje el
        cerrojo tomado para siempre.

        Rinde (True) si lo obtuvo y (False) si ya estaba tomado. El
        cerrojo se libera solo si sigue siendo nuestro, comparando el
        dueno, para no soltar el de otro proceso tras una expiracion.
        """
        key = self.key("lock", name)
        token = owner or f"{self.service}:{time.time()}:{random.randint(0, 1 << 30)}"
        acquired = bool(self.strict_set(key, token, ttl_seconds, only_if_absent=True))
        try:
            yield acquired
        finally:
            if acquired:
                try:
                    self.client().eval(
                        "if redis.call('GET', KEYS[1]) == ARGV[1] then "
                        "return redis.call('DEL', KEYS[1]) end return 0",
                        1, key, token)
                except Exception:                      # noqa: BLE001
                    pass    # el TTL lo liberara

    # -----------------------------------------------------------------
    # Estado para /health y /metrics
    # -----------------------------------------------------------------
    def health(self):
        """Bloque de estado que cada servicio incrusta en su /health."""
        if not self.configured:
            return {"status": "not_configured",
                    "message": "REDIS_URL sin fijar: sesiones, revocacion y cache "
                               "no estan disponibles."}
        ok, detail = self.ping()
        block = {"status": "ok" if ok else "error",
                 "target": env.redacted(self.url)}
        if not ok:
            block["message"] = detail
        return block
