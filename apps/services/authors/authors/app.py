"""
apps/services/authors/authors/app.py
Microservicio Flask de AUTORES: el catalogo y su relacion con los libros
(library_db / esquema library).

Restricciones de la practica
  * Flask SIN blueprints: todas las rutas sobre la unica instancia `app`.
  * Psycopg 3; credenciales solo por variables de entorno.
  * XML y JSON (?format= / ?output= / Accept). Sin parametro, XML.
  * CORS enumerando los origenes de las aplicaciones cliente.

QUE ES PUBLICO Y QUE NO
  Las LECTURAS son publicas: quien escribio un libro es informacion de
  catalogo, la misma que ya publica GET /books. Van cacheadas en Redis
  con TTL corto.
  Las ESCRITURAS exigen Authorization: Bearer <JWT> y el permiso
  authors:write del rol:
      401  token ausente, invalido, caducado o revocado
      403  token valido pero el rol no tiene authors:write
      503  Redis caido (no se puede comprobar la revocacion)

DONDE ACABA ESTE SERVICIO
  Administra autores y la tabla book_authors. NO toca los datos del libro
  (titulo, precio, stock): eso es del microservicio de libros. Por eso la
  ficha de un autor devuelve un RESUMEN de cada obra y no el libro
  completo.
"""
import logging

from flasgger import Swagger
from flask import Flask, request
from werkzeug.exceptions import HTTPException

from . import _bootstrap  # noqa: F401
from . import cache as author_cache
from . import config
from . import openapi
from . import repository as repo
from .shared import (
    database,
    negotiator,
    optional_token,
    permission_required,
    store,
)
from library_common import logging_support, metrics
from library_common.db import is_unique_violation
from library_common.errors import Conflict, NotFound, ValidationError
from library_common.flask_support import (
    configure_cors,
    install_security_headers,
    metrics_payload,
    register_error_handlers,
    register_request_metrics,
)
from library_common.jwt_auth import current_identity

log = logging_support.configure(
    logging.DEBUG if config.DEBUG else logging.INFO, service="authors")

app = Flask(__name__)
app.json.sort_keys = False
API = config.API_PREFIX

configure_cors(app, config.CORS_ORIGINS, with_credentials=False,
               max_age=config.CORS_MAX_AGE, service="authors")
install_security_headers(app)
register_request_metrics(app, "authors")

SWAGGER_CONFIG = {
    "openapi": "3.0.3",
    "uiversion": 3,
    "headers": [],
    "title": "Libreria en Linea — Microservicio de autores",
    "specs": [{"endpoint": "openapi", "route": "/openapi.json",
               "rule_filter": lambda rule: False,
               "model_filter": lambda tag: True}],
    "static_url_path": "/docs/static",
    "swagger_ui": True,
    "specs_route": "/docs/",
}
swagger = Swagger(app, template=openapi.build_spec(), config=SWAGGER_CONFIG, merge=False)

MAX_NAME = 150


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
    data = {}
    for child in root:
        if len(child):      # <books><book>1</book><book>2</book></books>
            data[_local(child.tag)] = [(g.text or "").strip() for g in child]
        else:
            data[_local(child.tag)] = (child.text or "").strip()
    if not data and root.text and root.text.strip():
        data["name"] = root.text.strip()
    return data


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


def _validate_name(raw):
    import re
    name = re.sub(r"\s+", " ", str(raw or "").strip())
    if not name:
        raise ValidationError("El nombre del autor es obligatorio.")
    if len(name) > MAX_NAME:
        raise ValidationError(
            f"El nombre del autor supera los {MAX_NAME} caracteres.")
    # library.authors.name es VARCHAR(150) UNIQUE; se admite cualquier
    # grafia de nombre propio (acentos, guiones, puntos, apostrofos) pero
    # no caracteres de control ni etiquetas.
    if re.search(r"[<>\x00-\x1f]", name):
        raise ValidationError("El nombre del autor contiene caracteres no validos.")
    return name


def _book_ids(data):
    raw = data.get("books") or data.get("bookIds") or data.get("libros") or []
    if isinstance(raw, str):
        raw = [p for p in raw.replace(",", " ").split() if p]
    if not isinstance(raw, (list, tuple)):
        raise ValidationError("'books' debe ser una lista de ids de libro.")
    ids = []
    errores = []
    for item in raw:
        try:
            ids.append(int(item if not isinstance(item, dict)
                           else item.get("id") or item.get("ref")))
        except (TypeError, ValueError):
            errores.append(f"'{item}' no es un id de libro valido.")
    if errores:
        raise ValidationError("Hay ids de libro invalidos.", errores)
    return ids


# =====================================================================
# Rutas: servicio
# =====================================================================
@app.get("/")
def index():
    payload = {
        "service": config.SERVICE_NAME,
        "description": "Microservicio Flask de autores y su relacion con los "
                       "libros de library_db (esquema library).",
        "version": config.XML_VERSION,
        "formats": ["application/xml", "application/json"],
        "defaultFormat": config.DEFAULT_FORMAT,
        "xmlNamespace": config.XML_NAMESPACE,
        "documentation": {"swaggerUi": "/docs", "openapi": "/openapi.json"},
        "authentication": {
            "scheme": "Bearer",
            "issuer": config.JWT_ISSUER,
            "note": "Las lecturas son publicas (informacion de catalogo); "
                    "las escrituras exigen el permiso authors:write.",
        },
        "endpoints": [
            {"method": "GET", "path": f"{API}/authors", "description": "Catalogo de autores (publico, cacheado)"},
            {"method": "GET", "path": f"{API}/authors/<id>", "description": "Un autor con sus obras (publico)"},
            {"method": "GET", "path": f"{API}/authors/<id>/books", "description": "Obras del autor (publico)"},
            {"method": "POST", "path": f"{API}/authors", "description": "Alta de autor (authors:write)"},
            {"method": "PUT", "path": f"{API}/authors/<id>", "description": "Renombrar autor (authors:write)"},
            {"method": "PATCH", "path": f"{API}/authors/<id>", "description": "Renombrar autor (authors:write)"},
            {"method": "DELETE", "path": f"{API}/authors/<id>", "description": "Baja de autor (authors:write)"},
            {"method": "PUT", "path": f"{API}/authors/<id>/books", "description": "Fijar las obras del autor (authors:write)"},
            {"method": "POST", "path": f"{API}/authors/<id>/books/<bookId>", "description": "Vincular una obra (authors:write)"},
            {"method": "DELETE", "path": f"{API}/authors/<id>/books/<bookId>", "description": "Desvincular una obra (authors:write)"},
            {"method": "GET", "path": "/health", "description": "Estado del servicio, PostgreSQL y Redis"},
            {"method": "GET", "path": "/metrics", "description": "Contadores del proceso y cache de Redis"},
        ],
    }
    return negotiator.dict_response("service", payload)


@app.get("/health")
def health():
    """
    Estado del servicio.

    PostgreSQL caido -> 503: sin base no hay catalogo.
    Redis caido -> DEGRADADO con 200: las lecturas publicas siguen
    funcionando (solo pierden el cache); las escrituras devolveran 503
    porque no se puede comprobar la revocacion de tokens.
    """
    warnings = config.warnings()
    redis_block = store.health()
    redis_ok = redis_block.get("status") == "ok"
    if not redis_ok and config.redis_configured():
        warnings.append("Redis no responde: las lecturas siguen (sin cache), "
                        "pero las escrituras devolveran 503 porque no se puede "
                        "comprobar la revocacion de tokens.")
    db_ok, db_block = database.health()

    payload = dict(db_block)
    payload["status"] = "ok" if (db_ok and redis_ok) else ("error" if not db_ok
                                                           else "degraded")
    payload["jwt"] = "ok" if config.jwt_configured() else "missing_secret"
    payload["redis"] = redis_block
    payload["cache"] = {"enabled": author_cache.enabled(),
                        "listTtl": config.CACHE_TTL,
                        "detailTtl": config.CACHE_DETAIL_TTL}
    if warnings:
        payload["warnings"] = warnings
    return negotiator.dict_response("health", payload, status=200 if db_ok else 503)


@app.get("/metrics")
def service_metrics():
    payload = metrics_payload(config.SERVICE_NAME, store, {
        "cache": {"enabled": author_cache.enabled(),
                  "listTtl": config.CACHE_TTL,
                  "detailTtl": config.CACHE_DETAIL_TTL},
    })
    return negotiator.dict_response("metrics", payload)


# =====================================================================
# Rutas: lectura del catalogo (publicas y cacheadas)
# =====================================================================
def _list_response():
    limit, offset = _pagination()
    filters = {}
    if request.args.get("q") or request.args.get("name"):
        filters["q"] = (request.args.get("q") or request.args.get("name")).strip()
    if request.args.get("has_books") not in (None, ""):
        raw = request.args["has_books"].strip().lower()
        if raw in ("1", "true", "si", "yes"):
            filters["has_books"] = True
        elif raw in ("0", "false", "no"):
            filters["has_books"] = False
        else:
            raise ValidationError("El parametro 'has_books' debe ser true o false.")

    rows, total = repo.list_authors(filters, sort=request.args.get("sort", "name"),
                                    order=request.args.get("order", "asc"),
                                    limit=limit, offset=offset)
    autores = [repo.author_to_dict(row) for row in rows]
    payload = {"count": len(autores), "total": total, "limit": limit,
               "offset": offset, "filters": filters, "authors": autores}
    return negotiator.collection_response(
        "authors", "author", autores, payload,
        total=total, limit=limit, offset=offset,
        headers={"X-Total-Count": str(total)})


@app.get(f"{API}/authors")
@optional_token
def list_authors():
    """
    Catalogo de autores con filtros, orden y paginacion.

    Lectura PUBLICA y CACHEADA (authors:list:...). Si viene un token, se
    verifica de verdad —un token invalido sigue siendo 401— pero no hace
    falta para leer.
    """
    key = author_cache.list_key(negotiator.wants_xml())
    return author_cache.cached(key, config.CACHE_TTL, _list_response)


@app.get(f"{API}/authors/<int:author_id>")
@optional_token
def get_author(author_id):
    """Un autor con el RESUMEN de sus obras. Publico y cacheado."""
    def producer():
        row = repo.get_author(author_id)
        if row is None:
            raise NotFound(f"No existe el autor {author_id}.")
        libros = [repo.book_to_dict(b) for b in repo.books_of(author_id)]
        return negotiator.dict_response("author",
                                        repo.author_to_dict(row, books=libros))

    return author_cache.cached(
        author_cache.item_key(author_id, negotiator.wants_xml()),
        config.CACHE_DETAIL_TTL, producer)


@app.get(f"{API}/authors/<int:author_id>/books")
@optional_token
def list_author_books(author_id):
    """
    Obras del autor.

    Es un RESUMEN (id, isbn, titulo, ano, precio, stock), no la ficha
    completa: esa la sirve GET /books/<id> del microservicio de libros,
    que es su dueno.
    """
    def producer():
        row = repo.get_author(author_id)
        if row is None:
            raise NotFound(f"No existe el autor {author_id}.")
        libros = [repo.book_to_dict(b) for b in repo.books_of(author_id)]
        payload = {"author": {"id": row["id"], "name": row["name"]},
                   "count": len(libros), "books": libros}
        return negotiator.collection_response(
            "books", "book", libros, payload, total=len(libros),
            headers={"X-Total-Count": str(len(libros))})

    return author_cache.cached(
        author_cache.item_key(author_id, negotiator.wants_xml(), kind="books"),
        config.CACHE_DETAIL_TTL, producer)


# =====================================================================
# Rutas: escritura (Bearer + authors:write)
# =====================================================================
@app.post(f"{API}/authors")
@permission_required("authors:write")
def create_author():
    """Alta de un autor. El nombre es unico en library.authors."""
    data = read_payload()
    name = _validate_name(_pick(data, "name", "nombre"))

    existente = repo.get_by_name(name)
    if existente is not None:
        raise Conflict(f"Ya existe el autor '{existente['name']}'.",
                       [f"Su id es {existente['id']}."])
    try:
        author_id = repo.create_author(name)
    except Exception as exc:                           # noqa: BLE001
        if is_unique_violation(exc):
            raise Conflict(f"Ya existe el autor '{name}'.") from exc
        raise

    libros = _book_ids(data)
    vinculados = 0
    if libros:
        faltan = [b for b in libros if repo.book_exists(b) is None]
        if faltan:
            raise ValidationError(
                "Hay libros que no existen.",
                [f"Ids inexistentes: {', '.join(str(b) for b in faltan)}."])
        vinculados, _ = repo.replace_books(author_id, libros)

    author_cache.invalidate(f"POST /authors id={author_id}")
    metrics.incr("authors.created")
    log.info("Autor creado id=%s por user_id=%s", author_id,
             current_identity().user_id)
    payload = repo.author_to_dict(repo.get_author(author_id))
    payload["booksLinked"] = vinculados
    return negotiator.dict_response("author", payload, status=201,
                                    headers={"Location": f"{API}/authors/{author_id}"})


@app.put(f"{API}/authors/<int:author_id>")
@app.patch(f"{API}/authors/<int:author_id>")
@permission_required("authors:write")
def update_author(author_id):
    """
    Renombra el autor.

    PUT y PATCH hacen lo mismo porque el autor tiene un solo campo
    editable (el nombre): no hay diferencia posible entre "reemplazo
    completo" y "cambio parcial", y fingirla seria peor que decirlo.
    Para cambiar sus obras esta PUT /authors/<id>/books.
    """
    if repo.get_author(author_id) is None:
        raise NotFound(f"No existe el autor {author_id}.")
    data = read_payload()
    name = _validate_name(_pick(data, "name", "nombre"))

    choque = repo.get_by_name(name)
    if choque is not None and choque["id"] != author_id:
        raise Conflict(f"Ya existe otro autor con el nombre '{name}'.",
                       [f"Su id es {choque['id']}."])
    try:
        repo.rename_author(author_id, name)
    except Exception as exc:                           # noqa: BLE001
        if is_unique_violation(exc):
            raise Conflict(f"Ya existe otro autor con el nombre '{name}'.") from exc
        raise

    # Renombrar al autor cambia tambien el cuerpo de sus libros, que
    # cachea el microservicio de libros: se invalidan las dos familias.
    author_cache.invalidate(f"PUT /authors/{author_id}")
    metrics.incr("authors.renamed")
    return negotiator.dict_response("author",
                                    repo.author_to_dict(repo.get_author(author_id)))


@app.delete(f"{API}/authors/<int:author_id>")
@permission_required("authors:write")
def delete_author(author_id):
    """
    Baja de un autor.

    Si tiene obras, se RECHAZA con 409 salvo que se pida
    ?force=true. Motivo: book_authors cae por ON DELETE CASCADE, de modo
    que borrar el autor dejaria sus libros sin autoria de forma
    silenciosa. Mejor obligar a confirmarlo que perder el dato sin avisar.
    """
    row = repo.get_author(author_id)
    if row is None:
        raise NotFound(f"No existe el autor {author_id}.")

    force = (request.args.get("force") or "").strip().lower() in ("1", "true", "si", "yes")
    obras = row.get("book_count") or 0
    if obras and not force:
        raise Conflict(
            f"El autor '{row['name']}' tiene {obras} obra(s) en el catalogo.",
            ["Borrarlo dejaria esos libros sin autoria (book_authors cae por "
             "ON DELETE CASCADE).",
             "Desvincule las obras primero, o repita con ?force=true si de "
             "verdad quiere borrarlo."])

    borrado = repo.delete_author(author_id)
    author_cache.invalidate(f"DELETE /authors/{author_id}")
    metrics.incr("authors.deleted")
    log.info("Autor %s borrado (obras desvinculadas=%s) por user_id=%s",
             author_id, obras, current_identity().user_id)
    payload = {"deleted": True, "id": borrado["id"], "name": borrado["name"],
               "booksUnlinked": obras}
    return negotiator.dict_response("author", payload)


@app.put(f"{API}/authors/<int:author_id>/books")
@permission_required("authors:write")
def set_author_books(author_id):
    """
    Fija la lista COMPLETA de obras del autor: lo que no venga se
    desvincula. Se hace en UNA transaccion, de modo que no existe un
    momento en el que el autor se quede sin ninguna obra.
    """
    if repo.get_author(author_id) is None:
        raise NotFound(f"No existe el autor {author_id}.")
    data = read_payload()
    libros = _book_ids(data)

    faltan = [b for b in libros if repo.book_exists(b) is None]
    if faltan:
        raise ValidationError(
            "Hay libros que no existen.",
            [f"Ids inexistentes: {', '.join(str(b) for b in faltan)}."])

    anadidos, quitados = repo.replace_books(author_id, libros)
    author_cache.invalidate(f"PUT /authors/{author_id}/books")
    metrics.incr("authors.books.replaced")
    obras = [repo.book_to_dict(b) for b in repo.books_of(author_id)]
    payload = repo.author_to_dict(repo.get_author(author_id), books=obras)
    payload["linked"] = anadidos
    payload["unlinked"] = quitados
    return negotiator.dict_response("author", payload)


@app.post(f"{API}/authors/<int:author_id>/books/<int:book_id>")
@permission_required("authors:write")
def link_book(author_id, book_id):
    """Vincula una obra al autor. Repetirlo no es un error (idempotente)."""
    if repo.get_author(author_id) is None:
        raise NotFound(f"No existe el autor {author_id}.")
    libro = repo.book_exists(book_id)
    if libro is None:
        raise NotFound(f"No existe el libro {book_id}.")

    creado = repo.link_book(author_id, book_id)
    if creado:
        author_cache.invalidate(f"POST /authors/{author_id}/books/{book_id}")
        metrics.incr("authors.books.linked")
    payload = {"linked": True, "created": creado, "authorId": author_id,
               "book": {"id": libro["id"], "isbn": libro["isbn"],
                        "title": libro["title"]},
               "alreadyLinked": not creado}
    return negotiator.dict_response("author", payload,
                                    status=201 if creado else 200)


@app.delete(f"{API}/authors/<int:author_id>/books/<int:book_id>")
@permission_required("authors:write")
def unlink_book(author_id, book_id):
    """Desvincula una obra del autor. El libro NO se borra."""
    if repo.get_author(author_id) is None:
        raise NotFound(f"No existe el autor {author_id}.")

    quitado = repo.unlink_book(author_id, book_id)
    if not quitado:
        raise NotFound(f"El libro {book_id} no estaba vinculado al autor "
                       f"{author_id}.")
    author_cache.invalidate(f"DELETE /authors/{author_id}/books/{book_id}")
    metrics.incr("authors.books.unlinked")
    payload = {"unlinked": True, "authorId": author_id, "bookId": book_id,
               "note": "Solo se quito la autoria; el libro sigue en el catalogo."}
    return negotiator.dict_response("author", payload)


# =====================================================================
# Manejo de errores
# =====================================================================
register_error_handlers(app, negotiator, debug=config.DEBUG, service="authors")


@app.errorhandler(HTTPException)
def handle_http_error(exc):
    code = {400: "bad_request", 404: "not_found", 405: "method_not_allowed",
            415: "unsupported_media_type"}.get(exc.code, "http_error")
    return negotiator.error_response(exc.code, code, exc.description or exc.name)


if __name__ == "__main__":
    from library_common.env import redacted

    log.info("Autores -> http://%s:%s%s/authors", config.HOST, config.PORT, API)
    log.info("Swagger UI -> http://%s:%s/docs", config.HOST, config.PORT)
    log.info("PostgreSQL -> %s (esquema %s)", database.target, config.PGSCHEMA)
    log.info("Redis -> %s (cache %ss / %ss)",
             redacted(config.REDIS_URL) or "SIN CONFIGURAR",
             config.CACHE_TTL, config.CACHE_DETAIL_TTL)
    log.info("CORS origins -> %s", ", ".join(config.CORS_ORIGINS))
    for item in config.warnings():
        log.warning(item)
    app.run(host=config.HOST, port=config.PORT, debug=config.DEBUG, load_dotenv=False)
