# Microservicio de usuarios — Flask + Psycopg 3 + PostgreSQL + Redis

Servicio independiente de **cuentas, roles, correos y contraseñas** para
`library_db` (esquema `library`). Expone sus respuestas en **XML** y
**JSON**; sin `?format=`, **XML** es el formato predeterminado.

Se documenta solo: **Swagger UI en `/docs`**, especificación OpenAPI 3.0.3
en `/openapi.json`.

Escucha en el puerto **5002**. Comparte el secreto del JWT y el servidor
Redis con los otros cinco servicios (login `5000`, libros `5001`, usuarios
`5002`, autores `5003`, pedidos `5004`, pagos `5005`).

---

## 1. Qué hace

| Operación | Endpoint | Quién puede |
|---|---|---|
| Listar cuentas | `GET /users` | `users:read` |
| Ver una cuenta | `GET /users/<id>` | la propia, o `users:read` |
| Alta administrativa | `POST /users` | `users:write` |
| Reemplazo completo | `PUT /users/<id>` | `users:write` |
| Cambio parcial | `PATCH /users/<id>` | la propia (nombres); campos administrativos con `users:write` |
| Baja **lógica** | `DELETE /users/<id>` | `users:write` |
| Cambiar contraseña | `PATCH /users/<id>/password` | la propia (con la actual), o `users:write` |
| Cambiar correo | `PATCH /users/<id>/email` | la propia, o `users:write` |
| Cambiar el rol | `PUT /users/<id>/role` | `users:roles` |
| Catálogo de roles | `GET /roles` · `GET /roles/<id>` | `users:read` |
| Crear un rol | `POST /roles` | `users:roles` |
| Fijar los permisos de un rol | `PUT /roles/<id>/permissions` | `users:roles` |
| Índice del servicio | `GET /` | público |
| Estado | `GET /health` | público |
| Contadores | `GET /metrics` | público |
| Documentación | `GET /docs` — `GET /openapi.json` | público |

### Aquí ninguna lectura es pública

Es la diferencia más visible con los microservicios de libros y autores:
allí el catálogo se sirve sin token porque es información pública. Una
lista de cuentas con sus correos **no lo es**, de modo que incluso los
`GET` exigen `Authorization: Bearer <JWT>`. El propio usuario ve su cuenta
con solo tener un token válido; para ver las de otros hace falta
`users:read`.

Por la misma razón los listados de cuentas **no se cachean en Redis**: son
datos personales, cambian con cada alta y el ahorro no compensa el riesgo
de servir la cuenta equivocada.

### `password_hash` nunca sale

`repository.public_user()` construye la respuesta campo por campo. No
filtra una fila completa: así, añadir una columna a `library.users` no la
publica por accidente. El hash bcrypt vive en la propia cuenta y jamás
aparece en XML ni en JSON.

### Por qué la baja es lógica

`DELETE /users/<id>` pone `is_active = false`; **no borra la fila**.
`library.orders` referencia a `library.users` con `ON DELETE RESTRICT` y un
pedido histórico no puede quedarse sin dueño. Desactivar conserva la
historia contable y cierra el acceso, que es lo que de verdad se quiere
cuando alguien dice "dar de baja". La respuesta lo dice explícitamente en
el campo `note`.

### Por qué cambiar el rol revoca sesiones

El JWT lleva `role_id` **dentro de la firma**. Si se cambia el rol en la
base y no se hace nada más, el usuario degradado seguiría operando con su
rol anterior hasta 30 minutos, que es lo que vive un token de acceso: no
hay forma de "editar" un token ya emitido.

Por eso cambiar el rol, la contraseña, el correo o desactivar una cuenta
**revoca en el acto todas las sesiones de ese usuario**: se recorre
`user:sessions:<id>` en Redis y cada `jti` se anota en `jwt:revoked:<jti>`
con lo que le quedaba de vida al token. Además se invalida
`roles:perms:<role_id>`, de modo que los seis servicios ven los permisos
nuevos en la siguiente petición y no cuando caduque el caché.

Si Redis no responde, la operación **completa se rechaza con 503**. No se
cambia un rol sin poder retirar el token que llevaba el rol anterior.

### Permisos que usa

| Permiso | Para qué |
|---|---|
| `users:read` | ver cuentas ajenas y el catálogo de roles |
| `users:write` | crear, modificar y desactivar cuentas |
| `users:roles` | cambiar el rol de una cuenta y editar los permisos de un rol |

`users:roles` es más estrecho que `users:write` a propósito: cambiar un rol
altera lo que ese usuario puede hacer en los **seis** microservicios, y no
tiene por qué venir incluido con el permiso de editar un apellido.

### El último administrador

La migración retira `ux_users_single_admin`, el índice que permitía **un
solo** admin y que hacía imposible administrar roles. Pero quedarse con
**cero** administradores activos deja el sistema sin nadie que pueda
arreglarlo, de modo que `_guard_last_admin()` rechaza con `409` degradar o
desactivar al único admin que queda.

---

## 2. Formatos

```
GET /users                  -> XML (por omisión)
GET /users?format=xml       -> XML
GET /users?format=json      -> JSON
GET /users?output=json      -> JSON (alias sin ambigüedad)
Accept: application/json    -> JSON
```

El orden de prioridad es: `?output=` / `?_format=` / `?format=` primero, la
cabecera `Accept` después, y `DEFAULT_FORMAT` del `.env` al final.

Todos los ejemplos necesitan un token emitido por el microservicio de
login:

```bash
TOKEN=$(curl -s -X POST "http://localhost:5000/login?format=json" \
  -H "Content-Type: application/json" \
  -d '{"email": "admin@libreria.mx", "password": "Secreto123"}' \
  | python3 -c "import sys, json; print(json.load(sys.stdin)['token'])")
```

Listar cuentas con filtros y paginación:

```bash
curl -s "http://localhost:5002/users?format=json&role=user&active=true&limit=10&sort=created&order=desc" \
  -H "Authorization: Bearer $TOKEN"
```

Alta administrativa (JSON). A diferencia del `/register` del login, aquí sí
se puede fijar el rol y marcar el correo como verificado: lo hace un
administrador, no el propio interesado.

```bash
curl -s -X POST "http://localhost:5002/users?format=json" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" -d '{
    "nombre": "Ada",
    "apellidoPaterno": "Lovelace",
    "apellidoMaterno": "Byron",
    "email": "ada@ejemplo.mx",
    "password": "Secreto123",
    "roleId": 3,
    "emailVerified": true
  }'
```

El mismo alta con cuerpo XML:

```bash
curl -s -X POST "http://localhost:5002/users?format=xml" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/xml" --data-binary '
<user>
  <nombre>Ada</nombre>
  <apellidoPaterno>Lovelace</apellidoPaterno>
  <apellidoMaterno>Byron</apellidoMaterno>
  <email>ada@ejemplo.mx</email>
  <password>Secreto123</password>
  <roleId>3</roleId>
</user>'
```

Cambiar la **propia** contraseña: hay que enviar la actual. Tener el token
no basta, porque un token robado no debe permitir apropiarse de la cuenta.

```bash
curl -s -X PATCH "http://localhost:5002/users/7/password?format=json" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"currentPassword": "Secreto123", "password": "OtroSecreto456"}'
```

Un administrador con `users:write` puede restablecerla sin conocer la
anterior (solo manda `password`). En ambos casos se cierran todas las
sesiones del usuario y la respuesta informa cuántas en `sessionsClosed`.

Cambiar el correo: queda **sin verificar**, porque el login exige correo
verificado para iniciar sesión y la propiedad del correo nuevo hay que
demostrarla con el token que llega por sendmail.

```bash
curl -s -X PATCH "http://localhost:5002/users/7/email?format=json" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" -d '{"email": "ada.nueva@ejemplo.mx"}'
```

Cambiar el rol y fijar los permisos de un rol:

```bash
curl -s -X PUT "http://localhost:5002/users/7/role?format=json" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" -d '{"role": "staff"}'

curl -s -X PUT "http://localhost:5002/roles/3/permissions?format=json" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"permissions": ["users:read", "books:write", "orders:read", "orders:status"]}'
```

`PUT /roles/<id>/permissions` **reemplaza** la lista completa, no añade. La
respuesta trae `cacheKeysInvalidated` con cuántas claves de Redis se
olvidaron.

Baja lógica:

```bash
curl -s -X DELETE "http://localhost:5002/users/7?format=json" \
  -H "Authorization: Bearer $TOKEN"
```

---

## 3. Restricciones de la práctica

* **Flask sin blueprints.** Todas las rutas se registran con `@app.get` /
  `@app.post` / `@app.put` / `@app.patch` / `@app.delete` sobre la única
  instancia `app` de `users/app.py`.
* **Psycopg 3** (`psycopg[binary,pool]`), consultas parametrizadas (`%s`) y
  una sola transacción por escritura. El nombre de la columna de
  ordenación sale de una **lista blanca** (`SORTABLE`), porque un nombre de
  columna no puede viajar como parámetro.
* **Sin credenciales en el código.** Todo sale de variables de entorno; el
  `.env` está en `.gitignore` y nunca se publica.
* **XML y JSON** para el mismo recurso, XML por omisión. El cuerpo de
  entrada también se acepta en JSON, XML o formulario.
* **CORS** enumerando los orígenes de las aplicaciones cliente. Este
  servicio **no usa cookies** (la identidad viaja en el JWT), de modo que
  `supports_credentials` queda en `false`.
* **bcrypt** para `password_hash`, con las mismas reglas de validación que
  el microservicio de login (mínimo 6 caracteres, máximo 72 bytes). Si el
  alta por login y el alta administrativa admitieran cosas distintas, la
  base acabaría con dos clases de cuentas.
* **Paquete compartido** `library_common`, instalado con
  `pip install -e packages/library_common`: JWT, Redis, PostgreSQL,
  negociación XML/JSON, errores y registro sin secretos están ahí para que
  los seis servicios se comporten igual sin copiar código.

---

## 4. Estructura

```
apps/services/users/
├── users/
│   ├── app.py              rutas Flask, CORS, autorización fina, errores
│   ├── config.py           lectura del .env (vía library_common.settings)
│   ├── shared.py           store, database, codec, negotiator, resolver
│   ├── repository.py       todo el SQL (cuentas, roles, permisos)
│   ├── validators.py       correo, nombres, contraseña, permisos, roles
│   ├── security.py         hash/verificación bcrypt
│   ├── openapi.py          especificación OpenAPI 3.0.3 escrita a mano
│   ├── _bootstrap.py       deja importable library_common sin instalarlo
│   └── wsgi.py             punto de entrada para gunicorn
├── scripts/pruebas.sh      batería de humo con curl (+ psql en la VM)
├── test/test_users_mocked.py   pruebas sin PostgreSQL ni Redis
├── requirements.txt
├── .env                    credenciales propias del servicio (NO se publica)
└── .gitignore
```

El paquete compartido y las migraciones viven fuera del servicio:

```
packages/library_common/library_common/
    settings.py       configuración común (secretos, TTL, PostgreSQL)
    jwt_auth.py       emisión/verificación de JWT y decoradores
    redis_store.py    sesiones, revocación, caché, cerrojos
    roles.py          vocabulario de permisos y resolutor de roles
    negotiation.py    XML/JSON
    errors.py         jerarquía de errores y códigos HTTP

data/roles_migration.sql    roles, permisos y users.role_id (este servicio)
```

---

## 5. Puesta en marcha en la instancia CentOS 10 Stream

Se asume PostgreSQL ya instalado con `library_user` / `library_db` y el
esquema inicial (`data/schema.sql`) aplicado.

### 5.1 Migración de la base (primero, desde la raíz del repo)

El orden importa: **roles → pedidos → pagos**. Este servicio necesita la
primera; las otras dos no le afectan, pero conviene aplicarlas en ese
orden porque `pagos_migration.sql` reemplaza `v_orders_detail` añadiéndole
`paid_amount`.

```bash
psql -U library_user -d library_db -f data/roles_migration.sql
```

Crea `library.roles` (1 admin, 2 user, 3 staff con ids fijos, que son los
que transporta el JWT en `role_id`), `library.role_permissions` —la
relación rol ↦ permiso es multivaluada, de modo que en 4FN va en su propia
tabla, igual que `book_authors`— y `users.role_id` con el disparador que lo
mantiene sincronizado en **ambos sentidos** con la columna ENUM `role`, que
se conserva para no romper el monolito. También retira
`ux_users_single_admin`.

El rol `user` no aparece en `role_permissions` a propósito: un cliente no
necesita ningún permiso especial para operar sobre lo suyo. Los permisos
son exclusivamente para lo **administrativo**.

### 5.2 Python, el paquete compartido y el código

```bash
sudo dnf install -y python3 python3-pip
sudo useradd --system --home-dir /opt/library --shell /sbin/nologin library || true

sudo mkdir -p /opt/library/packages
sudo cp -r packages/library_common /opt/library/packages/library_common
sudo cp -r apps/services/users /opt/library/users
sudo chown -R library:library /opt/library

sudo -u library python3 -m venv /opt/library/users/.venv
sudo -u library /opt/library/users/.venv/bin/pip install -r /opt/library/users/requirements.txt
sudo -u library /opt/library/users/.venv/bin/pip install -e /opt/library/packages/library_common
```

El `pip install -e` del paquete compartido **no es opcional**: sin él, el
servicio arranca gracias al respaldo de `_bootstrap.py` (que busca
`packages/library_common` dentro del repo), pero en `/opt/library` esa ruta
ya no existe con la misma forma y lo correcto es instalarlo en el venv.

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
`/health` reporta `jwt: missing_secret` y el servicio rechaza toda petición
autenticada.

Lo **propio del servicio** va en su propio `.env`:

```bash
sudo -u library tee /opt/library/users/.env > /dev/null <<'EOF'
HOST=0.0.0.0
PORT=5002
DEBUG=false

# En producción enumere los orígenes; "*" solo sirve en desarrollo.
CORS_ORIGINS=*
CORS_MAX_AGE=86400

DEFAULT_FORMAT=xml
XML_NAMESPACE=urn:library:users:1.0
XML_VERSION=1.0

DEFAULT_LIMIT=50
MAX_LIMIT=200
EOF
sudo chmod 600 /opt/library/users/.env
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
comparten, y por eso `requirepass` no es opcional. La contraseña viaja
dentro de `REDIS_URL` con la forma `redis://:password@host:6379/0`; el
filtro de `logging_support` la tacha antes de que llegue a cualquier log.

### 5.5 Servicio systemd

```bash
sudo tee /etc/systemd/system/library-users.service > /dev/null <<'EOF'
[Unit]
Description=Libreria en Linea — microservicio de usuarios (Flask)
After=network-online.target postgresql.service redis.service
Wants=network-online.target

[Service]
Type=simple
User=library
Group=library
WorkingDirectory=/opt/library/users
ExecStart=/opt/library/users/.venv/bin/gunicorn \
          --workers 3 --bind 127.0.0.1:5002 \
          --access-logfile - --error-logfile - users.wsgi:application
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
sudo systemctl enable --now library-users
sudo systemctl status library-users
```

### 5.6 Proxy inverso y firewall

Con **nginx**:

```nginx
location /users/ {
    proxy_pass http://127.0.0.1:5002/;
    proxy_set_header Host              $host;
    proxy_set_header X-Real-IP         $remote_addr;
    proxy_set_header X-Forwarded-For   $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header Authorization     $http_authorization;
}
```

La última línea importa: si el proxy se come la cabecera `Authorization`,
todas las peticiones llegan sin token y el servicio responde `401`.

`gunicorn` no lee `PORT` del `.env`: el puerto va en `--bind`.
**No añada cabeceras CORS en el proxy** (ya las emite Flask) y recuerde
`sudo setsebool -P httpd_can_network_connect 1` con SELinux.

```bash
sudo firewall-cmd --permanent --add-service=http --add-service=https
sudo firewall-cmd --permanent --add-port=5002/tcp   # solo si necesita acceso directo
sudo firewall-cmd --permanent --add-port=6379/tcp   # Redis compartido
sudo firewall-cmd --reload
```

### 5.7 Verificación

```bash
curl -s "http://localhost:5002/health?format=json"
BASE=http://localhost:5002 ./scripts/pruebas.sh
```

`/health` responde `200` solo si PostgreSQL **y** Redis están sanos. Con
Redis caído devuelve `503` con `status: degraded`, y lo dice: sin poder
comprobar la revocación de tokens este servicio no acepta ninguna
petición, de modo que no puede hacer nada útil y fingir que está sano
sería mentir.

---

## 6. Pruebas sin PostgreSQL ni Redis (esta máquina)

```bash
cd apps/services/users
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pip install -e ../../../packages/library_common
python test/test_users_mocked.py
```

`test/test_users_mocked.py` sustituye el repositorio por diccionarios en
memoria y el `RedisStore` por el doble de `library_common.testing`. Recorre
los doce bloques que importan: que ninguna lectura sea pública, la
autorización de grano fino (propio vs. ajeno), alta/reemplazo/cambio
parcial/baja lógica, que `password_hash` no salga nunca ni en XML ni en
JSON, que cambiar la propia contraseña exija la actual, que cambiar el
correo lo deje sin verificar, que rol/contraseña/correo/baja revoquen
sesiones en Redis, que no se pueda dejar el sistema sin administradores, el
reemplazo de permisos con invalidación de caché, los dos formatos, y el
**fallo seguro**: con Redis roto todo devuelve `503 redis_unavailable` y
cuando Redis vuelve, el servicio funciona de nuevo.

---

## 7. Códigos de error

Todos los errores salen con la misma forma, en XML o en JSON:
`{"error": {"status", "code", "message", "details": [...]}}`.

| Código | `code` | Cuándo |
|---|---|---|
| `400` | `validation_error` | Campos inválidos, XML/JSON mal formado, cambiar rol/correo/contraseña por la ruta equivocada |
| `401` | `unauthorized` | Token ausente, malformado, inválido, **caducado** o **revocado**; contraseña actual incorrecta |
| `403` | `forbidden` | Token válido pero el rol no tiene `users:read` / `users:write` / `users:roles`, o se intenta tocar la cuenta de otro |
| `404` | `not_found` | No existe la cuenta o el rol |
| `409` | `conflict` | Correo ya registrado, nombre de rol repetido, último administrador activo, quitarle `*` al rol admin |
| `503` | `redis_unavailable` · `database_unavailable` | Redis o PostgreSQL caídos |

### Las dos políticas de fallo de Redis

Son distintas a propósito, y conviene tenerlas claras:

1. **Lecturas cacheadas — Redis es opcional.** Un fallo se trata como
   ausencia de caché y la petición sigue contra PostgreSQL; el cliente no
   se entera. En este servicio casi no aplica, porque las cuentas no se
   cachean; sí aplica al caché de permisos de rol (`roles:perms:<id>`, TTL
   300 s), que ante un fallo de Redis se resuelve leyendo
   `role_permissions` directamente.
2. **Sesiones, revocación y autorización — fallo seguro con `503`.** Si no
   se puede consultar si un `jti` está revocado, el token **no se acepta**.
   Antes un `503` honesto que arriesgarse a honrar una credencial que ya
   fue retirada. Lo mismo al revés: no se cambia un rol si no se pueden
   revocar los tokens que llevaban el rol anterior.

---

## 8. Seguridad

* El `.env` **no se publica** (`apps/services/users/.gitignore`), ni el de
  la raíz. Los secretos solo viajan por variables de entorno.
* Solo se guarda el **hash bcrypt** de la contraseña. `public_user()` la
  omite por construcción, no por filtrado.
* Todo el SQL usa parámetros (`%s`); el único texto que se interpola es el
  nombre de columna de `ORDER BY`, y sale de una lista blanca.
* El filtro de `logging_support` tacha mecánicamente `Bearer <token>`,
  cualquier JWT suelto, `password`/`contrasena`/`secret` y la contraseña
  dentro de una URL `redis://:x@host`. No se registran correos completos en
  las altas: basta el `id` para auditar.
* Verificación del JWT en cada petición, en este orden: cabecera `Bearer`
  bien formada → algoritmo esperado (se rechaza `none` y la confusión de
  algoritmos) → firma → `exp` e `iss` → claims obligatorios → `jti` no
  revocado.
* Cabeceras `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer`
  y `Cache-Control: no-store` en las respuestas con datos del usuario: el
  caché de verdad es el de Redis, del lado del servidor, donde se puede
  invalidar.
* `DEBUG=false` en el servidor: con `true`, los errores 500 devuelven el
  detalle interno al cliente.
