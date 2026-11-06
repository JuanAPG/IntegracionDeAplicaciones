# Guía para grabar el vídeo de evidencias

Paso a paso exacto, con cada clic y cada texto que hay que escribir.
Dura unos **6 minutos** grabando sin prisa.

---

## Antes de empezar (no se graba)

**1. Comprueba que los siete componentes responden.**

```bash
cd "apps/JavaDesktop_app"
java -cp "target/classes:$(cat target/cp.txt)" mx.udem.library.desktop.Diagnostico
```

Los siete destinos deben decir `ARRIBA`. Si `tracking` dice `CAIDO`, arranca
el servidor de rastreo (paso 2). Si falla alguno de los otros seis, la IP de la
instancia cambió: mírala con `gcloud compute instances list` y cámbiala en
**Ajustes** dentro de la app.

**2. Arranca el servidor de rastreo** (déjalo en una terminal aparte):

```bash
cd apps/JavaDesktop_app/tracking_server
./run.sh
```

Debe decir `Servidor de rastreo en http://0.0.0.0:5900`. Si dice que el puerto
está ocupado, te dirá qué proceso lo tiene: mátalo y repite.

**3. Arranca la aplicación:**

```bash
cd apps/JavaDesktop_app
mvn -s maven-settings.xml clean javafx:run
```

**4. Ten a mano** tu correo y contraseña. Empieza a grabar con la ventana de
inicio de sesión ya visible.

---

## El guion, paso a paso

### 1 · Inicio de sesión  *(~40 s)*

| # | Qué haces | Qué se ve y qué decir |
|---|---|---|
| 1.1 | Clic en el campo **correo electrónico**, escribe tu correo | — |
| 1.2 | Clic en **contraseña**, escribe tu contraseña | — |
| 1.3 | Clic en **Iniciar sesion** | Entra al catálogo |

> **Qué contar:** la aplicación manda las credenciales a `POST /login` del
> microservicio de autenticación y recibe un **JWT**. La contraseña no se
> guarda en ningún sitio; lo que se conserva es el token, que el servidor
> puede revocar.

### 2 · Identidad y estado de los servicios  *(~30 s)*

| # | Qué haces | Qué se ve |
|---|---|---|
| 2.1 | Señala la barra superior | Los **siete semáforos en verde** y tu nombre |
| 2.2 | Pon el ratón encima de un semáforo | Aparece el detalle de ese servicio |
| 2.3 | Clic en **Comprobar servicios** | Los siete vuelven a consultarse |

> **Qué contar:** el nombre sale del microservicio de **usuarios**
> (`GET /users/<id>`), no del token. Los semáforos tienen **tres** estados:
> verde disponible, **ámbar lee pero no escribe** (Redis caído) y rojo caído.

### 3 · Catálogo  *(~50 s)*

| # | Qué haces | Qué se ve |
|---|---|---|
| 3.1 | Señala las tarjetas | Portada, título, autores, precio, ISBN y disponibilidad |
| 3.2 | Señala **Cien Anos de Soledad** | **Sin existencias** en rojo y su botón *Agregar* deshabilitado |
| 3.3 | Escribe `clean` en el buscador y pulsa **Buscar** | Filtra; arriba a la derecha cambia el contador |
| 3.4 | Clic en **Ver detalle** de *Clean Code* | Ficha con descripción y **Sobre los autores** |
| 3.5 | Clic en **Close** | Vuelve al catálogo |
| 3.6 | Clic en **Ver todo** | Los 16 libros otra vez |

> **Qué contar:** el catálogo viene del microservicio de **libros** y es una
> lectura **pública**: va sin token a propósito. La ficha del autor viene de
> **otro** microservicio, el de autores: una pantalla, dos servicios.
> La descripción son las definiciones de los conceptos, porque el catálogo
> no almacena sinopsis — se comprobó contra el esquema.

### 4 · Cesta  *(~50 s)*

| # | Qué haces | Qué se ve |
|---|---|---|
| 4.1 | En *Fundamentos de Sistemas…* pulsa **Agregar** | El botón dice *Agregado* y la pestaña Cesta muestra **1** |
| 4.2 | En *Fundacion* pulsa **Agregar** | La pestaña muestra **2** |
| 4.3 | Clic en la pestaña **Cesta** | Tabla con los dos libros y el subtotal |
| 4.4 | Sube la cantidad de un libro con la flecha ▲ | El subtotal se recalcula solo |
| 4.5 | Vuelve a bajarla a 1 | — |

> **Qué contar:** la cesta vive **en memoria** en la aplicación, porque no
> existe microservicio de cesta y no se inventó uno. Los importes de esta
> pantalla son una **estimación**: el total de verdad lo calcula el servidor
> congelando los precios del catálogo.

### 5 · Compra: pedido + pago  *(~80 s)*

| # | Qué haces | Qué se ve |
|---|---|---|
| 5.1 | Clic en **Confirmar compra** | Diálogo con la dirección y el método de pago |
| 5.2 | Deja la dirección y el costo de envío como están | `120.00` |
| 5.3 | Comprueba que el método sea **efectivo** | Aviso: *nacerá APLICADO y el pedido pasará a pagado* |
| 5.4 | Clic en **Comprar** | La bitácora avanza paso a paso |
| 5.5 | Espera 5-10 s y lee la bitácora | Número de pedido, referencia de pago y código de rastreo |
| 5.6 | Clic en **Close** | Salta solo a **Rastreo** con el código puesto |

> **Qué contar, leyendo la bitácora:** son **cuatro** llamadas a servicios
> reales — revalidar la cesta contra el catálogo, `POST /pedidos`,
> consultar el saldo en pagos y `POST /pagos` —. El precio **no** se envía.
> La clave de idempotencia se genera una vez por diálogo, de modo que un
> doble clic devolvería el mismo pago en lugar de cobrar dos veces. Y no se
> pide ningún dato de tarjeta: el servicio los rechaza con 400.

### 6 · Rastreo en el mapa  *(~2 min — es el plato fuerte)*

Ya estás en la pestaña **Rastreo** con el código puesto.

| # | Qué haces | Qué se ve |
|---|---|---|
| 6.1 | Clic en **Rastrear pedido** | El mapa dibuja la ruta y aparece el vehículo |
| 6.2 | Espera sin tocar nada | *Pedido confirmado* → *Preparando pedido* → *Pedido enviado* |
| 6.3 | A los ~16 s | Pasa a **En ruta de entrega** y el vehículo arranca |
| 6.4 | Deja correr 1-2 min | La estela azul se alarga; bajan los km y el tiempo |
| 6.5 | Al llegar | **Entregado**, el vehículo se pone **verde** y dice *ya llegó* |

> **Qué contar:** las coordenadas llegan por **WebSocket**, una por segundo,
> y el mapa no se recarga en ningún momento. La conexión la abre **Java**, no
> la página, y manda el JWT en la cabecera del saludo. La ruta va por calles
> reales de Monterrey (polilíneas de OSRM cacheadas). **«Entregado» ocurre al
> terminar la ruta**, no por un temporizador.

#### Demuestra la autorización *(opcional pero vale la pena, ~20 s)*

| # | Qué haces | Qué se ve |
|---|---|---|
| 6.6 | Borra el código y escribe `LIB-MTY-2026-000999` | Un pedido que no es tuyo |
| 6.7 | Clic en **Rastrear pedido** | *El servidor no autorizó este rastreo* |

> **Qué contar:** el servidor de rastreo verifica la firma del token y después
> le **pregunta al microservicio de pedidos** si el pedido es tuyo. Adivinar un
> código no sirve de nada.

### 7 · Mis compras  *(~40 s)*

| # | Qué haces | Qué se ve |
|---|---|---|
| 7.1 | Clic en la pestaña **Mis compras** | Tabla con tus pedidos |
| 7.2 | Clic en la fila del pedido recién creado | Abajo: libros, importes y el pago |
| 7.3 | Señala el estado | **pagado**, y el pago **aplicado** |
| 7.4 | Clic en **Rastrear este pedido** | Vuelve al mapa con ese código |

> **Qué contar:** los libros y los importes vienen del servicio de **pedidos**
> y el estado del cobro del de **pagos**: dos microservicios en una pantalla.
> El pedido figura como `pagado` porque un **disparador de PostgreSQL** lo
> cambió cuando el pago aplicado cubrió el total; la aplicación no lo decidió.

### 8 · Cerrar sesión  *(~15 s)*

| # | Qué haces | Qué se ve |
|---|---|---|
| 8.1 | Clic en **Cerrar sesion** | Pide confirmación |
| 8.2 | Clic en **OK** | Vuelve al inicio de sesión |

> **Qué contar:** el cierre de sesión **se manda al servidor** con el token,
> para que lo revoque en Redis. Un logout que solo borra en el cliente dejaría
> el token vivo media hora.

---

## Cosas que pueden salir mal durante la grabación

| Síntoma | Causa y arreglo |
|---|---|
| Semáforos en rojo al entrar | Cambió la IP de la instancia. **Ajustes** → escribe la IP nueva → Guardar |
| `tracking` en rojo y el resto verde | El servidor de rastreo no está arrancado: `./run.sh` |
| *El servidor no autorizó este rastreo* con **tu** código | Al `run.sh` le falta `JWT_SECRET_KEY`, o no es el mismo que el de los servicios |
| El mapa tarda en pintarse | Los mosaicos vienen de Internet; dale unos segundos antes de seguir |
| *Sin existencias* en el libro que ibas a comprar | Elige otro: cada compra descuenta existencias de verdad |

## Qué NO hacer en el vídeo

- **No enseñes tu contraseña al teclearla** si grabas el teclado.
- **No abras el archivo `tracking_server/.env`**: contiene el secreto que firma
  todos los tokens.
- No pases por **Ajustes** enseñando IPs si prefieres no publicarlas.
