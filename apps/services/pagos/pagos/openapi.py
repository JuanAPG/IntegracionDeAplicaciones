"""
apps/services/pagos/pagos/openapi.py
Especificacion OpenAPI 3.0.3 del microservicio de pagos.
"""
from . import config
from library_common.openapi import build

PAYMENT_SCHEMA = {
    "type": "object",
    "properties": {
        "id": {"type": "integer"},
        "reference": {"type": "string", "example": "PAG-000045"},
        "status": {"type": "string",
                   "enum": ["pendiente", "autorizado", "aplicado",
                            "rechazado", "reembolsado"]},
        "amount": {"type": "number", "format": "double"},
        "currency": {"type": "string", "example": "MXN"},
        "method": {"type": "object",
                   "properties": {"id": {"type": "integer"},
                                  "name": {"type": "string", "example": "tarjeta"}}},
        "order": {"type": "object",
                  "properties": {"id": {"type": "integer"},
                                 "number": {"type": "string"},
                                 "status": {"type": "string"},
                                 "total": {"type": "number", "format": "double"}}},
        "authorizationCode": {"type": "string", "nullable": True,
                              "description": "Referencia que devuelve la pasarela."},
        "cardLast4": {"type": "string", "nullable": True,
                      "description": "Los cuatro ultimos digitos que publica la "
                                     "pasarela. NUNCA el numero completo."},
        "createdAt": {"type": "string", "format": "date-time"},
        "appliedAt": {"type": "string", "format": "date-time", "nullable": True},
    },
}

BALANCE_SCHEMA = {
    "type": "object",
    "properties": {
        "orderId": {"type": "integer"},
        "orderNumber": {"type": "string"},
        "orderStatus": {"type": "string"},
        "total": {"type": "number", "format": "double"},
        "paid": {"type": "number", "format": "double",
                 "description": "Suma de los pagos APLICADOS."},
        "committed": {"type": "number", "format": "double",
                      "description": "Autorizados y pendientes, aun sin aplicar."},
        "balance": {"type": "number", "format": "double",
                    "description": "total - paid: lo que falta por cobrar."},
    },
}

METHOD_SCHEMA = {
    "type": "object",
    "properties": {
        "id": {"type": "integer"},
        "name": {"type": "string", "example": "tarjeta"},
        "description": {"type": "string"},
        "requiresAuthorization": {
            "type": "boolean",
            "description": "false (efectivo) hace que el pago nazca ya aplicado."},
        "isActive": {"type": "boolean"},
    },
}

REGISTER_BODY = {
    "type": "object",
    "required": ["amount"],
    "properties": {
        "orderId": {"type": "integer", "description": "O bien orderNumber."},
        "orderNumber": {"type": "string", "example": "PED-000123"},
        "amount": {"type": "number", "format": "double", "minimum": 0.01},
        "methodId": {"type": "integer", "description": "O bien method por nombre."},
        "method": {"type": "string", "example": "tarjeta"},
        "idempotencyKey": {
            "type": "string", "maxLength": 80,
            "description": "Dos intentos con la misma clave son el MISMO pago. "
                           "Es lo que evita el cobro doble cuando el cliente "
                           "reintenta tras un tiempo de espera."},
        "authorizationCode": {"type": "string",
                              "description": "Referencia de la pasarela."},
        "cardLast4": {"type": "string", "pattern": "^[0-9]{4}$"},
        "notes": {"type": "string"},
    },
}

ID_PARAM = [{"name": "id", "in": "path", "required": True,
             "schema": {"type": "integer"}, "description": "Id del pago."}]
API = config.API_PREFIX


def build_spec():
    return build(
        service=config.SERVICE_NAME,
        title="Libreria en Linea — Microservicio de pagos",
        description=(
            "Registra pagos y actualiza el estado de los pedidos.\n\n"
            "**Aqui no hay ninguna lectura publica.** Un pago es informacion "
            "financiera de una persona concreta. Lo unico que el par "
            "pedidos/pagos publica sin token es el ESTATUS DE ENVIO, y vive en "
            "el microservicio de pedidos (`GET /envios/{numero}`), porque es lo "
            "que necesita un tercero para manejar su logistica. Incluso "
            "`GET /metodos` exige token.\n\n"
            "**Que NO se guarda:** numero de tarjeta, CVV, fecha de "
            "vencimiento ni titular. Solo la referencia de la pasarela "
            "(`authorizationCode`) y, como mucho, los cuatro ultimos digitos "
            "que ella misma publica. Mandar un campo que parezca un "
            "instrumento de pago (`cardNumber`, `cvv`, `pan`...) devuelve 400.\n\n"
            "**El pago mueve el pedido, pero no lo decide este codigo.** Cuando "
            "la suma de lo APLICADO alcanza el total, un DISPARADOR de la base "
            "pasa el pedido a `pagado`. Asi no hay forma de marcar un pedido "
            "como pagado sin que exista el dinero detras.\n\n"
            "**Estados del pago:**\n\n"
            "    pendiente  -> autorizado | aplicado | rechazado\n"
            "    autorizado -> aplicado | rechazado\n"
            "    aplicado   -> reembolsado\n"
            "    rechazado, reembolsado -> (finales)\n\n"
            "**Contra el cobro doble:** `idempotencyKey` mas un cerrojo en "
            "Redis por pedido mientras se registra."),
        version=config.XML_VERSION,
        namespace=config.XML_NAMESPACE,
        port=config.PORT,
        tags=["Servicio", "Metodos", "Pagos", "Saldo"],
        extra_schemas={"Payment": PAYMENT_SCHEMA, "Balance": BALANCE_SCHEMA,
                       "PaymentMethod": METHOD_SCHEMA},
        paths=[
            {"path": "/", "method": "get", "tag": "Servicio",
             "summary": "Indice del servicio", "auth": None,
             "success": (200, "Indice", {"type": "object"})},
            {"path": "/health", "method": "get", "tag": "Servicio",
             "summary": "Estado del servicio",
             "description": "Devuelve 503 si PostgreSQL o Redis fallan: sin "
                            "Redis no se puede comprobar la revocacion y, como "
                            "este servicio no tiene endpoints publicos, no "
                            "puede hacer nada util.",
             "auth": None, "success": (200, "Estado", {"type": "object"}),
             "errors": ["Unavailable"]},
            {"path": "/metrics", "method": "get", "tag": "Servicio",
             "summary": "Metricas del proceso", "auth": None,
             "success": (200, "Metricas", {"type": "object"})},

            {"path": f"{API}/metodos", "method": "get", "tag": "Metodos",
             "summary": "Catalogo de metodos de pago",
             "description": "Exige token aunque no tenga datos personales: en "
                            "este servicio no hay ninguna puerta publica.",
             "auth": True,
             "params": [{"name": "all", "in": "query",
                         "schema": {"type": "boolean"},
                         "description": "Incluye los metodos desactivados."}],
             "success": (200, "Metodos", {"type": "object",
                                          "properties": {"methods": {"type": "array",
                                                                     "items": METHOD_SCHEMA}}}),
             "errors": ["Unauthorized", "Unavailable"]},

            {"path": f"{API}/pagos", "method": "post", "tag": "Pagos",
             "summary": "Registrar un pago",
             "description": "Un cliente puede pagar SUS pedidos; cobrar el de "
                            "otro exige `payments:write`. El importe no puede "
                            "exceder el saldo pendiente. Un metodo que no "
                            "requiere autorizacion (efectivo) nace ya "
                            "`aplicado`.",
             "auth": True, "body": REGISTER_BODY,
             "success": (201, "Pago registrado", PAYMENT_SCHEMA),
             "errors": ["BadRequest", "Unauthorized", "Forbidden", "NotFound",
                        "Conflict", "Unavailable"]},

            {"path": f"{API}/pagos", "method": "get", "tag": "Pagos",
             "summary": "Listar pagos",
             "description": "Por omision solo los de los pedidos del usuario "
                            "del token. Con `payments:read`, `?all=true` o "
                            "`?userId=`.",
             "auth": True, "paginated": True,
             "params": [
                 {"name": "all", "in": "query", "schema": {"type": "boolean"},
                  "description": "Todos los pagos. Requiere payments:read."},
                 {"name": "userId", "in": "query", "schema": {"type": "integer"}},
                 {"name": "orderId", "in": "query", "schema": {"type": "integer"}},
                 {"name": "status", "in": "query",
                  "schema": {"type": "string",
                             "enum": ["pendiente", "autorizado", "aplicado",
                                      "rechazado", "reembolsado"]}},
                 {"name": "method", "in": "query", "schema": {"type": "string"}},
                 {"name": "sort", "in": "query",
                  "schema": {"type": "string",
                             "enum": ["id", "reference", "amount", "status",
                                      "created", "applied"]}},
             ],
             "success": (200, "Pagos", {"type": "object",
                                        "properties": {"payments": {"type": "array",
                                                                    "items": PAYMENT_SCHEMA}}}),
             "errors": ["BadRequest", "Unauthorized", "Forbidden", "NotFound",
                        "Unavailable"]},

            {"path": f"{API}/pagos/{{id}}", "method": "get", "tag": "Pagos",
             "summary": "Un pago con su bitacora",
             "description": "El propio siempre; los ajenos con `payments:read`.",
             "auth": True, "params": ID_PARAM,
             "success": (200, "El pago", PAYMENT_SCHEMA),
             "errors": ["Unauthorized", "Forbidden", "NotFound", "Unavailable"]},

            {"path": f"{API}/pagos/referencia/{{ref}}", "method": "get",
             "tag": "Pagos", "summary": "Un pago por su referencia",
             "auth": True,
             "params": [{"name": "ref", "in": "path", "required": True,
                         "schema": {"type": "string"}, "example": "PAG-000045"}],
             "success": (200, "El pago", PAYMENT_SCHEMA),
             "errors": ["Unauthorized", "Forbidden", "NotFound", "Unavailable"]},

            {"path": f"{API}/pagos/{{id}}/aplicar", "method": "post", "tag": "Pagos",
             "summary": "Aplicar (confirmar) el pago",
             "description": "Es el paso que mueve el pedido: cuando lo aplicado "
                            "alcanza el total, un disparador de la base lo pasa "
                            "a `pagado`. Idempotente: aplicar dos veces "
                            "devuelve 200 con `alreadyApplied`.",
             "auth": "payments:write", "params": ID_PARAM,
             "body": {"type": "object",
                      "properties": {"authorizationCode": {"type": "string"}}},
             "body_required": False,
             "success": (200, "Pago aplicado", PAYMENT_SCHEMA),
             "errors": ["Unauthorized", "Forbidden", "NotFound", "Conflict",
                        "Unavailable"]},

            {"path": f"{API}/pagos/{{id}}/rechazar", "method": "post", "tag": "Pagos",
             "summary": "Rechazar el pago",
             "description": "La pasarela lo denego.",
             "auth": "payments:write", "params": ID_PARAM,
             "body": {"type": "object", "properties": {"note": {"type": "string"}}},
             "body_required": False,
             "success": (200, "Pago rechazado", PAYMENT_SCHEMA),
             "errors": ["Unauthorized", "Forbidden", "NotFound", "Conflict",
                        "Unavailable"]},

            {"path": f"{API}/pagos/{{id}}/reembolsar", "method": "post",
             "tag": "Pagos", "summary": "Reembolsar un pago aplicado",
             "description": "OJO con lo que NO hace: el pedido no vuelve de "
                            "`pagado` a `pendiente`. Esa transicion no es "
                            "valida, y rehacer la historia de un pedido seria "
                            "peor que dejar constancia. El reembolso queda en "
                            "`payment_status_history` y el descuadre lo "
                            "resuelve una persona.",
             "auth": "payments:write", "params": ID_PARAM,
             "body": {"type": "object", "properties": {"note": {"type": "string"}}},
             "body_required": False,
             "success": (200, "Pago reembolsado", PAYMENT_SCHEMA),
             "errors": ["Unauthorized", "Forbidden", "NotFound", "Conflict",
                        "Unavailable"]},

            {"path": f"{API}/pedidos/{{id}}/saldo", "method": "get", "tag": "Saldo",
             "summary": "Saldo del pedido",
             "description": "Total, cobrado, comprometido y lo que falta. Es la "
                            "pregunta que hace una caja antes de aceptar un pago.",
             "auth": True,
             "params": [{"name": "id", "in": "path", "required": True,
                         "schema": {"type": "integer"},
                         "description": "Id del PEDIDO."}],
             "success": (200, "Saldo", BALANCE_SCHEMA),
             "errors": ["Unauthorized", "Forbidden", "NotFound", "Unavailable"]},
        ])
