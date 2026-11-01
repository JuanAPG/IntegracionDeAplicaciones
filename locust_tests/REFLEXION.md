# Reflexión

Pruebas de rendimiento con Locust sobre la Librería en Línea · instancia `34.51.65.207` · 2026-10-30. Todos los números citados salen de `evidencias/` y de las tablas de [`RESULTADOS.md`](RESULTADOS.md). No hay ninguna cifra estimada.

## 1. ¿Qué diferencias observaste entre el monolito y los microservicios? ¿Qué evidencia las sustenta?

La diferencia medible fue **la contraria a la que esperaba**: el monolito resultó más rápido. Con 20 usuarios (perfil `stress`, 1268 peticiones), el catálogo del monolito dio **p50 de 95 ms** contra los **140 ms** del mismo catálogo en `books`, y el detalle de un libro **51 ms** contra **100 ms**. Y eso pese a que el monolito sirve HTML renderizado con EJS (16.7 KB) y el microservicio solo serializa JSON (18.9 KB).

La evidencia que explica la diferencia no está en los tiempos, sino en las cabeceras:

```
monolito :3000   Connection: keep-alive   Keep-Alive: timeout=5
books    :5001   Server: Werkzeug/3.1.9   Connection: close
```

Los seis microservicios corren con el **servidor de desarrollo de Flask**, que cierra la conexión tras cada respuesta. Cada petición paga un saludo TCP nuevo, y el ping a la instancia es de ~24 ms: un saludo cuesta una ida y vuelta, lo que cuadra casi exactamente con los 45-50 ms de diferencia observados. El monolito, con Express y keep-alive, reutiliza la conexión.

**Por eso la conclusión honesta es que esta prueba no compara arquitecturas: compara configuraciones de despliegue.** Para comparar monolito contra microservicios habría que servir los seis con gunicorn y keep-alive; mientras no sea así, cualquier ventaja del monolito se explica por el transporte. Es la lección que más me costó aceptar, porque el resultado numérico invitaba a concluir lo contrario.

## 2. ¿Qué servicio o ruta mostró primero degradación y cómo lo determinaste?

**Ninguno se degradó por carga dentro de los límites del enunciado**, y decirlo así es más exacto que señalar un culpable. En `stress`, con 20 usuarios y 7 RPS, el p95 global se quedó en 140 ms —siete veces por debajo del umbral de 1 s— con un 0.08 % de errores (1 fallo de 1268: una conexión caída en la búsqueda del monolito).

Lo que sí ocurrió fue una **caída completa de la instancia durante el soak**, y lo determiné por tres indicios, no por uno:

1. Los 66 fallos aparecieron en **los siete destinos a la vez**, que son siete procesos distintos: ninguna carga individual explica eso.
2. Sucedió con **3 usuarios**, la carga más baja de la práctica, cuarenta minutos después de aguantar 20 sin esfuerzo.
3. El patrón fue **colgarse y después morir**: el p50 y el p95 saltaron de 100 y 140 ms a **13 000-17 000 ms** —el techo del tiempo límite de 15 s— antes de que apareciera un solo fallo, y el RPS cayó a cero porque los tres usuarios estaban todos esperando. Horas después, los puertos ya rechazaban la conexión al instante. Un proceso muerto rechaza de inmediato; colgarse primero indica procesos vivos que no podían avanzar, que es la firma de un recurso agotado en la máquina.

La confirmación llegó al terminar: ICMP respondía con 0 % de pérdida, el puerto 22 aceptaba conexiones desde esta misma IP, y los siete puertos de aplicación rechazaban la conexión. La máquina estaba viva; los procesos, no. La causa raíz no la pude establecer porque el SSH a la instancia pide una llave que no está en este equipo, y **no la invento**: queda como comprobación pendiente en la máquina (`systemctl status` y `journalctl` alrededor de las 21:51 UTC).

## 3. ¿Qué diferencias hubo entre load, stress, spike, soak y punto de quiebre?

Cada perfil responde a una pregunta distinta, y en esta corrida se vio con claridad:

- **Load** (5 usuarios, 2 min) mide el régimen esperado. Dio 3.02 RPS y 0 % de errores. Lo interesante es que **ese RPS lo impuso el cliente, no el servidor**: 5 usuarios con pausa de 1-2 s no pueden pedir más. Un load nunca mide capacidad.
- **Stress** (2→20 por etapas) busca el punto donde se dobla la curva. No se dobló: siete escalones y el p95 inmóvil en 140 ms. La conclusión útil es negativa —"20 usuarios no bastan"—, y es un resultado, no un fracaso.
- **Spike** (2→15 de golpe y vuelta a 2) mide dos cosas que el stress no ve: el golpe y la **recuperación**. El RPS pasó de 1.1 a 9.5 en cinco segundos, el p95 subió de 140 a 160 ms durante unos diez segundos y volvió a 140. La recuperación fue inmediata, que era la pregunta de verdad.
- **Soak** (3 usuarios, 4 min) no busca picos sino **deriva**. Fue el único que encontró algo, y precisamente porque mira el tiempo: 170 segundos planos y después la caída. Un stress de tres minutos no la habría visto.
- **Punto de quiebre** no es un perfil más: es un perfil **adaptativo**, que sube hasta incumplir el umbral y deja de subir. En esta corrida **no fue válido** porque se ejecutó contra la instancia ya caída y las 257 peticiones fallaron por conexión rechazada.

En una frase: load describe lo normal, stress busca el techo, spike mide el golpe y la recuperación, soak busca la deriva en el tiempo y el punto de quiebre busca una cifra concreta de concurrencia.

## 4. ¿Qué limitaciones tuvo la prueba?

**Duración.** Los seis perfiles suman unos 16 minutos. El soak de 4 minutos es una miniatura: una fuga de conexiones o de memoria puede tardar horas en manifestarse. El punto de quiebre sale de una ventana de 4 minutos, no de una curva de capacidad.

**Rutas.** Solo tres de los siete destinos tienen lecturas públicas de datos: monolito, books y authors. De `login`, `users`, `pedidos` y `pagos` únicamente se midieron `/health` y el rechazo `401`, porque sus operaciones de negocio son escrituras y el enunciado pide preferir lecturas que no cambien datos. Comparar su p95 con el del catálogo sería comparar cosas distintas.

**Datos.** El catálogo tiene 31 libros y 35 autores. Con ese volumen, PostgreSQL resuelve casi todo en memoria y la caché de Redis acierta mucho: la prueba mide el camino caliente, no el comportamiento con un catálogo grande ni con índices bajo presión.

**Equipo y red.** La carga se generó desde un portátil por Internet hasta GCP. Cada medición incluye el viaje de ida y vuelta, que en el smoke ya era del orden de 100 ms sin carga: ese suelo está dentro de todos los números y no es culpa del servidor. Además, un único generador de carga puede saturarse antes que el servidor; con las concurrencias de esta práctica no se llegó a ese punto, pero es un techo real.

**Generación de carga.** La pausa de 1-2 segundos entre tareas limita el RPS por diseño. El RPS observado dice cuánto pidieron estos clientes, no cuánto aguanta el sistema.

## 5. ¿Qué sugerencia de IA ayudó, qué hubo que corregir y qué aprendí?

**Lo que ayudó.** La estructura del archivo: separar los perfiles en una `LoadTestShape` controlada por una variable de entorno, en vez de seis archivos casi iguales, y validar el **cuerpo** de cada respuesta con `catch_response` en lugar de conformarse con el código de estado. Eso último resultó decisivo: varias respuestas con estado 200 no traían lo que debían.

**Lo que tuve que corregir y comprobar: la comprobación de los componentes y su integración.** No bastó con pedir el código; hubo que verificar uno por uno qué estaba realmente levantado y cómo encajaba:

- El mapa de puertos del enunciado está invertido respecto a lo desplegado. Lo comprobé pidiendo `/health` a cada puerto y leyendo el nombre del servicio que declara: `5002` es `users` y no `pagos`, `5004` es `orders` y no `users`. Si no lo llego a comprobar, las estadísticas habrían salido etiquetadas al revés.
- La versión desplegada no es la del repositorio, ni en `books` ni en el monolito: filtros en español, el JSON envuelto en `libros`, el detalle por ISBN, y rutas enteras que en el repo existen y en la instancia dan 404. Todas las rutas del `locustfile.py` se verificaron con `curl` contra la instancia antes de escribir una sola aserción.
- Una primera versión repartía la carga en siete clases de usuario, una por destino. Al ejecutar el smoke de **1 usuario** descubrí que Locust le asigna ese único usuario a **una** clase: seis destinos se quedaron sin una sola petición. Lo reestructuré a una clase que recorre los siete con URL absoluta.
- La búsqueda del monolito (`?q=`) busca por título o ISBN, no por autor ni género: términos como `orwell` devolvían cero resultados y una página sin tarjetas, y mi aserción los contaba como fallo del servicio. Corregí los términos en vez de aflojar la aserción.

**Lo que aprendí por mi cuenta.** Que una prueba de carga es, antes que nada, una prueba de integración: el 90 % del trabajo fue verificar qué componentes estaban arriba, en qué puerto, con qué contrato y qué devuelven de verdad. Un `locustfile` escrito contra la documentación habría corrido sin errores y habría medido mentiras.

## 6. ¿Qué cambiaría en la arquitectura o en la siguiente prueba?

**En la arquitectura.**

1. **Alinear lo desplegado con el repositorio.** Hoy conviven dos implementaciones distintas de `books` y del monolito. Cualquier medición envejece mal mientras eso siga así, y un cliente escrito contra el repo falla contra la instancia.
2. **Servir los servicios con gunicorn y no con el servidor de desarrollo.** La cabecera `Server: Werkzeug` y el `Connection: close` de `books` indican que no hay reutilización de conexión: cada petición paga un saludo TCP nuevo.
3. **Dar al monolito una ruta de salud.** Es el único de los siete sin `/health`, y por eso hay que usar la portada como sustituto, que consulta la base y no distingue "vivo" de "sano".

**En la siguiente prueba.**

1. Medir **un destino a la vez** con toda la concurrencia, en lugar de repartir los usuarios entre siete. El número de usuarios de esta práctica es la concurrencia del sistema completo; para hablar de la capacidad de `books` hay que apuntarle solo a él.
2. Bajar la pausa entre tareas para que el RPS lo imponga el servidor y no el cliente.
3. Incluir las operaciones de negocio de `pedidos` y `pagos` contra una base de datos de pruebas desechable, que es la única forma honesta de medir escrituras.
4. Alargar el soak a horas y vigilar a la vez las conexiones de PostgreSQL y la memoria de los procesos, que es donde se vería una fuga.

## 7. ¿Qué indican las gráficas?

Las gráficas están en los reportes HTML de `evidencias/` (`load.html`, `stress.html`, `spike.html`, `soak.html`), cada uno con tres paneles: peticiones por segundo, tiempos de respuesta (mediana y p95) y usuarios activos. Lo que muestran, perfil por perfil:

**`load.html` — tres líneas planas.** El panel de usuarios sube en escalera de 0 a 5 durante los primeros cinco segundos y se queda horizontal. El de RPS se estabiliza en ~3 y no se mueve. El de tiempos muestra la mediana y el p95 pegados y rectos (100 y 140 ms). Tres líneas planas es exactamente lo que debe dar un load sano: el sistema absorbe la carga esperada sin que nada se acumule.

**`stress.html` — la escalera que no se traduce en latencia.** El panel de usuarios dibuja los siete escalones (2, 5, 8, 11, 14, 17, 20) y el de RPS los copia fielmente, subiendo hasta ~7. La gráfica importante es la tercera: **el p95 sigue plano mientras el RPS se multiplica por siete**. Cuando un sistema se acerca a su límite, esa línea se despega de la mediana y empieza a trepar; aquí no lo hace. Es la prueba visual de que el cuello de botella no se alcanzó.

**`spike.html` — el pico y la cicatriz que no queda.** En el segundo 25 el panel de usuarios da un salto vertical de 2 a 15 y el de RPS salta con él, de 1.1 a 9.5. En el panel de tiempos se ve un diente pequeño —de 140 a 160 ms— que dura unos diez segundos y desaparece. En el segundo 85 los usuarios vuelven a 2 y el RPS baja en rampa, no en vertical: son las peticiones ya en vuelo terminándose. Que **no quede escalón** en la línea de latencia después del pico es lo que indica que no hubo cola acumulada ni conexiones agotadas.

**`soak.html` — la gráfica que delata la caída.** Es la única con forma interesante y hay que leer los tres paneles juntos (captura en `evidencias/capturas/04_soak_graficas_caida_de_la_instancia.jpg`).

El panel de usuarios es una línea recta en 3 de principio a fin: **la carga nunca varió**, lo que descarta de entrada que el cambio venga del cliente. El de RPS va plano en ~1.9 durante 170 segundos y entonces **se desploma a cero** a las 15:51:00; la línea roja de fallos por segundo, que estuvo pegada al eje toda la prueba, despega después, hacia las 15:51:30, y llega a ~2.1.

Ese desfase entre las dos líneas rojas y verdes es la clave, y se explica con el tercer panel: los tiempos de respuesta, que iban en 100 ms (mediana) y 140 ms (p95), **saltan a 13 000-17 000 ms**. Es decir, las peticiones no fallaron: **se quedaron colgadas** hasta agotar el tiempo límite de 15 segundos. El RPS cayó a cero porque los tres usuarios virtuales estaban los tres esperando a la vez, y los fallos aparecieron 30 segundos más tarde, cuando vencieron esos tiempos límite.

Leer esa secuencia correctamente cambia el diagnóstico. Si fuera saturación por la carga, la latencia subiría **progresivamente** con el RPS, y aquí saltó de 140 ms al techo de golpe, con 3 usuarios y después de haber aguantado 20. Si los procesos hubieran muerto de golpe, no habría habido cuelgue: una conexión a un puerto sin nadie escuchando se rechaza en milisegundos, que es justo lo que se midió más tarde, a las 16:05. La forma de la gráfica dice que los servicios **seguían vivos pero no podían avanzar**, y que murieron después.

**Qué no muestran las gráficas.** No muestran nada de la instancia: ni CPU, ni memoria, ni conexiones de PostgreSQL, ni el estado de Redis. Locust solo ve lo que ve un cliente desde fuera. Para explicar *por qué* cayeron los siete procesos hace falta mirar la máquina por dentro, y eso es justo lo que quedó pendiente.
