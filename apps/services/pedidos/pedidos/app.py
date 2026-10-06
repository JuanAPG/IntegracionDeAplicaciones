"""
apps/services/pedidos/pedidos/app.py
Microservicio Flask de PEDIDOS: pedidos, lineas, reserva de stock y
estados (library_db / esquema library).

Restricciones de la practica
  * Flask SIN blueprints; Psycopg 3; credenciales solo por entorno.
  * XML y JSON (?format= / ?output= / Accept). Sin parametro, XML.
  * CORS enumerando los origenes de las aplicaciones cliente.

EL STOCK NO SE DUPLICA
  library.books.stock ya existe y lo publica el microservicio de libros.
  Aqui se RESERVA al crear el pedido y se DEVUELVE al cancelarlo, en la
  misma transaccion que las lineas, mediante procedimientos almacenados.
  No hay una segunda tabla de inventario.

QUE ES PUBLICO
  Solo GET /envios/<numero>: el ESTATUS DE ENVIO, para que un tercero
  pueda manejar su logistica. Devuelve numero, estado, paqueteria, guia,
  fechas y cuantas piezas; nada de dueno, correo, importes ni que libros
  se compraron.
  Todo lo demas exige Authorization: Bearer <JWT>.

AUTORIZACION
  * Un cliente opera sobre LO SUYO con solo tener un token valido: crea
    sus pedidos, los lista y los cancela mientras sigan pendientes.
  * Ver o tocar pedidos ajenos exige permisos:
        orders:read    ver cualquier pedido
        orders:write   crear pedidos a nombre de otro, cancelar cualquiera
        orders:status  mover el estado (enviado, entregado)
  * 401 token ausente/invalido/caducado/revocado · 403 rol insuficiente
    · 503 Redis o PostgreSQL caidos.
"""
import logging

from flasgger import Swagger
from flask import Flask, request
from werkzeug.exceptions import HTTPException

from . import _bootstrap  # noqa: F401
from . import cache as order_cache
from . import config
from . import openapi
from . import repository as repo
from .shared import (
    database,
    negotiator,
    permission_required,
    store,
    token_required,
)
from library_common import logging_support, metrics
from library_common.db import raised_message
from library_common.errors import (
    Conflict,
    Forbidden,
    NotFound,
    Unauthorized,
    ValidationError,
)
from library_common.flask_support import (
    configure_cors,
    install_security_headers,
    metrics_payload,
    register_error_handlers,
    register_request_metrics,
)
from library_common.jwt_auth import current_identity

log = logging_support.configure(
    logging.DEBUG if config.DEBUG else logging.INFO, service="pedidos")

app = Flask(__name__)
app.json.sort_keys = False
API = config.API_PREFIX

configure_cors(app, config.CORS_ORIGINS, with_credentials=False,
               max_age=config.CORS_MAX_AGE, service="pedidos")
install_security_headers(app)
register_request_metrics(app, "pedidos")

SWAGGER_CONFIG = {
    "openapi": "3.0.3", "uiversion": 3, "headers": [],
    "title": "Libreria en Linea — Microservicio de pedidos",
    "specs": [{"endpoint": "openapi", "route": "/openapi.json",
               "rule_filter": lambda rule: False,
               "model_filter": lambda tag: True}],
    "static_url_path": "/docs/static", "swagger_ui": True,
    "specs_route": "/docs/",
}
swagger = Swagger(app, template=openapi.build_spec(), config=SWAGGER_CONFIG, merge=False)

MAX_LINEAS = 50
MAX_UNIDADES = 100


# =====================================================================
# Lectura del cuerpo y de los parametros
# =====================================================================
def _local(tag):
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def _xml_dict(text):
    from xml.etree import ElementTree
    try:
        root = ElementTree.fromstring(text)
    except ElementTree.ParseError as exc:
        raise ValidationError("El cuerpo XML no se pudo interpretar.",
                              [str(exc).strip()]) from exc

    def nodo(elemento):
        if not len(elemento):
            return (elemento.text or "").strip()
        hijos = [_local(h.tag) for h in elemento]
        # <lines><line>...</line><line>...</line></lines> -> lista
        if len(set(hijos)) == 1 and len(hijos) >= 1:
            return [nodo(h) for h in elemento]
        return {_local(h.tag): nodo(h) for h in elemento}

    return {_local(hijo.tag): nodo(hijo) for hijo in root}


def read_payload():
    ctype = (request.content_type or "").lower()
    if "json" in ctype:
        data = request.get_json(silent=True)
        if data is None:
            raise ValidationError("El cuerpo JSON no se pudo interpretar.")
        if not isinstance(data, dict):
            raise ValidationError("El cuerpo JSON debe ser un objeto.")
        return data
    if "xml" in ctype or (request.data or b"").lstrip().startswith(b"<"):
        return _xml_dict(request.get_data(as_text=True))
    if request.form:
        return dict(request.form)
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else {}


def _pick(data, *names, default=""):
    for name in names:
        if name in data and data[name] not in (None, ""):
            value = data[name]
            return value.strip() if isinstance(value, str) else value
    return default


def _pagination():
    def positive(name, default, maximum=None):
        raw = request.args.get(name)
        if raw in (None, ""):
            return default
        try:
            value = int(raw)
        except ValueError:
            raise ValidationError(f"El parametro '{name}' debe ser un entero.")
        if value < 0:
            raise ValidationError(f"El parametro '{name}' no puede ser negativo.")
        return min(value, maximum) if maximum else value

    limit = positive("limit", config.DEFAULT_LIMIT, config.MAX_LIMIT)
    return max(limit, 1), positive("offset", 0)


def _read_lines(data):
    """
    Interpreta y valida las lineas del pedido.

    Acepta [{"bookId": 3, "quantity": 2}, ...] y tambien la forma corta
    {"3": 2}. Acumula las repeticiones del mismo libro en lugar de
    rechazarlas: order_lines tiene UNIQUE (order_id, book_id), de modo
    que pedir dos veces el mismo libro significa querer mas unidades.
    """
    raw = data.get("lines") or data.get("lineas") or data.get("items")
    if raw is None:
        raise ValidationError(
            "Falta la lista de lineas.",
            ['Envie {"lines": [{"bookId": 3, "quantity": 2}]}.'])
    if isinstance(raw, dict):
        raw = [{"bookId": k, "quantity": v} for k, v in raw.items()]
    if not isinstance(raw, (list, tuple)) or not raw:
        raise ValidationError("El pedido debe tener al menos una linea.")
    if len(raw) > MAX_LINEAS:
        raise ValidationError(f"Un pedido admite como maximo {MAX_LINEAS} lineas.")

    acumulado = {}
    errores = []
    for indice, item in enumerate(raw, start=1):
        if not isinstance(item, dict):
            errores.append(f"La linea {indice} debe ser un objeto con bookId y quantity.")
            continue
        try:
            book_id = int(item.get("bookId") or item.get("book_id") or item.get("libro"))
        except (TypeError, ValueError):
            errores.append(f"La linea {indice} no trae un bookId valido.")
            continue
        try:
            cantidad = int(item.get("quantity") or item.get("cantidad") or 0)
        except (TypeError, ValueError):
            errores.append(f"La linea {indice} no trae una quantity valida.")
            continue
        if cantidad <= 0:
            errores.append(f"La linea {indice} (libro {book_id}) debe pedir al "
                           "menos una unidad.")
            continue
        if cantidad > MAX_UNIDADES:
            errores.append(f"La linea {indice} (libro {book_id}) pide {cantidad} "
                           f"unidades; el maximo por libro es {MAX_UNIDADES}.")
            continue
        acumulado[book_id] = acumulado.get(book_id, 0) + cantidad

    if errores:
        raise ValidationError("Hay lineas invalidas.", errores)
    return [{"bookId": b, "quantity": q} for b, q in sorted(acumulado.items())]


# =====================================================================
# Autorizacion
# =====================================================================
def _require_owner_or(permission, user_id):
    """Deja pasar si el recurso es del propio usuario, o si tiene el permiso."""
    identity = current_identity()
    if identity is None:
        raise Unauthorized("Se requiere un token valido.")
    if identity.is_self(user_id) or identity.has(permission):
        return identity
    metrics.incr("authz.denied")
    raise Forbidden(
        "Ese pedido no es suyo.",
        [f"Para operar sobre pedidos ajenos hace falta el permiso '{permission}'.",
         f"Rol actual: {identity.role or identity.role_id}."])


def _order_or_404(order_id):
    row = repo.get_order(order_id)
    if row is None:
        raise NotFound(f"No existe el pedido {order_id}.")
    return row


# =====================================================================
# Rutas: servicio
# =====================================================================
@app.get("/")
def index():
    payload = {
        "service": config.SERVICE_NAME,
        "description": "Microservicio Flask de pedidos, lineas, reserva de "
                       "stock y estados de library_db (esquema library).",
        "version": config.XML_VERSION,
        "formats": ["application/xml", "application/json"],
        "defaultFormat": config.DEFAULT_FORMAT,
        "xmlNamespace": config.XML_NAMESPACE,
        "documentation": {"swaggerUi": "/docs", "openapi": "/openapi.json"},
        "stock": {
            "source": "library.books.stock",
            "note": "No hay inventario paralelo: se reserva al crear el pedido "
                    "y se devuelve al cancelarlo, en la misma transaccion que "
                    "las lineas.",
        },
        "publicEndpoints": [f"{API}/envios/<numero>"],
        "statuses": list(repo.ESTADOS),
        "transitions": {
            "pendiente": ["pagado", "cancelado"],
            "pagado": ["enviado", "cancelado"],
            "enviado": ["entregado"],
            "entregado": [], "cancelado": [],
        },
        "endpoints": [
            {"method": "GET", "path": f"{API}/envios/<numero>",
             "description": "RASTREO PUBLICO: solo el estatus de envio"},
            {"method": "POST", "path": f"{API}/pedidos", "description": "Crear pedido (token)"},
            {"method": "GET", "path": f"{API}/pedidos", "description": "Listar (propios; ajenos con orders:read)"},
            {"method": "GET", "path": f"{API}/pedidos/<id>", "description": "Un pedido (propio, o orders:read)"},
            {"method": "GET", "path": f"{API}/pedidos/numero/<numero>", "description": "Un pedido por su numero"},
            {"method": "GET", "path": f"{API}/pedidos/<id>/historial", "description": "Bitacora de estados"},
            {"method": "PATCH", "path": f"{API}/pedidos/<id>/lineas", "description": "Ajustar cantidades (solo pendiente)"},
            {"method": "DELETE", "path": f"{API}/pedidos/<id>", "description": "Cancelar y devolver stock"},
            {"method": "PUT", "path": f"{API}/pedidos/<id>/estado", "description": "Mover el estado (orders:status)"},
            {"method": "GET", "path": "/health", "description": "Estado del servicio, PostgreSQL y Redis"},
            {"method": "GET", "path": "/metrics", "description": "Contadores del proceso y Redis"},
        ],
    }
    return negotiator.dict_response("service", payload)


@app.get("/health")
def health():
    warnings = config.warnings()
    redis_block = store.health()
    redis_ok = redis_block.get("status") == "ok"
    if not redis_ok and config.redis_configured():
        warnings.append("Redis no responde: el rastreo publico sigue (sin "
                        "cache), pero toda operacion con token devolvera 503 "
                        "porque no se puede comprobar la revocacion.")
    db_ok, db_block = database.health()
    payload = dict(db_block)
    payload["status"] = "ok" if (db_ok and redis_ok) else ("error" if not db_ok
                                                           else "degraded")
    payload["jwt"] = "ok" if config.jwt_configured() else "missing_secret"
    payload["redis"] = redis_block
    if warnings:
        payload["warnings"] = warnings
    return negotiator.dict_response("health", payload, status=200 if db_ok else 503)


@app.get("/metrics")
def service_metrics():
    return negotiator.dict_response(
        "metrics", metrics_payload(config.SERVICE_NAME, store))


# =====================================================================
# RASTREO PUBLICO  (lo unico sin token)
# =====================================================================
@app.get(f"{API}/envios/<path:order_number>")
def track_shipment(order_number):
    """
    Estatus de envio de un pedido. SIN TOKEN, a proposito.

    Existe para que un tercero —la paqueteria— pueda manejar su logistica
    sin tener una cuenta en el sistema. Por eso devuelve EXCLUSIVAMENTE
    el estado del envio y sus fechas: ni dueno, ni correo, ni importes,
    ni que libros se compraron. Lo construye tracking_to_dict campo por
    campo, de modo que anadir una columna a la vista no la publica sola.

    El numero de pedido (PED-000123) hace de identificador: es
    secuencial, asi que conviene tratarlo como un dato que se comparte
    con quien transporta el paquete, no como un secreto.
    """
    numero = (order_number or "").strip().upper()
    if not numero:
        raise ValidationError("Falta el numero de pedido.")

    def producer():
        row = repo.tracking_of(numero)
        if row is None:
            raise NotFound(f"No hay ningun pedido con el numero {numero}.")
        metrics.incr("tracking.served")
        return negotiator.dict_response("shipment", repo.tracking_to_dict(row))

    return order_cache.cached(
        order_cache.tracking_key(numero, negotiator.wants_xml()),
        config.CACHE_TTL, producer)


# =====================================================================
# Rutas: pedidos
# =====================================================================
@app.post(f"{API}/pedidos")
@token_required
def create_order():
    """
    Crea un pedido reservando stock.

    El dueno es SIEMPRE el del token, salvo que quien llame tenga
    orders:write y mande un userId distinto (alta en mostrador). Un
    cliente no puede crear pedidos a nombre de otro.

    Los precios NO vienen del cliente: sp_crear_pedido los congela desde
    library.books. La reserva de stock es atomica; si no alcanza, el
    procedimiento revienta con un mensaje que dice de que libro se trata
    y la peticion entera se revierte.

    Un CERROJO en Redis por usuario evita el pedido doble cuando el
    cliente reintenta por un tiempo de espera agotado.
    """
    identity = current_identity()
    data = read_payload()
    lines = _read_lines(data)

    user_id = identity.user_id
    solicitado = _pick(data, "userId", "user_id", default=None)
    if solicitado not in (None, ""):
        try:
            solicitado = int(solicitado)
        except (TypeError, ValueError):
            raise ValidationError("userId debe ser un entero.")
        if solicitado != identity.user_id and not identity.has("orders:write"):
            raise Forbidden(
                "No puede crear pedidos a nombre de otro usuario.",
                ["Hace falta el permiso 'orders:write'."])
        user_id = solicitado

    cuenta = repo.user_is_active(user_id)
    if cuenta is None:
        raise ValidationError(f"El usuario {user_id} no existe.")
    if not cuenta.get("is_active", True):
        raise Conflict("La cuenta esta desactivada y no puede hacer pedidos.")

    # Aviso temprano y legible: la base volveria a comprobarlo de todas
    # formas (ahi esta la verdad), pero un 400 que dice "faltan 2 de
    # Clean Code" es mas util que esperar al error del procedimiento.
    disponibles = repo.books_availability([l["bookId"] for l in lines])
    problemas = []
    for linea in lines:
        libro = disponibles.get(linea["bookId"])
        if libro is None:
            problemas.append(f"El libro {linea['bookId']} no existe.")
        elif libro["stock"] < linea["quantity"]:
            problemas.append(
                f"Stock insuficiente de \"{libro['title']}\" (ISBN {libro['isbn']}): "
                f"hay {libro['stock']}, se piden {linea['quantity']}.")
    if problemas:
        raise Conflict("El pedido no se puede surtir.", problemas)

    notas = str(_pick(data, "notes", "notas", default="") or "")[:500] or None
    direccion = str(_pick(data, "shippingAddress", "direccion", default="") or "")[:500] or None
    try:
        envio = float(_pick(data, "shippingCost", "costoEnvio", default=0) or 0)
    except (TypeError, ValueError):
        raise ValidationError("shippingCost debe ser un numero.")
    if envio < 0:
        raise ValidationError("shippingCost no puede ser negativo.")

    # Cerrojo de 10 s por usuario: dos POST identicos seguidos (el cliente
    # reintenta tras un tiempo de espera) no crean dos pedidos.
    with store.lock(f"pedido:crear:{user_id}", ttl_seconds=10) as tomado:
        if not tomado:
            raise Conflict(
                "Ya hay un pedido en curso para esta cuenta.",
                ["Espere unos segundos y vuelva a intentarlo.",
                 "Si el anterior se creo, aparecera en GET /pedidos."])
        try:
            order_id = repo.create_order(user_id, lines, notes=notas,
                                         shipping_cost=envio,
                                         shipping_address=direccion)
        except Exception as exc:                       # noqa: BLE001
            mensaje = raised_message(exc)
            if "stock" in mensaje.lower() or "no existe" in mensaje.lower():
                raise Conflict("El pedido no se pudo crear.", [mensaje]) from exc
            raise

    # El stock cambio: el catalogo cacheado anunciaria unidades que ya no
    # estan disponibles.
    order_cache.invalidate_stock(f"POST /pedidos id={order_id}")
    metrics.incr("orders.created")
    log.info("Pedido %s creado para user_id=%s (%s lineas) por user_id=%s",
             order_id, user_id, len(lines), identity.user_id)

    row = repo.get_order(order_id)
    payload = repo.order_to_dict(
        row, lines=[repo.line_to_dict(l) for l in repo.lines_of(order_id)])
    return negotiator.dict_response(
        "order", payload, status=201,
        headers={"Location": f"{API}/pedidos/{order_id}"})


@app.get(f"{API}/pedidos")
@token_required
def list_orders():
    """
    Lista pedidos.

    Por omision, SOLO los del usuario del token. Quien tenga orders:read
    puede pedir los de todos con ?all=true, o los de una cuenta concreta
    con ?userId=.
    """
    identity = current_identity()
    limit, offset = _pagination()
    filters = {}

    pide_todos = (request.args.get("all") or "").strip().lower() in ("1", "true", "si", "yes")
    pedido_user = request.args.get("userId")
    if pide_todos or pedido_user:
        if not identity.has("orders:read"):
            raise Forbidden(
                "Solo puede listar sus propios pedidos.",
                ["Para ver los de otros hace falta el permiso 'orders:read'."])
        if pedido_user:
            try:
                filters["user_id"] = int(pedido_user)
            except (TypeError, ValueError):
                raise ValidationError("userId debe ser un entero.")
    else:
        filters["user_id"] = identity.user_id

    estado = (request.args.get("status") or "").strip().lower()
    if estado:
        if estado not in repo.ESTADOS:
            raise ValidationError(
                f"Estado desconocido: '{estado}'.",
                [f"Estados validos: {', '.join(repo.ESTADOS)}."])
        filters["status"] = estado
    for name, key in (("number", "number"), ("from", "from"), ("to", "to")):
        if request.args.get(name):
            filters[key] = request.args[name].strip()

    rows, total = repo.list_orders(filters, sort=request.args.get("sort", "placed"),
                                   order=request.args.get("order", "desc"),
                                   limit=limit, offset=offset)
    pedidos = [repo.order_to_dict(row) for row in rows]
    payload = {"count": len(pedidos), "total": total, "limit": limit,
               "offset": offset, "filters": filters, "orders": pedidos}
    return negotiator.collection_response(
        "orders", "order", pedidos, payload, total=total, limit=limit,
        offset=offset, headers={"X-Total-Count": str(total)})


@app.get(f"{API}/pedidos/<int:order_id>")
@token_required
def get_order(order_id):
    """Un pedido con sus lineas. El propio siempre; los ajenos con orders:read."""
    row = _order_or_404(order_id)
    _require_owner_or("orders:read", row["user_id"])
    payload = repo.order_to_dict(
        row, lines=[repo.line_to_dict(l) for l in repo.lines_of(order_id)])
    return negotiator.dict_response("order", payload)


@app.get(f"{API}/pedidos/numero/<path:order_number>")
@token_required
def get_order_by_number(order_number):
    """
    El pedido COMPLETO por su numero. Exige token y ser el dueno (o
    orders:read). Para el estatus de envio sin token esta
    GET /envios/<numero>.
    """
    row = repo.get_order_by_number((order_number or "").strip().upper())
    if row is None:
        raise NotFound(f"No existe el pedido {order_number}.")
    _require_owner_or("orders:read", row["user_id"])
    payload = repo.order_to_dict(
        row, lines=[repo.line_to_dict(l) for l in repo.lines_of(row["id"])])
    return negotiator.dict_response("order", payload)


@app.get(f"{API}/pedidos/<int:order_id>/historial")
@token_required
def get_order_history(order_id):
    """Bitacora de cambios de estado: quien, cuando y de que a que."""
    row = _order_or_404(order_id)
    _require_owner_or("orders:read", row["user_id"])
    historial = [repo.history_to_dict(h) for h in repo.history_of(order_id)]
    payload = {"orderId": order_id, "orderNumber": row["order_number"],
               "status": row["status"], "count": len(historial),
               "history": historial}
    return negotiator.collection_response("history", "entry", historial, payload,
                                          total=len(historial))


@app.patch(f"{API}/pedidos/<int:order_id>/lineas")
@token_required
def adjust_lines(order_id):
    """
    Ajusta las cantidades de un pedido PENDIENTE.

    quantity = 0 quita la linea. El stock se ajusta por la DIFERENCIA, de
    modo que subir de 2 a 3 reserva una unidad mas y bajar de 3 a 1
    devuelve dos. Solo se admite mientras el pedido siga pendiente: una
    vez pagado, cambiar lo que se compro descuadraria el cobro.
    """
    row = _order_or_404(order_id)
    _require_owner_or("orders:write", row["user_id"])
    if row["status"] != "pendiente":
        raise Conflict(
            f"El pedido esta en estado '{row['status']}' y ya no se puede modificar.",
            ["Solo un pedido pendiente admite cambios de lineas.",
             "Cancelelo si ya no lo quiere."])

    data = read_payload()
    raw = data.get("lines") or data.get("lineas")
    if raw is None:
        raise ValidationError(
            "Falta la lista de lineas.",
            ['Envie {"lines": [{"bookId": 3, "quantity": 0}]} '
             "(quantity 0 quita la linea)."])
    if isinstance(raw, dict):
        raw = [{"bookId": k, "quantity": v} for k, v in raw.items()]
    if not isinstance(raw, (list, tuple)) or not raw:
        raise ValidationError("Envie al menos una linea que ajustar.")

    ajustes = []
    errores = []
    for indice, item in enumerate(raw, start=1):
        if not isinstance(item, dict):
            errores.append(f"La linea {indice} debe ser un objeto.")
            continue
        try:
            book_id = int(item.get("bookId") or item.get("book_id"))
            cantidad = int(item.get("quantity", item.get("cantidad")))
        except (TypeError, ValueError):
            errores.append(f"La linea {indice} necesita bookId y quantity enteros.")
            continue
        if cantidad < 0:
            errores.append(f"La linea {indice} no puede pedir una cantidad negativa.")
            continue
        if cantidad > MAX_UNIDADES:
            errores.append(f"La linea {indice} supera el maximo de "
                           f"{MAX_UNIDADES} unidades por libro.")
            continue
        ajustes.append((book_id, cantidad))
    if errores:
        raise ValidationError("Hay ajustes invalidos.", errores)

    for book_id, cantidad in ajustes:
        try:
            repo.adjust_line(order_id, book_id, cantidad)
        except Exception as exc:                       # noqa: BLE001
            mensaje = raised_message(exc)
            if "stock" in mensaje.lower() or "no existe" in mensaje.lower() \
                    or "pendiente" in mensaje.lower():
                raise Conflict("No se pudo ajustar el pedido.", [mensaje]) from exc
            raise

    lineas = repo.lines_of(order_id)
    if not lineas:
        # Un pedido sin lineas no es un pedido: se cancela, lo que ademas
        # devuelve cualquier stock que siguiera reservado.
        repo.cancel_order(order_id, current_identity().user_id,
                          "quedo sin lineas al ajustarlo")
        order_cache.invalidate_stock(f"PATCH /pedidos/{order_id}/lineas (vacio)")
        row = repo.get_order(order_id)
        payload = repo.order_to_dict(row, lines=[])
        payload["note"] = ("El pedido quedo sin lineas, de modo que se cancelo "
                           "y se devolvio el stock.")
        return negotiator.dict_response("order", payload)

    order_cache.invalidate_stock(f"PATCH /pedidos/{order_id}/lineas")
    metrics.incr("orders.lines.adjusted")
    row = repo.get_order(order_id)
    payload = repo.order_to_dict(row, lines=[repo.line_to_dict(l) for l in lineas])
    return negotiator.dict_response("order", payload)


@app.delete(f"{API}/pedidos/<int:order_id>")
@token_required
def cancel_order(order_id):
    """
    Cancela el pedido DEVOLVIENDO el stock reservado.

    El dueno puede cancelar mientras siga pendiente. Cancelar uno ya
    pagado (hay dinero de por medio) exige orders:write. Un pedido
    enviado o entregado ya no se cancela: eso es una devolucion, que es
    otra cosa y no esta en el alcance de esta entrega.
    """
    row = _order_or_404(order_id)
    identity = current_identity()

    if row["status"] in ("enviado", "entregado"):
        raise Conflict(
            f"Un pedido '{row['status']}' ya no se puede cancelar.",
            ["Eso seria una devolucion, que este servicio no gestiona."])
    if row["status"] == "cancelado":
        payload = repo.order_to_dict(row)
        payload["alreadyCancelled"] = True
        return negotiator.dict_response("order", payload)

    if row["status"] == "pagado":
        if not identity.has("orders:write"):
            raise Forbidden(
                "Un pedido ya pagado solo lo puede cancelar el personal.",
                ["Hace falta el permiso 'orders:write'.",
                 "Hay un pago aplicado que habria que reembolsar."])
    else:
        _require_owner_or("orders:write", row["user_id"])

    motivo = str(_pick(read_payload(), "reason", "motivo",
                       default="cancelado por el usuario"))[:300]
    try:
        repo.cancel_order(order_id, identity.user_id, motivo)
    except Exception as exc:                           # noqa: BLE001
        mensaje = raised_message(exc)
        if "cancelar" in mensaje.lower() or "no existe" in mensaje.lower():
            raise Conflict("No se pudo cancelar.", [mensaje]) from exc
        raise

    order_cache.invalidate_stock(f"DELETE /pedidos/{order_id}")
    metrics.incr("orders.cancelled")
    log.info("Pedido %s cancelado por user_id=%s", order_id, identity.user_id)
    actualizado = repo.get_order(order_id)
    payload = repo.order_to_dict(actualizado)
    payload["cancelled"] = True
    payload["stockReturned"] = True
    return negotiator.dict_response("order", payload)


@app.put(f"{API}/pedidos/<int:order_id>/estado")
@permission_required("orders:status")
def change_status(order_id):
    """
    Mueve el estado del pedido.

    Las transiciones validas las impone un DISPARADOR de la base, no esta
    funcion: pendiente -> pagado|cancelado, pagado -> enviado|cancelado,
    enviado -> entregado. Asi la regla se cumple aunque el estado se
    cambie desde otro sitio.

    El paso a 'pagado' normalmente NO se hace aqui: lo dispara el
    microservicio de pagos cuando lo aplicado alcanza el total. Se deja
    disponible para corregir a mano un caso excepcional.

    Al marcar 'enviado' conviene mandar carrier y trackingCode: es lo que
    despues lee la paqueteria en GET /envios/<numero>.
    """
    row = _order_or_404(order_id)
    data = read_payload()
    destino = str(_pick(data, "status", "estado")).strip().lower()
    if not destino:
        raise ValidationError(
            "Falta el estado destino.",
            [f"Estados validos: {', '.join(repo.ESTADOS)}."])
    if destino not in repo.ESTADOS:
        raise ValidationError(
            f"Estado desconocido: '{destino}'.",
            [f"Estados validos: {', '.join(repo.ESTADOS)}."])
    if destino == row["status"]:
        payload = repo.order_to_dict(row)
        payload["unchanged"] = True
        return negotiator.dict_response("order", payload)

    carrier = str(_pick(data, "carrier", "paqueteria", default="") or "")[:60] or None
    guia = str(_pick(data, "trackingCode", "guia", default="") or "")[:60] or None
    nota = str(_pick(data, "note", "nota", default="") or "")[:300] or None

    try:
        repo.change_status(order_id, destino, current_identity().user_id,
                           nota, carrier, guia)
    except Exception as exc:                           # noqa: BLE001
        mensaje = raised_message(exc)
        if "transicion" in mensaje.lower() or "cancelar" in mensaje.lower() \
                or "no existe" in mensaje.lower():
            raise Conflict(
                "Transicion de estado no permitida.",
                [mensaje,
                 "pendiente -> pagado|cancelado · pagado -> enviado|cancelado "
                 "· enviado -> entregado."]) from exc
        raise

    # Cancelar devuelve stock; el resto de transiciones no lo tocan.
    if destino == "cancelado":
        order_cache.invalidate_stock(f"PUT /pedidos/{order_id}/estado")
    else:
        order_cache.invalidate_tracking(f"PUT /pedidos/{order_id}/estado")
    metrics.incr(f"orders.status.{destino}")
    log.info("Pedido %s: %s -> %s por user_id=%s", order_id, row["status"],
             destino, current_identity().user_id)

    actualizado = repo.get_order(order_id)
    payload = repo.order_to_dict(actualizado)
    payload["previousStatus"] = row["status"]
    if destino == "enviado" and not guia:
        payload["warning"] = ("No se registro codigo de guia: el rastreo "
                              "publico no podra darselo a la paqueteria.")
    return negotiator.dict_response("order", payload)


# =====================================================================
# Manejo de errores
# =====================================================================
register_error_handlers(app, negotiator, debug=config.DEBUG, service="pedidos")


@app.errorhandler(HTTPException)
def handle_http_error(exc):
    code = {400: "bad_request", 404: "not_found", 405: "method_not_allowed",
            415: "unsupported_media_type"}.get(exc.code, "http_error")
    return negotiator.error_response(exc.code, code, exc.description or exc.name)


if __name__ == "__main__":
    from library_common.env import redacted

    log.info("Pedidos -> http://%s:%s%s/pedidos", config.HOST, config.PORT, API)
    log.info("Rastreo publico -> http://%s:%s%s/envios/<numero>",
             config.HOST, config.PORT, API)
    log.info("Swagger UI -> http://%s:%s/docs", config.HOST, config.PORT)
    log.info("PostgreSQL -> %s (esquema %s)", database.target, config.PGSCHEMA)
    log.info("Redis -> %s", redacted(config.REDIS_URL) or "SIN CONFIGURAR")
    log.info("CORS origins -> %s", ", ".join(config.CORS_ORIGINS))
    for item in config.warnings():
        log.warning(item)
    app.run(host=config.HOST, port=config.PORT, debug=config.DEBUG, load_dotenv=False)
