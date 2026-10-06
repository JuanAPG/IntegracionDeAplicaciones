"""
test/test_pedidos_mocked.py
Pruebas del microservicio de pedidos SIN PostgreSQL y SIN servidor Redis.

El repositorio simulado reproduce lo que hacen los procedimientos
almacenados (reserva y devolucion de stock sobre books.stock, maquina de
estados), para poder comprobar el COMPORTAMIENTO del servicio. La
correccion del SQL en si se verifica en la VM con scripts/pruebas.sh.

Cubre:
  1. RASTREO PUBLICO: sin token, y solo el estatus de envio.
  2. Crear pedido: reserva stock, congela precios, rechaza si no alcanza.
  3. El cliente no puede pedir a nombre de otro sin orders:write.
  4. Cerrojo de Redis: no se crean dos pedidos por un reintento.
  5. Listar: propios por omision; ajenos solo con orders:read.
  6. Ajustar lineas: solo pendiente, ajusta stock por la diferencia.
  7. Cancelar: devuelve stock; pagado exige orders:write; enviado no.
  8. Estados: transiciones validas, y orders:status para moverlos.
  9. Invalidacion del cache del catalogo cuando se mueve el stock.
 10. Redis caido: rastreo publico si, operaciones con token 503.

Uso (desde apps/services/pedidos):
    python test/test_pedidos_mocked.py
"""
import os
import sys
from datetime import datetime, timezone

os.environ.setdefault("JWT_SECRET_KEY", "secreto-jwt-de-pruebas-suficientemente-largo")
os.environ.setdefault("REDIS_URL", "redis://:prueba@localhost:6379/0")
os.environ.setdefault("DEFAULT_FORMAT", "xml")

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

import pedidos.shared as shared  # noqa: E402
from library_common import testing as redis_testing  # noqa: E402

FAKE = redis_testing.install(shared.store)

import pedidos.app as appmod  # noqa: E402
import pedidos.repository as repo  # noqa: E402

AHORA = datetime.now(timezone.utc)

# ---------------------------------------------------------------------
# Base simulada
# ---------------------------------------------------------------------
# Stock holgado a proposito: la bateria encadena muchas reservas y la
# idea es probar el COMPORTAMIENTO, no quedarse sin existencias a mitad.
# El libro 3 nace agotado justamente para probar el rechazo.
LIBROS = {
    1: {"id": 1, "isbn": "978-1111111111", "title": "Clean Code", "price": 500.0, "stock": 40},
    2: {"id": 2, "isbn": "978-2222222222", "title": "Refactoring", "price": 300.0, "stock": 20},
    3: {"id": 3, "isbn": "978-3333333333", "title": "Agotado", "price": 100.0, "stock": 0},
}
USUARIOS = {7: {"id": 7, "email": "cliente@ejemplo.mx", "is_active": True,
                "full_name": "Cliente Uno"},
            8: {"id": 8, "email": "otro@ejemplo.mx", "is_active": True,
                "full_name": "Cliente Dos"},
            9: {"id": 9, "email": "baja@ejemplo.mx", "is_active": False,
                "full_name": "Cliente Baja"}}
PEDIDOS = {}
LINEAS = {}
HISTORIAL = {}
SIGUIENTE = {"id": 1}

TRANSICIONES = {"pendiente": {"pagado", "cancelado"},
                "pagado": {"enviado", "cancelado"},
                "enviado": {"entregado"},
                "entregado": set(), "cancelado": set()}


class ErrorBase(Exception):
    """Equivale a un RAISE EXCEPTION de PL/pgSQL."""


def _recalcular(oid):
    lineas = LINEAS.get(oid, [])
    subtotal = sum(l["quantity"] * l["unit_price"] for l in lineas)
    PEDIDOS[oid]["subtotal"] = subtotal
    PEDIDOS[oid]["total"] = subtotal + PEDIDOS[oid]["shipping_cost"]


def fake_create_order(user_id, lines, notes=None, currency="MXN",
                      shipping_cost=0, shipping_address=None):
    """Reproduce sp_crear_pedido: reserva stock o revienta."""
    if not lines:
        raise ErrorBase("El pedido debe tener al menos una linea")
    for linea in sorted(lines, key=lambda l: l["bookId"]):
        libro = LIBROS.get(linea["bookId"])
        if libro is None:
            raise ErrorBase(f"El libro {linea['bookId']} no existe")
        if libro["stock"] < linea["quantity"]:
            raise ErrorBase(
                f"Stock insuficiente de \"{libro['title']}\" (ISBN {libro['isbn']}): "
                f"hay {libro['stock']}, se piden {linea['quantity']}")
    oid = SIGUIENTE["id"]
    SIGUIENTE["id"] += 1
    PEDIDOS[oid] = {"id": oid, "order_number": f"PED-{oid:06d}", "user_id": user_id,
                    "status": "pendiente", "currency": currency,
                    "subtotal": 0.0, "shipping_cost": float(shipping_cost),
                    "total": 0.0, "paid_amount": 0.0,
                    "carrier": None, "tracking_code": None,
                    "placed_at": AHORA, "paid_at": None, "shipped_at": None,
                    "delivered_at": None, "cancelled_at": None}
    LINEAS[oid] = []
    for indice, linea in enumerate(sorted(lines, key=lambda l: l["bookId"]), start=1):
        libro = LIBROS[linea["bookId"]]
        libro["stock"] -= linea["quantity"]
        LINEAS[oid].append({"id": indice, "book_id": libro["id"],
                            "book_isbn": libro["isbn"], "book_title": libro["title"],
                            "quantity": linea["quantity"],
                            "unit_price": libro["price"],
                            "line_total": linea["quantity"] * libro["price"]})
    _recalcular(oid)
    HISTORIAL[oid] = [{"from_status": None, "to_status": "pendiente",
                       "changed_by": user_id, "note": "pedido creado",
                       "changed_at": AHORA}]
    return oid


def fake_adjust_line(oid, book_id, quantity):
    """Reproduce sp_ajustar_linea_pedido."""
    oid, book_id, quantity = int(oid), int(book_id), int(quantity)
    if PEDIDOS[oid]["status"] != "pendiente":
        raise ErrorBase(f"Solo se puede modificar un pedido pendiente "
                        f"(esta en {PEDIDOS[oid]['status']})")
    actual = next((l for l in LINEAS[oid] if l["book_id"] == book_id), None)
    libro = LIBROS.get(book_id)
    if libro is None:
        raise ErrorBase(f"El libro {book_id} no existe")
    previa = actual["quantity"] if actual else 0
    delta = quantity - previa
    if delta > 0 and libro["stock"] < delta:
        raise ErrorBase(
            f"Stock insuficiente de \"{libro['title']}\" (ISBN {libro['isbn']}): "
            f"hay {libro['stock']}, faltan {delta}")
    libro["stock"] -= delta
    if quantity == 0:
        LINEAS[oid] = [l for l in LINEAS[oid] if l["book_id"] != book_id]
    elif actual:
        actual["quantity"] = quantity
        actual["line_total"] = quantity * actual["unit_price"]
    else:
        LINEAS[oid].append({"id": len(LINEAS[oid]) + 1, "book_id": book_id,
                            "book_isbn": libro["isbn"], "book_title": libro["title"],
                            "quantity": quantity, "unit_price": libro["price"],
                            "line_total": quantity * libro["price"]})
    _recalcular(oid)


def fake_cancel(oid, changed_by=None, reason=None):
    oid = int(oid)
    if oid not in PEDIDOS:
        raise ErrorBase(f"El pedido {oid} no existe")
    estado = PEDIDOS[oid]["status"]
    if estado in ("cancelado", "entregado", "enviado"):
        raise ErrorBase(f"Un pedido en estado {estado} ya no se puede cancelar")
    for linea in LINEAS.get(oid, []):
        LIBROS[linea["book_id"]]["stock"] += linea["quantity"]
    PEDIDOS[oid]["status"] = "cancelado"
    PEDIDOS[oid]["cancelled_at"] = AHORA
    HISTORIAL[oid].append({"from_status": estado, "to_status": "cancelado",
                           "changed_by": changed_by,
                           "note": reason, "changed_at": AHORA})


def fake_change_status(oid, to_status, changed_by=None, note=None,
                       carrier=None, tracking_code=None):
    oid = int(oid)
    if to_status == "cancelado":
        return fake_cancel(oid, changed_by, note)
    if oid not in PEDIDOS:
        raise ErrorBase(f"El pedido {oid} no existe")
    actual = PEDIDOS[oid]["status"]
    if to_status not in TRANSICIONES[actual]:
        raise ErrorBase(f"Transicion de estado no permitida: {actual} -> {to_status}")
    PEDIDOS[oid]["status"] = to_status
    if carrier:
        PEDIDOS[oid]["carrier"] = carrier
    if tracking_code:
        PEDIDOS[oid]["tracking_code"] = tracking_code
    PEDIDOS[oid][{"pagado": "paid_at", "enviado": "shipped_at",
                  "entregado": "delivered_at"}[to_status]] = AHORA
    HISTORIAL[oid].append({"from_status": actual, "to_status": to_status,
                           "changed_by": changed_by, "note": note,
                           "changed_at": AHORA})


def _vista(oid):
    """Equivale a una fila de v_orders_detail."""
    p = dict(PEDIDOS[oid])
    u = USUARIOS[p["user_id"]]
    p["user_email"] = u["email"]
    p["user_name"] = u["full_name"]
    p["line_count"] = len(LINEAS.get(oid, []))
    p["item_count"] = sum(l["quantity"] for l in LINEAS.get(oid, []))
    return p


def fake_list(filters, sort="placed", order="desc", limit=50, offset=0):
    filas = [_vista(o) for o in PEDIDOS]
    if filters.get("user_id") is not None:
        filas = [f for f in filas if f["user_id"] == filters["user_id"]]
    if filters.get("status"):
        filas = [f for f in filas if f["status"] == filters["status"]]
    filas.sort(key=lambda f: f["id"], reverse=(str(order).lower() != "asc"))
    return filas[offset:offset + limit], len(filas)


repo.create_order = fake_create_order
repo.adjust_line = fake_adjust_line
repo.cancel_order = fake_cancel
repo.change_status = fake_change_status
repo.list_orders = fake_list
repo.get_order = lambda oid: (_vista(int(oid)) if int(oid) in PEDIDOS else None)
repo.get_order_by_number = lambda num: next(
    (_vista(o) for o in PEDIDOS if PEDIDOS[o]["order_number"] == num), None)
repo.lines_of = lambda oid: [dict(l) for l in LINEAS.get(int(oid), [])]
repo.history_of = lambda oid: [dict(h) for h in HISTORIAL.get(int(oid), [])]
repo.owner_of = lambda oid: ({"user_id": PEDIDOS[int(oid)]["user_id"],
                              "status": PEDIDOS[int(oid)]["status"]}
                             if int(oid) in PEDIDOS else None)
repo.user_is_active = lambda uid: (dict(USUARIOS[int(uid)]) if int(uid) in USUARIOS
                                   else None)
repo.books_availability = lambda ids: {b: dict(LIBROS[b]) for b in ids if b in LIBROS}


def fake_tracking(num):
    fila = next((o for o in PEDIDOS if PEDIDOS[o]["order_number"] == num), None)
    if fila is None:
        return None
    p = PEDIDOS[fila]
    return {"order_number": p["order_number"], "status": p["status"],
            "carrier": p["carrier"], "tracking_code": p["tracking_code"],
            "placed_at": p["placed_at"], "shipped_at": p["shipped_at"],
            "delivered_at": p["delivered_at"],
            "item_count": sum(l["quantity"] for l in LINEAS.get(fila, []))}


repo.tracking_of = fake_tracking

PERMISOS = {1: {"*"}, 2: set(),
            3: {"orders:read", "orders:write", "orders:status"}}
shared.resolver.permissions_of = lambda rid: frozenset(PERMISOS.get(int(rid), set()))
shared.database.health = lambda: (True, {"status": "ok", "database": "library_db",
                                         "user": "library_user", "schema": "library",
                                         "server": "PostgreSQL 16"})

client = appmod.app.test_client()
PASSED, FAILED = 0, 0


def check(name, cond, extra=""):
    global PASSED, FAILED
    if cond:
        PASSED += 1
        print(f"  OK    {name}")
    else:
        FAILED += 1
        print(f"  FALLA {name} {extra}")


def auth(user_id, role_id=2):
    rol = {1: "admin", 2: "user", 3: "staff"}[role_id]
    tok, _ = shared.codec.issue_access_token(
        user_id=user_id, email=USUARIOS.get(user_id, {}).get("email", "x@y.z"),
        role=rol, role_id=role_id, sid=f"sid-{user_id}")
    return {"Authorization": f"Bearer {tok}"}


# =====================================================================
print("1. Crear pedido: reserva de stock y precios congelados")
stock_antes = LIBROS[1]["stock"]
r = client.post("/pedidos?format=json",
                json={"lines": [{"bookId": 1, "quantity": 2}], "shippingCost": 50},
                headers=auth(7))
cuerpo = r.get_json()
check("crear -> 201", r.status_code == 201, r.get_data(as_text=True)[:220])
PED1 = cuerpo["id"]
check("reservo el stock", LIBROS[1]["stock"] == stock_antes - 2,
      f"{stock_antes} -> {LIBROS[1]['stock']}")
check("congelo el precio del catalogo",
      cuerpo["lines"][0]["unitPrice"] == 500.0
      and cuerpo["lines"][0]["lineTotal"] == 1000.0, str(cuerpo["lines"]))
check("sumo el envio al total", cuerpo["total"] == 1050.0, str(cuerpo["total"]))
check("nace pendiente y con numero legible",
      cuerpo["status"] == "pendiente" and cuerpo["orderNumber"].startswith("PED-"),
      str(cuerpo["orderNumber"]))
check("el dueno es el del token", cuerpo["user"]["id"] == 7, str(cuerpo["user"]))
r = client.post("/pedidos?format=json",
                json={"lines": [{"bookId": 1, "quantity": 1},
                                {"bookId": 1, "quantity": 2}]}, headers=auth(7))
check("repetir un libro suma unidades en vez de fallar",
      r.status_code == 201 and len(r.get_json()["lines"]) == 1
      and r.get_json()["lines"][0]["quantity"] == 3,
      r.get_data(as_text=True)[:220])
PED2 = r.get_json()["id"]

print("2. Rechazos al crear")
r = client.post("/pedidos?format=json", json={"lines": [{"bookId": 3, "quantity": 1}]},
                headers=auth(7))
check("stock insuficiente -> 409 que dice que libro",
      r.status_code == 409 and "Agotado" in r.get_data(as_text=True),
      r.get_data(as_text=True)[:240])
r = client.post("/pedidos?format=json", json={"lines": []}, headers=auth(7))
check("sin lineas -> 400", r.status_code == 400, str(r.status_code))
r = client.post("/pedidos?format=json", json={}, headers=auth(7))
check("sin el campo lines -> 400 que dice como enviarlo",
      r.status_code == 400 and "bookId" in r.get_data(as_text=True),
      r.get_data(as_text=True)[:200])
r = client.post("/pedidos?format=json",
                json={"lines": [{"bookId": 1, "quantity": 0}]}, headers=auth(7))
check("cantidad cero -> 400", r.status_code == 400, str(r.status_code))
r = client.post("/pedidos?format=json",
                json={"lines": [{"bookId": 1, "quantity": 101}]}, headers=auth(7))
check("cantidad por encima del maximo -> 400", r.status_code == 400,
      str(r.status_code))
r = client.post("/pedidos?format=json",
                json={"lines": [{"bookId": 999, "quantity": 1}]}, headers=auth(7))
check("libro inexistente -> 409", r.status_code == 409, str(r.status_code))
r = client.post("/pedidos?format=json",
                json={"lines": [{"bookId": 1, "quantity": 1}], "userId": 9},
                headers=auth(7, role_id=3))
check("cuenta desactivada -> 409", r.status_code == 409
      and "desactivada" in r.get_data(as_text=True), r.get_data(as_text=True)[:200])

print("3. Pedir a nombre de otro exige orders:write")
r = client.post("/pedidos?format=json",
                json={"lines": [{"bookId": 1, "quantity": 1}], "userId": 8},
                headers=auth(7))
check("cliente a nombre de otro -> 403", r.status_code == 403,
      r.get_data(as_text=True)[:200])
r = client.post("/pedidos?format=json",
                json={"lines": [{"bookId": 1, "quantity": 1}], "userId": 8},
                headers=auth(7, role_id=3))
check("staff a nombre de otro -> 201 y el dueno es el indicado",
      r.status_code == 201 and r.get_json()["user"]["id"] == 8,
      r.get_data(as_text=True)[:200])
PED_OTRO = r.get_json()["id"]

print("4. Cerrojo de Redis contra el pedido doble")
tomado = shared.store.strict_set(shared.store.key("lock", "pedido:crear:7"),
                                 "otro-proceso", 10, only_if_absent=True)
r = client.post("/pedidos?format=json", json={"lines": [{"bookId": 1, "quantity": 1}]},
                headers=auth(7))
check("con el cerrojo tomado -> 409 en vez de un segundo pedido",
      tomado and r.status_code == 409 and "curso" in r.get_data(as_text=True),
      r.get_data(as_text=True)[:200])
shared.store.strict_delete(shared.store.key("lock", "pedido:crear:7"))
r = client.post("/pedidos?format=json", json={"lines": [{"bookId": 2, "quantity": 1}]},
                headers=auth(7))
check("liberado el cerrojo, vuelve a crear", r.status_code == 201,
      str(r.status_code))
PED3 = r.get_json()["id"]

print("5. Listar: propios por omision")
r = client.get("/pedidos?format=json", headers=auth(7))
cuerpo = r.get_json()
check("un cliente ve solo los suyos", r.status_code == 200
      and all(o["user"]["id"] == 7 for o in cuerpo["orders"]),
      r.get_data(as_text=True)[:200])
r = client.get("/pedidos?format=json&all=true", headers=auth(7))
check("?all=true sin orders:read -> 403", r.status_code == 403, str(r.status_code))
r = client.get("/pedidos?format=json&all=true", headers=auth(7, role_id=3))
check("?all=true con orders:read -> ve todos", r.status_code == 200
      and any(o["user"]["id"] == 8 for o in r.get_json()["orders"]),
      r.get_data(as_text=True)[:200])
r = client.get("/pedidos?format=json&userId=8", headers=auth(7))
check("?userId ajeno sin permiso -> 403", r.status_code == 403, str(r.status_code))
r = client.get("/pedidos?format=json&status=inventado", headers=auth(7))
check("estado desconocido -> 400 que lista los validos",
      r.status_code == 400 and "pendiente" in r.get_data(as_text=True),
      r.get_data(as_text=True)[:200])
r = client.get(f"/pedidos/{PED_OTRO}?format=json", headers=auth(7))
check("ver el pedido de otro -> 403", r.status_code == 403, str(r.status_code))
r = client.get(f"/pedidos/{PED_OTRO}?format=json", headers=auth(7, role_id=3))
check("con orders:read si -> 200", r.status_code == 200, str(r.status_code))
r = client.get(f"/pedidos/numero/PED-{PED1:06d}?format=json", headers=auth(7))
check("buscar por numero", r.status_code == 200 and r.get_json()["id"] == PED1,
      r.get_data(as_text=True)[:160])
r = client.get("/pedidos/9999?format=json", headers=auth(7))
check("pedido inexistente -> 404", r.status_code == 404, str(r.status_code))

print("6. Ajustar lineas (solo pendiente)")
stock_antes = LIBROS[1]["stock"]
r = client.patch(f"/pedidos/{PED1}/lineas?format=json",
                 json={"lines": [{"bookId": 1, "quantity": 4}]}, headers=auth(7))
check("subir la cantidad reserva la diferencia",
      r.status_code == 200 and LIBROS[1]["stock"] == stock_antes - 2,
      f"{r.status_code} stock {stock_antes} -> {LIBROS[1]['stock']}")
stock_antes = LIBROS[1]["stock"]
r = client.patch(f"/pedidos/{PED1}/lineas?format=json",
                 json={"lines": [{"bookId": 1, "quantity": 1}]}, headers=auth(7))
check("bajarla devuelve la diferencia",
      r.status_code == 200 and LIBROS[1]["stock"] == stock_antes + 3,
      f"stock {stock_antes} -> {LIBROS[1]['stock']}")
r = client.patch(f"/pedidos/{PED1}/lineas?format=json",
                 json={"lines": [{"bookId": 1, "quantity": 999}]}, headers=auth(7))
check("pedir mas de lo que hay -> 400 por el maximo por libro",
      r.status_code == 400, r.get_data(as_text=True)[:160])
stock_antes = LIBROS[1]["stock"]
r = client.patch(f"/pedidos/{PED1}/lineas?format=json",
                 json={"lines": [{"bookId": 1, "quantity": 0}]}, headers=auth(7))
check("dejarlo sin lineas lo cancela y devuelve el stock",
      r.status_code == 200 and r.get_json()["status"] == "cancelado"
      and LIBROS[1]["stock"] == stock_antes + 1,
      r.get_data(as_text=True)[:240])
r = client.patch(f"/pedidos/{PED1}/lineas?format=json",
                 json={"lines": [{"bookId": 1, "quantity": 1}]}, headers=auth(7))
check("ajustar uno ya cancelado -> 409", r.status_code == 409,
      r.get_data(as_text=True)[:200])

print("7. Estados")
r = client.put(f"/pedidos/{PED2}/estado?format=json", json={"status": "enviado"},
               headers=auth(7, role_id=3))
check("pendiente -> enviado no es valido -> 409",
      r.status_code == 409 and "Transicion" in r.get_data(as_text=True),
      r.get_data(as_text=True)[:240])
r = client.put(f"/pedidos/{PED2}/estado?format=json", json={"status": "pagado"},
               headers=auth(7))
check("mover el estado sin orders:status -> 403", r.status_code == 403,
      str(r.status_code))
r = client.put(f"/pedidos/{PED2}/estado?format=json", json={"status": "pagado"},
               headers=auth(7, role_id=3))
check("pendiente -> pagado con permiso -> 200", r.status_code == 200
      and r.get_json()["status"] == "pagado", r.get_data(as_text=True)[:200])
r = client.put(f"/pedidos/{PED2}/estado?format=json", json={"status": "enviado"},
               headers=auth(7, role_id=3))
check("pagado -> enviado sin guia avisa",
      r.status_code == 200 and "warning" in r.get_json(),
      r.get_data(as_text=True)[:240])
r = client.put(f"/pedidos/{PED3}/estado?format=json", json={"status": "inventado"},
               headers=auth(7, role_id=3))
check("estado desconocido -> 400", r.status_code == 400, str(r.status_code))
r = client.get(f"/pedidos/{PED2}/historial?format=json", headers=auth(7))
hist = r.get_json()
check("la bitacora registra cada paso", r.status_code == 200
      and [h["toStatus"] for h in hist["history"]] == ["pendiente", "pagado", "enviado"],
      r.get_data(as_text=True)[:260])

print("8. RASTREO PUBLICO: sin token y sin datos personales")
client.put(f"/pedidos/{PED2}/estado?format=json",
           json={"status": "entregado", "carrier": "Estafeta",
                 "trackingCode": "EST-998877"}, headers=auth(7, role_id=3))
numero = f"PED-{PED2:06d}"
r = client.get(f"/envios/{numero}?format=json")
cuerpo = r.get_json()
check("sin token -> 200", r.status_code == 200, r.get_data(as_text=True)[:200])
check("trae el estatus de envio y la guia",
      cuerpo["status"] == "entregado" and cuerpo["trackingCode"] == "EST-998877"
      and cuerpo["carrier"] == "Estafeta", str(cuerpo))
check("NO filtra dueno, correo ni importes",
      not any(k in cuerpo for k in ("user", "total", "subtotal", "lines",
                                    "paidAmount", "userId")),
      str(sorted(cuerpo)))
texto = r.get_data(as_text=True)
check("ni el correo del cliente aparece en el cuerpo",
      "cliente@ejemplo.mx" not in texto and "Clean Code" not in texto, texto[:200])
check("se cachea (clave envios:<numero>)",
      any(k.startswith(f"envios:{numero.lower()}") for k in FAKE.keys_matching("envios:*")),
      str(FAKE.keys_matching("envios:*")))
r2 = client.get(f"/envios/{numero}?format=json")
check("segunda consulta HIT", r2.headers.get("X-Cache") == "HIT",
      str(r2.headers.get("X-Cache")))
r = client.get(f"/envios/{numero}")
check("tambien en XML", r.get_data(as_text=True).startswith("<?xml")
      and "<shipment" in r.get_data(as_text=True), r.get_data(as_text=True)[:160])
r = client.get("/envios/PED-999999?format=json")
check("numero inexistente -> 404", r.status_code == 404, str(r.status_code))
r = client.get(f"/pedidos/numero/{numero}?format=json")
check("el pedido COMPLETO por numero si exige token -> 401",
      r.status_code == 401, str(r.status_code))

print("9. Cancelar")
r = client.delete(f"/pedidos/{PED_OTRO}?format=json", headers=auth(7))
check("cancelar el pedido de otro -> 403", r.status_code == 403, str(r.status_code))
stock_antes = LIBROS[2]["stock"]
r = client.delete(f"/pedidos/{PED3}?format=json", json={"reason": "ya no lo quiero"},
                  headers=auth(7))
check("el dueno cancela el suyo y se devuelve el stock",
      r.status_code == 200 and r.get_json()["status"] == "cancelado"
      and LIBROS[2]["stock"] == stock_antes + 1,
      f"{r.status_code} stock {stock_antes} -> {LIBROS[2]['stock']}")
r = client.delete(f"/pedidos/{PED3}?format=json", headers=auth(7))
check("cancelar dos veces es idempotente", r.status_code == 200
      and r.get_json().get("alreadyCancelled") is True,
      r.get_data(as_text=True)[:160])
r = client.delete(f"/pedidos/{PED2}?format=json", headers=auth(7, role_id=3))
check("un pedido entregado ya no se cancela -> 409",
      r.status_code == 409 and "devolucion" in r.get_data(as_text=True),
      r.get_data(as_text=True)[:240])
r = client.post("/pedidos?format=json", json={"lines": [{"bookId": 1, "quantity": 1}]},
                headers=auth(8))
PED_PAGADO = r.get_json()["id"]
client.put(f"/pedidos/{PED_PAGADO}/estado?format=json", json={"status": "pagado"},
           headers=auth(7, role_id=3))
r = client.delete(f"/pedidos/{PED_PAGADO}?format=json", headers=auth(8))
check("el dueno NO cancela uno ya pagado -> 403",
      r.status_code == 403 and "reembolsar" in r.get_data(as_text=True),
      r.get_data(as_text=True)[:240])
r = client.delete(f"/pedidos/{PED_PAGADO}?format=json", headers=auth(7, role_id=3))
check("con orders:write si -> 200", r.status_code == 200, str(r.status_code))

print("10. Invalidacion del catalogo e informes")
shared.store.cache_set(shared.store.key("books", "list", "json", "all"),
                       {"body": "{}", "status": 200}, 30, jitter=0)
r = client.post("/pedidos?format=json", json={"lines": [{"bookId": 1, "quantity": 1}]},
                headers=auth(8))
check("crear un pedido invalida el cache del catalogo (movio el stock)",
      r.status_code == 201 and len(FAKE.keys_matching("books:*")) == 0,
      str(FAKE.keys_matching("books:*")))
r = client.get("/metrics?format=json")
m = r.get_json()
check("metrics cuenta pedidos creados y cancelados",
      m["counters"].get("orders.created", 0) > 0
      and m["counters"].get("orders.cancelled", 0) > 0, str(m["counters"])[:240])
check("metrics cuenta los rastreos servidos",
      m["counters"].get("tracking.served", 0) > 0, str(m["counters"])[:240])

print("11. Redis caido: rastreo si, operaciones con token no")
redis_testing.break_store(shared.store)
r = client.get(f"/envios/{numero}?format=json")
check("rastreo publico con Redis caido -> 200 (sin cache)", r.status_code == 200,
      f"{r.status_code} {r.get_data(as_text=True)[:140]}")
r = client.post("/pedidos?format=json", json={"lines": [{"bookId": 1, "quantity": 1}]},
                headers=auth(7))
check("crear con Redis caido -> 503", r.status_code == 503
      and r.get_json()["error"]["code"] == "redis_unavailable",
      f"{r.status_code} {r.get_data(as_text=True)[:160]}")
r = client.get("/health?format=json")
check("health 200 degradado", r.status_code == 200
      and r.get_json()["status"] == "degraded", str(r.get_json().get("status")))
check("health no filtra la clave de Redis", "prueba" not in r.get_data(as_text=True))
redis_testing.install(shared.store, FAKE)

print(f"\nResultado: {PASSED} OK, {FAILED} fallos")
sys.exit(1 if FAILED else 0)
