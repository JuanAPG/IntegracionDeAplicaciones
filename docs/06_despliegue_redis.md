# Despliegue de Redis y de los cuatro microservicios nuevos

Guía de puesta en marcha sobre la instancia **CentOS 10 Stream** de GCP.
Se asume que PostgreSQL ya está instalado con `library_db` / `library_user`
y que los microservicios **login** (5000) y **books** (5001) ya corren como
unidades de systemd, tal como describen
[`apps/services/login/README.md`](../apps/services/login/README.md) §5 y
[`library_soap_service/README.md`](../library_soap_service/README.md) §11.

> La IP pública de la instancia es **efímera** y cambia cada vez que se
> reinicia. En esta guía aparece como `<IP_VM>`; al momento de escribirla
> era `34.51.14.158`. Verifíquela antes de copiar cualquier comando que la
> lleve.

---

## 1. Qué cambia en esta entrega

Hasta ahora había dos microservicios independientes, cada uno con su propia
copia del código de autenticación, y la sesión de login vivía dentro de la
cookie firmada de Flask. Esta entrega introduce tres cosas:

1. **Redis** como capa compartida de estado: sesiones, lista de revocación
   de JWT, caché de lecturas, caché de permisos por rol y cerrojos.
2. **Un paquete común** (`packages/library_common`) que los seis servicios
   instalan en su venv, en lugar de copiar seis veces el mismo código.
3. **Cuatro microservicios nuevos**: usuarios, autores, pedidos y pagos.

### Mapa de puertos

| Componente | Puerto | Unidad systemd | Estado |
|---|---|---|---|
| Monolito web (Node) | 3000 | — | existente |
| Microservicio de autenticación (**login**) | 5000 | `library-login` | se actualiza |
| Microservicio de libros (**books** / soap) | 5001 | `library-soap` | se actualiza |
| Microservicio de usuarios (**users**) | 5002 | `library-users` | **nuevo** |
| Microservicio de autores (**authors**) | 5003 | `library-authors` | **nuevo** |
| Microservicio de pedidos (**pedidos**) | 5004 | `library-pedidos` | **nuevo** |
| Microservicio de pagos (**pagos**) | 5005 | `library-pagos` | **nuevo** |
| **Redis** | 6379 | `redis` | **nuevo** |

Los seis servicios HTTP escuchan en `127.0.0.1:<puerto>` (gunicorn) y se
publican por el proxy inverso. Redis escucha en `0.0.0.0:6379` por una
decisión explícita que se justifica —y se acota— en la sección siguiente.

---

## 2. Redis en la instancia

### 2.1 Instalación

```bash
sudo dnf install -y redis
```

### 2.2 Generar la contraseña

Hágalo **antes** de editar la configuración: el mismo valor va en
`/etc/redis/redis.conf` y en el `REDIS_URL` del `.env` de la raíz. Si no
coinciden, todos los servicios arrancan y fallan con `NOAUTH`.

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
```

### 2.3 Configuración

```bash
sudo cp /etc/redis/redis.conf /etc/redis/redis.conf.bak
sudo vi /etc/redis/redis.conf
```

Deje estas directivas así (busque cada una; algunas vienen comentadas):

```conf
# --- Autenticación ---------------------------------------------------
# Sin esto, cualquiera que alcance el puerto 6379 lee y escribe todo.
requirepass PEGUE_AQUI_LA_CONTRASENA_GENERADA

# --- Interfaces de escucha -------------------------------------------
# Por omisión Redis escucha solo en 127.0.0.1. Se abre a todas las
# interfaces para poder depurar con redis-cli desde la Mac; el acceso
# real lo limita la regla de firewall de GCP (2.5), no esta línea.
bind 0.0.0.0

# protected-mode es la red de seguridad que Redis activa cuando detecta
# bind abierto; con requirepass puesto y el firewall acotado se apaga a
# conciencia. Si alguna vez quita el requirepass, vuelva a ponerla en yes.
protected-mode no

# --- Memoria ----------------------------------------------------------
# Techo duro: Redis no se come la RAM de la VM ni provoca que el kernel
# mate a PostgreSQL. Ajústelo a ~1/4 de la memoria de la instancia.
maxmemory 256mb

# Qué hacer al llegar al techo: descartar las claves menos usadas
# recientemente que TENGAN expiración. Todas nuestras claves (sesiones,
# revocación, caché) la tienen, de modo que la política nunca tira un
# dato sin fecha de caducidad; simplemente adelanta el vencimiento de lo
# más frío. Con `noeviction` las escrituras empezarían a fallar.
maxmemory-policy allkeys-lru
```

### 2.4 Arranque y firewall de la VM

```bash
sudo systemctl enable --now redis
sudo systemctl status redis

sudo firewall-cmd --permanent --add-port=6379/tcp
sudo firewall-cmd --reload
```

### 2.5 Regla de GCP — **aquí está el riesgo**

Exponer el 6379 a Internet es la parte peligrosa de esta guía, y conviene
decir exactamente qué se arriesga: **en Redis viven las claves de sesión y
la lista de revocación de JWT**. Quien pueda leerlas obtiene identificadores
de sesión activos de usuarios reales —puede suplantarlos sin saber su
contraseña— y quien pueda escribirlas puede **borrar la lista de revocación**,
con lo que un token que ya se había cerrado vuelve a ser válido. La caché del
catálogo es lo de menos; lo grave es que Redis es, de hecho, el registro de
"quién está dentro".

Por eso la regla **no** debe quedar abierta al mundo. Ponga como
`--source-ranges` la IP pública de su equipo, no `0.0.0.0/0`:

```bash
# La IP desde la que usted se conecta (ejecútelo en la Mac):
curl -s https://ifconfig.me ; echo

# La regla, con esa IP y /32 (un solo host):
gcloud compute firewall-rules create library-redis-debug \
    --description="Redis 6379 solo para depuracion desde el equipo del desarrollador" \
    --direction=INGRESS \
    --action=allow \
    --rules=tcp:6379 \
    --source-ranges=<SU_IP_PUBLICA>/32 \
    --target-tags=library-server
```

La etiqueta `library-server` debe estar aplicada a la instancia
(`gcloud compute instances add-tags <instancia> --tags=library-server`).
Si su IP doméstica también cambia, actualice la regla en lugar de abrirla:

```bash
gcloud compute firewall-rules update library-redis-debug \
    --source-ranges=<NUEVA_IP>/32
```

Y cuando termine de depurar, bórrela. Es gratis volver a crearla:

```bash
gcloud compute firewall-rules delete library-redis-debug
```

### 2.6 Comprobación

En la instancia:

```bash
redis-cli -a '<clave>' ping          # -> PONG
```

Desde la Mac, que es el motivo por el que se abrió el puerto:

```bash
redis-cli -h <IP_VM> -a '<clave>' ping          # -> PONG
redis-cli -h <IP_VM> -a '<clave>' info server | head
```

Si el `ping` local responde `PONG` pero el remoto se queda colgado, el
problema es de red (regla de GCP o `firewall-cmd`), no de Redis. Si el
remoto responde `NOAUTH Authentication required`, la red está bien y lo que
falla es la contraseña.

> `redis-cli -a` deja la contraseña en el historial del intérprete de
> comandos y avisa de ello. Para no dejar rastro, use `redis-cli -h <IP_VM>`
> y escriba `AUTH <clave>` ya dentro de la sesión.

---

## 3. Migraciones de la base, **en este orden**

El orden no es una preferencia de estilo: cada archivo depende del anterior.

```bash
cd /ruta/al/repo/library

psql -U library_user -d library_db -f data/roles_migration.sql
psql -U library_user -d library_db -f data/pedidos_migration.sql
psql -U library_user -d library_db -f data/pagos_migration.sql
```

1. **`roles_migration.sql` primero.** Crea `library.roles`,
   `library.role_permissions` y la columna `users.role_id`. El JWT lleva
   `role_id` dentro, y todos los servicios resuelven sus permisos contra
   estas tablas: sin ellas, ninguno de los tres siguientes tiene a qué
   apuntar.
2. **`pedidos_migration.sql` después.** Crea `orders`, `order_lines`,
   `order_status_history` y la vista `library.v_orders_detail`.
3. **`pagos_migration.sql` al final.** `payments` tiene una clave foránea
   hacia `orders`, así que no puede ir antes. Y, sobre todo, **vuelve a
   crear `v_orders_detail`** con `CREATE OR REPLACE VIEW` para añadirle la
   columna `paid_amount`: la vista de pedidos no puede informar cuánto se ha
   cobrado hasta que existe la tabla de pagos. Si invirtiera el orden, la
   versión con `paid_amount` quedaría pisada por la de pedidos y los
   listados perderían esa columna.

Las tres migraciones son **idempotentes** (`CREATE TABLE IF NOT EXISTS`,
`CREATE OR REPLACE`, `ADD VALUE IF NOT EXISTS`, bloques `DO $$` que
comprueban antes de crear): puede volver a correrlas sin romper nada, que es
justo lo que uno quiere cuando un despliegue se queda a medias.

Comprobación rápida:

```bash
psql -U library_user -d library_db -c "\dt library.*"
psql -U library_user -d library_db -c "SELECT paid_amount FROM library.v_orders_detail LIMIT 1;"
```

La segunda consulta es la que confirma que `pagos_migration.sql` corrió
**después** de `pedidos_migration.sql`.

---

## 4. El paquete compartido `library_common`

### Por qué es un paquete y no código copiado seis veces

Los seis servicios necesitan exactamente lo mismo: verificar un JWT,
consultar la lista de revocación, hablar con Redis sin colgarse cuando está
caído, resolver permisos por rol, negociar XML/JSON y leer la configuración.
Si eso se copia en seis carpetas, un arreglo de seguridad —por ejemplo,
dejar de aceptar un token con `alg: none`— hay que aplicarlo seis veces, y a
la tercera alguien se olvida de una. Como paquete, se arregla **una** vez y
los seis lo heredan en el siguiente despliegue.

Además, el paquete declara sus propias dependencias (`Flask`, `PyJWT`,
`redis`, `python-dotenv`) en `pyproject.toml`, de modo que instalarlo
arrastra lo que necesita. **Es el paquete, y no el `requirements.txt` de
login o de books, el que instala el cliente `redis` en esos dos servicios.**

### Instalación

```bash
sudo mkdir -p /opt/library/packages
sudo cp -r packages/library_common /opt/library/packages/library_common
sudo chown -R library:library /opt/library/packages
```

Y en el venv de **cada** servicio, los seis:

```bash
for s in login soap users authors pedidos pagos; do
  sudo -u library /opt/library/$s/.venv/bin/pip install -e /opt/library/packages/library_common
done
```

Se instala en modo editable (`-e`) a propósito: al actualizar
`/opt/library/packages/library_common` con un `git pull` + `cp`, basta
reiniciar los servicios; no hay que reinstalar nada en seis venvs.

---

## 5. Los cuatro microservicios nuevos

El procedimiento es idéntico para los cuatro; cambian el nombre y el puerto:

| Servicio | Puerto | Carpeta de origen | Destino |
|---|---|---|---|
| `users` | 5002 | `apps/services/users` | `/opt/library/users` |
| `authors` | 5003 | `apps/services/authors` | `/opt/library/authors` |
| `pedidos` | 5004 | `apps/services/pedidos` | `/opt/library/pedidos` |
| `pagos` | 5005 | `apps/services/pagos` | `/opt/library/pagos` |

### 5.1 Código y entorno virtual

Repítalo con cada nombre de la tabla (aquí, `users`):

```bash
sudo cp -r apps/services/users /opt/library/users
sudo chown -R library:library /opt/library/users

sudo -u library python3 -m venv /opt/library/users/.venv
sudo -u library /opt/library/users/.venv/bin/pip install -r /opt/library/users/requirements.txt
sudo -u library /opt/library/users/.venv/bin/pip install -e /opt/library/packages/library_common
```

### 5.2 Configuración

Lo compartido (JWT, Redis, PostgreSQL, tiempos) vive en el `.env` de la
**raíz** del despliegue; lo propio del servicio, en su `.env`. La
precedencia que aplica `library_common` es
**entorno real > `.env` de la raíz > `.env` del servicio**.

```bash
# El .env compartido, una sola vez:
sudo -u library cp .env.example /opt/library/.env
sudo -u library vi /opt/library/.env    # JWT_SECRET_KEY, SECRET_KEY, REDIS_URL, PGPASSWORD
sudo chmod 600 /opt/library/.env
```

Si cada servicio lleva su propia copia del `.env` compartido —porque
`WorkingDirectory` apunta a su carpeta—, entonces el `JWT_SECRET_KEY` debe
ser **idéntico** en los seis archivos; es el error más fácil de cometer y el
más difícil de diagnosticar (ver §8).

```bash
sudo chmod 600 /opt/library/users/.env
sudo chown library:library /opt/library/users/.env
```

`chmod 600` no es un detalle cosmético: ese archivo tiene la contraseña de
PostgreSQL, la de Redis y la llave con la que se firman **todos** los tokens
del sistema. Con permisos de lectura para todos, cualquier cuenta de la
máquina puede fabricarse un token de administrador.

### 5.3 Unidades de systemd

Siguen el mismo formato que `library-login.service` (README de login, §5.5).
Las cuatro, completas:

```bash
sudo tee /etc/systemd/system/library-users.service > /dev/null <<'EOF'
[Unit]
Description=Libreria en Linea — microservicio de usuarios y roles (Flask)
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
```

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
```

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
```

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
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now library-users library-authors library-pedidos library-pagos
sudo systemctl status library-users library-authors library-pedidos library-pagos
```

Sobre las directivas, que son las mismas de login y por las mismas razones:

* `After=... redis.service` evita que el servicio arranque antes que sus dos
  dependencias. No es garantía (systemd ordena el arranque, no espera a que
  Redis acepte conexiones), pero junto con `Restart=on-failure` basta.
* `User=library` — una cuenta de sistema sin intérprete de comandos
  (`/sbin/nologin`): si alguien consigue ejecución dentro del proceso, no
  tiene con qué moverse.
* `NoNewPrivileges=true` impide que el proceso o sus hijos escalen
  privilegios vía binarios *setuid*.
* `PrivateTmp=true` le da un `/tmp` propio, de modo que no puede leer ni
  pisar los archivos temporales de otros servicios.
* `ProtectSystem=full` monta `/usr`, `/boot` y `/etc` en solo lectura.
* `ProtectHome=true` le oculta `/home`, `/root` y `/run/user`: ningún
  microservicio tiene nada que hacer ahí.
* `gunicorn` **no** lee `PORT` del `.env`; el puerto va en `--bind`.
* `--access-logfile - --error-logfile -` manda los registros a la salida
  estándar, que es lo que systemd recoge en el journal:
  `journalctl -u library-pagos -f`.

---

## 6. Actualizar login y books

Los dos servicios ya existían y no cambian de puerto ni de unidad, pero
ahora dependen de Redis y del paquete compartido.

```bash
cd /ruta/al/repo/library
git pull

# Código nuevo sobre el despliegue (el .env NO está en el repo y se conserva)
sudo cp -r apps/services/login/. /opt/library/login/
sudo cp -r library_soap_service/.  /opt/library/soap/
sudo cp -r packages/library_common/. /opt/library/packages/library_common/
sudo chown -R library:library /opt/library

# Dependencias
sudo -u library /opt/library/login/.venv/bin/pip install -r /opt/library/login/requirements.txt
sudo -u library /opt/library/login/.venv/bin/pip install -e /opt/library/packages/library_common
sudo -u library /opt/library/soap/.venv/bin/pip install -r /opt/library/soap/requirements.txt
sudo -u library /opt/library/soap/.venv/bin/pip install -e /opt/library/packages/library_common

sudo systemctl restart library-login library-soap
```

El `pip install -e` del paquete compartido es el que instala el cliente
`redis` en estos dos venvs: ni `apps/services/login/requirements.txt` ni
`library_soap_service/requirements.txt` lo declaran por su cuenta. No se
salte ese paso o ambos servicios arrancarán y reportarán Redis como caído.

Revise también el `.env` de los dos: debe tener `REDIS_URL` y, si todavía
usa el nombre antiguo `JWT_SECRET`, puede dejarlo (se sigue aceptando) o
renombrarlo a `JWT_SECRET_KEY`. Lo que **no** puede es tener los dos con
valores distintos.

### Aviso: todas las sesiones anteriores dejan de valer

Este es el efecto visible del cambio y conviene anunciarlo antes de
desplegar. Hasta ahora la cookie de Flask **contenía** el estado de la
sesión; ahora la cookie lleva **solo un identificador** (`sid`) y el estado
real vive en Redis. Las cookies emitidas antes del despliegue no traen un
`sid` que exista en Redis, de modo que:

* Toda sesión abierta se invalida en el momento del reinicio.
* **Todos los usuarios tienen que volver a iniciar sesión una vez.** Después
  de eso, el comportamiento es el normal.
* Los clientes de escritorio y Electron que guardasen un token tendrán que
  autenticarse otra vez; el token viejo ya no corresponde a ninguna sesión.

A cambio se gana lo que la cookie no podía dar: cerrar sesión de verdad del
lado del servidor, revocar un token concreto y expirar por inactividad.

---

## 7. Verificación

Los seis `/health` responden XML por omisión; pida JSON para leerlos con
`jq`:

```bash
for p in 5000 5001 5002 5003 5004 5005; do
  echo "--- $p"
  curl -s "http://localhost:$p/health?format=json" | python3 -m json.tool
done
```

En cada respuesta debe aparecer un bloque `redis` así:

```json
"redis": {
    "status": "ok",
    "target": "redis://:***@127.0.0.1:6379/0"
}
```

Dos cosas que mirar: `status` debe decir `ok` —no `not_configured`, que
significa que el servicio no encontró `REDIS_URL`— y `target` debe traer la
contraseña **tapada** con `***`. Esa redacción es deliberada: `/health` es
un extremo que cualquiera puede consultar y jamás debe revelar un secreto.
Compruebe de paso que `"jwt"` dice `"ok"` y no `"missing_secret"`.

### Qué pasa cuando Redis se cae

No todos los servicios reaccionan igual, y la diferencia es intencionada:
cada uno falla de la forma que menos daño hace.

| Servicio | Código | `status` | Por qué |
|---|---|---|---|
| **login** (5000) | `503` | `degraded` | Sin Redis no hay dónde guardar la sesión ni el refresh. `/login`, `/refresh`, `/logout` y `/session` no pueden operar. |
| **pagos** (5005) | `503` | `degraded` | No tiene ni un solo extremo público: todo exige token, y sin Redis no puede comprobar la revocación. No puede hacer nada útil. |
| **users** (5002) | `503` | `degraded` | Igual que pagos: todas sus rutas son administrativas y autenticadas. |
| **books** (5001) | `200` | `degraded` | Las lecturas del catálogo siguen funcionando contra PostgreSQL, solo pierden la caché. |
| **authors** (5003) | `200` | `degraded` | Igual que books: lecturas públicas sí, escrituras no. |
| **pedidos** (5004) | `200` | `degraded` | El rastreo público de envíos sigue; cualquier operación con token devuelve `503`. |

La regla de fondo: **las lecturas públicas sobreviven a la caída de Redis;
las escrituras no.** Una escritura exige verificar que el token no haya sido
revocado, y esa lista vive en Redis. Si no se puede consultar, el servicio
rechaza la operación en lugar de aceptarla a ciegas: fallo seguro, no
permisivo. Por eso un `200` con `"status": "degraded"` no es un servicio
sano, y el bloque `warnings` de la respuesta explica exactamente qué dejó de
funcionar.

Prueba completa de extremo a extremo, con token real:

```bash
TOKEN=$(curl -s -X POST "http://localhost:5000/login?format=json" \
        -H 'Content-Type: application/json' \
        -d '{"email":"<correo_de_una_cuenta>","password":"<clave>"}' \
        | python3 -c 'import json,sys; print(json.load(sys.stdin)["token"])')

curl -s -H "Authorization: Bearer $TOKEN" \
     "http://localhost:5002/users?format=json" | head
```

El token solo viaja en la respuesta **JSON**: el XML publica `tokenType` y
`expiresIn` pero no el token, a propósito, porque un XML acaba con
frecuencia en archivos y registros intermedios. De ahí el `?format=json`.

Si ese token funciona en el 5002, el `JWT_SECRET_KEY` está bien compartido.

---

## 8. Si algo falla

### `NOAUTH Authentication required` / el bloque `redis` dice `error`

Redis tiene `requirepass` y el `REDIS_URL` del `.env` no lleva contraseña, o
lleva otra. Recuerde el formato exacto, con los dos puntos pegados al `//`
porque el campo de usuario va vacío:

```
REDIS_URL=redis://:LA_CONTRASENA@127.0.0.1:6379/0
```

Compruébelo por separado antes de culpar al servicio:

```bash
redis-cli -a '<clave>' ping
sudo grep '^requirepass' /etc/redis/redis.conf
```

El caso inverso también existe: si el `.env` lleva contraseña y
`redis.conf` **no** tiene `requirepass`, Redis responde
`ERR Client sent AUTH, but no password is set`.

### `401` en absolutamente todo, pero login sí emite tokens

El `JWT_SECRET_KEY` no es el mismo en todos los servicios. Es el fallo más
desconcertante de los seis porque login funciona de maravilla —firma con su
secreto— y los demás rechazan cada token sin dar pista alguna.

```bash
# Debe imprimir exactamente el mismo valor seis veces:
for s in login soap users authors pedidos pagos; do
  printf '%-9s ' "$s"
  sudo grep -hE '^JWT_SECRET(_KEY)?=' /opt/library/$s/.env /opt/library/.env 2>/dev/null \
    | head -1 | md5sum
done
```

Se compara el resumen MD5 y no el secreto, para no imprimirlo en pantalla.
Si una línea difiere, corrija ese `.env` y reinicie el servicio. Ojo también
con tener `JWT_SECRET` y `JWT_SECRET_KEY` a la vez con valores distintos:
gana `JWT_SECRET_KEY`, y el otro queda como una trampa para el siguiente que
lea el archivo.

### El servicio no arranca: puerto ocupado

```bash
sudo ss -ltnp | grep -E ':(3000|5000|5001|5002|5003|5004|5005|6379)'
```

En el journal aparece como `[ERROR] Connection in use: ('127.0.0.1', 5003)`
seguido de varios reintentos y `Shutting down: Master`. Suele deberse a un
gunicorn anterior que quedó huérfano o a dos unidades con el mismo `--bind`.
Identifique el PID con la orden de arriba y reinicie la unidad correcta.

### SELinux bloquea la conexión de red

En CentOS, SELinux está en *enforcing* e impide por omisión que un proceso
confinado abra conexiones salientes —incluidas las que van al 6379 o al 5432
de la propia máquina—. El síntoma es un timeout limpio que no aparece en
ningún log de Redis ni de PostgreSQL, como si nadie hubiera llamado.

```bash
# ¿Hay denegaciones recientes?
sudo ausearch -m avc -ts recent

sudo setsebool -P httpd_can_network_connect 1
```

El `-P` hace el cambio permanente (sobrevive al reinicio). Es el mismo
booleano que ya hacía falta para el proxy inverso de nginx hacia los
servicios.

### Permisos del `.env`

```bash
sudo chmod 600 /opt/library/.env /opt/library/*/.env
sudo chown library:library /opt/library/.env /opt/library/*/.env
ls -l /opt/library/*/.env        # debe verse -rw------- library library
```

Si el archivo quedó legible para todos, no basta con corregir los permisos:
el secreto estuvo expuesto. Regenere `JWT_SECRET_KEY`, cámbielo en los seis
servicios y reinícielos —lo que, igual que en §6, obliga a todos los
usuarios a iniciar sesión otra vez.

### Otros sitios donde mirar

```bash
journalctl -u library-pagos -n 100 --no-pager
journalctl -u redis -n 50 --no-pager
sudo systemctl status library-users library-authors library-pedidos library-pagos
```

Cada servicio registra al arrancar su URL de Redis **con la contraseña
tapada** (`redis://:***@127.0.0.1:6379/0`) o la cadena `SIN CONFIGURAR`, que
es la forma más rápida de ver si encontró el `.env` de la raíz.
