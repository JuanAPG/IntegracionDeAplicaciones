"""
library_soap_service/soap/cache.py
Cache del catalogo de libros en Redis.

La mecanica (guardar el cuerpo serializado, huella de los filtros,
cabecera X-Cache, invalidacion por patron con SCAN + UNLINK) vive en el
paquete compartido library_common.response_cache, de modo que libros,
autores y el rastreo de envios la comparten en lugar de tener tres
copias. Aqui solo queda lo propio del catalogo.

QUE SE CACHEA
    GET /books             -> books:list:<representacion>:<filtros>
    GET /books/search      -> books:list:<representacion>:<filtros>
    GET /books/<id>        -> books:id:<id>:<representacion>
    GET /books/isbn/<isbn> -> books:<isbn>:<representacion>

CUANDO SE INVALIDA
    Despues de CUALQUIER POST, PUT, PATCH o DELETE sobre libros, y
    tambien cuando pedidos o pagos mueven books.stock (para eso existe
    POST /cache/invalidate). Una sola pasada con books:* cubre las dos
    familias de claves, listados y fichas.

Redis es OPCIONAL aqui: cualquier fallo se trata como ausencia de cache
y la peticion sigue contra PostgreSQL.
"""
from . import config
from .shared import store
from library_common.response_cache import ResponseCache

# Parametros que cambian el cuerpo de la respuesta. Los que anada un
# cliente por su cuenta no entran en la clave.
RELEVANT = ("q", "title", "isbn", "author", "genre", "concept", "category",
            "format", "year", "year_min", "year_max", "price_min", "price_max",
            "stock_min", "stock_max", "in_stock", "sort", "order",
            "limit", "offset", "model")

_cache = ResponseCache(store, "books", RELEVANT, enabled=config.CACHE_ENABLED)


def list_key(xml):
    return _cache.list_key(xml)


def isbn_key(isbn, xml):
    # La clave que pide el enunciado: books:<isbn>, mas la representacion,
    # porque el mismo libro tiene cuerpo XML y cuerpo JSON.
    return _cache.item_key(isbn, xml)


def id_key(book_id, xml):
    return _cache.item_key(book_id, xml, kind="id")


def enabled():
    return _cache.enabled()


def get(key):
    return _cache.get(key)


def put(key, response, ttl):
    return _cache.put(key, response, ttl)


def invalidate(reason=""):
    return _cache.invalidate(reason)
