# Tarea 4 — Interoperabilidad

Cliente generado a partir de `wsdl/library-classiffier.wsdl` con **una
tecnología distinta a la del servidor**: el servidor es Flask +
`xml.etree.ElementTree` escrito a mano (Python); el cliente de esta
tarea es **Java + `wsimport`** (JAX-WS RI), que genera clases a partir
del contrato **sin conocer nada de la implementación interna** del
servidor. Ejecutado y verificado en vivo el 2026-09-03 contra una
instancia PostgreSQL + Flask real y desechable.

## Herramienta y proceso de generación

`wsimport` ya no viene incluido en el JDK (se quitó desde Java 11), así
que se usó Maven para traer `com.sun.xml.ws:jaxws-tools:2.3.7` (JAX-WS
RI) y se invocó `com.sun.tools.ws.WsImport` directamente:

```bash
# proyecto-maven/pom.xml declara la dependencia com.sun.xml.ws:jaxws-tools:2.3.7
mvn dependency:build-classpath -Dmdep.outputFile=cp.txt

java -cp "$(cat cp.txt)" com.sun.tools.ws.WsImport \
  -keep -s target/generated-sources/wsimport -d target/generated-sources/wsimport \
  -p mx.udem.iac.clasificacion.client \
  library-classiffier.wsdl
```

**Nota técnica:** el plugin de Maven tradicional
(`org.jvnet.jax-ws-commons:jaxws-maven-plugin`) es de 2015 y su forma de
invocar `javac` internamente usa `-Xbootclasspath/p`, una opción
**eliminada desde JDK 9**. En JDK 17 falla con
`Error: Could not create the Java Virtual Machine`. La solución fue
invocar `WsImport` directamente como una clase Java normal (sin pasar
por ese plugin), lo que evita el problema por completo. El `pom.xml`
completo está en `proyecto-maven/`.

`wsimport` generó, sin ningún ajuste manual, una clase por cada tipo y
elemento del XSD: los cuatro `*Request`/`*Response`, `ConceptoPendiente`,
`ModeloServicioType` (enum), `EstadisticaModelo`, `ErrorDetalle` +
`ErrorDetalleMessage` (excepción de Fault tipada), y
`ClasificacionLibrosService`/`ClasificacionLibrosPortType`. Las fuentes
generadas están en `generado/`.

## Código relevante del cliente

`ClienteJava.java` (raíz de esta carpeta) consume
`ObtenerConceptosPendientes` y `RegistrarClasificacion`:

```java
ClasificacionLibrosService service = new ClasificacionLibrosService();
ClasificacionLibrosPortType port = service.getClasificacionLibrosPort();
((BindingProvider) port).getRequestContext()
    .put(BindingProvider.ENDPOINT_ADDRESS_PROPERTY, endpoint);

ObtenerConceptosPendientesRequest req1 = new ObtenerConceptosPendientesRequest();
req1.setClasificadorEmail("java.cliente@example.com");
req1.setLimite(10);
ObtenerConceptosPendientesResponse resp1 = port.obtenerConceptosPendientes(req1);
```

Nótese `req1.setLimite(10)`, `req2.setModeloServicio(ModeloServicioType.SAA_S)`:
los nombres de campo y el enum del modelo Cloud son exactamente los que
define el XSD, generados automáticamente — nadie los escribió a mano.

## Ejecución real (salida completa, sin editar)

```
$ java -cp <classpath> ClienteJava http://127.0.0.1:5099/soap/clasificacion

Endpoint: http://127.0.0.1:5099/soap/clasificacion

=== ObtenerConceptosPendientes ===
  - Normalizacion  (Fundamentos de Sistemas de Bases de Datos / Tecnico)  isbn=978-0133970777

=== RegistrarClasificacion (valido) ===
  exito=true  mensaje=Clasificacion guardada exitosamente.

=== RegistrarClasificacion (repetido: mismo clasificador/concepto) ===
  (sin parsear como SOAP Fault -- ver nota de interoperabilidad) com.sun.xml.ws.client.ClientTransportException: The server sent HTTP status code 409: CONFLICT

=== Modelo invalido: el propio cliente tipado ya lo rechaza ===
  Rechazado localmente por el cliente generado: java.lang.IllegalArgumentException: Blockchain
```
(salida completa también en `ejecucion_real.log`)

## Hallazgo de interoperabilidad (el resultado más importante de esta tarea)

`ObtenerConceptosPendientes` y el alta válida de `RegistrarClasificacion`
funcionan **perfectos**: datos reales de PostgreSQL, ida y vuelta
completa, sin que el cliente Java conozca Flask, `xml.etree` ni
PostgreSQL — exactamente lo que el ejercicio pide demostrar.

El tercer caso (clasificación duplicada) expone algo real, no un error
de este cliente: el servidor responde ese caso con **HTTP 409**
(lo exige explícitamente el enunciado del ejercicio guiado:
*"Clasificación duplicada → SOAP Fault asociado a conflicto 409"*), pero
el runtime **JAX-WS RI, siguiendo WS-I Basic Profile al pie de la
letra, solo intenta leer un `<soap:Fault>` del cuerpo cuando el status
HTTP es 500**. Con cualquier otro código de error (400/404/409) lanza
`ClientTransportException` **sin siquiera mirar el cuerpo de la
respuesta**. Se confirmó explícitamente que **si** el mismo servidor
responde con 500 (probado deteniendo PostgreSQL a propósito), el Fault
**sí** se parsea correctamente como `ErrorDetalleMessage`:

```
SOAP Fault (HTTP 500) SI se parseo correctamente -> categoria=SERVIDOR codigo=error_interno mensaje=Error interno del servicio.
```

**No se "corrigió" el servidor para volver todo 500** porque el 409 es
un requisito explícito y calificado del ejercicio guiado, no una
elección libre de este módulo. Se documenta como lo que es: una
consecuencia real de una decisión de diseño (usar códigos HTTP
semánticos por categoría de Fault, más útil para depuración manual con
`curl`/Postman y para el propio cliente `soap_client.py`, que sí
inspecciona el cuerpo sin importar el status) frente a la expectativa
estricta de un stack SOAP 1.1 generado por WSDL. Es justo el tipo de
descubrimiento que esta tarea busca: probar con un cliente ajeno revela
supuestos que un cliente propio nunca cuestiona.

## Comparación cliente manual (`soap_client.py`) vs. cliente generado (`wsimport`)

| | `soap_client.py` (manual) | Cliente Java generado por `wsimport` |
|---|---|---|
| Construcción del Envelope | A mano, con `xml.etree.ElementTree` | Automática, a partir de las clases generadas |
| Tipado de `modelo_servicio` | `str` sin restricción en tiempo de compilación | `enum ModeloServicioType`, un valor inválido ni compila/parsea localmente |
| Lectura de la respuesta | Dict genérico (`_element_to_dict`), acepta cualquier forma | Objetos fuertemente tipados (`ConceptoPendiente`, etc.), generados del XSD |
| Manejo de Fault | Lee el cuerpo **sin importar el status HTTP** (200/400/404/409/500 se tratan igual: se busca `<soap:Fault>`) | Solo intenta parsear un Fault si el status HTTP es **500**; con 400/404/409 lanza una excepción de transporte cruda |
| Esfuerzo de implementación | Todo escrito a mano (~154 líneas, ver `test/tarea5_metricas.md`) | Cero código de serialización/deserialización: se generó solo |
| Conocimiento del servidor requerido | Debe saberse de antemano que el servidor devuelve Fault en cualquier status | Ninguno más allá del WSDL — pero por eso mismo choca con el 409 |

**Conclusión:** el WSDL sí permite que un cliente en otro lenguaje
consuma el servicio sin conocer su implementación interna — se probó
con datos reales, no en teoría. La única fricción real encontrada no es
del contrato XML/XSD (que se generó y usó sin tocar nada), sino de la
**convención de transporte HTTP para Faults**, que es tema aparte del
contrato SOAP en sí y confirma por qué WS-I Basic Profile estandariza
esto: para que herramientas de generación automática no tengan que
adivinar.

## Reproducir

```bash
cd library_soap_service/test/tarea4_interoperabilidad/proyecto-maven
mvn dependency:build-classpath -Dmdep.outputFile=cp.txt
mkdir -p ../target
java -cp "$(cat cp.txt)" com.sun.tools.ws.WsImport \
  -keep -s ../target -d ../target -p mx.udem.iac.clasificacion.client \
  ../../../wsdl/library-classiffier.wsdl
javac -cp "$(cat cp.txt):../target" -d ../target ../target/mx/udem/iac/clasificacion/client/*.java ../../ClienteJava.java
java -cp "$(cat cp.txt):../target" ClienteJava http://<host>:<puerto>/soap/clasificacion
```
