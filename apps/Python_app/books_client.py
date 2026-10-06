"""Cliente del microservicio de libros. Siempre pide JSON (?output=json).

Ojo con el parámetro: en ESTE servicio `?format=` es un filtro de
búsqueda (formato Físico/Digital/Audiolibro), de modo que la
representación se pide con `?output=json`. En los demás servicios el
parámetro es `?format=`.

Desde la entrega de Redis el cliente hereda de ApiClient, con lo que
comparte el token con los demás servicios, lo RENUEVA solo antes de que
caduque (30 min) y reintenta una vez si una escritura devuelve 401.
Las lecturas siguen siendo públicas: no mandan token.
"""
import requests

from api_client import ApiClient


def _err(resp, fallback):
    try:
        data = resp.json()
    except Exception:
        data = None
    if isinstance(data, dict) and isinstance(data.get("error"), dict):
        e = data["error"]
        msg = e.get("message") or fallback
        for d in (e.get("details") or [])[:2]:
            msg += f" — {d}"
        return msg
    return f"{fallback} (HTTP {resp.status_code})."


class BooksClient(ApiClient):
    """
    Mantiene la forma (ok, mensaje, datos) que ya usaba la interfaz, en
    lugar de la (ok, datos, error) de ApiClient: así ui_books.py no
    cambia. La diferencia está en lo de abajo — token compartido,
    renovación y reintento.
    """

    SERVICE = "Libros"

    def __init__(self, base_url, timeout=8, tokens=None, refresher=None):
        if tokens is None:
            from api_client import TokenBox
            tokens = TokenBox()
        super().__init__(base_url, tokens, timeout=timeout,
                         refresher=refresher, format_param="output")

    def set_token(self, token):
        """Compatibilidad: fija solo el token de acceso en el TokenBox
        compartido. El refresh lo administra LoginClient."""
        self.tokens.access = token or None

    def _adapt(self, resultado, fallback="No se pudieron obtener libros"):
        """(ok, datos, error) de ApiClient -> (ok, mensaje, datos)."""
        ok, data, error = resultado
        if ok:
            return True, "", data
        return False, (error.message if error else fallback), None

    def _get(self, path, params=None):
        # Las lecturas del catálogo son públicas: sin token.
        return self._adapt(self.request("GET", path, params=params, auth=False,
                                        fallback="No se pudieron obtener libros"))

    def health(self):
        try:
            r = self.session.get(f"{self.base_url}/health",
                                 params={"output": "json"}, timeout=self.timeout)
        except requests.RequestException as exc:
            return False, f"Sin conexión con {self.base_url}: {exc}", None
        try:
            data = r.json() if "json" in r.headers.get("Content-Type", "") else {}
        except Exception:
            data = {}
        if r.status_code == 200:
            # Con Redis caído, books responde 200 con status "degraded":
            # el catálogo se lee, pero las escrituras darán 503. El
            # semáforo lo pinta en amarillo (ver health_monitor).
            return True, "up", data
        msg = _err(r, "Books no disponible")
        if r.status_code == 503 and isinstance(data, dict):
            data = {"status": "error", "degraded": True,
                    "message": data.get("message", msg)}
            return False, msg, data
        return False, msg, None

    def list_books(self, limit=50, offset=0):
        return self._get("/books", {"limit": limit, "offset": offset})

    def search(self, q="", author="", genre="", title="", isbn="",
                 year="", year_min="", year_max="", price_min="", price_max=""):
        params = {}
        if q:
            params["q"] = q
        if author:
            params["author"] = author
        if genre:
            params["genre"] = genre
        if title:
            params["title"] = title
        if isbn:
            params["isbn"] = isbn
        if year:
            params["year"] = year
        if year_min:
            params["year_min"] = year_min
        if year_max:
            params["year_max"] = year_max
        if price_min:
            params["price_min"] = price_min
        if price_max:
            params["price_max"] = price_max
        return self._get("/books/search", params)

    def get(self, book_id):
        return self._get(f"/books/{book_id}")

    def get_by_isbn(self, isbn):
        """Detalle por ISBN (dependencia funcional ISBN -> libro)."""
        isbn = (isbn or "").strip()
        if not isbn:
            return False, "Escribe un ISBN para consultar.", None
        ok, msg, data = self._get(f"/books/isbn/{isbn}")
        if not ok and "404" in msg:
            return False, f"No existe ningún libro con ISBN {isbn}.", None
        return ok, msg, data

    def catalog(self, name):
        ok, msg, data = self._get(f"/{name}")
        if not ok:
            return ok, msg, []
        if isinstance(data, dict):
            for key in ("formats", "categories", "genres", "authors", "items", "data"):
                if isinstance(data.get(key), list):
                    return True, "", data[key]
            return True, "", []
        return True, "", data if isinstance(data, list) else []

    def _write(self, method, path, payload):
        """
        Escritura con token.

        ApiClient ya renueva el token si le queda poco y reintenta una
        vez ante un 401. Aquí solo se afinan los mensajes para los casos
        típicos del catálogo.
        """
        ok, data, error = self.request(method, path, json_body=payload,
                                       fallback="Operación rechazada")
        if ok:
            return True, "", data
        msg = error.message
        if error.status == 409:
            msg = f"ISBN duplicado — ya existe un libro con ese ISBN. {msg}"
        elif error.status == 404:
            msg = f"Libro inexistente — no hay libro con ese id/ISBN. {msg}"
        elif error.status == 403:
            msg = ("Tu rol no puede modificar el catálogo (hace falta "
                   f"books:write). {msg}")
        return False, msg, None

    def create(self, payload):
        return self._write("POST", "/books", payload)

    def put(self, book_id, payload):
        """Reemplazo completo: el cuerpo describe el libro entero."""
        return self._write("PUT", f"/books/{book_id}", payload)

    def patch(self, book_id, payload):
        """Cambio parcial: solo se modifica lo enviado."""
        return self._write("PATCH", f"/books/{book_id}", payload)

    def delete(self, book_id):
        ok, _data, error = self.request("DELETE", f"/books/{book_id}",
                                        fallback="No se pudo eliminar")
        if ok:
            return True, "Libro eliminado."
        msg = error.message
        if error.status == 403:
            msg = ("Tu rol no puede borrar libros (hace falta books:write). "
                   + msg)
        return False, msg

    def invalidate_cache(self):
        """
        Pide al servicio que vacíe su caché de Redis.

        Útil tras un pedido (que mueve el stock) o para una demostración.
        Exige books:write, de modo que un cliente normal recibirá 403.
        """
        ok, data, error = self.request("POST", "/cache/invalidate",
                                       fallback="No se pudo invalidar la caché")
        return (True, "", data) if ok else (False, error.message, None)


# ---- helpers de presentación ----
def _name(value):
    if isinstance(value, dict):
        return value.get("name") or ""
    return value or ""


def row_of(book):
    authors = ", ".join(a.get("name", "") for a in book.get("authors", []) if isinstance(a, dict))
    return (book.get("id", ""), book.get("isbn", ""), book.get("title", ""),
            book.get("publicationYear", ""), book.get("price", ""),
            book.get("stock", ""), _name(book.get("format")), _name(book.get("category")),
            authors)


def detail_text(book):
    lines = [f"{book.get('title','')}  (id {book.get('id','')})",
             f"ISBN: {book.get('isbn','')}  ·  Año: {book.get('publicationYear','')}  ·  "
             f"Precio: {book.get('price','')} {book.get('currency','')}  ·  Stock: {book.get('stock','')}",
             f"Formato: {_name(book.get('format'))}  ·  Categoría: {_name(book.get('category'))}",
             ""]
    lines.append("Autores: " + (", ".join(a.get("name", "") for a in book.get("authors", [])) or "—"))
    lines.append("Géneros: " + (", ".join(g.get("name", "") for g in book.get("genres", [])) or "—"))
    concepts = book.get("concepts", []) or []
    if concepts:
        lines.append("")
        lines.append("Conceptos:")
        for c in concepts:
            lines.append(f"  • {c.get('name','')} — {(c.get('definition','') or '')[:160]}")
    images = book.get("images", []) or []
    covers = [i.get("url", "") for i in images if i.get("url")]
    if covers:
        lines.append("")
        lines.append("Portada: " + covers[0])
    return "\n".join(lines)


def books_from_payload(data):
    if isinstance(data, dict):
        if isinstance(data.get("books"), list):
            return data["books"]
        if isinstance(data.get("book"), dict):
            return [data["book"]]
    if isinstance(data, list):
        return data
    return []
