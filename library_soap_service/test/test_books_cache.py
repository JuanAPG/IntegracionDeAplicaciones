"""
test/test_books_cache.py
Pruebas del cache de Redis y de la autorizacion por rol en el
microservicio de libros, SIN PostgreSQL y SIN servidor Redis: el
repositorio se simula y Redis se sustituye por el doble en memoria de
library_common.testing.

Lo que comprueba, que es justo lo que es facil creer sin verificarlo:

  1. La primera lectura va a PostgreSQL (X-Cache: MISS) y la segunda a
     Redis (X-Cache: HIT), sin tocar la base.
  2. XML y JSON se cachean por separado: pedir JSON no devuelve el XML.
  3. Filtros distintos = entradas distintas; el mismo filtro en otro
     orden = la MISMA entrada.
  4. Cualquier POST/PUT/PATCH/DELETE invalida el cache: la lectura
     siguiente vuelve a la base.
  5. Las escrituras exigen Bearer y el permiso books:write:
     401 sin token o con token malo, 403 con rol insuficiente.
  6. Un token REVOCADO se rechaza con 401.
  7. Con Redis caido: las lecturas siguen funcionando (sin cache) y las
     escrituras devuelven 503.

Uso (desde library_soap_service):
    python test/test_books_cache.py
"""
import os
import sys

os.environ.setdefault("JWT_SECRET_KEY", "secreto-jwt-de-pruebas-suficientemente-largo")
os.environ.setdefault("REDIS_URL", "redis://:prueba@localhost:6379/0")
os.environ.setdefault("DEFAULT_FORMAT", "xml")

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

import soap.shared as shared  # noqa: E402
from library_common import testing as redis_testing  # noqa: E402

FAKE = redis_testing.install(shared.store)

import soap.app as appmod  # noqa: E402
import soap.books_repository as repo  # noqa: E402
import soap.config as config  # noqa: E402
import soap.db as dbmod  # noqa: E402
from library_common.errors import NotFound  # noqa: E402

# ---------------------------------------------------------------------
# Catalogo simulado y contador de viajes a PostgreSQL
# ---------------------------------------------------------------------
VIAJES = {"list": 0, "get": 0, "isbn": 0}

# Misma forma PLANA que devuelve books_repository (format_id/format_name,
# no un diccionario anidado): serializers.book_to_dict es quien anida.
LIBRO = {
    "id": 1, "isbn": "978-607-11-1111-1", "title": "Integracion de Aplicaciones",
    "publication_year": 2024, "price": 499.00, "stock": 7,
    "format_id": 1, "format_name": "Fisico",
    "category_id": 1, "category_name": "Tecnico",
    "authors": [{"id": 1, "name": "Ada Lovelace"}],
    "genres": [], "concepts": [], "images": [],
    "created_at": None, "updated_at": None,
}


def fake_list_books(filters, sort="id", order="asc", limit=50, offset=0):
    VIAJES["list"] += 1
    filas = [dict(LIBRO)]
    if filters.get("title") and filters["title"].lower() not in LIBRO["title"].lower():
        filas = []
    return filas, len(filas)


def fake_get_book(book_id):
    VIAJES["get"] += 1
    if int(book_id) != 1:
        raise NotFound(f"No existe el libro {book_id}.")
    return dict(LIBRO)


def fake_get_book_by_isbn(isbn):
    VIAJES["isbn"] += 1
    if isbn != LIBRO["isbn"]:
        raise NotFound(f"No existe el libro con ISBN {isbn}.")
    return dict(LIBRO)


repo.list_books = fake_list_books
repo.get_book = fake_get_book
repo.get_book_by_isbn = fake_get_book_by_isbn
repo.create_book = lambda data: dict(LIBRO)
repo.update_book = lambda bid, data, replace=False: dict(LIBRO)
repo.delete_book = lambda bid: {"id": 1, "isbn": LIBRO["isbn"], "title": LIBRO["title"]}
dbmod.ping = lambda: {"db": "library_db", "usr": "library_user",
                      "version": "PostgreSQL 16 on test"}

# Permisos por rol (en produccion los lee library.role_permissions).
PERMISOS = {1: {"*"}, 2: set(), 3: {"books:write"}}
shared.resolver.permissions_of = lambda role_id: frozenset(PERMISOS.get(int(role_id), set()))

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


def token_de(role_id, user_id=7, role="admin"):
    tok, _claims = shared.codec.issue_access_token(
        user_id=user_id, email="a@b.mx", role=role, role_id=role_id, sid="sid-prueba")
    return tok


def auth(role_id, role="admin"):
    return {"Authorization": f"Bearer {token_de(role_id, role=role)}"}


def reset_cache():
    FAKE._data.clear()
    VIAJES.update({"list": 0, "get": 0, "isbn": 0})


# =====================================================================
print("1. MISS y HIT: la segunda lectura no toca PostgreSQL")
reset_cache()
r1 = client.get("/books?output=json")
check("primera lectura 200 y MISS",
      r1.status_code == 200 and r1.headers.get("X-Cache") == "MISS",
      f"{r1.status_code} X-Cache={r1.headers.get('X-Cache')}")
check("la primera lectura si fue a la base", VIAJES["list"] == 1, str(VIAJES))
r2 = client.get("/books?output=json")
check("segunda lectura HIT", r2.headers.get("X-Cache") == "HIT",
      str(r2.headers.get("X-Cache")))
check("la segunda NO fue a la base", VIAJES["list"] == 1, str(VIAJES))
check("el cuerpo cacheado es identico", r1.get_data() == r2.get_data())
check("se conserva X-Total-Count en el HIT",
      r2.headers.get("X-Total-Count") == r1.headers.get("X-Total-Count"),
      str(r2.headers.get("X-Total-Count")))
check("la clave es books:list:<repr>:<filtros>",
      any(k.startswith("books:list:json:") for k in FAKE.keys_matching("books:*")),
      str(FAKE.keys_matching("books:*")))

print("2. XML y JSON se cachean por separado")
reset_cache()
client.get("/books?output=json")
rx = client.get("/books?output=xml")
check("el XML no reutiliza la entrada del JSON",
      rx.headers.get("X-Cache") == "MISS" and VIAJES["list"] == 2, str(VIAJES))
check("el XML es XML", rx.content_type.startswith("application/xml"), rx.content_type)
rx2 = client.get("/books?output=xml")
check("el XML tambien se cachea", rx2.headers.get("X-Cache") == "HIT")
check("hay dos entradas, una por representacion",
      len([k for k in FAKE.keys_matching("books:list:*")]) == 2,
      str(FAKE.keys_matching("books:list:*")))

print("3. Identidad de la entrada: filtros")
reset_cache()
client.get("/books?output=json&title=Integracion&limit=10")
r = client.get("/books?output=json&limit=10&title=Integracion")
check("mismos filtros en otro orden = mismo cache",
      r.headers.get("X-Cache") == "HIT" and VIAJES["list"] == 1, str(VIAJES))
r = client.get("/books?output=json&title=Otro&limit=10")
check("filtro distinto = entrada distinta",
      r.headers.get("X-Cache") == "MISS" and VIAJES["list"] == 2, str(VIAJES))

print("4. books:<isbn> y books/<id>")
reset_cache()
r = client.get(f"/books/isbn/{LIBRO['isbn']}?output=json")
check("ficha por ISBN 200 MISS", r.status_code == 200
      and r.headers.get("X-Cache") == "MISS", f"{r.status_code}")
r = client.get(f"/books/isbn/{LIBRO['isbn']}?output=json")
check("ficha por ISBN HIT", r.headers.get("X-Cache") == "HIT" and VIAJES["isbn"] == 1,
      str(VIAJES))
check("la clave es books:<isbn>:<repr>",
      any(k.startswith(f"books:{LIBRO['isbn'].lower()}:") for k in FAKE.keys_matching("books:*")),
      str(FAKE.keys_matching("books:*")))
r = client.get("/books/1?output=json")
check("ficha por id MISS", r.headers.get("X-Cache") == "MISS")
r = client.get("/books/1?output=json")
check("ficha por id HIT", r.headers.get("X-Cache") == "HIT" and VIAJES["get"] == 1,
      str(VIAJES))
r = client.get("/books/999?output=json")
check("un 404 NO se cachea", r.status_code == 404
      and r.headers.get("X-Cache") in (None, "MISS", "BYPASS"),
      f"{r.status_code} {r.headers.get('X-Cache')}")

print("5. Toda escritura invalida el cache")
for metodo, ruta, esperado in (("POST", "/books", 201),
                               ("PUT", "/books/1", 200),
                               ("PATCH", "/books/1", 200),
                               ("DELETE", "/books/1", 200)):
    reset_cache()
    client.get("/books?output=json")
    client.get(f"/books/isbn/{LIBRO['isbn']}?output=json")
    antes = len(FAKE.keys_matching("books:*"))
    r = client.open(f"{ruta}?output=json", method=metodo,
                    json={"isbn": LIBRO["isbn"], "title": "X",
                          "publicationYear": 2024, "price": 1, "stock": 1,
                          "format": 1, "category": 1},
                    headers=auth(1))
    quedan = len(FAKE.keys_matching("books:*"))
    r2 = client.get("/books?output=json")
    check(f"{metodo} {ruta} -> {r.status_code} e invalida el cache",
          r.status_code == esperado and antes >= 2 and quedan == 0
          and r2.headers.get("X-Cache") == "MISS",
          f"status={r.status_code} antes={antes} quedan={quedan} "
          f"recarga={r2.headers.get('X-Cache')} {r.get_data(as_text=True)[:120]}")

print("6. Autorizacion de las escrituras: 401 sin token, 403 sin permiso")
# ISBN valido: payloads.py exige entre 10 y 20 caracteres.
cuerpo = {"isbn": "978-607-11-2222-2", "title": "X", "publicationYear": 2024,
          "price": 1, "stock": 1, "format": 1, "category": 1}
r = client.post("/books?output=json", json=cuerpo)
check("sin token -> 401", r.status_code == 401
      and r.get_json()["error"]["code"] == "unauthorized",
      f"{r.status_code} {r.get_data(as_text=True)[:120]}")
r = client.post("/books?output=json", json=cuerpo,
                headers={"Authorization": "Bearer basura.no.valida"})
check("token basura -> 401 (antes era 403)", r.status_code == 401, str(r.status_code))
r = client.post("/books?output=json", json=cuerpo,
                headers={"Authorization": token_de(1)})
check("sin el esquema Bearer -> 401", r.status_code == 401, str(r.status_code))
r = client.post("/books?output=json", json=cuerpo, headers=auth(2, role="user"))
check("rol cliente (sin books:write) -> 403", r.status_code == 403
      and r.get_json()["error"]["code"] == "forbidden",
      f"{r.status_code} {r.get_data(as_text=True)[:140]}")
r = client.post("/books?output=json", json=cuerpo, headers=auth(3, role="staff"))
check("rol staff (con books:write) -> 201", r.status_code == 201, str(r.status_code))
r = client.get("/books?output=json")
check("las lecturas siguen siendo publicas", r.status_code == 200)

print("7. Token revocado -> 401")
tok = token_de(1)
import jwt as pyjwt  # noqa: E402
jti = pyjwt.decode(tok, options={"verify_signature": False})["jti"]
shared.store.revoke_jti(jti, 1800, reason="logout")
r = client.post("/books?output=json", json=cuerpo,
                headers={"Authorization": f"Bearer {tok}"})
check("token revocado -> 401", r.status_code == 401
      and "revoc" in r.get_json()["error"]["message"].lower(),
      f"{r.status_code} {r.get_data(as_text=True)[:140]}")

print("8. El error XML sale en XML (formato por omision)")
r = client.post("/books", json=cuerpo)
check("401 en XML por omision", r.status_code == 401
      and "<error" in r.get_data(as_text=True), r.get_data(as_text=True)[:140])

print("9. /health y /metrics")
r = client.get("/health?output=json")
cuerpo_h = r.get_json()
check("health 200 con Redis arriba",
      r.status_code == 200 and cuerpo_h["redis"]["status"] == "ok",
      str(cuerpo_h.get("redis")))
check("health informa el cache y sus TTL",
      cuerpo_h["cache"]["enabled"] is True and cuerpo_h["cache"]["listTtl"] == config.CACHE_TTL,
      str(cuerpo_h.get("cache")))
check("health NO publica la clave de Redis",
      "prueba" not in str(cuerpo_h.get("redis")), str(cuerpo_h.get("redis")))
r = client.get("/metrics?output=json")
m = r.get_json()
check("metrics cuenta aciertos y fallos de cache",
      m["counters"].get("redis.cache.hit", 0) > 0
      and m["counters"].get("redis.cache.miss", 0) > 0, str(m["counters"])[:220])
check("metrics cuenta las invalidaciones",
      m["counters"].get("redis.cache.invalidated", 0) > 0, str(m["counters"])[:220])
check("metrics cuenta los 401 y 403",
      m["counters"].get("http.status.4xx", 0) > 0)

print("10. Con Redis caido: lecturas si, escrituras no")
redis_testing.break_store(shared.store)
VIAJES.update({"list": 0})
r = client.get("/books?output=json")
check("lectura con Redis caido -> 200 (sin cache)",
      r.status_code == 200 and VIAJES["list"] == 1,
      f"{r.status_code} {VIAJES}")
r2 = client.get("/books?output=json")
check("y sigue yendo a PostgreSQL cada vez", r2.status_code == 200 and VIAJES["list"] == 2,
      str(VIAJES))
r = client.post("/books?output=json", json=cuerpo, headers=auth(1))
check("escritura con Redis caido -> 503 (no se puede comprobar revocacion)",
      r.status_code == 503 and r.get_json()["error"]["code"] == "redis_unavailable",
      f"{r.status_code} {r.get_data(as_text=True)[:160]}")
r = client.get("/health?output=json")
check("health sigue en 200 pero degradado",
      r.status_code == 200 and r.get_json()["status"] == "degraded",
      f"{r.status_code} {r.get_json().get('status')}")
check("health avisa de lo que deja de funcionar",
      any("escrituras" in w for w in r.get_json().get("warnings", [])),
      str(r.get_json().get("warnings")))

redis_testing.install(shared.store, FAKE)
r = client.get("/books?output=json")
check("cuando Redis vuelve, el cache vuelve a usarse",
      r.headers.get("X-Cache") in ("MISS", "HIT"), str(r.headers.get("X-Cache")))

print(f"\nResultado: {PASSED} OK, {FAILED} fallos")
sys.exit(1 if FAILED else 0)
