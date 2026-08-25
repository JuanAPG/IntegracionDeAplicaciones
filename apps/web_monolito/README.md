# Libreria en Linea — Aplicacion Web Monolitica

Sistema web para la gestion de una libreria en linea. Un unico proceso Node.js
renderiza HTML en el servidor y accede **directamente a PostgreSQL**.

## 1. Caracteristicas y restricciones de arquitectura

| Requisito | Implementacion |
|---|---|
| Macro-arquitectura monolitica | Un solo proceso Node.js (`server.js`) sirve vistas y datos |
| Patron MVC para la UI | `*.model.js` (datos) / `*.controller.js` (logica) / `views/*.ejs` (presentacion) |
| Organizacion por modulos | `src/modules/<modulo>/` con su modelo, controlador, rutas y vistas |
| HTML renderizado en el servidor | Plantillas EJS; el navegador solo recibe HTML y CSS |
| Sin APIs REST / GraphQL / SOAP | Solo rutas de formularios HTML (`GET` para mostrar, `POST` para enviar) |
| Sin JSON ni XML como intercambio | `express.json()` **no** esta habilitado; no existe ningun `res.json()`. La entrada es `application/x-www-form-urlencoded` y `multipart/form-data` (solo para archivos de imagen) |
| Acceso directo a PostgreSQL | Driver `pg` con SQL parametrizado, sin ORM |
| Usuarios registrados | Registro, inicio/cierre de sesion, perfil y contrasenas cifradas con bcrypt |
| Maximo un administrador | Indice unico parcial `ux_users_single_admin` en la BD + validaciones en la aplicacion |
| CRUD del modelo normalizado | Todas las tablas: `users`, `books`, `authors`, `genres`, `concepts`, `formats`, `categories`, `book_authors`, `book_genres`, `book_concepts`, `book_images` |
| Manejo de imagenes | Carga por formulario, almacenamiento en disco, ruta persistida en `book_images`, portada unica por libro |
| Conceptos por libro | `book_concepts` guarda la definicion propia de cada par (libro, concepto) |
| Interfaz | Sistema de diseño propio en una sola hoja de estilos (tema oscuro, glassmorphism) y hero 3D de Spline. Sin React, TypeScript, Tailwind ni paso de compilacion. Detalle en [`docs/UI.md`](docs/UI.md) |

`package.json` existe unicamente porque npm lo requiere para administrar el
proyecto Node.js; no se usa JSON como formato de intercambio de datos.

## 2. Modelo de datos

Dependencias funcionales:

```
ISBN        -> titulo, ano_publicacion, precio, stock, formato, categoria
autor_id    -> nombre_autor
genero_id   -> nombre_genero
concepto_id -> nombre_concepto
(libro_id, concepto_id) -> definicion
usuario_id  -> nombre, email, password_hash, rol
```

Dependencias multivaluadas (resueltas en 4FN con tablas propias):

```
libro ->> autor                    book_authors
libro ->> genero                   book_genres
libro ->> imagen                   book_images
libro ->> (concepto, definicion)   book_concepts
```

`formats` y `categories` son catalogos independientes (1:N hacia `books`).
El esquema completo esta en `data/schema.sql` (raiz del proyecto).

## 3. Estructura del codigo

```
apps/web_monolito/
├── server.js                  Punto de entrada del monolito
├── db/seed.sql                Datos de demostracion (idempotente)
├── scripts/setup-db.js        Instalador: esquema + datos + administrador
└── src/
    ├── app.js                 Composicion de Express (vistas, sesion, rutas)
    ├── config/                env.js (configuracion) y database.js (pool pg)
    ├── core/
    │   ├── crud/              Fabricas MVC reutilizadas por los catalogos
    │   ├── middlewares/       auth, flash, locals, upload, errors
    │   └── utils/             validacion, contrasenas, errores HTTP
    ├── modules/               Un directorio por modulo del dominio
    │   ├── auth/              Registro, sesion y perfil
    │   ├── catalog/           Catalogo para usuarios registrados
    │   ├── books/             CRUD de libros, conceptos e imagenes
    │   ├── authors/  genres/  concepts/  formats/  categories/
    │   ├── users/             CRUD de usuarios y panel de administracion
    │   └── index.js           Router que compone todos los modulos
    ├── views/                 layout, parciales y vistas compartidas
    └── public/
        ├── css/styles.css     Sistema de diseño unico (tokens + componentes)
        ├── js/                Mejoras progresivas: menu movil, hero 3D, spotlight
        └── uploads/           Imagenes cargadas por el administrador
```

La carpeta `docs/` documenta el sistema de diseño y el port a JavaScript plano
de los componentes de React usados como referencia.

## 4. Mapa de rutas (todas devuelven HTML)

| Ruta | Metodo | Acceso | Descripcion |
|---|---|---|---|
| `/` | GET | publico | Pagina de bienvenida |
| `/auth/register` | GET, POST | invitado | Alta de usuario (rol `user`) |
| `/auth/login` | GET, POST | invitado | Inicio de sesion |
| `/auth/logout` | POST | sesion | Cierre de sesion |
| `/auth/profile` | GET, POST | sesion | Datos personales y cambio de contrasena |
| `/catalog` | GET | registrado | Catalogo con busqueda y filtros |
| `/catalog/:id` | GET | registrado | Ficha del libro, imagenes y conceptos |
| `/admin` | GET | admin | Panel con el resumen del modelo |
| `/admin/books` | GET, POST | admin | Listado y alta de libros |
| `/admin/books/:id/edit` | GET | admin | Edicion con autores, generos, conceptos e imagenes |
| `/admin/books/:id/concepts[...]` | POST | admin | Alta, edicion y baja de definiciones por libro |
| `/admin/books/:id/images[...]` | POST | admin | Carga, portada y baja de imagenes |
| `/admin/authors`, `/admin/genres`, `/admin/concepts`, `/admin/formats`, `/admin/categories` | GET, POST | admin | CRUD de catalogos |
| `/admin/users` | GET, POST | admin | CRUD de usuarios registrados |

---

# 5. Interfaz de usuario

La capa View sigue siendo EJS renderizado en el servidor. El aspecto visual lo
define una unica hoja de estilos, `src/public/css/styles.css`, organizada como
sistema de diseño con variables CSS.

- **Tema oscuro** con superficies de vidrio (`backdrop-filter`), primario
  violeta `#7C3AED` e indigo `#6366F1`, tipografia `Outfit` + `Inter`.
- **Portada con hero 3D**: una escena de Spline en un `<canvas>`, con un foco
  radial que sigue al cursor.
- **Sin framework de interfaz**: no hay React, TypeScript, Tailwind, shadcn/ui
  ni bundler. Los tres componentes de React tomados como referencia
  (`SplineScene`, `Spotlight` y `Card`) estan portados a JavaScript plano y CSS.
- **Unica dependencia nueva**: `@splinetool/runtime`, servido como ESM nativo
  desde `node_modules` en la ruta estatica `/vendor/spline`.
- **Degradacion elegante**: sin WebGL, con `prefers-reduced-motion` o si la
  escena falla, se muestra un orbe estatico. La aplicacion es utilizable sin
  JavaScript, porque todo el HTML llega renderizado y cada accion es un
  formulario.
- **Accesibilidad**: contraste AA, foco visible, objetivos tactiles de 44 px,
  enlace de salto al contenido e iconos SVG en linea.

El detalle completo —tokens, mapeo componente a componente y decisiones de
arquitectura— esta en [`docs/UI.md`](docs/UI.md).

## Vista previa sin base de datos

Para revisar las 19 pantallas con datos de prueba, sin PostgreSQL:

```bash
npm start
# http://localhost:3000/__preview__/
```

Esa carpeta se genera aparte, esta excluida de git y puede borrarse con
`rm -rf src/public/__preview__`.

---

# 6. Despliegue en CentOS 10 Stream

Se asume que **PostgreSQL ya esta instalado y en ejecucion**, con:

- usuario: `library_user`
- contrasena: `777`
- base de datos: `library_db`

Todos los comandos se ejecutan como un usuario con `sudo`.

## 6.1 Instalar Node.js

```bash
sudo dnf -y update
sudo dnf -y install nodejs npm git
node -v      # debe ser 18 o superior
npm -v
```

Si el repositorio AppStream ofreciera una version menor a 18:

```bash
curl -fsSL https://rpm.nodesource.com/setup_22.x | sudo bash -
sudo dnf -y install nodejs
```

## 6.2 Verificar el acceso a PostgreSQL

```bash
sudo dnf -y install postgresql          # solo el cliente psql, si falta
psql "postgresql://library_user:777@localhost:5432/library_db" -c "SELECT version();"
```

Si la conexion es rechazada por autenticacion, habilite contrasenas en
`/var/lib/pgsql/data/pg_hba.conf` para las conexiones locales:

```
# TYPE  DATABASE     USER           ADDRESS         METHOD
local   library_db   library_user                   scram-sha-256
host    library_db   library_user   127.0.0.1/32    scram-sha-256
host    library_db   library_user   ::1/128         scram-sha-256
```

y recargue el servicio:

```bash
sudo systemctl reload postgresql
```

El usuario necesita poder crear el esquema `library` dentro de su base de datos:

```bash
sudo -u postgres psql -d library_db -c "GRANT ALL ON DATABASE library_db TO library_user;"
sudo -u postgres psql -d library_db -c "GRANT ALL ON SCHEMA public TO library_user;"
sudo -u postgres psql -d library_db -c "CREATE EXTENSION IF NOT EXISTS pgcrypto;"
```

> `pgcrypto` requiere privilegios de superusuario, por eso se crea con el
> usuario `postgres`. El paquete `postgresql-contrib` debe estar instalado.

## 6.3 Crear el usuario de servicio y copiar la aplicacion

```bash
sudo useradd --system --create-home --home-dir /opt/library --shell /sbin/nologin library
sudo mkdir -p /opt/library/app
# Copie el proyecto (carpetas apps/ y data/) al servidor, por ejemplo con scp o git clone
sudo cp -r /ruta/al/proyecto/library/* /opt/library/app/
sudo chown -R library:library /opt/library
```

Estructura esperada en el servidor:

```
/opt/library/app/
├── data/schema.sql
└── apps/web_monolito/
```

## 6.4 Instalar dependencias

```bash
cd /opt/library/app/apps/web_monolito
sudo -u library npm ci --omit=dev      # o: sudo -u library npm install --omit=dev
```

## 6.5 Configurar el entorno

```bash
sudo -u library cp .env.example .env
sudo -u library vi .env
```

Contenido minimo de `.env`:

```ini
PORT=3000
NODE_ENV=production

PGHOST=localhost
PGPORT=5432
PGDATABASE=library_db
PGUSER=library_user
PGPASSWORD=777
PGSCHEMA=library

SESSION_SECRET=coloque-aqui-una-cadena-larga-y-aleatoria

ADMIN_NAME=Administrador
ADMIN_EMAIL=admin@library.local
ADMIN_PASSWORD=Admin123!

UPLOAD_MAX_MB=5
```

Genere un secreto de sesion robusto:

```bash
openssl rand -hex 32
```

Proteja el archivo, porque contiene la contrasena de la base de datos:

```bash
sudo chmod 600 /opt/library/app/apps/web_monolito/.env
sudo chown library:library /opt/library/app/apps/web_monolito/.env
```

## 6.6 Crear el esquema y el administrador

```bash
cd /opt/library/app/apps/web_monolito
sudo -u library npm run db:setup
```

El script:

1. aplica `data/schema.sql` si el esquema `library` todavia no existe;
2. carga los datos de demostracion de `db/seed.sql`;
3. crea el **unico** administrador con la contrasena cifrada con bcrypt.

Variantes:

```bash
sudo -u library node scripts/setup-db.js --reset       # borra y recrea el esquema
sudo -u library node scripts/setup-db.js --no-demo     # sin datos de demostracion
sudo -u library node scripts/setup-db.js --seed-only   # solo datos + administrador
```

Alternativa manual con `psql`:

```bash
psql "postgresql://library_user:777@localhost:5432/library_db" -f /opt/library/app/data/schema.sql
psql "postgresql://library_user:777@localhost:5432/library_db" -f /opt/library/app/apps/web_monolito/db/seed.sql
# El administrador debe crearse con el script, para que la contrasena quede cifrada:
sudo -u library node scripts/setup-db.js --seed-only
```

## 6.7 Permisos del directorio de imagenes

Las imagenes cargadas se guardan en `src/public/uploads`:

```bash
sudo mkdir -p /opt/library/app/apps/web_monolito/src/public/uploads
sudo chown -R library:library /opt/library/app/apps/web_monolito/src/public/uploads
sudo chmod 750 /opt/library/app/apps/web_monolito/src/public/uploads
```

## 6.8 Servicio systemd

```bash
sudo tee /etc/systemd/system/library.service > /dev/null <<'EOF'
[Unit]
Description=Libreria en Linea (monolito Node.js)
After=network-online.target postgresql.service
Wants=network-online.target
Requires=postgresql.service

[Service]
Type=simple
User=library
Group=library
WorkingDirectory=/opt/library/app/apps/web_monolito
EnvironmentFile=/opt/library/app/apps/web_monolito/.env
ExecStart=/usr/bin/node server.js
Restart=on-failure
RestartSec=5
StandardOutput=journal
StandardError=journal
SyslogIdentifier=library

# Endurecimiento
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=full
ProtectHome=true
ReadWritePaths=/opt/library/app/apps/web_monolito/src/public/uploads

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable --now library.service
sudo systemctl status library.service
```

Ver los registros:

```bash
sudo journalctl -u library.service -f
```

## 6.9 Firewall (firewalld)

Acceso directo al puerto 3000:

```bash
sudo firewall-cmd --permanent --add-port=3000/tcp
sudo firewall-cmd --reload
```

## 6.10 Nginx como proxy inverso (recomendado)

```bash
sudo dnf -y install nginx
sudo setsebool -P httpd_can_network_connect 1     # SELinux: permite el proxy

sudo tee /etc/nginx/conf.d/library.conf > /dev/null <<'EOF'
server {
    listen 80;
    server_name _;

    client_max_body_size 10M;   # debe ser mayor que UPLOAD_MAX_MB

    location / {
        proxy_pass http://127.0.0.1:3000;
        proxy_http_version 1.1;
        proxy_set_header Host              $host;
        proxy_set_header X-Real-IP         $remote_addr;
        proxy_set_header X-Forwarded-For   $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
EOF

sudo nginx -t
sudo systemctl enable --now nginx
sudo firewall-cmd --permanent --add-service=http
sudo firewall-cmd --reload
```

## 6.11 Verificacion

```bash
curl -I http://localhost:3000/            # HTTP/1.1 200 OK
curl -s http://localhost:3000/ | head     # HTML renderizado en el servidor
```

Desde el navegador: `http://<ip-del-servidor>/`

1. Inicie sesion con `ADMIN_EMAIL` / `ADMIN_PASSWORD`.
2. Cambie de inmediato la contrasena en **Mi perfil**.
3. Cree libros, autores, generos, conceptos, formatos y categorias.
4. Cargue imagenes y defina conceptos desde la ficha de cada libro.

---

# 7. Operacion

## Actualizar la aplicacion

```bash
sudo systemctl stop library
sudo -u library cp -r /ruta/nueva/version/* /opt/library/app/
cd /opt/library/app/apps/web_monolito
sudo -u library npm ci --omit=dev
sudo systemctl start library
```

## Respaldo y restauracion

```bash
# Respaldo de la base de datos
pg_dump "postgresql://library_user:777@localhost:5432/library_db" -Fc -f /var/backups/library_$(date +%F).dump

# Respaldo de las imagenes cargadas
sudo tar czf /var/backups/library_uploads_$(date +%F).tar.gz \
  -C /opt/library/app/apps/web_monolito/src/public uploads

# Restauracion
pg_restore -d "postgresql://library_user:777@localhost:5432/library_db" --clean /var/backups/library_YYYY-MM-DD.dump
```

## Sesiones

Las sesiones se guardan en la memoria del proceso. Al reiniciar el servicio
(`systemctl restart library`) los usuarios deben iniciar sesion nuevamente;
los datos de la aplicacion no se ven afectados porque residen en PostgreSQL.

## Problemas frecuentes

| Sintoma | Causa probable | Solucion |
|---|---|---|
| "No fue posible conectar con PostgreSQL" | Servicio detenido o credenciales incorrectas | `sudo systemctl status postgresql`; revise `.env` y `pg_hba.conf` |
| `permission denied to create extension` | `pgcrypto` requiere superusuario | `sudo -u postgres psql -d library_db -c "CREATE EXTENSION IF NOT EXISTS pgcrypto;"` |
| `permission denied for database library_db` | Falta el permiso de creacion | `GRANT ALL ON DATABASE library_db TO library_user;` |
| "Ya existe un administrador" | Regla de negocio: solo se admite uno | Edite el administrador existente en `/admin/users` |
| Las imagenes no se guardan | Permisos de `src/public/uploads` | `chown -R library:library` y `ReadWritePaths` en el servicio |
| Error 413 al cargar imagenes | Limite de Nginx | Aumente `client_max_body_size` |
| El servicio no arranca | Puerto ocupado o `.env` ilegible | `sudo journalctl -u library -n 50` |

## Seguridad

- Cambie `ADMIN_PASSWORD` y `SESSION_SECRET` antes de exponer el servidor.
- Cambie la contrasena de PostgreSQL: `777` solo es adecuada para practicas.
- Publique el sitio detras de Nginx con TLS (`certbot`) si sale a Internet.
- Las contrasenas se almacenan con bcrypt; el SQL usa siempre consultas
  parametrizadas para evitar inyeccion.

---

# 8. Ejecucion en un entorno de desarrollo

```bash
cd apps/web_monolito
npm install
cp .env.example .env          # ajuste PGUSER, PGPASSWORD, PGDATABASE
npm run db:setup              # esquema + datos de demostracion + administrador
npm run dev                   # http://localhost:3000
```

Credenciales iniciales: las que indique `.env` (por omision
`admin@library.local` / `Admin123!`).
