# Resultados de las pruebas de rendimiento

**Fecha:** 2026-10-30 · **Instancia GCP:** `34.51.65.207` · **Generador de carga:** equipo local (macOS), Locust 2.47.0 · **Archivo:** `locust_tests/locustfile.py`

Las hipótesis se escribieron **antes** de ejecutar y están en [`HIPOTESIS.md`](HIPOTESIS.md), sin retocar.

## Cómo se obtuvieron estos números

```bash
cd locust_tests
./correr_perfiles.sh                 # los seis perfiles, en orden
# equivale a, para cada perfil:
PERFIL=<perfil> locust --headless --csv evidencias/<perfil> --html evidencias/<perfil>.html
```

Cada corrida deja en `evidencias/`: `<perfil>_stats.csv`, `<perfil>_failures.csv`, `<perfil>_stats_history.csv`, `<perfil>_exceptions.csv`, `<perfil>.html` (reporte con gráficas) y `<perfil>.log` (consola, con el veredicto del umbral). En `evidencias/capturas/` hay cuatro capturas de los reportes:

| Captura | Qué muestra |
|---|---|
| `01_stress_estadisticas_cabecera.jpg` | Cabecera del reporte de `stress`: fechas, host y tabla de estadísticas |
| `02_stress_estadisticas_por_destino.jpg` | La tabla con los nombres `[monolito]`, `[books]`, `[authors]`, `[login]`, `[users]`, `[pedidos]`, `[pagos]`: cada sistema y servicio separado |
| `03_stress_graficas_rps_y_latencia.jpg` | El RPS subiendo a 12 con el p50/p95 planos en 100/140 ms |
| `04_soak_graficas_caida_de_la_instancia.jpg` | La caída: RPS a cero, latencia al techo de 15 s y los fallos despegando después |

Las tablas de abajo las genera `extraer_metricas.py` leyendo esos mismos CSV. No se transcribió ningún número a mano: se toman las columnas `95%`, `Requests/s`, `Request Count` y `Failure Count` tal como las escribió Locust.

## Umbral de servicio

El del enunciado, sin modificar: **p95 > 1000 ms** o **errores > 5 %** ⇒ degradado.

## Los siete destinos

Verificados al arrancar cada corrida (el bloque aparece en todos los `.log`):

| Destino | Puerto | `/health` dice | Lecturas públicas disponibles |
|---|---|---|---|
| monolito | 3000 | *(no tiene `/health`)* | portada, catálogo, detalle por ISBN, búsqueda, login, estático |
| login | 5000 | `service=login` | solo `/health` |
| books | 5001 | `service=books` | catálogo, detalle por ISBN, búsqueda filtrada, `/health` |
| users | 5002 | `service=users` | solo `/health` |
| authors | 5003 | `service=authors` | listado, detalle, `/health` |
| pedidos | 5004 | `service=orders` | solo `/health` |
| pagos | 5005 | `service=payments` | solo `/health` |

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

## Tabla global por perfil

| Perfil | Usuarios | Duracion | Peticiones | RPS | p95 (ms) | Errores | Umbral |
|---|---|---|---|---|---|---|---|
| smoke | 1 (pico medido 1) | 31 s | 17 | 0.60 | 150 | 0.00 % | cumplido |
| load | 5 (pico medido 5) | 2 min 01 s | 365 | 3.02 | 140 | 0.00 % | cumplido |
| stress | 2->20 (pico medido 20) | 3 min 01 s | 1268 | 7.01 | 140 | 0.08 % | cumplido |
| spike | 2->15->2 (pico medido 15) | 2 min 01 s | 604 | 5.02 | 140 | 0.00 % | cumplido |
| soak | 3 (pico medido 3) | 4 min 01 s | 368 | 1.53 | 150 | 17.93 % | DEGRADADO |
| quiebre | 1->20 (+1/12 s) (pico medido 2) | 13 min 47 s | 257 | 0.31 | 45 | 100.00 % | NO VALIDO (destino caido) |

## Tabla por destino y perfil

| Perfil | Destino | Usuarios | Duracion | Peticiones | RPS | p95 (ms) | Errores | Umbral |
|---|---|---|---|---|---|---|---|---|
| smoke | books | 1 | 31 s | 5 | 0.18 | 140 (peor ruta) | 0.00 % | cumplido |
| smoke | monolito | 1 | 31 s | 5 | 0.18 | 150 (peor ruta) | 0.00 % | cumplido |
| smoke | pagos | 1 | 31 s | 4 | 0.14 | 110 (peor ruta) | 0.00 % | cumplido |
| smoke | pedidos | 1 | 31 s | 2 | 0.07 | 110 (peor ruta) | 0.00 % | cumplido |
| smoke | users | 1 | 31 s | 1 | 0.04 | 100 (peor ruta) | 0.00 % | cumplido |
| load | authors | 5 | 2 min 01 s | 63 | 0.52 | 110 (peor ruta) | 0.00 % | cumplido |
| load | books | 5 | 2 min 01 s | 110 | 0.91 | 150 (peor ruta) | 0.00 % | cumplido |
| load | login | 5 | 2 min 01 s | 18 | 0.15 | 110 (peor ruta) | 0.00 % | cumplido |
| load | monolito | 5 | 2 min 01 s | 116 | 0.96 | 140 (peor ruta) | 0.00 % | cumplido |
| load | pagos | 5 | 2 min 01 s | 24 | 0.20 | 110 (peor ruta) | 0.00 % | cumplido |
| load | pedidos | 5 | 2 min 01 s | 21 | 0.17 | 110 (peor ruta) | 0.00 % | cumplido |
| load | users | 5 | 2 min 01 s | 13 | 0.11 | 110 (peor ruta) | 0.00 % | cumplido |
| stress | authors | 2->20 | 3 min 01 s | 195 | 1.08 | 110 (peor ruta) | 0.00 % | cumplido |
| stress | books | 2->20 | 3 min 01 s | 382 | 2.11 | 150 (peor ruta) | 0.00 % | cumplido |
| stress | login | 2->20 | 3 min 01 s | 79 | 0.44 | 110 (peor ruta) | 0.00 % | cumplido |
| stress | monolito | 2->20 | 3 min 01 s | 405 | 2.24 | 140 (peor ruta) | 0.25 % | cumplido |
| stress | pagos | 2->20 | 3 min 01 s | 86 | 0.48 | 130 (peor ruta) | 0.00 % | cumplido |
| stress | pedidos | 2->20 | 3 min 01 s | 59 | 0.33 | 170 (peor ruta) | 0.00 % | cumplido |
| stress | users | 2->20 | 3 min 01 s | 62 | 0.34 | 110 (peor ruta) | 0.00 % | cumplido |
| spike | authors | 2->15->2 | 2 min 01 s | 94 | 0.78 | 150 (peor ruta) | 0.00 % | cumplido |
| spike | books | 2->15->2 | 2 min 01 s | 187 | 1.55 | 140 (peor ruta) | 0.00 % | cumplido |
| spike | login | 2->15->2 | 2 min 01 s | 33 | 0.27 | 110 (peor ruta) | 0.00 % | cumplido |
| spike | monolito | 2->15->2 | 2 min 01 s | 178 | 1.48 | 160 (peor ruta) | 0.00 % | cumplido |
| spike | pagos | 2->15->2 | 2 min 01 s | 40 | 0.33 | 160 (peor ruta) | 0.00 % | cumplido |
| spike | pedidos | 2->15->2 | 2 min 01 s | 32 | 0.27 | 110 (peor ruta) | 0.00 % | cumplido |
| spike | users | 2->15->2 | 2 min 01 s | 40 | 0.33 | 120 (peor ruta) | 0.00 % | cumplido |
| soak | authors | 3 | 4 min 01 s | 60 | 0.25 | 370 (peor ruta) | 20.00 % | DEGRADADO |
| soak | books | 3 | 4 min 01 s | 104 | 0.43 | 180 (peor ruta) | 15.38 % | DEGRADADO |
| soak | login | 3 | 4 min 01 s | 18 | 0.07 | 100 (peor ruta) | 33.33 % | DEGRADADO |
| soak | monolito | 3 | 4 min 01 s | 122 | 0.51 | 15000 (peor ruta) | 17.21 % | DEGRADADO |
| soak | pagos | 3 | 4 min 01 s | 16 | 0.07 | 14000 (peor ruta) | 25.00 % | DEGRADADO |
| soak | pedidos | 3 | 4 min 01 s | 24 | 0.10 | 17000 (peor ruta) | 20.83 % | DEGRADADO |
| soak | users | 3 | 4 min 01 s | 24 | 0.10 | 14000 (peor ruta) | 8.33 % | DEGRADADO |
| quiebre | authors | 1->20 (+1/12 s) | 13 min 47 s | 52 | 0.06 | 230 (peor ruta) | 100.00 % | NO VALIDO (destino caido) |
| quiebre | books | 1->20 (+1/12 s) | 13 min 47 s | 76 | 0.09 | 100 (peor ruta) | 100.00 % | NO VALIDO (destino caido) |
| quiebre | login | 1->20 (+1/12 s) | 13 min 47 s | 19 | 0.02 | 45 (peor ruta) | 100.00 % | NO VALIDO (destino caido) |
| quiebre | monolito | 1->20 (+1/12 s) | 13 min 47 s | 61 | 0.07 | 130 (peor ruta) | 100.00 % | NO VALIDO (destino caido) |
| quiebre | pagos | 1->20 (+1/12 s) | 13 min 47 s | 27 | 0.03 | 55 (peor ruta) | 100.00 % | NO VALIDO (destino caido) |
| quiebre | pedidos | 1->20 (+1/12 s) | 13 min 47 s | 14 | 0.02 | 33 (peor ruta) | 100.00 % | NO VALIDO (destino caido) |
| quiebre | users | 1->20 (+1/12 s) | 13 min 47 s | 8 | 0.01 | 150 (peor ruta) | 100.00 % | NO VALIDO (destino caido) |

## El par comparable: catalogo

| Perfil | [monolito] /library/libros p95 | [books] /books?format=json p95 |
|---|---|---|
| smoke | 110 ms |  140 ms |
| load | 140 ms |  140 ms |
| stress | 140 ms |  150 ms |
| spike | 160 ms |  140 ms |
| soak | 340 ms |  180 ms |
| quiebre | 29 ms |  77 ms |

## Desviaciones respecto al enunciado, y por qué

Se registran en lugar de disimularlas.

1. **No existe `levanta_todo.ps1` ni `README.md` en la raíz del repositorio.** Lo comprobé con `find` sobre todo el monorepo: los únicos `.ps1` son los `Activate.ps1` de los entornos virtuales. Las instrucciones 1 a 3 (preparar PostgreSQL según el README de la raíz y levantar los servicios con ese script en PowerShell) no se pueden seguir tal como están escritas en este repositorio.
2. **No hizo falta levantar nada**: los siete componentes ya estaban corriendo en la instancia de GCP, y así se verificó antes de cada corrida (`GET /health?format=json` de los seis servicios y `GET /library/` del monolito, todos 200). El enunciado además exige apuntar las pruebas a la instancia y **no** a `localhost`, que es lo que se hizo.
3. **La carga se generó desde macOS, no desde PowerShell.** El enunciado menciona PowerShell para levantar los servicios en el equipo local; como no se levantó nada en local, el único papel del equipo es generar carga, y eso no cambia lo que mide el servidor. Sí cambia la latencia de red, y eso está anotado en las limitaciones.
4. **El mapa de puertos del enunciado no coincide con la realidad.** El enunciado dice `pagos 5002, pedidos 5003, users 5004, autores 5005`. La instancia responde `users 5002, authors 5003, orders 5004, payments 5005`, y no es una suposición: cada `/health` declara su propio nombre de servicio. El `locustfile.py` usa el mapa real y vuelve a comprobarlo en cada arranque; si algún día un puerto contesta con otra identidad, la aserción de `/health` falla y lo dice.
5. **La versión desplegada no es la del repositorio**, ni en `books` ni en el monolito. En la instancia, `books` usa filtros en español, envuelve el JSON en `libros`/`count`, resuelve el detalle por ISBN e ignora la cabecera `Accept`; y el monolito sirve `/library/libros` público (en el repo el catálogo exige sesión) y resuelve el detalle por ISBN en vez de por id. Las rutas del `locustfile.py` se verificaron **una por una con curl contra la instancia**, no contra el código.
6. **No se usaron credenciales.** Las rutas que exigen `Authorization: Bearer` se prueban exigiendo el `401`, que ejercita la cadena de autorización completa sin tocar datos y sin guardar secretos en el archivo entregado.

## Qué NO mide esta prueba

1. **Las operaciones de negocio de `users`, `pedidos` y `pagos`.** Esos tres servicios no tienen ninguna lectura pública: crear un pedido o registrar un cobro son escrituras, y el enunciado pide preferir lecturas que no cambien datos. De ellos se mide `/health` (que sí ejerce PostgreSQL y Redis) y el rechazo `401` (que ejerce la verificación del JWT contra Redis). **Su p95 bajo no significa que sean más rápidos: significa que se les está midiendo menos trabajo.**
2. **La capacidad máxima del sistema.** El punto de quiebre de la tabla es el observado en una corrida de 4 minutos, con pausa de 1-2 s entre tareas, desde un equipo doméstico y por Internet hasta GCP.
3. **Ningún destino recibió los 20 usuarios.** La carga se reparte entre los siete destinos según los pesos de las tareas, de modo que el número de usuarios del perfil es la concurrencia del **sistema completo**, no la de un servicio aislado.
