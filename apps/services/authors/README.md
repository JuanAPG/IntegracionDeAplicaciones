# Microservicio de autores — Flask + Psycopg 3 + PostgreSQL + Redis

Servicio independiente del **catálogo de autores y su relación con los
libros** de `library_db` (esquema `library`). Expone sus respuestas en
**XML** y **JSON**; sin `?format=`, **XML** es el formato predeterminado.

Se documenta solo: **Swagger UI en `/docs`**, especificación OpenAPI 3.0.3
en `/openapi.json`.

Escucha en el puerto **5003**. Comparte el secreto del JWT y el servidor
Redis con los otros cinco servicios (login `5000`, libros `5001`, usuarios
`5002`, autores `5003`, pedidos `5004`, pagos `5005`).

---

## 1. Qué hace

| Operación | Endpoint | Quién puede |
|---|---|---|
| Catálogo de autores | `GET /authors` | **público**, cacheado |
| Un autor con sus obras | `GET /authors/<id>` | **público**, cacheado |
| Obras del autor | `GET /authors/<id>/books` | **público**, cacheado |
| Alta de autor | `POST /authors` | `authors:write` |
| Renombrar | `PUT /authors/<id>` · `PATCH /authors/<id>` | `authors:write` |
| Baja de autor | `DELETE /authors/<id>` | `authors:write` |
| Fijar las obras del autor | `PUT /authors/<id>/books` | `authors:write` |
| Vincular una obra | `POST /authors/<id>/books/<bookId>` | `authors:write` |
| Desvincular una obra | `DELETE /authors/<id>/books/<bookId>` | `authors:write` |
| Índice del servicio | `GET /` | público |
| Estado | `GET /health` | público |
| Contadores | `GET /metrics` | público |
| Documentación | `GET /docs` — `GET /openapi.json` | público |

### Qué es público y qué no

Las **lecturas son públicas**: quién escribió un libro es información de
catálogo, exactamente la misma que ya publica `GET /books` del
microservicio de libros. Van cacheadas en Redis con TTL corto (30 s los
listados, 60 s las fichas).

Las **escrituras** exigen `Authorization: Bearer <JWT>` y el permiso
`authors:write` del rol. Si viene un token en una lectura, se verifica de
verdad —un token inválido sigue siendo `401`— pero no hace falta para
leer.

### Dónde acaba este servicio

Administra `library.authors` y la tabla `library.book_authors`. **No toca
los datos del libro** (título, precio, stock): eso es del microservicio de
libros, que es su dueño. Por eso la ficha de un autor devuelve un
**resumen** de cada obra (id, ISBN, título, año, precio, stock) y no el
libro completo: para la ficha entera está `GET /books/<id>` en el `5001`.

La relación libro ↦ autor es **multivaluada** (un libro tiene muchos
autores y un autor muchos libros), de modo que en 4FN vive en su propia
tabla, `book_authors`, tal como la creó `data/schema.sql`.

### Por qué `PUT` y `PATCH` hacen lo mismo

Un autor tiene **un solo campo editable**: el nombre. Entre "reemplazo
completo" y "cambio parcial" no hay diferencia posible cuando solo hay un
campo, y fingir que la hay sería peor que decirlo. Las dos rutas apuntan a
la misma función `update_author()`.

Lo que sí es distinto es cambiar sus **obras**: para eso está
`PUT /authors/<id>/books`, que fija la lista completa en una sola
transacción, y el par `POST`/`DELETE .../books/<bookId>` para tocar una
sola relación.

### Por qué borrar un autor con obras exige `?force=true`

`book_authors` cae por `ON DELETE CASCADE`. Borrar un autor que tiene
obras **dejaría esos libros sin autoría de forma silenciosa**: el `DELETE`
respondería `200` y nadie se enteraría de que se perdió un dato hasta
verlo en el catálogo.

Por eso `DELETE /authors/<id>` responde `409` cuando el autor tiene obras,
diciendo cuántas son y qué va a pasar, y solo procede si se repite la
petición con `?force=true`. Obligar a confirmarlo cuesta una petición más;
perder el dato sin avisar cuesta mucho más.

### Invalidación cruzada con el catálogo de libros

Cambiar un autor cambia también el cuerpo de **los libros**, porque la
ficha de un libro incluye sus autores y el microservicio de libros la
cachea en `books:*`. Hay un solo Redis compartido, de modo que cada
escritura de aquí invalida **las dos familias de claves**: `authors:*` y
`books:*`.

La alternativa sería llamar a un endpoint de invalidación del servicio de
libros por HTTP, pero eso acopla los dos servicios y falla justo cuando el
otro está caído. El caché es estado compartido: se toca donde vive.

---

## 2. Formatos

```
GET /authors                -> XML (por omisión)
GET /authors?format=xml     -> XML
GET /authors?format=json    -> JSON
GET /authors?output=json    -> JSON (alias sin ambigüedad)
Accept: application/json    -> JSON
```

El orden de prioridad es: `?output=` / `?_format=` / `?format=` primero, la
cabecera `Accept` después, y `DEFAULT_FORMAT` del `.env` al final. La
representación forma parte de la clave de caché, de modo que XML y JSON se
guardan por separado.

Lecturas públicas, sin token:

```bash
curl -s "http://localhost:5003/authors?format=json&q=lovelace&limit=10&sort=books&order=desc"
curl -s "http://localhost:5003/authors/1?format=json"
curl -s "http://localhost:5003/authors/1/books?format=json"
curl -s "http://localhost:5003/authors?format=json&has_books=false"   # autores sin obras
curl -s "http://localhost:5003/authors/1"                              # XML por omisión
```

Las escrituras necesitan un token emitido por el microservicio de login,
con un rol que tenga `authors:write` (admin o staff):

```bash
TOKEN=$(curl -s -X POST "http://localhost:5000/login?format=json" \
  -H "Content-Type: application/json" \
  -d '{"email": "admin@libreria.mx", "password": "Secreto123"}' \
  | python3 -c "import sys, json; print(json.load(sys.stdin)['token'])")
```

Alta de autor, opcionalmente vinculando obras de una vez:

```bash
curl -s -X POST "http://localhost:5003/authors?format=json" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name": "Ada Lovelace", "books": [10, 11]}'
```

El mismo alta con cuerpo XML (las listas van como elementos repetidos):

```bash
curl -s -X POST "http://localhost:5003/authors?format=xml" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/xml" --data-binary '
<author>
  <name>Ada Lovelace</name>
  <books>
    <book>10</book>
    <book>11</book>
  </books>
</author>'
```

Renombrar (`PUT` y `PATCH` son equivalentes):

```bash
curl -s -X PATCH "http://localhost:5003/authors/1?format=json" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" -d '{"name": "Augusta Ada King"}'
```

Fijar la lista **completa** de obras: lo que no venga se desvincula, todo
en una sola transacción, de modo que no existe un instante en el que el
autor se quede sin ninguna obra. La respuesta trae `linked` y `unlinked`.

```bash
curl -s -X PUT "http://localhost:5003/authors/1/books?format=json" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" -d '{"books": [10, 12]}'
```

Vincular y desvincular una sola obra. Vincular es **idempotente**:
repetirlo responde `200` con `alreadyLinked: true` en vez de `201`, y no
es un error.

```bash
curl -s -X POST "http://localhost:5003/authors/1/books/11?format=json" \
  -H "Authorization: Bearer $TOKEN"

curl -s -X DELETE "http://localhost:5003/authors/1/books/11?format=json" \
  -H "Authorization: Bearer $TOKEN"
```

Borrar un autor. Con obras, la primera llamada falla a propósito:

```bash
curl -s -X DELETE "http://localhost:5003/authors/1?format=json" \
  -H "Authorization: Bearer $TOKEN"
# 409: "El autor 'Ada Lovelace' tiene 2 obra(s) en el catálogo."

curl -s -X DELETE "http://localhost:5003/authors/1?force=true&format=json" \
  -H "Authorization: Bearer $TOKEN"
# 200: {"deleted": true, "booksUnlinked": 2}
```

---

## 3. Restricciones de la práctica

* **Flask sin blueprints.** Todas las rutas se registran con `@app.get` /
  `@app.post` / `@app.put` / `@app.patch` / `@app.delete` sobre la única
  instancia `app` de `authors/app.py`.
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
* **Paquete compartido** `library_common`, instalado con
  `pip install -e packages/library_common`: JWT, Redis, PostgreSQL,
  negociación XML/JSON, caché de respuestas, errores y registro sin
  secretos están ahí para que los seis servicios se comporten igual sin
  copiar código.

---

## 4. Estructura

```
apps/services/authors/
├── authors/
│   ├── app.py              rutas Flask, CORS, validación, errores
│   ├── config.py           lectura del .env (vía library_common.settings)
│   ├── shared.py           store, database, codec, negotiator, resolver
│   ├── cache.py            claves authors:* e invalidación cruzada con books:*
│   ├── repository.py       todo el SQL (authors, book_authors)
│   ├── openapi.py          especificación OpenAPI 3.0.3 escrita a mano
│   ├── _bootstrap.py       deja importable library_common sin instalarlo
│   └── wsgi.py             punto de entrada para gunicorn
├── scripts/pruebas.sh      batería de humo con curl (+ psql en la VM)
├── test/test_authors_mocked.py   pruebas sin PostgreSQL ni Redis
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
    response_cache.py caché de respuestas HTTP ya serializadas
    roles.py          vocabulario de permisos y resolutor de roles
    negotiation.py    XML/JSON
    errors.py         jerarquía de errores y códigos HTTP

data/roles_migration.sql    roles y permisos (de ahí sale authors:write)
```

`library.authors` y `library.book_authors` ya existen desde
`data/schema.sql`: este servicio **no añade tablas**, solo las administra.

---

## 5. Puesta en marcha en la instancia CentOS 10 Stream

Se asume PostgreSQL ya instalado con `library_user` / `library_db` y el
esquema inicial (`data/schema.sql`) aplicado.

### 5.1 Migración de la base (primero, desde la raíz del repo)

El orden de las migraciones es **roles → pedidos → pagos**
(`pagos_migration.sql` reemplaza `v_orders_detail` para añadirle
`paid_amount`, de modo que necesita que la de pedidos ya esté aplicada).
Este servicio solo depende de la primera:

```bash
psql -U library_user -d library_db -f data/roles_migration.sql
```

Crea `library.roles`, `library.role_permissions` —de donde sale el permiso
`authors:write`, concedido a `admin` (por el comodín `*`) y a `staff`— y
`users.role_id`, que es lo que el JWT transporta en el claim `role_id`.

### 5.2 Python, el paquete compartido y el código

```bash
sudo dnf install -y python3 python3-pip
sudo useradd --system --home-dir /opt/library --shell /sbin/nologin library || true

sudo mkdir -p /opt/library/packages
sudo cp -r packages/library_common /opt/library/packages/library_common
sudo cp -r apps/services/authors /opt/library/authors
sudo chown -R library:library /opt/library

sudo -u library python3 -m venv /opt/library/authors/.venv
sudo -u library /opt/library/authors/.venv/bin/pip install -r /opt/library/authors/requirements.txt
sudo -u library /opt/library/authors/.venv/bin/pip install -e /opt/library/packages/library_common
```

El `pip install -e` del paquete compartido **no es opcional**: sin él, el
servicio arranca gracias al respaldo de `_bootstrap.py` (que busca
`packages/library_common` subiendo directorios dentro del repo), pero en
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
`/health` reporta `jwt: missing_secret` y las escrituras se rechazan.

Lo **propio del servicio** va en su propio `.env`:

```bash
sudo -u library tee /opt/library/authors/.env > /dev/null <<'EOF'
HOST=0.0.0.0
PORT=5003
DEBUG=false

# En producción enumere los orígenes; "*" solo sirve en desarrollo.
CORS_ORIGINS=*
CORS_MAX_AGE=86400

DEFAULT_FORMAT=xml
XML_NAMESPACE=urn:library:authors:1.0
XML_VERSION=1.0

DEFAULT_LIMIT=50
MAX_LIMIT=200

# Poner en false deja el servicio funcionando sin caché (útil para depurar).
CACHE_ENABLED=true
EOF
sudo chmod 600 /opt/library/authors/.env
```

Precedencia: **entorno real > `.env` de la raíz > `.env` del servicio**.

### 5.4 Redis en la misma VM

```bash
sudo dnf install -y redis
sudo sed -i 's/^# *requirepass .*/requirepass CAMBIEME_password_redis/' /etc/redis/redis.conf
sudo sed -i 's/^bind .*/bind 0.0.0.0/' /etc/redis/redis.conf
sudo systemctl enable --now redis
redis-cli -a 'CAMBIEME_password_redis' ping        # PONG
redis-cli -a 'CAMBIEME_password_redis' --scan --pattern 'authors:*'
```

Redis queda **expuesto** en el puerto 6379 porque los seis servicios lo
comparten —el caché cruzado `authors:*` / `books:*` depende de que sea el
mismo servidor— y por eso `requirepass` no es opcional. La contraseña
viaja dentro de `REDIS_URL` con la forma `redis://:password@host:6379/0`;
el filtro de `logging_support` la tacha antes de que llegue a cualquier
log.

### 5.5 Servicio systemd

```bash
sudo tee /etc/systemd/system/library-authors.service > /dev/null <<'EOF'
[Unit]
Description=Libreria en Linea — microservicio de autores (Flask)
After=network-online.target postgresql.service redis.service
Wants=network-online.target

[Service]
Type=simple
User=library
Group=library
WorkingDirectory=/opt/library/authors
ExecStart=/opt/library/authors/.venv/bin/gunicorn \
          --workers 3 --bind 127.0.0.1:5003 \
          --access-logfile - --error-logfile - authors.wsgi:application
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
sudo systemctl enable --now library-authors
sudo systemctl status library-authors
```

### 5.6 Proxy inverso y firewall

Con **nginx**:

```nginx
location /authors/ {
    proxy_pass http://127.0.0.1:5003/;
    proxy_set_header Host              $host;
    proxy_set_header X-Real-IP         $remote_addr;
    proxy_set_header X-Forwarded-For   $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header Authorization     $http_authorization;
}
```

La última línea importa: si el proxy se come la cabecera `Authorization`,
las lecturas siguen funcionando (son públicas) pero toda escritura
responde `401`, que es el síntoma más desconcertante posible.

`gunicorn` no lee `PORT` del `.env`: el puerto va en `--bind`.
**No añada cabeceras CORS en el proxy** (ya las emite Flask) y tampoco
active el caché de nginx sobre estas rutas: el caché de verdad es el de
Redis, donde se puede invalidar. Con SELinux, recuerde
`sudo setsebool -P httpd_can_network_connect 1`.

```bash
sudo firewall-cmd --permanent --add-service=http --add-service=https
sudo firewall-cmd --permanent --add-port=5003/tcp   # solo si necesita acceso directo
sudo firewall-cmd --permanent --add-port=6379/tcp   # Redis compartido
sudo firewall-cmd --reload
```

### 5.7 Verificación

```bash
curl -s "http://localhost:5003/health?format=json"
curl -si "http://localhost:5003/authors?format=json" | grep -i x-cache   # MISS
curl -si "http://localhost:5003/authors?format=json" | grep -i x-cache   # HIT
BASE=http://localhost:5003 ./scripts/pruebas.sh
```

`/health` responde `200` incluso con Redis caído, con `status: degraded` y
un aviso que lo explica: las lecturas públicas siguen funcionando (solo
pierden el caché), de modo que el servicio sí está haciendo algo útil.
Solo PostgreSQL caído lo lleva a `503`.

---

## 6. Pruebas sin PostgreSQL ni Redis (esta máquina)

```bash
cd apps/services/authors
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pip install -e ../../../packages/library_common
python test/test_authors_mocked.py
```

`test/test_authors_mocked.py` sustituye el repositorio por diccionarios en
memoria y el `RedisStore` por el doble de `library_common.testing`. Cuenta
los viajes a la "base" para comprobar que el segundo `GET` no llega a ella
(MISS → HIT, con XML y JSON contados por separado), y recorre: `401` sin
token, `403` sin `authors:write`, alta y renombrado con unicidad (`409`),
la baja rechazada salvo `?force=true`, el juego completo de la relación con
libros, que **cada escritura invalide `authors:*` y `books:*`**, el token
revocado (`401`) y el **fallo asimétrico de Redis**: con Redis roto las
lecturas responden `200` y las escrituras `503 redis_unavailable`.

---

## 7. Códigos de error

Todos los errores salen con la misma forma, en XML o en JSON:
`{"error": {"status", "code", "message", "details": [...]}}`.

| Código | `code` | Cuándo |
|---|---|---|
| `400` | `validation_error` | Nombre vacío o con caracteres no válidos, ids de libro no numéricos, `has_books` que no es booleano, XML/JSON mal formado |
| `401` | `unauthorized` | Token ausente, malformado, inválido, **caducado** o **revocado** |
| `403` | `forbidden` | Token válido pero el rol no tiene `authors:write` |
| `404` | `not_found` | No existe el autor, el libro, o la relación que se quiere desvincular |
| `409` | `conflict` | Nombre de autor repetido, o borrar un autor con obras sin `?force=true` |
| `503` | `redis_unavailable` · `database_unavailable` | Redis caído **en una escritura**, o PostgreSQL caído |

### Las dos políticas de fallo de Redis

Son distintas a propósito, y este servicio es donde mejor se ven porque
tiene tráfico de los dos tipos:

1. **Lecturas cacheadas — Redis es opcional.** Cualquier fallo se trata
   como ausencia de caché y la petición sigue contra PostgreSQL; el
   cliente no se entera. `GET /authors` responde `200` con Redis apagado.
   El TTL corto (30 s / 60 s) es además la red de seguridad: si una
   invalidación se pierde porque Redis estaba caído en ese momento, la
   entrada caduca sola en segundos.
2. **Sesiones, revocación y autorización — fallo seguro con `503`.** Si no
   se puede consultar si un `jti` está revocado, el token **no se acepta**,
   y como toda escritura exige token, toda escritura devuelve `503`. Antes
   un `503` honesto que dejar que alguien a quien se le retiró el permiso
   siga editando el catálogo durante los minutos que le queden al token.

---

## 8. Seguridad

* El `.env` **no se publica** (`apps/services/authors/.gitignore`), ni el
  de la raíz. Los secretos solo viajan por variables de entorno.
* Todo el SQL usa parámetros (`%s`); el único texto que se interpola es el
  nombre de columna de `ORDER BY`, y sale de una lista blanca.
* El nombre del autor se normaliza (espacios colapsados, máximo 150
  caracteres, que es lo que admite `library.authors.name`) y se rechazan
  caracteres de control y `<`/`>`: se admite cualquier grafía de nombre
  propio —acentos, guiones, puntos, apóstrofos— pero no etiquetas.
* El filtro de `logging_support` tacha mecánicamente `Bearer <token>`,
  cualquier JWT suelto y la contraseña dentro de una URL
  `redis://:x@host`. Las escrituras registran el `id` del autor y el
  `user_id` de quien las hizo, nada más.
* Verificación del JWT en cada escritura, en este orden: cabecera `Bearer`
  bien formada → algoritmo esperado (se rechaza `none` y la confusión de
  algoritmos) → firma → `exp` e `iss` → claims obligatorios → `jti` no
  revocado.
* Cabeceras `X-Content-Type-Options: nosniff` y
  `Referrer-Policy: no-referrer` en todas las respuestas.
* `DEBUG=false` en el servidor: con `true`, los errores 500 devuelven el
  detalle interno al cliente.
