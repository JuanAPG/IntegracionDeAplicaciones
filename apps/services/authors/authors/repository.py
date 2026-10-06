"""
apps/services/authors/authors/repository.py
Todo el SQL del microservicio de autores.

MODELO
  library.authors        catalogo de autores (id, name UNIQUE)
  library.book_authors    relacion M:N con libros

  libro ->> autor es una dependencia MULTIVALUADA (un libro tiene muchos
  autores y un autor muchos libros): en 4FN vive en su propia tabla,
  book_authors, tal como la creo data/schema.sql. Este servicio
  administra el catalogo y ESA RELACION; los datos del libro en si son
  del microservicio de libros.

Todas las consultas usan parametros (%s). El nombre de la columna de
ordenacion sale de una lista blanca, porque un nombre de columna no
puede viajar como parametro.
"""
from .shared import database

SORTABLE = {"id": "a.id", "name": "a.name", "books": "book_count"}


def author_to_dict(row, books=None):
    """Fila de authors -> diccionario JSON en camelCase."""
    if row is None:
        return None
    payload = {
        "id": row["id"],
        "name": row["name"],
        "bookCount": row.get("book_count", 0),
    }
    if books is not None:
        payload["books"] = books
    return payload


def book_to_dict(row):
    """
    Resumen del libro visto desde el autor.

    A proposito NO es la ficha completa: el libro entero lo sirve el
    microservicio de libros (GET /books/<id>). Aqui solo lo necesario
    para saber de que obra se habla.
    """
    return {
        "id": row["id"],
        "isbn": row["isbn"],
        "title": row["title"],
        "publicationYear": row.get("publication_year"),
        "price": float(row["price"]) if row.get("price") is not None else None,
        "stock": row.get("stock"),
    }


# ---------------------------------------------------------------------
# Lectura
# ---------------------------------------------------------------------
def list_authors(filters, sort="name", order="asc", limit=50, offset=0):
    where = []
    params = []
    if filters.get("q") or filters.get("name"):
        where.append("a.name ILIKE %s")
        params.append(f"%{filters.get('q') or filters.get('name')}%")
    if filters.get("has_books") is True:
        where.append("EXISTS (SELECT 1 FROM book_authors ba WHERE ba.author_id = a.id)")
    elif filters.get("has_books") is False:
        where.append("NOT EXISTS (SELECT 1 FROM book_authors ba WHERE ba.author_id = a.id)")

    clause = (" WHERE " + " AND ".join(where)) if where else ""
    column = SORTABLE.get(sort, "a.name")
    direction = "DESC" if str(order).lower() == "desc" else "ASC"

    with database.cursor() as cur:
        cur.execute(f"SELECT count(*) AS total FROM authors a{clause}", params)
        total = cur.fetchone()["total"]
        cur.execute(
            "SELECT a.id, a.name, "
            "       (SELECT count(*) FROM book_authors ba WHERE ba.author_id = a.id) "
            "           AS book_count "
            f"  FROM authors a{clause} "
            f" ORDER BY {column} {direction}, a.id ASC LIMIT %s OFFSET %s",
            params + [limit, offset])
        return cur.fetchall(), total


def get_author(author_id):
    with database.cursor() as cur:
        cur.execute(
            "SELECT a.id, a.name, "
            "       (SELECT count(*) FROM book_authors ba WHERE ba.author_id = a.id) "
            "           AS book_count "
            "  FROM authors a WHERE a.id = %s", (author_id,))
        return cur.fetchone()


def get_by_name(name):
    with database.cursor() as cur:
        cur.execute("SELECT id, name FROM authors WHERE lower(name) = lower(%s)",
                    (name,))
        return cur.fetchone()


def books_of(author_id):
    with database.cursor() as cur:
        cur.execute(
            "SELECT b.id, b.isbn, b.title, b.publication_year, b.price, b.stock "
            "  FROM books b JOIN book_authors ba ON ba.book_id = b.id "
            " WHERE ba.author_id = %s ORDER BY b.publication_year DESC, b.title",
            (author_id,))
        return cur.fetchall()


def book_exists(book_id):
    with database.cursor() as cur:
        cur.execute("SELECT id, isbn, title FROM books WHERE id = %s", (book_id,))
        return cur.fetchone()


# ---------------------------------------------------------------------
# Escritura del catalogo
# ---------------------------------------------------------------------
def create_author(name):
    with database.cursor(commit=True) as cur:
        cur.execute("INSERT INTO authors (name) VALUES (%s) RETURNING id", (name,))
        return cur.fetchone()["id"]


def rename_author(author_id, name):
    with database.cursor(commit=True) as cur:
        cur.execute("UPDATE authors SET name = %s WHERE id = %s RETURNING id",
                    (name, author_id))
        return cur.fetchone() is not None


def delete_author(author_id):
    """
    Borra el autor. book_authors cae por ON DELETE CASCADE, de modo que
    las relaciones con sus libros desaparecen con el; app.py se encarga
    de no llamar aqui sin confirmacion explicita cuando tiene obras.
    """
    with database.cursor(commit=True) as cur:
        cur.execute("DELETE FROM authors WHERE id = %s RETURNING id, name",
                    (author_id,))
        return cur.fetchone()


# ---------------------------------------------------------------------
# Escritura de la relacion autor <-> libro
# ---------------------------------------------------------------------
def link_book(author_id, book_id):
    """Devuelve True si creo la relacion, False si ya existia."""
    with database.cursor(commit=True) as cur:
        cur.execute(
            "INSERT INTO book_authors (book_id, author_id) VALUES (%s, %s) "
            "ON CONFLICT DO NOTHING RETURNING book_id",
            (book_id, author_id))
        return cur.fetchone() is not None


def unlink_book(author_id, book_id):
    with database.cursor(commit=True) as cur:
        cur.execute(
            "DELETE FROM book_authors WHERE author_id = %s AND book_id = %s "
            "RETURNING book_id", (author_id, book_id))
        return cur.fetchone() is not None


def replace_books(author_id, book_ids):
    """
    Fija la lista COMPLETA de libros del autor, en UNA transaccion: borra
    las relaciones que no vienen e inserta las que faltan.

    Devuelve (anadidos, quitados) para poder informar lo que cambio.
    """
    deseados = sorted(set(int(b) for b in book_ids))
    with database.cursor(commit=True) as cur:
        cur.execute("SELECT book_id FROM book_authors WHERE author_id = %s",
                    (author_id,))
        actuales = {row["book_id"] for row in cur.fetchall()}
        quitar = actuales - set(deseados)
        anadir = set(deseados) - actuales
        if quitar:
            cur.execute(
                "DELETE FROM book_authors WHERE author_id = %s "
                "AND book_id = ANY(%s)", (author_id, list(quitar)))
        for book_id in sorted(anadir):
            cur.execute(
                "INSERT INTO book_authors (book_id, author_id) VALUES (%s, %s) "
                "ON CONFLICT DO NOTHING", (book_id, author_id))
        return len(anadir), len(quitar)
