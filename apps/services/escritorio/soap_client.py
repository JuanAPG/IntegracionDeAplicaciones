"""
apps/services/escritorio/soap_client.py
Cliente SOAP 1.1 manual (sin Spyne/zeep) para el modulo de clasificacion
en la nube de library_soap_service. Construye y lee el sobre a mano con
xml.etree.ElementTree y urllib.request de la libreria estandar: la GUI
no agrega ninguna dependencia nueva y no conoce PostgreSQL en absoluto,
solo habla HTTP/XML con la URL del servicio SOAP que el usuario
configure (ver library-classiffier.wsdl para el contrato).
"""
import urllib.error
import urllib.request
from xml.etree import ElementTree

SOAP_NS = "http://schemas.xmlsoap.org/soap/envelope/"
TNS = "urn:library:clasificacion:1.0"
# WS-Security UsernameToken Profile 1.0 (OASIS), perfil PasswordText.
# Solo se usa en ObtenerEstadisticasPorModelo (ver soap_endpoint.py).
WSSE_NS = "http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-secext-1.0.xsd"
WSSE_PASSWORD_TEXT = ("http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-"
                     "username-token-profile-1.0#PasswordText")

ElementTree.register_namespace("soap", SOAP_NS)
ElementTree.register_namespace("clv", TNS)
ElementTree.register_namespace("wsse", WSSE_NS)


def _q(ns, local):
    return f"{{{ns}}}{local}"


def _local(tag):
    return tag.split("}", 1)[1] if "}" in tag else tag


class SoapFaultError(Exception):
    """El servidor respondio con <soap:Fault>. Trae categoria/codigo/mensaje
    ya traducidos por el servicio (ver soap_endpoint.py), nunca un stack
    trace ni detalle tecnico."""

    def __init__(self, categoria, codigo, mensaje):
        super().__init__(mensaje)
        self.categoria = categoria
        self.codigo = codigo
        self.mensaje = mensaje


class SoapTransportError(Exception):
    """No hubo una respuesta SOAP valida (red, timeout, HTML de un proxy, etc.)."""


def _build_envelope(operation, fields, header=None, wsse_credentials=None):
    """
    wsse_credentials: tupla opcional (username, password). Si se da, se
    agrega un <wsse:Security><wsse:UsernameToken> a soap:Header, perfil
    PasswordText -- la contrasena viaja en texto dentro del XML (por
    eso esta operacion debe correr detras de HTTPS/TLS en produccion),
    nunca se concatena a mano: es .text de un SubElement, igual que
    cualquier otro campo, asi que se escapa igual.
    """
    envelope = ElementTree.Element(_q(SOAP_NS, "Envelope"))
    header_el = ElementTree.SubElement(envelope, _q(SOAP_NS, "Header"))
    if header:
        cliente_info = ElementTree.SubElement(header_el, _q(TNS, "ClienteInfo"))
        for key, value in header.items():
            ElementTree.SubElement(cliente_info, _q(TNS, key)).text = str(value)
    if wsse_credentials:
        username, password = wsse_credentials
        security = ElementTree.SubElement(header_el, _q(WSSE_NS, "Security"))
        token = ElementTree.SubElement(security, _q(WSSE_NS, "UsernameToken"))
        ElementTree.SubElement(token, _q(WSSE_NS, "Username")).text = username
        password_el = ElementTree.SubElement(token, _q(WSSE_NS, "Password"))
        password_el.set("Type", WSSE_PASSWORD_TEXT)
        password_el.text = password

    body = ElementTree.SubElement(envelope, _q(SOAP_NS, "Body"))
    request_el = ElementTree.SubElement(body, _q(TNS, f"{operation}Request"))
    for key, value in fields.items():
        # .text escapa < > & " al serializar: nunca se concatena XML a mano.
        ElementTree.SubElement(request_el, _q(TNS, key)).text = str(value)

    return b'<?xml version="1.0" encoding="UTF-8"?>\n' + ElementTree.tostring(envelope, encoding="UTF-8")


def _element_to_dict(element):
    """
    Convierte un elemento de respuesta en dict; si un hijo se repite
    (p.ej. <concepto> dentro de ObtenerConceptosPendientesResponse), las
    repeticiones se juntan en una lista bajo esa clave.
    """
    result = {}
    for child in element:
        key = _local(child.tag)
        value = _element_to_dict(child) if len(child) > 0 else (child.text.strip() if child.text else "")
        if key in result:
            if not isinstance(result[key], list):
                result[key] = [result[key]]
            result[key].append(value)
        else:
            result[key] = value
    return result


def call(url, operation, fields, header=None, wsse_credentials=None, timeout=10):
    """
    Ejecuta una operacion SOAP contra `url`. Devuelve un dict con la
    respuesta ya deserializada, o lanza SoapFaultError (el servidor
    entendio la peticion pero la rechazo -- incluye credenciales
    WS-Security ausentes o invalidas) o SoapTransportError (no se
    obtuvo una respuesta SOAP interpretable).
    """
    body = _build_envelope(operation, fields, header, wsse_credentials)
    request = urllib.request.Request(
        url, data=body, method="POST",
        headers={"Content-Type": "text/xml; charset=utf-8",
                "SOAPAction": f'"{TNS}#{operation}"'})

    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read()
    except urllib.error.HTTPError as exc:
        # El servicio SIEMPRE devuelve un sobre SOAP valido en el cuerpo,
        # incluso en 400/404/409/500 (ver soap_endpoint.py): se lee igual
        # que una respuesta 200 y se distingue mirando <soap:Fault>.
        raw = exc.read()
    except urllib.error.URLError as exc:
        raise SoapTransportError(
            f"No se pudo conectar con el servicio SOAP en {url}: {exc.reason}") from exc
    except TimeoutError as exc:
        raise SoapTransportError(f"El servicio SOAP no respondio a tiempo ({url}).") from exc

    try:
        root = ElementTree.fromstring(raw)
    except ElementTree.ParseError as exc:
        raise SoapTransportError(
            "El servidor no respondio con un sobre SOAP valido.") from exc

    body_el = root.find(_q(SOAP_NS, "Body"))
    if body_el is None or len(body_el) == 0:
        raise SoapTransportError("La respuesta SOAP no tiene <Body>.")

    child = body_el[0]
    if _local(child.tag) == "Fault":
        detail = child.find("detail")
        error_el = detail.find(_q(TNS, "ErrorDetalle")) if detail is not None else None
        if error_el is not None:
            data = _element_to_dict(error_el)
            raise SoapFaultError(data.get("categoria", "SERVIDOR"),
                                 data.get("codigo", "desconocido"),
                                 data.get("mensaje", "Error desconocido del servicio."))
        faultstring = child.find("faultstring")
        raise SoapFaultError("SERVIDOR", "desconocido",
                             faultstring.text if faultstring is not None else "Error desconocido.")

    return _element_to_dict(child)


# ---------------------------------------------------------------------
# Envolturas por operacion (lo unico que la GUI deberia llamar)
# ---------------------------------------------------------------------
def obtener_conceptos_pendientes(url, email, limite=10, header=None):
    data = call(url, "ObtenerConceptosPendientes",
               {"clasificador_email": email, "limite": limite}, header=header)
    conceptos = data.get("concepto", [])
    if isinstance(conceptos, dict):
        conceptos = [conceptos]
    return conceptos


def registrar_clasificacion(url, email, isbn, concepto, modelo, header=None):
    data = call(url, "RegistrarClasificacion",
               {"clasificador_email": email, "referencia_libro": isbn,
                "referencia_concepto": concepto, "modelo_servicio": modelo},
               header=header)
    return data.get("mensaje", "Clasificacion guardada exitosamente.")


def obtener_progreso_usuario(url, email, header=None):
    data = call(url, "ObtenerProgresoUsuario", {"clasificador_email": email}, header=header)
    return int(data.get("total_clasificados", 0)), int(data.get("total_pendientes", 0))


def obtener_estadisticas_por_modelo(url, username, password, header=None):
    """
    Operacion protegida con WS-Security: username/password NUNCA se
    guardan en este modulo ni se registran en ningun lado, solo viajan
    en la llamada. Devuelve {'IaaS': total, 'PaaS': total, ...}. Lanza
    SoapFaultError con categoria='AUTENTICACION' si el servidor rechaza
    las credenciales.
    """
    data = call(url, "ObtenerEstadisticasPorModelo", {}, header=header,
               wsse_credentials=(username, password))
    items = data.get("estadistica", [])
    if isinstance(items, dict):
        items = [items]
    return {item["modelo_servicio"]: int(item["total"]) for item in items}
