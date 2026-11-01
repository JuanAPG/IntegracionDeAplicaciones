# Hipótesis previas a la ejecución

> Escrito **antes** de lanzar las corridas, como exige el enunciado. Se conserva
> sin retocar para poder comparar lo esperado con lo medido en `RESULTADOS.md`.
> Fecha: 2026-10-30. Instancia: `34.51.65.207`. Carga generada desde el equipo
> local (macOS) contra GCP.

## Umbral de servicio

El del enunciado, sin modificar: **p95 > 1000 ms** o **errores > 5 %** ⇒ degradado.
No se justifica ningún umbral distinto porque no se cambió ninguno.

## Lo que espero observar, por perfil

| Perfil | Hipótesis |
|---|---|
| **Smoke** (1 usuario, 30 s) | Todas las rutas responden; 0 % de errores; p95 muy por debajo de 1 s. Si algo falla aquí es un error de ruta o de aserción, no de capacidad. Espero que el latido de red Monterrey→GCP domine el tiempo (~40-80 ms por petición). |
| **Load** (5 usuarios, rampa 1/s, 2 min) | Umbral cumplido en los siete destinos. El RPS debe quedar en ~3-5 (lo imponen 5 usuarios con pausa de 1-2 s, no el servidor). El p95 del catálogo del monolito debe ser mayor que el de `/health`, porque renderiza plantilla y consulta la base. |
| **Stress** (2→20 por etapas, 3 min) | Degradación progresiva visible en escalones. Espero que **el monolito se degrade antes que los microservicios de lectura cacheada**: `[books] GET /books?format=json` suele salir de Redis (`X-Cache: HIT`) mientras el catálogo del monolito renderiza EJS cada vez. Espero incumplir el umbral en algún punto entre 11 y 20 usuarios. |
| **Spike** (2→15 de golpe, vuelve a 2, 2 min) | Pico de latencia en los primeros segundos tras el salto y recuperación al volver a 2 usuarios. La pregunta real es si **recupera**: si el p95 no vuelve a su valor inicial, hay cola o conexiones agotadas, no solo saturación momentánea. |
| **Soak** (3 usuarios, 4 min) | Umbral cumplido y latencia **plana**. Una pendiente creciente con carga constante indicaría fuga (conexiones de PostgreSQL sin devolver, memoria del proceso, `MemoryStore` de sesiones del monolito emitiendo cookie en cada petición). |
| **Punto de quiebre** (1→20, +1 cada 12 s, 4 min) | Que se incumpla el umbral por **p95** antes que por errores: espero ver la latencia subir mucho antes de que empiecen a caer conexiones. Estimo el incumplimiento en el rango de 8 a 15 usuarios. Este número será el punto de quiebre **observado en 4 minutos desde este equipo**, no la capacidad máxima del sistema. |

## Hipótesis sobre la comparación de arquitecturas

1. **El monolito tendrá p95 más alto en el catálogo** que el microservicio `books`, porque sirve 16.7 KB de HTML renderizado con EJS y el microservicio sirve JSON que, además, puede venir de la caché de Redis.
2. **Los cuatro servicios sin lectura pública** (`login`, `users`, `pedidos`, `pagos`) tendrán el p95 más bajo de todos: `/health` y el rechazo 401 son operaciones cortas. Eso **no** significa que sean "más rápidos" como servicios: significa que se les está midiendo menos trabajo. Es la limitación principal de esta comparación y conviene no olvidarla al leer la tabla.
3. **El primero en degradarse** debería ser el destino con más trabajo por petición: el catálogo del monolito, o la búsqueda filtrada de `books` (`?<filtros>`), que casi siempre es `MISS` de caché y va a PostgreSQL.
4. La carga se reparte por igual entre los siete destinos (siete clases de usuario con `weight = 1`), de modo que con 20 usuarios cada destino recibe ~3 clientes virtuales. **Ningún destino ve los 20 usuarios**: es una prueba del sistema completo, no de un servicio aislado a 20 usuarios.

---

# Hipótesis de la segunda tanda (2026-11-01)

> Escritas **antes** de ejecutar, igual que las de arriba, y sin retocar
> después. Fecha: 2026-11-01. Instancia: `34.51.89.203`.

## Por qué hay una segunda tanda

El 2026-11-01 se reinició la instancia. Lo que servía el 30-oct eran
procesos lanzados a mano que **no** eran el código del repositorio; al
habilitar las unidades de systemd arrancó el despliegue de
`/opt/library/*`, que sí lo es. Cambiaron las rutas, las claves del JSON,
los filtros (de español a inglés), la visibilidad de `/metrics` y, sobre
todo, **el servidor**: ahora los seis corren con **gunicorn y 3 workers**.
El `locustfile.py` se rehízo contra ese contrato. La tanda de octubre se
conserva íntegra en `evidencias/2026-10-30/`.

## Umbral

El mismo del enunciado, sin cambios: **p95 > 1000 ms** o **errores > 5 %**.

## Lo que espero observar

| Perfil | Hipótesis |
|---|---|
| **Smoke** (1 usuario, 30 s) | 0 % de errores y p95 por debajo de 300 ms. Si algo falla aquí es contrato, no capacidad. |
| **Load** (5 usuarios, 2 min) | Umbral cumplido en los siete destinos. RPS ~3-5, impuesto por el cliente. |
| **Stress** (2→20, 3 min) | Con **tres workers por servicio** en vez de uno, espero **menos** degradación que en octubre, no más: el cuello de botella de un solo proceso desaparece. Sigo esperando no alcanzar el límite con 20 usuarios. |
| **Spike** (2→15→2, 2 min) | Pico pequeño y recuperación inmediata. Con tres workers el pico debería notarse **menos** que en octubre (160 ms). |
| **Soak** (3 usuarios, 4 min) | Latencia plana y umbral cumplido. Si vuelve a aparecer la caída de octubre con 3 usuarios, ya no sería casualidad y apuntaría a la instancia, no a la carga. |
| **Punto de quiebre** (1→20, 4 min) | **No espero alcanzarlo.** En octubre 20 usuarios no bastaron con un servidor peor; con gunicorn deberían bastar todavía menos. Lo probable es terminar los 4 minutos sin incumplir, y eso también es un resultado: el quiebre está por encima de 20 usuarios con esta pausa entre tareas. |

## Hipótesis sobre la comparación de arquitecturas

1. **La diferencia monolito-microservicios de octubre debería encogerse.**
   Aquella ventaja del monolito se explicó por el transporte: Werkzeug
   cerraba la conexión en cada respuesta y Express la reutilizaba. Con
   gunicorn esperaba keep-alive… pero al comprobar las cabeceras **sigue
   saliendo `Connection: close`** (gunicorn con workers sync tampoco lo
   mantiene). Predicción, entonces: **la diferencia se mantiene**, y la
   causa no era "Werkzeug" sino "la pila Flask tal como está desplegada".
   Es una corrección a la conclusión de octubre que esta tanda permite
   contrastar.
2. **El monolito queda mal medido en esta tanda, y no por su culpa.** Su
   catálogo exige sesión y no se dieron credenciales, de modo que las
   tres tareas del catálogo miden un **302** —enrutado + comprobación de
   sesión— y no una consulta ni un renderizado. Espero por eso que el
   monolito salga artificialmente rápido. **No debe leerse como que el
   monolito es más rápido**: se le está midiendo menos trabajo. La única
   lectura real suya es la portada, que sí consulta la base.
3. **`books` será el destino con más trabajo por petición** y, si algo se
   degrada primero, espero que sea su búsqueda filtrada, que casi siempre
   es MISS de caché.
4. El catálogo ahora tiene **16 libros y 24 autores** (en octubre eran 31
   y 35). Con menos datos, menos trabajo por consulta: otro motivo para
   no comparar los números absolutos de las dos tandas.
