"""
apps/services/pedidos/pedidos/cache.py
Cache del RASTREO PUBLICO de envios.

Solo se cachea eso. Los pedidos en si NO se cachean: llevan datos
personales e importes, cambian con cada pago y se leen poco. Cachearlos
daria un rendimiento que nadie necesita a cambio de un riesgo real de
servir el pedido de otro.

    envios:<numero de pedido>:<representacion>

El rastreo, en cambio, es consulta publica y repetitiva —una paqueteria
preguntando por el mismo numero— y se beneficia de un TTL corto.

INVALIDACION CRUZADA CON EL CATALOGO
  Crear o cancelar un pedido mueve library.books.stock, y el stock sale
  en las fichas que cachea el microservicio de libros (books:*). Hay un
  solo Redis: se invalida ahi directamente en lugar de dejar el catalogo
  anunciando unidades que ya no existen.
"""
from . import config
from .shared import store
from library_common.response_cache import ResponseCache

_cache = ResponseCache(store, "envios", (), enabled=config.CACHE_ENABLED)

BOOKS_PATTERN = ("books", "*")


def tracking_key(order_number, xml):
    return _cache.item_key(order_number, xml)


def enabled():
    return _cache.enabled()


def cached(key, ttl, producer):
    return _cache.cached(key, ttl, producer)


def invalidate_tracking(reason=""):
    """Invalida el rastreo (cambio un estado de envio)."""
    return _cache.invalidate(reason)


def invalidate_stock(reason=""):
    """
    Invalida el rastreo Y el catalogo de libros.

    Se llama cuando el pedido mueve books.stock: al crearlo (reserva) y
    al cancelarlo (devolucion).
    """
    return _cache.invalidate(reason, extra_patterns=[BOOKS_PATTERN])
