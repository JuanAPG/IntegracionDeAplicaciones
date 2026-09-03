# Plan de pruebas — Módulo SOAP de clasificación

Casos P01–P04 (positivos) y N01–N07 (negativos) del módulo
`library_soap_service`. Cada caso trae los pasos exactos para
reproducirlo (por `curl` y, cuando aplica, desde la app de escritorio),
la petición SOAP completa, el resultado esperado y una **salida de
referencia real**, ya verificada, capturada el 2026-09-02 contra una
instancia PostgreSQL 16 + Flask desechable. Las columnas *Resultado
obtenido*, *Estado* y *Conclusión* de cada caso se dejan en blanco para
que quien ejecute las pruebas en su propio entorno las llene con su
propia evidencia.

---

## 0. Preparar el entorno

Estos pasos dejan el servicio y la base listos para correr los 11 casos.
Repítelos cada vez que quieras una base limpia.

1. **Base de datos.** Con PostgreSQL disponible (local, contenedor, o el
   servidor real):
   ```bash
   psql -U <rol_admin> -f db/00_create_database.sql
   psql -U library_user -d library_db -f db/01_schema.sql
   psql -U library_user -d library_db -f library_soap_service/sql/soap_module.sql
   ```
2. **Datos mínimos para clasificar.** Necesitas al menos un libro, una
   categoría y **más de 5 pares (libro, concepto)** sin clasificar para
   poder ejecutar P04 con margen. Ejemplo mínimo (ajusta si ya tienes
   catálogo real):
   ```sql
   SET search_path TO library, public;
   INSERT INTO formats(name) VALUES ('Digital'), ('Fisico');
   INSERT INTO categories(name) VALUES ('Tecnico'), ('Academico');
   INSERT INTO books(isbn, title, publication_year, price, stock, format_id, category_id) VALUES
     ('978-0000000001', 'Libro Uno', 2020, 100, 5, 1, 1),
     ('978-0000000002', 'Libro Dos', 2020, 100, 5, 1, 1),
     ('978-0000000003', 'Libro Tres', 2020, 100, 5, 1, 1);
   INSERT INTO concepts(name) VALUES
     ('ConceptoA'), ('ConceptoB'), ('ConceptoC'), ('ConceptoD'), ('ConceptoE'), ('ConceptoF'), ('ConceptoG');
   INSERT INTO book_concepts(book_id, concept_id, definition) VALUES
     (1, 1, 'def A'), (1, 2, 'def B'), (1, 3, 'def C'),
     (2, 4, 'def D'), (2, 5, 'def E'),
     (3, 6, 'def F'), (3, 7, 'def G');
   ```
3. **Levantar el microservicio** (ajusta `.env` con las credenciales
   reales, o exporta las variables antes de arrancar):
   ```bash
   cd library_soap_service
   source .venv/bin/activate
   PGHOST=localhost PGPORT=5432 PGDATABASE=library_db PGUSER=library_user \
   PGPASSWORD=777 PGSCHEMA=library HOST=127.0.0.1 PORT=5001 \
   python soap/app.py
   ```
   El endpoint queda en `http://127.0.0.1:5001/soap/clasificacion`
   (variable `BASE` en los comandos de abajo).
4. **Correo de prueba.** Todos los casos usan
   `clasificador_email = "prueba@example.com"`; el clasificador se da de
   alta automáticamente en el primer contacto (ver
   `fn_get_or_create_clasificador` en `soap_module.sql`), no hace falta
   crearlo a mano.

### Cómo ejecutar cada caso

Cada caso trae el comando `curl` exacto. También puedes reproducirlo
desde la GUI (`apps/services/escritorio/Ejercicio1.py`, pestaña
**Clasificación SOAP**): captura la misma información en los campos
Nombre/Apellidos/Correo, "Cargar conceptos pendientes",
"Registrar clasificación (SOAP)" y "Actualizar progreso"; la evidencia
en ese caso es una captura de pantalla del resultado o del cuadro de
error mostrado.

---

## 1. Pruebas positivas

### P01 — Obtener conceptos pendientes

**Objetivo:** confirmar que `ObtenerConceptosPendientes` devuelve una
lista válida de pares (libro, concepto) sin clasificar.

**Precondición:** entorno preparado (paso 0); `prueba@example.com` no ha
clasificado nada todavía.

**Pasos:**
1. Enviar la petición de abajo al endpoint.
2. Confirmar HTTP 200.
3. Confirmar que `<clv:ObtenerConceptosPendientesResponse>` trae uno o
   más `<clv:concepto>`, cada uno con `referencia_libro`,
   `referencia_concepto`, `titulo_libro`, `nombre_categoria` y
   `nombre_concepto`.

**Entrada:**
```bash
BASE=http://127.0.0.1:5001/soap/clasificacion
curl -sS -X POST "$BASE" -H "Content-Type: text/xml" --data-binary '<?xml version="1.0" encoding="UTF-8"?>
<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">
  <soap:Body>
    <ObtenerConceptosPendientesRequest xmlns="urn:library:clasificacion:1.0">
      <clasificador_email>prueba@example.com</clasificador_email>
      <limite>10</limite>
    </ObtenerConceptosPendientesRequest>
  </soap:Body>
</soap:Envelope>'
```

**Resultado esperado:** HTTP 200, un `ObtenerConceptosPendientesResponse`
con al menos un `<concepto>` completo.

**Salida de referencia (verificada):**
```xml
<soap:Envelope xmlns:clv="urn:library:clasificacion:1.0" xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/"><soap:Header/><soap:Body><clv:ObtenerConceptosPendientesResponse><clv:concepto><clv:referencia_libro>978-1491950357</clv:referencia_libro><clv:referencia_concepto>Microservicio</clv:referencia_concepto><clv:titulo_libro>Building Microservices</clv:titulo_libro><clv:nombre_categoria>Tecnico</clv:nombre_categoria><clv:nombre_concepto>Microservicio</clv:nombre_concepto></clv:concepto>...</clv:ObtenerConceptosPendientesResponse></soap:Body></soap:Envelope>
HTTP=200
```

**Evidencia a capturar:** salida completa del `curl` (o captura de la
lista de pendientes en la GUI).

| Resultado obtenido | Estado | Conclusión |
|---|---|---|
| | | |

---

### P02 — Registrar IaaS/PaaS/SaaS/FaaS

**Objetivo:** validar que `RegistrarClasificacion` acepta y persiste
cada uno de los cuatro modelos Cloud válidos.

**Precondición:** ejecutar P01 primero para obtener 4 pares
(libro, concepto) distintos aún pendientes (uno por modelo a probar).

**Pasos:** repetir 4 veces, una por modelo, cambiando
`referencia_libro`/`referencia_concepto` por un par pendiente distinto
cada vez.

**Entrada (ejemplo con SaaS; repetir con IaaS/PaaS/FaaS):**
```bash
curl -sS -X POST "$BASE" -H "Content-Type: text/xml" --data-binary '<?xml version="1.0" encoding="UTF-8"?>
<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">
  <soap:Body>
    <RegistrarClasificacionRequest xmlns="urn:library:clasificacion:1.0">
      <clasificador_email>prueba@example.com</clasificador_email>
      <referencia_libro>978-1491950357</referencia_libro>
      <referencia_concepto>Microservicio</referencia_concepto>
      <modelo_servicio>SaaS</modelo_servicio>
    </RegistrarClasificacionRequest>
  </soap:Body>
</soap:Envelope>'
```

**Resultado esperado:** HTTP 200, `exito=true`,
`mensaje="Clasificacion guardada exitosamente."`, para cada uno de los
4 modelos.

**Salida de referencia (verificada, IaaS/PaaS/SaaS/FaaS los 4 se probaron
por separado en la sesión de desarrollo con el mismo resultado):**
```xml
<soap:Envelope xmlns:clv="urn:library:clasificacion:1.0" xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/"><soap:Header/><soap:Body><clv:RegistrarClasificacionResponse><clv:exito>true</clv:exito><clv:mensaje>Clasificacion guardada exitosamente.</clv:mensaje></clv:RegistrarClasificacionResponse></soap:Body></soap:Envelope>
HTTP=200
```

**Evidencia a capturar:** las 4 respuestas `curl`, más
```sql
SELECT modelo_cloud, count(*) FROM library.clasificaciones_cloud GROUP BY modelo_cloud;
```
mostrando una fila por modelo probado.

| Resultado obtenido | Estado | Conclusión |
|---|---|---|
| | | |

---

### P03 — Obtener progreso de usuario

**Objetivo:** confirmar que `total_clasificados` y `total_pendientes`
reflejan exactamente lo registrado.

**Precondición:** ejecutar P02 primero (para tener clasificaciones
reales que contar). Anota cuántos pares clasificaste (`N`) y cuántos
quedaban pendientes en el catálogo de prueba (`M`).

**Pasos:**
1. Enviar la petición.
2. Comparar `total_clasificados` contra `N` y `total_pendientes` contra
   `M - N`.
3. Verificar el mismo número directamente en PostgreSQL (ver query de
   abajo) para confirmar que la función SQL y el conteo manual
   coinciden.

**Entrada:**
```bash
curl -sS -X POST "$BASE" -H "Content-Type: text/xml" --data-binary '<?xml version="1.0" encoding="UTF-8"?>
<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">
  <soap:Body>
    <ObtenerProgresoUsuarioRequest xmlns="urn:library:clasificacion:1.0">
      <clasificador_email>prueba@example.com</clasificador_email>
    </ObtenerProgresoUsuarioRequest>
  </soap:Body>
</soap:Envelope>'
```

**Resultado esperado:** HTTP 200, `total_clasificados` = número real de
filas en `clasificaciones_cloud` para ese clasificador,
`total_pendientes` = conceptos de `book_concepts` que ese clasificador
aún no registró.

**Salida de referencia (verificada, tras 1 clasificación sobre 2
pendientes):**
```xml
<soap:Envelope xmlns:clv="urn:library:clasificacion:1.0" xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/"><soap:Header/><soap:Body><clv:ObtenerProgresoUsuarioResponse><clv:total_clasificados>1</clv:total_clasificados><clv:total_pendientes>1</clv:total_pendientes></clv:ObtenerProgresoUsuarioResponse></soap:Body></soap:Envelope>
```

**Verificación cruzada en PostgreSQL:**
```sql
SET search_path TO library, public;
SELECT cl.email, count(cc.id) AS total_clasificados
  FROM clasificadores cl
  LEFT JOIN clasificaciones_cloud cc ON cc.clasificador_id = cl.id
 WHERE cl.email = 'prueba@example.com'
 GROUP BY cl.email;
```

**Evidencia a capturar:** respuesta SOAP + salida de la query SQL lado a
lado.

| Resultado obtenido | Estado | Conclusión |
|---|---|---|
| | | |

---

### P04 — Limitar conceptos pendientes (límite = 5)

**Objetivo:** confirmar que el parámetro `limite` efectivamente acota el
número de `<concepto>` devueltos.

**Precondición:** el catálogo de prueba debe tener **más de 5** pares
(libro, concepto) pendientes para ese clasificador (usa un correo que
no haya clasificado nada, o el bloque de datos del paso 0.2, que deja 7
pendientes).

**Pasos:**
1. Enviar la petición con `<limite>5</limite>`.
2. Contar los elementos `<concepto>` en la respuesta.
3. Confirmar que son exactamente 5, aunque haya más pendientes en la
   base.

**Entrada:**
```bash
curl -sS -X POST "$BASE" -H "Content-Type: text/xml" --data-binary '<?xml version="1.0" encoding="UTF-8"?>
<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">
  <soap:Body>
    <ObtenerConceptosPendientesRequest xmlns="urn:library:clasificacion:1.0">
      <clasificador_email>plan@example.com</clasificador_email>
      <limite>5</limite>
    </ObtenerConceptosPendientesRequest>
  </soap:Body>
</soap:Envelope>' | grep -o "<clv:concepto>" | wc -l
```

**Resultado esperado:** el conteo de `<clv:concepto>` es exactamente
`5`, nunca más, sin importar cuántos pendientes reales existan.

**Salida de referencia (verificada, sobre 7 pendientes reales):**
```
5
```

**Nota de diseño:** el límite por omisión es 10
(`CLASIFICACION_DEFAULT_LIMIT`) y el tope duro es 100
(`CLASIFICACION_MAX_LIMIT`, ver `config.py`): un cliente no puede pedir
un `limite` mayor a ese tope aunque lo intente, ni uno menor o igual a
cero (responde `SOAP Fault` de validación).

**Evidencia a capturar:** el número exacto de `<concepto>` contados.

| Resultado obtenido | Estado | Conclusión |
|---|---|---|
| | | |

---

## 2. Pruebas negativas (validación, seguridad y tolerancia a fallos)

### N01 — Repetir clasificación

**Objetivo:** verificar que reclasificar un concepto ya registrado por
el mismo clasificador responde `SOAP Fault` de conflicto (HTTP 409).

**Precondición:** haber registrado ya una clasificación válida para
`(prueba@example.com, <isbn>, <concepto>)` — usa la del caso P02.

**Pasos:**
1. Reenviar exactamente la misma petición de P02 (mismo email, mismo
   libro, mismo concepto; el modelo puede cambiar, no importa).
2. Confirmar HTTP 409 y `<faultcode>soap:Client.Conflicto</faultcode>`.

**Entrada:** igual que P02, pero ejecutada una segunda vez.

**Resultado esperado:** HTTP 409, categoría `CONFLICTO`, código
`clasificacion_duplicada`.

**Salida de referencia (verificada):**
```xml
<soap:Envelope xmlns:clv="urn:library:clasificacion:1.0" xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/"><soap:Header/><soap:Body><soap:Fault><faultcode>soap:Client.Conflicto</faultcode><faultstring>El clasificador 'ana@example.com' ya habia registrado el concepto 'Normalizacion'.</faultstring><detail><clv:ErrorDetalle><clv:categoria>CONFLICTO</clv:categoria><clv:codigo>clasificacion_duplicada</clv:codigo><clv:mensaje>El clasificador 'ana@example.com' ya habia registrado el concepto 'Normalizacion'.</clv:mensaje></clv:ErrorDetalle></detail></soap:Fault></soap:Body></soap:Envelope>
HTTP=409
```

**Evidencia a capturar:** respuesta completa + código HTTP.

| Resultado obtenido | Estado | Conclusión |
|---|---|---|
| | | |

---

### N02 — Concepto inexistente

**Objetivo:** validar que pedir un concepto que no existe en el
catálogo responde `SOAP Fault` de cliente, con mensaje claro.

**Pasos:**
1. Enviar `RegistrarClasificacion` con un `referencia_concepto` que no
   exista en `concepts.name`.
2. Confirmar HTTP 404 y el mensaje "No existe el concepto '...'.".

**Entrada:**
```bash
curl -sS -X POST "$BASE" -H "Content-Type: text/xml" --data-binary '<?xml version="1.0" encoding="UTF-8"?>
<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">
  <soap:Body>
    <RegistrarClasificacionRequest xmlns="urn:library:clasificacion:1.0">
      <clasificador_email>prueba@example.com</clasificador_email>
      <referencia_libro>978-0133970777</referencia_libro>
      <referencia_concepto>ConceptoQueNoExiste</referencia_concepto>
      <modelo_servicio>SaaS</modelo_servicio>
    </RegistrarClasificacionRequest>
  </soap:Body>
</soap:Envelope>' -w '\nHTTP=%{http_code}\n'
```

**Resultado esperado:** HTTP 404, categoría `CLIENTE`, código
`concepto_inexistente`.

**Salida de referencia (verificada):**
```xml
<soap:Envelope xmlns:clv="urn:library:clasificacion:1.0" xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/"><soap:Header/><soap:Body><soap:Fault><faultcode>soap:Client</faultcode><faultstring>No existe el concepto 'ConceptoQueNoExiste'.</faultstring><detail><clv:ErrorDetalle><clv:categoria>CLIENTE</clv:categoria><clv:codigo>concepto_inexistente</clv:codigo><clv:mensaje>No existe el concepto 'ConceptoQueNoExiste'.</clv:mensaje></clv:ErrorDetalle></detail></soap:Fault></soap:Body></soap:Envelope>
HTTP=404
```

| Resultado obtenido | Estado | Conclusión |
|---|---|---|
| | | |

---

### N03 — Modelo inválido

**Objetivo:** confirmar que un `modelo_servicio` fuera del catálogo
(`IaaS/PaaS/SaaS/FaaS/N-A`) es rechazado con `SOAP Fault` de validación.

**Pasos:**
1. Enviar `RegistrarClasificacion` con `modelo_servicio` = `"Papiro"`.
2. Confirmar HTTP 400 y `<faultcode>soap:Client.Validacion</faultcode>`.

**Entrada:**
```bash
curl -sS -X POST "$BASE" -H "Content-Type: text/xml" --data-binary '<?xml version="1.0" encoding="UTF-8"?>
<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">
  <soap:Body>
    <RegistrarClasificacionRequest xmlns="urn:library:clasificacion:1.0">
      <clasificador_email>prueba@example.com</clasificador_email>
      <referencia_libro>978-0133970777</referencia_libro>
      <referencia_concepto>Normalizacion</referencia_concepto>
      <modelo_servicio>Papiro</modelo_servicio>
    </RegistrarClasificacionRequest>
  </soap:Body>
</soap:Envelope>' -w '\nHTTP=%{http_code}\n'
```

**Resultado esperado:** HTTP 400, categoría `VALIDACION`, código
`modelo_invalido`, mensaje que enumera los valores permitidos.

**Salida de referencia (verificada):**
```xml
<soap:Envelope xmlns:clv="urn:library:clasificacion:1.0" xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/"><soap:Header/><soap:Body><soap:Fault><faultcode>soap:Client.Validacion</faultcode><faultstring>El modelo de servicio 'Papiro' no es valido. Valores permitidos: IaaS, PaaS, SaaS, FaaS, N/A.</faultstring><detail><clv:ErrorDetalle><clv:categoria>VALIDACION</clv:categoria><clv:codigo>modelo_invalido</clv:codigo><clv:mensaje>El modelo de servicio 'Papiro' no es valido. Valores permitidos: IaaS, PaaS, SaaS, FaaS, N/A.</clv:mensaje></clv:ErrorDetalle></detail></soap:Fault></soap:Body></soap:Envelope>
HTTP=400
```

| Resultado obtenido | Estado | Conclusión |
|---|---|---|
| | | |

---

### N04 — Enviar XML SOAP mal formado

**Objetivo:** confirmar que un XML mal formado produce un `SOAP Fault`
de cliente **sin ejecutar ninguna consulta SQL**, y sin exponer detalle
interno.

**Pasos:**
1. Anotar el conteo de filas en `clasificaciones_cloud` antes de la
   prueba (`SELECT count(*) FROM library.clasificaciones_cloud;`).
2. Enviar un cuerpo que no cierra las etiquetas.
3. Confirmar HTTP 400, `codigo=xml_invalido`, y que el conteo de filas
   **no cambió**.

**Entrada:**
```bash
curl -sS -X POST "$BASE" -H "Content-Type: text/xml" \
  --data-binary '<soap:Envelope><soap:Body><Roto>' -w '\nHTTP=%{http_code}\n'
```

**Resultado esperado:** HTTP 400, `faultcode=soap:Client`, mensaje de
parseo XML (nunca una traza de Python), cero filas nuevas en la base.

**Salida de referencia (verificada):**
```xml
<soap:Envelope xmlns:clv="urn:library:clasificacion:1.0" xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/"><soap:Header/><soap:Body><soap:Fault><faultcode>soap:Client</faultcode><faultstring>XML mal formado: unbound prefix: line 1, column 0</faultstring><detail><clv:ErrorDetalle><clv:categoria>CLIENTE</clv:categoria><clv:codigo>xml_invalido</clv:codigo><clv:mensaje>XML mal formado: unbound prefix: line 1, column 0</clv:mensaje></clv:ErrorDetalle></detail></soap:Fault></soap:Body></soap:Envelope>
HTTP=400
```

**Evidencia a capturar:** respuesta completa + los dos conteos de
`clasificaciones_cloud` (antes/después) demostrando que no cambiaron.

| Resultado obtenido | Estado | Conclusión |
|---|---|---|
| | | |

---

### N05 — Referencia de libro inexistente

**Objetivo:** validar que un ISBN que no existe en `books.isbn`
responde con un `SOAP Fault` de cliente claro (no un error genérico ni
una excepción de PostgreSQL sin traducir).

**Pasos:**
1. Enviar `RegistrarClasificacion` con un ISBN inventado.
2. Confirmar HTTP 404 y el mensaje "No existe un libro con ISBN '...'.".

**Entrada:**
```bash
curl -sS -X POST "$BASE" -H "Content-Type: text/xml" --data-binary '<?xml version="1.0" encoding="UTF-8"?>
<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">
  <soap:Body>
    <RegistrarClasificacionRequest xmlns="urn:library:clasificacion:1.0">
      <clasificador_email>prueba@example.com</clasificador_email>
      <referencia_libro>000-no-existe</referencia_libro>
      <referencia_concepto>Normalizacion</referencia_concepto>
      <modelo_servicio>IaaS</modelo_servicio>
    </RegistrarClasificacionRequest>
  </soap:Body>
</soap:Envelope>' -w '\nHTTP=%{http_code}\n'
```

**Resultado esperado:** HTTP 404, categoría `CLIENTE`, código
`libro_inexistente`.

**Salida de referencia (verificada):**
```xml
<soap:Envelope xmlns:clv="urn:library:clasificacion:1.0" xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/"><soap:Header/><soap:Body><soap:Fault><faultcode>soap:Client</faultcode><faultstring>No existe un libro con ISBN '000-no-existe'.</faultstring><detail><clv:ErrorDetalle><clv:categoria>CLIENTE</clv:categoria><clv:codigo>libro_inexistente</clv:codigo><clv:mensaje>No existe un libro con ISBN '000-no-existe'.</clv:mensaje></clv:ErrorDetalle></detail></soap:Fault></soap:Body></soap:Envelope>
HTTP=404
```

| Resultado obtenido | Estado | Conclusión |
|---|---|---|
| | | |

---

### N06 — Usuario/clasificador no autorizado o vacío

**Objetivo:** verificar que una petición sin identidad de clasificador
se rechaza en vez de ejecutarse con un usuario implícito.

**Alcance real de esta prueba (léelo antes de ejecutar):** el módulo
**no implementa autenticación/autorización** para las tres operaciones
base — `clasificador_email` es un dato de identidad, no una credencial
verificada; cualquier correo con formato válido es aceptado y
auto-registrado en `clasificadores` en el primer contacto (ver
`fn_get_or_create_clasificador`, `soap_module.sql`). La autenticación
real (WS-Security usuario/contraseña) está fuera del alcance del
ejercicio guiado y se implementa por separado sobre
`ObtenerEstadisticasPorModelo` (Tarea 1 del trabajo en casa). Por eso
este caso se acota a lo que **sí** está implementado y es verificable
hoy: rechazar `clasificador_email` ausente o vacío. Si tu rúbrica exige
además una prueba de autorización real, ejecútala contra
`ObtenerEstadisticasPorModelo` una vez implementada la Tarea 1, no
contra estas tres operaciones.

**Pasos:**
1. Enviar cualquiera de las tres operaciones con
   `<clasificador_email></clasificador_email>` vacío.
2. Repetir omitiendo la etiqueta por completo.
3. Confirmar en ambos casos HTTP 400, `codigo=campo_obligatorio`.

**Entrada (email vacío):**
```bash
curl -sS -X POST "$BASE" -H "Content-Type: text/xml" --data-binary '<?xml version="1.0" encoding="UTF-8"?>
<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">
  <soap:Body>
    <ObtenerProgresoUsuarioRequest xmlns="urn:library:clasificacion:1.0">
      <clasificador_email></clasificador_email>
    </ObtenerProgresoUsuarioRequest>
  </soap:Body>
</soap:Envelope>' -w '\nHTTP=%{http_code}\n'
```

**Entrada (email ausente):**
```bash
curl -sS -X POST "$BASE" -H "Content-Type: text/xml" --data-binary '<?xml version="1.0" encoding="UTF-8"?>
<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">
  <soap:Body>
    <RegistrarClasificacionRequest xmlns="urn:library:clasificacion:1.0">
      <referencia_libro>978-0000000001</referencia_libro>
      <referencia_concepto>ConceptoA</referencia_concepto>
      <modelo_servicio>IaaS</modelo_servicio>
    </RegistrarClasificacionRequest>
  </soap:Body>
</soap:Envelope>' -w '\nHTTP=%{http_code}\n'
```

**Resultado esperado:** HTTP 400 en los dos casos, categoría
`VALIDACION`, código `campo_obligatorio`, sin ejecutar ninguna
operación de negocio.

**Salida de referencia (verificada, ambos casos):**
```xml
<soap:Envelope xmlns:clv="urn:library:clasificacion:1.0" xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/"><soap:Header/><soap:Body><soap:Fault><faultcode>soap:Client.Validacion</faultcode><faultstring>Falta el campo obligatorio 'clasificador_email'.</faultstring><detail><clv:ErrorDetalle><clv:categoria>VALIDACION</clv:categoria><clv:codigo>campo_obligatorio</clv:codigo><clv:mensaje>Falta el campo obligatorio 'clasificador_email'.</clv:mensaje></clv:ErrorDetalle></detail></soap:Fault></soap:Body></soap:Envelope>
HTTP=400
```

| Resultado obtenido | Estado | Conclusión |
|---|---|---|
| | | |

---

### N07 — Caída de conexión a PostgreSQL

**Objetivo:** verificar que una falla real de PostgreSQL produce un
`SOAP Fault` de servidor limpio para el cliente, mientras el detalle
técnico (host, puerto, motivo de la falla) queda **solo** en el log del
servicio.

**Pasos:**
1. Con el servicio corriendo y funcionando normalmente, detener
   PostgreSQL (`podman stop <contenedor>`, `systemctl stop postgresql`,
   o equivalente).
2. Enviar cualquier operación (por ejemplo `ObtenerProgresoUsuario`).
3. Confirmar HTTP 500, `faultcode=soap:Server`, mensaje genérico
   ("No hay conexion con la base de datos." o "Error interno del
   servicio.", según en qué punto falle la conexión).
4. Revisar el log del proceso Flask: ahí sí debe aparecer el motivo
   técnico completo (host/puerto/excepción), nunca en la respuesta al
   cliente.
5. Reiniciar PostgreSQL para dejar el entorno operativo otra vez.

**Entrada:**
```bash
curl -sS -X POST "$BASE" -H "Content-Type: text/xml" --data-binary '<?xml version="1.0" encoding="UTF-8"?>
<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">
  <soap:Body>
    <ObtenerProgresoUsuarioRequest xmlns="urn:library:clasificacion:1.0">
      <clasificador_email>prueba@example.com</clasificador_email>
    </ObtenerProgresoUsuarioRequest>
  </soap:Body>
</soap:Envelope>' -w '\nHTTP=%{http_code}\n'
```

**Resultado esperado:** HTTP 500, categoría `SERVIDOR`, mensaje
genérico sin credenciales/host/ruta/SQL; el log del proceso contiene el
detalle completo.

**Salida de referencia — respuesta al cliente (verificada, pool ya
agotado en conexiones muertas: cae en el manejador genérico):**
```xml
<soap:Envelope xmlns:clv="urn:library:clasificacion:1.0" xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/"><soap:Header/><soap:Body><soap:Fault><faultcode>soap:Server</faultcode><faultstring>Error interno del servicio.</faultstring><detail><clv:ErrorDetalle><clv:categoria>SERVIDOR</clv:categoria><clv:codigo>error_interno</clv:codigo><clv:mensaje>Error interno del servicio.</clv:mensaje></clv:ErrorDetalle></detail></soap:Fault></soap:Body></soap:Envelope>
HTTP=500
```

**Salida de referencia — respuesta al cliente (verificada, proceso
recién iniciado con PostgreSQL ya caído desde el arranque: cae en el
manejador explícito `DatabaseUnavailable`):**
```xml
<soap:Envelope xmlns:clv="urn:library:clasificacion:1.0" xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/"><soap:Header/><soap:Body><soap:Fault><faultcode>soap:Server</faultcode><faultstring>No hay conexion con la base de datos.</faultstring><detail><clv:ErrorDetalle><clv:categoria>SERVIDOR</clv:categoria><clv:codigo>base_datos_no_disponible</clv:codigo><clv:mensaje>No hay conexion con la base de datos.</clv:mensaje></clv:ErrorDetalle></detail></soap:Fault></soap:Body></soap:Envelope>
HTTP=500
```

**Salida de referencia — SOLO en el log del servidor, nunca en la
respuesta anterior (verificada):**
```
2026-09-02 20:13:19,041 ERROR   PostgreSQL no disponible: connection to server at "localhost" (127.0.0.1), port 15432 failed: Connection refused
	Is the server running on that host and accepting TCP/IP connections?
```

**Evidencia a capturar:** las dos respuestas (cliente y log) una junto a
la otra, para dejar explícito qué ve el cliente y qué se queda en el
servidor.

| Resultado obtenido | Estado | Conclusión |
|---|---|---|
| | | |

---

## 3. Tabla resumen

| ID | Prueba | Resultado esperado | Resultado obtenido | Estado |
|---|---|---|---|---|
| P01 | Obtener conceptos pendientes | Lista válida | | |
| P02 | Registrar IaaS/PaaS/SaaS/FaaS | Registro exitoso (×4) | | |
| P03 | Obtener progreso de usuario | Totales exactos | | |
| P04 | Limitar conceptos pendientes (límite=5) | Máximo 5 elementos | | |
| N01 | Repetir clasificación | SOAP Fault 409 | | |
| N02 | Concepto inexistente | SOAP Fault 404 | | |
| N03 | Modelo inválido | SOAP Fault 400 | | |
| N04 | Enviar XML SOAP mal formado | SOAP Fault 400, sin SQL | | |
| N05 | Referencia de libro inexistente | SOAP Fault 404 | | |
| N06 | Usuario/clasificador vacío | SOAP Fault 400 | | |
| N07 | Caída de conexión a PostgreSQL | SOAP Fault 500, detalle solo en log | | |

---

## 4. Verificación final de persistencia (punto 16 del ejercicio guiado)

Tras correr P01–P04, confirma en PostgreSQL:

```sql
SET search_path TO library, public;

-- Clasificaciones registradas por libro/concepto/modelo
SELECT b.isbn, k.name AS concepto, cc.modelo_cloud, cc.fecha_clasificacion
  FROM clasificaciones_cloud cc
  JOIN books b ON b.isbn = cc.libro_isbn
  JOIN concepts k ON k.id = cc.concepto_id
 ORDER BY cc.fecha_clasificacion DESC;

-- Clientes de escritorio atendidos (si se probó con el header ClienteInfo)
SELECT tipo_cliente, identificador, peticiones_atendidas, ultima_peticion_en
  FROM clientes_servidos
 ORDER BY ultima_peticion_en DESC;
```

Adjunta ambas salidas como evidencia de que el módulo SOAP escribió en
sus propias tablas sin tocar el esquema del monolito.
