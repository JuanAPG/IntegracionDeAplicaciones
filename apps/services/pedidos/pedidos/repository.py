"""
apps/services/pedidos/pedidos/repository.py
Todo el SQL del microservicio de pedidos.

EL STOCK NO SE DUPLICA
  library.books.stock ya existe y lo expone el microservicio de libros.
  Este servicio NO lleva un inventario paralelo: reserva y devuelve
  unidades sobre books.stock dentro de la MISMA transaccion que escribe
  las lineas, mediante los procedimientos de
  data/pedidos_migration.sql. Dos tablas de stock serian dos verdades.

LA LOGICA DELICADA ESTA EN LA BASE
  Crear un pedido (reservar stock sin condiciones de carrera), cancelarlo
  (devolver stock) y mover su estado (transiciones validas) son
  procedimientos almacenados: sp_crear_pedido, sp_cancelar_pedido y
  sp_cambiar_estado_pedido. Asi la regla se cumple aunque la escriba otro
  cliente, y la reserva de stock es atomica de verdad.

LLAMADAS A PROCEDIMIENTOS: CADA PARAMETRO CON SU CAST
  Psycopg 3 envia los parametros tipados: un int pequeno viaja como
  smallint, un float como double precision y un str o None como unknown.
  PostgreSQL resuelve la sobrecarga de una funcion solo con conversiones
  IMPLICITAS, y double precision -> numeric no lo es: sin el cast la
  llamada falla con "function ... does not exist". Por eso cada %s lleva
  el tipo exacto de la firma del procedimiento.

Todas las consultas usan parametros (%s). El nombre de la columna de
ordenacion sale de una lista blanca.
"""
import json

from .shared import database

SORTABLE = {"id": "o.id", "number": "o.order_number", "total": "o.total",
            "status": "o.status", "placed": "o.placed_at",
            "updated": "o.updated_at"}

ESTADOS = ("pendiente", "pagado", "enviado", "entregado", "cancelado")
# Lo que el rastreo PUBLICO puede revelar. Se escribe aqui, explicito,
# para que nadie anada un campo por descuido.
TRACKING_FIELDS = ("order_number", "status", "carrier", "tracking_code",
                   "placed_at", "shipped_at", "delivered_at", "item_count")


def _iso(value):
    return value.isoformat() if hasattr(value, "isoformat") else value


def _money(value):
    return float(value) if value is not None else None


def order_to_dict(row, lines=None, history=None):
    """Fila de v_orders_detail -> diccionario JSON en camelCase."""
    if row is None:
        return None
    payload = {
        "id": row["id"],
        "orderNumber": row["order_number"],
        "status": row["status"],
        "currency": row.get("currency"),
        "subtotal": _money(row.get("subtotal")),
        "shippingCost": _money(row.get("shipping_cost")),
        "total": _money(row.get("total")),
        "paidAmount": _money(row.get("paid_amount")),
        "user": {"id": row.get("user_id"), "email": row.get("user_email"),
                 "name": row.get("user_name")},
        "shipping": {"carrier": row.get("carrier"),
                     "trackingCode": row.get("tracking_code")},
        "lineCount": row.get("line_count"),
        "itemCount": row.get("item_count"),
        "placedAt": _iso(row.get("placed_at")),
        "paidAt": _iso(row.get("paid_at")),
        "shippedAt": _iso(row.get("shipped_at")),
        "deliveredAt": _iso(row.get("delivered_at")),
        "cancelledAt": _iso(row.get("cancelled_at")),
    }
    if lines is not None:
        payload["lines"] = lines
    if history is not None:
        payload["history"] = history
    return payload


def line_to_dict(row):
    return {
        "id": row["id"],
        "bookId": row["book_id"],
        "isbn": row["book_isbn"],
        "title": row["book_title"],
        "quantity": row["quantity"],
        "unitPrice": _money(row["unit_price"]),
        "lineTotal": _money(row["line_total"]),
    }


def history_to_dict(row):
    return {
        "fromStatus": row.get("from_status"),
        "toStatus": row["to_status"],
        "changedBy": row.get("changed_by"),
        "note": row.get("note"),
        "changedAt": _iso(row.get("changed_at")),
    }


def tracking_to_dict(row):
    """
    Rastreo PUBLICO: solo el estado del envio.

    Es la unica cara de un pedido que se sirve sin token, para que la
    paqueteria pueda manejar su logistica. NO lleva dueno, ni correo, ni
    importes, ni que libros se compraron. Se construye campo por campo
    desde TRACKING_FIELDS en lugar de filtrar una fila completa: asi,
    anadir una columna a la vista no la publica por accidente.
    """
    if row is None:
        return None
    return {
        "orderNumber": row["order_number"],
        "status": row["status"],
        "carrier": row.get("carrier"),
        "trackingCode": row.get("tracking_code"),
        "placedAt": _iso(row.get("placed_at")),
        "shippedAt": _iso(row.get("shipped_at")),
        "deliveredAt": _iso(row.get("delivered_at")),
        "itemCount": row.get("item_count"),
    }


# ---------------------------------------------------------------------
# Lectura
# ---------------------------------------------------------------------
def list_orders(filters, sort="placed", order="desc", limit=50, offset=0):
    where = []
    params = []
    if filters.get("user_id") is not None:
        where.append("o.user_id = %s")
        params.append(filters["user_id"])
    if filters.get("status"):
        where.append("o.status::text = %s")
        params.append(filters["status"])
    if filters.get("number"):
        where.append("o.order_number ILIKE %s")
        params.append(f"%{filters['number']}%")
    if filters.get("from"):
        where.append("o.placed_at >= %s")
        params.append(filters["from"])
    if filters.get("to"):
        where.append("o.placed_at <= %s")
        params.append(filters["to"])

    clause = (" WHERE " + " AND ".join(where)) if where else ""
    column = SORTABLE.get(sort, "o.placed_at")
    direction = "ASC" if str(order).lower() == "asc" else "DESC"

    with database.cursor() as cur:
        cur.execute(f"SELECT count(*) AS total FROM v_orders_detail o{clause}", params)
        total = cur.fetchone()["total"]
        cur.execute(
            f"SELECT * FROM v_orders_detail o{clause} "
            f"ORDER BY {column} {direction}, o.id DESC LIMIT %s OFFSET %s",
            params + [limit, offset])
        return cur.fetchall(), total


def get_order(order_id):
    with database.cursor() as cur:
        cur.execute("SELECT * FROM v_orders_detail WHERE id = %s", (order_id,))
        return cur.fetchone()


def get_order_by_number(order_number):
    with database.cursor() as cur:
        cur.execute("SELECT * FROM v_orders_detail WHERE order_number = %s",
                    (order_number,))
        return cur.fetchone()


def lines_of(order_id):
    with database.cursor() as cur:
        cur.execute(
            "SELECT id, book_id, book_isbn, book_title, quantity, unit_price, "
            "       line_total FROM order_lines WHERE order_id = %s "
            " ORDER BY id", (order_id,))
        return cur.fetchall()


def history_of(order_id):
    with database.cursor() as cur:
        cur.execute(
            "SELECT from_status, to_status, changed_by, note, changed_at "
            "  FROM order_status_history WHERE order_id = %s "
            " ORDER BY changed_at, id", (order_id,))
        return cur.fetchall()


def tracking_of(order_number):
    """Rastreo publico: lee la vista que solo expone el estado del envio."""
    with database.cursor() as cur:
        cur.execute(
            "SELECT order_number, status, carrier, tracking_code, placed_at, "
            "       shipped_at, delivered_at, item_count "
            "  FROM v_order_tracking WHERE order_number = %s", (order_number,))
        return cur.fetchone()


def owner_of(order_id):
    """Solo el dueno, para decidir la autorizacion sin traer el pedido entero."""
    with database.cursor() as cur:
        cur.execute("SELECT user_id, status FROM orders WHERE id = %s", (order_id,))
        return cur.fetchone()


def user_is_active(user_id):
    with database.cursor() as cur:
        cur.execute("SELECT id, email, is_active FROM users WHERE id = %s", (user_id,))
        return cur.fetchone()


def books_availability(book_ids):
    """Stock y precio actuales, para avisar ANTES de intentar la reserva."""
    if not book_ids:
        return {}
    with database.cursor() as cur:
        cur.execute(
            "SELECT id, isbn, title, price, stock FROM books WHERE id = ANY(%s)",
            (list(book_ids),))
        return {row["id"]: row for row in cur.fetchall()}


# ---------------------------------------------------------------------
# Escritura (via procedimientos almacenados)
# ---------------------------------------------------------------------
def create_order(user_id, lines, notes=None, currency="MXN",
                 shipping_cost=0, shipping_address=None):
    """
    Crea el pedido reservando stock. Devuelve el id.

    Las lineas van como JSON a sp_crear_pedido, que es quien congela el
    precio desde library.books, resta el stock de forma atomica y revienta
    con un mensaje legible si no alcanza. El precio NO lo manda el
    cliente: nadie se compra un libro a su propio precio.
    """
    payload = json.dumps([{"bookId": int(l["bookId"]), "quantity": int(l["quantity"])}
                          for l in lines])
    with database.cursor(commit=True) as cur:
        cur.execute(
            "SELECT sp_crear_pedido(%s::integer, %s::jsonb, %s::text, "
            "%s::char(3), %s::numeric, %s::text) AS id",
            (user_id, payload, notes, currency, shipping_cost, shipping_address))
        return cur.fetchone()["id"]


def adjust_line(order_id, book_id, quantity):
    """Cambia la cantidad de una linea ajustando el stock por la diferencia."""
    with database.cursor(commit=True) as cur:
        cur.execute("SELECT sp_ajustar_linea_pedido(%s::bigint, %s::integer, %s::integer)",
                    (order_id, book_id, quantity))


def cancel_order(order_id, changed_by=None, reason=None):
    """Cancela DEVOLVIENDO el stock reservado."""
    with database.cursor(commit=True) as cur:
        cur.execute("SELECT sp_cancelar_pedido(%s::bigint, %s::integer, %s::varchar)",
                    (order_id, changed_by, reason))


def change_status(order_id, to_status, changed_by=None, note=None,
                  carrier=None, tracking_code=None):
    """Mueve el estado. La transicion la valida un disparador de la base."""
    with database.cursor(commit=True) as cur:
        cur.execute(
            "SELECT sp_cambiar_estado_pedido(%s::bigint, %s::library.order_status, "
            "%s::integer, %s::varchar, %s::varchar, %s::varchar)",
            (order_id, to_status, changed_by, note, carrier, tracking_code))
