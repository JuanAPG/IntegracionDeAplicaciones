# Microservicio de pedidos — Flask + Psycopg 3 + PostgreSQL + Redis

Servicio independiente de **pedidos, líneas, reserva de stock y estados**
para `library_db` (esquema `library`). Expone sus respuestas en **XML** y
**JSON**; sin `?format=`, **XML** es el formato predeterminado.

Se documenta solo: **Swagger UI en `/docs`**, especificación OpenAPI 3.0.3
en `/openapi.json`.

Escucha en el puerto **5004**. Comparte el secreto del JWT y el servidor
Redis con los otros cinco servicios (login `5000`, libros `5001`, usuarios
`5002`, autores `5003`, pedidos `5004`, pagos `5005`).

---

## 1. Qué hace

| Operación | Endpoint | Quién puede |
|---|---|---|
| **Rastreo de envío** | `GET /envios/<numero>` | **público** (lo único sin token) |
| Crear pedido | `POST /pedidos` | cualquier token; a nombre de otro, `orders:write` |
| Listar pedidos | `GET /pedidos` | los propios; `?all=true` o `?userId=` con `orders:read` |
| Un pedido por id | `GET /pedidos/<id>` | el propio, o `orders:read` |
| Un pedido por número | `GET /pedidos/numero/<numero>` | el propio, o `orders:read` |
| Bitácora de estados | `GET /pedidos/<id>/historial` | el propio, o `orders:read` |
| Ajustar cantidades | `PATCH /pedidos/<id>/lineas` | el propio **y pendiente**, o `orders:write` |
| Cancelar y devolver stock | `DELETE /pedidos/<id>` | el propio si está pendiente; si está pagado, `orders:write` |
| Mover el estado | `PUT /pedidos/<id>/estado` | `orders:status` |
| Índice del servicio | `GET /` | público |
| Estado | `GET /health` | público |
| Contadores | `GET /metrics` | público |
| Documentación | `GET /docs` — `GET /openapi.json` | público |

### El stock no se duplica

`library.books.stock` ya existe desde `data/schema.sql` y el microservicio
de libros ya lo publica y lo filtra. Este servicio **no crea una tabla de
inventario paralela**: reserva unidades al crear el pedido y las devuelve
al cancelarlo, **en la misma transacción** que escribe las líneas.

Dos tablas de stock serían dos verdades, y la segunda siempre acaba
mintiendo. La reserva se hace así:

```sql
UPDATE books SET stock = stock - q WHERE id = ? AND stock >= q
```

y se comprueba que haya afectado una fila. Si dos pedidos piden la última
unidad al mismo tiempo, uno gana y el otro recibe el error: el `UPDATE`
toma el bloqueo de fila, de modo que no hay ventana entre "consultar el
stock" y "restarlo". Las filas se recorren **ordenadas por `book_id`** para
que dos pedidos con los mismos libros no se bloqueen mutuamente en orden
inverso (interbloqueo).

Los precios **no vienen del cliente**: `sp_crear_pedido` los congela desde
`library.books`. Nadie se compra un libro a su propio precio, y un pedido
histórico no muta cuando el catálogo sube de precio.

### La máquina de estados

```
pendiente ──> pagado ──> enviado ──> entregado
    │            │
    └──> cancelado <──┘
```

| Desde | Hacia |
|---|---|
| `pendiente` | `pagado`, `cancelado` |
| `pagado` | `enviado`, `cancelado` |
| `enviado` | `entregado` |
| `entregado` | — (final) |
| `cancelado` | — (final) |

La regla la impone un **disparador de la base**, no esta aplicación. Así se
cumple aunque el estado lo cambie el microservicio de pagos, el monolito,
o alguien con `psql`: ningún cliente —ni un microservicio con un error—
puede dejar un pedido en un estado imposible. `app.py` se limita a traducir
el error del disparador a un `409` legible.

El paso a `pagado` normalmente **no se hace aquí**: lo dispara el
microservicio de pagos cuando la suma de lo aplicado alcanza el total.
`PUT /pedidos/<id>/estado` lo deja disponible para corregir a mano un caso
excepcional, pero la vía normal es registrar y aplicar un pago.

Cada cambio queda en `order_status_history`: quién, cuándo y de qué a qué.
Es lo que hace auditable un pedido.

### El cerrojo de Redis contra el pedido doble

El escenario es muy concreto: el cliente manda `POST /pedidos`, la
respuesta tarda, el cliente agota su tiempo de espera y **reintenta**. Sin
defensa, se crean dos pedidos y se reserva el stock dos veces.

Antes de llamar al procedimiento se toma un cerrojo en Redis con la clave
`lock:pedido:crear:<user_id>` y 10 segundos de vida. Si ya está tomado, la
segunda petición recibe `409` diciendo que hay un pedido en curso y que, si
el anterior se creó, aparecerá en `GET /pedidos`. El TTL evita que un
proceso que muera a mitad deje la cuenta bloqueada para siempre.

El cerrojo es por **usuario**, no por cuerpo de la petición: pedir dos
veces lo mismo en diez segundos es casi siempre un reintento, y casi nunca
una compra deliberada.

### Lo único público: `GET /envios/<numero>`

Existe para que **un tercero —la paquetería— pueda llevar su logística sin
tener una cuenta en el sistema**. Devuelve exclusivamente:

```
orderNumber · status · carrier · trackingCode
placedAt · shippedAt · deliveredAt · itemCount
```

Nada de dueño, correo, importes ni qué libros se compraron. La respuesta la
construye `tracking_to_dict()` **campo por campo** desde la lista
`TRACKING_FIELDS`, en vez de filtrar una fila completa: así, añadir una
columna a la vista `v_order_tracking` no la publica por accidente.

El número de pedido (`PED-000123`) hace de identificador y es secuencial,
de modo que conviene tratarlo como un dato que se comparte con quien
transporta el paquete, **no como un secreto**. Para el pedido completo por
número está `GET /pedidos/numero/<numero>`, que sí exige token.

El rastreo se cachea en Redis (`envios:<numero>:<representación>`, TTL
30 s) porque es la consulta más repetitiva del servicio. **Los pedidos en
sí no se cachean**: llevan datos personales e importes, cambian con cada
pago y se leen poco; cachearlos daría un rendimiento que nadie necesita a
cambio de un riesgo real de servir el pedido de otro.

### Autorización

Un cliente opera sobre **lo suyo** con solo tener un token válido: crea sus
pedidos, los lista, los ajusta y los cancela mientras sigan pendientes. Los
permisos son para lo administrativo:

| Permiso | Para qué |
|---|---|
| `orders:read` | ver cualquier pedido |
| `orders:write` | crear pedidos a nombre de otro, ajustar o cancelar cualquiera |
| `orders:status` | mover el estado (enviado, entregado) |

Cancelar un pedido **ya pagado** exige `orders:write` aunque sea el propio:
hay dinero de por medio y habría que reembolsarlo. Un pedido `enviado` o
`entregado` ya no se cancela en absoluto: eso es una devolución, que es
otra cosa y no está en el alcance de esta entrega.

### Invalidación cruzada con el catálogo

Crear o cancelar un pedido mueve `library.books.stock`, y el stock sale en
las fichas que cachea el microservicio de libros (`books:*`). Hay un solo
Redis compartido: se invalida ahí directamente en lugar de dejar el
catálogo anunciando unidades que ya no existen.

---

## 2. Formatos

```
GET /pedidos                -> XML (por omisión)
GET /pedidos?format=xml     -> XML
GET /pedidos?format=json    -> JSON
GET /pedidos?output=json    -> JSON (alias sin ambigüedad)
Accept: application/json    -> JSON
```

Rastreo público, sin token:

```bash
curl -s "http://localhost:5004/envios/PED-000123?format=json"
curl -s "http://localhost:5004/envios/PED-000123"        # XML por omisión
```

Todo lo demás necesita un token emitido por el microservicio de login:

```bash
TOKEN=$(curl -s -X POST "http://localhost:5000/login?format=json" \
  -H "Content-Type: application/json" \
  -d '{"email": "ada@ejemplo.mx", "password": "Secreto123"}' \
  | python3 -c "import sys, json; print(json.load(sys.stdin)['token'])")
```

Crear un pedido. Las líneas se acumulan si se repite el mismo libro
(`order_lines` tiene `UNIQUE (order_id, book_id)`, de modo que pedir dos
veces el mismo libro significa querer más unidades):

```bash
curl -s -X POST "http://localhost:5004/pedidos?format=json" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" -d '{
    "lines": [
      {"bookId": 1, "quantity": 2},
      {"bookId": 2, "quantity": 1}
    ],
    "shippingAddress": "Av. Morones Prieto 4500, Monterrey",
    "shippingCost": 120.00,
    "notes": "Entregar por la tarde"
  }'
```

El mismo pedido con cuerpo XML:

```bash
curl -s -X POST "http://localhost:5004/pedidos?format=xml" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/xml" --data-binary '
<order>
  <lines>
    <line><bookId>1</bookId><quantity>2</quantity></line>
    <line><bookId>2</bookId><quantity>1</quantity></line>
  </lines>
  <shippingCost>120.00</shippingCost>
</order>'
```

Si el stock no alcanza, la respuesta es un `409` que dice **de qué libro se
trata**: `Stock insuficiente de "Clean Code" (ISBN 978-...): hay 1, se piden 3`.
Esa comprobación previa es un aviso temprano y legible; la verdad sigue
estando en el procedimiento, que vuelve a comprobarlo de forma atómica.

Consultar:

```bash
curl -s "http://localhost:5004/pedidos?format=json&status=pendiente&limit=20" \
  -H "Authorization: Bearer $TOKEN"

curl -s "http://localhost:5004/pedidos/42?format=json" -H "Authorization: Bearer $TOKEN"
curl -s "http://localhost:5004/pedidos/numero/PED-000042?format=json" -H "Authorization: Bearer $TOKEN"
curl -s "http://localhost:5004/pedidos/42/historial?format=json" -H "Authorization: Bearer $TOKEN"
```

Con `orders:read` se puede pedir el panorama completo:

```bash
curl -s "http://localhost:5004/pedidos?format=json&all=true&from=2026-01-01" \
  -H "Authorization: Bearer $TOKEN_STAFF"
curl -s "http://localhost:5004/pedidos?format=json&userId=7" \
  -H "Authorization: Bearer $TOKEN_STAFF"
```

Ajustar cantidades (solo mientras el pedido siga `pendiente`). El stock se
ajusta por la **diferencia**: subir de 2 a 3 reserva una unidad más, bajar
de 3 a 1 devuelve dos, y `quantity: 0` quita la línea. Si el pedido se
queda sin ninguna línea se cancela solo y devuelve todo el stock, porque un
pedido sin líneas no es un pedido.

```bash
curl -s -X PATCH "http://localhost:5004/pedidos/42/lineas?format=json" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"lines": [{"bookId": 1, "quantity": 3}, {"bookId": 2, "quantity": 0}]}'
```

Cancelar devolviendo el stock:

```bash
curl -s -X DELETE "http://localhost:5004/pedidos/42?format=json" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" -d '{"reason": "ya no lo necesito"}'
```

Mover el estado (exige `orders:status`). Al marcar `enviado` conviene
mandar `carrier` y `trackingCode`: es exactamente lo que después lee la
paquetería en `GET /envios/<numero>`, y si falta la guía la respuesta lo
avisa en el campo `warning`.

```bash
curl -s -X PUT "http://localhost:5004/pedidos/42/estado?format=json" \
  -H "Authorization: Bearer $TOKEN_STAFF" \
  -H "Content-Type: application/json" \
  -d '{"status": "enviado", "carrier": "Estafeta", "trackingCode": "EST123456789"}'

curl -s -X PUT "http://localhost:5004/pedidos/42/estado?format=json" \
  -H "Authorization: Bearer $TOKEN_STAFF" \
  -H "Content-Type: application/json" -d '{"status": "entregado"}'
```

---

## 3. Restricciones de la práctica

* **Flask sin blueprints.** Todas las rutas se registran con `@app.get` /
  `@app.post` / `@app.put` / `@app.patch` / `@app.delete` sobre la única
  instancia `app` de `pedidos/app.py`.
* **Psycopg 3** (`psycopg[binary,pool]`), consultas parametrizadas (`%s`) y
  una sola transacción por escritura. El nombre de la columna de
  ordenación sale de una **lista blanca** (`SORTABLE`).
* **La lógica delicada vive en la base.** Crear un pedido reservando stock
  sin condiciones de carrera, cancelarlo devolviendo stock y mover su
  estado son **procedimientos almacenados**: `sp_crear_pedido`,
  `sp_ajustar_linea_pedido`, `sp_cancelar_pedido` y
  `sp_cambiar_estado_pedido`. Así la regla se cumple venga la escritura de
  donde venga, y la reserva es atómica de verdad.
* **Sin credenciales en el código.** Todo sale de variables de entorno; el
  `.env` está en `.gitignore` y nunca se publica.
* **XML y JSON** para el mismo recurso, XML por omisión. El cuerpo de
  entrada también se acepta en JSON, XML o formulario; el lector de XML
  reconoce listas anidadas (`<lines><line>…</line></lines>`).
* **CORS** enumerando los orígenes de las aplicaciones cliente. Este
  servicio **no usa cookies** (la identidad viaja en el JWT), de modo que
  `supports_credentials` queda en `false`.
* **Paquete compartido** `library_common`, instalado con
  `pip install -e packages/library_common`.
* **Límites de cordura:** 50 líneas por pedido y 100 unidades por libro.

---

## 4. Estructura

```
apps/services/pedidos/
├── pedidos/
│   ├── app.py              rutas Flask, CORS, autorización, errores
│   ├── config.py           lectura del .env (vía library_common.settings)
│   ├── shared.py           store, database, codec, negotiator, resolver
│   ├── cache.py            claves envios:* e invalidación cruzada con books:*
│   ├── repository.py       todo el SQL (vistas + procedimientos almacenados)
│   ├── openapi.py          especificación OpenAPI 3.0.3 escrita a mano
│   ├── _bootstrap.py       deja importable library_common sin instalarlo
│   └── wsgi.py             punto de entrada para gunicorn
├── scripts/pruebas.sh      batería de humo con curl (+ psql en la VM)
├── test/test_pedidos_mocked.py   pruebas sin PostgreSQL ni Redis
├── requirements.txt
├── .env                    credenciales propias del servicio (NO se publica)
└── .gitignore
```

Lo que aporta la migración de este servicio:

```
data/pedidos_migration.sql
    orders                  cabecera (dueño, estado, importes, envío)
    order_lines             líneas, con el precio CONGELADO al comprar
    order_status_history    bitácora de cambios de estado
    order_number_seq        numeración legible PED-000001
    sp_crear_pedido · sp_ajustar_linea_pedido ·
    sp_cancelar_pedido · sp_cambiar_estado_pedido
    v_orders_detail         pedido con su dueño e importes (administrativa)
    v_order_tracking        RASTREO PÚBLICO: solo el estado del envío
```

---

## 5. Puesta en marcha en la instancia CentOS 10 Stream

Se asume PostgreSQL ya instalado con `library_user` / `library_db` y el
esquema inicial (`data/schema.sql`) aplicado.

### 5.1 Migraciones de la base (primero, desde la raíz del repo)

El orden **importa**: `roles` → `pedidos` → `pagos`.

```bash
psql -U library_user -d library_db -f data/roles_migration.sql
psql -U library_user -d library_db -f data/pedidos_migration.sql
psql -U library_user -d library_db -f data/pagos_migration.sql
```

* `roles_migration.sql` crea `library.roles` y `library.role_permissions`,
  de donde salen `orders:read`, `orders:write` y `orders:status`, y
  `users.role_id`, que es lo que el JWT transporta.
* `pedidos_migration.sql` crea las tablas, los procedimientos, el
  disparador de la máquina de estados y las dos vistas.
* `pagos_migration.sql` **reemplaza `v_orders_detail`** añadiéndole la
  columna `paid_amount`, una vez que `library.payments` existe
  (`CREATE OR REPLACE VIEW` admite añadir columnas al final). Por eso va
  después: al revés, la vista no podría referenciar una tabla inexistente.

Las tres son idempotentes y pueden correrse dos veces sin daño.

Comprobación rápida:

```bash
psql -U library_user -d library_db -c \
  "SELECT library.sp_crear_pedido(1, '[{\"bookId\":1,\"quantity\":1}]'::jsonb);"
psql -U library_user -d library_db -c \
  "SELECT * FROM library.v_order_tracking ORDER BY placed_at DESC LIMIT 3;"
```

### 5.2 Python, el paquete compartido y el código

```bash
sudo dnf install -y python3 python3-pip
sudo useradd --system --home-dir /opt/library --shell /sbin/nologin library || true

sudo mkdir -p /opt/library/packages
sudo cp -r packages/library_common /opt/library/packages/library_common
sudo cp -r apps/services/pedidos /opt/library/pedidos
sudo chown -R library:library /opt/library

sudo -u library python3 -m venv /opt/library/pedidos/.venv
sudo -u library /opt/library/pedidos/.venv/bin/pip install -r /opt/library/pedidos/requirements.txt
sudo -u library /opt/library/pedidos/.venv/bin/pip install -e /opt/library/packages/library_common
```

El `pip install -e` del paquete compartido **no es opcional**: sin él, el
servicio arranca gracias al respaldo de `_bootstrap.py`, pero en
`/opt/library` esa ruta ya no tiene la misma forma y lo correcto es
instalarlo en el venv.

### 5.3 Configuración

Los secretos **compartidos** van en el `.env` de la **raíz** del repo
(copiado a `/opt/library/.env`), porque los leen los seis servicios y
tenerlos repetidos seis veces garantiza que un día dejen de coincidir:

```bash
sudo -u library tee /opt/library/.env > /dev/null <<'EOF'
# Secreto de firma HS256 — IDÉNTICO en los seis servicios.
#   python3 -c "import secrets; print(secrets.token_urlsafe(64))"
JWT_SECRET_KEY=CAMBIEME_secreto_jwt_compartido
JWT_ALGORITHM=HS256
JWT_ISSUER=library-login-service
JWT_ACCESS_TTL_MINUTES=30
JWT_REFRESH_TTL_HOURS=8
SESSION_TTL_HOURS=8

# Redis en la misma VM, con requirepass.
REDIS_URL=redis://:CAMBIEME_password_redis@127.0.0.1:6379/0
CACHE_TTL_SECONDS=30
CACHE_DETAIL_TTL_SECONDS=60
ROLE_CACHE_TTL_SECONDS=300

# PostgreSQL
PGHOST=localhost
PGPORT=5432
PGDATABASE=library_db
PGUSER=library_user
PGPASSWORD=CAMBIEME_contrasena_de_postgres
PGSCHEMA=library
EOF
sudo chmod 600 /opt/library/.env
```

`JWT_SECRET_KEY` es el nombre actual; se sigue aceptando `JWT_SECRET` como
nombre anterior para no romper los despliegues que ya existen.

Lo **propio del servicio** va en su propio `.env`:

```bash
sudo -u library tee /opt/library/pedidos/.env > /dev/null <<'EOF'
HOST=0.0.0.0
PORT=5004
DEBUG=false

# En producción enumere los orígenes; "*" solo sirve en desarrollo.
CORS_ORIGINS=*
CORS_MAX_AGE=86400

DEFAULT_FORMAT=xml
XML_NAMESPACE=urn:library:orders:1.0
XML_VERSION=1.0

DEFAULT_LIMIT=50
MAX_LIMIT=200

# Caché del rastreo público. Los pedidos nunca se cachean.
CACHE_ENABLED=true
EOF
sudo chmod 600 /opt/library/pedidos/.env
```

Precedencia: **entorno real > `.env` de la raíz > `.env` del servicio**.

### 5.4 Redis en la misma VM

```bash
sudo dnf install -y redis
sudo sed -i 's/^# *requirepass .*/requirepass CAMBIEME_password_redis/' /etc/redis/redis.conf
sudo sed -i 's/^bind .*/bind 0.0.0.0/' /etc/redis/redis.conf
sudo systemctl enable --now redis
redis-cli -a 'CAMBIEME_password_redis' ping        # PONG
redis-cli -a 'CAMBIEME_password_redis' --scan --pattern 'lock:*'
```

Redis queda **expuesto** en el puerto 6379 porque los seis servicios lo
comparten —el cerrojo contra el pedido doble y la invalidación cruzada del
catálogo dependen de que sea el mismo servidor— y por eso `requirepass` no
es opcional. La contraseña viaja dentro de `REDIS_URL` con la forma
`redis://:password@host:6379/0`; el filtro de `logging_support` la tacha
antes de que llegue a cualquier log.

### 5.5 Servicio systemd

```bash
sudo tee /etc/systemd/system/library-pedidos.service > /dev/null <<'EOF'
[Unit]
Description=Libreria en Linea — microservicio de pedidos (Flask)
After=network-online.target postgresql.service redis.service
Wants=network-online.target

[Service]
Type=simple
User=library
Group=library
WorkingDirectory=/opt/library/pedidos
ExecStart=/opt/library/pedidos/.venv/bin/gunicorn \
          --workers 3 --bind 127.0.0.1:5004 \
          --access-logfile - --error-logfile - pedidos.wsgi:application
Restart=on-failure
RestartSec=5

NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=full
ProtectHome=true

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable --now library-pedidos
sudo systemctl status library-pedidos
```

### 5.6 Proxy inverso y firewall

Con **nginx**:

```nginx
location /pedidos/ {
    proxy_pass http://127.0.0.1:5004/;
    proxy_set_header Host              $host;
    proxy_set_header X-Real-IP         $remote_addr;
    proxy_set_header X-Forwarded-For   $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header Authorization     $http_authorization;
}
```

La última línea importa: si el proxy se come la cabecera `Authorization`,
el rastreo público sigue funcionando y **todo lo demás responde `401`**.

`gunicorn` no lee `PORT` del `.env`: el puerto va en `--bind`.
**No añada cabeceras CORS en el proxy** (ya las emite Flask) y recuerde
`sudo setsebool -P httpd_can_network_connect 1` con SELinux.

```bash
sudo firewall-cmd --permanent --add-service=http --add-service=https
sudo firewall-cmd --permanent --add-port=5004/tcp   # solo si necesita acceso directo
sudo firewall-cmd --permanent --add-port=6379/tcp   # Redis compartido
sudo firewall-cmd --reload
```

### 5.7 Verificación

```bash
curl -s "http://localhost:5004/health?format=json"
curl -s "http://localhost:5004/envios/PED-000001?format=json"
BASE=http://localhost:5004 ./scripts/pruebas.sh
```

`/health` responde `200` incluso con Redis caído, con `status: degraded` y
un aviso: el rastreo público sigue funcionando (solo pierde el caché), de
modo que el servicio sí está haciendo algo útil. Solo PostgreSQL caído lo
lleva a `503`.

---

## 6. Pruebas sin PostgreSQL ni Redis (esta máquina)

```bash
cd apps/services/pedidos
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pip install -e ../../../packages/library_common
python test/test_pedidos_mocked.py
```

`test/test_pedidos_mocked.py` sustituye el `RedisStore` por el doble de
`library_common.testing` y el repositorio por uno en memoria que
**reproduce lo que hacen los procedimientos almacenados**: la reserva y
devolución de stock sobre `books.stock` y la máquina de estados. Eso
permite comprobar el *comportamiento* del servicio sin base de datos; la
corrección del SQL en sí se verifica en la VM con `scripts/pruebas.sh`.

Cubre los once bloques: el rastreo público sin token y con solo el estatus
de envío, la creación con reserva de stock y precios congelados, el
rechazo por stock insuficiente, que un cliente no pueda pedir a nombre de
otro sin `orders:write`, el **cerrojo de Redis** impidiendo el pedido doble,
el listado propio frente al ajeno, el ajuste de líneas por diferencia solo
en `pendiente`, la cancelación con devolución de stock y sus reglas por
estado, las transiciones válidas con `orders:status`, la invalidación del
caché del catálogo cuando se mueve el stock, y el **fallo asimétrico de
Redis**: rastreo `200`, operaciones con token `503 redis_unavailable`.

---

## 7. Códigos de error

Todos los errores salen con la misma forma, en XML o en JSON:
`{"error": {"status", "code", "message", "details": [...]}}`.

| Código | `code` | Cuándo |
|---|---|---|
| `400` | `validation_error` | Líneas ausentes o inválidas, cantidades negativas o por encima del límite, `userId`/`shippingCost` no numéricos, estado desconocido, XML/JSON mal formado |
| `401` | `unauthorized` | Token ausente, malformado, inválido, **caducado** o **revocado** |
| `403` | `forbidden` | El pedido no es suyo y el rol no tiene `orders:read` / `orders:write` / `orders:status` |
| `404` | `not_found` | No existe el pedido, ni el número de envío |
| `409` | `conflict` | Stock insuficiente, cuenta desactivada, pedido en curso (cerrojo), modificar un pedido que ya no está `pendiente`, cancelar uno `enviado`/`entregado`, transición de estado no permitida |
| `503` | `redis_unavailable` · `database_unavailable` | Redis caído **en una operación con token**, o PostgreSQL caído |

### Las dos políticas de fallo de Redis

Son distintas a propósito:

1. **Lecturas cacheadas — Redis es opcional.** El rastreo público
   (`envios:*`, TTL 30 s) degrada en silencio: un fallo se trata como
   ausencia de caché y la petición sigue contra PostgreSQL. El cliente no
   se entera, y la paquetería sigue pudiendo consultar su guía. El TTL
   corto es además la red de seguridad por si una invalidación se pierde.
2. **Sesiones, revocación y autorización — fallo seguro con `503`.** Si no
   se puede consultar si un `jti` está revocado, el token **no se acepta**.
   Antes un `503` honesto que dejar que alguien con una credencial
   revocada cree pedidos y reserve stock. El cerrojo contra el pedido doble
   va por la misma vía estricta: sin cerrojo no se crea el pedido, porque
   crear sin protección es exactamente el fallo que se quiere evitar.

---

## 8. Seguridad

* El `.env` **no se publica** (`apps/services/pedidos/.gitignore`), ni el
  de la raíz. Los secretos solo viajan por variables de entorno.
* Todo el SQL usa parámetros (`%s`); el único texto que se interpola es el
  nombre de columna de `ORDER BY`, y sale de una lista blanca. Las líneas
  viajan al procedimiento como `jsonb`, no como SQL construido.
* **El rastreo público se construye campo por campo.** Es la medida más
  importante de este servicio: una proyección explícita no se amplía sola
  cuando alguien añade una columna a la vista.
* El precio y el total nunca los manda el cliente: los calcula la base
  desde `library.books` y los disparadores de `order_lines`.
* El filtro de `logging_support` tacha mecánicamente `Bearer <token>`,
  cualquier JWT suelto y la contraseña dentro de una URL
  `redis://:x@host`. Los registros guardan ids (`order_id`, `user_id`), no
  direcciones ni correos.
* Verificación del JWT en cada petición con token, en este orden: cabecera
  `Bearer` bien formada → algoritmo esperado (se rechaza `none` y la
  confusión de algoritmos) → firma → `exp` e `iss` → claims obligatorios →
  `jti` no revocado.
* Cabeceras `X-Content-Type-Options: nosniff`,
  `Referrer-Policy: no-referrer` y `Cache-Control: no-store` en las
  respuestas con datos del usuario.
* `DEBUG=false` en el servidor: con `true`, los errores 500 devuelven el
  detalle interno al cliente.
