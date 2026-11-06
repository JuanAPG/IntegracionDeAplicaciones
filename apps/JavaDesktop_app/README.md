# Cliente de escritorio Java — Librería en Línea

Aplicación de escritorio **JavaFX** que consume los seis microservicios Flask del
monorepo por **REST/JSON con JWT**, y un **servidor de rastreo propio
(Flask + Flask-Sock)** por **WebSocket**, para seguir la entrega de un pedido
sobre un mapa de **Leaflet + OpenStreetMap** embebido en un `WebView`.

No hay ninguna conexión directa a PostgreSQL: **todas** las operaciones de
negocio pasan por los microservicios.

---

## 1. Qué necesitas

| Pieza | Versión | Comprobar con |
|---|---|---|
| JDK | 21 o superior (probado con 25) | `java -version` |
| Maven | 3.9+ | `mvn -version` |
| Python | 3.11+ (para el servidor de rastreo) | `python3 --version` |
| Los seis microservicios | corriendo en la instancia de GCP | `curl http://<IP>:5000/health` |

JavaFX **no** hay que instalarlo: lo descarga Maven.

---

## 2. Arrancar

### 2.1 El servidor de rastreo

```bash
cd apps/JavaDesktop_app/tracking_server
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# El MISMO secreto que usan los seis microservicios, para poder
# verificar los tokens que emite el servicio de login:
export JWT_SECRET_KEY="<el mismo valor que en el .env de la raiz>"
export PEDIDOS_URL="http://<IP_DE_LA_VM>:5004"

python app.py          # queda escuchando en el 5900
```

Comprobación: `curl http://localhost:5900/health` y, en el navegador,
`http://localhost:5900/mapa` debe pintar Monterrey.

> **Sin `JWT_SECRET_KEY` no se autoriza ningún rastreo**, y el servidor lo dice
> al arrancar. Para enseñar el mapa sin levantar los microservicios existe
> `REQUIRE_AUTH=false`, que **abre el rastreo a cualquiera**: solo para una
> demostración local.

### 2.2 La aplicación

```bash
cd apps/JavaDesktop_app
mvn -s maven-settings.xml clean javafx:run
```

El `-s maven-settings.xml` solo hace falta en equipos cuyo `~/.m2/settings.xml`
redirige `central` a un repositorio interno; en un equipo normal basta
`mvn clean javafx:run`.

### 2.3 Apuntar a tu instancia

La IP de GCP cambia en cada reinicio. Tres formas, de más a menos cómoda:

1. **Ajustes** dentro de la aplicación: un campo reapunta los siete destinos.
2. `export LIBRARY_VM_IP=34.51.89.203` antes de arrancar.
3. `~/.library-desktop/config.properties` (lo escribe la propia aplicación).

El servidor de rastreo corre en **tu equipo** (`localhost:5900`), así que su URL
hay que dejarla apuntando ahí aunque los otros seis estén en la nube.

---

## 3. Los siete destinos

| Servicio | Puerto | Qué usa la aplicación |
|---|---|---|
| login | 5000 | `POST /login`, `POST /refresh`, `POST /logout`, `GET /session` |
| books | 5001 | `GET /books`, `GET /books/<id>` |
| users | 5002 | `GET /users/<id>` (el perfil propio) |
| authors | 5003 | `GET /authors`, `GET /authors/<id>` |
| pedidos | 5004 | `POST /pedidos`, `GET /pedidos`, `GET /pedidos/<id>` |
| pagos | 5005 | `GET /metodos`, `GET /pedidos/<id>/saldo`, `POST /pagos`, `GET /pagos` |
| rastreo | 5900 | `WS /ws?code=…`, `GET /health`, `GET /api/entregas/<codigo>` |

**El mapa de puertos del enunciado está invertido** respecto a lo que responde la
instancia (dice *pagos 5002, pedidos 5003, users 5004, autores 5005*). Se usa el
mapa real, y la aplicación lo vuelve a comprobar en cada arranque: cada
`/health` declara su propio nombre, y si un puerto contesta con otra identidad
el semáforo se pone en ámbar y lo dice.

---

## 4. Estructura

```
apps/JavaDesktop_app/
├── pom.xml                     JavaFX 25 + Jackson. Sin driver de PostgreSQL
├── maven-settings.xml          solo para equipos con un espejo interno
├── src/main/java/mx/udem/library/desktop/
│   ├── App.java                arranque y navegación
│   ├── Contexto.java           un TokenStore y seis clientes, construidos una vez
│   ├── config/                 Config, Service (puertos y parámetro de formato)
│   ├── net/                    ApiClient (REST+JWT), ApiException, TrackingSocket (WS)
│   ├── auth/TokenStore.java    token, refresco, caducidad, claims
│   ├── model/                  Book, Author, Order, Payment, Balance, Shipment…
│   ├── service/                un cliente por microservicio
│   ├── cart/Cart.java          la cesta, en memoria
│   └── ui/                     Login, Catálogo, Cesta, Checkout, Mis compras, Rastreo
├── src/main/resources/
│   ├── estilos.css
│   └── map/mapa.html           el mapa de Leaflet que carga el WebView
└── tracking_server/            Flask + Flask-Sock
    ├── app.py                  WebSocket, difusión por código, HTTP
    ├── auth.py                 verificación del JWT + propiedad del pedido
    ├── entregas.py             estados de entrega y avance sobre la ruta
    ├── rutas.py                rutas por calles reales de Monterrey
    ├── rutas_monterrey.json    120 tramos OSRM cacheados (16 puntos de la ciudad)
    └── static/mapa.html        la misma página, servida por HTTP para probar
```

---

## 5. Cómo rastrear un pedido

1. Compra algo (pestaña **Catálogo** → **Cesta** → *Confirmar compra*).
2. Al terminar, la aplicación salta sola a **Rastreo** con el código ya puesto.
3. También puedes ir a **Mis compras**, elegir un pedido y pulsar *Rastrear*,
   o escribir el código a mano.

El código se deriva del número real del pedido:
`PED-000042` → **`LIB-MTY-2026-000042`**.

**Cada código tiene su propia ruta**: el destino se deriva del código con un
hash estable, de modo que dos pedidos van a sitios distintos y el mismo pedido
va siempre al mismo sitio, incluso tras reiniciar el servidor.

Los cinco estados —*Pedido confirmado · Preparando pedido · Pedido enviado ·
En ruta de entrega · Entregado*— avanzan solos, y **«Entregado» se alcanza al
terminar la ruta**, no por un temporizador.

---

## 6. Limitaciones conocidas, y por qué

1. **El catálogo no tiene sinopsis.** Lo verifiqué contra el esquema y contra el
   serializador: la tabla `books` guarda ISBN, título, año, precio, existencias,
   formato y categoría, y nada más. Como descripción se muestran las
   definiciones de los conceptos asociados al libro, diciéndolo en la ficha.
2. **El `trackingCode` del servicio de pedidos siempre viene vacío** para un
   usuario normal: escribirlo exige el permiso `orders:status`, que da 403
   incluso sobre el propio pedido. Por eso el seguimiento se ancla al número de
   pedido, que sí es real, en lugar de a un campo que el cliente no puede
   rellenar. El enunciado contempla exactamente este caso.
3. **El servidor de rastreo no guarda nada en disco.** Si se reinicia, las
   entregas en curso vuelven a empezar. Es deliberado: el estado del negocio
   vive en el microservicio de pedidos, no aquí.
4. **Los mosaicos del mapa necesitan Internet** (OpenStreetMap). Las rutas no:
   están cacheadas en `rutas_monterrey.json`.
5. **La aplicación no registra cuentas ni verifica correos.** Usa una cuenta ya
   creada; el registro existe en el cliente de Tkinter del monorepo.
