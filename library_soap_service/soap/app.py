"""
library_soap_service/soap/app.py
Microservicio Flask del catalogo de libros (library_db / esquema library).

Restricciones de la practica:
  * Flask SIN blueprints: todas las rutas se registran sobre la misma
    instancia `app` que se crea en este archivo.
  * Credenciales solo por variables de entorno (.env), nunca en el codigo.
  * CORS habilitado: el servicio se consume desde clientes de otro dominio.

Negociacion de contenido
  * ?format=xml | ?format=json  tiene prioridad
  * si no, se mira la cabecera Accept
  * si tampoco, DEFAULT_FORMAT del .env
El XML de salida sigue el diseno de apps/services/soap/library.xml.
"""
import logging

from flasgger import Swagger
from flask import Flask, Response, jsonify, request
from flask_cors import CORS
from werkzeug.exceptions import HTTPException

from . import _bootstrap  # noqa: F401  (deja library_common importable)
from . import books_repository as repo
from . import cache as book_cache
from . import config
from . import db
from . import openapi
from . import serializers
from . import clasificacion_repository as clasif_repo
from . import soap_endpoint
from .auth import current_identity, permission_required, token_required  # noqa: F401
from .errors import ApiError, ValidationError
from .payloads import read_book_payload
from .shared import store
from library_common import logging_support, metrics
from library_common.errors import ApiError as SharedApiError
from library_common.errors import DependencyUnavailable
from library_common.flask_support import metrics_payload

# Filtro de secretos en el logger raiz: ni tokens, ni contrasenas, ni la
# URL de Redis con su clave acaban en los registros.
log = logging_support.configure(
    logging.DEBUG if config.DEBUG else logging.INFO, service="books")

app = Flask(__name__)
# Mantiene el orden en que se construye el diccionario (id, isbn, title, ...)
# en lugar del alfabetico, para que el JSON se lea igual que el XML.
app.json.sort_keys = False
API = config.API_PREFIX

# ---------------------------------------------------------------------
# CORS
# El servicio es de solo datos y no usa cookies ni sesiones, por lo que
# puede abrirse a cualquier origen sin exponer credenciales del navegador
# (supports_credentials queda en False a proposito).
# ---------------------------------------------------------------------
CORS(
    app,
    resources={r"/*": {"origins": config.CORS_ORIGINS}},
    methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Accept", "Origin", "X-Requested-With", "Authorization"],
    expose_headers=["Content-Type", "Content-Length", "X-Total-Count", "Location"],
    supports_credentials=False,
    max_age=config.CORS_MAX_AGE,
)


if config.SHARED.cors_wildcard:
    log.warning("CORS_ORIGINS='*' deja el catalogo abierto a cualquier origen: "
                "en produccion enumere los origenes de los clientes en el .env")


# ---------------------------------------------------------------------
# Metricas por peticion (las publica GET /metrics)
# ---------------------------------------------------------------------
@app.before_request
def _metrics_start():
    import time
    request.environ["library.started_at"] = time.perf_counter()


@app.after_request
def _metrics_end(response):
    import time
    started = request.environ.get("library.started_at")
    if started is not None:
        metrics.observe(f"http.{request.method.lower()}",
                        (time.perf_counter() - started) * 1000.0)
    metrics.incr("http.requests")
    metrics.incr(f"http.status.{response.status_code // 100}xx")
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    return response


# ---------------------------------------------------------------------
# Documentacion Swagger / OpenAPI
#
#   /openapi.json   el documento OpenAPI 3.0.3 (soap/openapi.py)
#   /docs           Swagger UI, con "Try it out" sobre este mismo servicio
#
# Flasgger sirve los archivos de Swagger UI desde el propio paquete, de
# modo que la documentacion funciona sin conexion a Internet. La
# especificacion se escribe a mano en openapi.py y se entrega ya
# construida (rule_filter descarta la introspeccion de docstrings, que
# aqui son prosa y no YAML).
# ---------------------------------------------------------------------
SWAGGER_CONFIG = {
    "openapi": "3.0.3",
    "uiversion": 3,
    "headers": [],
    "title": "Libreria en Linea — Microservicio de libros",
    "specs": [{
        "endpoint": "openapi",
        "route": "/openapi.json",
        "rule_filter": lambda rule: False,
        "model_filter": lambda tag: True,
    }],
    "static_url_path": "/docs/static",
    "swagger_ui": True,
    "specs_route": "/docs/",
}

swagger = Swagger(app, template=openapi.build_spec(), config=SWAGGER_CONFIG, merge=False)


# =====================================================================
# Negociacion de contenido
# =====================================================================
# Vocabulario del parametro de representacion. "format" tambien es un filtro
# de busqueda (el catalogo formats: Fisico, Digital, Audiolibro, Pasta dura),
# de modo que solo se interpreta como negociacion cuando su valor es una de
# estas palabras; con cualquier otro valor filtra libros. El parametro
# "output" no tiene esa ambiguedad y es el recomendado.
REPRESENTATIONS = {
    "xml": True, "application/xml": True, "text/xml": True,
    "json": False, "application/json": False,
}


def requested_representation():
    """Devuelve True/False (xml/json) si el cliente lo pidio, o None."""
    for name in ("output", "_format", "format"):
        value = (request.args.get(name) or "").strip().lower()
        if value in REPRESENTATIONS:
            return REPRESENTATIONS[value]
    return None


def wants_xml():
    explicit = requested_representation()
    if explicit is not None:
        return explicit

    accept = request.headers.get("Accept", "")
    if accept and "*/*" not in accept:
        xml_pos = min((accept.find(t) for t in ("application/xml", "text/xml")
                       if t in accept), default=-1)
        json_pos = accept.find("application/json")
        if xml_pos >= 0 and (json_pos < 0 or xml_pos < json_pos):
            return True
        if json_pos >= 0:
            return False
    return config.DEFAULT_FORMAT == "xml"


def respond(payload, element, status=200, headers=None):
    """Emite el mismo recurso como XML o como JSON, segun lo pedido."""
    if wants_xml():
        response = Response(serializers.to_xml_bytes(element),
                            status=status, mimetype="application/xml")
    else:
        response = jsonify(payload)
        response.status_code = status
    for key, value in (headers or {}).items():
        response.headers[key] = value
    return response


def _pagination():
    def positive(name, default, maximum=None):
        raw = request.args.get(name)
        if raw is None or raw == "":
            return default
        try:
            value = int(raw)
        except ValueError:
            raise ValidationError(f"El parametro '{name}' debe ser un entero.")
        if value < 0:
            raise ValidationError(f"El parametro '{name}' no puede ser negativo.")
        return min(value, maximum) if maximum else value

    limit = positive("limit", config.DEFAULT_LIMIT, config.MAX_LIMIT)
    offset = positive("offset", 0)
    return max(limit, 1), offset


FILTER_KEYS = ("q", "title", "isbn", "author", "genre", "concept", "category",
               "format", "year", "year_min", "year_max", "price_min", "price_max",
               "stock_min", "stock_max", "in_stock")


def _filters():
    filters = {k: v for k, v in request.args.items() if k in FILTER_KEYS and v != ""}
    # ?format=xml pide una representacion, no un formato de libro.
    if filters.get("format", "").strip().lower() in REPRESENTATIONS:
        filters.pop("format")
    return filters


def _books_response(status=200, headers=None):
    """Listado/busqueda: comparten filtros, orden y paginacion."""
    limit, offset = _pagination()
    filters = _filters()
    rows, total = repo.list_books(
        filters,
        sort=request.args.get("sort", "id"),
        order=request.args.get("order", "asc"),
        limit=limit, offset=offset)

    payload = serializers.collection_to_dict(rows, total, limit, offset, filters)
    element = serializers.library_element(rows, total, limit, offset)
    all_headers = {"X-Total-Count": str(total)}
    all_headers.update(headers or {})
    return respond(payload, element, status=status, headers=all_headers)


def _cached_books_response():
    """
    Listado con cache en Redis (clave books:list:<representacion>:<filtros>).

    Si Redis acierta, PostgreSQL no se toca. Si Redis falla o no esta, se
    consulta la base igual: el cache es opcional para las lecturas.
    """
    key = book_cache.list_key(wants_xml())
    hit = book_cache.get(key)
    if hit is not None:
        return hit
    return book_cache.put(key, _books_response(), config.CACHE_TTL)


def _single_book_response(row, status=200, headers=None):
    return respond({"book": serializers.book_to_dict(row)},
                   serializers.book_element(row), status=status, headers=headers)


# =====================================================================
# Rutas: servicio
# =====================================================================
@app.get("/")
def index():
    payload = {
        "service": "library-books-service",
        "description": "Microservicio Flask de operaciones CRUD sobre los libros "
                       "de library_db (esquema library).",
        "version": config.XML_VERSION,
        "formats": ["application/json", "application/xml"],
        "xmlNamespace": config.XML_NAMESPACE,
        "documentation": {"swaggerUi": "/docs", "openapi": "/openapi.json"},
        "endpoints": [
            {"method": "GET", "path": "/health", "description": "Estado del servicio, de PostgreSQL y de Redis"},
            {"method": "GET", "path": "/metrics", "description": "Contadores del proceso y cache de Redis"},
            {"method": "POST", "path": f"{API}/cache/invalidate", "description": "Invalidar el cache del catalogo (requiere books:write)"},
            {"method": "GET", "path": "/docs", "description": "Documentacion interactiva (Swagger UI)"},
            {"method": "GET", "path": "/openapi.json", "description": "Especificacion OpenAPI 3.0.3"},
            {"method": "GET", "path": f"{API}/books", "description": "Todos los libros (admite filtros, orden y paginacion)"},
            {"method": "GET", "path": f"{API}/books/search", "description": "Busqueda por atributos"},
            {"method": "GET", "path": f"{API}/books/<id>", "description": "Un libro por id"},
            {"method": "GET", "path": f"{API}/books/isbn/<isbn>", "description": "Un libro por ISBN"},
            {"method": "POST", "path": f"{API}/books", "description": "Alta de un libro"},
            {"method": "PUT", "path": f"{API}/books/<id>", "description": "Modificar: reemplazo completo"},
            {"method": "PATCH", "path": f"{API}/books/<id>", "description": "Actualizar: cambio parcial"},
            {"method": "DELETE", "path": f"{API}/books/<id>", "description": "Baja de un libro"},
            {"method": "GET", "path": f"{API}/formats", "description": "Catalogo de formatos"},
            {"method": "GET", "path": f"{API}/categories", "description": "Catalogo de categorias"},
            {"method": "GET", "path": f"{API}/genres", "description": "Catalogo de generos"},
            {"method": "GET", "path": f"{API}/authors", "description": "Catalogo de autores"},
            {"method": "GET", "path": f"{API}/concepts", "description": "Catalogo de conceptos"},
            {"method": "GET", "path": f"{API}/cloud-concepts",
             "description": "Conceptos clasificados por modelo de nube (IaaS/PaaS/SaaS/FaaS) con su libro"},
            {"method": "POST", "path": config.SOAP_ENDPOINT_PATH,
             "description": "Modulo SOAP 1.1 de clasificacion en la nube (ver wsdl/library-classiffier.wsdl)"},
        ],
        "filters": list(FILTER_KEYS),
        "sort": sorted(repo.SORTABLE),
    }
    return respond(payload, serializers.dict_element("service", payload))


@app.get("/health")
def health():
    """
    Estado del servicio y de sus dependencias.

    PostgreSQL caido es un 503: sin base no hay catalogo.
    Redis caido es DEGRADADO, no caido: las lecturas siguen funcionando
    (solo pierden el cache), pero las escrituras devolveran 503 porque
    no se puede comprobar la revocacion de tokens. El semaforo de las
    aplicaciones de escritorio lo pinta en amarillo.
    """
    warnings = config.warnings()
    redis_block = store.health()
    redis_ok = redis_block.get("status") == "ok"
    if not redis_ok and config.redis_configured():
        warnings.append("Redis no responde: las lecturas siguen (sin cache), "
                        "pero las escrituras devolveran 503 porque no se puede "
                        "comprobar la revocacion de tokens.")
    try:
        info = db.ping()
        payload = {"status": "ok" if redis_ok else "degraded",
                   "database": info["db"], "user": info["usr"],
                   "schema": config.PGSCHEMA,
                   "server": info["version"].split(" on ")[0],
                   "jwt": "ok" if config.jwt_configured() else "missing_secret",
                   "redis": redis_block,
                   "cache": {"enabled": book_cache.enabled(),
                             "listTtl": config.CACHE_TTL,
                             "detailTtl": config.CACHE_DETAIL_TTL}}
        # 200 aunque Redis este caido: el catalogo se puede leer igual.
        status = 200
    except Exception as exc:                       # noqa: BLE001 - se reporta al cliente
        payload = {"status": "error", "database": config.PGDATABASE,
                   "message": str(exc).strip(), "redis": redis_block}
        status = 503
    if warnings:
        payload["warnings"] = warnings
    return respond(payload, serializers.dict_element("health", payload), status=status)


@app.get("/metrics")
def service_metrics():
    """
    Contadores del proceso y estado del servidor Redis.

    Lo util aqui es la pareja redis.cache.hit / redis.cache.miss: dice si
    el cache esta sirviendo de algo. redis.cache.degraded cuenta las
    veces que Redis fallo y la peticion siguio contra PostgreSQL.
    """
    payload = metrics_payload("library-books-service", store, {
        "cache": {"enabled": book_cache.enabled(),
                  "listTtl": config.CACHE_TTL,
                  "detailTtl": config.CACHE_DETAIL_TTL},
    })
    return respond(payload, serializers.dict_element("metrics", payload))


# =====================================================================
# Rutas: libros  (CRUD)
# =====================================================================
@app.get(f"{API}/books")
def list_books():
    """
    Todos los libros. Los mismos filtros que /books/search.

    Lectura PUBLICA (no exige token) y CACHEADA en Redis con TTL corto.
    La cabecera X-Cache dice si la respuesta vino de Redis (HIT) o de
    PostgreSQL (MISS).
    """
    return _cached_books_response()


@app.get(f"{API}/books/search")
def search_books():
    """Busqueda por atributos: titulo, autor, genero, concepto, precio, etc."""
    return _cached_books_response()


@app.get(f"{API}/books/<int:book_id>")
def get_book(book_id):
    """Un libro por su id, con autores, generos, conceptos e imagenes."""
    key = book_cache.id_key(book_id, wants_xml())
    hit = book_cache.get(key)
    if hit is not None:
        return hit
    return book_cache.put(key, _single_book_response(repo.get_book(book_id)),
                          config.CACHE_DETAIL_TTL)


@app.get(f"{API}/books/isbn/<path:isbn>")
def get_book_by_isbn(isbn):
    """
    Un libro por su ISBN (dependencia funcional ISBN -> libro).

    Cacheado con la clave books:<isbn> que pide el enunciado.
    """
    isbn = isbn.strip()
    key = book_cache.isbn_key(isbn, wants_xml())
    hit = book_cache.get(key)
    if hit is not None:
        return hit
    return book_cache.put(key, _single_book_response(repo.get_book_by_isbn(isbn)),
                          config.CACHE_DETAIL_TTL)


# =====================================================================
# Escrituras
#
# Todas exigen Authorization: Bearer <JWT> Y el permiso "books:write"
# del rol (admin y staff lo tienen; un cliente, no):
#     401  token ausente, invalido, caducado o revocado
#     403  token valido pero el rol no tiene books:write
#     503  Redis caido y no se puede comprobar la revocacion
#
# Y todas INVALIDAN el cache del catalogo al terminar, antes de
# responder: la siguiente lectura no puede ver datos viejos.
# =====================================================================
@app.post(f"{API}/books")
@permission_required("books:write")
def create_book():
    """Alta de un libro. Acepta el cuerpo en JSON o en XML. Requiere JWT."""
    data = read_book_payload(request, partial=False)
    row = repo.create_book(data)
    book_cache.invalidate(f"POST /books id={row['id']}")
    return _single_book_response(row, status=201,
                                 headers={"Location": f"{API}/books/{row['id']}"})


@app.put(f"{API}/books/<int:book_id>")
@permission_required("books:write")
def replace_book(book_id):
    """Modificar un libro: el cuerpo describe el libro completo. Requiere JWT."""
    data = read_book_payload(request, partial=False)
    row = repo.update_book(book_id, data, replace=True)
    book_cache.invalidate(f"PUT /books/{book_id}")
    return _single_book_response(row)


@app.patch(f"{API}/books/<int:book_id>")
@permission_required("books:write")
def update_book(book_id):
    """Actualizar un libro: solo cambian los campos enviados. Requiere JWT."""
    data = read_book_payload(request, partial=True)
    row = repo.update_book(book_id, data, replace=False)
    book_cache.invalidate(f"PATCH /books/{book_id}")
    return _single_book_response(row)


@app.delete(f"{API}/books/<int:book_id>")
@permission_required("books:write")
def delete_book(book_id):
    """Borrar un libro (las tablas hijas caen por ON DELETE CASCADE). Requiere JWT."""
    deleted = repo.delete_book(book_id)
    book_cache.invalidate(f"DELETE /books/{book_id}")
    payload = {"deleted": True, "id": deleted["id"], "isbn": deleted["isbn"],
               "title": deleted["title"]}
    return respond(payload, serializers.dict_element("deleted", payload))


@app.post(f"{API}/cache/invalidate")
@permission_required("books:write")
def invalidate_cache():
    """
    Invalida a mano el cache del catalogo.

    Existe por dos motivos concretos: para que PEDIDOS y PAGOS puedan
    avisar cuando mueven books.stock (lo hacen por SQL, en su propia
    transaccion, y el catalogo cacheado se quedaria con el stock viejo),
    y para poder vaciarlo durante una demostracion sin reiniciar nada.
    """
    removed = book_cache.invalidate("POST /cache/invalidate")
    payload = {"invalidated": True, "keysRemoved": removed,
               "cacheEnabled": book_cache.enabled()}
    return respond(payload, serializers.dict_element("cache", payload))


# =====================================================================
# Rutas: catalogos de apoyo
# =====================================================================
def _catalog_response(table, item_tag):
    rows = repo.list_catalog(table)
    payload = {"count": len(rows),
               table: [{"ref": r["id"], "name": r["name"]} for r in rows]}
    return respond(payload, serializers.catalog_element(table, item_tag, rows))


@app.get(f"{API}/formats")
def list_formats():
    return _catalog_response("formats", "format")


@app.get(f"{API}/categories")
def list_categories():
    return _catalog_response("categories", "category")


@app.get(f"{API}/genres")
def list_genres():
    return _catalog_response("genres", "genre")


@app.get(f"{API}/authors")
def list_authors():
    return _catalog_response("authors", "author")


@app.get(f"{API}/concepts")
def list_concepts():
    return _catalog_response("concepts", "concept")


# =====================================================================
# Ruta: conceptos de computo en la nube
#
# Devuelve los conceptos ya clasificados en un modelo de servicio (IaaS,
# PaaS, SaaS, FaaS) junto con el libro completo en el que estan
# definidos. Los datos los alimenta el modulo SOAP de clasificacion
# (POST /soap/clasificacion, tabla clasificaciones_cloud); este endpoint
# es la cara de LECTURA de esa informacion para clientes que hablan
# JSON/XML en vez de SOAP.
#
# Los cuatro modelos aparecen SIEMPRE, con count="0" si aun no tienen
# clasificaciones, para que la forma de la respuesta no dependa de los
# datos -- mismo criterio que sp_estadisticas_por_modelo. "N/A" es la
# excepcion: solo sale si hay filas, porque no es un modelo de nube sino
# la marca de "este concepto no es de la nube".
# =====================================================================
@app.get(f"{API}/cloud-concepts")
def list_cloud_concepts():
    limit, offset = _pagination()
    modelo = (request.args.get("model") or "").strip() or None
    rows, total = clasif_repo.conceptos_cloud(modelo, limite=limit, offset=offset)

    # Un solo viaje a la base por todos los libros implicados, en lugar de
    # uno por clasificacion (ver books_repository.get_books_by_ids).
    books = repo.get_books_by_ids([row["libro_id"] for row in rows])

    # Se siembran primero los modelos que deben salir aunque no tengan
    # filas (los cuatro, o solo el pedido si se filtro), y despues se
    # agregan los que aparezcan en los datos -- "N/A", en la practica.
    semilla = [modelo] if modelo else list(clasif_repo.MODELOS_CLOUD)
    agrupado = {m: [] for m in semilla}
    for row in rows:
        agrupado.setdefault(row["modelo_cloud"], [])
    for row in rows:
        agrupado[row["modelo_cloud"]].append((row, books.get(row["libro_id"])))

    orden = {m: i for i, m in enumerate(clasif_repo.MODELOS_SERVICIO_VALIDOS)}
    groups = sorted(agrupado.items(), key=lambda kv: orden.get(kv[0], len(orden)))

    filters = {"model": modelo} if modelo else {}
    payload = serializers.cloud_concepts_to_dict(groups, total, limit, offset, filters)
    element = serializers.cloud_concepts_element(groups, total, limit, offset)
    return respond(payload, element, headers={"X-Total-Count": str(total)})


# =====================================================================
# Ruta: modulo SOAP de clasificacion
# Unico punto que no negocia JSON/XML: SOAP 1.1 siempre responde XML.
# Ver wsdl/library-classiffier.wsdl y soap_endpoint.py.
# =====================================================================
@app.post(config.SOAP_ENDPOINT_PATH)
def soap_clasificacion():
    xml_bytes, status = soap_endpoint.handle_request(request.get_data())
    return Response(xml_bytes, status=status, mimetype="text/xml")


# =====================================================================
# Manejo de errores: una sola forma de responder, en JSON o en XML
# =====================================================================
def _error_response(status, code, message, details=None):
    payload = {"error": {"status": status, "code": code, "message": message,
                         "details": details or []}}
    element = serializers.error_element(status, code, message, details)
    return respond(payload, element, status=status)


@app.errorhandler(ApiError)
def handle_api_error(exc):
    return _error_response(exc.status, exc.code, exc.message, exc.details)


@app.errorhandler(SharedApiError)
def handle_shared_api_error(exc):
    """
    Errores del paquete compartido: 401 de token ausente, invalido,
    caducado o revocado; 403 de rol sin permiso. Misma forma de respuesta
    (XML o JSON) que el resto del servicio.
    """
    if exc.status >= 500:
        log.error("%s: %s", exc.code, exc.message)
    return _error_response(exc.status, exc.code, exc.message, exc.details)


@app.errorhandler(DependencyUnavailable)
def handle_dependency_down(exc):
    """
    Redis caido durante la comprobacion de revocacion de un token. Es un
    fallo SEGURO: antes que aceptar una credencial que quiza fue
    retirada, se responde 503. Las LECTURAS no pasan por aqui.
    """
    log.error("Dependencia no disponible (%s): %s", exc.code, exc.message)
    return _error_response(exc.status, exc.code, exc.message, exc.details)


@app.errorhandler(db.DatabaseUnavailable)
def handle_db_down(exc):
    # El texto de psycopg y usuario@host:puerto/db van al registro, no al
    # cliente: ahi es donde los busca quien opera el servicio.
    log.error("PostgreSQL no disponible (%s@%s:%s/%s): %s - revise PGHOST/PGPORT/"
              "PGUSER/PGPASSWORD en soap/.env", config.PGUSER, config.PGHOST,
              config.PGPORT, config.PGDATABASE, exc)
    return _error_response(
        503, "database_unavailable",
        "No hay conexion con PostgreSQL.",
        ["La base de datos no responde. Reintente en unos segundos; "
         "el detalle tecnico queda en el registro del servicio."])


@app.errorhandler(HTTPException)
def handle_http_error(exc):
    code = {404: "not_found", 405: "method_not_allowed",
            415: "unsupported_media_type"}.get(exc.code, "http_error")
    return _error_response(exc.code, code, exc.description or exc.name)


@app.errorhandler(Exception)
def handle_unexpected(exc):
    log.exception("Error no controlado")
    details = [f"{type(exc).__name__}: {exc}"] if config.DEBUG else []
    return _error_response(500, "internal_error",
                           "Error interno del microservicio.", details)


if __name__ == "__main__":
    log.info("Libros -> http://%s:%s%s/books", config.HOST, config.PORT, API)
    log.info("SOAP clasificacion -> http://%s:%s%s", config.HOST, config.PORT, config.SOAP_ENDPOINT_PATH)
    log.info("Swagger UI -> http://%s:%s/docs", config.HOST, config.PORT)
    log.info("PostgreSQL -> %s@%s:%s/%s (esquema %s)",
             config.PGUSER, config.PGHOST, config.PGPORT, config.PGDATABASE, config.PGSCHEMA)
    from library_common.env import redacted
    log.info("Redis -> %s (cache %ss listados / %ss fichas)",
             redacted(config.REDIS_URL) or "SIN CONFIGURAR",
             config.CACHE_TTL, config.CACHE_DETAIL_TTL)
    log.info("CORS origins -> %s", ", ".join(config.CORS_ORIGINS))
    for item in config.warnings():
        log.warning(item)
    app.run(host=config.HOST, port=config.PORT, debug=config.DEBUG)
