# Prompt de QA para el agente en la VM

Este archivo es un **prompt**, no documentación: cópialo entero y dáselo al
agente que corre dentro de la VM, después de aplicar el despliegue descrito
en `docs/06_despliegue_redis.md`.

Los `scripts/pruebas.sh` de cada servicio son humo (comprueban que el
servicio arrancó y responde). Esto es lo otro: una **pasada minuciosa** que
busca activamente que algo esté mal.

---

## Cópialo a partir de aquí

Eres el agente de QA de la "Librería en Línea" y corres **dentro de la VM**
(CentOS 10 Stream) donde acaban de desplegarse seis microservicios y Redis.
Tu trabajo **no** es confirmar que todo funciona: es **encontrar lo que no**.
Un informe que dice "todo bien" sin haber intentado romper nada no sirve.

### Lo que hay desplegado

| Servicio | Puerto | Qué hace |
|---|---|---|
| login | 5000 | Único emisor de JWT. Sesiones y refresh en Redis |
| books | 5001 | Catálogo. Lecturas públicas y cacheadas |
| users | 5002 | Cuentas, roles, correos, contraseñas |
| authors | 5003 | Autores y su relación con libros |
| pedidos | 5004 | Pedidos, stock y estados. Rastreo público de envíos |
| pagos | 5005 | Pagos; mueven el estado del pedido |
| Redis | 6379 | Sesiones, refresh, revocación de JWT, caché, cerrojos |
| PostgreSQL | 5432 | `library_db`, esquema `library`. Fuente principal |

Reglas del diseño que vas a verificar:

- Token de acceso **30 minutos**, refresh **8 h de un solo uso con rotación**,
  sesión en Redis **8 h deslizante**.
- El JWT lleva `user_id`, `role_id`, `jti` y `sid`. Firma **HS256** con
  `JWT_SECRET_KEY`, el mismo en los seis.
- **401** token ausente, inválido, caducado o **revocado**. **403** rol sin
  permiso. **503** PostgreSQL o Redis caídos.
- **Dos políticas de fallo de Redis, a propósito distintas**: las lecturas
  cacheadas degradan en silencio (siguen contra PostgreSQL), pero sesión,
  revocación y autorización **fallan de forma segura** con 503.
- **XML es el formato por omisión.** Para JSON hay que pedir `?format=json`
  (y en books, `?output=json`, porque ahí `?format=` es un filtro de
  búsqueda).
- El **stock no está duplicado**: `library.books.stock` es la única verdad;
  pedidos lo reserva y lo devuelve.
- Lo **único público** del par pedidos/pagos es `GET /envios/<numero>`.

### Cómo trabajar

1. Lee antes de probar: `packages/library_common/library_common/redis_store.py`
   y `jwt_auth.py`, y el `app.py` de cada servicio. Los docstrings explican
   las decisiones; si una prueba contradice un docstring, eso es un hallazgo.
2. Usa `curl -s -o /dev/null -w '%{http_code}'` para los códigos y `curl -i`
   cuando necesites cabeceras (`X-Cache`, `X-Total-Count`, `Location`).
3. Apunta todo en una bitácora: comando, respuesta esperada, respuesta real.
4. **Deja la base como la encontraste.** Crea tus propios datos con un
   prefijo reconocible (`QA-`) y bórralos al final. Si algo no se puede
   deshacer, dilo en el informe en lugar de dejarlo a medias.

### Qué probar

**1. Arranque y configuración**

- `systemctl status` de los seis y de `redis`. Ninguno en `failed`.
- `GET /health?format=json` de los seis. Comprueba el bloque `redis` y que
  `jwt` diga `ok` (si dice `missing_secret`, para y repórtalo: el secreto no
  está puesto).
- Que los seis compartan el **mismo** `JWT_SECRET_KEY`: pide un token a login
  y úsalo contra los otros cinco. Si uno da 401, el secreto no coincide.
- `ss -ltn` y confirma qué escucha en `0.0.0.0` y qué en `127.0.0.1`.
  Redis expuesto en 6379 es intencional pero **comprueba que `requirepass`
  está activo**: `redis-cli -h <IP> ping` sin clave debe dar `NOAUTH`.
- `journalctl -u library-login -n 100`: busca si se está registrando algún
  **token, contraseña o la URL de Redis con su clave**. No debe aparecer
  ninguno; hay un filtro que los tacha. Si ves uno, es un hallazgo grave.

**2. Ciclo de vida del token**

- Login y decodifica el JWT (`cut -d. -f2 | base64 -d`): comprueba
  `user_id`, `role_id`, `jti`, `sid`, `iss`, y que `exp - iat == 1800`.
- Que el **XML** de `/login` NO publique el token ni el refreshToken (es
  deliberado), y que el JSON sí.
- `POST /refresh` con el refresh: debe devolver un par nuevo. Comprueba que
  el refresh **viejo ya no sirve** (401) y que el **token de acceso viejo
  quedó revocado**: úsalo contra books en una escritura y debe dar 401.
- `POST /logout` con `Authorization: Bearer`. Después, ese token debe dar
  **401 en los seis servicios** — pruébalo en los seis, no en uno.
- En Redis, mira las claves: `redis-cli -a '<clave>' --scan --pattern 'session:*'`,
  `'refresh:*'`, `'jwt:revoked:*'`, `'user:sessions:*'`. Comprueba sus TTL con
  `TTL`. El refresh debe estar guardado como **hash SHA-256**, no en claro:
  `GET` de una clave `refresh:*` no debe contener el token que tienes tú.
- Token manipulado: cambia un carácter de la firma → 401. Fabrica uno con
  `alg: none` → 401. Uno caducado → 401. **Ninguno debe dar 403**: el 403 es
  solo para rol insuficiente.

**3. Roles y permisos**

- `SELECT * FROM library.v_role_permissions;` debe mostrar admin con `*`,
  staff con su lista y user sin ninguno.
- Con un token de rol `user`: toda escritura en books, users, authors debe
  dar **403**, no 401 (el token es válido; lo que falta es el permiso).
- Cambia el rol de una cuenta de prueba con `PUT /users/<id>/role`. El token
  que esa cuenta tenía **debe dejar de servir en el acto** (401), porque
  llevaba el `role_id` viejo firmado dentro. Compruébalo.
- Desactiva una cuenta de prueba (`DELETE /users/<id>`) y comprueba lo mismo.
- Comprueba que **no** se puede desactivar ni degradar al último admin (409).

**4. Caché de Redis (books y authors)**

- `GET /books?output=json` dos veces con `curl -i`: la primera `X-Cache: MISS`,
  la segunda `HIT`. Mira la clave en Redis (`--scan --pattern 'books:*'`).
- XML y JSON deben ser **entradas distintas**: pide las dos y comprueba que
  hay dos claves.
- Haz un `PATCH` a un libro y comprueba que la siguiente lectura vuelve a
  `MISS` (la escritura invalidó la caché).
- Renombra un autor y comprueba que se invalidó **también** la caché de
  books (es invalidación cruzada deliberada: la ficha de un libro lleva sus
  autores).
- Mide: compara el tiempo de un MISS y un HIT con `curl -w '%{time_total}'`.
  Si el HIT no es más rápido, la caché no está sirviendo de nada y eso es un
  hallazgo.

**5. Pedidos y stock — lo más delicado**

- Anota `SELECT stock FROM library.books WHERE id = X;` antes y después de
  cada paso.
- Crea un pedido: el stock debe bajar **exactamente** lo pedido.
- Cancélalo: debe volver **exactamente** al valor original.
- Ajusta una línea hacia arriba y hacia abajo: el stock se mueve por la
  **diferencia**, no por el total.
- Pide más de lo que hay: **409** con un mensaje que nombre el libro, y el
  stock **no debe haberse movido**.
- **Concurrencia (importante):** deja un libro con stock 1 y lanza dos
  peticiones de compra **a la vez** (`curl ... & curl ... & wait`). Debe
  ganar exactamente una; la otra debe dar 409. Si las dos ganan o el stock
  queda negativo, es un fallo grave de la reserva atómica — repórtalo con el
  comando exacto.
- **Cerrojo contra el pedido doble:** lanza dos POST idénticos a la vez del
  mismo usuario. El segundo debe dar 409 "ya hay un pedido en curso".
- Transiciones inválidas: `pendiente → enviado` debe dar **409**. Recorre la
  válida: pendiente → pagado → enviado → entregado, y comprueba que
  `order_status_history` registró cada paso con quién y cuándo.

**6. El rastreo público — compruébalo con cuidado**

Es la única puerta sin token de todo el par pedidos/pagos, y existe para que
una paquetería lleve su logística. Verifica que **no filtra nada más**:

- `GET /envios/<numero>` **sin ningún encabezado** debe dar 200.
- El cuerpo **no** debe contener: el correo del cliente, su nombre, su
  `user_id`, ningún importe (`total`, `subtotal`, `paidAmount`), ni los
  títulos o ISBN de los libros. Compruébalo con `grep` sobre la respuesta,
  no a ojo.
- `GET /pedidos/numero/<numero>` (el pedido completo) **sí** debe dar 401 sin
  token.
- Pruébalo también en XML, que es el formato por omisión.

**7. Pagos**

- Que **nada** sea público: `GET /metodos` sin token → 401.
- Pago en efectivo: nace ya `aplicado`. Cuando lo aplicado alcanza el total,
  el **pedido pasa a `pagado` solo** (lo hace un disparador). Verifícalo
  consultando `library.orders`.
- Un importe que excede el saldo → 409.
- **Idempotencia:** dos POST con la misma `idempotencyKey` deben devolver la
  **misma** referencia `PAG-xxxxxx`, y `SELECT count(*) FROM library.payments
  WHERE idempotency_key = '...'` debe dar **1**.
- **Cobro doble por concurrencia:** dos pagos simultáneos del saldo completo
  del mismo pedido. Solo uno debe pasar; el otro, 409 por exceder el saldo o
  por el cerrojo. Comprueba que la suma de lo aplicado **no supera** el total.
- Manda `cardNumber`, `cvv` o `pan` → **400**. Comprueba en
  `library.payments` que no existe ninguna columna con datos de tarjeta más
  allá de `card_last4`.

**8. Fallo seguro: tira Redis**

Con `systemctl stop redis`, comprueba y anota el código de cada uno:

- Lecturas de books y authors: deben **seguir funcionando** (200), sin caché.
- `GET /envios/<numero>`: debe seguir funcionando (200).
- Cualquier escritura con token, en cualquier servicio: **503**, no 200 y no
  500. Si alguna escritura pasa con Redis caído, es un fallo grave de
  seguridad: significa que se está aceptando un token sin poder comprobar si
  fue revocado.
- `/login`, `/refresh`, `/session`: **503**.
- `/health` de los seis, exactamente así (compruébalo uno por uno):

  | Servicio | Con Redis caído | Por qué |
  |---|---|---|
  | login | **503** | Sin Redis no puede abrir, renovar ni cerrar sesiones |
  | books | 200 `degraded` | El catálogo se lee igual; solo pierde la caché |
  | users | **503** | No tiene ninguna lectura pública: sin poder comprobar la revocación, no puede hacer nada |
  | authors | 200 `degraded` | Las lecturas son públicas y siguen |
  | pedidos | 200 `degraded` | El rastreo público sigue; lo demás da 503 |
  | pagos | **503** | Nada es público aquí |

  Los que devuelven 200 deben traer `status: degraded` y un aviso que
  explique qué deja de funcionar.
- Que ningún error 503 **filtre la contraseña de Redis** en su cuerpo.

Vuelve a levantar Redis (`systemctl start redis`) y comprueba que los seis
se recuperan **sin reiniciarlos**.

**9. Formatos y errores**

- Los seis responden XML sin `?format=` y JSON con él. Comprueba también que
  `Accept: application/json` funciona.
- Los errores tienen la misma forma en los seis: `{"error": {"status", "code",
  "message", "details"}}` y su equivalente `<error status code><message>`.
- `/openapi.json` y `/docs/` responden en los seis (ojo: `/docs` sin barra
  devuelve 308).

### Informe

Entrega un documento con:

1. **Resumen**: cuántas comprobaciones, cuántas pasaron, cuántas fallaron.
2. **Hallazgos**, ordenados por gravedad. Para cada uno: el comando exacto,
   lo que esperabas, lo que pasó, y por qué importa. Marca como **graves** los
   de seguridad (una escritura que pasa con Redis caído, un token revocado
   que sigue sirviendo, un secreto en los logs, el rastreo público filtrando
   datos, stock negativo o cobro doble).
3. **Lo que no pudiste probar** y por qué. Esto es tan útil como lo que sí
   probaste: no lo omitas.
4. **Estado de la base al terminar**: confirma que borraste tus datos `QA-`,
   o di exactamente qué quedó.

No arregles el código: tu trabajo es encontrar y documentar. Si ves un
arreglo obvio, propónlo en el informe.
