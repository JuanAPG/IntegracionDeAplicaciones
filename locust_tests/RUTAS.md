# Rutas identificadas

Dos inventarios, porque se midieron **dos despliegues distintos**. Ninguno
se dedujo de la documentación: todos se comprobaron con `curl` contra la
instancia, mirando código de estado **y cuerpo**.

## Por qué hay dos

El 2026-11-01 se reinició la VM. Lo que servía el 30-oct eran procesos
lanzados **a mano** que no eran el código del repositorio; al habilitar
las unidades de systemd arrancó el despliegue de `/opt/library/*`, que sí
lo es. Cambió casi todo el contrato:

| | Tanda 1 (2026-10-30) | Tanda 2 (2026-11-01) |
|---|---|---|
| Servidor de los seis | Werkzeug (desarrollo), 1 proceso | **gunicorn, 3 workers** |
| Identidad del servicio | en `/health` (`service=books`) | en `GET /?format=json` (`library-books-service`) |
| Catálogo JSON | envuelto en `libros` + `count` | envuelto en `books`, con `library` aparte |
| Filtros del catálogo | **español** (`titulo`, `autor`, `genero`, `precio_min`) | **inglés** (`title`, `author`, `genre`, `price_min`) |
| Detalle de libro | solo por ISBN | por **id** y por **ISBN** (`/books/isbn/<isbn>`) |
| Autores | `autores` / `id_autor` | `authors` / `id` |
| Pedidos y pagos | `/orders`, `/payments` | `/pedidos`, `/pagos`, `/metodos` |
| Rastreo público | no existía (404) | **`/envios/<numero>`** existe |
| `/docs/` y `/openapi.json` | 404 | **200** (Swagger) |
| `/metrics` | 401 (exigía Bearer) | **200, público** (XML) |
| `/session` | 401 | **200** `{"authenticated": false}` |
| Monolito | `/library/libros` **público**, detalle por ISBN | `/library/catalog` **exige sesión**, detalle por id |
| Datos | 31 libros, 35 autores | 16 libros, 24 autores |

La consecuencia práctica: **los números de las dos tandas no se comparan
entre sí**. Cada una mide un sistema distinto.

---

## Tanda 2 (2026-11-01) — el despliegue del repositorio

Es el que mide el `locustfile.py` actual.

### En los OpenAPI del repositorio

Ahora sí se pueden consultar en vivo: `GET /docs/` y `GET /openapi.json`
responden 200 en los seis (en la tanda 1 daban 404). El código de cada
uno está en `apps/services/<servicio>/<servicio>/openapi.py` y
`library_soap_service/soap/openapi.py`.

### En la instancia, verificadas con curl (es lo que se prueba)

| Destino | Públicas | Protegidas (401) | No existen (404) |
|---|---|---|---|
| monolito :3000 | `/library/`, `/library/auth/login`, `/library/auth/register`, estáticos | `/library/catalog`, `/library/catalog/<id>`, `/library/admin/*` → **302** a `/library/auth/login` | `/library/libros`, `/health` |
| login :5000 | `/`, `/health`, `/metrics`, `/session`, `/validate-email`, `/docs/`, `/openapi.json` | escrituras de sesión | — |
| books :5001 | `/`, `/health`, `/metrics`, `/books`, `/books/<id>`, `/books/isbn/<isbn>`, `/books/search?q=`, `/books?<filtros>`, `/formats`, `/categories`, `/genres`, `/authors`, `/docs/` | `POST/PUT/PATCH/DELETE /books` | — |
| users :5002 | `/`, `/health`, `/metrics`, `/docs/` | `/users`, `/roles` | — |
| authors :5003 | `/`, `/health`, `/metrics`, `/authors`, `/authors/<id>`, `/authors/<id>/books`, `/docs/` | escrituras | — |
| pedidos :5004 | `/`, `/health`, `/metrics`, `/envios/<numero>`, `/docs/` | `/pedidos` | — |
| pagos :5005 | `/`, `/health`, `/metrics`, `/docs/` | `/pagos`, `/metodos` | — |

**Tres salvedades que conviene no pasar por alto:**

1. **`/envios/<numero>` existe pero no hay ningún pedido en la base.** Se
   probaron `PED-000001`, `PED-000002` y `PED-000003`: los tres dan 404
   con el mensaje de dominio ("No hay ningún pedido con el número…"). Lo
   que se mide, por tanto, es la consulta a PostgreSQL que termina en
   404, no una lectura de negocio.
2. **El catálogo del monolito exige sesión.** Sin credenciales, las tres
   tareas del catálogo miden un **302**: enrutado + comprobación de
   sesión, sin consulta ni renderizado. La única lectura real del
   monolito es la portada, que consulta `library.v_catalog_stats`.
3. **Los filtros en español se ignoran en silencio.** `titulo=1984`
   devuelve el catálogo entero con `filters` vacío, en vez de dar un
   error. Es peor que un fallo: una aserción escrita contra el contrato
   viejo habría pasado midiendo otra cosa. Por eso la tarea de búsqueda
   comprueba que `filters` **no** venga vacío.

---

## Tanda 1 (2026-10-30) — el despliegue que ya no existe

Se conserva porque es lo que miden las evidencias de
`evidencias/2026-10-30/`. Ninguna de estas rutas responde ya igual.

### En los OpenAPI del repositorio (consultados en el código)

| Servicio | Públicas (sin token) | Protegidas |
|---|---|---|
| login | `/`, `/health`, `/metrics`, `/validate-email`, `POST /register`, `/verify`, `POST /login` | `POST /refresh`, `POST /logout`, `GET /session` |
| books | `/`, `/health`, `/metrics`, `/books`, `/books/search`, `/books/<id>`, `/books/isbn/<isbn>`, `/formats`, `/categories`, `/genres`, `/authors`, `/concepts`, `/cloud-concepts`, `POST /soap/clasificacion` | escrituras, `POST /cache/invalidate` |
| users | `/`, `/health`, `/metrics` | todo `/users*` y `/roles*` |
| authors | `/`, `/health`, `/metrics`, `/authors`, `/authors/<id>`, `/authors/<id>/books` | escrituras |
| pedidos | `/`, `/health`, `/metrics`, `/envios/<numero>` | todo `/pedidos*` |
| pagos | `/`, `/health`, `/metrics` | todo `/pagos*` y `/metodos` |

### En la instancia, tal como respondía entonces

| Destino | Públicas | Protegidas (401) | No existían (404) |
|---|---|---|---|
| monolito :3000 | `/library/`, `/library/libros`, `/library/libros/<ISBN>`, `/library/libros?q=`, `/library/login`, `/library/registro` | `/library/autores`, `/library/generos` (302) | `/library/catalog`, `/library/auth/login`, `/health` |
| login :5000 | `/health` | `/session`, `/metrics` | `/`, `/docs`, `/openapi.json`, `/validate-email` |
| books :5001 | `/health`, `/books`, `/books/<ISBN>`, `/books?<filtros en español>` | `/metrics`, escrituras | `/`, `/docs`, `/books/search`, `/books/isbn/<isbn>`, `/formats`, `/categories`, `/genres`, `/authors`, `/concepts`, `/soap/clasificacion` |
| users :5002 | `/health` | `/users`, `/metrics` | `/`, `/docs`, `/roles` |
| authors :5003 | `/health`, `/authors`, `/authors/<id>` | `/metrics`, escrituras | `/`, `/docs`, `/authors/<id>/books` |
| pedidos :5004 | `/health` | `/orders`, `/orders/<id>`, `/metrics` | `/pedidos`, `/envios/<numero>` |
| pagos :5005 | `/health` | `/payments`, `/metrics` | `/pagos`, `/metodos` |
