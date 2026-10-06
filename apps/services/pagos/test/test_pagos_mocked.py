"""
test/test_pagos_mocked.py
Pruebas del microservicio de pagos SIN PostgreSQL y SIN servidor Redis.

El repositorio simulado reproduce lo que hacen los procedimientos y
disparadores (tope de saldo, maquina de estados, y el pedido que pasa a
'pagado' cuando lo aplicado cubre el total).

Cubre:
  1. NADA es publico: incluso el catalogo de metodos exige token.
  2. Registrar: un cliente paga lo suyo; cobrar lo ajeno exige permiso.
  3. El importe no puede exceder el saldo del pedido.
  4. Efectivo nace aplicado; tarjeta nace pendiente o autorizado.
  5. Aplicar un pago que cubre el total pasa el PEDIDO a 'pagado'.
  6. Cobro doble: idempotencyKey devuelve el mismo pago; el cerrojo de
     Redis bloquea dos registros simultaneos.
  7. Datos de tarjeta RECHAZADOS (cardNumber, cvv...) y cardLast4 validado.
  8. Estados: rechazar, reembolsar, y las transiciones imposibles.
  9. Saldo del pedido.
 10. Redis caido -> 503 en todo (este servicio no tiene puerta publica).

Uso (desde apps/services/pagos):
    python test/test_pagos_mocked.py
"""
import os
import sys
from datetime import datetime, timezone

os.environ.setdefault("JWT_SECRET_KEY", "secreto-jwt-de-pruebas-suficientemente-largo")
os.environ.setdefault("REDIS_URL", "redis://:prueba@localhost:6379/0")
os.environ.setdefault("DEFAULT_FORMAT", "xml")

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

import pagos.shared as shared  # noqa: E402
from library_common import testing as redis_testing  # noqa: E402

FAKE = redis_testing.install(shared.store)

import pagos.app as appmod  # noqa: E402
import pagos.repository as repo  # noqa: E402

AHORA = datetime.now(timezone.utc)

METODOS = {
    1: {"id": 1, "name": "efectivo", "description": "Mostrador",
        "requires_authorization": False, "is_active": True},
    2: {"id": 2, "name": "tarjeta", "description": "Pasarela",
        "requires_authorization": True, "is_active": True},
    3: {"id": 3, "name": "retirado", "description": "Desactivado",
        "requires_authorization": True, "is_active": False},
}
PEDIDOS = {
    100: {"id": 100, "order_number": "PED-000100", "user_id": 7,
          "status": "pendiente", "total": 1000.0, "currency": "MXN"},
    200: {"id": 200, "order_number": "PED-000200", "user_id": 8,
          "status": "pendiente", "total": 500.0, "currency": "MXN"},
    300: {"id": 300, "order_number": "PED-000300", "user_id": 7,
          "status": "cancelado", "total": 300.0, "currency": "MXN"},
}
PAGOS = {}
HISTORIAL = {}
SIGUIENTE = {"id": 1}

TRANSICIONES = {"pendiente": {"autorizado", "aplicado", "rechazado"},
                "autorizado": {"aplicado", "rechazado"},
                "aplicado": {"reembolsado"},
                "rechazado": set(), "reembolsado": set()}


class ErrorBase(Exception):
    """Equivale a un RAISE EXCEPTION de PL/pgSQL."""


def _aplicado(order_id):
    return sum(p["amount"] for p in PAGOS.values()
               if p["order_id"] == order_id and p["status"] == "aplicado")


def _comprometido(order_id):
    return sum(p["amount"] for p in PAGOS.values()
               if p["order_id"] == order_id
               and p["status"] in ("aplicado", "autorizado", "pendiente"))


def _liquidar(order_id):
    """Reproduce el disparador trg_payments_settle_order."""
    pedido = PEDIDOS[order_id]
    if _aplicado(order_id) >= pedido["total"] and pedido["status"] == "pendiente":
        pedido["status"] = "pagado"


def fake_register(order_id, method_id, amount, registered_by=None,
                  idempotency_key=None, authorization_code=None,
                  card_last4=None, notes=None):
    """Reproduce sp_registrar_pago."""
    if idempotency_key:
        previo = next((p for p in PAGOS.values()
                       if p["idempotency_key"] == idempotency_key), None)
        if previo:
            return previo["id"]
    pedido = PEDIDOS.get(order_id)
    if pedido is None:
        raise ErrorBase(f"El pedido {order_id} no existe")
    if pedido["status"] == "cancelado":
        raise ErrorBase("No se puede pagar un pedido cancelado")
    metodo = METODOS.get(method_id)
    if metodo is None:
        raise ErrorBase(f"El metodo de pago {method_id} no existe")
    if not metodo["is_active"]:
        raise ErrorBase(f'El metodo de pago "{metodo["name"]}" esta desactivado')
    if _comprometido(order_id) + amount > pedido["total"]:
        raise ErrorBase(
            f"El pago excede el saldo del pedido: total {pedido['total']}, "
            f"comprometido {_comprometido(order_id)}, se intenta {amount}")

    pid = SIGUIENTE["id"]
    SIGUIENTE["id"] += 1
    estado = ("aplicado" if not metodo["requires_authorization"]
              else ("autorizado" if authorization_code else "pendiente"))
    PAGOS[pid] = {"id": pid, "payment_reference": f"PAG-{pid:06d}",
                  "order_id": order_id, "method_id": method_id,
                  "status": estado, "amount": float(amount),
                  "currency": pedido["currency"],
                  "authorization_code": authorization_code,
                  "idempotency_key": idempotency_key, "card_last4": card_last4,
                  "registered_by": registered_by, "notes": notes,
                  "created_at": AHORA, "authorized_at": None, "applied_at": None,
                  "rejected_at": None, "refunded_at": None}
    HISTORIAL[pid] = [{"from_status": None, "to_status": estado,
                       "changed_by": registered_by, "note": "pago registrado",
                       "changed_at": AHORA}]
    if estado == "aplicado":
        PAGOS[pid]["applied_at"] = AHORA
        _liquidar(order_id)
    return pid


def fake_apply(pid, changed_by=None, authorization_code=None):
    pid = int(pid)
    if pid not in PAGOS:
        raise ErrorBase(f"El pago {pid} no existe")
    actual = PAGOS[pid]["status"]
    if "aplicado" not in TRANSICIONES[actual]:
        raise ErrorBase(f"Transicion de pago no permitida: {actual} -> aplicado")
    PAGOS[pid]["status"] = "aplicado"
    PAGOS[pid]["applied_at"] = AHORA
    if authorization_code:
        PAGOS[pid]["authorization_code"] = authorization_code
    HISTORIAL[pid].append({"from_status": actual, "to_status": "aplicado",
                           "changed_by": changed_by, "note": None,
                           "changed_at": AHORA})
    _liquidar(PAGOS[pid]["order_id"])


def fake_change(pid, to_status, changed_by=None, note=None):
    pid = int(pid)
    if pid not in PAGOS:
        raise ErrorBase(f"El pago {pid} no existe")
    actual = PAGOS[pid]["status"]
    if to_status not in TRANSICIONES[actual]:
        raise ErrorBase(f"Transicion de pago no permitida: {actual} -> {to_status}")
    PAGOS[pid]["status"] = to_status
    PAGOS[pid][{"rechazado": "rejected_at", "reembolsado": "refunded_at",
                "autorizado": "authorized_at", "aplicado": "applied_at"}[to_status]] = AHORA
    HISTORIAL[pid].append({"from_status": actual, "to_status": to_status,
                           "changed_by": changed_by, "note": note,
                           "changed_at": AHORA})


def _vista(pid):
    """Equivale a una fila de v_payments_detail."""
    p = dict(PAGOS[pid])
    pedido = PEDIDOS[p["order_id"]]
    p["order_number"] = pedido["order_number"]
    p["order_status"] = pedido["status"]
    p["order_total"] = pedido["total"]
    p["user_id"] = pedido["user_id"]
    p["user_email"] = f"user{pedido['user_id']}@ejemplo.mx"
    p["method_name"] = METODOS[p["method_id"]]["name"]
    return p


def fake_list(filters, sort="created", order="desc", limit=50, offset=0):
    filas = [_vista(p) for p in PAGOS]
    if filters.get("user_id") is not None:
        filas = [f for f in filas if f["user_id"] == filters["user_id"]]
    if filters.get("order_id") is not None:
        filas = [f for f in filas if f["order_id"] == filters["order_id"]]
    if filters.get("status"):
        filas = [f for f in filas if f["status"] == filters["status"]]
    if filters.get("method"):
        filas = [f for f in filas if f["method_name"] == filters["method"]]
    filas.sort(key=lambda f: f["id"], reverse=(str(order).lower() != "asc"))
    return filas[offset:offset + limit], len(filas)


repo.register_payment = fake_register
repo.apply_payment = fake_apply
repo.change_status = fake_change
repo.list_payments = fake_list
repo.get_payment = lambda pid: (_vista(int(pid)) if int(pid) in PAGOS else None)
repo.get_by_reference = lambda ref: next(
    (_vista(p) for p in PAGOS if PAGOS[p]["payment_reference"] == ref), None)
repo.get_by_idempotency_key = lambda key: next(
    (_vista(p) for p in PAGOS if PAGOS[p]["idempotency_key"] == key), None)
repo.history_of = lambda pid: [dict(h) for h in HISTORIAL.get(int(pid), [])]
repo.list_methods = lambda only_active=True: [
    dict(m) for m in METODOS.values() if m["is_active"] or not only_active]
repo.get_method = lambda mid: (dict(METODOS[int(mid)]) if int(mid) in METODOS else None)
repo.get_method_by_name = lambda name: next(
    (dict(m) for m in METODOS.values() if m["name"].lower() == name.lower()), None)
repo.order_owner = lambda oid: (dict(PEDIDOS[int(oid)]) if int(oid) in PEDIDOS else None)
repo.order_by_number = lambda num: next(
    (dict(p) for p in PEDIDOS.values() if p["order_number"] == num), None)
repo.order_balance = lambda oid: (
    {"order_id": int(oid), "order_number": PEDIDOS[int(oid)]["order_number"],
     "status": PEDIDOS[int(oid)]["status"], "currency": PEDIDOS[int(oid)]["currency"],
     "total": PEDIDOS[int(oid)]["total"], "paid": _aplicado(int(oid)),
     "committed": _comprometido(int(oid)) - _aplicado(int(oid)),
     "balance": PEDIDOS[int(oid)]["total"] - _aplicado(int(oid))}
    if int(oid) in PEDIDOS else None)

PERMISOS = {1: {"*"}, 2: set(), 3: {"payments:read", "payments:write"}}
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
        user_id=user_id, email=f"user{user_id}@ejemplo.mx", role=rol,
        role_id=role_id, sid=f"sid-{user_id}")
    return {"Authorization": f"Bearer {tok}"}


# =====================================================================
print("1. Ninguna lectura es publica")
for ruta in ("/metodos", "/pagos", "/pagos/1", "/pedidos/100/saldo"):
    r = client.get(f"{ruta}?format=json")
    check(f"GET {ruta} sin token -> 401",
          r.status_code == 401 and r.get_json()["error"]["code"] == "unauthorized",
          str(r.status_code))
check("solo /health y /metrics son publicos",
      client.get("/health?format=json").status_code == 200
      and client.get("/metrics?format=json").status_code == 200)
r = client.get("/metodos?format=json", headers=auth(7))
check("con token, los metodos activos", r.status_code == 200
      and {m["name"] for m in r.get_json()["methods"]} == {"efectivo", "tarjeta"},
      r.get_data(as_text=True)[:200])
r = client.get("/metodos?format=json&all=true", headers=auth(7))
check("?all=true incluye los desactivados", len(r.get_json()["methods"]) == 3)

print("2. Registrar un pago")
r = client.post("/pagos?format=json",
                json={"orderId": 100, "amount": 400, "method": "tarjeta"},
                headers=auth(7))
cuerpo = r.get_json()
check("el dueno paga su pedido -> 201", r.status_code == 201,
      r.get_data(as_text=True)[:240])
PAGO1 = cuerpo["id"]
check("tarjeta sin codigo nace 'pendiente'", cuerpo["status"] == "pendiente",
      str(cuerpo["status"]))
check("trae la referencia legible", cuerpo["reference"].startswith("PAG-"),
      str(cuerpo["reference"]))
check("informa el saldo del pedido",
      cuerpo["balance"]["total"] == 1000.0 and cuerpo["balance"]["balance"] == 1000.0,
      str(cuerpo.get("balance")))
r = client.post("/pagos?format=json",
                json={"orderNumber": "PED-000100", "amount": 100,
                      "method": "tarjeta", "authorizationCode": "AUTH-123"},
                headers=auth(7))
check("por numero de pedido y con codigo nace 'autorizado'",
      r.status_code == 201 and r.get_json()["status"] == "autorizado",
      r.get_data(as_text=True)[:200])
PAGO2 = r.get_json()["id"]
r = client.post("/pagos?format=json",
                json={"orderId": 200, "amount": 100, "method": "efectivo"},
                headers=auth(7, role_id=3))
check("efectivo nace ya 'aplicado'", r.status_code == 201
      and r.get_json()["status"] == "aplicado", r.get_data(as_text=True)[:200])

print("3. Autorizacion al cobrar")
r = client.post("/pagos?format=json",
                json={"orderId": 200, "amount": 50, "method": "efectivo"},
                headers=auth(7))
check("pagar el pedido de otro sin permiso -> 403", r.status_code == 403,
      r.get_data(as_text=True)[:200])
r = client.post("/pagos?format=json",
                json={"orderId": 300, "amount": 50, "method": "efectivo"},
                headers=auth(7))
check("pagar un pedido cancelado -> 409", r.status_code == 409
      and "cancelado" in r.get_data(as_text=True), r.get_data(as_text=True)[:200])
r = client.post("/pagos?format=json",
                json={"orderId": 9999, "amount": 50, "method": "efectivo"},
                headers=auth(7, role_id=3))
check("pedido inexistente -> 404", r.status_code == 404, str(r.status_code))

print("4. Validacion del importe y del metodo")
r = client.post("/pagos?format=json", json={"orderId": 100, "method": "tarjeta"},
                headers=auth(7))
check("sin importe -> 400", r.status_code == 400, str(r.status_code))
r = client.post("/pagos?format=json",
                json={"orderId": 100, "amount": -5, "method": "tarjeta"},
                headers=auth(7))
check("importe negativo -> 400", r.status_code == 400, str(r.status_code))
r = client.post("/pagos?format=json",
                json={"orderId": 100, "amount": "mucho", "method": "tarjeta"},
                headers=auth(7))
check("importe no numerico -> 400", r.status_code == 400, str(r.status_code))
r = client.post("/pagos?format=json", json={"orderId": 100, "amount": 10},
                headers=auth(7))
check("sin metodo -> 400 que remite al catalogo",
      r.status_code == 400 and "/metodos" in r.get_data(as_text=True),
      r.get_data(as_text=True)[:200])
r = client.post("/pagos?format=json",
                json={"orderId": 100, "amount": 10, "method": "retirado"},
                headers=auth(7))
check("metodo desactivado -> 409", r.status_code == 409, str(r.status_code))
r = client.post("/pagos?format=json",
                json={"orderId": 100, "amount": 900, "method": "tarjeta"},
                headers=auth(7))
check("importe que excede el saldo -> 409 que lo explica",
      r.status_code == 409 and "excede" in r.get_data(as_text=True),
      r.get_data(as_text=True)[:240])

print("5. Datos de tarjeta rechazados")
for campo in ("cardNumber", "cvv", "pan", "titular"):
    r = client.post("/pagos?format=json",
                    json={"orderId": 100, "amount": 10, "method": "tarjeta",
                          campo: "4111111111111111"},
                    headers=auth(7))
    check(f"se rechaza el campo {campo} -> 400",
          r.status_code == 400 and "no acepta datos de tarjeta" in r.get_data(as_text=True),
          r.get_data(as_text=True)[:200])
r = client.post("/pagos?format=json",
                json={"orderId": 100, "amount": 10, "method": "tarjeta",
                      "cardLast4": "4111111111111111"},
                headers=auth(7))
check("cardLast4 con un numero completo -> 400",
      r.status_code == 400 and "4 digitos" in r.get_data(as_text=True),
      r.get_data(as_text=True)[:220])
r = client.post("/pagos?format=json",
                json={"orderId": 100, "amount": 10, "method": "tarjeta",
                      "cardLast4": "1111"},
                headers=auth(7))
check("cardLast4 con cuatro digitos si se admite",
      r.status_code == 201 and r.get_json()["cardLast4"] == "1111",
      r.get_data(as_text=True)[:200])
PAGO_L4 = r.get_json()["id"]

print("6. Cobro doble: idempotencyKey y cerrojo")
cuerpo_pago = {"orderId": 200, "amount": 100, "method": "efectivo",
               "idempotencyKey": "demo-001"}
r1 = client.post("/pagos?format=json", json=cuerpo_pago, headers=auth(7, role_id=3))
r2 = client.post("/pagos?format=json", json=cuerpo_pago, headers=auth(7, role_id=3))
check("el primer intento crea el pago", r1.status_code == 201,
      r1.get_data(as_text=True)[:160])
check("el segundo devuelve EL MISMO pago, no otro",
      r2.status_code == 200 and r2.get_json()["id"] == r1.get_json()["id"]
      and r2.get_json().get("idempotentReplay") is True,
      r2.get_data(as_text=True)[:240])
check("y no se cobro dos veces",
      sum(1 for p in PAGOS.values() if p["idempotency_key"] == "demo-001") == 1)
tomado = shared.store.strict_set(shared.store.key("lock", "pago:pedido:200"),
                                 "otro-proceso", 10, only_if_absent=True)
r = client.post("/pagos?format=json",
                json={"orderId": 200, "amount": 50, "method": "efectivo"},
                headers=auth(7, role_id=3))
check("con el cerrojo del pedido tomado -> 409",
      tomado and r.status_code == 409 and "en curso" in r.get_data(as_text=True),
      r.get_data(as_text=True)[:200])
shared.store.strict_delete(shared.store.key("lock", "pago:pedido:200"))

print("7. Aplicar: el pago mueve el PEDIDO")
check("el pedido 100 sigue pendiente", PEDIDOS[100]["status"] == "pendiente")
r = client.post(f"/pagos/{PAGO1}/aplicar?format=json", headers=auth(7))
check("aplicar sin payments:write -> 403", r.status_code == 403, str(r.status_code))
r = client.post(f"/pagos/{PAGO1}/aplicar?format=json", headers=auth(7, role_id=3))
check("aplicar con permiso -> 200", r.status_code == 200
      and r.get_json()["status"] == "aplicado", r.get_data(as_text=True)[:200])
check("el pedido sigue pendiente porque aun no se cubre el total",
      PEDIDOS[100]["status"] == "pendiente" and _aplicado(100) == 400.0,
      f"{PEDIDOS[100]['status']} aplicado={_aplicado(100)}")
r = client.post(f"/pagos/{PAGO1}/aplicar?format=json", headers=auth(7, role_id=3))
check("aplicar dos veces es idempotente", r.status_code == 200
      and r.get_json().get("alreadyApplied") is True,
      r.get_data(as_text=True)[:160])
client.post(f"/pagos/{PAGO2}/aplicar?format=json", headers=auth(7, role_id=3))
client.post(f"/pagos/{PAGO_L4}/aplicar?format=json", headers=auth(7, role_id=3))
r = client.post("/pagos?format=json",
                json={"orderId": 100, "amount": 490, "method": "efectivo"},
                headers=auth(7, role_id=3))
check("el ultimo pago cubre el total y el PEDIDO pasa a 'pagado'",
      r.status_code == 201 and PEDIDOS[100]["status"] == "pagado"
      and _aplicado(100) == 1000.0,
      f"{r.status_code} estado={PEDIDOS[100]['status']} aplicado={_aplicado(100)}")

print("8. Rechazar y reembolsar")
r = client.post("/pagos?format=json",
                json={"orderId": 200, "amount": 100, "method": "tarjeta"},
                headers=auth(7, role_id=3))
PAGO_R = r.get_json()["id"]
r = client.post(f"/pagos/{PAGO_R}/rechazar?format=json",
                json={"note": "fondos insuficientes"}, headers=auth(7, role_id=3))
check("rechazar -> 200", r.status_code == 200
      and r.get_json()["status"] == "rechazado", r.get_data(as_text=True)[:200])
r = client.post(f"/pagos/{PAGO_R}/aplicar?format=json", headers=auth(7, role_id=3))
check("aplicar uno rechazado -> 409 (transicion invalida)",
      r.status_code == 409 and "Transicion" in r.get_data(as_text=True),
      r.get_data(as_text=True)[:240])
r = client.post(f"/pagos/{PAGO_R}/reembolsar?format=json", headers=auth(7, role_id=3))
check("reembolsar uno no aplicado -> 409 que sugiere rechazarlo",
      r.status_code == 409 and "rechacelo" in r.get_data(as_text=True),
      r.get_data(as_text=True)[:240])
r = client.post(f"/pagos/{PAGO1}/reembolsar?format=json",
                json={"note": "devolucion"}, headers=auth(7, role_id=3))
cuerpo = r.get_json()
check("reembolsar uno aplicado -> 200", r.status_code == 200
      and cuerpo["status"] == "reembolsado", r.get_data(as_text=True)[:200])
check("el pedido NO vuelve a 'pendiente' y se avisa",
      PEDIDOS[100]["status"] == "pagado" and "no vuelve" in cuerpo["note"].lower(),
      f"{PEDIDOS[100]['status']} / {cuerpo.get('note')}")

print("9. Consultas y saldo")
r = client.get("/pagos?format=json", headers=auth(8))
check("un cliente ve solo los pagos de SUS pedidos", r.status_code == 200
      and all(p["order"]["id"] == 200 for p in r.get_json()["payments"]),
      r.get_data(as_text=True)[:200])
r = client.get("/pagos?format=json&all=true", headers=auth(8))
check("?all=true sin payments:read -> 403", r.status_code == 403, str(r.status_code))
r = client.get("/pagos?format=json&all=true", headers=auth(8, role_id=3))
check("?all=true con permiso -> ve todos", r.status_code == 200
      and r.get_json()["total"] >= 5, r.get_data(as_text=True)[:160])
r = client.get(f"/pagos/{PAGO1}?format=json", headers=auth(8))
check("ver el pago de otro -> 403", r.status_code == 403, str(r.status_code))
r = client.get(f"/pagos/{PAGO1}?format=json", headers=auth(7))
check("el dueno ve el suyo, con bitacora", r.status_code == 200
      and len(r.get_json()["history"]) >= 3, r.get_data(as_text=True)[:200])
r = client.get("/pagos/referencia/PAG-000001?format=json", headers=auth(7))
check("buscar por referencia", r.status_code == 200
      and r.get_json()["reference"] == "PAG-000001", r.get_data(as_text=True)[:160])
r = client.get("/pedidos/100/saldo?format=json", headers=auth(7))
saldo = r.get_json()
check("saldo del pedido", r.status_code == 200 and saldo["total"] == 1000.0
      and saldo["orderStatus"] == "pagado", r.get_data(as_text=True)[:200])
r = client.get("/pedidos/200/saldo?format=json", headers=auth(7))
check("saldo de un pedido ajeno -> 403", r.status_code == 403, str(r.status_code))

print("10. Formatos y Redis caido")
r = client.get("/metodos", headers=auth(7))
check("XML por omision", r.get_data(as_text=True).startswith("<?xml")
      and "<method>" in r.get_data(as_text=True), r.get_data(as_text=True)[:160])
r = client.post("/pagos", json={"orderId": 100}, headers=auth(7))
check("el error tambien sale en XML", r.status_code == 400
      and "<error" in r.get_data(as_text=True), r.get_data(as_text=True)[:160])
redis_testing.break_store(shared.store)
r = client.get("/metodos?format=json", headers=auth(7))
check("sin poder comprobar la revocacion -> 503", r.status_code == 503
      and r.get_json()["error"]["code"] == "redis_unavailable",
      f"{r.status_code} {r.get_data(as_text=True)[:140]}")
r = client.post("/pagos?format=json",
                json={"orderId": 200, "amount": 10, "method": "efectivo"},
                headers=auth(7, role_id=3))
check("registrar con Redis caido -> 503", r.status_code == 503, str(r.status_code))
r = client.get("/health?format=json")
check("health -> 503 (este servicio no tiene puerta publica)",
      r.status_code == 503 and r.get_json()["status"] == "degraded",
      f"{r.status_code} {r.get_json().get('status')}")
check("health no filtra la clave de Redis", "prueba" not in r.get_data(as_text=True))
redis_testing.install(shared.store, FAKE)
r = client.get("/metrics?format=json")
m = r.get_json()
check("metrics cuenta pagos registrados y aplicados",
      m["counters"].get("payments.registered", 0) > 0
      and m["counters"].get("payments.applied", 0) > 0, str(m["counters"])[:240])
check("metrics cuenta los reintentos idempotentes",
      m["counters"].get("payments.idempotent_hit", 0) > 0, str(m["counters"])[:240])

print(f"\nResultado: {PASSED} OK, {FAILED} fallos")
sys.exit(1 if FAILED else 0)
