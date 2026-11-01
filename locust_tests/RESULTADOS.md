# Resultados de las pruebas de rendimiento

**Instancia GCP:** `maquina-01` (proyecto `mythic-evening-505221-n7`, zona `northamerica-south1-c`) · **Generador de carga:** equipo local (macOS), Locust 2.47.0 · **Archivo:** `locust_tests/locustfile.py`

Las hipótesis de cada tanda se escribieron **antes** de ejecutar y están en [`HIPOTESIS.md`](HIPOTESIS.md), sin retocar. El inventario de rutas, comprobado con `curl` contra la instancia, está en [`RUTAS.md`](RUTAS.md).

## Umbral de servicio

El del enunciado, sin modificar: **p95 > 1000 ms** o **errores > 5 %** ⇒ degradado. No se justifica ningún umbral distinto porque no se cambió ninguno.

## AVISO: hay DOS tandas contra DOS despliegues distintos

No es un capricho de presentación, y pasarlo por alto llevaría a conclusiones falsas.

El 2026-11-01 se reinició la VM. Lo que servía el 30-oct eran procesos lanzados **a mano** que no eran el código del repositorio; al habilitar las unidades de systemd arrancó el despliegue de `/opt/library/*`, que sí lo es. Cambiaron las rutas, las claves del JSON, los filtros (de español a inglés), la visibilidad de `/metrics`, los datos del catálogo y, sobre todo, **el servidor**: de Werkzeug con un proceso a **gunicorn con tres workers**.

| | Tanda 1 — 2026-10-30 | Tanda 2 — 2026-11-01 |
|---|---|---|
| IP de la instancia | `34.51.65.207` | `34.51.89.203` |
| Despliegue | procesos a mano, código distinto al del repo | `/opt/library/*` por systemd, **el del repositorio** |
| Servidor de los seis | Werkzeug (desarrollo), 1 proceso | **gunicorn, 3 workers** |
| Datos | 31 libros, 35 autores | 16 libros, 24 autores |
| Catálogo del monolito | `/library/libros`, **público** | `/library/catalog`, **exige sesión** |
| Evidencias | `evidencias/2026-10-30/` | `evidencias/2026-11-01/` |

La tabla completa de diferencias de contrato está en [`RUTAS.md`](RUTAS.md). **Los números de una tanda no se comparan con los de la otra**: miden sistemas distintos. Lo que sí se puede comparar es *dentro* de cada tanda.

---

# Tanda 2 — 2026-11-01 — el despliegue del repositorio

## Cómo se obtuvieron estos números

```bash
cd locust_tests
RONDA=2026-11-01 ./correr_perfiles.sh        # los seis perfiles, en orden
# equivale a, para cada perfil:
PERFIL=<perfil> locust --headless \
    --csv evidencias/2026-11-01/<perfil> --html evidencias/2026-11-01/<perfil>.html
```

Cada corrida deja en `evidencias/2026-11-01/`: `<perfil>_stats.csv`, `<perfil>_failures.csv`, `<perfil>_stats_history.csv`, `<perfil>_exceptions.csv`, `<perfil>.html` (reporte con gráficas) y `<perfil>.log` (consola, con el veredicto del umbral).

Las tablas de abajo las genera `extraer_metricas.py` leyendo esos mismos CSV (`RONDA=2026-11-01 ./armar_resultados.sh`). No se transcribió ningún número a mano: se toman las columnas `95%`, `Requests/s`, `Request Count` y `Failure Count` tal como las escribió Locust, y la duración y la concurrencia pico salen del historial, no del perfil declarado.

## Capturas de esta tanda

En `evidencias/2026-11-01/capturas/`:

| Captura | Qué muestra |
|---|---|
| `01_quiebre_graficas_rps_latencia_y_fallos.jpg` | El perfil de quiebre: el RPS sube en línea recta de 0.6 a 12.5 mientras el p50 y el p95 se quedan planos en 95 y 140 ms y la línea de fallos no despega del eje. Es la prueba visual de que **no se alcanzó el quiebre** |
| `02_stress_fallos_suben_con_la_latencia_plana.jpg` | El `stress`: la línea roja de fallos despega a las 17:03:20 y llega a ~4.5/s **con los tiempos de respuesta inmóviles en 95/140 ms**. Esa combinación es la firma de un componente que deja de aceptar conexiones, no de uno saturado |
| `03_stress_los_386_fallos_son_del_monolito.jpg` | La tabla de fallos del reporte: las cinco filas son `[monolito]` (50+28+164+72+72 = 386) y ninguna es de un microservicio |

## Los siete destinos

Verificados al arrancar cada corrida (el bloque aparece en todos los `.log`). La identidad ya no se lee de `/health` —esta versión no la publica ahí— sino de `GET /?format=json`:

| Destino | Puerto | Identidad declarada | Lecturas públicas disponibles |
|---|---|---|---|
| monolito | 3000 | *(no tiene `/health`)* | portada; el catálogo **exige sesión** |
| login | 5000 | `library-login-service` | `/health`, `/session`, `/validate-email`, `/metrics` |
| books | 5001 | `library-books-service` | catálogo, detalle, búsqueda, filtros, `/health`, `/metrics` |
| users | 5002 | `library-users-service` | `/health`, `/metrics` |
| authors | 5003 | `library-authors-service` | listado, detalle, `/health`, `/metrics` |
| pedidos | 5004 | `library-pedidos-service` | `/health`, `/metrics`, `/envios/<numero>` |
| pagos | 5005 | `library-pagos-service` | `/health`, `/metrics` |

<!--TABLAS 2026-11-01-->

## Tabla global por perfil

| Perfil | Usuarios | Duracion | Peticiones | RPS | p95 (ms) | Errores | Umbral |
|---|---|---|---|---|---|---|---|
| smoke | 1 (pico medido 1) | 30 s | 18 | 0.61 | 300 | 0.00 % | cumplido |
| load | 5 (pico medido 5) | 2 min 01 s | 372 | 3.08 | 140 | 0.00 % | cumplido |
| stress | 2->20 (pico medido 20) | 3 min 00 s | 1272 | 7.07 | 140 | 30.35 % | DEGRADADO |
| spike | 2->15->2 (pico medido 15) | 2 min 01 s | 601 | 5.01 | 140 | 0.00 % | cumplido |
| soak | 3 (pico medido 3) | 4 min 01 s | 441 | 1.84 | 140 | 0.00 % | cumplido |
| quiebre | 1->20 (+1/12 s) (pico medido 20) | 4 min 00 s | 1571 | 6.54 | 140 | 0.00 % | cumplido |

## Tabla por destino y perfil

| Perfil | Destino | Usuarios | Duracion | Peticiones | RPS | p95 (ms) | Errores | Umbral |
|---|---|---|---|---|---|---|---|---|
| smoke | authors | 1 | 30 s | 2 | 0.07 | 96 (peor ruta) | 0.00 % | cumplido |
| smoke | books | 1 | 30 s | 7 | 0.24 | 150 (peor ruta) | 0.00 % | cumplido |
| smoke | monolito | 1 | 30 s | 5 | 0.17 | 100 (peor ruta) | 0.00 % | cumplido |
| smoke | pagos | 1 | 30 s | 3 | 0.10 | 95 (peor ruta) | 0.00 % | cumplido |
| smoke | pedidos | 1 | 30 s | 1 | 0.03 | 300 (peor ruta) | 0.00 % | cumplido |
| load | authors | 5 | 2 min 01 s | 64 | 0.53 | 110 (peor ruta) | 0.00 % | cumplido |
| load | books | 5 | 2 min 01 s | 111 | 0.92 | 180 (peor ruta) | 0.00 % | cumplido |
| load | login | 5 | 2 min 01 s | 23 | 0.19 | 100 (peor ruta) | 0.00 % | cumplido |
| load | monolito | 5 | 2 min 01 s | 121 | 1.00 | 100 (peor ruta) | 0.00 % | cumplido |
| load | pagos | 5 | 2 min 01 s | 14 | 0.12 | 270 (peor ruta) | 0.00 % | cumplido |
| load | pedidos | 5 | 2 min 01 s | 15 | 0.12 | 98 (peor ruta) | 0.00 % | cumplido |
| load | users | 5 | 2 min 01 s | 24 | 0.20 | 230 (peor ruta) | 0.00 % | cumplido |
| stress | authors | 2->20 | 3 min 00 s | 210 | 1.17 | 110 (peor ruta) | 0.00 % | cumplido |
| stress | books | 2->20 | 3 min 00 s | 371 | 2.06 | 140 (peor ruta) | 0.00 % | cumplido |
| stress | login | 2->20 | 3 min 00 s | 89 | 0.49 | 99 (peor ruta) | 0.00 % | cumplido |
| stress | monolito | 2->20 | 3 min 00 s | 401 | 2.23 | 94 (peor ruta) | 96.26 % | DEGRADADO |
| stress | pagos | 2->20 | 3 min 00 s | 79 | 0.44 | 100 (peor ruta) | 0.00 % | cumplido |
| stress | pedidos | 2->20 | 3 min 00 s | 68 | 0.38 | 110 (peor ruta) | 0.00 % | cumplido |
| stress | users | 2->20 | 3 min 00 s | 54 | 0.30 | 110 (peor ruta) | 0.00 % | cumplido |
| spike | authors | 2->15->2 | 2 min 01 s | 127 | 1.06 | 110 (peor ruta) | 0.00 % | cumplido |
| spike | books | 2->15->2 | 2 min 01 s | 266 | 2.22 | 150 (peor ruta) | 0.00 % | cumplido |
| spike | login | 2->15->2 | 2 min 01 s | 56 | 0.47 | 100 (peor ruta) | 0.00 % | cumplido |
| spike | pagos | 2->15->2 | 2 min 01 s | 44 | 0.37 | 110 (peor ruta) | 0.00 % | cumplido |
| spike | pedidos | 2->15->2 | 2 min 01 s | 61 | 0.51 | 100 (peor ruta) | 0.00 % | cumplido |
| spike | users | 2->15->2 | 2 min 01 s | 47 | 0.39 | 520 (peor ruta) | 0.00 % | cumplido |
| soak | authors | 3 | 4 min 01 s | 94 | 0.39 | 110 (peor ruta) | 0.00 % | cumplido |
| soak | books | 3 | 4 min 01 s | 215 | 0.90 | 150 (peor ruta) | 0.00 % | cumplido |
| soak | login | 3 | 4 min 01 s | 31 | 0.13 | 170 (peor ruta) | 0.00 % | cumplido |
| soak | pagos | 3 | 4 min 01 s | 48 | 0.20 | 110 (peor ruta) | 0.00 % | cumplido |
| soak | pedidos | 3 | 4 min 01 s | 18 | 0.08 | 99 (peor ruta) | 0.00 % | cumplido |
| soak | users | 3 | 4 min 01 s | 35 | 0.15 | 110 (peor ruta) | 0.00 % | cumplido |
| quiebre | authors | 1->20 (+1/12 s) | 4 min 00 s | 381 | 1.59 | 100 (peor ruta) | 0.00 % | cumplido |
| quiebre | books | 1->20 (+1/12 s) | 4 min 00 s | 659 | 2.74 | 140 (peor ruta) | 0.00 % | cumplido |
| quiebre | login | 1->20 (+1/12 s) | 4 min 00 s | 147 | 0.61 | 100 (peor ruta) | 0.00 % | cumplido |
| quiebre | pagos | 1->20 (+1/12 s) | 4 min 00 s | 134 | 0.56 | 170 (peor ruta) | 0.00 % | cumplido |
| quiebre | pedidos | 1->20 (+1/12 s) | 4 min 00 s | 123 | 0.51 | 110 (peor ruta) | 0.00 % | cumplido |
| quiebre | users | 1->20 (+1/12 s) | 4 min 00 s | 127 | 0.53 | 110 (peor ruta) | 0.00 % | cumplido |

## El par comparable: catalogo

| Perfil | [monolito] catalogo p95 | [books] /books?format=json p95 |
|---|---|---|
| smoke | 95 ms |  150 ms |
| load | 96 ms |  140 ms |
| stress | 52 ms |  140 ms |
| spike | — |  150 ms |
| soak | — |  150 ms |
| quiebre | — |  140 ms |

<!--FIN TABLAS 2026-11-01-->

## Tanda 2 · Ficha por perfil: parámetros, hipótesis y conclusión

| Perfil | Usuarios | spawn_rate | Duración | RPS | p95 | Errores | Umbral | Hipótesis previa | Conclusión |
|---|---|---|---|---|---|---|---|---|---|
| **Smoke** | 1 | 1/s | 30 s | 0.61 | 300 ms | 0.00 % | cumplido | 0 errores, p95 < 300 ms | Se cumple. 18 peticiones, ningún fallo, y los **siete** destinos verificados con su identidad correcta en el bloque de arranque. El p95 de 300 ms es el de la primerísima petición a `pedidos` (arranque en frío del worker); la mediana fue de 96 ms |
| **Load** | 5 | 1/s | 2 min | 3.08 | 140 ms | 0.00 % | Umbral cumplido, RPS ~3-5 impuesto por el cliente | Se cumple. 372 peticiones, cero fallos, los siete destinos dentro del umbral. El RPS es el techo que imponen 5 usuarios con pausa de 1-2 s |
| **Stress** | 2→20 en 7 etapas | 1-2/s | 3 min | 7.07 | 140 ms | **30.35 %** | Menos degradación que en octubre gracias a los 3 workers | **Los seis microservicios la confirman; el monolito la refuta.** Los 386 fallos son **todos del monolito**, que dejó de responder a mitad de la rampa. Los seis microservicios hicieron 871 peticiones con **cero** fallos y p95 de 140 ms |
| **Spike** | 2→15→2 | 10/s en el salto | 2 min | 5.01 | 140 ms | 0.00 % | Pico menor que en octubre | Se cumple. Cero errores y p95 de 140 ms. Sin el monolito (ya caído), **seis** destinos |
| **Soak** | 3 | 1/s | 4 min | 1.84 | 140 ms | 0.00 % | Latencia plana; si se repitiera la caída de octubre no sería casualidad | **Se cumple, y es un resultado importante: NO se repitió la caída.** Cuatro minutos planos, cero fallos. La caída del 30-oct no se reprodujo con este despliegue |
| **Punto de quiebre** | 1→20, +1 cada 12 s | 1/s | 4 min | 6.54 | 140 ms | 0.00 % | No alcanzarlo | **VÁLIDO y confirmado: no se alcanzó.** Los 240 s completos, hasta 20 usuarios y 12.5 RPS sostenidos, con el p95 clavado en 140 ms y **cero fallos**. El punto de quiebre de los seis microservicios está **por encima de 20 usuarios** en estas condiciones |

## Tanda 2 · Por qué se cayó el monolito: NO fue la carga

Es el apartado que más cambió al buscarle la causa, y conviene contarlo entero porque la primera lectura era la cómoda y resultó ser falsa.

**Lo que se midió.** En el `stress`, los 386 fallos son **todos del monolito**:

| Destino | Peticiones en `stress` | Fallos |
|---|---|---|
| monolito | 401 | **386** (96.3 %) |
| books | 371 | 0 |
| authors | 210 | 0 |
| login · pagos · pedidos · users | 290 | 0 |

Los seis microservicios aguantaron la misma rampa, en la misma máquina y al mismo tiempo, sin un solo fallo. La conclusión que se ofrecía sola era "el monolito es el primero en degradarse bajo carga, los microservicios aguantan mejor". **Es falsa.**

**La causa real, con la evidencia.** El log de la aplicación (`/tmp/monolito.log`) termina en su línea de arranque: ni excepción, ni traza, ni error. Un proceso que se cae por su cuenta deja algo; éste no dejó nada, lo que apunta a que lo mataron desde fuera. La consola serie de la instancia lo confirma al segundo:

| Hora (UTC) | Evento |
|---|---|
| 22:57:49 | `Started session-39.scope - Session 39 of User jgalvann` — la sesión SSH desde la que se lanzó `npm start` |
| **23:03:08** | **`session-39.scope: Deactivated successfully. Consumed 1.813s CPU time, 111.1M memory peak`** |
| **23:03:09** | **primer fallo del monolito en Locust** (`stress_failures.csv`) |

Un segundo de diferencia. **systemd retiró el scope de la sesión al cerrarse el SSH y se llevó por delante el proceso de Node**, que vivía dentro de ese cgroup. Los 111 MB de pico del scope son el propio Node. `nohup` protege de la señal SIGHUP, pero **no** de que systemd elimine el cgroup entero de la sesión — es el comportamiento de `systemd-logind` en esta familia de distribuciones.

Dos comprobaciones que descartan las alternativas:

1. **No fue falta de memoria.** Los únicos dos `SIGKILL ... Perhaps out of memory?` de esa ventana son de las **23:11 y 23:15**, posteriores a la muerte del monolito, y corresponden a workers de gunicorn de los microservicios, que siguieron respondiendo sin un fallo.
2. **No fue la carga.** El monolito había servido el `load` entero —5 usuarios, 121 peticiones— con **cero fallos** y p95 de 100 ms, y en el `stress` solo empezó a fallar en el segundo exacto del cierre de sesión, no al subir un escalón de concurrencia.

**Qué queda, entonces, como resultado honesto:**

* El `stress` de la tanda 2 **no es una medición válida del monolito**: mide un proceso que fue terminado por una causa ajena a la prueba. Hay que repetirlo con el monolito bajo un supervisor.
* **No hay ninguna evidencia de que el monolito se degrade antes que los microservicios.** Dentro de los límites de esta práctica, **ningún componente se degradó por carga** en ninguna de las dos tandas.
* Lo que sí queda en pie, y es un hallazgo de despliegue y no de rendimiento: el monolito es el **único de los siete sin unidad de systemd**. Por eso no sobrevivió al reinicio de la VM mientras los seis microservicios volvieron solos, y por eso un `npm start` lanzado a mano muere al cerrar la sesión. La corrección es una unidad con `Restart=always`, no un cambio en la aplicación.

## Tanda 2 · Hipótesis contra resultados: qué se refutó

1. **"Con gunicorn y tres workers habrá menos degradación." CONFIRMADA en los seis microservicios.** El perfil de quiebre llegó a 20 usuarios y 12.5 RPS con el p95 inmóvil en 140 ms y cero fallos durante los 4 minutos completos. En octubre, el `stress` con los mismos 20 usuarios ya dejaba un fallo y no se pudo medir el quiebre.

2. **"La ventaja del monolito no era Werkzeug sino la pila Flask desplegada." CONFIRMADA.** Se comprobó mirando la cabecera, no suponiéndola: con gunicorn, `books` sigue respondiendo `Connection: close`. El worker síncrono de gunicorn tampoco mantiene la conexión viva, de modo que cada petición sigue pagando un saludo TCP. **Esto corrige la conclusión de octubre**, que atribuía la diferencia a Werkzeug en particular.

3. **"El monolito saldrá artificialmente rápido porque se le mide un 302." CONFIRMADA, y hay que insistir en ella.** En la tabla del par comparable el monolito aparece con 52-96 ms contra los 140-150 ms de `books`. **Ese número no dice que el monolito sea más rápido**: dice que se le está midiendo una redirección —enrutado más comprobación de sesión, sin consulta ni plantilla— mientras a `books` se le mide una consulta y una serialización completas. Sin credenciales, **el par comparable de esta tanda no es válido**, y así hay que leerlo.

4. **"Si la caída del soak se repitiera, apuntaría a la instancia." NO se repitió.** Cuatro minutos de carga sostenida con cero fallos. Aquella caída no era un defecto reproducible de la aplicación bajo esta carga.

5. **"El monolito será el primero en degradarse." NO SE PUDO COMPROBAR, y por poco se da por buena.** Los 386 fallos del `stress` son suyos y la conclusión se ofrecía sola. Al buscarle la causa resultó que systemd mató el proceso al cerrarse la sesión SSH, un segundo antes del primer fallo. **No hay ninguna evidencia de que el monolito se degrade antes que los microservicios**: dentro de los límites de esta práctica, ningún componente se degradó por carga en ninguna de las dos tandas.

6. **La caché de Redis funciona y se nota:** entre el 43 % y el 55 % de las lecturas cacheables se sirvieron con `X-Cache: HIT` en los cinco perfiles con carga.

## Tanda 2 · Qué NO mide

1. **El par comparable monolito-vs-microservicios**, por lo dicho en el punto 3: sin sesión, el catálogo del monolito es un 302. Para medirlo de verdad hay que exportar `MONO_EMAIL` y `MONO_PASSWORD` y repetir; el `locustfile.py` ya lo soporta y lo deja dicho en el `.log` de cada corrida.
2. **Las operaciones de negocio de `users`, `pedidos` y `pagos`**, que son escrituras. De ellos se mide `/health` (que ejerce PostgreSQL y Redis), `/metrics` y el rechazo `401` (que ejerce la verificación del JWT contra Redis). **Su p95 bajo no significa que sean más rápidos: significa que se les mide menos trabajo.**
3. **El rastreo público de pedidos como lectura de negocio.** `/envios/<numero>` existe, pero la base no tiene ningún pedido: los tres números probados dan 404. Lo que se mide es la consulta que termina en 404.
4. **La capacidad máxima.** "No se alcanzó el quiebre con 20 usuarios" significa eso y nada más: con esta pausa entre tareas, cuatro minutos, desde este equipo y por Internet hasta GCP.
5. **Ningún destino recibió los 20 usuarios.** La carga se reparte entre los destinos disponibles según los pesos, de modo que el número de usuarios del perfil es la concurrencia del **sistema completo**.

---

# Tanda 1 — 2026-10-30 — el despliegue que ya no existe

Se conserva completa. Sus evidencias están en `evidencias/2026-10-30/`, incluidas las cuatro capturas de `evidencias/2026-10-30/capturas/`:

| Captura | Qué muestra |
|---|---|
| `01_stress_estadisticas_cabecera.jpg` | Cabecera del reporte de `stress`: fechas, host y tabla de estadísticas |
| `02_stress_estadisticas_por_destino.jpg` | La tabla con los nombres `[monolito]`, `[books]`, `[authors]`, `[login]`, `[users]`, `[pedidos]`, `[pagos]`: cada sistema y servicio separado |
| `03_stress_graficas_rps_y_latencia.jpg` | El RPS subiendo a 12 con el p50/p95 planos en 100/140 ms |
| `04_soak_graficas_caida_de_la_instancia.jpg` | La caída: RPS a cero, latencia al techo de 15 s y los fallos despegando después |

<!--TABLAS 2026-10-30-->

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

| Perfil | [monolito] catalogo p95 | [books] /books?format=json p95 |
|---|---|---|
| smoke | 110 ms |  140 ms |
| load | 140 ms |  140 ms |
| stress | 140 ms |  150 ms |
| spike | 160 ms |  140 ms |
| soak | 340 ms |  180 ms |
| quiebre | 29 ms |  77 ms |

<!--FIN TABLAS 2026-10-30-->

## Tanda 1 · Ficha por perfil: parámetros, hipótesis y conclusión

| Perfil | Usuarios | spawn_rate | Duración | RPS | p95 | Errores | Umbral | Hipótesis previa | Conclusión |
|---|---|---|---|---|---|---|---|---|---|
| **Smoke** | 1 | 1/s | 30 s | 0.60 | 150 ms | 0.00 % | cumplido | Todo responde, 0 errores, p95 muy por debajo de 1 s | Se cumple. 17 peticiones, ningún fallo. Con 1 usuario no dio tiempo a tocar los siete destinos (`login` no salió sorteado): la cobertura de los siete la garantiza la comprobación previa de `test_start`, que sí los consulta y queda en el `.log` |
| **Load** | 5 | 1/s | 2 min | 3.02 | 140 ms | 0.00 % | Umbral cumplido, RPS ~3-5 impuesto por el cliente | Se cumple exactamente: 3.02 RPS, el techo que imponen 5 usuarios con pausa de 1-2 s. 365 peticiones sin un solo fallo |
| **Stress** | 2→20 en 7 etapas | 1-2/s | 3 min | 7.01 | 140 ms | 0.08 % | Degradación progresiva; incumplir el umbral entre 11 y 20 usuarios | **Refutada.** Con 20 usuarios el p95 siguió en 140 ms y los errores en 0.08 % (1 conexión caída de 1268). No hubo degradación: el sistema no llegó a su límite |
| **Spike** | 2→15→2 | 10/s en el salto | 2 min | 5.02 | 140 ms | 0.00 % | Pico de latencia al saltar y recuperación posterior | Pico mínimo y recuperación inmediata: al pasar de 2 a 15 usuarios el RPS subió de 1.1 a 9.5 y el p95 solo fue de 140 a 160 ms durante ~10 s, volviendo a 140 ms. Cero errores |
| **Soak** | 3 | 1/s | 4 min | 1.53 | 150 ms | **17.93 %** | Latencia plana; una pendiente indicaría fuga | **Incumple el umbral, pero no por lo que la hipótesis esperaba.** La latencia fue plana (p50 100 ms, p95 140 ms) durante los primeros 170 s; después la instancia dejó de responder. Ver el apartado siguiente |
| **Punto de quiebre** | 1→20, +1 cada 12 s | 1/s | 4 min (límite) | — | — | 100 % | Incumplir por p95 entre 8 y 15 usuarios | **NO VÁLIDO.** Se ejecutó contra una instancia que ya no servía: las 257 peticiones fallaron por conexión rechazada. No se puede estimar ningún punto de quiebre con estos datos |

## Tanda 1 · Lo que pasó en el soak: la instancia dejó de servir

Es el resultado más importante de la práctica y conviene contarlo con precisión, porque es fácil confundirlo con saturación.

**La secuencia medida**, leída de `evidencias/2026-10-30/soak.html` (gráficas) y de `soak_stats_history.csv`:

| Momento | Qué se observa |
|---|---|
| 15:48:04 → 15:50:45 (170 s) | Todo plano: 3 usuarios, ~1.9 RPS, p50 **100 ms**, p95 **140 ms**, cero fallos |
| ~15:50:50 | La latencia empieza a subir de golpe |
| 15:51:00 → 15:51:45 | **p50 y p95 llegan a 13 000-17 000 ms**: las peticiones se quedan colgadas, no son rechazadas. El RPS cae a **0.0** porque los tres usuarios están todos esperando |
| 15:51:30 → 15:52:00 | Empiezan a vencer los tiempos límite de 15 s: los fallos por segundo suben a ~2.1. Los 66 fallos se reparten por **los siete destinos a la vez** |
| 16:05 (ya sin carga) | Los siete puertos **rechazan** la conexión al instante, mientras ICMP y SSH siguen bien |

**El matiz importante.** La caída tuvo dos fases distintas y conviene no confundirlas: primero los servicios **aceptaron conexiones y dejaron de contestar** (de ahí los 13-17 s colgados hasta el tiempo límite), y solo después **dejaron de escuchar** (de ahí el rechazo instantáneo del final). Un proceso muerto rechaza de inmediato; colgarse antes indica que los procesos seguían vivos pero sin poder avanzar.

**Por qué no es saturación por la carga de la prueba.** Dos razones:

1. Los siete destinos son **procesos distintos** —uno de Node y seis de Flask—. Que se cuelguen a la vez no se explica por la carga de ninguno de ellos por separado; apunta a un recurso compartido de la máquina.
2. La carga era de **3 usuarios**, la más baja de todos los perfiles. Cinco minutos antes el mismo sistema había aguantado **20 usuarios a 12 RPS con p95 de 140 ms** y un único fallo.

El patrón —colgarse primero, morir después, los siete a la vez, con una carga trivial— es el de un **agotamiento de recursos en la instancia** (memoria, CPU o conexiones), no el de un servicio que no da abasto. Pero eso es una lectura del síntoma, no una causa comprobada.

**Qué se comprobó después, a las 16:05.** Con la instancia ya sin tráfico de prueba:

```
ICMP  (ping)        5 paquetes, 0 % de pérdida, 24 ms de ida y vuelta
TCP   22 (ssh)      ABIERTO
TCP   3000, 5000, 5001, 5002, 5003, 5004, 5005   conexión rechazada
```

La máquina está viva y su red funciona —responde al ping y acepta SSH desde esta misma IP—, pero **ningún proceso escucha ya en los siete puertos de aplicación**. Eso descarta un bloqueo de red contra el equipo que genera la carga: si fuera un cortafuegos contra esta IP, el 22 también estaría cerrado.

Las capturas de `evidencias/2026-10-30/capturas/04_soak_graficas_caida_de_la_instancia.jpg` muestran las dos gráficas que sostienen todo lo anterior.

**Qué queda sin saber, y por qué.** No se pudo determinar *por qué* se cayeron los siete procesos —si fue el matador por falta de memoria del núcleo, un reinicio de la instancia o una parada manual— porque el acceso por SSH a la instancia exige una llave que no está en este equipo. Esa comprobación hay que hacerla en la máquina (`systemctl status` de las seis unidades y del monolito, y `journalctl` alrededor de las 21:51 UTC del 2026-10-30). **No se especula con la causa: se registra el síntoma.**

## Tanda 1 · Pruebas que no se pudieron completar

| Prueba | Estado | Motivo |
|---|---|---|
| **Punto de quiebre** | **No completada** | Se ejecutó entre las 15:52 y las 16:05 contra una instancia que ya no aceptaba conexiones. Las 257 peticiones fallaron, de modo que no hay ninguna medición de la que estimar el quiebre. Hay que repetirla con los servicios en pie |
| **Soak** | **Completada, con la segunda mitad inválida** | Los primeros 170 s son datos buenos (latencia plana, sin fallos); el resto mide la caída, no la resistencia a carga sostenida |
| Operaciones de negocio de `users`, `pedidos` y `pagos` | No ejecutadas | No tienen lecturas públicas y sus operaciones son escrituras. Ver el apartado "Qué NO mide esta prueba" |

Además, durante la corrida del perfil de quiebre se descubrió **un defecto en el propio `locustfile.py`**: al evaluar el umbral con el destino caído, el greenlet de la forma de carga moría en silencio y la prueba, que debía durar 4 minutos, siguió 13 hasta que se detuvo a mano. Ya está corregido —el cálculo va dentro de un `try`, y si no hay ninguna petición con éxito el perfil se aborta diciendo "destino caído" en lugar de declarar un punto de quiebre falso con 2 usuarios—. **La corrida de `quiebre` que está en `evidencias/2026-10-30/` es la que falló**; se conserva como evidencia de lo ocurrido, no como medición.

## Tanda 1 · Hipótesis contra resultados: qué se refutó

1. **"El monolito tendrá p95 más alto que el microservicio en el catálogo." REFUTADA, y al revés de lo esperado.** Con 20 usuarios, en `stress`:

   | Operación | Monolito (HTML) | books (JSON) |
   |---|---|---|
   | Catálogo completo | p50 **95 ms** · p95 140 ms · 16.7 KB | p50 **140 ms** · p95 150 ms · 18.9 KB |
   | Detalle de un libro | p50 **51 ms** · p95 100 ms | p50 **100 ms** · p95 110 ms |
   | Búsqueda | p50 **94 ms** · p95 140 ms | p50 **100 ms** · p95 140 ms |

   El monolito renderiza una plantilla EJS y aun así es más rápido. La causa se comprobó mirando las cabeceras, no suponiéndola:

   ```
   monolito :3000   Connection: keep-alive   Keep-Alive: timeout=5
   books    :5001   Server: Werkzeug/3.1.9   Connection: close
   authors  :5003   Server: Werkzeug/3.1.9   Connection: close
   ```

   Los seis microservicios corren con el **servidor de desarrollo de Flask (Werkzeug)**, que cierra la conexión en cada respuesta: cada petición paga un saludo TCP nuevo. El ping a la instancia es de ~24 ms, y un saludo TCP cuesta una ida y vuelta: eso explica casi exactamente los ~45-50 ms de diferencia. **La diferencia que mide esta prueba es de transporte, no de arquitectura.** Comparar monolito contra microservicios con esta configuración mide sobre todo quién reutiliza la conexión.

2. **"El primero en degradarse será el que más trabajo hace por petición." No se pudo comprobar**: dentro de los límites del enunciado ningún destino se degradó. El único fallo de `stress` fue una conexión caída en la búsqueda del monolito, y 66 de los 66 fallos del `soak` son la caída general, no una ruta concreta.

3. **"El punto de quiebre estará entre 8 y 15 usuarios." No se pudo comprobar** por la caída descrita arriba. Lo que sí quedó medido es que **20 usuarios no bastan para degradar el sistema**: `stress` terminó con p95 de 140 ms y 0.08 % de errores. El punto de quiebre está por encima de 20 usuarios con esta pausa entre tareas, y no se puede acotar más con estos datos.

4. **La caché de Redis funciona y se nota**: entre el 59 % y el 72 % de las lecturas del catálogo se sirvieron con `X-Cache: HIT` en los cuatro perfiles válidos.

---

## Desviaciones respecto al enunciado, y por qué

Se registran en lugar de disimularlas.

1. **No existe `levanta_todo.ps1` ni `README.md` en la raíz del repositorio.** Comprobado con `find` sobre todo el monorepo: los únicos `.ps1` son los `Activate.ps1` de los entornos virtuales. Las instrucciones 1 a 3 (preparar PostgreSQL según el README de la raíz y levantar los servicios con ese script en PowerShell) no se pueden seguir tal como están escritas.
2. **La preparación de PostgreSQL se verificó por el único camino disponible: `/health`.** Los seis declaran `database: library_db`, `schema: library`, `server: PostgreSQL 16.14` y `redis: ok`. Eso confirma que la base está en pie, accesible y con el esquema esperado; no sustituye a un README que diga qué migraciones deben estar aplicadas.
3. **La carga se generó desde macOS, no desde PowerShell.** El enunciado menciona PowerShell para levantar los servicios en el equipo local; aquí no se levantó nada en local porque el enunciado también exige apuntar a la instancia y **no** a `localhost`. El único papel del equipo es generar carga.
4. **El mapa de puertos del enunciado no coincide con la realidad.** El enunciado dice `pagos 5002, pedidos 5003, users 5004, autores 5005`. La instancia responde `users 5002, authors 5003, pedidos 5004, pagos 5005`, y no es una suposición: `GET /?format=json` de cada puerto declara su propio nombre de servicio, y el arranque de cada corrida lo vuelve a comprobar y lo deja escrito en el `.log`.
5. **Hubo que levantar seis de los siete componentes, y eso cambió lo que se mide.** Tras el reinicio del 2026-11-01 solo `library-login` arrancó solo. Al habilitar las unidades de systemd arrancó el despliegue de `/opt/library/*`, que **no** es el mismo código que se midió el 30-oct: de ahí que haya dos tandas y no una. El monolito, que no tiene unidad de systemd, hubo que lanzarlo a mano.
6. **Los seis microservicios escuchaban solo en `127.0.0.1`.** Las unidades traían `--bind 127.0.0.1:<puerto>` (salvo login). Se cambiaron a `0.0.0.0` para poder medirlos desde fuera, con copia de seguridad de cada unidad. Es un cambio de despliegue, no de la aplicación, pero queda anotado porque afecta a lo que se puede medir.
7. **Hubo que abrir los puertos 5002-5005 en el cortafuegos de GCP**, que no tenían ninguna regla (la de 5004 existía pero apuntaba al tag `library-server`, que la instancia no tiene, y a la IP de la propia VM como origen: nunca aplicó). Conviene cerrarlos al terminar.
8. **No se usaron credenciales.** Las rutas que exigen `Authorization: Bearer` se prueban exigiendo el `401`, que ejercita la cadena de autorización completa sin tocar datos y sin guardar secretos en el archivo entregado. La consecuencia es que **el par comparable de la tanda 2 no es válido**: el catálogo del monolito exige sesión y se midió como 302. El `locustfile.py` admite credenciales por variable de entorno para medirlo de verdad.

## Pruebas que no se pudieron completar

| Prueba | Tanda | Estado | Motivo |
|---|---|---|---|
| **Punto de quiebre** | 1 (30-oct) | **No completada** | Se ejecutó contra una instancia que ya no aceptaba conexiones: las 257 peticiones fallaron. Se conserva como evidencia de lo ocurrido, no como medición |
| **Punto de quiebre** | 2 (01-nov) | **Completada y válida** | 240 s, hasta 20 usuarios, 12.5 RPS, p95 140 ms, cero fallos. No se alcanzó el umbral: el quiebre está por encima de 20 usuarios |
| **Soak** | 1 (30-oct) | Completada, segunda mitad inválida | Los primeros 170 s son datos buenos; el resto mide la caída de la instancia |
| **Soak** | 2 (01-nov) | Completada | Cuatro minutos planos, cero fallos. La caída de octubre no se reprodujo |
| **Stress** | 2 (01-nov) | **Válida para los seis microservicios; inválida para el monolito** | Los seis dan 871 peticiones sin un fallo. Los 386 fallos del monolito **no son de carga**: systemd retiró el cgroup de la sesión SSH y mató el proceso un segundo antes del primer fallo. Hay que repetirla con el monolito bajo una unidad de systemd |
| **El par comparable del catálogo** | 2 (01-nov) | **No medido** | El catálogo del monolito exige sesión y no se usaron credenciales: se midió el 302, no la página |
| **Causa de la caída del monolito** | 2 (01-nov) | **Resuelta** | `session-39.scope: Deactivated` a las 23:03:08 UTC y primer fallo a las 23:03:09. Lo mató systemd al cerrar la sesión SSH, no la carga |
| Operaciones de negocio de `users`, `pedidos` y `pagos` | ambas | No ejecutadas | No tienen lecturas públicas y sus operaciones son escrituras |

## Qué NO miden estas pruebas, en las dos tandas

1. **Las operaciones de negocio de `users`, `pedidos` y `pagos`.** No tienen lecturas públicas: crear un pedido o registrar un cobro son escrituras, y el enunciado pide preferir lecturas que no cambien datos. De ellos se mide `/health` (que ejerce PostgreSQL y Redis) y el rechazo `401` (que ejerce la verificación del JWT contra Redis). **Su p95 bajo no significa que sean más rápidos: significa que se les está midiendo menos trabajo.**
2. **La capacidad máxima del sistema.** Lo medido es lo observado en corridas de 4 minutos, con pausa de 1-2 s entre tareas, desde un equipo doméstico y por Internet hasta GCP. "No se alcanzó el quiebre con 20 usuarios" no es lo mismo que "aguanta 20 usuarios".
3. **Ningún destino recibió los 20 usuarios.** La carga se reparte entre los destinos disponibles según los pesos de las tareas, de modo que el número de usuarios del perfil es la concurrencia del **sistema completo**, no la de un servicio aislado.
4. **Nada del interior de la máquina**: ni CPU, ni memoria, ni conexiones de PostgreSQL. Locust solo ve lo que ve un cliente desde fuera.
