"""
apps/services/pagos/pagos/repository.py
Todo el SQL del microservicio de pagos.

QUE SE GUARDA Y QUE NO
  Se registra el HECHO del pago: cuanto, con que metodo, cuando, contra
  que pedido y con que referencia de la pasarela.
  NO se guarda el instrumento de pago: ni numero de tarjeta, ni CVV, ni
  fecha de vencimiento, ni titular. Como mucho, los cuatro ultimos
  digitos que la propia pasarela publica. Lo que no se guarda no se
  puede filtrar.

EL PAGO MUEVE EL PEDIDO, PERO NO LO DECIDE ESTE CODIGO
  Cuando la suma de los pagos APLICADOS alcanza el total del pedido, un
  DISPARADOR de la base lo pasa a 'pagado'. Asi no hay forma de marcar
  un pedido como pagado sin que exista el dinero detras, venga la
  escritura de donde venga.

La logica delicada vive en procedimientos almacenados
(sp_registrar_pago, sp_aplicar_pago, sp_cambiar_estado_pago), definidos
en data/pagos_migration.sql.

LLAMADAS A PROCEDIMIENTOS: CADA PARAMETRO CON SU CAST
  Psycopg 3 envia los parametros tipados: un int pequeno viaja como
  smallint, un float como double precision y un str o None como unknown.
  PostgreSQL resuelve la sobrecarga de una funcion solo con conversiones
  IMPLICITAS, y double precision -> numeric no lo es: sin el cast la
  llamada falla con "function ... does not exist". Por eso cada %s lleva
  el tipo exacto de la firma del procedimiento.
"""
from .shared import database

SORTABLE = {"id": "p.id", "reference": "p.payment_reference",
            "amount": "p.amount", "status": "p.status",
            "created": "p.created_at", "applied": "p.applied_at"}

ESTADOS = ("pendiente", "autorizado", "aplicado", "rechazado", "reembolsado")


def _iso(value):
    return value.isoformat() if hasattr(value, "isoformat") else value


def _money(value):
    return float(value) if value is not None else None


def payment_to_dict(row, history=None):
    """Fila de v_payments_detail -> diccionario JSON en camelCase."""
    if row is None:
        return None
    payload = {
        "id": row["id"],
        "reference": row["payment_reference"],
        "status": row["status"],
        "amount": _money(row.get("amount")),
        "currency": row.get("currency"),
        "method": {"id": row.get("method_id"), "name": row.get("method_name")},
        "order": {"id": row.get("order_id"),
                  "number": row.get("order_number"),
                  "status": row.get("order_status"),
                  "total": _money(row.get("order_total"))},
        # authorizationCode y cardLast4 son lo UNICO que se guarda del
        # instrumento de pago, y los publica la propia pasarela.
        "authorizationCode": row.get("authorization_code"),
        "cardLast4": (row.get("card_last4") or "").strip() or None,
        "registeredBy": row.get("registered_by"),
        "notes": row.get("notes"),
        "createdAt": _iso(row.get("created_at")),
        "authorizedAt": _iso(row.get("authorized_at")),
        "appliedAt": _iso(row.get("applied_at")),
        "rejectedAt": _iso(row.get("rejected_at")),
        "refundedAt": _iso(row.get("refunded_at")),
    }
    if history is not None:
        payload["history"] = history
    return payload


def method_to_dict(row):
    return {
        "id": row["id"],
        "name": row["name"],
        "description": row.get("description") or "",
        "requiresAuthorization": bool(row.get("requires_authorization")),
        "isActive": bool(row.get("is_active", True)),
    }


def balance_to_dict(row):
    if row is None:
        return None
    return {
        "orderId": row["order_id"],
        "orderNumber": row["order_number"],
        "orderStatus": row["status"],
        "currency": row.get("currency"),
        "total": _money(row.get("total")),
        "paid": _money(row.get("paid")),
        "committed": _money(row.get("committed")),
        "balance": _money(row.get("balance")),
    }


def history_to_dict(row):
    return {
        "fromStatus": row.get("from_status"),
        "toStatus": row["to_status"],
        "changedBy": row.get("changed_by"),
        "note": row.get("note"),
        "changedAt": _iso(row.get("changed_at")),
    }


# ---------------------------------------------------------------------
# Lectura
# ---------------------------------------------------------------------
def list_payments(filters, sort="created", order="desc", limit=50, offset=0):
    where = []
    params = []
    if filters.get("user_id") is not None:
        where.append("p.user_id = %s")
        params.append(filters["user_id"])
    if filters.get("order_id") is not None:
        where.append("p.order_id = %s")
        params.append(filters["order_id"])
    if filters.get("status"):
        where.append("p.status::text = %s")
        params.append(filters["status"])
    if filters.get("method"):
        where.append("p.method_name = %s")
        params.append(filters["method"])

    clause = (" WHERE " + " AND ".join(where)) if where else ""
    column = SORTABLE.get(sort, "p.created_at")
    direction = "ASC" if str(order).lower() == "asc" else "DESC"

    with database.cursor() as cur:
        cur.execute(f"SELECT count(*) AS total FROM v_payments_detail p{clause}",
                    params)
        total = cur.fetchone()["total"]
        cur.execute(
            f"SELECT * FROM v_payments_detail p{clause} "
            f"ORDER BY {column} {direction}, p.id DESC LIMIT %s OFFSET %s",
            params + [limit, offset])
        return cur.fetchall(), total


def get_payment(payment_id):
    with database.cursor() as cur:
        cur.execute("SELECT * FROM v_payments_detail WHERE id = %s", (payment_id,))
        return cur.fetchone()


def get_by_reference(reference):
    with database.cursor() as cur:
        cur.execute("SELECT * FROM v_payments_detail WHERE payment_reference = %s",
                    (reference,))
        return cur.fetchone()


def get_by_idempotency_key(key):
    with database.cursor() as cur:
        cur.execute("SELECT * FROM v_payments_detail WHERE id = "
                    "(SELECT id FROM payments WHERE idempotency_key = %s)", (key,))
        return cur.fetchone()


def history_of(payment_id):
    with database.cursor() as cur:
        cur.execute(
            "SELECT from_status, to_status, changed_by, note, changed_at "
            "  FROM payment_status_history WHERE payment_id = %s "
            " ORDER BY changed_at, id", (payment_id,))
        return cur.fetchall()


def list_methods(only_active=True):
    with database.cursor() as cur:
        cur.execute(
            "SELECT id, name, description, requires_authorization, is_active "
            "  FROM payment_methods"
            + (" WHERE is_active" if only_active else "")
            + " ORDER BY id")
        return cur.fetchall()


def get_method(method_id):
    with database.cursor() as cur:
        cur.execute(
            "SELECT id, name, description, requires_authorization, is_active "
            "  FROM payment_methods WHERE id = %s", (method_id,))
        return cur.fetchone()


def get_method_by_name(name):
    with database.cursor() as cur:
        cur.execute(
            "SELECT id, name, description, requires_authorization, is_active "
            "  FROM payment_methods WHERE lower(name) = lower(%s)", (name,))
        return cur.fetchone()


def order_balance(order_id):
    with database.cursor() as cur:
        cur.execute("SELECT * FROM v_order_balance WHERE order_id = %s", (order_id,))
        return cur.fetchone()


def order_owner(order_id):
    """Dueno y estado del pedido, para decidir la autorizacion."""
    with database.cursor() as cur:
        cur.execute(
            "SELECT id, user_id, status, total, currency, order_number "
            "  FROM orders WHERE id = %s", (order_id,))
        return cur.fetchone()


def order_by_number(order_number):
    with database.cursor() as cur:
        cur.execute(
            "SELECT id, user_id, status, total, currency, order_number "
            "  FROM orders WHERE order_number = %s", (order_number,))
        return cur.fetchone()


# ---------------------------------------------------------------------
# Escritura (via procedimientos almacenados)
# ---------------------------------------------------------------------
def register_payment(order_id, method_id, amount, registered_by=None,
                     idempotency_key=None, authorization_code=None,
                     card_last4=None, notes=None):
    """
    Registra el pago. Devuelve el id.

    sp_registrar_pago comprueba que el importe no exceda el saldo del
    pedido, que el metodo exista y este activo, y que el pedido no este
    cancelado. Si la clave de idempotencia ya existe, devuelve el pago
    que ya estaba en lugar de crear otro.
    """
    with database.cursor(commit=True) as cur:
        cur.execute(
            "SELECT sp_registrar_pago(%s::bigint, %s::integer, %s::numeric, "
            "%s::integer, %s::varchar, %s::varchar, %s::char(4), %s::varchar) AS id",
            (order_id, method_id, amount, registered_by, idempotency_key,
             authorization_code, card_last4, notes))
        return cur.fetchone()["id"]


def apply_payment(payment_id, changed_by=None, authorization_code=None):
    """
    Aplica (confirma) un pago. Si con eso se cubre el total del pedido,
    un disparador de la base lo pasa a 'pagado'.
    """
    with database.cursor(commit=True) as cur:
        cur.execute("SELECT sp_aplicar_pago(%s::bigint, %s::integer, %s::varchar)",
                    (payment_id, changed_by, authorization_code))


def change_status(payment_id, to_status, changed_by=None, note=None):
    """Rechaza o reembolsa. La transicion la valida un disparador."""
    with database.cursor(commit=True) as cur:
        cur.execute(
            "SELECT sp_cambiar_estado_pago(%s::bigint, %s::library.payment_status, "
            "%s::integer, %s::varchar)",
            (payment_id, to_status, changed_by, note))
