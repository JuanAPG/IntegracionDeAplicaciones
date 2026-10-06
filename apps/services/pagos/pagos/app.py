"""
apps/services/pagos/pagos/app.py
Microservicio Flask de PAGOS: registra pagos y actualiza el estado de los
pedidos (library_db / esquema library).

Restricciones de la practica
  * Flask SIN blueprints; Psycopg 3; credenciales solo por entorno.
  * XML y JSON (?format= / ?output= / Accept). Sin parametro, XML.
  * CORS enumerando los origenes de las aplicaciones cliente.

AQUI NO HAY NINGUNA LECTURA PUBLICA
  Un pago es informacion financiera de una persona concreta. La unica
  cosa que este par de servicios publica sin token es el ESTATUS DE
  ENVIO, y vive en el microservicio de pedidos
  (GET /envios/<numero>), porque es lo que necesita un tercero para
  manejar su logistica. Todo lo de aqui, incluido el catalogo de metodos
  de pago, exige Authorization: Bearer <JWT>.

AUTORIZACION
  * Un cliente puede pagar SUS pedidos y ver SUS pagos con solo tener un
    token valido.
  * Lo demas exige permisos:
        payments:read   ver pagos ajenos
        payments:write  aplicar, rechazar y reembolsar; cobrar en nombre
                        de otro
  * 401 token ausente/invalido/caducado/revocado · 403 rol insuficiente
    · 503 Redis o PostgreSQL caidos.

QUE NO SE GUARDA
  Ni numero de tarjeta, ni CVV, ni vencimiento, ni titular. Solo la
  referencia de la pasarela y, como mucho, los cuatro ultimos digitos que
  ella misma publica. Lo que no se guarda no se puede filtrar.

CONTRA EL COBRO DOBLE
  Dos defensas que se complementan:
    1. idempotencyKey: dos intentos con la misma clave son el MISMO pago.
       Es lo que salva un reintento del cliente tras un tiempo de espera.
    2. Un CERROJO en Redis por pedido mientras se registra, para que dos
       peticiones simultaneas no pasen a la vez por la comprobacion de
       saldo.
"""
import logging

from flasgger import Swagger
from flask import Flask, request
from werkzeug.exceptions import HTTPException

from . import _bootstrap  # noqa: F401
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
    logging.DEBUG if config.DEBUG else logging.INFO, service="pagos")

app = Flask(__name__)
app.json.sort_keys = False
API = config.API_PREFIX

configure_cors(app, config.CORS_ORIGINS, with_credentials=False,
               max_age=config.CORS_MAX_AGE, service="pagos")
install_security_headers(app)
register_request_metrics(app, "pagos")

SWAGGER_CONFIG = {
    "openapi": "3.0.3", "uiversion": 3, "headers": [],
    "title": "Libreria en Linea — Microservicio de pagos",
    "specs": [{"endpoint": "openapi", "route": "/openapi.json",
               "rule_filter": lambda rule: False,
               "model_filter": lambda tag: True}],
    "static_url_path": "/docs/static", "swagger_ui": True,
    "specs_route": "/docs/",
}
swagger = Swagger(app, template=openapi.build_spec(), config=SWAGGER_CONFIG, merge=False)

MAX_IMPORTE = 1_000_000


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
    return {_local(h.tag): (h.text or "").strip() for h in root}


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


def _amount(data):
    raw = _pick(data, "amount", "importe", "monto", default=None)
    if raw in (None, ""):
        raise ValidationError("Falta el importe del pago (amount).")
    try:
        amount = round(float(raw), 2)
    except (TypeError, ValueError):
        raise ValidationError("El importe debe ser un numero.")
    if amount <= 0:
        raise ValidationError("El importe debe ser mayor que cero.")
    if amount > MAX_IMPORTE:
        raise ValidationError(f"El importe supera el maximo admitido "
                              f"({MAX_IMPORTE:,.2f}).")
    return amount


def _resolve_method(data):
    """Acepta methodId numerico o method por nombre."""
    raw_id = _pick(data, "methodId", "method_id", default=None)
    raw_name = _pick(data, "method", "metodo", default=None)
    if raw_id not in (None, ""):
        try:
            method_id = int(raw_id)
        except (TypeError, ValueError):
            raise ValidationError("methodId debe ser un entero.")
        metodo = repo.get_method(method_id)
    elif raw_name not in (None, ""):
        metodo = repo.get_method_by_name(str(raw_name))
    else:
        raise ValidationError(
            "Falta el metodo de pago.",
            ["Envie methodId o method. Consulte GET /metodos."])
    if metodo is None:
        raise ValidationError(
            f"El metodo de pago '{raw_id or raw_name}' no existe.",
            ["Consulte GET /metodos."])
    if not metodo.get("is_active", True):
        raise Conflict(f"El metodo de pago '{metodo['name']}' esta desactivado.")
    return metodo


def _card_last4(data):
    """
    Solo los cuatro ultimos digitos, si vienen. Cualquier intento de
    mandar un numero de tarjeta completo se RECHAZA: este servicio no
    guarda instrumentos de pago y no va a empezar por accidente.
    """
    raw = str(_pick(data, "cardLast4", "card_last4", default="") or "").strip()
    if not raw:
        return None
    if not raw.isdigit():
        raise ValidationError("cardLast4 solo admite digitos.")
    if len(raw) != 4:
        raise ValidationError(
            "cardLast4 debe tener exactamente 4 digitos.",
            ["Este servicio NO almacena numeros de tarjeta: solo los cuatro "
             "ultimos digitos que publica la pasarela."])
    return raw


def _reject_card_data(data):
    """Rechaza de plano cualquier campo que parezca un instrumento de pago."""
    prohibidos = [k for k in data
                  if str(k).lower() in ("cardnumber", "card_number", "pan",
                                        "cvv", "cvc", "securitycode",
                                        "expiry", "expirationdate", "cardholder",
                                        "numerotarjeta", "titular")]
    if prohibidos:
        raise ValidationError(
            "Este servicio no acepta datos de tarjeta.",
            [f"Campos rechazados: {', '.join(sorted(prohibidos))}.",
             "El cobro lo hace la pasarela; aqui solo se registra su "
             "referencia (authorizationCode) y, si acaso, cardLast4."])


# =====================================================================
# Autorizacion
# =====================================================================
def _require_owner_or(permission, user_id):
    identity = current_identity()
    if identity is None:
        raise Unauthorized("Se requiere un token valido.")
    if identity.is_self(user_id) or identity.has(permission):
        return identity
    metrics.incr("authz.denied")
    raise Forbidden(
        "Ese pago no es suyo.",
        [f"Para operar sobre pagos ajenos hace falta el permiso '{permission}'.",
         f"Rol actual: {identity.role or identity.role_id}."])


def _payment_or_404(payment_id):
    row = repo.get_payment(payment_id)
    if row is None:
        raise NotFound(f"No existe el pago {payment_id}.")
    return row


# =====================================================================
# Rutas: servicio
# =====================================================================
@app.get("/")
def index():
    payload = {
        "service": config.SERVICE_NAME,
        "description": "Microservicio Flask de pagos: registra el cobro y "
                       "actualiza el estado del pedido (library_db, esquema "
                       "library).",
        "version": config.XML_VERSION,
        "formats": ["application/xml", "application/json"],
        "defaultFormat": config.DEFAULT_FORMAT,
        "xmlNamespace": config.XML_NAMESPACE,
        "documentation": {"swaggerUi": "/docs", "openapi": "/openapi.json"},
        "authentication": {
            "scheme": "Bearer",
            "issuer": config.JWT_ISSUER,
            "note": "NINGUNA lectura de este servicio es publica: un pago es "
                    "informacion financiera. Lo unico publico del par "
                    "pedidos/pagos es el estatus de envio, y vive en el "
                    "microservicio de pedidos (GET /envios/<numero>).",
        },
        "neverStored": ["numero de tarjeta", "CVV", "fecha de vencimiento",
                        "titular"],
        "statuses": list(repo.ESTADOS),
        "transitions": {
            "pendiente": ["autorizado", "aplicado", "rechazado"],
            "autorizado": ["aplicado", "rechazado"],
            "aplicado": ["reembolsado"],
            "rechazado": [], "reembolsado": [],
        },
        "endpoints": [
            {"method": "GET", "path": f"{API}/metodos", "description": "Metodos de pago (token)"},
            {"method": "POST", "path": f"{API}/pagos", "description": "Registrar un pago"},
            {"method": "GET", "path": f"{API}/pagos", "description": "Listar (propios; ajenos con payments:read)"},
            {"method": "GET", "path": f"{API}/pagos/<id>", "description": "Un pago"},
            {"method": "GET", "path": f"{API}/pagos/referencia/<ref>", "description": "Un pago por su referencia"},
            {"method": "POST", "path": f"{API}/pagos/<id>/aplicar", "description": "Aplicar (payments:write)"},
            {"method": "POST", "path": f"{API}/pagos/<id>/rechazar", "description": "Rechazar (payments:write)"},
            {"method": "POST", "path": f"{API}/pagos/<id>/reembolsar", "description": "Reembolsar (payments:write)"},
            {"method": "GET", "path": f"{API}/pedidos/<id>/saldo", "description": "Saldo del pedido"},
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
    db_ok, db_block = database.health()
    payload = dict(db_block)
    payload["jwt"] = "ok" if config.jwt_configured() else "missing_secret"
    payload["redis"] = redis_block
    if db_ok and redis_ok:
        payload["status"] = "ok"
        status = 200
    else:
        payload["status"] = "error" if not db_ok else "degraded"
        # Sin Redis este servicio no puede comprobar la revocacion y no
        # tiene ningun endpoint publico: no puede hacer nada util.
        status = 503
        if not redis_ok and config.redis_configured():
            warnings.append("Redis no responde: no se puede comprobar la "
                            "revocacion de tokens, de modo que el servicio "
                            "rechazara toda peticion (fallo seguro).")
    if warnings:
        payload["warnings"] = warnings
    return negotiator.dict_response("health", payload, status=status)


@app.get("/metrics")
def service_metrics():
    return negotiator.dict_response(
        "metrics", metrics_payload(config.SERVICE_NAME, store))


# =====================================================================
# Rutas: metodos de pago
# =====================================================================
@app.get(f"{API}/metodos")
@token_required
def list_methods():
    """
    Catalogo de metodos de pago.

    Exige token aunque no tenga datos personales: en este servicio no hay
    ninguna puerta publica, y quien va a pagar ya esta autenticado de
    todas formas.
    """
    incluir_inactivos = (request.args.get("all") or "").strip().lower() in (
        "1", "true", "si", "yes")
    filas = repo.list_methods(only_active=not incluir_inactivos)
    metodos = [repo.method_to_dict(f) for f in filas]
    payload = {"count": len(metodos), "methods": metodos}
    return negotiator.collection_response("methods", "method", metodos, payload,
                                          total=len(metodos))


# =====================================================================
# Rutas: pagos
# =====================================================================
@app.post(f"{API}/pagos")
@token_required
def register_payment():
    """
    Registra un pago contra un pedido.

    Un cliente puede pagar SUS pedidos; cobrar el de otro exige
    payments:write. El importe no puede exceder el saldo pendiente: eso
    lo comprueba sp_registrar_pago contra lo ya aplicado, autorizado y
    pendiente.

    Un metodo que no requiere autorizacion (efectivo) nace directamente
    'aplicado', y si con eso se cubre el total, el DISPARADOR de la base
    pasa el pedido a 'pagado'. Los demas nacen 'pendiente', o
    'autorizado' si se manda el codigo de la pasarela.

    Contra el cobro doble: idempotencyKey (mismo pago, no dos) y un
    cerrojo en Redis por pedido mientras se registra.
    """
    identity = current_identity()
    data = read_payload()
    _reject_card_data(data)

    # El pedido se puede indicar por id o por numero (PED-000123).
    order_id = _pick(data, "orderId", "order_id", default=None)
    order_number = _pick(data, "orderNumber", "numeroPedido", default=None)
    if order_id not in (None, ""):
        try:
            pedido = repo.order_owner(int(order_id))
        except (TypeError, ValueError):
            raise ValidationError("orderId debe ser un entero.")
    elif order_number not in (None, ""):
        pedido = repo.order_by_number(str(order_number).strip().upper())
    else:
        raise ValidationError("Falta el pedido.",
                              ["Envie orderId o orderNumber."])
    if pedido is None:
        raise NotFound("No existe ese pedido.")

    _require_owner_or("payments:write", pedido["user_id"])

    if pedido["status"] == "cancelado":
        raise Conflict("No se puede pagar un pedido cancelado.")

    amount = _amount(data)
    metodo = _resolve_method(data)
    clave = str(_pick(data, "idempotencyKey", "idempotency_key",
                      default="") or "")[:80] or None
    codigo = str(_pick(data, "authorizationCode", "authorization_code",
                       default="") or "")[:60] or None
    last4 = _card_last4(data)
    notas = str(_pick(data, "notes", "notas", default="") or "")[:300] or None

    # Si la clave ya se uso, es el MISMO pago: se devuelve el que estaba.
    if clave:
        previo = repo.get_by_idempotency_key(clave)
        if previo is not None:
            metrics.incr("payments.idempotent_hit")
            payload = repo.payment_to_dict(previo)
            payload["idempotentReplay"] = True
            payload["note"] = ("Ya existia un pago con esa idempotencyKey: se "
                               "devuelve el original en lugar de cobrar dos veces.")
            return negotiator.dict_response("payment", payload)

    # Cerrojo por PEDIDO: dos peticiones simultaneas no pueden pasar a la
    # vez por la comprobacion de saldo de sp_registrar_pago.
    with store.lock(f"pago:pedido:{pedido['id']}", ttl_seconds=10) as tomado:
        if not tomado:
            raise Conflict(
                "Ya hay un pago en curso para este pedido.",
                ["Espere unos segundos y consulte GET /pagos?orderId=... "
                 "antes de volver a intentarlo."])
        try:
            payment_id = repo.register_payment(
                pedido["id"], metodo["id"], amount,
                registered_by=identity.user_id, idempotency_key=clave,
                authorization_code=codigo, card_last4=last4, notes=notas)
        except Exception as exc:                       # noqa: BLE001
            mensaje = raised_message(exc)
            bajo = mensaje.lower()
            if any(p in bajo for p in ("excede", "cancelado", "desactivado",
                                       "no existe", "importe")):
                raise Conflict("El pago no se pudo registrar.", [mensaje]) from exc
            raise

    metrics.incr("payments.registered")
    # Se registra el hecho, NUNCA el importe junto a datos de la persona
    # ni ningun dato de tarjeta.
    log.info("Pago %s registrado para el pedido %s por user_id=%s",
             payment_id, pedido["id"], identity.user_id)

    fila = repo.get_payment(payment_id)
    payload = repo.payment_to_dict(fila)
    payload["balance"] = repo.balance_to_dict(repo.order_balance(pedido["id"]))
    return negotiator.dict_response(
        "payment", payload, status=201,
        headers={"Location": f"{API}/pagos/{payment_id}"})


@app.get(f"{API}/pagos")
@token_required
def list_payments():
    """
    Lista pagos.

    Por omision, SOLO los de los pedidos del usuario del token. Con
    payments:read se puede pedir ?all=true o filtrar por ?userId=.
    """
    identity = current_identity()
    limit, offset = _pagination()
    filters = {}

    pide_todos = (request.args.get("all") or "").strip().lower() in ("1", "true", "si", "yes")
    pedido_user = request.args.get("userId")
    if pide_todos or pedido_user:
        if not identity.has("payments:read"):
            raise Forbidden(
                "Solo puede listar sus propios pagos.",
                ["Para ver los de otros hace falta el permiso 'payments:read'."])
        if pedido_user:
            try:
                filters["user_id"] = int(pedido_user)
            except (TypeError, ValueError):
                raise ValidationError("userId debe ser un entero.")
    else:
        filters["user_id"] = identity.user_id

    if request.args.get("orderId"):
        try:
            order_id = int(request.args["orderId"])
        except (TypeError, ValueError):
            raise ValidationError("orderId debe ser un entero.")
        pedido = repo.order_owner(order_id)
        if pedido is None:
            raise NotFound(f"No existe el pedido {order_id}.")
        _require_owner_or("payments:read", pedido["user_id"])
        filters["order_id"] = order_id
        filters.pop("user_id", None)

    estado = (request.args.get("status") or "").strip().lower()
    if estado:
        if estado not in repo.ESTADOS:
            raise ValidationError(
                f"Estado desconocido: '{estado}'.",
                [f"Estados validos: {', '.join(repo.ESTADOS)}."])
        filters["status"] = estado
    if request.args.get("method"):
        filters["method"] = request.args["method"].strip().lower()

    rows, total = repo.list_payments(filters, sort=request.args.get("sort", "created"),
                                     order=request.args.get("order", "desc"),
                                     limit=limit, offset=offset)
    pagos = [repo.payment_to_dict(row) for row in rows]
    payload = {"count": len(pagos), "total": total, "limit": limit,
               "offset": offset, "filters": filters, "payments": pagos}
    return negotiator.collection_response(
        "payments", "payment", pagos, payload, total=total, limit=limit,
        offset=offset, headers={"X-Total-Count": str(total)})


@app.get(f"{API}/pagos/<int:payment_id>")
@token_required
def get_payment(payment_id):
    """Un pago con su bitacora. El propio siempre; los ajenos con payments:read."""
    row = _payment_or_404(payment_id)
    _require_owner_or("payments:read", row["user_id"])
    historial = [repo.history_to_dict(h) for h in repo.history_of(payment_id)]
    return negotiator.dict_response("payment",
                                    repo.payment_to_dict(row, history=historial))


@app.get(f"{API}/pagos/referencia/<path:reference>")
@token_required
def get_payment_by_reference(reference):
    """Un pago por su referencia legible (PAG-000123)."""
    row = repo.get_by_reference((reference or "").strip().upper())
    if row is None:
        raise NotFound(f"No existe el pago {reference}.")
    _require_owner_or("payments:read", row["user_id"])
    return negotiator.dict_response("payment", repo.payment_to_dict(row))


@app.get(f"{API}/pedidos/<int:order_id>/saldo")
@token_required
def order_balance(order_id):
    """
    Saldo del pedido: total, cobrado, comprometido y lo que falta.

    Es la pregunta que hace una caja antes de aceptar un pago.
    """
    pedido = repo.order_owner(order_id)
    if pedido is None:
        raise NotFound(f"No existe el pedido {order_id}.")
    _require_owner_or("payments:read", pedido["user_id"])
    saldo = repo.order_balance(order_id)
    if saldo is None:
        raise NotFound(f"No existe el pedido {order_id}.")
    return negotiator.dict_response("balance", repo.balance_to_dict(saldo))


# =====================================================================
# Rutas: mover el estado de un pago
# =====================================================================
@app.post(f"{API}/pagos/<int:payment_id>/aplicar")
@permission_required("payments:write")
def apply_payment(payment_id):
    """
    Aplica (confirma) el pago.

    Es el paso que de verdad mueve el pedido: cuando la suma de lo
    aplicado alcanza su total, un DISPARADOR de la base lo pasa a
    'pagado'. No se hace desde aqui a proposito, para que no exista forma
    de marcar un pedido como pagado sin dinero detras.
    """
    row = _payment_or_404(payment_id)
    if row["status"] == "aplicado":
        payload = repo.payment_to_dict(row)
        payload["alreadyApplied"] = True
        return negotiator.dict_response("payment", payload)

    data = read_payload()
    codigo = str(_pick(data, "authorizationCode", default="") or "")[:60] or None
    try:
        repo.apply_payment(payment_id, current_identity().user_id, codigo)
    except Exception as exc:                           # noqa: BLE001
        mensaje = raised_message(exc)
        if "transicion" in mensaje.lower() or "no existe" in mensaje.lower():
            raise Conflict(
                "No se puede aplicar este pago.",
                [mensaje,
                 "pendiente|autorizado -> aplicado · aplicado -> reembolsado."]) from exc
        raise

    metrics.incr("payments.applied")
    log.info("Pago %s aplicado por user_id=%s", payment_id,
             current_identity().user_id)
    actualizado = repo.get_payment(payment_id)
    payload = repo.payment_to_dict(actualizado)
    payload["previousStatus"] = row["status"]
    payload["balance"] = repo.balance_to_dict(repo.order_balance(row["order_id"]))
    # El pedido pudo pasar a 'pagado' por el disparador: se informa.
    payload["orderStatusAfter"] = (actualizado or {}).get("order_status")
    return negotiator.dict_response("payment", payload)


@app.post(f"{API}/pagos/<int:payment_id>/rechazar")
@permission_required("payments:write")
def reject_payment(payment_id):
    """Marca el pago como rechazado (la pasarela lo denego)."""
    row = _payment_or_404(payment_id)
    nota = str(_pick(read_payload(), "note", "motivo",
                     default="rechazado por la pasarela"))[:300]
    try:
        repo.change_status(payment_id, "rechazado", current_identity().user_id, nota)
    except Exception as exc:                           # noqa: BLE001
        mensaje = raised_message(exc)
        if "transicion" in mensaje.lower():
            raise Conflict("No se puede rechazar este pago.", [mensaje]) from exc
        raise
    metrics.incr("payments.rejected")
    payload = repo.payment_to_dict(repo.get_payment(payment_id))
    payload["previousStatus"] = row["status"]
    return negotiator.dict_response("payment", payload)


@app.post(f"{API}/pagos/<int:payment_id>/reembolsar")
@permission_required("payments:write")
def refund_payment(payment_id):
    """
    Reembolsa un pago ya aplicado.

    OJO con lo que NO hace: el pedido NO vuelve de 'pagado' a
    'pendiente'. 'pagado' -> 'pendiente' no es una transicion valida, y
    rehacer la historia de un pedido seria peor que dejar constancia. El
    reembolso queda registrado en payment_status_history y el descuadre
    lo resuelve una persona.
    """
    row = _payment_or_404(payment_id)
    if row["status"] != "aplicado":
        raise Conflict(
            f"Solo se puede reembolsar un pago aplicado (este esta "
            f"'{row['status']}').",
            ["Si aun no se aplico, rechacelo en lugar de reembolsarlo."])
    nota = str(_pick(read_payload(), "note", "motivo",
                     default="reembolso"))[:300]
    try:
        repo.change_status(payment_id, "reembolsado", current_identity().user_id, nota)
    except Exception as exc:                           # noqa: BLE001
        mensaje = raised_message(exc)
        if "transicion" in mensaje.lower():
            raise Conflict("No se puede reembolsar este pago.", [mensaje]) from exc
        raise
    metrics.incr("payments.refunded")
    log.info("Pago %s reembolsado por user_id=%s", payment_id,
             current_identity().user_id)
    payload = repo.payment_to_dict(repo.get_payment(payment_id))
    payload["previousStatus"] = row["status"]
    payload["balance"] = repo.balance_to_dict(repo.order_balance(row["order_id"]))
    payload["note"] = ("El pedido NO vuelve a 'pendiente': queda constancia del "
                       "reembolso y el descuadre lo resuelve una persona.")
    return negotiator.dict_response("payment", payload)


# =====================================================================
# Manejo de errores
# =====================================================================
register_error_handlers(app, negotiator, debug=config.DEBUG, service="pagos")


@app.errorhandler(HTTPException)
def handle_http_error(exc):
    code = {400: "bad_request", 404: "not_found", 405: "method_not_allowed",
            415: "unsupported_media_type"}.get(exc.code, "http_error")
    return negotiator.error_response(exc.code, code, exc.description or exc.name)


if __name__ == "__main__":
    from library_common.env import redacted

    log.info("Pagos -> http://%s:%s%s/pagos", config.HOST, config.PORT, API)
    log.info("Swagger UI -> http://%s:%s/docs", config.HOST, config.PORT)
    log.info("PostgreSQL -> %s (esquema %s)", database.target, config.PGSCHEMA)
    log.info("Redis -> %s", redacted(config.REDIS_URL) or "SIN CONFIGURAR")
    log.info("CORS origins -> %s", ", ".join(config.CORS_ORIGINS))
    for item in config.warnings():
        log.warning(item)
    app.run(host=config.HOST, port=config.PORT, debug=config.DEBUG, load_dotenv=False)
