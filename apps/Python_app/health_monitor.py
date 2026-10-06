"""apps/Python_app/health_monitor.py
Semáforos de los SEIS microservicios, con 3 estados.

  verde    (up)        el servicio responde 200 y se declara sano
  amarillo (degraded)  responde, pero una dependencia suya falla
                       (Redis caído, SECRET_KEY sin fijar, avisos de
                       configuración). En este estado unos endpoints
                       siguen y otros no, y eso hay que verlo.
  rojo     (down)      no hay conexión

Por qué importa el amarillo: con Redis caído, el catálogo se puede
seguir leyendo (solo pierde la caché) pero NINGUNA escritura funciona,
porque no se puede comprobar si un token fue revocado. Pintar eso de
verde sería mentir, y de rojo, exagerar.
"""
import threading
from datetime import datetime

UP = "up"
DEGRADED = "degraded"
DOWN = "down"


def _classify(ok, msg, data):
    """(estado, texto) a partir de la respuesta de /health."""
    if ok:
        if isinstance(data, dict):
            avisos = list(data.get("warnings") or [])
            estado = str(data.get("status", "ok"))
            firma = str(data.get("sessionSigning", "ok"))
            jwt_estado = str(data.get("jwt", "ok"))
            redis_bloque = data.get("redis") or {}
            redis_estado = str(redis_bloque.get("status", "ok"))

            detalles = []
            if estado not in ("ok",):
                detalles.append(estado)
            if redis_estado not in ("ok", "not_configured"):
                detalles.append("Redis caído")
            elif redis_estado == "not_configured":
                detalles.append("Redis sin configurar")
            if firma == "missing_secret":
                detalles.append("SECRET_KEY sin fijar")
            if jwt_estado == "missing_secret":
                detalles.append("JWT_SECRET_KEY sin fijar")
            if avisos and not detalles:
                detalles.append(avisos[0])

            if detalles:
                return DEGRADED, "; ".join(detalles[:2])
        return UP, "up"
    if isinstance(data, dict) and (data.get("degraded") or data.get("status") == "error"):
        return DEGRADED, data.get("message") or msg
    return DOWN, msg


class HealthMonitor:
    """
    Consulta /health de cada servicio cada `poll` segundos.

    clients   diccionario nombre -> cliente con .health()
    on_update fn(servicio, estado, texto, hora)
    """

    def __init__(self, clients, poll_seconds, on_update):
        self.clients = dict(clients or {})
        self.poll = max(int(poll_seconds), 5)
        self.on_update = on_update
        self._stop = threading.Event()
        self._thread = None
        self._lock = threading.Lock()
        self.last = {}            # nombre -> (estado, texto, hora)

    def replace_clients(self, clients):
        """Cambia los clientes sin reiniciar el hilo (p. ej. al cambiar la IP)."""
        with self._lock:
            self.clients = dict(clients or {})

    def start(self):
        self.stop()
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()

    def check_now(self):
        threading.Thread(target=self._once, daemon=True).start()

    @staticmethod
    def _stamp():
        return datetime.now().strftime("%H:%M:%S")

    def _once(self):
        stamp = self._stamp()
        with self._lock:
            pares = list(self.clients.items())
        for nombre, cliente in pares:
            if self._stop.is_set():
                return
            try:
                ok, msg, data = cliente.health()
                estado, texto = _classify(ok, msg, data)
            except Exception as exc:                    # noqa: BLE001
                estado, texto = DOWN, str(exc)
            self.last[nombre] = (estado, texto, stamp)
            try:
                self.on_update(nombre, estado, texto, stamp)
            except Exception:                           # noqa: BLE001
                # Un fallo pintando el semáforo no debe matar el hilo.
                pass

    def _loop(self):
        self._once()
        while not self._stop.wait(self.poll):
            self._once()

    def summary(self):
        """Resumen para la barra de estado: cuántos verdes, amarillos, rojos."""
        conteo = {UP: 0, DEGRADED: 0, DOWN: 0}
        for estado, _texto, _hora in self.last.values():
            conteo[estado] = conteo.get(estado, 0) + 1
        return conteo
