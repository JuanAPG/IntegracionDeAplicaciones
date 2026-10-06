"""
apps/Python_app/test_app_smoke.py
Prueba de humo de la app de escritorio SIN interfaz grafica y SIN
servidores: comprueba que las piezas encajan.

Tkinter no se puede abrir en un entorno sin pantalla, de modo que aqui
no se levanta la ventana: se ejercita la capa de clientes, que es donde
vive la logica (tokens, renovacion, reintento tras 401, errores).

Uso (desde apps/Python_app):
    python test_app_smoke.py
"""
import json
import sys
import time
from datetime import datetime, timedelta, timezone

import api_client
import config_store
from api_client import ApiClient, TokenBox

PASSED, FAILED = 0, 0


def check(name, cond, extra=""):
    global PASSED, FAILED
    if cond:
        PASSED += 1
        print(f"  OK    {name}")
    else:
        FAILED += 1
        print(f"  FALLA {name} {extra}")


def hacer_token(segundos_restantes=1800, role="user", role_id=2, user_id=7):
    """JWT de mentira: la firma da igual, aqui solo se lee el payload."""
    import base64

    def b64(obj):
        return base64.urlsafe_b64encode(
            json.dumps(obj).encode()).decode().rstrip("=")

    exp = int((datetime.now(timezone.utc)
               + timedelta(seconds=segundos_restantes)).timestamp())
    cabecera = b64({"alg": "HS256", "typ": "JWT"})
    cuerpo = b64({"sub": str(user_id), "user_id": user_id, "role": role,
                  "role_id": role_id, "exp": exp, "jti": "x", "sid": "s"})
    return f"{cabecera}.{cuerpo}.firmafalsa"


print("1. TokenBox: vigencia y renovacion anticipada")
cambios = []
caja = TokenBox(on_change=lambda a, r: cambios.append((bool(a), bool(r))))
caja.set(hacer_token(1800), "refresh-abc", renew_before=300)
check("guarda los dos tokens", caja.access and caja.refresh == "refresh-abc")
check("avisa del cambio para persistirlo", cambios == [(True, True)], str(cambios))
check("lee el rol y el user_id del token",
      caja.role == "user" and caja.user_id == 7 and caja.role_id == 2,
      f"{caja.role} {caja.user_id} {caja.role_id}")
check("quedan ~30 min", 1700 < caja.seconds_left() <= 1800, str(caja.seconds_left()))
check("no hay que renovar todavia", not caja.expiring_soon())
caja.set(hacer_token(120), "refresh-abc")
check("a 2 min del final, toca renovar", caja.expiring_soon())
check("y aun no ha caducado", not caja.expired())
caja.set(hacer_token(-10), "refresh-abc")
check("pasado el exp, caducado", caja.expired())
caja.clear()
check("clear deja todo vacio", caja.access is None and caja.refresh is None)

print("2. ApiClient: renovacion antes de una escritura")
renovaciones = {"n": 0}


class ClienteFalso(ApiClient):
    SERVICE = "Prueba"

    def __init__(self, tokens, respuestas):
        super().__init__("http://fake", tokens, timeout=1,
                         refresher=self._renovar)
        self.respuestas = list(respuestas)
        self.enviados = []

    def _renovar(self):
        renovaciones["n"] += 1
        self.tokens.set(hacer_token(1800), "refresh-nuevo")
        return True

    def request(self, method, path, **kwargs):
        # Se intercepta el envio real: interesa QUE token se habria usado.
        if kwargs.get("auth", True):
            self._renew_if_needed()
        self.enviados.append(self.tokens.access)
        estado = self.respuestas.pop(0) if self.respuestas else 200
        if estado == 401 and kwargs.get("retry", True) and self.tokens.refresh:
            if self._renovar():
                return self.request(method, path, **{**kwargs, "retry": False})
        if estado in (200, 201):
            return True, {"ok": True}, None
        return False, None, api_client.ApiError("fallo", estado)


caja = TokenBox()
caja.set(hacer_token(120), "refresh-abc", renew_before=300)
cliente = ClienteFalso(caja, [200])
cliente.request("POST", "/algo")
check("renovo antes de enviar, por quedar poco", renovaciones["n"] == 1,
      str(renovaciones))
check("envio con el token NUEVO", cliente.enviados[0] == caja.access)

print("3. ApiClient: un 401 se reintenta una sola vez")
renovaciones["n"] = 0
caja = TokenBox()
caja.set(hacer_token(1800), "refresh-abc", renew_before=300)
cliente = ClienteFalso(caja, [401, 200])
ok, _data, _error = cliente.request("PUT", "/algo")
check("tras renovar, el reintento funciona", ok is True)
check("renovo exactamente una vez", renovaciones["n"] == 1, str(renovaciones))
check("hizo dos envios", len(cliente.enviados) == 2, str(len(cliente.enviados)))

renovaciones["n"] = 0
caja = TokenBox()
caja.set(hacer_token(1800), "refresh-abc", renew_before=300)
cliente = ClienteFalso(caja, [401, 401])
ok, _data, error = cliente.request("PUT", "/algo")
check("dos 401 seguidos ya es sesion perdida", ok is False and error.status == 401,
      f"{ok} {error}")
check("y no entra en bucle de renovaciones", renovaciones["n"] == 1,
      str(renovaciones))

print("4. Mensajes de error: dicen que hacer")
caja = TokenBox()
cliente = ApiClient("http://127.0.0.1:1", caja, timeout=1)
ok, _data, error = cliente.get("/health", auth=False)
check("sin servidor -> error de conexion legible",
      ok is False and "sin conexion" in error.message.lower(),
      error.message[:90])


class RespuestaFalsa:
    def __init__(self, status, cuerpo):
        self.status_code = status
        self._cuerpo = cuerpo

    def json(self):
        return self._cuerpo


error = api_client.parse_error(
    RespuestaFalsa(403, {"error": {"status": 403, "code": "forbidden",
                                   "message": "Su rol no tiene permiso.",
                                   "details": ["Permiso requerido: books:write."]}}),
    "fallo")
check("un 403 conserva codigo y detalles",
      error.status == 403 and error.code == "forbidden"
      and "books:write" in error.message, error.message)

print("5. config_store: los seis endpoints")
cfg = config_store._deep_merge(config_store.DEFAULTS, {})
urls = config_store.service_urls(cfg)
check("hay seis servicios", len(urls) == 6 and set(urls) == set(config_store.SERVICIOS),
      str(sorted(urls)))
check("los puertos son los esperados",
      urls["login"].endswith(":5000") and urls["pagos"].endswith(":5005"),
      str(urls))
cfg_copia = json.loads(json.dumps(cfg))
puertos = {}
host = "http://10.0.0.9"
for nombre, puerto in (("login", 5000), ("books", 5001), ("users", 5002),
                       ("authors", 5003), ("pedidos", 5004), ("pagos", 5005)):
    puertos[nombre] = f"{host}:{puerto}"
cfg_copia.setdefault("endpoints", {}).update(
    {f"{k}_base_url": v for k, v in puertos.items()})
check("cambiar la IP reapunta los seis",
      config_store.service_urls(cfg_copia) == puertos,
      str(config_store.service_urls(cfg_copia)))

print("6. Los clientes de los servicios nuevos se construyen")
from services_client import AuthorsClient, PagosClient, PedidosClient, UsersClient

caja = TokenBox()
clientes = {
    "users": UsersClient("http://x:5002", caja),
    "authors": AuthorsClient("http://x:5003", caja),
    "pedidos": PedidosClient("http://x:5004", caja),
    "pagos": PagosClient("http://x:5005", caja),
}
check("los cuatro comparten el mismo TokenBox",
      all(c.tokens is caja for c in clientes.values()))
check("todos piden JSON con ?format=",
      all(c.format_param == "format" for c in clientes.values()))
from books_client import BooksClient
libros = BooksClient("http://x:5001", tokens=caja)
check("books usa ?output= (en el, ?format= es un filtro)",
      libros.format_param == "output")

print("7. Las piezas de la interfaz importan sin pantalla")
import importlib
for modulo in ("login_client", "services_client", "health_monitor", "api_client"):
    try:
        importlib.import_module(modulo)
        check(f"{modulo} importa", True)
    except Exception as exc:                            # noqa: BLE001
        check(f"{modulo} importa", False, str(exc)[:120])
# ui_* necesitan tkinter, que puede no tener pantalla: se comprueba que
# el archivo compile, no que la ventana se abra.
import py_compile
for modulo in ("ui_books.py", "ui_dialogs.py", "ui_orders.py", "app.py"):
    try:
        py_compile.compile(modulo, doraise=True)
        check(f"{modulo} compila", True)
    except Exception as exc:                            # noqa: BLE001
        check(f"{modulo} compila", False, str(exc)[:160])

print(f"\nResultado: {PASSED} OK, {FAILED} fallos")
sys.exit(1 if FAILED else 0)
