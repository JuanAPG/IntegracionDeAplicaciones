## Rutas identificadas

Dos fuentes, porque **no coinciden**: la especificación OpenAPI del repositorio (`openapi.py` de cada servicio y el código del monolito) y lo que de verdad responde la instancia. Se probó contra **lo desplegado**.

### En los OpenAPI del repositorio (`apps/services/*/openapi.py`, `library_soap_service/soap/openapi.py`)

| Servicio | Públicas (sin token) | Protegidas |
|---|---|---|
| login | `/`, `/health`, `/metrics`, `/validate-email`, `POST /register`, `/verify`, `POST /login` | `POST /refresh`, `POST /logout`, `GET /session` (con credencial) |
| books | `/`, `/health`, `/metrics`, `/books`, `/books/search`, `/books/<id>`, `/books/isbn/<isbn>`, `/formats`, `/categories`, `/genres`, `/authors`, `/concepts`, `/cloud-concepts`, `POST /soap/clasificacion` | `POST/PUT/PATCH/DELETE /books`, `POST /cache/invalidate` (`books:write`) |
| users | `/`, `/health`, `/metrics` | todo `/users*` y `/roles*` (`users:read`/`write`/`roles`) |
| authors | `/`, `/health`, `/metrics`, `/authors`, `/authors/<id>`, `/authors/<id>/books` | escrituras (`authors:write`) |
| pedidos | `/`, `/health`, `/metrics`, `/envios/<numero>` | todo `/pedidos*` (`orders:read`/`write`/`status`) |
| pagos | `/`, `/health`, `/metrics` | todo `/pagos*` y `/metodos` (`payments:read`/`write`) |

En el **código del monolito** (`apps/web_monolito/src/`): `BASE_PATH=/library`; públicas solo `/library`, `/library/auth/login`, `/library/auth/register` y los estáticos; `/library/catalog` y `/library/catalog/:id` exigen sesión (`requireLogin`) y responden **302 al formulario**, no 401; no existe ninguna ruta de salud. Discrepancias internas detectadas: `openapi.py` de login no documenta `POST /refresh` ni `GET /metrics`, y el de books no documenta `/metrics`, `/cache/invalidate` ni `POST /soap/clasificacion`.

### En la instancia, verificadas con curl (es lo que se prueba)

| Destino | Públicas | Protegidas (401) | No existen (404) |
|---|---|---|---|
| monolito :3000 | `/library/`, `/library/libros`, `/library/libros/<ISBN>`, `/library/libros?q=`, `/library/login`, `/library/registro`, estáticos | `/library/autores`, `/library/generos`, `/library/conceptos` (302 al inicio) | `/library/catalog`, `/library/auth/login`, `/health` |
| login :5000 | `/health` | `/session`, `/metrics` | `/`, `/docs`, `/openapi.json`, `/validate-email` |
| books :5001 | `/health`, `/books`, `/books/<ISBN>`, `/books?<filtros en español>` | `/metrics`, escrituras | `/`, `/docs`, `/books/search`, `/books/isbn/<isbn>`, `/formats`, `/categories`, `/genres`, `/authors`, `/concepts`, `/cloud-concepts`, `/soap/clasificacion` |
| users :5002 | `/health` | `/users`, `/metrics` | `/`, `/docs`, `/roles` |
| authors :5003 | `/health`, `/authors`, `/authors/<id>` | `/metrics`, escrituras | `/`, `/docs`, `/authors/<id>/books` |
| pedidos :5004 | `/health` | `/orders`, `/orders/<id>`, `/metrics` | `/pedidos`, `/envios/<numero>` |
| pagos :5005 | `/health` | `/payments`, `/metrics` | `/pagos`, `/metodos` |

La consecuencia práctica es que **solo tres destinos tienen lecturas públicas de datos** (monolito, books y authors), y son los que soportan la comparación. De los otros cuatro se mide `/health` y el rechazo autorizado.
