# Reflexión

Pruebas de rendimiento con Locust sobre la Librería en Línea, instancia `maquina-01` de GCP. **Dos tandas** contra **dos despliegues distintos**: 2026-10-30 (procesos lanzados a mano, Werkzeug) y 2026-11-01 (el despliegue del repositorio, gunicorn). Todos los números salen de `evidencias/` y de las tablas de [`RESULTADOS.md`](RESULTADOS.md). No hay ninguna cifra estimada.

## 1. ¿Qué diferencias observaste entre el monolito y los microservicios? ¿Qué evidencia las sustenta?

**En latencia, el monolito salió más rápido en las dos tandas, y en las dos por el mismo motivo, que no es la arquitectura.**

En octubre, con 20 usuarios, el catálogo del monolito dio p50 de **95 ms** contra los **140 ms** del mismo catálogo en `books`, y el detalle **51 ms** contra **100 ms** — y eso sirviendo HTML renderizado con EJS (16.7 KB) frente a JSON (18.9 KB). La explicación no estaba en los tiempos sino en las cabeceras:

```
monolito :3000   Connection: keep-alive   Keep-Alive: timeout=5
books    :5001   Server: Werkzeug/3.1.9   Connection: close
```

Mi conclusión entonces fue "los seis corren con el servidor de desarrollo de Flask, que cierra la conexión". **La segunda tanda la corrigió.** Ahora los seis corren con **gunicorn**, y al volver a mirar la cabecera:

```
books :5001   Server: gunicorn   Connection: close
```

Sigue cerrando. El worker síncrono de gunicorn tampoco mantiene la conexión viva, así que cada petición sigue pagando un saludo TCP completo —unos 24 ms de ida y vuelta hasta GCP—. **La causa no era "Werkzeug": era la pila Flask tal como está desplegada, con cualquiera de los dos servidores.** Me pareció importante corregirlo en vez de dejar la frase de octubre, que sonaba bien y era falsa.

**En robustez creí ver una diferencia enorme, y era un espejismo.** En el `stress` del 1-nov los 386 fallos fueron todos del monolito (401 peticiones, 386 fallidas) mientras los seis microservicios hacían 871 sin uno. Escribí que el monolito era el primero en caerse. **Al buscarle la causa resultó que no se cayó por la carga**: la consola serie muestra `session-39.scope: Deactivated` a las 23:03:08 UTC y el primer fallo a las 23:03:09 — systemd retiró el cgroup de mi sesión SSH y se llevó el proceso de Node con él. El log de la aplicación no tiene ni una traza de error, que es justo lo que se espera de un proceso matado desde fuera.

Así que la respuesta honesta es que **en robustez esta prueba no encontró diferencia**: ningún componente se degradó por carga en ninguna de las dos tandas. Lo que sí quedó, y es un hallazgo de despliegue y no de rendimiento, es que el monolito es el único de los siete sin unidad de systemd — por eso no sobrevivió al reinicio de la VM ni al cierre de una sesión SSH.

La comparación de latencia de la tanda 2, eso sí, **no es válida**: el catálogo de este monolito exige sesión y no usé credenciales, de modo que sus tareas midieron un **302** —enrutado y comprobación de sesión— y no una consulta con su plantilla. Que aparezca con 52-96 ms frente a 140-150 ms de `books` no dice que sea más rápido: dice que se le midió menos trabajo. Prefiero decirlo así que presentar un número que favorece la conclusión fácil.

## 2. ¿Qué servicio o ruta mostró primero degradación y cómo lo determinaste?

**Ninguno se degradó por carga**, en ninguna de las dos tandas, y llegar a esa respuesta costó descartar dos falsos positivos.

**El falso positivo de noviembre.** Los 386 fallos del `stress` eran todos del monolito y la conclusión se ofrecía sola: "el monolito es el primero en caerse". Antes de darla por buena fui a la causa:

| Hora (UTC) | Evento |
|---|---|
| 22:57:49 | `Started session-39.scope — Session 39 of User jgalvann`: la sesión SSH desde la que se lanzó `npm start` |
| **23:03:08** | **`session-39.scope: Deactivated. Consumed 1.813s CPU time, 111.1M memory peak`** |
| **23:03:09** | **primer fallo del monolito en Locust** |

Un segundo. **systemd eliminó el cgroup de la sesión y mató el proceso**; `nohup` protege de SIGHUP pero no de eso. Lo confirman dos comprobaciones más: el log de la aplicación no tiene ni una traza de error —lo propio de un proceso terminado desde fuera—, y los únicos dos avisos de falta de memoria de esa ventana son posteriores (23:11 y 23:15) y de workers de los microservicios, que siguieron sirviendo sin fallar. Además el monolito había completado el `load` entero con cero fallos cinco minutos antes.

**El falso positivo de octubre**, al revés: ahí sí hubo una caída real, pero de la instancia entera durante el soak —los siete componentes a la vez, con 3 usuarios, cuarenta minutos después de aguantar 20—. La diagnostiqué por tres indicios: siete procesos distintos cayendo a la vez; la carga más baja de la práctica; y el patrón de **colgarse y después morir** (p50 y p95 saltaron de 100 y 140 ms a 13 000-17 000 ms antes de que apareciera un solo fallo, y el RPS cayó a cero porque los tres usuarios estaban los tres esperando). La consola serie mostró después 45 líneas de `Worker was sent SIGKILL! Perhaps out of memory?`, lo que **corrobora** el agotamiento de memoria de la máquina — aunque la ventana exacta no quedó registrada, así que es respaldo y no prueba.

**La lección de las dos.** Un fallo concentrado en un componente parece degradación de ese componente, y casi nunca lo es sin más. La pregunta "¿qué se degradó primero?" solo se puede responder después de descartar que el componente muriera por algo ajeno a la prueba — y las dos veces que la respuesta parecía evidente, la causa estaba fuera de la carga.

## 3. ¿Qué diferencias hubo entre load, stress, spike, soak y punto de quiebre?

Cada perfil responde a una pregunta distinta, y en estas dos tandas se vio con claridad:

- **Load** (5 usuarios, 2 min) mide el régimen esperado: 3.08 RPS y 0 % de errores. Lo importante es que **ese RPS lo impuso el cliente, no el servidor**: 5 usuarios con pausa de 1-2 s no pueden pedir más. Un load nunca mide capacidad.
- **Stress** (2→20 por etapas) busca dónde se dobla la curva. No se dobló: siete escalones y el p95 inmóvil en 140 ms, con los seis microservicios a cero fallos. La conclusión útil es negativa —"20 usuarios no bastan"— y es un resultado, no un fracaso. El monolito figura con 386 fallos, pero por la muerte del proceso que se explica en la pregunta 2, no por la rampa.
- **Spike** (2→15 de golpe y vuelta a 2) mide dos cosas que el stress no ve: el golpe y la **recuperación**. Cero errores, p95 de 140 ms, recuperación inmediata.
- **Soak** (3 usuarios, 4 min) no busca picos sino **deriva**. En octubre fue el único que encontró algo, y precisamente porque mira el tiempo: 170 segundos planos y después la caída. En noviembre, cuatro minutos planos y cero fallos: **la caída no se reprodujo**, que es un resultado y no un no-resultado.
- **Punto de quiebre** no es un perfil más: es **adaptativo**, sube hasta incumplir el umbral y deja de subir. En octubre no fue válido (se ejecutó contra la instancia ya caída). En noviembre **sí**: 240 s completos, hasta 20 usuarios, 12.5 RPS sostenidos, p95 clavado en 140 ms y cero fallos. **No se alcanzó el quiebre**, y eso también responde la pregunta: está por encima de 20 usuarios en estas condiciones.

En una frase: load describe lo normal, stress busca el techo, spike mide el golpe y la recuperación, soak busca la deriva en el tiempo, y el punto de quiebre busca una cifra concreta de concurrencia.

## 4. ¿Qué limitaciones tuvo la prueba?

**Duración.** Los seis perfiles suman ~16 minutos. El soak de 4 minutos es una miniatura: una fuga de conexiones o de memoria puede tardar horas. El punto de quiebre sale de una ventana de 4 minutos, no de una curva de capacidad.

**Rutas.** Solo tres de los siete destinos tienen lecturas públicas de datos. De `login`, `users`, `pedidos` y `pagos` se midieron `/health`, `/metrics` y el rechazo `401`. Y `/envios/<numero>`, la única ruta pública de pedidos, devuelve 404 siempre porque **no hay ningún pedido en la base**: lo que mide es la consulta que acaba en 404.

**El monolito, mal medido por partida doble.** Sin credenciales, su catálogo es un 302 y la única lectura real suya es la portada: el par comparable —el núcleo de la práctica— quedó sin medir. Y en el `stress` el proceso murió por el cierre de la sesión SSH, de modo que esa corrida tampoco mide su comportamiento bajo carga.

**Datos.** 16 libros y 24 autores (31 y 35 en octubre). Con ese volumen PostgreSQL resuelve casi todo en memoria y Redis acierta entre el 43 % y el 55 % de las veces: se mide el camino caliente, no un catálogo grande.

**Equipo y red.** La carga se generó desde un portátil por Internet hasta GCP. Cada medición incluye el viaje de ida y vuelta (~24 ms), que está dentro de todos los números y no es culpa del servidor.

**Generación de carga.** La pausa de 1-2 s entre tareas limita el RPS por diseño. El RPS observado dice cuánto pidieron estos clientes, no cuánto aguanta el sistema.

**Dos despliegues.** La mitad del trabajo de la segunda tanda fue descubrir que ya no medía lo mismo. Los números de las dos tandas **no se comparan entre sí**.

## 5. ¿Qué sugerencia de IA ayudó, qué hubo que corregir y qué aprendí?

**Lo que ayudó.** Dos cosas, y las dos estructurales. La primera, meter los seis perfiles en una `LoadTestShape` controlada por una variable de entorno en vez de seis archivos casi iguales. La segunda, y más valiosa: **validar el cuerpo de cada respuesta** con `catch_response` en lugar de conformarse con el código de estado. Resultó decisivo — sin eso, media tanda habría pasado midiendo otra cosa.

**Lo que tuve que corregir y comprobar.** El grueso del trabajo, y casi todo fue verificar componentes e integración:

- **El mapa de puertos del enunciado está invertido.** Lo comprobé pidiendo la identidad a cada puerto y leyendo el nombre del servicio que declara: `5002` es `users`, no `pagos`. Sin comprobarlo, las estadísticas habrían salido etiquetadas al revés.
- **Una primera versión repartía la carga en siete clases de usuario.** Al ejecutar el smoke de **1 usuario** descubrí que Locust le asigna ese único usuario a **una** clase: seis destinos se quedaron sin una sola petición. Lo reestructuré a una clase que recorre los siete con URL absoluta.
- **El despliegue cambió debajo de la prueba.** Tras el reinicio, lo que arrancó systemd no era lo que se midió el 30-oct: cambiaron las rutas, las claves del JSON, los filtros (de español a inglés), la visibilidad de `/metrics` y hasta los datos. Tuve que reinventariar las rutas con `curl` y rehacer todas las aserciones. **Lo peor fue que los filtros viejos no dan error: se ignoran en silencio** y devuelven el catálogo entero con `filters` vacío. Una aserción escrita contra el contrato viejo habría pasado tan campante midiendo una cosa distinta, así que la tarea de búsqueda ahora comprueba que `filters` no venga vacío.
- **Un defecto en el propio `locustfile.py` que descubrí ejecutando:** el sondeo de arranque usaba el límite de 15 s de las peticiones normales. Con cuatro destinos caídos eso son 60 s bloqueando el arranque — más que el perfil smoke entero (30 s), así que la prueba terminaba **sin lanzar ni una petición**. Ahora el sondeo tiene su propio límite de 3 s.
- **Y antes, otro peor:** al evaluar el umbral con el destino caído, una excepción mataba en silencio el greenlet de la forma de carga y la prueba seguía indefinidamente — 4 minutos previstos, 13 reales. El cálculo va ahora dentro de un `try`, y si no hay ni una petición con éxito el perfil se aborta declarando "destino caído" en vez de inventar un punto de quiebre falso con 2 usuarios.

- **Y la corrección más importante, que por poco no hago.** Con los 386 fallos del monolito delante, escribí que era el primero en degradarse bajo carga: encajaba con el relato esperable y con lo que la práctica parecía buscar. Al ir a la consola serie a buscar la causa, la respuesta fue la contraria —systemd mató el proceso al cerrarse mi sesión SSH, un segundo antes del primer fallo— y hubo que rehacer el apartado entero. **La conclusión cómoda era la falsa, y solo se cayó al pedirle evidencia.**

**Lo que aprendí por mi cuenta.** Que una prueba de carga es, antes que nada, **una prueba de integración**: el 90 % del trabajo fue verificar qué estaba arriba, en qué puerto, con qué contrato y qué devuelve de verdad. Un `locustfile` escrito contra la documentación habría corrido sin errores y habría medido mentiras. Y una segunda lección, más incómoda, que esta práctica me enseñó **dos veces**: **cuando un número confirma lo que esperabas, es cuando más hay que buscarle la causa**. La ventaja de latencia del monolito encajaba con un relato razonable ("hace menos saltos") y resultó ser un saludo TCP. Los 386 fallos del monolito encajaban con otro relato razonable ("el monolito escala peor") y resultaron ser systemd cerrando un cgroup. Las dos veces el número era correcto y la explicación, inventada.

## 6. ¿Qué cambiaría en la arquitectura o en la siguiente prueba?

**En la arquitectura.**

1. **Dar al monolito una unidad de systemd con `Restart=always`.** Es el único de los siete sin supervisor, y eso costó caro dos veces: no sobrevivió al reinicio de la VM, y murió a mitad del `stress` porque un `npm start` lanzado desde una sesión SSH vive dentro del cgroup de esa sesión. Una unidad del sistema no depende de que haya alguien conectado.
2. **Servir los seis con un worker que mantenga la conexión viva** (gunicorn con `gthread`/`uvicorn`, o un proxy delante). Hoy, con gunicorn síncrono, cada petición paga un saludo TCP nuevo, y eso es la mitad de la latencia medida.
3. **Dar al monolito una ruta de salud.** Es el único sin `/health`, y hay que usar la portada como sustituto, que consulta la base y no distingue "vivo" de "sano".
4. **Alinear lo desplegado con el repositorio y dejarlo en systemd.** Que convivieran dos implementaciones distintas obligó a medir dos veces y a tirar la comparación entre tandas.

**En la siguiente prueba.**

1. **Medir el par comparable de verdad**, con sesión en el monolito (`MONO_EMAIL`/`MONO_PASSWORD`, que el `locustfile.py` ya admite). Sin eso, la comparación central de la práctica no existe.
2. **Repetir el stress con el monolito supervisado**, para separar "se cayó por la carga" de "se cayó porque lo lancé a mano".
3. **Medir un destino a la vez** con toda la concurrencia, en lugar de repartir los usuarios entre siete.
4. **Bajar la pausa entre tareas** para que el RPS lo imponga el servidor y no el cliente, y subir por encima de 20 usuarios: ahí no está el quiebre.
5. **Vigilar la máquina por dentro** (CPU, memoria, conexiones de PostgreSQL) a la vez que se genera la carga. Las dos incógnitas que quedaron abiertas —la caída de octubre y la del monolito— se habrían resuelto solas con eso.

## 7. ¿Qué indican las gráficas?

Los reportes HTML de `evidencias/2026-11-01/` y `evidencias/2026-10-30/` traen tres paneles cada uno: peticiones por segundo, tiempos de respuesta (mediana y p95) y usuarios activos. Hay que leerlos **juntos**: casi todo el diagnóstico sale de comparar un panel con otro.

**`quiebre.html` (1-nov) — la escalera que no se traduce en latencia.** Es la gráfica más informativa de las dos tandas (captura en `evidencias/2026-11-01/capturas/01_quiebre_graficas_rps_latencia_y_fallos.jpg`). El panel de usuarios sube en escalera recta de 1 a 20, un peldaño cada 12 segundos. El de RPS **la copia fielmente**, de ~0.6 a 12.5. Y el tercero, el de tiempos, **se queda plano**: la mediana en 95 ms y el p95 en 140 ms de principio a fin, con la línea de fallos pegada al eje. Lo que indica es que el sistema todavía está en su zona lineal: **el trabajo entra, se despacha y no se acumula**. Cuando un sistema se acerca a su límite, el p95 se despega de la mediana y empieza a trepar mientras el RPS deja de subir aunque entren más usuarios. Aquí no pasa ninguna de las dos cosas, y por eso la conclusión es "el quiebre está más arriba" y no "aguanta justo 20".

**`stress.html` (1-nov) — dos sistemas en la misma gráfica** (capturas `02_stress_fallos_suben_con_la_latencia_plana.jpg` y `03_stress_los_386_fallos_son_del_monolito.jpg`). El panel de RPS sube con la escalera de usuarios hasta ~7 y luego **pierde altura**, y la línea roja de fallos despega a los 50 segundos y ya no vuelve a bajar. Pero el panel de tiempos **sigue plano en 140 ms**. Esa combinación —fallos subiendo con la latencia quieta— es la firma de un componente que **deja de aceptar conexiones** en vez de ponerse lento: una conexión rechazada se resuelve en milisegundos, de modo que no mueve el percentil, solo el contador de errores. Si el sistema estuviera saturado, la latencia subiría *antes* que los fallos. **Y esa forma es justamente la que hay que saber leer**: dice "aquí hay un proceso que ya no está", no "aquí hay un sistema saturado". La causa resultó ser systemd cerrando el cgroup de la sesión SSH (pregunta 2), y la gráfica era compatible con eso desde el principio.

**`soak.html` (1-nov) — tres líneas planas, y eso es la noticia.** Usuarios en 3, RPS en ~1.8, mediana y p95 pegadas en 98 y 140 ms durante los cuatro minutos. Comparada con la de octubre vale por sí sola: **la caída no se reprodujo**.

**`soak.html` (30-oct) — la gráfica que delata la caída.** La única con forma interesante, y hay que leer los tres paneles juntos (captura en `evidencias/2026-10-30/capturas/04_soak_graficas_caida_de_la_instancia.jpg`). El panel de usuarios es una recta en 3 de principio a fin: **la carga nunca varió**, lo que descarta de entrada que el cambio venga del cliente. El de RPS va plano en ~1.9 durante 170 segundos y **se desploma a cero**; la línea de fallos, pegada al eje toda la prueba, despega **30 segundos más tarde**. Ese desfase es la clave, y lo explica el tercer panel: los tiempos, que iban en 100 y 140 ms, **saltan a 13 000-17 000 ms**. Las peticiones no fallaron: **se quedaron colgadas** hasta agotar el límite de 15 s. El RPS cayó a cero porque los tres usuarios estaban los tres esperando, y los fallos aparecieron cuando vencieron esos plazos.

Leer esa secuencia correctamente cambia el diagnóstico. Si fuera saturación, la latencia subiría **progresivamente** con el RPS; aquí saltó al techo de golpe, con 3 usuarios y después de haber aguantado 20. Si los procesos hubieran muerto de golpe, no habría habido cuelgue: un puerto sin nadie escuchando rechaza en milisegundos — que es justo lo que se midió horas después. **La forma de la gráfica dice que los servicios seguían vivos pero no podían avanzar, y que murieron después.**

**`stress.html` (30-oct) — la escalera sin consecuencias.** Siete peldaños de 2 a 20 usuarios, el RPS copiándolos hasta ~12 y el p95 inmóvil en 140 ms. La prueba visual de que, con aquel despliegue, 20 usuarios tampoco bastaban.

**Qué NO muestran las gráficas.** Nada del interior de la instancia: ni CPU, ni memoria, ni conexiones de PostgreSQL, ni el estado de Redis. Locust solo ve lo que ve un cliente desde fuera. Para explicar *por qué* cayeron los siete procesos en octubre, o *por qué* murió el monolito en noviembre, hace falta mirar la máquina por dentro — y eso es justo lo que quedó pendiente las dos veces.
