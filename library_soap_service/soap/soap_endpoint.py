"""
library_soap_service/soap/soap_endpoint.py
Endpoint SOAP 1.1 (document/literal) del modulo de clasificacion en la
nube. Implementa el contrato de wsdl/library-classiffier.wsdl:

    ObtenerConceptosPendientes, RegistrarClasificacion, ObtenerProgresoUsuario,
    ObtenerEstadisticasPorModelo (protegida con WS-Security, ver mas abajo)

Disenio
  * xml.etree.ElementTree para leer Y construir el XML: nunca se arma un
    sobre a mano con f-strings/concatenacion, asi que un valor con "<",
    "&" o comillas queda escapado por ElementTree al serializar, no por
    disciplina del programador.
  * Envelope, Header y Body se tratan como tres cosas distintas:
      - Header es OPCIONAL y no forma parte del contrato de negocio; solo
        se usa para un bloque <ClienteInfo> (tipo_cliente/identificador)
        con el que el cliente de escritorio se identifica ante
        clientes_servidos. Si no viene, la operacion de negocio igual
        se atiende.
      - Body es OBLIGATORIO y contiene exactamente el elemento de la
        operacion pedida.
  * Namespaces: todo se busca calificado con la URI real (via
    "{namespace}localname"), nunca por texto plano ni por el prefijo que
    haya elegido el cliente (soap:, soapenv:, s: son todos validos si
    apuntan a la URI correcta).

Diseno de errores (SOAP Fault)
  Todo fallo se responde como <soap:Fault> con informacion suficiente
  para que el cliente distinga, sin adivinar por el texto, entre error
  de entrada, conflicto y error interno. Cada Fault lleva:
    - faultcode:   soap:Client | soap:Client.Validacion |
                   soap:Client.Conflicto | soap:Server
    - faultstring: mensaje legible (nunca stack trace, SQL, password ni
                   rutas de servidor)
    - detail/ErrorDetalle: categoria + codigo (para logica de cliente) y
                   mensaje (redundante con faultstring, por si el
                   binding del cliente solo expone <detail>)

  | Caso                                    | categoria  | codigo                | HTTP |
  |------------------------------------------|-----------|------------------------|------|
  | XML mal formado / <Body> vacio / op.     | CLIENTE    | xml_invalido,          | 400  |
  |   desconocida (fallo de PROTOCOLO)       |            | body_vacio,            |      |
  |                                           |            | operacion_desconocida  |      |
  | Campo obligatorio ausente o de tipo      | VALIDACION | campo_obligatorio,     | 400  |
  |   invalido                               |            | tipo_invalido          |      |
  | Modelo distinto de IaaS/PaaS/SaaS/FaaS/  | VALIDACION | modelo_invalido        | 400  |
  |   N/A                                    |            |                        |      |
  | Libro o concepto inexistente             | CLIENTE    | libro_inexistente,     | 404  |
  |                                           |            | concepto_inexistente   |      |
  | Clasificacion duplicada                  | CONFLICTO  | clasificacion_duplicada| 409  |
  | WS-Security ausente o credenciales        | AUTENTICACION | credenciales_ausentes,| 401 |
  |   invalidas (solo ObtenerEstadisticasPorModelo)|      | credenciales_invalidas |     |
  | Falla de PostgreSQL / error no controlado| SERVIDOR   | base_datos_no_disponible,| 500|
  |                                           |            | error_interno          |      |

  Las dos primeras filas se detectan ANTES de tocar la base (parseo del
  sobre y lectura de campos), asi que un XML invalido nunca ejecuta SQL.
  Los tres casos de negocio (modelo, libro/concepto, duplicado) los
  resuelve sp_registrar_clasificacion (soap_module.sql) dentro de la
  misma transaccion atomica; clasificacion_repository.py traduce su
  resultado a ValidationError/NotFound/Conflict (errors.py, la misma
  jerarquia que ya usa la API REST/XML), y este modulo las traduce a
  Fault. Nunca se expone al cliente un stack trace, la contrasena de
  PostgreSQL, una ruta del servidor ni el texto de una consulta SQL: eso
  solo se registra en el log (ver _fault_response y los manejadores de
  db.DatabaseUnavailable / Exception en handle_request).

WS-Security (ObtenerEstadisticasPorModelo)
  Unica operacion protegida: exige un wsse:UsernameToken (perfil
  PasswordText de WS-Security 1.0) dentro de soap:Header. La contrasena
  SIEMPRE viaja como parametro enlazado hacia
  sp_verificar_credencial_soap (soap_module.sql), que la compara contra
  un hash bcrypt (pgcrypto) sin que esta capa la vea en claro en ningun
  otro punto; nunca se registra en el log ni aparece en un Fault. Sin
  header, sin UsernameToken, o con credenciales que no verifican ->
  Unauthorized (errors.py) -> Fault categoria AUTENTICACION, HTTP 401,
  antes de ejecutar la consulta de estadisticas.

  PasswordText manda la contrasena en texto plano dentro del XML (no en
  claro por la red si el endpoint esta detras de HTTPS/TLS, que es
  obligatorio en produccion para esta operacion); es el perfil minimo
  de WS-Security 1.0 y el apropiado para un ejercicio academico. Un
  perfil PasswordDigest evitaria ademas eso, a costa de sincronizar
  nonce+timestamp entre cliente y servidor -- fuera de alcance aqui.
"""
import logging
from xml.etree import ElementTree

import clasificacion_repository as repo
import config
import db
from errors import ApiError, Conflict, NotFound, Unauthorized, ValidationError

log = logging.getLogger("library.soap.clasificacion")

SOAP_NS = "http://schemas.xmlsoap.org/soap/envelope/"
TNS = config.CLASIFICACION_NAMESPACE
# Namespace estandar de WS-Security UsernameToken Profile 1.0 (OASIS).
# No se importa el XSD completo (innecesario para el alcance del
# ejercicio): solo se leen los dos elementos que interesan,
# wsse:Username y wsse:Password, calificados con esta URI.
WSSE_NS = "http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-secext-1.0.xsd"

ElementTree.register_namespace("soap", SOAP_NS)
ElementTree.register_namespace("clv", TNS)
ElementTree.register_namespace("wsse", WSSE_NS)

# categoria -> prefijo de faultcode y estado HTTP por omision. SOAP
# 1.1 admite subcodigos con notacion de punto bajo Client/Server (p.ej.
# "Client.Validacion"); se usan para que el faultcode por si solo ya
# distinga los cinco casos sin tener que leer <detail>.
_FAULTCODE = {
    "CLIENTE": "soap:Client",
    "VALIDACION": "soap:Client.Validacion",
    "CONFLICTO": "soap:Client.Conflicto",
    "AUTENTICACION": "soap:Client.Autenticacion",
    "SERVIDOR": "soap:Server",
}


def _q(ns, local):
    return f"{{{ns}}}{local}"


def _local_name(tag):
    return tag.split("}", 1)[1] if "}" in tag else tag


class SoapFault(Exception):
    """
    Fallo de PROTOCOLO: el sobre SOAP en si no es valido (XML mal
    formado, falta <Body>, operacion desconocida). Distinto de los
    errores de negocio (errors.ValidationError/NotFound/Conflict), que
    se generan una vez que ya se sabe que el sobre es valido.
    """

    def __init__(self, message, code="error_protocolo", ayuda=None):
        super().__init__(message)
        self.message = message
        self.code = code
        self.ayuda = ayuda  # info segura y no sensible (p.ej. lista de operaciones validas)


# ---------------------------------------------------------------------
# Lectura: Envelope / Header / Body y los campos de cada operacion
# ---------------------------------------------------------------------
def _parse_envelope(raw_body):
    try:
        root = ElementTree.fromstring(raw_body)
    except ElementTree.ParseError as exc:
        raise SoapFault(f"XML mal formado: {exc}", code="xml_invalido") from exc

    if root.tag != _q(SOAP_NS, "Envelope"):
        raise SoapFault(
            f"La raiz del documento debe ser soap:Envelope ({SOAP_NS}).",
            code="xml_invalido")

    header = root.find(_q(SOAP_NS, "Header"))
    body = root.find(_q(SOAP_NS, "Body"))
    if body is None:
        raise SoapFault("El sobre SOAP no tiene <soap:Body>.", code="body_vacio")

    return header, body


def _find_text(parent, local_tag, required=True, default=None):
    """
    Busca un hijo calificado con el namespace del contrato; si el cliente
    no lo namespaceo (documento invalido pero comun en pruebas manuales),
    cae a buscarlo sin calificar antes de darlo por ausente.
    """
    elem = parent.find(_q(TNS, local_tag))
    if elem is None:
        elem = parent.find(local_tag)
    text = elem.text.strip() if elem is not None and elem.text else None
    if not text:
        if required:
            raise ValidationError(f"Falta el campo obligatorio '{local_tag}'.",
                                  code="campo_obligatorio")
        return default
    return text


def _find_int(parent, local_tag, required=True, default=None):
    raw = _find_text(parent, local_tag, required=required, default=None)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ValidationError(
            f"El campo '{local_tag}' debe ser un entero, se recibio '{raw}'.",
            code="tipo_invalido") from exc


def _read_cliente_info(header):
    """
    Bloque opcional <clv:ClienteInfo><tipo_cliente/><identificador/></...>
    dentro de soap:Header. No forma parte de ninguna operacion de negocio:
    solo alimenta clientes_servidos para metricas de uso por app cliente.
    """
    if header is None:
        return None
    info = header.find(_q(TNS, "ClienteInfo"))
    if info is None:
        info = header.find("ClienteInfo")
    if info is None:
        return None
    tipo = _find_text(info, "tipo_cliente", required=False)
    identificador = _find_text(info, "identificador", required=False)
    if not tipo or not identificador:
        return None
    return tipo, identificador


def _leer_credenciales_wsse(header):
    """
    Extrae usuario/contrasena de un wsse:UsernameToken (perfil
    PasswordText) dentro de soap:Header. Lanza Unauthorized -- nunca
    devuelve credenciales parciales -- si falta el header, el bloque
    Security, el token, o si usuario/contrasena vienen vacios. NO
    verifica la contrasena aqui: eso lo hace
    clasificacion_repository.verificar_credencial_soap contra el hash
    en PostgreSQL; esta funcion solo se asegura de que algo se recibio.
    """
    if header is not None:
        security = header.find(_q(WSSE_NS, "Security"))
        token = security.find(_q(WSSE_NS, "UsernameToken")) if security is not None else None
        if token is not None:
            username_el = token.find(_q(WSSE_NS, "Username"))
            password_el = token.find(_q(WSSE_NS, "Password"))
            username = username_el.text.strip() if username_el is not None and username_el.text else ""
            password = password_el.text.strip() if password_el is not None and password_el.text else ""
            if username and password:
                return username, password

    raise Unauthorized(
        "Esta operacion requiere autenticacion WS-Security: un "
        "wsse:UsernameToken con Username y Password dentro de soap:Header.",
        code="credenciales_ausentes")


# ---------------------------------------------------------------------
# Construccion de la respuesta
# ---------------------------------------------------------------------
def _envelope_with_body(*body_children):
    envelope = ElementTree.Element(_q(SOAP_NS, "Envelope"))
    ElementTree.SubElement(envelope, _q(SOAP_NS, "Header"))
    body = ElementTree.SubElement(envelope, _q(SOAP_NS, "Body"))
    for child in body_children:
        body.append(child)
    return envelope


def _to_xml_bytes(envelope):
    return b'<?xml version="1.0" encoding="UTF-8"?>\n' + ElementTree.tostring(envelope, encoding="UTF-8")


def _fault_response(categoria, codigo, mensaje, http_status, ayuda=None):
    """
    Construye el <soap:Fault>. mensaje SIEMPRE debe ser texto seguro para
    el cliente (nunca stack trace, contrasena, ruta de servidor o SQL):
    quien llama a esta funcion con datos de un error interno (ver
    handle_request) ya debe haber sustituido el detalle tecnico por un
    mensaje generico y haberlo registrado aparte con log.exception/error.
    """
    envelope = ElementTree.Element(_q(SOAP_NS, "Envelope"))
    ElementTree.SubElement(envelope, _q(SOAP_NS, "Header"))
    body = ElementTree.SubElement(envelope, _q(SOAP_NS, "Body"))
    fault = ElementTree.SubElement(body, _q(SOAP_NS, "Fault"))
    ElementTree.SubElement(fault, "faultcode").text = _FAULTCODE.get(categoria, "soap:Server")
    ElementTree.SubElement(fault, "faultstring").text = mensaje

    detail = ElementTree.SubElement(fault, "detail")
    error_el = ElementTree.SubElement(detail, _q(TNS, "ErrorDetalle"))
    ElementTree.SubElement(error_el, _q(TNS, "categoria")).text = categoria
    ElementTree.SubElement(error_el, _q(TNS, "codigo")).text = codigo or "desconocido"
    ElementTree.SubElement(error_el, _q(TNS, "mensaje")).text = mensaje
    if ayuda:
        ElementTree.SubElement(error_el, _q(TNS, "ayuda")).text = ayuda

    log.info("SOAP Fault categoria=%s codigo=%s http=%s: %s", categoria, codigo, http_status, mensaje)
    return _to_xml_bytes(envelope), http_status


# categoria de Fault segun la excepcion de negocio (errors.py) atrapada.
_CATEGORIA_POR_EXCEPCION = (
    (Unauthorized, "AUTENTICACION"),
    (Conflict, "CONFLICTO"),
    (NotFound, "CLIENTE"),
    (ValidationError, "VALIDACION"),
)


def _fault_from_api_error(exc):
    categoria = next((c for cls, c in _CATEGORIA_POR_EXCEPCION if isinstance(exc, cls)), "CLIENTE")
    return _fault_response(categoria, exc.code, exc.message, exc.status)


# ---------------------------------------------------------------------
# Operaciones
# ---------------------------------------------------------------------
def _op_obtener_conceptos_pendientes(request_el, header):
    email = _find_text(request_el, "clasificador_email")
    limite = _find_int(request_el, "limite", required=False,
                       default=config.CLASIFICACION_DEFAULT_LIMIT)
    if limite <= 0:
        raise ValidationError("El campo 'limite' debe ser mayor que cero.", code="tipo_invalido")
    limite = min(limite, config.CLASIFICACION_MAX_LIMIT)

    pendientes = repo.conceptos_pendientes(email, limite)

    response = ElementTree.Element(_q(TNS, "ObtenerConceptosPendientesResponse"))
    for item in pendientes:
        concepto_el = ElementTree.SubElement(response, _q(TNS, "concepto"))
        for field in ("referencia_libro", "referencia_concepto", "titulo_libro",
                     "nombre_categoria", "nombre_concepto"):
            ElementTree.SubElement(concepto_el, _q(TNS, field)).text = item[field]
    return response


def _op_registrar_clasificacion(request_el, header):
    email = _find_text(request_el, "clasificador_email")
    isbn = _find_text(request_el, "referencia_libro")
    concepto = _find_text(request_el, "referencia_concepto")
    modelo = _find_text(request_el, "modelo_servicio")

    # Lanza ValidationError/NotFound/Conflict si algo falla; ver la tabla
    # de casos en el docstring del modulo.
    mensaje = repo.registrar_clasificacion(email, isbn, concepto, modelo)

    response = ElementTree.Element(_q(TNS, "RegistrarClasificacionResponse"))
    ElementTree.SubElement(response, _q(TNS, "exito")).text = "true"
    ElementTree.SubElement(response, _q(TNS, "mensaje")).text = mensaje
    return response


def _op_obtener_progreso_usuario(request_el, header):
    email = _find_text(request_el, "clasificador_email")
    total_clasificados, total_pendientes = repo.progreso_usuario(email)

    response = ElementTree.Element(_q(TNS, "ObtenerProgresoUsuarioResponse"))
    ElementTree.SubElement(response, _q(TNS, "total_clasificados")).text = str(total_clasificados)
    ElementTree.SubElement(response, _q(TNS, "total_pendientes")).text = str(total_pendientes)
    return response


_MODELOS_ESTADISTICA = ("IaaS", "PaaS", "SaaS", "FaaS")


def _op_obtener_estadisticas_por_modelo(request_el, header):
    # Sin parametros de entrada: request_el no se lee. Se autentica
    # ANTES de tocar la base -- credenciales invalidas nunca llegan a
    # ejecutar la consulta de estadisticas.
    username, password = _leer_credenciales_wsse(header)
    if not repo.verificar_credencial_soap(username, password):
        raise Unauthorized("Usuario o contrasena invalidos.", code="credenciales_invalidas")

    conteos = repo.estadisticas_por_modelo()

    response = ElementTree.Element(_q(TNS, "ObtenerEstadisticasPorModeloResponse"))
    for modelo in _MODELOS_ESTADISTICA:
        item = ElementTree.SubElement(response, _q(TNS, "estadistica"))
        ElementTree.SubElement(item, _q(TNS, "modelo_servicio")).text = modelo
        ElementTree.SubElement(item, _q(TNS, "total")).text = str(conteos.get(modelo, 0))
    return response


# El WSDL envuelve cada operacion en un elemento "<Operacion>Request"
# (patron document/literal "wrapped"); tambien se acepta el nombre de la
# operacion sin el sufijo, como en el ejemplo conceptual del enunciado
# (<RegistrarClasificacion> a secas dentro de <soap:Body>).
_OPERATIONS = {
    "ObtenerConceptosPendientes": _op_obtener_conceptos_pendientes,
    "RegistrarClasificacion": _op_registrar_clasificacion,
    "ObtenerProgresoUsuario": _op_obtener_progreso_usuario,
    "ObtenerEstadisticasPorModelo": _op_obtener_estadisticas_por_modelo,
}


def _operation_name(local_tag):
    return local_tag[:-len("Request")] if local_tag.endswith("Request") else local_tag


# ---------------------------------------------------------------------
# Punto de entrada: lo llama la ruta Flask POST /soap/clasificacion
# ---------------------------------------------------------------------
def handle_request(raw_body):
    """Devuelve (xml_bytes, http_status)."""
    try:
        header, body = _parse_envelope(raw_body)

        cliente_info = _read_cliente_info(header)
        if cliente_info:
            tipo_cliente, identificador = cliente_info
            try:
                repo.registrar_cliente_servido(tipo_cliente, identificador)
            except Exception:                                    # noqa: BLE001
                log.warning("No se pudo registrar clientes_servidos", exc_info=True)

        children = [c for c in body if isinstance(c.tag, str)]  # descarta comentarios/PIs
        if not children:
            raise SoapFault("<soap:Body> esta vacio: falta el elemento de la operacion.",
                            code="body_vacio")
        request_el = children[0]

        op_name = _operation_name(_local_name(request_el.tag))
        handler = _OPERATIONS.get(op_name)
        if handler is None:
            raise SoapFault(
                f"Operacion desconocida: '{op_name}'.", code="operacion_desconocida",
                ayuda=f"Operaciones validas: {', '.join(_OPERATIONS)}.")

        response_el = handler(request_el, header)
        envelope = _envelope_with_body(response_el)
        return _to_xml_bytes(envelope), 200

    except SoapFault as fault:
        # Fallo de protocolo: el XML nunca llego a tocar la base (ver
        # _parse_envelope, que corre antes que cualquier repo.*).
        return _fault_response("CLIENTE", fault.code, fault.message, 400, fault.ayuda)

    except ApiError as exc:
        # Errores de negocio (campo invalido, modelo invalido, libro o
        # concepto inexistente, clasificacion duplicada): exc.message ya
        # es texto seguro para el cliente, exc.status trae 400/404/409.
        return _fault_from_api_error(exc)

    except db.DatabaseUnavailable as exc:
        # El detalle de conexion (host, puerto, motivo) SOLO va al log;
        # el cliente recibe un mensaje generico, sin credenciales ni rutas.
        log.error("PostgreSQL no disponible: %s", exc)
        return _fault_response("SERVIDOR", "base_datos_no_disponible",
                               "No hay conexion con la base de datos.", 500)

    except Exception:                                              # noqa: BLE001
        # Cualquier otra falla no prevista (incluye errores de
        # PostgreSQL que no capturo la funcion almacenada). El stack
        # trace completo queda SOLO en el log; el cliente recibe un
        # mensaje generico, nunca la excepcion original.
        log.exception("Error no controlado en el endpoint SOAP")
        return _fault_response("SERVIDOR", "error_interno",
                               "Error interno del servicio.", 500)
