"""
soap/books_repository.py
Todo el SQL del servicio. Modelo normalizado de data/schema.sql
(esquema "library" de PostgreSQL).

Un libro se lee siempre completo: los atributos escalares salen de books y
las dependencias multivaluadas (autores, generos, conceptos, imagenes) se
agregan con json_agg en subconsultas, de modo que una fila = un libro y no
hace falta desduplicar en Python.
"""
import psycopg2
from psycopg2 import errorcodes

import db
from errors import Conflict, NotFound, ValidationError

# ---------------------------------------------------------------------
# SELECT base
# ---------------------------------------------------------------------
BOOK_COLUMNS = """
    b.id,
    b.isbn,
    b.title,
    b.publication_year,
    b.price,
    b.stock,
    b.format_id,
    f.name  AS format_name,
    b.category_id,
    c.name  AS category_name,
    b.created_at,
    b.updated_at,
    COALESCE((
        SELECT json_agg(json_build_object('id', a.id, 'name', a.name) ORDER BY a.name)
        FROM book_authors ba
        JOIN authors a ON a.id = ba.author_id
        WHERE ba.book_id = b.id
    ), '[]'::json) AS authors,
    COALESCE((
        SELECT json_agg(json_build_object('id', g.id, 'name', g.name) ORDER BY g.name)
        FROM book_genres bg
        JOIN genres g ON g.id = bg.genre_id
        WHERE bg.book_id = b.id
    ), '[]'::json) AS genres,
    COALESCE((
        SELECT json_agg(json_build_object('id', k.id, 'name', k.name,
                                          'definition', bk.definition) ORDER BY k.name)
        FROM book_concepts bk
        JOIN concepts k ON k.id = bk.concept_id
        WHERE bk.book_id = b.id
    ), '[]'::json) AS concepts,
    COALESCE((
        SELECT json_agg(json_build_object('id', i.id, 'url', i.url,
                                          'is_cover', i.is_cover)
                        ORDER BY i.is_cover DESC, i.id)
        FROM book_images i
        WHERE i.book_id = b.id
    ), '[]'::json) AS images
"""

FROM_BOOKS = """
    FROM books b
    JOIN formats    f ON f.id = b.format_id
    JOIN categories c ON c.id = b.category_id
"""

SORTABLE = {
    "id": "b.id",
    "isbn": "b.isbn",
    "title": "b.title",
    "year": "b.publication_year",
    "publication_year": "b.publication_year",
    "price": "b.price",
    "stock": "b.stock",
    "created_at": "b.created_at",
    "updated_at": "b.updated_at",
}


# ---------------------------------------------------------------------
# Filtros de busqueda por atributos
# ---------------------------------------------------------------------
def build_filters(params):
    """
    Traduce los parametros de consulta a (condiciones SQL, valores).
    Todo valor viaja como parametro: nunca se concatena en el SQL.
    """
    where, values = [], []

    def like(value):
        return f"%{value.strip()}%"

    def number(value, field):
        try:
            return float(value)
        except (TypeError, ValueError):
            raise ValidationError(f"El parametro '{field}' debe ser numerico.")

    def integer(value, field):
        try:
            return int(value)
        except (TypeError, ValueError):
            raise ValidationError(f"El parametro '{field}' debe ser un entero.")

    q = params.get("q")
    if q:
        where.append("""(
            b.title ILIKE %s OR b.isbn ILIKE %s
            OR EXISTS (SELECT 1 FROM book_authors ba JOIN authors a ON a.id = ba.author_id
                       WHERE ba.book_id = b.id AND a.name ILIKE %s)
        )""")
        values.extend([like(q), like(q), like(q)])

    if params.get("title"):
        where.append("b.title ILIKE %s")
        values.append(like(params["title"]))

    if params.get("isbn"):
        where.append("b.isbn ILIKE %s")
        values.append(like(params["isbn"]))

    if params.get("author"):
        where.append("""EXISTS (SELECT 1 FROM book_authors ba JOIN authors a ON a.id = ba.author_id
                                WHERE ba.book_id = b.id AND a.name ILIKE %s)""")
        values.append(like(params["author"]))

    if params.get("genre"):
        where.append("""EXISTS (SELECT 1 FROM book_genres bg JOIN genres g ON g.id = bg.genre_id
                                WHERE bg.book_id = b.id AND g.name ILIKE %s)""")
        values.append(like(params["genre"]))

    if params.get("concept"):
        where.append("""EXISTS (SELECT 1 FROM book_concepts bk JOIN concepts k ON k.id = bk.concept_id
                                WHERE bk.book_id = b.id AND k.name ILIKE %s)""")
        values.append(like(params["concept"]))

    for field, column, name_column in (("category", "b.category_id", "c.name"),
                                       ("format", "b.format_id", "f.name")):
        value = params.get(field)
        if value:
            if str(value).isdigit():
                where.append(f"{column} = %s")
                values.append(int(value))
            else:
                where.append(f"{name_column} ILIKE %s")
                values.append(like(value))

    if params.get("year"):
        where.append("b.publication_year = %s")
        values.append(integer(params["year"], "year"))
    if params.get("year_min"):
        where.append("b.publication_year >= %s")
        values.append(integer(params["year_min"], "year_min"))
    if params.get("year_max"):
        where.append("b.publication_year <= %s")
        values.append(integer(params["year_max"], "year_max"))

    if params.get("price_min"):
        where.append("b.price >= %s")
        values.append(number(params["price_min"], "price_min"))
    if params.get("price_max"):
        where.append("b.price <= %s")
        values.append(number(params["price_max"], "price_max"))

    if params.get("stock_min"):
        where.append("b.stock >= %s")
        values.append(integer(params["stock_min"], "stock_min"))
    if params.get("stock_max"):
        where.append("b.stock <= %s")
        values.append(integer(params["stock_max"], "stock_max"))

    in_stock = params.get("in_stock")
    if in_stock is not None and str(in_stock).lower() in ("1", "true", "yes", "si"):
        where.append("b.stock > 0")

    return where, values


def build_order(sort, order):
    column = SORTABLE.get((sort or "id").lower())
    if column is None:
        raise ValidationError(
            f"El parametro 'sort' no admite '{sort}'.",
            details=[f"Valores validos: {', '.join(sorted(SORTABLE))}."])
    direction = "DESC" if (order or "asc").lower() in ("desc", "descending") else "ASC"
    # column y direction provienen de listas blancas, nunca del usuario.
    return f"ORDER BY {column} {direction}, b.id ASC"


# ---------------------------------------------------------------------
# Lectura
# ---------------------------------------------------------------------
def list_books(params, sort="id", order="asc", limit=50, offset=0):
    where, values = build_filters(params)
    clause = ("WHERE " + " AND ".join(where)) if where else ""
    order_by = build_order(sort, order)

    with db.cursor() as cur:
        cur.execute(f"SELECT COUNT(*) AS total {FROM_BOOKS} {clause}", values)
        total = cur.fetchone()["total"]
        cur.execute(
            f"SELECT {BOOK_COLUMNS} {FROM_BOOKS} {clause} {order_by} LIMIT %s OFFSET %s",
            values + [limit, offset])
        rows = cur.fetchall()
    return [dict(row) for row in rows], total


def get_book(book_id):
    with db.cursor() as cur:
        cur.execute(f"SELECT {BOOK_COLUMNS} {FROM_BOOKS} WHERE b.id = %s", (book_id,))
        row = cur.fetchone()
    if row is None:
        raise NotFound(f"No existe un libro con id {book_id}.")
    return dict(row)


def get_book_by_isbn(isbn):
    with db.cursor() as cur:
        cur.execute(f"SELECT {BOOK_COLUMNS} {FROM_BOOKS} WHERE b.isbn = %s", (isbn,))
        row = cur.fetchone()
    if row is None:
        raise NotFound(f"No existe un libro con ISBN {isbn}.")
    return dict(row)


def _fetch_book(cur, book_id):
    cur.execute(f"SELECT {BOOK_COLUMNS} {FROM_BOOKS} WHERE b.id = %s", (book_id,))
    return dict(cur.fetchone())


# ---------------------------------------------------------------------
# Catalogos
# ---------------------------------------------------------------------
def list_catalog(table):
    if table not in ("formats", "categories", "genres", "authors", "concepts"):
        raise ValidationError(f"Catalogo desconocido: {table}.")
    with db.cursor() as cur:
        cur.execute(f"SELECT id, name FROM {table} ORDER BY name")  # tabla de lista blanca
        return [dict(row) for row in cur.fetchall()]


def _resolve_fixed_catalog(cur, table, value, field):
    """
    formats y categories son catalogos cerrados: el valor debe existir.
    Admite el id (4) o el nombre ('Pasta dura', sin distinguir mayusculas).
    """
    if str(value).isdigit():
        cur.execute(f"SELECT id FROM {table} WHERE id = %s", (int(value),))
    else:
        cur.execute(f"SELECT id FROM {table} WHERE lower(name) = lower(%s)", (str(value),))
    row = cur.fetchone()
    if row:
        return row["id"]

    cur.execute(f"SELECT id, name FROM {table} ORDER BY id")
    disponibles = [f"{r['id']}={r['name']}" for r in cur.fetchall()]
    raise ValidationError(
        f"El {field} '{value}' no existe en el catalogo.",
        details=[f"Valores disponibles: {', '.join(disponibles)}."])


def _resolve_or_create(cur, table, item, field):
    """
    authors, genres y concepts son catalogos abiertos: si el nombre no
    existe se da de alta, para no obligar al cliente a poblarlos antes.
    """
    if item.get("ref"):
        cur.execute(f"SELECT id FROM {table} WHERE id = %s", (item["ref"],))
        row = cur.fetchone()
        if row is None:
            raise ValidationError(f"No existe {field} con ref {item['ref']}.")
        return row["id"]

    name = item.get("name")
    if not name:
        raise ValidationError(f"Cada elemento de '{field}' necesita 'name' o 'ref'.")
    cur.execute(f"SELECT id FROM {table} WHERE lower(name) = lower(%s)", (name,))
    row = cur.fetchone()
    if row:
        return row["id"]
    cur.execute(f"INSERT INTO {table} (name) VALUES (%s) RETURNING id", (name,))
    return cur.fetchone()["id"]


# ---------------------------------------------------------------------
# Escritura de las relaciones multivaluadas
# ---------------------------------------------------------------------
def _replace_authors(cur, book_id, authors):
    cur.execute("DELETE FROM book_authors WHERE book_id = %s", (book_id,))
    for item in authors:
        author_id = _resolve_or_create(cur, "authors", item, "authors")
        cur.execute(
            "INSERT INTO book_authors (book_id, author_id) VALUES (%s, %s) "
            "ON CONFLICT DO NOTHING", (book_id, author_id))


def _replace_genres(cur, book_id, genres):
    cur.execute("DELETE FROM book_genres WHERE book_id = %s", (book_id,))
    for item in genres:
        genre_id = _resolve_or_create(cur, "genres", item, "genres")
        cur.execute(
            "INSERT INTO book_genres (book_id, genre_id) VALUES (%s, %s) "
            "ON CONFLICT DO NOTHING", (book_id, genre_id))


def _replace_concepts(cur, book_id, concepts):
    cur.execute("DELETE FROM book_concepts WHERE book_id = %s", (book_id,))
    for item in concepts:
        concept_id = _resolve_or_create(cur, "concepts", item, "concepts")
        # (book_id, concept_id) -> definition: la definicion pertenece al par.
        cur.execute(
            "INSERT INTO book_concepts (book_id, concept_id, definition) "
            "VALUES (%s, %s, %s) "
            "ON CONFLICT (book_id, concept_id) DO UPDATE SET definition = EXCLUDED.definition",
            (book_id, concept_id, item["definition"]))


def _replace_images(cur, book_id, images):
    cur.execute("DELETE FROM book_images WHERE book_id = %s", (book_id,))
    for item in images:
        cur.execute(
            "INSERT INTO book_images (book_id, url, is_cover) VALUES (%s, %s, %s)",
            (book_id, item["url"], item["is_cover"]))


def _apply_collections(cur, book_id, data):
    if "authors" in data:
        _replace_authors(cur, book_id, data["authors"])
    if "genres" in data:
        _replace_genres(cur, book_id, data["genres"])
    if "concepts" in data:
        _replace_concepts(cur, book_id, data["concepts"])
    if "images" in data:
        _replace_images(cur, book_id, data["images"])


def _translate_integrity_error(exc, isbn=None):
    code = exc.pgcode
    detail = (exc.diag.message_detail or str(exc)).strip()
    if code == errorcodes.UNIQUE_VIOLATION:
        constraint = exc.diag.constraint_name or ""
        if "isbn" in constraint or "isbn" in detail:
            return Conflict(f"Ya existe un libro con el ISBN {isbn}.", details=[detail])
        if "one_cover" in constraint:
            return Conflict("El libro ya tiene una imagen marcada como portada.",
                            details=[detail])
        return Conflict("La operacion viola una restriccion de unicidad.", details=[detail])
    if code == errorcodes.FOREIGN_KEY_VIOLATION:
        return ValidationError("Referencia inexistente en un catalogo.", details=[detail])
    if code == errorcodes.CHECK_VIOLATION:
        return ValidationError("Un valor no cumple las restricciones del esquema.",
                               details=[detail])
    if code == errorcodes.NOT_NULL_VIOLATION:
        return ValidationError("Falta un campo obligatorio.", details=[detail])
    return None


# ---------------------------------------------------------------------
# Alta / modificacion / baja
# ---------------------------------------------------------------------
def create_book(data):
    try:
        with db.cursor(commit=True) as cur:
            format_id = _resolve_fixed_catalog(cur, "formats", data["format"], "formato")
            category_id = _resolve_fixed_catalog(cur, "categories", data["category"], "categoria")
            cur.execute(
                """INSERT INTO books (isbn, title, publication_year, price, stock,
                                      format_id, category_id)
                   VALUES (%s, %s, %s, %s, %s, %s, %s)
                   RETURNING id""",
                (data["isbn"], data["title"], data["publication_year"], data["price"],
                 data.get("stock", 0), format_id, category_id))
            book_id = cur.fetchone()["id"]
            _apply_collections(cur, book_id, data)
            return _fetch_book(cur, book_id)
    except psycopg2.IntegrityError as exc:
        raise _translate_integrity_error(exc, data.get("isbn")) or exc


def update_book(book_id, data, replace=False):
    """
    replace=False (PATCH): solo se tocan los campos y colecciones enviados.
    replace=True  (PUT):   el cuerpo describe el libro completo; las cuatro
                           colecciones se sustituyen (ausente = vacia).
    """
    if replace:
        for field in ("authors", "genres", "concepts", "images"):
            data.setdefault(field, [])

    try:
        with db.cursor(commit=True) as cur:
            cur.execute("SELECT id FROM books WHERE id = %s FOR UPDATE", (book_id,))
            if cur.fetchone() is None:
                raise NotFound(f"No existe un libro con id {book_id}.")

            assignments, values = [], []
            for field, column in (("isbn", "isbn"), ("title", "title"),
                                  ("publication_year", "publication_year"),
                                  ("price", "price"), ("stock", "stock")):
                if field in data:
                    assignments.append(f"{column} = %s")
                    values.append(data[field])
            if "format" in data:
                assignments.append("format_id = %s")
                values.append(_resolve_fixed_catalog(cur, "formats", data["format"], "formato"))
            if "category" in data:
                assignments.append("category_id = %s")
                values.append(_resolve_fixed_catalog(cur, "categories", data["category"],
                                                     "categoria"))

            if assignments:
                # updated_at lo mantiene el disparador trg_books_updated_at.
                cur.execute(f"UPDATE books SET {', '.join(assignments)} WHERE id = %s",
                            values + [book_id])

            _apply_collections(cur, book_id, data)
            return _fetch_book(cur, book_id)
    except psycopg2.IntegrityError as exc:
        raise _translate_integrity_error(exc, data.get("isbn")) or exc


def delete_book(book_id):
    """
    Borra el libro. Las tablas hijas tienen ON DELETE CASCADE, de modo que
    autores, generos, conceptos e imagenes del libro se van con el.
    """
    with db.cursor(commit=True) as cur:
        cur.execute(
            "DELETE FROM books WHERE id = %s RETURNING id, isbn, title", (book_id,))
        row = cur.fetchone()
    if row is None:
        raise NotFound(f"No existe un libro con id {book_id}.")
    return dict(row)
