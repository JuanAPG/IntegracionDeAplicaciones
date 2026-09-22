"""Semáforos con 3 estados: up / degradado / down + hora de comprobación."""
import threading
from datetime import datetime

UP = "up"
DEGRADED = "degraded"
DOWN = "down"


def _classify(ok, msg, data):
    """up = 200 + status ok; degraded = accesible pero dependencia mal
    (503 con cuerpo, warnings, SECRET_KEY ausente); down = sin conexión."""
    if ok:
        if isinstance(data, dict):
            warnings = data.get("warnings") or []
            signing = str(data.get("sessionSigning", "ok"))
            if data.get("status", "ok") != "ok" or warnings or signing == "missing_secret":
                detail = "; ".join(warnings[:2]) if warnings else ""
                if signing == "missing_secret":
                    detail = ((detail + "; ") if detail else "") + "SECRET_KEY sin fijar"
                return DEGRADED, detail or "dependencia degradada"
        return UP, "up"
    if isinstance(data, dict) and (data.get("degraded") or data.get("status") == "error"):
        return DEGRADED, data.get("message") or msg
    return DOWN, msg


class HealthMonitor:
    def __init__(self, login_client, books_client, poll_seconds, on_update):
        self.login_client = login_client
        self.books_client = books_client
        self.poll = poll_seconds
        self.on_update = on_update  # fn(service, state, text, checked_at_str)
        self._stop = threading.Event()
        self._thread = None

    def start(self):
        self.stop()
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()

    def check_now(self):
        t = threading.Thread(target=self._once, daemon=True)
        t.start()

    def _stamp(self):
        return datetime.now().strftime("%H:%M:%S")

    def _once(self):
        stamp = self._stamp()
        try:
            ok, msg, data = self.login_client.health()
            state, text = _classify(ok, msg, data)
            self.on_update("login", state, text, stamp)
        except Exception as exc:  # noqa: BLE001
            self.on_update("login", DOWN, str(exc), stamp)
        try:
            ok, msg, data = self.books_client.health()
            state, text = _classify(ok, msg, data)
            self.on_update("books", state, text, stamp)
        except Exception as exc:  # noqa: BLE001
            self.on_update("books", DOWN, str(exc), stamp)

    def _loop(self):
        self._once()
        while not self._stop.wait(self.poll):
            self._once()
