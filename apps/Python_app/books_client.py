"""Cliente del microservicio de libros. Siempre pide JSON (?output=json)."""
import requests


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


class BooksClient:
    def __init__(self, base_url, timeout=8):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({"Accept": "application/json"})
        self._token = None

    def set_token(self, token):
        """Fija el JWT Bearer para las escrituras (POST/PUT/PATCH/DELETE).
        Las lecturas son publicas y no lo necesitan."""
        self._token = token or None

    def _auth_headers(self):
        if self._token:
            return {"Authorization": f"Bearer {self._token}"}
        return {}

    def _get(self, path, params=None):
        p = dict(params or {})
        p.setdefault("output", "json")
        try:
            r = self.session.get(f"{self.base_url}{path}", params=p, timeout=self.timeout)
        except requests.RequestException as exc:
            return False, f"Sin conexión: {exc}", None
        if r.status_code == 200:
            try:
                return True, "", r.json()
            except Exception:
                return False, "Respuesta no válida del servicio.", None
        return False, _err(r, "No se pudieron obtener libros"), None

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
        try:
            r = self.session.request(method, f"{self.base_url}{path}",
                                     params={"output": "json"}, json=payload,
                                     headers=self._auth_headers(),
                                     timeout=self.timeout)
        except requests.RequestException as exc:
            return False, f"Servicio no disponible — sin conexión con {self.base_url}: {exc}", None
        if r.status_code in (200, 201):
            try:
                return True, "", r.json()
            except Exception:
                return True, "", {}
        msg = _err(r, "Operación rechazada")
        if r.status_code == 401:
            msg = ("Falta el token de sesión — vuelve a iniciar sesión. " + msg)
        elif r.status_code == 403:
            msg = ("Sesión sin permiso o token expirado — vuelve a iniciar sesión. " + msg)
        elif r.status_code == 409:
            msg = f"ISBN duplicado — ya existe un libro con ese ISBN. {msg}"
        elif r.status_code == 404:
            msg = f"Libro inexistente — no hay libro con ese id/ISBN. {msg}"
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
        try:
            r = self.session.delete(f"{self.base_url}/books/{book_id}",
                                    params={"output": "json"},
                                    headers=self._auth_headers(),
                                    timeout=self.timeout)
        except requests.RequestException as exc:
            return False, f"Sin conexión: {exc}"
        if r.status_code in (200, 204):
            return True, "Libro eliminado."
        msg = _err(r, "No se pudo eliminar")
        if r.status_code == 401:
            msg = "Falta el token de sesión — vuelve a iniciar sesión. " + msg
        elif r.status_code == 403:
            msg = "Sesión sin permiso o token expirado — vuelve a iniciar sesión. " + msg
        return False, msg


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
