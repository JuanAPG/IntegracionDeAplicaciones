# Evidencia de persistencia e integración

Corrida real capturada el **2026-09-02** contra una instancia PostgreSQL
16 + Flask desechable (no producción), con un catálogo de 5 libros en 4
categorías distintas y 5 conceptos (uno de ellos, "Principios SOLID",
compartido por dos libros — a propósito, para demostrar que la
restricción de duplicado es por concepto, no por par libro-concepto).
Corresponde al punto 16 del ejercicio guiado ("Verificar persistencia e
integración").

## Qué se hizo

1. Se aplicó el esquema del monolito (`db/01_schema.sql`) y el del
   módulo SOAP (`sql/soap_module.sql`) sobre una base nueva.
2. Se sembraron 5 libros / 4 categorías / 5 conceptos / 6 pares
   (libro, concepto) pendientes (ver `seed` reproducible en
   `test/plan_pruebas.md`, sección 0.2, con nombres de catálogo
   ligeramente distintos — aquí se usó un catálogo más amplio a
   propósito de "varios libros y categorías").
3. Se ejecutaron las tres operaciones del contrato **con el mismo
   cliente Python que usa la GUI** (`apps/services/escritorio/soap_client.py`,
   sin atajos ni mocks) simulando **dos clasificadores distintos**
   (`ana.torres@example.com`, `carlos.mendez@example.com`) y **dos tipos
   de cliente de escritorio distintos** vía el encabezado SOAP opcional
   `ClienteInfo` (`Python-Tkinter-Clasificador` / `Java-Swing-Clasificador`),
   para poder verificar que `clientes_servidos` distingue tipo de
   cliente y cuenta peticiones correctamente.
4. Se provocaron intencionalmente dos `SOAP Fault` (clasificación
   duplicada y modelo inválido).
5. Se consultó PostgreSQL directamente para confirmar que todo quedó
   escrito en las tablas propias del módulo, sin tocar el esquema del
   monolito.

## Índice de evidencia

### Contrato (WSDL)
El contrato usado en esta corrida es el publicado en
[`../../wsdl/library-classiffier.wsdl`](../../wsdl/library-classiffier.wsdl)
— no se modificó para esta prueba.

### Solicitudes/respuestas XML (`xml/`)
Cada operación tiene su par `*_request.xml` / `*_response.xml`, bytes
crudos tal cual viajaron por HTTP (nada reconstruido a mano después):

| Archivo | Qué demuestra |
|---|---|
| `01_obtener_conceptos_pendientes_*` | Lista real de 6 pares pendientes, de 4 categorías distintas |
| `02a`…`02e_registrar_*` | Alta de 5 clasificaciones reales — IaaS, PaaS, SaaS, FaaS y N/A, sobre 4 libros/categorías |
| `03_obtener_progreso_usuario_*` | Progreso de Ana tras clasificar: `total_clasificados=5`, `total_pendientes=0` |
| `04_soap_fault_clasificacion_duplicada_*` | **SOAP Fault 409**: Ana reintenta "Principios SOLID" desde *el otro libro* que también lo define — la restricción es por concepto, no por par libro-concepto |
| `05_soap_fault_modelo_invalido_*` | **SOAP Fault 400**: modelo `"Blockchain"`, fuera del catálogo `IaaS/PaaS/SaaS/FaaS/N-A` |
| `06a`…`06c_java_*` | Un segundo clasificador (Carlos) con un cliente de tipo distinto (`Java-Swing-Clasificador`): progreso independiente (`1` clasificado, `4` pendientes) |

### Consultas de verificación en PostgreSQL (`postgresql/`)

- **`clasificaciones_cloud.txt`** — 6 filas: título, categoría y
  concepto reales (vía `JOIN` con `books`/`categories`/`concepts` del
  monolito, que el módulo SOAP solo lee), modelo Cloud y clasificador.
  Incluye el caso de "Protocolo TCP/IP" clasificado **dos veces por dos
  clasificadores distintos** (Ana y Carlos) — válido, porque la
  restricción `UNIQUE(clasificador_id, concepto_id)` es por
  clasificador.
- **`clientes_servidos.txt`** — 2 filas, una por tipo de cliente
  simulado, con el conteo real de `peticiones_atendidas`:
  `Python-Tkinter-Clasificador` = 9 (incluye las 2 llamadas que
  terminaron en Fault: el conteo es de *peticiones atendidas*, no solo
  de éxitos) y `Java-Swing-Clasificador` = 3.

### GUI

**No se incluye una captura de pantalla.** Se intentó capturar la
ventana de `Ejercicio1.py` en ejecución, pero el mecanismo disponible
(`screencapture` de macOS) solo pudo capturar la pantalla completa, no
la ventana de la app: el primer intento devolvió el escritorio con
pestañas de navegador y contenido personal ajenos a este ejercicio. Esa
captura se descartó y se borró de inmediato sin guardarla en ningún
lado, para no exponer información que no corresponde a esta evidencia.

En su lugar, la evidencia funcional de la GUI son los propios archivos
de `xml/`: se generaron llamando literalmente al módulo
`apps/services/escritorio/soap_client.py`, el mismo que usa la pestaña
"Clasificación SOAP" de la GUI — son bit a bit las mismas peticiones que
la ventana construye y envía. Si tu rúbrica exige una captura visual,
ábrela tú mismo (`python3 apps/services/escritorio/Ejercicio1.py`),
repite el flujo de este documento (cargar pendientes → seleccionar →
registrar → ver progreso, y al menos un intento duplicado para ver el
`messagebox` de error) y captura solo la ventana con
`Cmd+Shift+4` + barra espaciadora (selector de ventana), no la pantalla
completa.

## Cómo reproducir esta corrida

Ver `test/plan_pruebas.md` para el procedimiento paso a paso genérico.
Esta corrida en particular usó un catálogo más grande a propósito; el
script exacto que la generó (semilla SQL + secuencia de llamadas) puede
reconstruirse siguiendo el orden de la sección "Qué se hizo" arriba.
