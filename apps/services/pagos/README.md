# Microservicio de pagos — Flask + Psycopg 3 + PostgreSQL + Redis

Servicio independiente que **registra pagos y, a través de ellos, actualiza
el estado de los pedidos** de `library_db` (esquema `library`). Expone sus
respuestas en **XML** y **JSON**; sin `?format=`, **XML** es el formato
predeterminado.

Se documenta solo: **Swagger UI en `/docs`**, especificación OpenAPI 3.0.3
en `/openapi.json`.

Escucha en el puerto **5005**. Comparte el secreto del JWT y el servidor
Redis con los otros cinco servicios (login `5000`, libros `5001`, usuarios
`5002`, autores `5003`, pedidos `5004`, pagos `5005`).

---

## 1. Qué hace

| Operación | Endpoint | Quién puede |
|---|---|---|
| Métodos de pago | `GET /metodos` | cualquier token |
| Registrar un pago | `POST /pagos` | el dueño del pedido; el de otro, `payments:write` |
| Listar pagos | `GET /pagos` | los propios; `?all=true` o `?userId=` con `payments:read` |
| Un pago con su bitácora | `GET /pagos/<id>` | el propio, o `payments:read` |
| Un pago por referencia | `GET /pagos/referencia/<ref>` | el propio, o `payments:read` |
| Saldo de un pedido | `GET /pedidos/<id>/saldo` | el propio, o `payments:read` |
| Aplicar (confirmar) | `POST /pagos/<id>/aplicar` | `payments:write` |
| Rechazar | `POST /pagos/<id>/rechazar` | `payments:write` |
| Reembolsar | `POST /pagos/<id>/reembolsar` | `payments:write` |
| Índice del servicio | `GET /` | público |
| Estado | `GET /health` | público |
| Contadores | `GET /metrics` | público |
| Documentación | `GET /docs` — `GET /openapi.json` | público |

### Aquí no hay ninguna lectura pública

Un pago es información financiera de una persona concreta. La única cosa
que el par pedidos/pagos publica sin token es el **estatus de envío**, y
vive en el microservicio de pedidos (`GET /envios/<numero>` en el `5004`),
porque es lo que necesita un tercero para llevar su logística.

Todo lo de aquí exige `Authorization: Bearer <JWT>`, **incluido el catálogo
de métodos de pago**. No es que `GET /metodos` tenga datos personales: es
que en este servicio no se abre ninguna puerta, y quien va a pagar ya está
autenticado de todas formas. Una excepción "inofensiva" es una excepción
que alguien tendrá que revisar después.

### Qué NO se guarda, y por qué

**No se guarda el instrumento de pago.** Ni número de tarjeta, ni CVV, ni
fecha de vencimiento, ni titular. Lo único que se conserva de la pasarela
es:

* `authorizationCode` — la referencia que ella misma devuelve;
* `cardLast4` — los cuatro últimos dígitos, **si la pasarela los publica**.

La columna tiene `CHECK (card_last4 ~ '^[0-9]{4}$')` y el servicio rechaza
de plano cualquier campo que *parezca* un instrumento de pago:
`cardNumber`, `card_number`, `pan`, `cvv`, `cvc`, `securityCode`, `expiry`,
`expirationDate`, `cardholder`, `numeroTarjeta`, `titular`. La petición
falla con `400` y explica por qué.

El razonamiento es corto: **lo que no se guarda no se puede filtrar**. El
cobro lo hace la pasarela; aquí solo se registra el *hecho* del pago.

### El pago mueve el pedido, pero no lo decide este código

Cuando la suma de los pagos **aplicados** alcanza el total del pedido, un
**disparador de la base** (`trg_payments_settle_order`) pasa el pedido a
`pagado`. No se hace desde Python a propósito: así no existe forma de
marcar un pedido como pagado sin que exista el dinero detrás, venga la
escritura de donde venga.

La respuesta de `POST /pagos/<id>/aplicar` informa del resultado en
`orderStatusAfter`, para que el cliente no tenga que preguntarle al
servicio de pedidos.

### Estados del pago

```
pendiente ──> autorizado ──> aplicado ──> reembolsado
    │              │
    └──> rechazado <┘
```

| Desde | Hacia |
|---|---|
| `pendiente` | `autorizado`, `aplicado`, `rechazado` |
| `autorizado` | `aplicado`, `rechazado` |
| `aplicado` | `reembolsado` |
| `rechazado` | — (final) |
| `reembolsado` | — (final) |

Un método que **no requiere autorización** (efectivo, en mostrador) nace
directamente `aplicado`, y si con eso se cubre el total el pedido pasa a
`pagado` en la misma transacción. Los demás nacen `pendiente`, o
`autorizado` si se manda el código de la pasarela.

Las transiciones las impone un disparador, igual que en pedidos: la regla
vive en la base y `app.py` se limita a traducir el error a un `409`
legible.

### Por qué el reembolso no devuelve el pedido a `pendiente`

Es la decisión menos obvia del servicio, y la que más conviene explicar.

Reembolsar un pago aplicado deja al pedido con menos dinero cobrado que su
total. La reacción intuitiva sería devolverlo a `pendiente`. **No se hace**,
por dos razones:

1. `pagado → pendiente` **no es una transición válida** de la máquina de
   estados de pedidos. Añadirla para este caso abriría la puerta a que un
   pedido ya enviado retrocediera.
2. Rehacer la historia de un pedido es peor que dejar constancia. Un
   pedido que estuvo pagado, se envió y luego se reembolsó **ocurrió así**,
   y el registro debe decirlo.

El reembolso queda en `payment_status_history` con quién lo hizo, cuándo y
por qué, el saldo del pedido vuelve a mostrar deuda en
`GET /pedidos/<id>/saldo`, y **el descuadre lo resuelve una persona**. La
respuesta lo dice explícitamente en el campo `note`.

Si el pago todavía no se había aplicado, lo correcto no es reembolsarlo
sino **rechazarlo**: el servicio responde `409` sugiriéndolo.

### Contra el cobro doble: dos defensas que se complementan

1. **`idempotencyKey`.** Dos intentos con la misma clave son el **mismo**
   pago: el servicio devuelve el que ya existía, con
   `idempotentReplay: true`, en vez de cobrar otra vez. Es lo que salva un
   reintento del cliente tras un tiempo de espera agotado. En la base hay
   un índice único **parcial** sobre `idempotency_key` (parcial porque los
   pagos de mostrador pueden no traerla).
2. **Un cerrojo en Redis por pedido** (`lock:pago:pedido:<id>`, 10 s)
   mientras se registra, para que dos peticiones **simultáneas** no pasen a
   la vez por la comprobación de saldo de `sp_registrar_pago`. La clave de
   idempotencia resuelve el reintento secuencial; el cerrojo resuelve la
   carrera.

Además, `sp_registrar_pago` no permite pagar **más de lo que falta**: el
importe se compara contra el saldo pendiente del pedido (total menos lo ya
aplicado o autorizado).

### Autorización

Un cliente puede pagar **sus** pedidos y ver **sus** pagos con solo tener un
token válido. Los permisos son para lo administrativo:

| Permiso | Para qué |
|---|---|
| `payments:read` | ver pagos y saldos ajenos |
| `payments:write` | aplicar, rechazar y reembolsar; cobrar en nombre de otro |

Nótese que **aplicar, rechazar y reembolsar siempre exigen
`payments:write`**, aunque el pago sea propio: confirmar que el dinero
llegó no es algo que decida quien paga.

---

## 2. Formatos

```
GET /pagos                  -> XML (por omisión)
GET /pagos?format=xml       -> XML
GET /pagos?format=json      -> JSON
GET /pagos?output=json      -> JSON (alias sin ambigüedad)
Accept: application/json    -> JSON
```

Todo necesita un token emitido por el microservicio de login:

```bash
TOKEN=$(curl -s -X POST "http://localhost:5000/login?format=json" \
  -H "Content-Type: application/json" \
  -d '{"email": "ada@ejemplo.mx", "password": "Secreto123"}' \
  | python3 -c "import sys, json; print(json.load(sys.stdin)['token'])")
```

Métodos disponibles (los siembra la migración: `efectivo`, `tarjeta`,
`transferencia`, `paypal`):

```bash
curl -s "http://localhost:5005/metodos?format=json" -H "Authorization: Bearer $TOKEN"
curl -s "http://localhost:5005/metodos?format=json&all=true" -H "Authorization: Bearer $TOKEN"
```

Consultar el saldo antes de cobrar — es la pregunta que hace una caja:

```bash
curl -s "http://localhost:5005/pedidos/42/saldo?format=json" \
  -H "Authorization: Bearer $TOKEN"
# {"orderId":42,"total":1120.0,"paid":0.0,"committed":0.0,"balance":1120.0}
```

Registrar un pago con tarjeta. El pedido se puede indicar por `orderId` o
por `orderNumber`:

```bash
curl -s -X POST "http://localhost:5005/pagos?format=json" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" -d '{
    "orderId": 42,
    "amount": 1120.00,
    "method": "tarjeta",
    "authorizationCode": "AUTH-9F2C41",
    "cardLast4": "4242",
    "idempotencyKey": "compra-42-intento-1"
  }'
```

El mismo pago con cuerpo XML, indicando el pedido por su número:

```bash
curl -s -X POST "http://localhost:5005/pagos?format=xml" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/xml" --data-binary '
<payment>
  <orderNumber>PED-000042</orderNumber>
  <amount>1120.00</amount>
  <method>tarjeta</method>
  <authorizationCode>AUTH-9F2C41</authorizationCode>
  <idempotencyKey>compra-42-intento-1</idempotencyKey>
</payment>'
```

Repetir la petición con la **misma** `idempotencyKey` devuelve el pago
original, no uno nuevo:

```bash
curl -s -X POST "http://localhost:5005/pagos?format=json" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"orderId": 42, "amount": 1120.00, "method": "tarjeta",
       "idempotencyKey": "compra-42-intento-1"}'
# {"idempotentReplay": true, "note": "Ya existía un pago con esa idempotencyKey..."}
```

Mandar datos de tarjeta se rechaza con `400`:

```bash
curl -s -X POST "http://localhost:5005/pagos?format=json" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"orderId": 42, "amount": 10, "method": "tarjeta",
       "cardNumber": "4111111111111111", "cvv": "123"}'
# 400: "Este servicio no acepta datos de tarjeta. Campos rechazados: cardnumber, cvv."
```

Pago en efectivo desde mostrador (nace `aplicado`; necesita
`payments:write` si se cobra a nombre de otro):

```bash
curl -s -X POST "http://localhost:5005/pagos?format=json" \
  -H "Authorization: Bearer $TOKEN_STAFF" \
  -H "Content-Type: application/json" \
  -d '{"orderNumber": "PED-000042", "amount": 1120.00, "method": "efectivo"}'
```

Consultar:

```bash
curl -s "http://localhost:5005/pagos?format=json&status=aplicado&limit=20" \
  -H "Authorization: Bearer $TOKEN"
curl -s "http://localhost:5005/pagos?format=json&orderId=42" -H "Authorization: Bearer $TOKEN"
curl -s "http://localhost:5005/pagos/7?format=json" -H "Authorization: Bearer $TOKEN"
curl -s "http://localhost:5005/pagos/referencia/PAG-000007?format=json" \
  -H "Authorization: Bearer $TOKEN"
curl -s "http://localhost:5005/pagos?format=json&all=true&method=tarjeta" \
  -H "Authorization: Bearer $TOKEN_STAFF"
```

Mover el estado del pago (siempre `payments:write`):

```bash
curl -s -X POST "http://localhost:5005/pagos/7/aplicar?format=json" \
  -H "Authorization: Bearer $TOKEN_STAFF" \
  -H "Content-Type: application/json" -d '{"authorizationCode": "AUTH-9F2C41"}'
# la respuesta trae orderStatusAfter: "pagado" si con esto se cubrió el total

curl -s -X POST "http://localhost:5005/pagos/7/rechazar?format=json" \
  -H "Authorization: Bearer $TOKEN_STAFF" \
  -H "Content-Type: application/json" -d '{"note": "la pasarela denegó el cargo"}'

curl -s -X POST "http://localhost:5005/pagos/7/reembolsar?format=json" \
  -H "Authorization: Bearer $TOKEN_STAFF" \
  -H "Content-Type: application/json" -d '{"note": "devolución acordada con el cliente"}'
```

---

## 3. Restricciones de la práctica

* **Flask sin blueprints.** Todas las rutas se registran con `@app.get` /
  `@app.post` sobre la única instancia `app` de `pagos/app.py`.
* **Psycopg 3** (`psycopg[binary,pool]`), consultas parametrizadas (`%s`) y
  una sola transacción por escritura. El nombre de la columna de
  ordenación sale de una **lista blanca** (`SORTABLE`).
* **La lógica delicada vive en la base.** Registrar un pago comprobando el
  saldo, aplicarlo y moverlo de estado son **procedimientos almacenados**:
  `sp_registrar_pago`, `sp_aplicar_pago` y `sp_cambiar_estado_pago`. Y el
  efecto sobre el pedido es un **disparador**, no una llamada HTTP al
  servicio de pedidos: así no se puede quedar a medias si el otro servicio
  está caído.
* **Sin credenciales en el código.** Todo sale de variables de entorno; el
  `.env` está en `.gitignore` y nunca se publica.
* **XML y JSON** para el mismo recurso, XML por omisión. El cuerpo de
  entrada también se acepta en JSON, XML o formulario.
* **CORS** enumerando los orígenes de las aplicaciones cliente. Este
  servicio **no usa cookies** (la identidad viaja en el JWT), de modo que
  `supports_credentials` queda en `false`.
* **Paquete compartido** `library_common`, instalado con
  `pip install -e packages/library_common`.
* **Importe máximo** de 1 000 000.00 por pago, redondeado a dos decimales.
  La moneda del pago debe coincidir con la del pedido: un cobro en otra
  divisa sería imposible de cuadrar, y lo rechaza un disparador.

---

## 4. Estructura

```
apps/services/pagos/
├── pagos/
│   ├── app.py              rutas Flask, CORS, rechazo de datos de tarjeta
│   ├── config.py           lectura del .env (vía library_common.settings)
│   ├── shared.py           store, database, codec, negotiator, resolver
│   ├── repository.py       todo el SQL (vistas + procedimientos almacenados)
│   ├── openapi.py          especificación OpenAPI 3.0.3 escrita a mano
│   ├── _bootstrap.py       deja importable library_common sin instalarlo
│   └── wsgi.py             punto de entrada para gunicorn
├── scripts/pruebas.sh      batería de humo con curl (+ psql en la VM)
├── test/test_pagos_mocked.py   pruebas sin PostgreSQL ni Redis
├── requirements.txt
├── .env                    credenciales propias del servicio (NO se publica)
└── .gitignore
```

No hay `cache.py`: **este servicio no cachea ninguna respuesta**. Un pago
es información financiera que cambia de estado constantemente y se lee
poco; cachearla daría un rendimiento que nadie necesita a cambio de un
riesgo real. Redis se usa aquí solo para la **revocación de tokens**, el
**caché de permisos de rol** y el **cerrojo** contra el cobro doble.

Lo que aporta la migración de este servicio:

```
data/pagos_migration.sql
    payment_methods           catálogo (efectivo, tarjeta, transferencia, paypal)
    payments                  el pago; sin instrumento de pago
    payment_status_history    bitácora de cambios de estado
    payment_reference_seq     numeración legible PAG-000001
    ux_payments_idempotency   índice único PARCIAL sobre idempotency_key
    sp_registrar_pago · sp_aplicar_pago · sp_cambiar_estado_pago
    trg_payments_settle_order el pedido pasa a 'pagado' solo
    v_payments_detail         pago con su pedido y su método
    v_order_balance           total, cobrado, comprometido y lo que falta
    v_orders_detail           REEMPLAZADA, ahora con paid_amount
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
  de donde salen `payments:read` y `payments:write`, y `users.role_id`, que
  es lo que el JWT transporta.
* `pedidos_migration.sql` crea `library.orders`, sin la cual `payments` no
  tiene a qué apuntar (`order_id` es una clave foránea con
  `ON DELETE RESTRICT`: un pago no se queda huérfano).
* `pagos_migration.sql` va **al final** porque, además de sus propias
  tablas, **reemplaza `v_orders_detail`** añadiéndole la columna
  `paid_amount`. `CREATE OR REPLACE VIEW` admite añadir columnas al final,
  que es exactamente lo que hace; pero esa columna agrega sobre
  `library.payments`, que hasta ese momento no existe. Al revés, la
  sentencia fallaría.

Las tres son idempotentes y pueden correrse dos veces sin daño.

Comprobación rápida:

```bash
psql -U library_user -d library_db -c \
  "SELECT library.sp_registrar_pago(1, 1, 199.00, 1, 'demo-001');"
psql -U library_user -d library_db -c "SELECT * FROM library.v_order_balance LIMIT 5;"
psql -U library_user -d library_db -c \
  "SELECT id, order_number, status, total, paid_amount FROM library.v_orders_detail LIMIT 5;"
```

### 5.2 Python, el paquete compartido y el código

```bash
sudo dnf install -y python3 python3-pip
sudo useradd --system --home-dir /opt/library --shell /sbin/nologin library || true

sudo mkdir -p /opt/library/packages
sudo cp -r packages/library_common /opt/library/packages/library_common
sudo cp -r apps/services/pagos /opt/library/pagos
sudo chown -R library:library /opt/library

sudo -u library python3 -m venv /opt/library/pagos/.venv
sudo -u library /opt/library/pagos/.venv/bin/pip install -r /opt/library/pagos/requirements.txt
sudo -u library /opt/library/pagos/.venv/bin/pip install -e /opt/library/packages/library_common
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
nombre anterior para no romper los despliegues que ya existen. Sin él,
`/health` reporta `jwt: missing_secret` y el servicio rechaza todo.

Lo **propio del servicio** va en su propio `.env`:

```bash
sudo -u library tee /opt/library/pagos/.env > /dev/null <<'EOF'
HOST=0.0.0.0
PORT=5005
DEBUG=false

# En producción enumere los orígenes; "*" solo sirve en desarrollo.
CORS_ORIGINS=*
CORS_MAX_AGE=86400

DEFAULT_FORMAT=xml
XML_NAMESPACE=urn:library:payments:1.0
XML_VERSION=1.0

DEFAULT_LIMIT=50
MAX_LIMIT=200
EOF
sudo chmod 600 /opt/library/pagos/.env
```

Precedencia: **entorno real > `.env` de la raíz > `.env` del servicio**.

### 5.4 Redis en la misma VM

```bash
sudo dnf install -y redis
sudo sed -i 's/^# *requirepass .*/requirepass CAMBIEME_password_redis/' /etc/redis/redis.conf
sudo sed -i 's/^bind .*/bind 0.0.0.0/' /etc/redis/redis.conf
sudo systemctl enable --now redis
redis-cli -a 'CAMBIEME_password_redis' ping        # PONG
```

Redis queda **expuesto** en el puerto 6379 porque los seis servicios lo
comparten —la revocación de tokens y el cerrojo contra el cobro doble
dependen de que sea el mismo servidor— y por eso `requirepass` no es
opcional. La contraseña viaja dentro de `REDIS_URL` con la forma
`redis://:password@host:6379/0`; el filtro de `logging_support` la tacha
antes de que llegue a cualquier log.

### 5.5 Servicio systemd

```bash
sudo tee /etc/systemd/system/library-pagos.service > /dev/null <<'EOF'
[Unit]
Description=Libreria en Linea — microservicio de pagos (Flask)
After=network-online.target postgresql.service redis.service
Wants=network-online.target

[Service]
Type=simple
User=library
Group=library
WorkingDirectory=/opt/library/pagos
ExecStart=/opt/library/pagos/.venv/bin/gunicorn \
          --workers 3 --bind 127.0.0.1:5005 \
          --access-logfile - --error-logfile - pagos.wsgi:application
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
sudo systemctl enable --now library-pagos
sudo systemctl status library-pagos
```

### 5.6 Proxy inverso y firewall

Con **nginx**:

```nginx
location /pagos/ {
    proxy_pass http://127.0.0.1:5005/;
    proxy_set_header Host              $host;
    proxy_set_header X-Real-IP         $remote_addr;
    proxy_set_header X-Forwarded-For   $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header Authorization     $http_authorization;
}
```

La última línea importa: si el proxy se come la cabecera `Authorization`,
**absolutamente todo** este servicio responde `401`, porque no tiene
ninguna ruta de datos pública.

`gunicorn` no lee `PORT` del `.env`: el puerto va en `--bind`.
**No añada cabeceras CORS en el proxy** (ya las emite Flask) y nunca active
el caché de nginx sobre estas rutas: son respuestas con información
financiera, y por eso Flask emite `Cache-Control: no-store`. Con SELinux,
recuerde `sudo setsebool -P httpd_can_network_connect 1`.

```bash
sudo firewall-cmd --permanent --add-service=http --add-service=https
sudo firewall-cmd --permanent --add-port=5005/tcp   # solo si necesita acceso directo
sudo firewall-cmd --permanent --add-port=6379/tcp   # Redis compartido
sudo firewall-cmd --reload
```

### 5.7 Verificación

```bash
curl -s "http://localhost:5005/health?format=json"
BASE=http://localhost:5005 ./scripts/pruebas.sh
```

`/health` responde `200` solo si PostgreSQL **y** Redis están sanos. Con
Redis caído devuelve `503` con `status: degraded`, igual que el
microservicio de usuarios y a diferencia de autores y pedidos: sin poder
comprobar la revocación de tokens, y sin ninguna puerta pública que
atender, este servicio no puede hacer **nada** útil. Decirlo es más honesto
que reportar un `200` engañoso.

---

## 6. Pruebas sin PostgreSQL ni Redis (esta máquina)

```bash
cd apps/services/pagos
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pip install -e ../../../packages/library_common
python test/test_pagos_mocked.py
```

`test/test_pagos_mocked.py` sustituye el `RedisStore` por el doble de
`library_common.testing` y el repositorio por uno en memoria que
**reproduce lo que hacen los procedimientos y disparadores**: el tope de
saldo, la máquina de estados y el pedido que pasa a `pagado` cuando lo
aplicado cubre el total. La corrección del SQL en sí se verifica en la VM
con `scripts/pruebas.sh`.

Cubre los diez bloques: que **nada** sea público (ni siquiera `/metodos`),
que un cliente pague lo suyo y cobrar lo ajeno exija permiso, el tope de
saldo, que efectivo nazca `aplicado` y tarjeta `pendiente`/`autorizado`,
que aplicar un pago que cubre el total pase el **pedido** a `pagado`, las
dos defensas contra el cobro doble (`idempotencyKey` devolviendo el mismo
pago y el cerrojo de Redis bloqueando dos registros simultáneos), el
rechazo de datos de tarjeta y la validación de `cardLast4`, rechazar y
reembolsar con sus transiciones imposibles, el saldo del pedido, y el
**fallo seguro total**: con Redis roto todo devuelve `503`, incluido
`/health`.

---

## 7. Códigos de error

Todos los errores salen con la misma forma, en XML o en JSON:
`{"error": {"status", "code", "message", "details": [...]}}`.

| Código | `code` | Cuándo |
|---|---|---|
| `400` | `validation_error` | Falta el pedido, el importe o el método; importe no numérico, cero, negativo o por encima del máximo; `cardLast4` que no son 4 dígitos; **cualquier campo de tarjeta prohibido**; estado desconocido; XML/JSON mal formado |
| `401` | `unauthorized` | Token ausente, malformado, inválido, **caducado** o **revocado** |
| `403` | `forbidden` | El pago o el pedido no son suyos y el rol no tiene `payments:read` / `payments:write` |
| `404` | `not_found` | No existe el pago, la referencia o el pedido |
| `409` | `conflict` | Importe que excede el saldo, pedido cancelado, método desactivado, pago en curso (cerrojo), transición no permitida, reembolsar un pago que no está `aplicado` |
| `503` | `redis_unavailable` · `database_unavailable` | Redis o PostgreSQL caídos |

### Las dos políticas de fallo de Redis

Son distintas a propósito en todo el proyecto, aunque en este servicio solo
se ve una de ellas en la práctica:

1. **Lecturas cacheadas — Redis es opcional.** Un fallo se trata como
   ausencia de caché y la petición sigue contra PostgreSQL; el cliente no
   se entera. Aquí no hay respuestas cacheadas, de modo que lo único que
   aplica es el caché de permisos de rol (`roles:perms:<id>`, TTL 300 s),
   que ante un fallo se resuelve leyendo `role_permissions` directamente.
2. **Sesiones, revocación y autorización — fallo seguro con `503`.** Si no
   se puede consultar si un `jti` está revocado, el token **no se acepta**.
   Como aquí toda ruta de datos exige token, el servicio entero devuelve
   `503`. En un servicio que mueve dinero, antes un `503` honesto que
   aceptar una credencial posiblemente revocada. El cerrojo contra el cobro
   doble va por la misma vía estricta: sin cerrojo no se registra el pago.

---

## 8. Seguridad

* **Lo que no se guarda no se puede filtrar.** Ni número de tarjeta, ni
  CVV, ni vencimiento, ni titular: el servicio los rechaza en la entrada y
  la base ni siquiera tiene columnas donde ponerlos. Solo
  `authorization_code` y `card_last4`, que publica la propia pasarela.
* El `.env` **no se publica** (`apps/services/pagos/.gitignore`), ni el de
  la raíz. Los secretos solo viajan por variables de entorno.
* Todo el SQL usa parámetros (`%s`); el único texto que se interpola es el
  nombre de columna de `ORDER BY`, y sale de una lista blanca.
* **El importe nunca se registra en el log junto a datos de la persona.**
  Se escribe el hecho: `Pago 7 registrado para el pedido 42 por user_id=3`.
  El filtro de `logging_support` tacha además `Bearer <token>`, cualquier
  JWT suelto y la contraseña dentro de una URL `redis://:x@host`.
* Verificación del JWT en cada petición, en este orden: cabecera `Bearer`
  bien formada → algoritmo esperado (se rechaza `none` y la confusión de
  algoritmos) → firma → `exp` e `iss` → claims obligatorios → `jti` no
  revocado.
* El estado del pedido lo cambia un **disparador**, no esta aplicación: no
  existe forma de marcar un pedido como pagado sin dinero detrás.
* Cabeceras `X-Content-Type-Options: nosniff`,
  `Referrer-Policy: no-referrer` y `Cache-Control: no-store` en todas las
  respuestas.
* `DEBUG=false` en el servidor: con `true`, los errores 500 devuelven el
  detalle interno al cliente.
