"""
packages/library_common/library_common/metrics.py
Contadores en proceso que alimentan el endpoint /metrics de cada servicio.

Deliberadamente simple: un diccionario protegido por un cerrojo, sin
dependencias externas ni servidor de metricas. Responde a las preguntas
que importan en la practica:

  * cuantas peticiones entraron y con que codigo salieron
  * cuantas veces se acerto o se fallo el cache de Redis
  * cuantas veces Redis dio error, y cuanto tardo
  * cuantos tokens se rechazaron por estar revocados

Los contadores son por PROCESO: con gunicorn --workers 3 cada trabajador
lleva los suyos, de modo que /metrics refleja al trabajador que atendio
la peticion. Para una vista agregada se usa el bloque "redis" de
/metrics, que si viene del servidor Redis compartido.
"""
import threading
import time
from collections import defaultdict

_lock = threading.Lock()
_counters = defaultdict(int)
_timers = defaultdict(lambda: {"count": 0, "total_ms": 0.0, "max_ms": 0.0})
_started_at = time.time()


def incr(name, amount=1):
    with _lock:
        _counters[name] += amount


def observe(name, elapsed_ms):
    """Registra una duracion (conteo, acumulado y maximo)."""
    with _lock:
        slot = _timers[name]
        slot["count"] += 1
        slot["total_ms"] += elapsed_ms
        if elapsed_ms > slot["max_ms"]:
            slot["max_ms"] = elapsed_ms


class timed:
    """Context manager que mide y registra la duracion de un bloque."""

    def __init__(self, name):
        self.name = name
        self.started = None

    def __enter__(self):
        self.started = time.perf_counter()
        return self

    def __exit__(self, *exc_info):
        observe(self.name, (time.perf_counter() - self.started) * 1000.0)
        return False


def snapshot():
    """Copia de los contadores, lista para serializar."""
    with _lock:
        counters = dict(_counters)
        timers = {
            name: {
                "count": slot["count"],
                "avgMs": round(slot["total_ms"] / slot["count"], 3) if slot["count"] else 0.0,
                "maxMs": round(slot["max_ms"], 3),
            }
            for name, slot in _timers.items()
        }
    return {
        "uptimeSeconds": int(time.time() - _started_at),
        "counters": dict(sorted(counters.items())),
        "latency": dict(sorted(timers.items())),
    }


def reset():
    """Solo para las pruebas: deja los contadores en cero."""
    global _started_at
    with _lock:
        _counters.clear()
        _timers.clear()
        _started_at = time.time()
