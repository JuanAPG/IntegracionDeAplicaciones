# Microservicio de libros — Flask + PostgreSQL

Servicio de datos que expone las operaciones **CRUD** sobre los libros de
`library_db` (esquema `library`). Habla dos formatos de intercambio, **JSON**
y **XML**; el XML reproduce el diseno de
[`../apps/services/soap/library.xml`](../apps/services/soap/library.xml).

Se documenta solo: **Swagger UI en `/docs`**, especificacion OpenAPI 3.0.3 en
`/openapi.json`.

---

## 1. Que hace

| Operacion | Endpoint |
|---|---|
| Todos los libros | `GET /books` |
| Un libro | `GET /books/{id}` — `GET /books/isbn/{isbn}` |
| Buscar por atributos | `GET /books/search?...` |
| Dar de alta | `POST /books` |
| Modificar (reemplazo completo) | `PUT /books/{id}` |
| Actualizar (cambio parcial) | `PATCH /books/{id}` |
| Borrar | `DELETE /books/{id}` |
| Catalogos | `GET /{formats\|categories\|genres\|authors\|concepts}` |
| Conceptos Cloud + su libro | `GET /cloud-concepts` |
| Estado | `GET /health` |
| Documentacion | `GET /docs` — `GET /openapi.json` |

Un **libro** es el agregado completo: sus dependencias funcionales
(`ISBN -> titulo, ano, precio, stock, formato, categoria`) son campos simples y
sus dependencias multivaluadas (`libro ->> autor`, `libro ->> genero`,
`libro ->> imagen`, `libro ->> (concepto, definicion)`) son colecciones. La
definicion pertenece al **par** libro-concepto: el mismo concepto se define de
otra forma en otro libro.

---

## 2. Restricciones de la practica

* **Flask sin blueprints.** Todas las rutas se registran con `@app.get`,
  `@app.post`, … sobre la unica instancia `app` de `app.py`. (Swagger UI la
  publica Flasgger, que internamente registra la suya; no hay ningun blueprint
  escrito en este proyecto.)
* **Sin credenciales en el codigo.** Todo sale de variables de entorno; el
  archivo `.env` esta en `.gitignore` y nunca se publica.
* **CORS habilitado.** El servicio se consume desde clientes de otro dominio.

---

## 3. Estructura

```
library_soap_service/
├── soap/
│   ├── app.py                 rutas Flask, CORS, negociacion de contenido, errores
│   ├── config.py              lectura del .env
│   ├── db.py                  pool de conexiones y transacciones
│   ├── books_repository.py    todo el SQL (lectura, filtros, escritura)
│   ├── payloads.py            lectura y validacion del cuerpo (JSON y XML)
│   ├── serializers.py         salida JSON y salida XML con el diseno de library.xml
│   ├── openapi.py             especificacion OpenAPI 3.0.3 escrita a mano
│   ├── errors.py              excepciones y su traduccion a codigos HTTP
│   └── wsgi.py                punto de entrada para gunicorn
├── requirements.txt
├── .env.example                plantilla (se publica)
├── .env                         credenciales reales (NO se publica)
└── scripts/pruebas.sh          bateria de humo con curl
```

---

## 4. Puesta en marcha (desarrollo)

Requisitos: Python 3.9 o superior y un PostgreSQL con la base cargada
(`db/00_create_database.sql` … `db/02_seed_30_per_table.sql`, o bien
`data/schema.sql` + `data/seed.sql`).

```bash
cd library_soap_service
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env        # y escriba la contrasena real en PGPASSWORD
python soap/app.py
```

```
http://localhost:5001/docs             Swagger UI
http://localhost:5001/books        catalogo completo
http://localhost:5001/health           estado de la conexion con PostgreSQL
```

Si `/health` responde `503`, el mensaje dice exactamente que fallo y contra
que servidor se intento conectar.

### Variables de entorno

| Variable | Por omision | Para que sirve |
|---|---|---|
| `HOST` / `PORT` | `0.0.0.0` / `5001` | Interfaz y puerto de escucha |
| `DEBUG` | `false` | Recarga automatica y traza en los errores 500 |
| `API_PREFIX` | *(vacio)* | Prefijo de los endpoints de datos. Vacio = cuelgan de la raiz; `/api` los agrupa bajo `/api/books` |
| `PGHOST` `PGPORT` `PGDATABASE` `PGUSER` `PGPASSWORD` | `localhost` `5432` `library_db` `library_user` — | Conexion |
| `PGSCHEMA` | `library` | Se fija en el `search_path` de cada conexion |
| `DB_POOL_MIN` / `DB_POOL_MAX` | `1` / `10` | Tamano del pool |
| `CORS_ORIGINS` | `*` | Origenes permitidos, separados por comas |
| `DEFAULT_FORMAT` | `xml` | Formato cuando el cliente no pide ninguno |
| `CURRENCY` | `MXN` | Atributo `currency` de `<price>` |
| `DEFAULT_LIMIT` / `MAX_LIMIT` | `50` / `200` | Paginacion |

La contrasena que fija el enunciado (`777`) vale para el entorno local. En un
servidor expuesto, cambiela por una larga y aleatoria: es la unica credencial
que protege la base.

---

## 5. JSON o XML

El mismo recurso se entrega en los dos formatos. Prioridad:

1. `?output=xml` o `?output=json`
2. cabecera `Accept: application/xml` / `application/json`
3. `DEFAULT_FORMAT` del `.env` — **`xml`**: si el cliente no pide nada,
   la respuesta va en XML.

`?format=xml` tambien funciona, pero **`format` es ademas un filtro de
busqueda** (el catalogo de formatos: Fisico, Digital, Audiolibro, Pasta dura).
Solo se lee como representacion cuando su valor es `xml` o `json`; con
cualquier otro valor filtra libros. Use `output` y no hay ambiguedad.

```bash
curl "http://localhost:5001/books/1"                       # XML (por omision)
curl "http://localhost:5001/books/1?output=json"           # JSON
curl -H "Accept: application/json" "http://localhost:5001/books/1"
curl "http://localhost:5001/books?format=Digital"          # filtro, responde XML
curl "http://localhost:5001/books?format=Digital&output=json"
```

El XML de un libro sale exactamente con el diseno de `library.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<book id="1" isbn="978-0133970777" xmlns="urn:library:catalog:1.0">
  <title>Fundamentos de Sistemas de Bases de Datos</title>
  <publicationYear>2016</publicationYear>
  <price currency="MXN">1250.00</price>
  <stock>12</stock>
  <format ref="4">Pasta dura</format>
  <category ref="5">Academico</category>
  <authors count="2">
    <author ref="1">Ramez Elmasri</author>
    <author ref="2">Shamkant Navathe</author>
  </authors>
  <genres count="2">
    <genre ref="1">Bases de datos</genre>
    <genre ref="2">Ingenieria de software</genre>
  </genres>
  <concepts count="1">
    <concept ref="1">
      <name>Normalizacion</name>
      <definition>Proceso de descomposicion de relaciones...</definition>
    </concept>
  </concepts>
  <images count="1">
    <image id="1" isCover="true">https://covers.openlibrary.org/b/isbn/9780133970777-L.jpg</image>
  </images>
</book>
```

El listado va envuelto en `<library><books count total limit offset>`, igual
que el archivo de origen.

---

## 6. Busqueda por atributos

Todos los filtros se combinan con AND. Los de texto son parciales y no
distinguen mayusculas (`ILIKE`).

| Parametro | Busca en |
|---|---|
| `q` | titulo, ISBN o nombre de autor |
| `title` `isbn` | columnas del libro |
| `author` `genre` `concept` | cruzando las tablas de relacion |
| `category` `format` | por id o por nombre |
| `year` `year_min` `year_max` | ano de publicacion |
| `price_min` `price_max` | precio |
| `stock_min` `stock_max` `in_stock` | existencias |
| `sort` `order` `limit` `offset` | orden y paginacion |

```bash
curl "http://localhost:5001/books/search?author=asimov"
curl "http://localhost:5001/books/search?genre=novela&price_max=400&sort=price&order=desc"
curl "http://localhost:5001/books/search?concept=SOLID"
curl "http://localhost:5001/books/search?category=Academico&in_stock=true"
curl "http://localhost:5001/books/search?q=clean&output=xml"
```

La respuesta trae `total` (libros que cumplen el filtro) y la cabecera
`X-Total-Count` con el mismo valor.

---

## 7. Escritura

`format` y `category` admiten el id (`4`) o el nombre (`"Pasta dura"`) y deben
existir en el catalogo: si no, la respuesta es `400` con la lista de valores
validos. `authors`, `genres` y `concepts` admiten `["Nombre"]`,
`[{"name": "..."}]` o `[{"ref": 3}]`; **si el nombre no existe, se da de alta**.

**Alta** — `POST /books`

```bash
curl -X POST http://localhost:5001/books \
  -H "Content-Type: application/json" -d '{
    "isbn": "978-1491950357",
    "title": "Building Microservices",
    "publicationYear": 2015,
    "price": 899.90,
    "stock": 5,
    "format": "Digital",
    "category": "Tecnico",
    "authors": ["Sam Newman"],
    "genres": ["Arquitectura de software"],
    "concepts": [{"name": "Microservicio",
                  "definition": "Servicio pequeno, autonomo y desplegable de forma independiente."}],
    "images": [{"url": "https://covers.openlibrary.org/b/isbn/9781491950357-L.jpg",
                "isCover": true}]
  }'
```

Responde `201` con la cabecera `Location`. El mismo alta con el cuerpo en XML
—una respuesta del servicio se puede reenviar tal cual como peticion:

```bash
curl -X POST "http://localhost:5001/books?output=xml" \
  -H "Content-Type: application/xml" --data-binary '<?xml version="1.0" encoding="UTF-8"?>
<book xmlns="urn:library:catalog:1.0" isbn="978-0596007126">
  <title>Head First Design Patterns</title>
  <publicationYear>2004</publicationYear>
  <price currency="MXN">720.00</price>
  <stock>8</stock>
  <format ref="1">Fisico</format>
  <category>Tecnico</category>
  <authors count="1"><author>Eric Freeman</author></authors>
</book>'
```

**Modificar** — `PUT /books/{id}`: el cuerpo describe el libro completo.
Las cuatro colecciones se sustituyen; la que no venga **queda vacia**.

**Actualizar** — `PATCH /books/{id}`: solo cambia lo enviado. Una coleccion
presente se reemplaza entera; una ausente no se toca.

```bash
curl -X PATCH http://localhost:5001/books/14 \
  -H "Content-Type: application/json" -d '{"price": 950.00, "stock": 3}'
```

**Borrar** — `DELETE /books/{id}`. Autores, generos, conceptos e imagenes
del libro caen con el por `ON DELETE CASCADE`; los catalogos no se tocan.

Cada operacion de escritura ocurre dentro de **una sola transaccion**: si algo
falla a medio camino, no queda un libro sin sus relaciones.

### Codigos de error

| Codigo | Cuando |
|---|---|
| `400` | Campo faltante o invalido, catalogo inexistente, parametro mal formado |
| `404` | El libro no existe |
| `409` | ISBN repetido, o una segunda imagen marcada como portada |
| `415` | `Content-Type` que no es JSON ni XML |
| `503` | PostgreSQL no responde |

El cuerpo del error respeta el formato pedido:

```json
{"error": {"status": 400, "code": "validation_error",
           "message": "El formato 'Papiro' no existe en el catalogo.",
           "details": ["Valores disponibles: 1=Fisico, 2=Digital, 3=Audiolibro, 4=Pasta dura."]}}
```

---

## 8. Conceptos de computo en la nube

`GET /cloud-concepts` devuelve los conceptos que ya fueron clasificados en un
modelo de servicio en la nube **junto con el libro completo** en el que estan
definidos, agrupados por modelo.

```bash
curl "http://localhost:5001/cloud-concepts"                  # XML, los cuatro modelos
curl "http://localhost:5001/cloud-concepts?model=IaaS"       # solo IaaS
curl "http://localhost:5001/cloud-concepts?output=json"
```

| Parametro | Para que sirve |
|---|---|
| `model` | `IaaS`, `PaaS`, `SaaS`, `FaaS` o `N/A`. Sin distinguir mayusculas (`iaas` vale). Omitido = todos |
| `limit` / `offset` | Paginacion sobre las clasificaciones, igual que en `/books` |
| `output` | `xml` o `json` |

**De donde salen los datos.** No de una tabla de conceptos "de nube": salen de
`library.clasificaciones_cloud`, que llena el modulo SOAP cuando la app de
escritorio ejecuta `RegistrarClasificacion`
([`wsdl/library-classiffier.wsdl`](wsdl/library-classiffier.wsdl)). Este
endpoint es la **cara de lectura** de esa informacion para clientes que hablan
JSON/XML en vez de SOAP. Si todavia nadie ha clasificado nada, los cuatro
modelos salen igual con `count="0"`: la forma de la respuesta no depende de los
datos.

**El `<book>` anidado es el mismo de `GET /books/{id}`**, con el diseno de
`library.xml` completo (autores, generos, conceptos, imagenes). Se emite con el
mismo serializador, de modo que no hay dos representaciones de un libro que
mantener en paralelo.

```xml
<?xml version="1.0" encoding="UTF-8"?>
<cloudConcepts xmlns="urn:library:catalog:1.0" version="1.0"
               generatedAt="2026-09-08T21:32:36Z" source="library_db" schema="library"
               count="3" total="3" limit="50" offset="0">
  <model count="1" name="IaaS">
    <concept ref="7">
      <name>Virtualizacion</name>
      <definition>Abstraccion del hardware fisico en recursos logicos.</definition>
      <classification id="1" model="IaaS">
        <classifiedBy>alumno@udem.mx</classifiedBy>
        <classifierName>Juan Perez</classifierName>
        <classifiedAt>2026-03-04T12:00:00-06:00</classifiedAt>
      </classification>
      <book id="3" isbn="978-0133970777">
        <title>Fundamentos de Sistemas de Bases de Datos</title>
        ...
      </book>
    </concept>
  </model>
  <model count="0" name="PaaS" />
  ...
</cloudConcepts>
```

Detalles que conviene conocer:

* **La unidad es la clasificacion, no el concepto.** Un mismo concepto aparece
  tantas veces como veces se haya clasificado (un par libro-concepto distinto,
  o un clasificador distinto). Por eso el libro va dentro del concepto.
* **`<definition>` puede faltar.** Las dos claves foraneas de
  `clasificaciones_cloud` son independientes (`concepto_id -> concepts`,
  `libro_isbn -> books`): nada obliga a que ese par exista ademas en
  `book_concepts`. Cuando no existe, la clasificacion es valida y aparece, solo
  que sin definicion.
* **`N/A` solo aparece si hay filas**, porque no es un modelo de nube sino la
  marca de "este concepto no es de computo en la nube" -- mismo criterio que
  `ObtenerEstadisticasPorModelo`.
* **Un `model` fuera de catalogo responde `400`** antes de tocar la base, con la
  lista de valores validos en `details`.
* Cabecera `X-Total-Count` con el total que cumple el filtro.

**Requisito**: el modulo SOAP debe estar cargado en la base
(`psql -U library_user -d library_db -f sql/soap_module.sql`), que es donde
viven la vista `v_conceptos_cloud` y la funcion `sp_conceptos_cloud` que
respaldan este endpoint.

---

## 9. Documentacion Swagger

* **`/docs`** — Swagger UI, con *Try it out* contra este mismo servicio.
* **`/openapi.json`** — el documento OpenAPI 3.0.3.

La especificacion se escribe a mano en `openapi.py` y describe los dos
formatos de intercambio, todos los filtros, los esquemas y los codigos de
error. Flasgger sirve los archivos de Swagger UI **desde el propio paquete**,
asi que la documentacion funciona sin conexion a Internet.

Para importarla en Postman o generar un cliente:

```bash
curl -s http://localhost:5001/openapi.json -o openapi.json
```

Si el servicio queda detras de un proxy inverso, en Swagger UI elija el
servidor *"Mismo origen que esta pagina"* para que *Try it out* apunte a la
URL publica.

---

## 10. Pruebas

```bash
./scripts/pruebas.sh                        # contra http://localhost:5001
BASE=http://192.168.1.50:5001 ./scripts/pruebas.sh
```

Recorre las operaciones CRUD, la busqueda por atributos, los dos formatos,
CORS y los codigos de error. Da de alta un libro de prueba y lo borra al
terminar, de modo que deja la base como la encontro.

---

## 11. Despliegue en CentOS 10 Stream

Se asume PostgreSQL ya instalado, con `library_user` / `library_db` cargados
(seccion 6.2 y 6.6 de [`../apps/web_monolito/README.md`](../apps/web_monolito/README.md)).

### 11.1 Python y el codigo

```bash
sudo dnf install -y python3 python3-pip
sudo useradd --system --home-dir /opt/library --shell /sbin/nologin library || true

sudo mkdir -p /opt/library
# Copie la carpeta library_soap_service/ al servidor (scp o git clone)
sudo cp -r library_soap_service /opt/library/soap
sudo chown -R library:library /opt/library

sudo -u library python3 -m venv /opt/library/soap/.venv
sudo -u library /opt/library/soap/.venv/bin/pip install -r /opt/library/soap/requirements.txt
```

### 11.2 Configuracion

```bash
sudo -u library cp /opt/library/soap/.env.example /opt/library/soap/.env
sudo -u library vi /opt/library/soap/.env        # PGPASSWORD y CORS_ORIGINS
sudo chmod 600 /opt/library/soap/.env            # solo el servicio lo lee
```

En produccion enumere los origenes en lugar de dejar `*`:

```
CORS_ORIGINS=https://libreria.ejemplo.mx,https://admin.ejemplo.mx
DEBUG=false
```

### 11.3 Servicio systemd

```bash
sudo tee /etc/systemd/system/library-soap.service > /dev/null <<'EOF'
[Unit]
Description=Libreria en Linea — microservicio de libros (Flask)
After=network-online.target postgresql.service
Wants=network-online.target

[Service]
Type=simple
User=library
Group=library
WorkingDirectory=/opt/library/soap/soap
ExecStart=/opt/library/soap/.venv/bin/gunicorn \
          --workers 3 --bind 127.0.0.1:5001 \
          --access-logfile - --error-logfile - wsgi:application
Restart=on-failure
RestartSec=5

# Endurecimiento
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=full
ProtectHome=true

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable --now library-soap
sudo systemctl status library-soap
```

`gunicorn` no lee `PORT` del `.env`: el puerto va en `--bind`. `python app.py`
(el servidor de desarrollo de Flask) si lo lee, pero no debe usarse en
produccion.

### 11.4 Proxy inverso

Con **nginx**:

```nginx
location /soap/ {
    proxy_pass http://127.0.0.1:5001/;
    proxy_set_header Host              $host;
    proxy_set_header X-Real-IP         $remote_addr;
    proxy_set_header X-Forwarded-For   $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
}
```

Con **Apache httpd** (`/etc/httpd/conf.d/library-soap.conf`):

```apache
ProxyPreserveHost On
ProxyPass        /soap/ http://127.0.0.1:5001/
ProxyPassReverse /soap/ http://127.0.0.1:5001/
RequestHeader set X-Forwarded-Proto "https"
```

En los dos casos, SELinux necesita permiso para que el servidor web abra
conexiones salientes:

```bash
sudo setsebool -P httpd_can_network_connect 1
```

**No anada cabeceras CORS en el proxy.** Ya las emite Flask; duplicar
`Access-Control-Allow-Origin` hace que el navegador rechace la respuesta.

### 11.5 Firewall

```bash
# Con proxy inverso (recomendado): solo 80/443
sudo firewall-cmd --permanent --add-service=http --add-service=https
# Acceso directo al microservicio, si lo necesita
sudo firewall-cmd --permanent --add-port=5001/tcp
sudo firewall-cmd --reload
```

### 11.6 Verificacion

```bash
curl -s http://localhost:5001/health
curl -s -o /dev/null -w '%{http_code}\n' http://localhost:5001/books
sudo journalctl -u library-soap -f
```

---

## 12. Problemas frecuentes

| Sintoma | Causa habitual |
|---|---|
| `/health` da `503` con *password authentication failed* | `PGPASSWORD` del `.env` no coincide con el rol de PostgreSQL |
| `/health` da `503` con *Connection refused* | PostgreSQL apagado, o `PGHOST`/`PGPORT` equivocados |
| `relation "books" does not exist` | `PGSCHEMA` no es `library`, o la base no tiene el esquema cargado |
| El navegador dice *blocked by CORS policy* | El origen no esta en `CORS_ORIGINS`, o el proxy duplica la cabecera |
| Todas las busquedas devuelven 0 con `?format=...` | Valor tomado como filtro de formato; use `?output=xml` |
| `pip install` falla al compilar `psycopg2` | Falta la rueda para su version de Python: `pip install -U pip` y reintente |

---

## 13. Seguridad

* El `.env` **no se publica**: esta en `library_soap_service/.gitignore`.
  Compruebelo con `git ls-files | grep -i "\.env"` — solo debe salir
  `library_soap_service/.env.example`.
* El servicio no autentica: cualquiera que lo alcance puede modificar el
  catalogo. Publiquelo solo detras del proxy inverso, restrinja
  `CORS_ORIGINS` y, si va a Internet, ponga autenticacion delante.
* Todo el SQL usa parametros (`%s`); los nombres de columna de `sort` salen de
  una lista blanca. No hay concatenacion de valores del usuario en las
  consultas.
* `DEBUG=false` en el servidor: con `true`, los errores 500 devuelven el
  detalle de la excepcion al cliente.
