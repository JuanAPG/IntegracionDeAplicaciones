"""
packages/library_common/library_common/testing.py
Dobles de prueba para que los seis microservicios se puedan probar SIN
PostgreSQL y SIN Redis, igual que ya hacia test/test_login_mocked.py con
el repositorio y el sendmail.

Se entrega dentro del paquete compartido, y no copiado en cada servicio,
porque la gracia es que las seis baterias de pruebas ejerciten el MISMO
doble: si el doble y el Redis de verdad se separan, se separan para todos
a la vez y se nota.

    FakeRedisClient   Redis en memoria: lo justo que usa redis_store
                      (get/set/delete/exists/scan/unlink/eval/info).
                      Respeta los TTL y permite adelantar el reloj.
    BrokenRedisClient Redis que falla en todo: sirve para comprobar las
                      dos politicas de fallo (cache degrada en silencio,
                      sesion y revocacion fallan con 503).
    install           enchufa un doble en un RedisStore ya construido.
"""
import fnmatch
import time


class _Entry:
    __slots__ = ("value", "expires_at")

    def __init__(self, value, expires_at):
        self.value = value
        self.expires_at = expires_at


class FakeRedisClient:
    """
    Redis en memoria. Implementa solo lo que usa redis_store.RedisStore.

    El reloj es inyectable (clock) para poder comprobar la expiracion sin
    esperar de verdad: avanzar con advance(segundos).
    """

    def __init__(self, clock=None):
        self._data = {}
        self._offset = 0.0
        self._clock = clock or time.time
        self.calls = []            # traza de operaciones, util en las pruebas

    # -- reloj ------------------------------------------------------
    def _now(self):
        return self._clock() + self._offset

    def advance(self, seconds):
        """Adelanta el reloj: lo que haya caducado deja de verse."""
        self._offset += float(seconds)

    def _live(self, key):
        entry = self._data.get(key)
        if entry is None:
            return None
        if entry.expires_at is not None and entry.expires_at <= self._now():
            self._data.pop(key, None)
            return None
        return entry

    # -- comandos ---------------------------------------------------
    def ping(self):
        self.calls.append(("ping",))
        return True

    def get(self, key):
        self.calls.append(("get", key))
        entry = self._live(key)
        return entry.value if entry else None

    def set(self, key, value, ex=None, nx=False):
        self.calls.append(("set", key))
        if nx and self._live(key) is not None:
            return None
        self._data[key] = _Entry(value,
                                 self._now() + float(ex) if ex else None)
        return True

    def delete(self, *keys):
        self.calls.append(("delete", *keys))
        removed = 0
        for key in keys:
            if self._live(key) is not None:
                removed += 1
            self._data.pop(key, None)
        return removed

    unlink = delete

    def exists(self, key):
        self.calls.append(("exists", key))
        return 1 if self._live(key) is not None else 0

    def expire(self, key, seconds):
        entry = self._live(key)
        if entry is None:
            return 0
        entry.expires_at = self._now() + float(seconds)
        return 1

    def ttl(self, key):
        entry = self._live(key)
        if entry is None:
            return -2
        if entry.expires_at is None:
            return -1
        return int(entry.expires_at - self._now())

    def scan_iter(self, match=None, count=None):
        self.calls.append(("scan_iter", match))
        for key in list(self._data.keys()):
            if self._live(key) is None:
                continue
            if match is None or fnmatch.fnmatchcase(key, match):
                yield key

    def eval(self, script, numkeys, *args):
        """
        Interpreta los dos unicos scripts Lua del proyecto, reconocidos
        por su contenido: GETDEL atomico y EXPIRE condicional.
        """
        self.calls.append(("eval", script.strip().splitlines()[0]))
        keys = list(args[:numkeys])
        rest = list(args[numkeys:])
        body = " ".join(script.split())

        if body.startswith("local value = redis.call('GET'"):
            value = self.get(keys[0])
            if value is not None:
                self.delete(keys[0])
            return value
        if body.startswith("if redis.call('EXISTS'"):
            return self.expire(keys[0], rest[0])
        if "if redis.call('GET', KEYS[1]) == ARGV[1]" in body:
            if self.get(keys[0]) == rest[0]:
                return self.delete(keys[0])
            return 0
        raise NotImplementedError(f"script Lua no reconocido: {body[:60]}")

    # -- conjuntos (indice de sesiones por usuario) ------------------
    def sadd(self, key, *values):
        entry = self._live(key)
        if entry is None or not isinstance(entry.value, set):
            entry = _Entry(set(), None)
            self._data[key] = entry
        antes = len(entry.value)
        entry.value.update(values)
        return len(entry.value) - antes

    def srem(self, key, *values):
        entry = self._live(key)
        if entry is None or not isinstance(entry.value, set):
            return 0
        antes = len(entry.value)
        entry.value.difference_update(values)
        return antes - len(entry.value)

    def smembers(self, key):
        entry = self._live(key)
        if entry is None or not isinstance(entry.value, set):
            return set()
        return set(entry.value)

    def pipeline(self):
        """Pipeline minimo: acumula y ejecuta en orden, sin transaccion."""
        return _FakePipeline(self)

    def info(self, section=None):
        live = [k for k in list(self._data) if self._live(k) is not None]
        return {"redis_version": "7.2.0-fake", "uptime_in_seconds": 1,
                "connected_clients": 1, "used_memory_human": "1.00M",
                "keyspace_hits": 0, "keyspace_misses": 0,
                "evicted_keys": 0, "expired_keys": 0,
                "db0": {"keys": len(live)}}

    # -- ayudas para las pruebas ------------------------------------
    # Se itera sobre una COPIA de las claves: _live() purga las caducadas
    # y mutar el diccionario mientras se recorre lo rompe.
    def keys_matching(self, pattern):
        return sorted(k for k in list(self._data)
                      if self._live(k) is not None
                      and fnmatch.fnmatchcase(k, pattern))

    def snapshot(self):
        return {k: entry.value for k in list(self._data)
                for entry in (self._live(k),) if entry is not None}


class _FakePipeline:
    """Encola llamadas y las ejecuta en orden al llamar execute()."""

    def __init__(self, client):
        self._client = client
        self._queue = []

    def __getattr__(self, name):
        def encolar(*args, **kwargs):
            self._queue.append((name, args, kwargs))
            return self
        return encolar

    def execute(self):
        resultados = []
        for name, args, kwargs in self._queue:
            resultados.append(getattr(self._client, name)(*args, **kwargs))
        self._queue.clear()
        return resultados


class BrokenRedisClient:
    """Redis que no responde: todo comando levanta ConnectionError."""

    def __init__(self, message="Connection refused (simulado)"):
        self.message = message

    def _fail(self, *args, **kwargs):
        raise ConnectionError(self.message)

    ping = get = set = delete = unlink = exists = expire = ttl = _fail
    eval = info = sadd = srem = smembers = pipeline = _fail

    def scan_iter(self, *args, **kwargs):
        raise ConnectionError(self.message)


def install(store, client=None):
    """
    Enchufa un doble en un RedisStore ya construido y devuelve el doble.

    Deja la URL con un valor ficticio para que store.configured sea True
    y limpia el enfriamiento de un fallo anterior.
    """
    client = client if client is not None else FakeRedisClient()
    store.url = store.url or "redis://:fake@localhost:6379/0"
    store._client = client
    store._down_until = 0.0
    store._last_error = None
    return client


def break_store(store, message="Connection refused (simulado)"):
    """Hace que un RedisStore se comporte como si Redis estuviera caido."""
    store._client = BrokenRedisClient(message)
    store._down_until = 0.0
    store._last_error = None
    return store._client
