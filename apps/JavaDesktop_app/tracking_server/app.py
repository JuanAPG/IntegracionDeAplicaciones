"""
tracking_server/app.py
Servidor de rastreo de entregas: Flask + Flask-Sock.

QUE ES Y QUE NO ES
Es un emisor en tiempo real. Simula el desplazamiento del vehiculo de
reparto de un pedido por calles reales de Monterrey y empuja cada
posicion por WebSocket a quien este viendo ESE pedido.

NO es el dueno de ningun dato de negocio. El pedido, su importe, su
estado real y su propiedad viven en el microservicio de pedidos y en
PostgreSQL. Este proceso no tiene base de datos a proposito: si se
reinicia, pierde el progreso de las simulaciones en curso y nada mas, y
al volver reconstruye la misma ruta para el mismo codigo porque el
destino se deriva del codigo.

POR QUE WEBSOCKET Y NO REST
Una posicion cada segundo por REST obliga al cliente a preguntar
"¿ya cambio?" una y otra vez, y casi siempre la respuesta es que no.
El WebSocket invierte la relacion: la conexion queda abierta y el
servidor habla cuando tiene algo que decir. Para un vehiculo en
movimiento, que es justo el caso en que el servidor siempre tiene algo
nuevo, ademas se ahorra el saludo TCP y las cabeceras HTTP de cada
sondeo.

EL PROTOCOLO, EN CUATRO MENSAJES (servidor -> cliente)

  snapshot  al conectar, una sola vez. Trae la ruta COMPLETA para
            dibujarla, la estela ya recorrida, la posicion actual y la
            lista de estados posibles.
  posicion  una por tick mientras el vehiculo se mueve.
  estado    solo cuando el estado CAMBIA (confirmado -> preparando ->
            enviado -> en ruta -> entregado).
  error     antes de cerrar, cuando no se autoriza el rastreo.

El cliente no manda nada: el rol de la conexion y el pedido que quiere
ver van en la URL, y el token en la cabecera.

      ws://host:5900/ws?code=LIB-MTY-2026-000042
      Authorization: Bearer <jwt>

QUIEN PUEDE VER QUE: ver auth.py. En resumen, se verifica la firma del
token con el mismo secreto que los seis microservicios y despues se le
pregunta al servicio de pedidos si el pedido es de quien lo pide.
"""
import json
import logging
import threading
import time

from flask import Flask, Response, jsonify, request, send_from_directory
from flask_sock import Sock

import auth
import config
import entregas

logging.basicConfig(
    level=logging.DEBUG if config.DEBUG else logging.INFO,
    format="%(asctime)s %(levelname)-7s [rastreo] %(message)s")
log = logging.getLogger("rastreo")

app = Flask(__name__, static_folder="static", static_url_path="/static")
# ping cada 25 s: mantiene viva la conexion a traves de proxies que
# cortan las conexiones ociosas, que es la causa numero uno de
# WebSockets que "se caen solos" cada minuto.
app.config["SOCK_SERVER_OPTIONS"] = {"ping_interval": 25}
sock = Sock(app)

REGISTRO = entregas.Registro()

# Suscriptores por codigo de rastreo: {codigo: {ws, ws, ...}}
#
# ES UN DICCIONARIO POR CODIGO Y NO UN CONJUNTO GLOBAL, y esa es la
# diferencia de fondo con el proyecto de referencia, donde todos los
# clientes recibian todos los vehiculos. Aqui cada quien recibe
# UNICAMENTE las posiciones del pedido que esta autorizado a ver.
_suscriptores = {}
_lock = threading.RLock()


# =====================================================================
# Difusion
# =====================================================================
def _suscribir(codigo, ws):
    with _lock:
        _suscriptores.setdefault(codigo, set()).add(ws)


def _desuscribir(codigo, ws):
    with _lock:
        conjunto = _suscriptores.get(codigo)
        if conjunto:
            conjunto.discard(ws)
            if not conjunto:
                _suscriptores.pop(codigo, None)


def _difundir(codigo, mensaje):
    """Manda el mensaje a los clientes de ESE codigo y solo a ellos."""
    texto = json.dumps(mensaje, ensure_ascii=False)
    with _lock:
        destinatarios = list(_suscriptores.get(codigo, ()))
    caidos = []
    for ws in destinatarios:
        try:
            ws.send(texto)
        except Exception:
            caidos.append(ws)
    for ws in caidos:
        _desuscribir(codigo, ws)


def _hay_quien_mire(codigo):
    with _lock:
        return bool(_suscriptores.get(codigo))


# =====================================================================
# El bucle de simulacion
# =====================================================================
def _bucle():
    """
    Avanza todas las entregas y emite sus posiciones.

    Solo emite si hay alguien escuchando ese codigo: una entrega sin
    espectadores sigue avanzando (para que al volver a conectarse se vea
    donde deberia estar) pero no gasta mensajes.
    """
    log.info("Bucle de simulacion en marcha: un tick cada %.1f s, "
             "reparto a %.0f km/h, reloj acelerado x%.0f",
             config.INTERVALO_S, config.VELOCIDAD_KMH, config.FACTOR_TIEMPO)
    while True:
        inicio = time.time()
        for entrega in REGISTRO.activas():
            try:
                cambio_estado = entrega.avanzar()
                if not _hay_quien_mire(entrega.codigo):
                    continue
                if cambio_estado:
                    _difundir(entrega.codigo, entrega.evento_estado())
                if entrega.estado != entregas.ENTREGADO or cambio_estado:
                    _difundir(entrega.codigo, entrega.posicion())
            except Exception:
                log.exception("Fallo avanzando la entrega %s", entrega.codigo)
        # Se descuenta lo que costo el tick para que el intervalo sea el
        # que dice ser aunque haya muchas entregas.
        time.sleep(max(0.05, config.INTERVALO_S - (time.time() - inicio)))


# =====================================================================
# WebSocket
# =====================================================================
@sock.route("/ws")
def websocket(ws):
    """
    Conexion de rastreo de UN pedido.

        ws://host:5900/ws?code=LIB-MTY-2026-000042
        Authorization: Bearer <jwt>

    El token se lee de la cabecera. Flask-Sock expone el `request` del
    handshake, de modo que la cabecera llega igual que en una peticion
    HTTP normal; no hace falta pasarlo por la URL, que es donde no debe
    ir (las URL acaban en registros y en el historial).
    """
    codigo = (request.args.get("code") or "").strip().upper()
    cabecera = request.headers.get("Authorization", "")
    token = cabecera[7:].strip() if cabecera.lower().startswith("bearer ") else ""
    # Se admite tambien ?token= como ultimo recurso para clientes que no
    # pueden poner cabeceras en el handshake (algunos navegadores). Se
    # avisa, porque es peor.
    if not token and request.args.get("token"):
        token = request.args.get("token").strip()
        log.warning("Token recibido por query string para %s: preferir la cabecera", codigo)

    try:
        numero_pedido, user_id = auth.autorizar(codigo, token)
    except auth.NoAutorizado as exc:
        log.info("Rastreo denegado para %s: %s", codigo or "(sin codigo)", exc.motivo)
        try:
            ws.send(json.dumps({"type": "error", "code": codigo,
                                "reason": exc.motivo, "errorCode": exc.codigo},
                               ensure_ascii=False))
        except Exception:
            pass
        # 1008 = violacion de politica. Es el codigo correcto para
        # "te entiendo pero no te dejo", y el cliente lo distingue de un
        # corte de red.
        ws.close(1008, exc.codigo)
        return

    entrega = REGISTRO.obtener_o_crear(codigo, numero_pedido)
    log.info("Rastreo abierto: %s (%s) usuario=%s destino=%s",
             codigo, numero_pedido, user_id, entrega.destino)

    _suscribir(codigo, ws)
    try:
        ws.send(json.dumps(entrega.snapshot(), ensure_ascii=False))
        # El cliente no manda nada; este bucle solo mantiene la conexion
        # abierta y detecta cuando se cierra.
        while True:
            if ws.receive() is None:
                break
    except Exception:
        pass
    finally:
        _desuscribir(codigo, ws)
        log.info("Rastreo cerrado: %s", codigo)


# =====================================================================
# HTTP
# =====================================================================
@app.get("/health")
def health():
    """Estado del servidor. Publico, como el /health de los seis servicios."""
    with _lock:
        mirones = sum(len(s) for s in _suscriptores.values())
    return jsonify({
        "service": "tracking",
        "status": "ok",
        "deliveries": len(REGISTRO.activas()),
        "subscribers": mirones,
        "requireAuth": config.REQUIRE_AUTH,
        "jwtConfigured": bool(config.JWT_SECRET),
        "pedidosUrl": config.PEDIDOS_URL,
        "timeFactor": config.FACTOR_TIEMPO,
    })


@app.get("/api/entregas/<codigo>")
def estado_entrega(codigo):
    """
    El estado actual por REST.

    Existe como RESPALDO: si el WebSocket no se puede abrir (un proxy
    que no admite el upgrade, por ejemplo), la aplicacion todavia puede
    ensenar donde va el pedido, aunque sin movimiento continuo. Exige la
    misma autorizacion que el WebSocket.
    """
    cabecera = request.headers.get("Authorization", "")
    token = cabecera[7:].strip() if cabecera.lower().startswith("bearer ") else ""
    try:
        numero, _ = auth.autorizar(codigo, token)
    except auth.NoAutorizado as exc:
        estado = {"token_missing": 401, "token_expired": 401, "invalid_token": 401,
                  "forbidden": 403, "not_found": 404, "bad_request": 400}.get(exc.codigo, 503)
        return jsonify({"error": {"status": estado, "code": exc.codigo,
                                  "message": exc.motivo, "details": []}}), estado

    entrega = REGISTRO.obtener_o_crear(codigo.strip().upper(), numero)
    entrega.avanzar()
    return jsonify(entrega.snapshot())


@app.get("/")
def indice():
    """Identidad del servicio, en la linea de los otros seis."""
    return jsonify({
        "service": "library-tracking-service",
        "description": "Rastreo de entregas en tiempo real por WebSocket "
                       "para el cliente de escritorio Java.",
        "websocket": "/ws?code=LIB-MTY-<anio>-<numero>",
        "endpoints": [
            {"method": "GET", "path": "/health"},
            {"method": "GET", "path": "/api/entregas/<codigo>"},
            {"method": "GET", "path": "/mapa"},
            {"method": "WS", "path": "/ws"},
        ],
    })


@app.get("/mapa")
def mapa():
    """
    La pagina del mapa.

    Se sirve tambien por HTTP ademas de empaquetarla en el JAR para
    poder abrirla en un navegador y comprobar el mapa sin levantar la
    aplicacion Java.
    """
    return send_from_directory("static", "mapa.html")


def main():
    if config.REQUIRE_AUTH and not config.JWT_SECRET:
        log.error("REQUIRE_AUTH esta activo pero no hay JWT_SECRET_KEY: "
                  "ningun rastreo se podra autorizar. Exporta el MISMO secreto "
                  "que usan los seis microservicios.")
    if not config.REQUIRE_AUTH:
        log.warning("REQUIRE_AUTH=false: el rastreo esta ABIERTO. Solo para "
                    "demostracion local; nunca en un despliegue real.")

    threading.Thread(target=_bucle, name="simulacion", daemon=True).start()
    log.info("Servidor de rastreo en http://%s:%s  (WebSocket en /ws)",
             config.HOST, config.PORT)
    # threaded=True es obligatorio con Flask-Sock: cada WebSocket ocupa
    # un hilo mientras dure la conexion.
    app.run(host=config.HOST, port=config.PORT, debug=config.DEBUG,
            threaded=True, use_reloader=False)


if __name__ == "__main__":
    main()
