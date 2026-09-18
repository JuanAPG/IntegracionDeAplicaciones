# Microservicio de autenticación — Flask + Psycopg 3 + PostgreSQL

Servicio independiente de autenticación y gestión básica de usuarios para
`library_db` (esquema `library`). Expone sus respuestas en **XML** y **JSON**;
sin `?format=`, **XML** es el formato predeterminado.

Se documenta solo: **Swagger UI en `/docs`**, especificación OpenAPI 3.0.3 en
`/openapi.json`.

---

## 1. Qué hace

| Operación | Endpoint |
|---|---|
| Registrar usuario | `POST /register` |
| Verificar correo (token del sendmail) | `GET /verify?token=…` · `POST /verify` |
| Validación previa del correo | `GET /validate-email?email=…` |
| Autenticar e iniciar sesión | `POST /login` |
| Cerrar la sesión | `POST /logout` |
| Consultar la sesión | `GET /session` |
| Estado | `GET /health` |
| Documentación | `GET /docs` — `GET /openapi.json` |

El registro pide `nombre`, `apellidoPaterno`, `apellidoMaterno` (opcional),
`email` y `password`. En la base los nombres viven normalizados
(`first_name`, `last_name_paternal`, `last_name_maternal`); `full_name` se
mantiene sincronizado por disparador para no romper el monolito.
`password_hash` vive **solo** en `users`: no hay tabla de contraseñas.

El correo se **valida antes de registrarse** (sintaxis + unicidad) y su
**propiedad** se verifica con un token enviado por el **sendmail alojado en
la instancia** (SMTP local, sin POP/IMAP). El registro interno
`verified_emails` recuerda los correos ya verificados previamente.

---

## 2. Formatos

```
POST /register                  -> XML (por omisión)
POST /register?format=xml       -> XML
POST /register?format=json      -> JSON
```

Ejemplo de alta (JSON):

```bash
curl -X POST http://localhost:5000/register?format=json \
  -H "Content-Type: application/json" -d '{
    "nombre": "Ada",
    "apellidoPaterno": "Lovelace",
    "apellidoMaterno": "Byron",
    "email": "ada@ejemplo.mx",
    "password": "Secreto123"
  }'
```

El mismo alta con cuerpo XML:

```bash
curl -X POST "http://localhost:5000/register?format=xml" \
  -H "Content-Type: application/xml" --data-binary '
<register>
  <nombre>Ada</nombre>
  <apellidoPaterno>Lovelace</apellidoPaterno>
  <apellidoMaterno>Byron</apellidoMaterno>
  <email>ada@ejemplo.mx</email>
  <password>Secreto123</password>
</register>'
```

La sesión viaja en cookie firmada de Flask: conserve cookies entre
peticiones (`curl -c jar -b jar`).

```bash
curl -c jar -b jar -X POST http://localhost:5000/login?format=json \
  -H "Content-Type: application/json" \
  -d '{"email": "ada@ejemplo.mx", "password": "Secreto123"}'
curl -b jar http://localhost:5000/session?format=json
curl -b jar -X POST http://localhost:5000/logout?format=json
```

---

## 3. Restricciones de la práctica

* **Flask sin blueprints.** Todas las rutas se registran con `@app.get` /
  `@app.post` sobre la única instancia `app` de `login/app.py`.
* **Psycopg 3** (`psycopg[binary]` + `psycopg_pool`), consultas
  parametrizadas, una sola transacción por escritura.
* **Sin credenciales en el código.** Todo sale de variables de entorno; el
  archivo `.env` está en `.gitignore` y nunca se publica.
* **CORS habilitado** con credenciales (la sesión usa cookie): en producción
  `CORS_ORIGINS` debe enumerar los dominios, `*` no combina con cookies.
* **bcrypt** para `password_hash`, compatible con los hashes bcryptjs que ya
  guarda el monolito. Mínimo 6 caracteres.

---

## 4. Estructura

```
apps/services/login/
├── login/
│   ├── app.py                  rutas Flask, CORS, sesiones, negociación, errores
│   ├── config.py               lectura del .env
│   ├── db.py                   pool Psycopg 3 y transacciones
│   ├── users_repository.py     todo el SQL (cuentas, tokens, verificados)
│   ├── validators.py           validación previa de campos y correo
│   ├── security.py             hash/verificación bcrypt
│   ├── tokens.py               emisión y hash de tokens de verificación
│   ├── mailer.py               entrega al sendmail local (smtplib)
│   ├── serializers.py          salida JSON y salida XML (ElementTree)
│   ├── openapi.py              especificación OpenAPI 3.0.3 escrita a mano
│   ├── errors.py               excepciones y su traducción a códigos HTTP
│   └── wsgi.py                 punto de entrada para gunicorn
├── scripts/pruebas.sh          batería de humo con curl (+ psql en la VM)
├── test/test_login_mocked.py   pruebas sin PostgreSQL (repositorio simulado)
├── requirements.txt
├── .env.example                plantilla (se publica)
└── .env                        credenciales reales (NO se publica)
```

La migración vive junto al esquema inicial, una por archivo:

```
data/login_migration.sql     nombres normalizados + verificación (este servicio)
```

---

## 5. Puesta en marcha en la instancia CentOS 10 Stream

Se asume PostgreSQL ya instalado con `library_user` / `library_db` y el
sendmail (postfix/sendmail) escuchando en `localhost:25`.

### 5.1 Migración de la base (primero, desde la raíz del repo)

```bash
psql -U library_user -d library_db -f data/login_migration.sql
```

Crea las columnas de nombre normalizado, el disparador que sincroniza
`full_name`, `email_verification_tokens` y `verified_emails`. Las cuentas
existentes (admin, seed) quedan marcadas como verificadas por el proceso
confiable que las creó, para no bloquear al administrador.

### 5.2 Python y el código

```bash
sudo dnf install -y python3 python3-pip
sudo useradd --system --home-dir /opt/library --shell /sbin/nologin library || true

sudo mkdir -p /opt/library
sudo cp -r apps/services/login /opt/library/login
sudo chown -R library:library /opt/library

sudo -u library python3 -m venv /opt/library/login/.venv
sudo -u library /opt/library/login/.venv/bin/pip install -r /opt/library/login/requirements.txt
```

### 5.3 Configuración

```bash
sudo -u library cp /opt/library/login/.env.example /opt/library/login/.env
sudo -u library vi /opt/library/login/.env   # PGPASSWORD, SECRET_KEY, SMTP_FROM, CORS_ORIGINS
sudo chmod 600 /opt/library/login/.env
```

Genere el secreto con `python3 -c "import secrets; print(secrets.token_hex(48))"`.

### 5.4 Sendmail local

```bash
sudo dnf install -y postfix
sudo systemctl enable --now postfix
sudo ss -ltn | grep :25        # debe escuchar en 127.0.0.1:25
```

El servicio **entrega** correo por SMTP local; nunca lee buzones (nada de
POP/IMAP).

### 5.5 Servicio systemd

```bash
sudo tee /etc/systemd/system/library-login.service > /dev/null <<'EOF'
[Unit]
Description=Libreria en Linea — microservicio de autenticacion (Flask)
After=network-online.target postgresql.service postfix.service
Wants=network-online.target

[Service]
Type=simple
User=library
Group=library
WorkingDirectory=/opt/library/login/login
ExecStart=/opt/library/login/.venv/bin/gunicorn \
          --workers 3 --bind 127.0.0.1:5000 \
          --access-logfile - --error-logfile - wsgi:application
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
sudo systemctl enable --now library-login
sudo systemctl status library-login
```

### 5.6 Proxy inverso y firewall

Con **nginx**:

```nginx
location /login/ {
    proxy_pass http://127.0.0.1:5000/;
    proxy_set_header Host              $host;
    proxy_set_header X-Real-IP         $remote_addr;
    proxy_set_header X-Forwarded-For   $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
}
```

`gunicorn` no lee `PORT` del `.env`: el puerto va en `--bind`.
**No añada cabeceras CORS en el proxy** (ya las emite Flask) y recuerde
`sudo setsebool -P httpd_can_network_connect 1` con SELinux.

```bash
sudo firewall-cmd --permanent --add-service=http --add-service=https
sudo firewall-cmd --permanent --add-port=5000/tcp   # solo si necesita acceso directo
sudo firewall-cmd --reload
```

### 5.7 Verificación

```bash
curl -s http://localhost:5000/health
BASE=http://localhost:5000 ./scripts/pruebas.sh
```

`pruebas.sh` deja la base como la encontró: el usuario de prueba lo borra
al final. El canje real del token se valida con el correo que llega por
sendmail; la batería cubre el resto del flujo y los dos formatos.

---

## 6. Pruebas sin PostgreSQL (esta máquina)

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m pytest test/ -q 2>/dev/null || python test/test_login_mocked.py
```

`test/test_login_mocked.py` simula el repositorio y el sendmail, y recorre
registro, verificación, login, sesión, logout y ambos formatos.

---

## 7. Códigos de error

| Código | Cuándo |
|---|---|
| `400` | Campos inválidos, token ausente, XML/JSON mal formado |
| `401` | Credenciales inválidas o cuenta desactivada |
| `403` | Correo sin verificar (`email_not_verified`) |
| `404` | Token de verificación inexistente |
| `409` | Correo ya registrado |
| `410` | Token usado o expirado |
| `503` | PostgreSQL o sendmail no disponibles |

---

## 8. Seguridad

* El `.env` **no se publica** (`apps/services/login/.gitignore`).
* Solo se guarda el **hash bcrypt**; el token en claro solo viaja en el
  correo y en la base vive su SHA-256, de un solo uso y con expiración.
* Todo el SQL usa parámetros (`%s`); no hay concatenación de valores del
  usuario en las consultas.
* `DEBUG=false` en el servidor: con `true`, los errores 500 devuelven el
  detalle al cliente.
