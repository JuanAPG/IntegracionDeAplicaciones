"""
apps/services/authors/authors/cache.py
Cache de las lecturas publicas de autores.

    authors:list:<representacion>:<filtros>
    authors:<id>:<representacion>

INVALIDACION CRUZADA
  Cambiar un autor cambia tambien el cuerpo de los LIBROS, porque la
  ficha de un libro incluye sus autores y el microservicio de libros la
  cachea en books:*. Hay un solo Redis compartido, de modo que al
  escribir aqui se invalidan las dos familias de claves en lugar de
  dejar a la vista un autor con el nombre viejo durante el TTL.

  La alternativa seria llamar a POST /cache/invalidate del servicio de
  libros, pero eso acopla los dos servicios por HTTP y falla si el otro
  esta caido. El cache es estado compartido: se toca donde vive.
"""
from . import config
from .shared import store
from library_common.response_cache import ResponseCache

RELEVANT = ("q", "name", "has_books", "sort", "order", "limit", "offset")

_cache = ResponseCache(store, "authors", RELEVANT, enabled=config.CACHE_ENABLED)

# Patron del cache del microservicio de libros (mismo Redis).
BOOKS_PATTERN = ("books", "*")


def list_key(xml):
    return _cache.list_key(xml)


def item_key(author_id, xml, kind=None):
    return _cache.item_key(author_id, xml, kind=kind)


def enabled():
    return _cache.enabled()


def get(key):
    return _cache.get(key)


def put(key, response, ttl):
    return _cache.put(key, response, ttl)


def cached(key, ttl, producer):
    """Devuelve el acierto de cache, o produce la respuesta y la guarda."""
    return _cache.cached(key, ttl, producer)


def invalidate(reason=""):
    """Invalida el cache de autores Y el del catalogo de libros."""
    return _cache.invalidate(reason, extra_patterns=[BOOKS_PATTERN])
