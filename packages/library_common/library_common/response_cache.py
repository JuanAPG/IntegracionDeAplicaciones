"""
packages/library_common/library_common/response_cache.py
Cache de respuestas HTTP en Redis, compartido por los servicios que
sirven lecturas publicas (libros, autores, rastreo de envios).

QUE SE GUARDA
    El CUERPO YA SERIALIZADO, no las filas de la base. Dos razones:
      * el mismo recurso se sirve en XML y en JSON, y cada uno necesita
        su propio cuerpo: la representacion forma parte de la clave;
      * guardar filas obligaria a volver a serializar Decimal y fechas en
        cada acierto, que es justo el trabajo que se quiere evitar.

CLAVES
    <prefijo>:list:<representacion>:<huella de los filtros>
    <prefijo>:<id>:<representacion>

POLITICA DE FALLO
    Redis es OPCIONAL aqui. Cualquier fallo se trata como ausencia de
    cache y la peticion sigue contra PostgreSQL; el cliente no se entera.
    Esto NO aplica a sesiones, revocacion ni autorizacion, que fallan de
    forma segura (ver redis_store.RedisStore).

TTL CORTO ademas de la invalidacion explicita: si una invalidacion se
pierde porque Redis estaba caido en ese momento, la entrada caduca sola
en segundos. El TTL es la red de seguridad, no el mecanismo principal.
"""
import hashlib
import logging

from flask import Response, request

log = logging.getLogger("library.cache")

# Mas de esto no se cachea: una pagina enorme no deberia desplazar al
# resto de las entradas.
MAX_BODY_BYTES = 512 * 1024


class ResponseCache:
    """
    store      RedisStore compartido.
    prefix     primer segmento de la clave ("books", "authors", ...).
    relevant   parametros de consulta que cambian el cuerpo y por tanto
               forman parte de la identidad de la entrada.
    enabled    permite apagar el cache por configuracion sin tocar codigo.
    """

    def __init__(self, store, prefix, relevant=(), enabled=True):
        self.store = store
        self.prefix = prefix
        self.relevant = tuple(relevant)
        self._enabled = bool(enabled)

    # -----------------------------------------------------------------
    # Claves
    # -----------------------------------------------------------------
    def fingerprint(self):
        """
        Huella estable de los filtros de la peticion.

        Los parametros se ORDENAN para que ?a=1&b=2 y ?b=2&a=1 caigan en
        la misma entrada. Si la cadena sale larga, se resume con SHA-256
        para no fabricar claves enormes en Redis.
        """
        pairs = sorted((name, request.args.get(name, ""))
                       for name in self.relevant
                       if request.args.get(name, "") != "")
        if not pairs:
            return "all"
        raw = "&".join(f"{name}={value}" for name, value in pairs)
        if len(raw) <= 120:
            return raw
        return "h:" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]

    @staticmethod
    def _repr(xml):
        return "xml" if xml else "json"

    def list_key(self, xml):
        return self.store.key(self.prefix, "list", self._repr(xml), self.fingerprint())

    def item_key(self, item_id, xml, kind=None):
        parts = [self.prefix]
        if kind:
            parts.append(kind)
        parts.extend([str(item_id).strip().lower(), self._repr(xml)])
        return self.store.key(*parts)

    # -----------------------------------------------------------------
    # Lectura y escritura
    # -----------------------------------------------------------------
    def enabled(self):
        return self._enabled and self.store.configured

    def get(self, key):
        """La entrada cacheada como Response, o None si no hay."""
        if not self.enabled():
            return None
        entry = self.store.cache_get(key)
        if not isinstance(entry, dict) or "body" not in entry:
            return None
        response = Response(entry["body"], status=entry.get("status", 200),
                            mimetype=entry.get("mimetype", "application/json"))
        for name, value in (entry.get("headers") or {}).items():
            response.headers[name] = value
        # X-Cache deja ver si la respuesta vino de Redis o de PostgreSQL:
        # sin esto, un cache es imposible de depurar desde fuera.
        response.headers["X-Cache"] = "HIT"
        return response

    def put(self, key, response, ttl, keep_headers=("X-Total-Count",)):
        """Guarda una respuesta exitosa. Nunca lanza; devuelve la respuesta."""
        if not self.enabled() or response.status_code != 200:
            return response
        body = response.get_data(as_text=True)
        if len(body) > MAX_BODY_BYTES:
            response.headers["X-Cache"] = "BYPASS"
            return response
        entry = {
            "body": body,
            "status": response.status_code,
            "mimetype": response.mimetype,
            "headers": {name: response.headers[name] for name in keep_headers
                        if name in response.headers},
        }
        self.store.cache_set(key, entry, ttl)
        response.headers["X-Cache"] = "MISS"
        return response

    def cached(self, key, ttl, producer):
        """Atajo: devuelve el acierto, o produce la respuesta y la guarda."""
        hit = self.get(key)
        if hit is not None:
            return hit
        return self.put(key, producer(), ttl)

    # -----------------------------------------------------------------
    # Invalidacion
    # -----------------------------------------------------------------
    def invalidate(self, reason="", extra_patterns=()):
        """
        Borra TODO el cache de este prefijo, mas los patrones extra.

        Se invalida en bloque y no clave por clave porque un recurso
        aparece en un numero indeterminado de listados (cada combinacion
        de filtros, orden y pagina es una entrada): averiguar cuales le
        afectan costaria mas que rehacerlas, y estos recursos se leen
        mucho mas de lo que se escriben.

        `extra_patterns` sirve para invalidar el cache de OTRO servicio
        que comparte el mismo Redis. Por ejemplo, renombrar un autor
        cambia el cuerpo de los libros, cuyo cache lo llena el
        microservicio de libros: hay un solo Redis, de modo que se
        invalida directamente en lugar de dejar datos viejos a la vista.
        """
        if not self.store.configured:
            return 0
        patterns = [self.store.key(self.prefix, "*")]
        patterns.extend(self.store.key(*p) if isinstance(p, tuple) else p
                        for p in extra_patterns)
        removed = self.store.invalidate(*patterns)
        if reason:
            log.info("Cache '%s' invalidado (%s): %s clave(s)",
                     self.prefix, reason, removed)
        return removed
