# Cliente de escritorio Java para la Librería en Línea
### Integración de aplicaciones · UDEM

---

# A. Explicación de la aplicación

## A.1 Objetivo

Construir una aplicación de escritorio en Java que actúe como cliente de la
arquitectura de microservicios que ya existe en el monorepo, y demostrar con
ella cómo tecnologías distintas —REST, WebSockets, JWT, PostgreSQL detrás de
servicios, un mapa web embebido en una ventana nativa— se integran en un solo
sistema distribuido que funciona.

La aplicación permite autenticarse, consultar el catálogo, armar una cesta,
simular una compra contra los servicios reales de pedidos y pagos, revisar las
compras anteriores y seguir la entrega sobre un mapa de Monterrey que se mueve
en tiempo real.

## A.2 Arquitectura de componentes

```
┌──────────────────────────── EQUIPO LOCAL ────────────────────────────┐
│                                                                      │
│   Aplicación JavaFX                      Servidor de rastreo         │
│   ┌───────────────────────┐              ┌──────────────────────┐    │
│   │ Login · Catálogo      │              │ Flask + Flask-Sock   │    │
│   │ Cesta · Mis compras   │              │ :5900                │    │
│   │ Rastreo (WebView)     │◄────────────►│ /ws?code=LIB-MTY-…   │    │
│   │   Leaflet + OSM       │  WebSocket   │ simulación GPS       │    │
│   └───────────┬───────────┘   JSON       └──────────┬───────────┘    │
│               │                                     │                │
└───────────────┼─────────────────────────────────────┼────────────────┘
                │  REST / JSON / JWT                  │ REST (verifica
                │                                     │  de quién es
                ▼                                     ▼  el pedido)
┌──────────────────────── INSTANCIA DE GCP ────────────────────────────┐
│  login :5000   books :5001   users :5002                             │
│  authors :5003   pedidos :5004   pagos :5005                         │
│         │           │          │         │         │                 │
│         └───────────┴──────────┴─────────┴─────────┘                 │
│                            PostgreSQL + Redis                        │
└──────────────────────────────────────────────────────────────────────┘
```

Tres observaciones sobre este dibujo:

1. **No hay ninguna flecha de Java a PostgreSQL**, y es el punto de la
   práctica. El `pom.xml` no tiene driver de base de datos; si algún día
   aparece uno, es que alguien se saltó la arquitectura.
2. **El servidor de rastreo también es cliente de los microservicios.** No
   decide por su cuenta de quién es un pedido: se lo pregunta al servicio de
   pedidos con el token del propio usuario.
3. **El WebSocket lo habla Java, no la página.** El mapa es solo una
   superficie de dibujo a la que Java le empuja coordenadas.

## A.3 Tecnologías

| Componente | Tecnología | Por qué esa |
|---|---|---|
| Cliente | Java 21+ | Lo pide el enunciado |
| Interfaz | JavaFX 25 | `WebView` permite embeber el mapa; Swing no trae navegador |
| HTTP | `java.net.http.HttpClient` | Viene en el JDK desde 11: una dependencia menos |
| WebSocket | `java.net.http.WebSocket` | Igual, y **sí permite cabeceras en el handshake** |
| JSON | Jackson Databind | Única dependencia externa real |
| Autenticación | JWT HS256 (`Authorization: Bearer`) | El que ya emiten los servicios |
| Tiempo real | WebSocket | Ver la reflexión, punto B.2 |
| Servidor de rastreo | Flask + Flask-Sock | Lo pide el enunciado y es el del proyecto de referencia |
| Mapa | Leaflet 1.9 + OpenStreetMap | Sin clave de API ni cuota |
| Rutas | Polilíneas OSRM cacheadas | Calles reales, sin depender de la red en caliente |
| Infraestructura | Google Cloud Platform | Los seis servicios ya están desplegados ahí |
| Base de datos | PostgreSQL, **solo a través de los servicios** | Requisito de la arquitectura |

## A.4 Microservicios consumidos y operaciones

| Servicio | Operación | Para qué | Auth |
|---|---|---|---|
| login 5000 | `POST /login` | Obtener el JWT | — |
| | `POST /refresh` | Renovar antes de que caduque | — |
| | `POST /logout` | **Revocar** el token en los seis servicios | Bearer |
| | `GET /session` | Comprobar si la sesión sigue viva | Bearer |
| users 5002 | `GET /users/<id>` | El perfil del usuario autenticado | Bearer |
| books 5001 | `GET /books?output=json&q=…` | Catálogo y búsqueda | pública |
| | `GET /books/<id>` | Ficha y revalidación de la cesta | pública |
| authors 5003 | `GET /authors/<id>` | Obras del autor en la ficha del libro | pública |
| pedidos 5004 | `POST /pedidos` | Crear el pedido | Bearer |
| | `GET /pedidos` | Mis compras | Bearer |
| | `GET /pedidos/<id>` | Detalle con las líneas | Bearer |
| | `GET /pedidos/numero/<n>` | Lo usa el servidor de rastreo para autorizar | Bearer |
| pagos 5005 | `GET /metodos` | Métodos de pago disponibles | Bearer |
| | `GET /pedidos/<id>/saldo` | Cuánto hay que cobrar | Bearer |
| | `POST /pagos` | Registrar el cobro | Bearer |
| | `GET /pagos?orderId=` | Estado de los pagos de un pedido | Bearer |

Ninguna ruta se inventó: todas salen del código de los servicios
(`app.py`, `openapi.py`, serializadores) y de comprobarlas contra la instancia.

**Dos detalles del contrato que condicionan el cliente:**

- En **books** el parámetro de representación es `?output=json` y no
  `?format=json`, porque en ese servicio `format` es *además* un filtro del
  catálogo (Físico, Digital, Audiolibro). En los otros cinco es `?format=json`.
  Está resuelto en el `enum Service`, no repartido por las llamadas.
- `GET /pedidos/<id>/saldo` **vive en pagos (5005)**, aunque la ruta empiece
  por `/pedidos`. Es el error de dirección más fácil de cometer.

## A.5 Autenticación con JWT

1. `POST /login` con correo y contraseña. La respuesta trae el JWT en el campo
   **`token`** (no `accessToken`), un `refreshToken` opaco, `expiresIn` (1800 s)
   y `renewBefore` (300 s).
2. La contraseña **no se guarda en ninguna parte**: ni en disco, ni en un campo,
   ni para reintentar. Se borra del formulario en cuanto el login responde.
3. Cada petición protegida lleva `Authorization: Bearer <token>`. El token nunca
   viaja por la URL.
4. **Se renueva antes del 401, no con el 401.** Antes de cada petición se mira
   el `exp` del propio token; si faltan menos de `renewBefore` segundos, se
   renueva primero. Gastar un 401 para enterarse significa que una operación de
   negocio falla a mitad.
5. Si aun así llega un 401, se renueva y se reintenta **exactamente una vez**.
   Ni cero (daría un error espurio al cruzar los 30 minutos) ni dos (un token
   revocado de verdad produciría un bucle contra el servidor).
6. El refresco es **de un solo uso con rotación**: cada renovación trae uno
   nuevo y el anterior muere.
7. `logout` **manda el Bearer**, no solo borra lo local: eso es lo que mete el
   `jti` en la lista de revocación de Redis y mata el token en los seis
   servicios al instante.
8. Los claims (`exp`, `role`, `user_id`) se leen decodificando Base64URL **sin
   verificar la firma**, y solo para decidir cuándo renovar y qué enseñar. La
   autorización de verdad la aplica cada microservicio.

## A.6 La cesta y la simulación de compra

La cesta vive **en memoria** dentro de la aplicación: no hay microservicio de
cesta y no se inventó uno. Permite agregar, cambiar cantidades, quitar y ver
subtotal y total.

Los importes que muestra son **una estimación**, y la pantalla lo dice. El
importe que vale lo calcula el servidor.

Al confirmar, el flujo es:

1. **Revalidar** contra el catálogo: se vuelven a pedir los libros y se avisa de
   cambios de precio o de existencias. Es cortesía, no autoridad.
2. **`POST /pedidos`** con las líneas (`bookId`, `quantity`) y la dirección.
   **El precio no se envía**: lo congela el procedimiento almacenado leyéndolo
   del catálogo dentro de la misma transacción en que reserva las existencias.
   Mandarlo permitiría comprar al precio que eligiera el cliente.
3. **`GET /pedidos/<id>/saldo`** para saber cuánto cobrar. Se usa `balance` y no
   `total`: el servicio rechaza con 409 un pago que exceda lo comprometido.
4. **`POST /pagos`** con una **clave de idempotencia generada una vez por
   diálogo**, no por clic: un doble clic devuelve el mismo pago con
   `idempotentReplay: true` en lugar de cobrar dos veces.
5. Se enseña el **estado real**. Si el método exige autorización, el pago nace
   `autorizado` y el pedido sigue pendiente; la aplicación lo dice en vez de
   fingir una compra liquidada. Solo con `efectivo` el pago nace `aplicado` y un
   disparador de PostgreSQL pasa el pedido a `pagado`.

**No se piden ni se envían datos de tarjeta.** El servicio rechaza con 400
cualquier cuerpo con `cardNumber`, `cvv`, `pan` o `titular`.

## A.7 El código de rastreo

Se deriva del número **real** del pedido:

```
PED-000042   →   LIB-MTY-2026-000042
```

**Por qué derivarlo en vez de leerlo del servicio.** El servicio de pedidos
tiene un campo `trackingCode`, pero escribirlo exige el permiso
`orders:status`, que un usuario normal no tiene: `PUT /pedidos/<id>/estado`
devuelve 403 incluso sobre el propio pedido. Para un cliente corriente ese campo
es siempre `null`. En lugar de pedir permisos de staff o inventar un endpoint,
el seguimiento se ancla al identificador real del pedido —que sí existe y sí se
puede comprobar—, que es justo lo que el enunciado permite cuando el servicio no
ofrece seguimiento.

El servidor de rastreo hace el camino inverso (`LIB-MTY-2026-000042` →
`PED-000042`) y le pregunta al servicio de pedidos si ese pedido es de quien lo
pide.

## A.8 El seguimiento por WebSockets

**Flujo completo**

```
Flask-Sock  ──WS──►  TrackingSocket (Java)  ──executeScript──►  Leaflet (WebView)
```

**Autorización, en dos comprobaciones.** Los códigos son correlativos y
adivinarlos es trivial, así que la autorización no es decorativa:

1. **La firma del token**, verificada con el mismo secreto HS256 que usan los
   seis servicios, exigiendo el emisor y rechazando `alg: none`.
2. **La propiedad del pedido**, preguntándosela al servicio de pedidos con el
   token del usuario: 200 es suyo; 403 o 404 no lo es. Si el servicio no
   responde, **no se enseña nada** (fallo seguro).

**Por qué el WebSocket está en Java y no en la página.** Además de que el
enunciado lo pide, el WebSocket de un navegador no permite poner cabeceras en el
handshake: el token tendría que ir en la URL, donde acaba en los registros del
servidor. Desde Java va como `Authorization: Bearer`.

**El protocolo, en cuatro mensajes** (servidor → cliente):

| Mensaje | Cuándo | Qué trae |
|---|---|---|
| `snapshot` | una vez, al conectar | ruta completa, estela recorrida, posición, estados |
| `posicion` | cada segundo en movimiento | lat, lon, rumbo, velocidad, progreso, ETA |
| `estado` | solo cuando el estado **cambia** | el estado nuevo |
| `error` | antes de cerrar | el motivo del rechazo |

**La simulación.** Las coordenadas no están escritas a mano ni son líneas
rectas: `rutas_monterrey.json` son 120 tramos entre 16 puntos de Monterrey
calculados con OSRM y cacheados, de modo que el vehículo circula por calles.
El destino de cada entrega se deriva del código con SHA-256, así que **cada
código tiene su propia ruta** y el mismo código da siempre la misma, incluso
tras reiniciar el servidor.

**Los cinco estados** avanzan solos: *Pedido confirmado* → *Preparando pedido* →
*Pedido enviado* → *En ruta de entrega* → *Entregado*. El último se alcanza
**al consumir el último punto de la ruta**, no por un temporizador. Es la
diferencia de fondo con el proyecto de referencia, donde los vehículos daban
vueltas en un bucle infinito que nunca terminaba.

El reloj de la simulación va acelerado ×10 y la pantalla lo dice: a 35 km/h
reales la ruta más larga tardaría 29 minutos. Se acelera el **reloj**, no la
velocidad, que es lo que hace cualquier simulador.

## A.9 Evidencias

| Evidencia | Estado |
|---|---|
| El proyecto compila (`mvn compile`) | ✅ verificado |
| La aplicación arranca y pinta el login | ✅ captura adjunta |
| El servidor de rastreo responde `/health` | ✅ verificado |
| El WebSocket entrega `snapshot`, `estado` y `posicion` | ✅ verificado con un cliente real |
| La máquina de estados llega a «Entregado» al acabar la ruta | ✅ verificado |
| Cada código produce una ruta y un destino distintos | ✅ verificado |
| El mapa pinta la ruta por calles y mueve el vehículo | ✅ captura adjunta |
| Login real, catálogo, compra y pago contra la instancia | ⏳ **pendiente: los siete componentes de la VM están caídos** |

**Sobre lo pendiente, con precisión:** el 2026-10-30 a las 15:51, durante una
prueba de carga, los siete componentes de la instancia dejaron de responder.
A día de hoy la máquina sigue viva (ICMP y SSH responden) pero ningún proceso
escucha en los puertos 3000 y 5000-5005. Las pantallas que dependen de esos
servicios no se pueden evidenciar hasta reiniciarlos. **No se sustituyeron por
respuestas simuladas**: el enunciado lo prohíbe expresamente y una captura de
datos inventados no demostraría nada.

---

# B. Reflexión sobre tecnologías de integración

## B.1 REST

REST encaja con estas operaciones porque todas son **peticiones puntuales con
una respuesta**: dame el catálogo, créame este pedido, cóbrame esto. El cliente
pregunta, el servidor contesta y la conversación termina. Encima, cada
operación cae de forma natural en un verbo con un significado ya acordado —`GET`
no cambia nada, `POST` crea— y eso hace que un cliente nuevo se escriba leyendo
la documentación y no el código del servidor.

Frente a conectar la aplicación directamente a la base de datos, la ventaja es
que **las reglas del negocio se aplican una sola vez y en un solo sitio**. Al
crear un pedido, el servicio congela el precio desde el catálogo y reserva las
existencias en la misma transacción. Una aplicación con acceso directo a SQL
tendría que repetir esa lógica, y a la tercera aplicación alguien la copiaría
mal. Además, el cliente no necesita saber qué tablas hay: si mañana se parte
`books` en dos, la aplicación Java no se entera. Y hay un argumento de
seguridad que pesa solo: para hablar con la base habría que repartir la
contraseña de PostgreSQL entre todos los clientes, y una contraseña repartida
es una contraseña filtrada.

## B.2 WebSockets

Para un vehículo que se mueve, el servidor **siempre tiene algo nuevo que
contar**, y REST obliga a preguntarlo. Con sondeo cada segundo, cada posición
cuesta un saludo TCP, unas cabeceras HTTP y una petición completa; si se
pregunta cada cinco segundos para ahorrar, el coche se mueve a saltos.

El WebSocket invierte la relación: la conexión se abre una vez y el servidor
habla cuando quiere. Las diferencias concretas son tres: **latencia** (la
posición llega cuando ocurre, no en el siguiente sondeo), **gasto** (una
trama de unas decenas de bytes contra una petición HTTP entera) y **dirección**
(el servidor puede avisar de un cambio de estado sin que nadie pregunte).

Hay un cuarto motivo menos obvio: con sondeo, el cliente tiene que llevar la
cuenta de qué ya vio para no repetir trabajo. Con WebSocket el servidor manda
un `snapshot` al conectar y después solo lo que cambia, y esa separación
—estado completo una vez, incrementos después— simplifica las dos puntas.

## B.3 SOAP

REST y SOAP resuelven lo mismo de maneras casi opuestas. REST es un estilo:
URLs que son recursos, verbos HTTP, y el formato lo eliges tú (aquí, JSON).
SOAP es un **protocolo**: un sobre XML obligatorio, un contrato formal en WSDL
que describe cada operación y cada tipo, y una familia de extensiones
(WS-Security, WS-ReliableMessaging, WS-AtomicTransaction) para firma, cifrado,
entrega garantizada y transacciones distribuidas.

SOAP conviene cuando **el contrato tiene que ser inapelable**: banca, seguros,
salud, aduanas, facturación electrónica. Ahí el WSDL es un documento que dos
organizaciones firman, y las herramientas generan el cliente y el servidor a
partir de él, de modo que un campo de más no compila en vez de descubrirse en
producción. También cuando hace falta firmar un mensaje concreto y que la firma
viaje con él, o cuando una operación debe abarcar varios sistemas en una sola
transacción. El precio es verbosidad y rigidez: cambiar un campo obliga a
regenerar clientes.

En Java la integración es directa, y es uno de los entornos donde mejor
soportado está: `wsimport` (o el plugin `jaxws-maven-plugin`, o `cxf-codegen`)
lee el WSDL y genera las clases del cliente; después se invoca el servicio como
si fueran métodos locales. En este proyecto hay un módulo SOAP real —el de
clasificación en la nube de `library_soap_service`, con su WSDL— que sería el
candidato natural para esa demostración.

## B.4 Google Cloud Platform

Lo que aporta: la instancia está encendida y accesible desde cualquier parte sin
montar nada en casa, se puede redimensionar sin reinstalar, tiene copias e
imágenes, y el cortafuegos se declara como reglas en vez de depender del router
de alguien.

Lo que implica que la aplicación Java corra en local contra servicios en la
nube, en los cuatro ejes que pide la pregunta:

- **Disponibilidad.** Deja de depender de tu equipo y pasa a depender de la
  instancia, y eso corta en los dos sentidos. En este mismo proyecto los siete
  componentes llevan días caídos: la aplicación está perfecta y no se puede
  usar. Un cliente de escritorio tiene que tratar la nube como algo que falla:
  por eso aquí hay semáforos de tres estados y mensajes que dicen qué hacer.
- **Seguridad.** El tráfico sale a Internet. Hoy va en HTTP plano, de modo que
  **el JWT viaja legible**: quien esté en medio puede copiarlo y usarlo hasta
  que caduque. Lo correcto sería HTTPS con un proxy inverso. Además, cada
  puerto abierto es superficie expuesta, y el 6379 de Redis —donde viven las
  sesiones y la lista de revocación— no debería estar abierto al mundo.
- **Latencia.** Medida: ~24 ms de ida y vuelta hasta la instancia. Eso es el
  **suelo** de toda operación; en una red local serían microsegundos. Se nota
  más de lo que parece, porque cada petición lo paga: por eso la aplicación hace
  el trabajo de red fuera del hilo de la interfaz y pide páginas de 24 libros en
  lugar de uno por uno.
- **Escalabilidad.** Con microservicios se puede crecer solo la pieza que lo
  necesita —replicar books sin tocar pagos—, pero eso solo funciona si el
  estado no está en el proceso. Aquí las sesiones están en Redis y no en memoria
  de cada servicio, que es justo lo que permite poner una segunda copia detrás
  de un balanceador. El servidor de rastreo, en cambio, **guarda el estado en
  memoria** y por eso no se puede replicar tal cual: es una limitación conocida.

## B.5 PostgreSQL

Es la fuente de verdad del sistema: usuarios, libros, autores, existencias,
pedidos, líneas, pagos y la bitácora de estados. Redis guarda lo volátil
—sesiones, caché, revocación—; PostgreSQL guarda lo que tiene que sobrevivir.

Que solo los servicios la toquen no es burocracia. Tres razones concretas de
este proyecto:

1. **Las reglas viven en la base y hay que atravesarlas.** El paso de un pedido
   a `pagado` lo decide un **disparador** cuando los pagos aplicados cubren el
   total, y otro disparador impide transiciones inválidas. Un cliente con `UPDATE`
   podría poner `entregado` un pedido sin pagar.
2. **Atomicidad.** Crear un pedido es congelar precios, descontar existencias y
   escribir las líneas **en una sola transacción**. Repartido entre clientes, el
   primer corte de red deja existencias descontadas sin pedido.
3. **Credenciales.** Acceso directo significa repartir la contraseña de la base
   a cada aplicación, y con ella se puede leer y borrar todo. Un JWT, en cambio,
   caduca en 30 minutos, se puede revocar al instante y lleva un rol que limita
   qué puede hacer su portador.

A lo que se suma lo evidente: la base puede cambiar de forma sin que ningún
cliente se entere, mientras el contrato REST siga igual.

## B.6 Arquitecturas de comunicación

| | REST | WebSocket | SOAP |
|---|---|---|---|
| Conexión | una por petición | una, persistente | una por petición |
| Quién habla | solo el cliente pregunta | los dos, cuando quieran | solo el cliente |
| Contrato | por convención (OpenAPI) | el que acuerdes | formal y obligatorio (WSDL) |
| Formato | libre (JSON) | libre (JSON) | XML con sobre |
| Estado | sin estado | con estado (la conexión) | sin estado |
| Cuesta | cabeceras en cada petición | mantener la conexión abierta | verbosidad del XML |

**Qué usaría para cada cosa, y por qué:**

- **Autenticación → REST.** Es una pregunta con respuesta que ocurre una vez.
  Una conexión persistente para eso no aporta nada, y sin estado es más fácil de
  escalar y de cachear. Eso sí: sobre HTTPS, que hoy falta.
- **Catálogo → REST.** Lecturas públicas, repetidas e idénticas entre usuarios:
  el caso perfecto para cachear, y el servicio ya lo hace en Redis con
  `X-Cache: HIT`. Un WebSocket aquí impediría aprovechar esa caché.
- **Pagos → REST, y con idempotencia.** Importa más que la operación sea
  inequívoca que que sea rápida: una petición con una clave de idempotencia se
  puede reintentar sin miedo. Si fuera una transacción entre bancos, con
  obligación de no repudio y firma por mensaje, **ahí sí consideraría SOAP** con
  WS-Security.
- **Rastreo GPS → WebSocket.** Es el único caso donde el servidor tiene algo
  nuevo continuamente y el cliente no sabe cuándo. Todo lo demás sería sondear.

La conclusión que me llevo es que la pregunta no es cuál es mejor, sino **quién
necesita hablar primero**. Si siempre pregunta el cliente, REST. Si el servidor
tiene que avisar, WebSocket. Si el contrato tiene que ser un documento que dos
organizaciones firman, SOAP.

---

# C. Reflexión sobre el uso de inteligencia artificial

**1. ¿Qué herramienta de IA utilizó?**
Claude Opus, a través de Claude Code, trabajando directamente sobre el
monorepo.

**2. ¿En qué actividades se apoyó en la IA?**
Únicamente en el desarrollo. El diseño y la arquitectura ya estaban planteados:
la decisión de qué microservicios existen, cómo se reparten las
responsabilidades, que la autorización se delegue en el servicio de pedidos y
que el cliente no toque la base, son decisiones tomadas antes de escribir
código. La IA escribió la implementación de esas decisiones y verificó los
contratos.

**3. ¿Qué instrucciones o prompts fueron más útiles?**
Dividir el trabajo en módulos y pedirlos por separado: autenticación, catálogo,
cesta, compra, mis compras y rastreo. Entregar el enunciado con los módulos ya
numerados hizo que cada parte se pudiera revisar por su cuenta en vez de
recibir un bloque entero imposible de auditar.

Dos instrucciones concretas resultaron más valiosas que el resto:

- **«No inventes rutas: sácalas del código de los microservicios.»** Esto evitó
  el fallo clásico de generar un cliente contra una API plausible pero
  inexistente. Antes de escribir una línea de Java se extrajeron los contratos
  reales de `app.py` y los serializadores de cada servicio.
- **«Si algo no existe, dilo en vez de rellenarlo.»** Gracias a eso salieron a
  la luz las limitaciones reales en lugar de quedar enterradas.

**4. ¿Qué errores o limitaciones presentó el código generado?**
El resultado de la primera versión fue bueno gracias al tipeo detallado de los
requerimientos, y la estructura no hubo que rehacerla. Lo que sí apareció
fueron **tres errores de compilación menores**, detectados al compilar y
corregidos en el momento:

- heredar de `PauseTransition`, que es una clase `final`;
- llamar a `Long.toHexString` con dos argumentos, que no existe;
- pesos de fuente `650` y `750` en el CSS, que JavaFX no acepta (solo múltiplos
  de 100).

Más interesantes que los errores fueron las **limitaciones de contexto**: la IA
no podía saber que el catálogo no tiene campo de sinopsis, ni que el
`trackingCode` del servicio es inescribible para un usuario normal, hasta que se
revisó el esquema y los permisos. Esas dos cosas cambiaron el diseño de dos
módulos, y ninguna se habría descubierto sin ir al código fuente de los
servicios.

**5. ¿Qué modificaciones realizó el equipo para que funcionara correctamente?**
Además de los tres arreglos de compilación:

- **El mapa de puertos del enunciado está invertido** respecto a lo desplegado
  (dice pagos 5002, pedidos 5003, users 5004, autores 5005; la instancia
  responde users 5002, authors 5003, orders 5004, payments 5005). Se comprobó
  pidiendo `/health` a cada puerto y leyendo el nombre que declara. Si se
  hubiera seguido el enunciado, la aplicación habría mandado los datos al
  servicio equivocado.
- **La ruta de los repartos nunca terminaba.** El proyecto de referencia recicla
  la ruta al llegar al final, de modo que el vehículo da vueltas para siempre.
  Hubo que sustituir ese reciclado por un estado terminal para que «Entregado»
  signifique algo.
- **La difusión del WebSocket iba a todos.** En el original, cualquier cliente
  recibía todos los vehículos. Se cambió a un diccionario de suscriptores por
  código para que cada quien vea únicamente su pedido.
- **Las fases previas a la salida pasaban demasiado rápido** al acelerar el
  reloj: los estados «confirmado» y «preparando» duraban décimas de segundo.
  Se dejaron en tiempo real y se aceleró solo el trayecto.
- **Las portadas:** se añadió la comprobación de que la imagen descargada tiene
  ancho real, porque un 302 con cero bytes no dispara ningún error y produce una
  imagen rota silenciosa.

**6. ¿Qué conceptos de integración comprendió mejor durante la práctica?**
La ventaja de incorporar WebSockets en una aplicación moderna: entender *cuándo*
una conexión persistente deja de ser un lujo y pasa a ser lo correcto —cuando es
el servidor quien tiene algo que decir y el cliente no sabe cuándo— y, sobre
todo, que esa decisión se toma por la dirección de la conversación y no por la
velocidad.

El segundo concepto fue **dónde vive la autorización**. La tentación era que el
servidor de rastreo decidiera por su cuenta de quién es cada pedido. Delegarlo
en el servicio de pedidos, con el token del propio usuario, deja la regla en un
solo sitio y evita mantener una copia de los datos que envejecería.

**7. ¿Qué partes del proyecto podría desarrollar sin asistencia de IA?**
El diseño de la arquitectura y la traducción de las necesidades del negocio a
requerimientos técnicos: decidir qué servicios existen, cómo se reparten las
responsabilidades, qué es público y qué no, dónde debe vivir cada regla y por
qué el cliente no debe tocar la base. Esa es la parte que no se delega, porque
requiere entender el problema antes de escribir la solución, y es también la que
determina si el código generado después sirve para algo o no.
