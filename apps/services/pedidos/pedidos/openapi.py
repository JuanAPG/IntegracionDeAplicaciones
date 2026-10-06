"""
apps/services/pedidos/pedidos/openapi.py
Especificacion OpenAPI 3.0.3 del microservicio de pedidos.
"""
from . import config
from library_common.openapi import build

LINE_SCHEMA = {
    "type": "object",
    "properties": {
        "id": {"type": "integer"},
        "bookId": {"type": "integer"},
        "isbn": {"type": "string"},
        "title": {"type": "string",
                  "description": "Congelado al comprar: si el libro se renombra, "
                                 "el pedido historico sigue diciendo que se compro."},
        "quantity": {"type": "integer", "minimum": 1},
        "unitPrice": {"type": "number", "format": "double",
                      "description": "Congelado al comprar; books.price puede cambiar."},
        "lineTotal": {"type": "number", "format": "double"},
    },
}

ORDER_SCHEMA = {
    "type": "object",
    "properties": {
        "id": {"type": "integer"},
        "orderNumber": {"type": "string", "example": "PED-000123"},
        "status": {"type": "string",
                   "enum": ["pendiente", "pagado", "enviado", "entregado", "cancelado"]},
        "currency": {"type": "string", "example": "MXN"},
        "subtotal": {"type": "number", "format": "double"},
        "shippingCost": {"type": "number", "format": "double"},
        "total": {"type": "number", "format": "double"},
        "paidAmount": {"type": "number", "format": "double",
                       "description": "Suma de los pagos aplicados."},
        "user": {"type": "object",
                 "properties": {"id": {"type": "integer"},
                                "email": {"type": "string"},
                                "name": {"type": "string"}}},
        "shipping": {"type": "object",
                     "properties": {"carrier": {"type": "string", "nullable": True},
                                    "trackingCode": {"type": "string", "nullable": True}}},
        "lines": {"type": "array", "items": LINE_SCHEMA},
        "placedAt": {"type": "string", "format": "date-time"},
        "paidAt": {"type": "string", "format": "date-time", "nullable": True},
        "shippedAt": {"type": "string", "format": "date-time", "nullable": True},
        "deliveredAt": {"type": "string", "format": "date-time", "nullable": True},
        "cancelledAt": {"type": "string", "format": "date-time", "nullable": True},
    },
}

TRACKING_SCHEMA = {
    "type": "object",
    "description": "LO UNICO que se publica sin token. No lleva dueno, ni "
                   "correo, ni importes, ni que libros se compraron.",
    "properties": {
        "orderNumber": {"type": "string", "example": "PED-000123"},
        "status": {"type": "string",
                   "enum": ["pendiente", "pagado", "enviado", "entregado", "cancelado"]},
        "carrier": {"type": "string", "nullable": True, "example": "Estafeta"},
        "trackingCode": {"type": "string", "nullable": True},
        "placedAt": {"type": "string", "format": "date-time"},
        "shippedAt": {"type": "string", "format": "date-time", "nullable": True},
        "deliveredAt": {"type": "string", "format": "date-time", "nullable": True},
        "itemCount": {"type": "integer", "description": "Cuantas piezas lleva el paquete."},
    },
}

CREATE_BODY = {
    "type": "object",
    "required": ["lines"],
    "properties": {
        "lines": {
            "type": "array", "minItems": 1,
            "description": "El precio NO se manda: lo congela el servidor desde "
                           "library.books. Repetir un libro suma unidades.",
            "items": {"type": "object", "required": ["bookId", "quantity"],
                      "properties": {"bookId": {"type": "integer"},
                                     "quantity": {"type": "integer", "minimum": 1,
                                                  "maximum": 100}}},
        },
        "userId": {"type": "integer",
                   "description": "Solo con orders:write; por omision, el del token."},
        "shippingCost": {"type": "number", "format": "double", "default": 0},
        "shippingAddress": {"type": "string"},
        "notes": {"type": "string"},
    },
}

ID_PARAM = [{"name": "id", "in": "path", "required": True,
             "schema": {"type": "integer"}, "description": "Id del pedido."}]
API = config.API_PREFIX


def build_spec():
    return build(
        service=config.SERVICE_NAME,
        title="Libreria en Linea — Microservicio de pedidos",
        description=(
            "Pedidos, lineas de pedido, reserva de stock y estados.\n\n"
            "**El stock no se duplica.** `library.books.stock` ya existe y lo "
            "publica el microservicio de libros. Aqui se RESERVA al crear el "
            "pedido y se DEVUELVE al cancelarlo, en la misma transaccion que "
            "las lineas (`sp_crear_pedido`, `sp_cancelar_pedido`). No hay un "
            "inventario paralelo.\n\n"
            "**Maquina de estados**, impuesta por un disparador de la base y no "
            "por la aplicacion:\n\n"
            "    pendiente -> pagado | cancelado\n"
            "    pagado    -> enviado | cancelado\n"
            "    enviado   -> entregado\n"
            "    entregado, cancelado -> (finales)\n\n"
            "El paso a `pagado` normalmente lo dispara el microservicio de "
            "PAGOS cuando lo aplicado alcanza el total.\n\n"
            "**Lo unico publico es `GET /envios/{numero}`**, el estatus de "
            "envio, para que un tercero pueda manejar su logistica sin tener "
            "cuenta. Todo lo demas exige token."),
        version=config.XML_VERSION,
        namespace=config.XML_NAMESPACE,
        port=config.PORT,
        tags=["Servicio", "Envios", "Pedidos", "Estados"],
        extra_schemas={"Order": ORDER_SCHEMA, "OrderLine": LINE_SCHEMA,
                       "Shipment": TRACKING_SCHEMA},
        paths=[
            {"path": "/", "method": "get", "tag": "Servicio",
             "summary": "Indice del servicio", "auth": None,
             "success": (200, "Indice", {"type": "object"})},
            {"path": "/health", "method": "get", "tag": "Servicio",
             "summary": "Estado del servicio", "auth": None,
             "success": (200, "Estado", {"type": "object"}),
             "errors": ["Unavailable"]},
            {"path": "/metrics", "method": "get", "tag": "Servicio",
             "summary": "Metricas del proceso", "auth": None,
             "success": (200, "Metricas", {"type": "object"})},

            {"path": f"{API}/envios/{{numero}}", "method": "get", "tag": "Envios",
             "summary": "RASTREO PUBLICO del envio (sin token)",
             "description": "Pensado para que la paqueteria maneje su "
                            "logistica. Devuelve EXCLUSIVAMENTE el estado del "
                            "envio y sus fechas. Cacheado en Redis con TTL "
                            "corto; `X-Cache` dice si vino de Redis.\n\n"
                            "El numero de pedido es secuencial (`PED-000123`): "
                            "tratelo como un dato que se comparte con quien "
                            "transporta el paquete, no como un secreto.",
             "auth": None,
             "params": [{"name": "numero", "in": "path", "required": True,
                         "schema": {"type": "string"}, "example": "PED-000123"}],
             "success": (200, "Estatus del envio", TRACKING_SCHEMA),
             "errors": ["BadRequest", "NotFound", "Unavailable"]},

            {"path": f"{API}/pedidos", "method": "post", "tag": "Pedidos",
             "summary": "Crear un pedido",
             "description": "Reserva stock de forma atomica y congela los "
                            "precios desde `library.books`. Si no alcanza el "
                            "stock responde 409 diciendo de que libro se trata "
                            "y no deja nada a medias. Un cerrojo en Redis por "
                            "usuario (10 s) evita el pedido doble cuando el "
                            "cliente reintenta tras un tiempo de espera.",
             "auth": True, "body": CREATE_BODY,
             "success": (201, "Pedido creado", ORDER_SCHEMA),
             "errors": ["BadRequest", "Unauthorized", "Forbidden", "Conflict",
                        "Unavailable"]},

            {"path": f"{API}/pedidos", "method": "get", "tag": "Pedidos",
             "summary": "Listar pedidos",
             "description": "Por omision solo los del usuario del token. Con "
                            "`orders:read` se puede pedir `?all=true` o "
                            "`?userId=`.",
             "auth": True, "paginated": True,
             "params": [
                 {"name": "all", "in": "query", "schema": {"type": "boolean"},
                  "description": "Todos los pedidos. Requiere orders:read."},
                 {"name": "userId", "in": "query", "schema": {"type": "integer"},
                  "description": "Pedidos de otra cuenta. Requiere orders:read."},
                 {"name": "status", "in": "query",
                  "schema": {"type": "string",
                             "enum": ["pendiente", "pagado", "enviado",
                                      "entregado", "cancelado"]}},
                 {"name": "number", "in": "query", "schema": {"type": "string"}},
                 {"name": "sort", "in": "query",
                  "schema": {"type": "string",
                             "enum": ["id", "number", "total", "status", "placed", "updated"]}},
                 {"name": "order", "in": "query",
                  "schema": {"type": "string", "enum": ["asc", "desc"]}},
             ],
             "success": (200, "Pedidos", {"type": "object",
                                          "properties": {"orders": {"type": "array",
                                                                    "items": ORDER_SCHEMA}}}),
             "errors": ["BadRequest", "Unauthorized", "Forbidden", "Unavailable"]},

            {"path": f"{API}/pedidos/{{id}}", "method": "get", "tag": "Pedidos",
             "summary": "Un pedido con sus lineas",
             "description": "El propio siempre; los ajenos con `orders:read`.",
             "auth": True, "params": ID_PARAM,
             "success": (200, "El pedido", ORDER_SCHEMA),
             "errors": ["Unauthorized", "Forbidden", "NotFound", "Unavailable"]},

            {"path": f"{API}/pedidos/numero/{{numero}}", "method": "get",
             "tag": "Pedidos", "summary": "Un pedido por su numero",
             "description": "El pedido COMPLETO: exige token y ser el dueno (o "
                            "`orders:read`). Para el estatus de envio sin token "
                            "esta `GET /envios/{numero}`.",
             "auth": True,
             "params": [{"name": "numero", "in": "path", "required": True,
                         "schema": {"type": "string"}, "example": "PED-000123"}],
             "success": (200, "El pedido", ORDER_SCHEMA),
             "errors": ["Unauthorized", "Forbidden", "NotFound", "Unavailable"]},

            {"path": f"{API}/pedidos/{{id}}/historial", "method": "get",
             "tag": "Estados", "summary": "Bitacora de estados",
             "description": "Quien cambio el estado, cuando y de que a que.",
             "auth": True, "params": ID_PARAM,
             "success": (200, "Bitacora", {"type": "object"}),
             "errors": ["Unauthorized", "Forbidden", "NotFound", "Unavailable"]},

            {"path": f"{API}/pedidos/{{id}}/lineas", "method": "patch",
             "tag": "Pedidos", "summary": "Ajustar cantidades",
             "description": "Solo mientras el pedido siga PENDIENTE: una vez "
                            "pagado, cambiar lo comprado descuadraria el cobro. "
                            "`quantity: 0` quita la linea. El stock se ajusta "
                            "por la DIFERENCIA. Si el pedido queda sin lineas "
                            "se cancela y se devuelve el stock.",
             "auth": True, "params": ID_PARAM,
             "body": {"type": "object", "required": ["lines"],
                      "properties": {"lines": {"type": "array",
                                               "items": {"type": "object",
                                                         "properties": {
                                                             "bookId": {"type": "integer"},
                                                             "quantity": {"type": "integer",
                                                                          "minimum": 0}}}}}},
             "success": (200, "Pedido ajustado", ORDER_SCHEMA),
             "errors": ["BadRequest", "Unauthorized", "Forbidden", "NotFound",
                        "Conflict", "Unavailable"]},

            {"path": f"{API}/pedidos/{{id}}", "method": "delete", "tag": "Pedidos",
             "summary": "Cancelar y devolver el stock",
             "description": "El dueno puede cancelar mientras siga pendiente. "
                            "Cancelar uno ya PAGADO exige `orders:write` (hay "
                            "dinero de por medio). Un pedido enviado o "
                            "entregado ya no se cancela: eso seria una "
                            "devolucion, fuera del alcance de esta entrega.",
             "auth": True, "params": ID_PARAM,
             "body": {"type": "object",
                      "properties": {"reason": {"type": "string"}}},
             "body_required": False,
             "success": (200, "Pedido cancelado", ORDER_SCHEMA),
             "errors": ["Unauthorized", "Forbidden", "NotFound", "Conflict",
                        "Unavailable"]},

            {"path": f"{API}/pedidos/{{id}}/estado", "method": "put",
             "tag": "Estados", "summary": "Mover el estado del pedido",
             "description": "Las transiciones validas las impone un disparador "
                            "de la base. Al marcar `enviado` conviene mandar "
                            "`carrier` y `trackingCode`: es lo que despues lee "
                            "la paqueteria en `GET /envios/{numero}`.",
             "auth": "orders:status", "params": ID_PARAM,
             "body": {"type": "object", "required": ["status"],
                      "properties": {
                          "status": {"type": "string",
                                     "enum": ["pagado", "enviado", "entregado", "cancelado"]},
                          "carrier": {"type": "string", "example": "Estafeta"},
                          "trackingCode": {"type": "string"},
                          "note": {"type": "string"}}},
             "success": (200, "Estado cambiado", ORDER_SCHEMA),
             "errors": ["BadRequest", "Unauthorized", "Forbidden", "NotFound",
                        "Conflict", "Unavailable"]},
        ])
