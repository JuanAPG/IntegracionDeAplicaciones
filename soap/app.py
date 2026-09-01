"""
soap/app.py
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

import books_repository as repo
import config
import db
import openapi
import serializers
from errors import ApiError, ValidationError
from payloads import read_book_payload

logging.basicConfig(
    level=logging.DEBUG if config.DEBUG else logging.INFO,
    format="%(asctime)s %(levelname)-7s %(message)s")
log = logging.getLogger("library.soap")

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
    allow_headers=["Content-Type", "Accept", "Origin", "X-Requested-With"],
    expose_headers=["Content-Type", "Content-Length", "X-Total-Count", "Location"],
    supports_credentials=False,
    max_age=config.CORS_MAX_AGE,
)


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
            {"method": "GET", "path": "/health", "description": "Estado del servicio y de la base de datos"},
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
        ],
        "filters": list(FILTER_KEYS),
        "sort": sorted(repo.SORTABLE),
    }
    return respond(payload, serializers.dict_element("service", payload))


@app.get("/health")
def health():
    try:
        info = db.ping()
        payload = {"status": "ok", "database": info["db"], "user": info["usr"],
                   "schema": config.PGSCHEMA,
                   "server": info["version"].split(" on ")[0]}
        status = 200
    except Exception as exc:                       # noqa: BLE001 - se reporta al cliente
        payload = {"status": "error", "database": config.PGDATABASE,
                   "message": str(exc).strip()}
        status = 503
    return respond(payload, serializers.dict_element("health", payload), status=status)


# =====================================================================
# Rutas: libros  (CRUD)
# =====================================================================
@app.get(f"{API}/books")
def list_books():
    """Todos los libros. Los mismos filtros que /books/search."""
    return _books_response()


@app.get(f"{API}/books/search")
def search_books():
    """Busqueda por atributos: titulo, autor, genero, concepto, precio, etc."""
    return _books_response()


@app.get(f"{API}/books/<int:book_id>")
def get_book(book_id):
    """Un libro por su id, con autores, generos, conceptos e imagenes."""
    return _single_book_response(repo.get_book(book_id))


@app.get(f"{API}/books/isbn/<path:isbn>")
def get_book_by_isbn(isbn):
    """Un libro por su ISBN (dependencia funcional ISBN -> libro)."""
    return _single_book_response(repo.get_book_by_isbn(isbn.strip()))


@app.post(f"{API}/books")
def create_book():
    """Alta de un libro. Acepta el cuerpo en JSON o en XML."""
    data = read_book_payload(request, partial=False)
    row = repo.create_book(data)
    return _single_book_response(row, status=201,
                                 headers={"Location": f"{API}/books/{row['id']}"})


@app.put(f"{API}/books/<int:book_id>")
def replace_book(book_id):
    """Modificar un libro: el cuerpo describe el libro completo."""
    data = read_book_payload(request, partial=False)
    return _single_book_response(repo.update_book(book_id, data, replace=True))


@app.patch(f"{API}/books/<int:book_id>")
def update_book(book_id):
    """Actualizar un libro: solo cambian los campos enviados."""
    data = read_book_payload(request, partial=True)
    return _single_book_response(repo.update_book(book_id, data, replace=False))


@app.delete(f"{API}/books/<int:book_id>")
def delete_book(book_id):
    """Borrar un libro (las tablas hijas caen por ON DELETE CASCADE)."""
    deleted = repo.delete_book(book_id)
    payload = {"deleted": True, "id": deleted["id"], "isbn": deleted["isbn"],
               "title": deleted["title"]}
    return respond(payload, serializers.dict_element("deleted", payload))


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


@app.errorhandler(db.DatabaseUnavailable)
def handle_db_down(exc):
    log.error("PostgreSQL no disponible: %s", exc)
    return _error_response(
        503, "database_unavailable",
        "No hay conexion con PostgreSQL.",
        [str(exc).strip(),
         f"Revise PGHOST/PGPORT/PGUSER/PGPASSWORD en soap/.env "
         f"(destino actual: {config.PGUSER}@{config.PGHOST}:{config.PGPORT}/{config.PGDATABASE})."])


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
    log.info("Swagger UI -> http://%s:%s/docs", config.HOST, config.PORT)
    log.info("PostgreSQL -> %s@%s:%s/%s (esquema %s)",
             config.PGUSER, config.PGHOST, config.PGPORT, config.PGDATABASE, config.PGSCHEMA)
    log.info("CORS origins -> %s", ", ".join(config.CORS_ORIGINS))
    app.run(host=config.HOST, port=config.PORT, debug=config.DEBUG)
