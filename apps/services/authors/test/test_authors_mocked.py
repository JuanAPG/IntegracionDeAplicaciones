"""
test/test_authors_mocked.py
Pruebas del microservicio de autores SIN PostgreSQL y SIN servidor Redis.

Cubre:
  1. Lecturas publicas y cacheadas (MISS -> HIT, XML y JSON por separado).
  2. Escrituras: 401 sin token, 403 sin authors:write, 2xx con permiso.
  3. Alta, renombrado y unicidad del nombre (409).
  4. Baja: se rechaza si el autor tiene obras, salvo ?force=true.
  5. Relacion con libros: fijar la lista completa, vincular y desvincular.
  6. Cada escritura invalida el cache de autores Y el de libros.
  7. Token revocado -> 401. Redis caido -> lecturas si, escrituras 503.

Uso (desde apps/services/authors):
    python test/test_authors_mocked.py
"""
import os
import sys

os.environ.setdefault("JWT_SECRET_KEY", "secreto-jwt-de-pruebas-suficientemente-largo")
os.environ.setdefault("REDIS_URL", "redis://:prueba@localhost:6379/0")
os.environ.setdefault("DEFAULT_FORMAT", "xml")

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

import authors.shared as shared  # noqa: E402
from library_common import testing as redis_testing  # noqa: E402

FAKE = redis_testing.install(shared.store)

import authors.app as appmod  # noqa: E402
import authors.config as config  # noqa: E402
import authors.repository as repo  # noqa: E402

# ---------------------------------------------------------------------
# Base simulada
# ---------------------------------------------------------------------
AUTORES = {1: {"id": 1, "name": "Ada Lovelace"},
           2: {"id": 2, "name": "Alan Turing"}}
LIBROS = {
    10: {"id": 10, "isbn": "978-607-11-1111-1", "title": "Notas sobre la maquina",
         "publication_year": 1843, "price": 499.0, "stock": 5},
    11: {"id": 11, "isbn": "978-607-11-2222-2", "title": "Computing Machinery",
         "publication_year": 1950, "price": 599.0, "stock": 3},
    12: {"id": 12, "isbn": "978-607-11-3333-3", "title": "On Computable Numbers",
         "publication_year": 1936, "price": 699.0, "stock": 0},
}
RELACION = {(1, 10)}          # (author_id, book_id)
SIGUIENTE = {"id": 3}
VIAJES = {"list": 0, "get": 0}


def fake_list_authors(filters, sort="name", order="asc", limit=50, offset=0):
    VIAJES["list"] += 1
    filas = []
    for a in AUTORES.values():
        n = sum(1 for (aid, _b) in RELACION if aid == a["id"])
        if filters.get("q") and filters["q"].lower() not in a["name"].lower():
            continue
        if filters.get("has_books") is True and n == 0:
            continue
        if filters.get("has_books") is False and n:
            continue
        filas.append({"id": a["id"], "name": a["name"], "book_count": n})
    filas.sort(key=lambda f: f["name"], reverse=(str(order).lower() == "desc"))
    return filas[offset:offset + limit], len(filas)


def fake_get_author(aid):
    VIAJES["get"] += 1
    aid = int(aid)
    if aid not in AUTORES:
        return None
    n = sum(1 for (a, _b) in RELACION if a == aid)
    return {"id": aid, "name": AUTORES[aid]["name"], "book_count": n}


repo.list_authors = fake_list_authors
repo.get_author = fake_get_author
repo.get_by_name = lambda name: next(
    (dict(a) for a in AUTORES.values() if a["name"].lower() == name.lower()), None)
repo.books_of = lambda aid: [dict(LIBROS[b]) for (a, b) in sorted(RELACION)
                             if a == int(aid)]
repo.book_exists = lambda bid: (dict(LIBROS[int(bid)]) if int(bid) in LIBROS else None)


def fake_create_author(name):
    aid = SIGUIENTE["id"]
    SIGUIENTE["id"] += 1
    AUTORES[aid] = {"id": aid, "name": name}
    return aid


def fake_rename(aid, name):
    if int(aid) not in AUTORES:
        return False
    AUTORES[int(aid)]["name"] = name
    return True


def fake_delete(aid):
    aid = int(aid)
    fila = AUTORES.pop(aid, None)
    for par in list(RELACION):
        if par[0] == aid:
            RELACION.discard(par)
    return fila


def fake_link(aid, bid):
    par = (int(aid), int(bid))
    if par in RELACION:
        return False
    RELACION.add(par)
    return True


def fake_unlink(aid, bid):
    par = (int(aid), int(bid))
    if par not in RELACION:
        return False
    RELACION.discard(par)
    return True


def fake_replace(aid, book_ids):
    aid = int(aid)
    deseados = {int(b) for b in book_ids}
    actuales = {b for (a, b) in RELACION if a == aid}
    for b in actuales - deseados:
        RELACION.discard((aid, b))
    for b in deseados - actuales:
        RELACION.add((aid, b))
    return len(deseados - actuales), len(actuales - deseados)


repo.create_author = fake_create_author
repo.rename_author = fake_rename
repo.delete_author = fake_delete
repo.link_book = fake_link
repo.unlink_book = fake_unlink
repo.replace_books = fake_replace

PERMISOS = {1: {"*"}, 2: set(), 3: {"authors:write"}}
shared.resolver.permissions_of = lambda rid: frozenset(PERMISOS.get(int(rid), set()))
shared.database.health = lambda: (True, {"status": "ok", "database": "library_db",
                                         "user": "library_user", "schema": "library",
                                         "server": "PostgreSQL 16"})

client = appmod.app.test_client()
PASSED, FAILED = 0, 0


def check(name, cond, extra=""):
    global PASSED, FAILED
    if cond:
        PASSED += 1
        print(f"  OK    {name}")
    else:
        FAILED += 1
        print(f"  FALLA {name} {extra}")


def auth(role_id, user_id=7):
    rol = {1: "admin", 2: "user", 3: "staff"}[role_id]
    tok, _ = shared.codec.issue_access_token(
        user_id=user_id, email="a@b.mx", role=rol, role_id=role_id, sid="sid-x")
    return {"Authorization": f"Bearer {tok}"}


def reset():
    FAKE._data.clear()
    VIAJES.update({"list": 0, "get": 0})


# =====================================================================
print("1. Lecturas publicas y cacheadas")
reset()
r1 = client.get("/authors?format=json")
check("listado sin token -> 200 MISS", r1.status_code == 200
      and r1.headers.get("X-Cache") == "MISS",
      f"{r1.status_code} {r1.headers.get('X-Cache')}")
r2 = client.get("/authors?format=json")
check("segunda lectura HIT sin tocar la base",
      r2.headers.get("X-Cache") == "HIT" and VIAJES["list"] == 1, str(VIAJES))
check("la clave es authors:list:<repr>:<filtros>",
      any(k.startswith("authors:list:json:") for k in FAKE.keys_matching("authors:*")),
      str(FAKE.keys_matching("authors:*")))
rx = client.get("/authors")
check("XML por omision y entrada de cache propia",
      rx.get_data(as_text=True).startswith("<?xml")
      and rx.headers.get("X-Cache") == "MISS" and VIAJES["list"] == 2, str(VIAJES))
check("el XML trae <author>", "<author>" in rx.get_data(as_text=True),
      rx.get_data(as_text=True)[:200])
r = client.get("/authors/1?format=json")
cuerpo = r.get_json()
check("ficha del autor con sus obras", r.status_code == 200
      and cuerpo["name"] == "Ada Lovelace" and len(cuerpo["books"]) == 1,
      r.get_data(as_text=True)[:200])
check("la obra es un RESUMEN, no la ficha completa",
      set(cuerpo["books"][0]) == {"id", "isbn", "title", "publicationYear",
                                  "price", "stock"},
      str(cuerpo["books"][0]))
r = client.get("/authors/999?format=json")
check("autor inexistente -> 404", r.status_code == 404, str(r.status_code))
r = client.get("/authors/1/books?format=json")
check("obras del autor", r.status_code == 200 and r.get_json()["count"] == 1,
      r.get_data(as_text=True)[:160])
r = client.get("/authors?format=json&has_books=true")
check("filtro has_books=true", r.status_code == 200
      and [a["name"] for a in r.get_json()["authors"]] == ["Ada Lovelace"],
      r.get_data(as_text=True)[:200])
r = client.get("/authors?format=json&has_books=quiza")
check("has_books invalido -> 400", r.status_code == 400, str(r.status_code))

print("2. Escrituras: token y permiso")
r = client.post("/authors?format=json", json={"name": "Grace Hopper"})
check("alta sin token -> 401", r.status_code == 401, str(r.status_code))
r = client.post("/authors?format=json", json={"name": "Grace Hopper"},
                headers=auth(2))
check("alta con rol cliente -> 403", r.status_code == 403
      and r.get_json()["error"]["code"] == "forbidden", str(r.status_code))
r = client.post("/authors?format=json", json={"name": "Grace Hopper"},
                headers=auth(3))
check("alta con rol staff -> 201", r.status_code == 201
      and r.get_json()["name"] == "Grace Hopper", r.get_data(as_text=True)[:200])
GRACE = r.get_json()["id"]
check("Location apunta al recurso",
      r.headers.get("Location") == f"/authors/{GRACE}", str(r.headers.get("Location")))

print("3. Alta: validacion y unicidad")
r = client.post("/authors?format=json", json={"name": "  "}, headers=auth(1))
check("nombre vacio -> 400", r.status_code == 400, str(r.status_code))
r = client.post("/authors?format=json", json={"name": "x" * 151}, headers=auth(1))
check("nombre de mas de 150 -> 400", r.status_code == 400, str(r.status_code))
r = client.post("/authors?format=json", json={"name": "ada lovelace"},
                headers=auth(1))
check("nombre duplicado (sin distinguir mayusculas) -> 409",
      r.status_code == 409 and "1" in r.get_data(as_text=True),
      r.get_data(as_text=True)[:200])
r = client.post("/authors?format=json",
                json={"name": "Donald Knuth", "books": [10, 11]}, headers=auth(1))
check("alta vinculando obras -> 201 con booksLinked",
      r.status_code == 201 and r.get_json()["booksLinked"] == 2,
      r.get_data(as_text=True)[:200])
KNUTH = r.get_json()["id"]
r = client.post("/authors?format=json",
                json={"name": "Nadie", "books": [9999]}, headers=auth(1))
check("vincular un libro inexistente -> 400 que dice cual",
      r.status_code == 400 and "9999" in r.get_data(as_text=True),
      r.get_data(as_text=True)[:200])

print("4. Renombrar")
r = client.put(f"/authors/{GRACE}?format=json", json={"name": "Grace M. Hopper"},
               headers=auth(1))
check("PUT renombra", r.status_code == 200
      and r.get_json()["name"] == "Grace M. Hopper", r.get_data(as_text=True)[:160])
r = client.patch(f"/authors/{GRACE}?format=json", json={"name": "Grace Hopper"},
                 headers=auth(1))
check("PATCH hace lo mismo que PUT", r.status_code == 200
      and r.get_json()["name"] == "Grace Hopper", r.get_data(as_text=True)[:160])
r = client.put(f"/authors/{GRACE}?format=json", json={"name": "Ada Lovelace"},
               headers=auth(1))
check("renombrar a un nombre ya usado -> 409", r.status_code == 409,
      str(r.status_code))
r = client.put("/authors/999?format=json", json={"name": "X"}, headers=auth(1))
check("renombrar un autor inexistente -> 404", r.status_code == 404,
      str(r.status_code))

print("5. Cada escritura invalida el cache de autores Y el de libros")
reset()
client.get("/authors?format=json")
client.get("/authors/1?format=json")
# El microservicio de libros habria dejado estas entradas en el mismo Redis.
shared.store.cache_set(shared.store.key("books", "list", "json", "all"),
                       {"body": "{}", "status": 200}, 30, jitter=0)
shared.store.cache_set(shared.store.key("books", "978-607-11-1111-1", "json"),
                       {"body": "{}", "status": 200}, 30, jitter=0)
antes_autores = len(FAKE.keys_matching("authors:*"))
antes_libros = len(FAKE.keys_matching("books:*"))
r = client.put("/authors/1?format=json", json={"name": "Ada Byron Lovelace"},
               headers=auth(1))
check("renombrar invalida el cache de autores",
      antes_autores >= 2 and len(FAKE.keys_matching("authors:*")) == 0,
      f"antes={antes_autores} ahora={FAKE.keys_matching('authors:*')}")
check("y TAMBIEN el del catalogo de libros (un solo Redis)",
      antes_libros == 2 and len(FAKE.keys_matching("books:*")) == 0,
      f"antes={antes_libros} ahora={FAKE.keys_matching('books:*')}")
r = client.get("/authors?format=json")
check("la lectura siguiente vuelve a la base",
      r.headers.get("X-Cache") == "MISS", str(r.headers.get("X-Cache")))

print("6. Relacion autor <-> obra")
r = client.post(f"/authors/{GRACE}/books/11?format=json", headers=auth(1))
check("vincular -> 201", r.status_code == 201 and r.get_json()["created"] is True,
      r.get_data(as_text=True)[:200])
r = client.post(f"/authors/{GRACE}/books/11?format=json", headers=auth(1))
check("vincular otra vez es idempotente -> 200 alreadyLinked",
      r.status_code == 200 and r.get_json()["alreadyLinked"] is True,
      r.get_data(as_text=True)[:200])
r = client.post(f"/authors/{GRACE}/books/9999?format=json", headers=auth(1))
check("vincular un libro inexistente -> 404", r.status_code == 404,
      str(r.status_code))
r = client.delete(f"/authors/{GRACE}/books/11?format=json", headers=auth(1))
check("desvincular -> 200 y el libro sigue en el catalogo",
      r.status_code == 200 and 11 in LIBROS
      and "sigue en el catalogo" in r.get_json()["note"],
      r.get_data(as_text=True)[:200])
r = client.delete(f"/authors/{GRACE}/books/11?format=json", headers=auth(1))
check("desvincular lo que no estaba -> 404", r.status_code == 404,
      str(r.status_code))
r = client.put(f"/authors/{KNUTH}/books?format=json", json={"books": [12]},
               headers=auth(1))
cuerpo = r.get_json()
check("fijar la lista completa reemplaza (no anade)",
      r.status_code == 200 and cuerpo["linked"] == 1 and cuerpo["unlinked"] == 2
      and [b["id"] for b in cuerpo["books"]] == [12],
      r.get_data(as_text=True)[:260])
r = client.put(f"/authors/{KNUTH}/books?format=json", json={"books": [12, 9999]},
               headers=auth(1))
check("fijar con un libro inexistente -> 400 y no cambia nada",
      r.status_code == 400 and {b for (a, b) in RELACION if a == KNUTH} == {12},
      f"{r.status_code} {sorted(RELACION)}")

print("7. Baja: protege la autoria de los libros")
r = client.delete(f"/authors/{KNUTH}?format=json", headers=auth(1))
check("autor con obras -> 409 que explica el riesgo",
      r.status_code == 409 and "autoria" in r.get_data(as_text=True),
      r.get_data(as_text=True)[:260])
check("y no se borro", KNUTH in AUTORES)
r = client.delete(f"/authors/{KNUTH}?format=json&force=true", headers=auth(1))
check("con ?force=true -> 200 y dice cuantas obras desvinculo",
      r.status_code == 200 and r.get_json()["booksUnlinked"] == 1,
      r.get_data(as_text=True)[:200])
check("el autor se borro y los libros siguen", KNUTH not in AUTORES and 12 in LIBROS)
r = client.delete(f"/authors/{GRACE}?format=json", headers=auth(1))
check("autor sin obras se borra sin force", r.status_code == 200, str(r.status_code))

print("8. Token revocado y Redis caido")
tok, claims = shared.codec.issue_access_token(
    user_id=7, email="a@b.mx", role="admin", role_id=1, sid="sid-rev")
shared.store.revoke_jti(claims["jti"], 1800, reason="logout")
r = client.post("/authors?format=json", json={"name": "Revocado"},
                headers={"Authorization": f"Bearer {tok}"})
check("token revocado -> 401", r.status_code == 401
      and "revoc" in r.get_json()["error"]["message"].lower(),
      r.get_data(as_text=True)[:200])
redis_testing.break_store(shared.store)
VIAJES["list"] = 0
r = client.get("/authors?format=json")
check("lectura con Redis caido -> 200 (sin cache)",
      r.status_code == 200 and VIAJES["list"] == 1, f"{r.status_code} {VIAJES}")
r = client.post("/authors?format=json", json={"name": "Sin Redis"}, headers=auth(1))
check("escritura con Redis caido -> 503", r.status_code == 503
      and r.get_json()["error"]["code"] == "redis_unavailable",
      f"{r.status_code} {r.get_data(as_text=True)[:160]}")
r = client.get("/health?format=json")
check("health 200 degradado y lo explica",
      r.status_code == 200 and r.get_json()["status"] == "degraded"
      and any("escrituras" in w for w in r.get_json().get("warnings", [])),
      r.get_data(as_text=True)[:260])
check("health no filtra la clave de Redis", "prueba" not in r.get_data(as_text=True))
redis_testing.install(shared.store, FAKE)
r = client.get("/metrics?format=json")
m = r.get_json()
check("metrics cuenta aciertos de cache e invalidaciones",
      m["counters"].get("redis.cache.hit", 0) > 0
      and m["counters"].get("redis.cache.invalidated", 0) > 0,
      str(m["counters"])[:220])

print(f"\nResultado: {PASSED} OK, {FAILED} fallos")
sys.exit(1 if FAILED else 0)
