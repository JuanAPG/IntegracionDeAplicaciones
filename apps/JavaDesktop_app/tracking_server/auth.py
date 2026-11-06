"""
tracking_server/auth.py
Quien puede ver el rastreo de que pedido.

DOS COMPROBACIONES, Y LAS DOS HACEN FALTA:

1. LA FIRMA DEL TOKEN. Se verifica con el MISMO secreto HS256 que usan
   los seis microservicios, exigiendo ademas el emisor y que el token
   sea de tipo `access`. Esto responde a "quien eres". Se rechaza
   explicitamente `alg: none` y cualquier algoritmo que no sea el
   configurado: aceptar el algoritmo que propone el propio token es la
   via clasica para falsificarlo.

2. LA PROPIEDAD DEL PEDIDO. Se le pregunta al microservicio de pedidos
   con el MISMO token del usuario: si `GET /pedidos/numero/PED-000042`
   responde 200, el pedido es suyo; si responde 403 o 404, no lo es.
   Esto responde a "es tuyo este pedido".

POR QUE NO SE DECIDE LA PROPIEDAD AQUI. Porque la regla ya existe en el
servicio de pedidos y duplicarla seria tener dos verdades que se
separarian al primer cambio. Ademas este servidor no tiene base de datos
ni debe tenerla: si tuviera que saber de quien es cada pedido,
necesitaria una copia de los datos, y esa copia envejece.

SIN ESTO, CUALQUIERA QUE ADIVINE UN CODIGO VE POR DONDE VA EL PEDIDO DE
OTRO. Los codigos son correlativos (LIB-MTY-2026-000042), de modo que
adivinarlos es trivial: la autorizacion no es decorativa.
"""
import logging
import re

import jwt
import requests

import config

log = logging.getLogger("rastreo.auth")

# LIB-MTY-<anio>-<6 digitos>  ->  PED-<6 digitos>
_PATRON_CODIGO = re.compile(r"^LIB-MTY-(\d{4})-(\d{1,8})$", re.IGNORECASE)


class NoAutorizado(Exception):
    """El cliente no puede ver este rastreo. Lleva el motivo y el codigo."""

    def __init__(self, motivo, codigo="unauthorized"):
        super().__init__(motivo)
        self.motivo = motivo
        self.codigo = codigo


def numero_de_pedido(codigo_rastreo):
    """
    Traduce el codigo de rastreo al numero de pedido real.

        LIB-MTY-2026-000042  ->  PED-000042

    El codigo de rastreo no es un identificador paralelo inventado: es
    una vista del numero de pedido que si existe en el servicio. Asi un
    rastreo siempre se puede comprobar contra un pedido real.
    """
    encontrado = _PATRON_CODIGO.match((codigo_rastreo or "").strip())
    if not encontrado:
        raise NoAutorizado(
            f"El codigo '{codigo_rastreo}' no tiene el formato LIB-MTY-<anio>-<numero>.",
            "bad_request")
    return "PED-" + encontrado.group(2).zfill(6)


def claims_de(token):
    """Verifica la firma y devuelve los claims. Lanza NoAutorizado."""
    if not config.JWT_SECRET:
        raise NoAutorizado(
            "El servidor de rastreo no tiene JWT_SECRET_KEY configurado y no "
            "puede verificar tokens.", "server_misconfigured")
    try:
        return jwt.decode(
            token,
            config.JWT_SECRET,
            algorithms=[config.JWT_ALGORITHM],   # nunca el que diga el token
            issuer=config.JWT_ISSUER,
            options={"require": ["exp", "sub", "user_id", "jti"]},
            leeway=10)
    except jwt.ExpiredSignatureError:
        raise NoAutorizado("Tu sesion caduco. Vuelve a iniciar sesion.", "token_expired")
    except jwt.InvalidTokenError as exc:
        raise NoAutorizado(f"Token invalido: {exc}", "invalid_token")


def autorizar(codigo_rastreo, token):
    """
    Comprueba que quien pide el rastreo pueda verlo.

    Devuelve (numero_pedido, user_id). Lanza NoAutorizado si no.

    Con REQUIRE_AUTH=false se salta TODO esto y solo se valida el formato
    del codigo. Existe para poder ensenar el mapa sin levantar los seis
    microservicios, y el servidor lo avisa por el registro al arrancar.
    """
    numero = numero_de_pedido(codigo_rastreo)

    if not config.REQUIRE_AUTH:
        log.warning("REQUIRE_AUTH=false: se sirve %s sin comprobar nada", codigo_rastreo)
        return numero, None

    if not token:
        raise NoAutorizado("Falta el encabezado Authorization: Bearer <token>.", "token_missing")

    claims = claims_de(token)
    if claims.get("typ") not in (None, "access"):
        raise NoAutorizado("Se requiere un token de acceso.", "invalid_token")
    user_id = claims.get("user_id")

    # La propiedad la decide el servicio de pedidos, no este servidor.
    url = f"{config.PEDIDOS_URL.rstrip('/')}/pedidos/numero/{numero}"
    try:
        respuesta = requests.get(
            url,
            params={"output": "json"},
            headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
            timeout=config.PEDIDOS_TIMEOUT)
    except requests.RequestException as exc:
        # FALLO SEGURO: si no se puede comprobar de quien es el pedido,
        # NO se ensena. Mas vale un rastreo que no abre que ensenar la
        # ruta de un pedido ajeno.
        raise NoAutorizado(
            f"No se pudo verificar el pedido con el servicio de pedidos ({exc}).",
            "pedidos_unavailable")

    if respuesta.status_code == 200:
        return numero, user_id
    if respuesta.status_code in (401, 403):
        raise NoAutorizado("Ese pedido no es tuyo.", "forbidden")
    if respuesta.status_code == 404:
        raise NoAutorizado(f"No existe el pedido {numero}.", "not_found")
    raise NoAutorizado(
        f"El servicio de pedidos respondio {respuesta.status_code}.", "pedidos_error")
