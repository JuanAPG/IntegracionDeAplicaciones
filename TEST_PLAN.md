# Plan de pruebas — Librería en Línea

**Proyecto:** Integración de Aplicaciones · Librería en línea
**Sistema bajo prueba:** `apps/web_monolito` sobre PostgreSQL 16, esquema `library`
**Casos de prueba:** `CASOS_DE_PRUEBA.txt` (15 casos, ejecución manual)

---

## 1. Objetivo y enfoque

Verificar que la aplicación cumple sus requisitos funcionales y no funcionales **ejecutándola**,
no leyendo su código. La distinción importa: los tres defectos más difíciles de este proyecto
—una redirección que perdía el prefijo de montaje, un mensaje que se consume en un salto
intermedio y un identificador no numérico que llega hasta PostgreSQL— son invisibles en revisión
de código y solo aparecen recorriendo el sistema completo.

Cada caso comprueba el resultado en **tres planos a la vez**:

| Plano | Qué se observa | Herramienta |
|---|---|---|
| **a. Interfaz** | La respuesta HTTP y el HTML que ve el usuario | Navegador, `curl` |
| **b. Datos** | El estado real de las tablas después de la operación | `psql` |
| **c. Motor** | Qué ocurre si alguien intenta lo mismo **saltándose la aplicación** | `psql` |

El plano (c) es deliberado y es lo que separa este plan de una lista de clics. Una regla que solo
vive en el controlador no es una regla, es una costumbre: si la aplicación impide crear un segundo
administrador pero un `INSERT` directo lo consigue, el requisito F8 **no está cumplido**. Siete de
los quince casos atacan el sistema por esa vía.

---

## 2. Alcance

### Incluido

- Autenticación, autorización y gestión de sesión.
- Catálogo: búsqueda, filtros combinados, ordenamiento y paginación.
- CRUD completo de las siete entidades: libros, autores, géneros, conceptos, formatos,
  categorías y usuarios.
- Las tres relaciones multivaluadas y la dependencia funcional sobre clave compuesta.
- Restricciones declarativas del motor: `UNIQUE`, `CHECK`, claves foráneas, índices únicos
  parciales, tipo `ENUM` y disparadores.
- Validación en servidor de campos y de archivos subidos.
- Parametrización de consultas frente a caracteres especiales y a cargas de inyección.
- Despliegue tras proxy inverso y comportamiento del prefijo de montaje.
- Navegación, funcionamiento sin JavaScript, accesibilidad básica y responsividad.

### Excluido, y por qué

| Fuera de alcance | Motivo |
|---|---|
| CSRF, límite de intentos de login, cabeceras de seguridad, sesiones en BD | No están implementados. Son carencias conocidas y declaradas (`apps/SEGURIDAD.txt`), no defectos que estas pruebas puedan descubrir. **Probar lo que no existe no aporta información.** |
| Carga y concurrencia | La regla del administrador único se verifica por construcción —el índice parcial la hace imposible de violar— y no lanzando peticiones simultáneas. |
| Accesibilidad automatizada (axe-core, WCAG completo) | Se cubre por inspección manual en TC-15. Una auditoría formal excede el alcance de la práctica. |
| Escena 3D de Spline | Es decorativa y su degradación es visual; se comprueba solo que degrada con elegancia (TC-15, paso 8). |
| Servicios SOAP/REST | No existen por decisión de arquitectura. Los XML de `apps/services/soap/` son diseño del contrato de datos, no un servicio en ejecución. |

---

## 3. Entorno de pruebas

| Componente | Configuración |
|---|---|
| Aplicación | Node.js ≥ 18, Express 4, EJS. `BASE_PATH=/library`, puerto 3000 |
| Base de datos | PostgreSQL 16, base `library_db`, esquema `library`, rol `library_user` |
| Instalación | `db/00_create_database.sql` como superusuario, después `npm run db:setup -- --reset` |
| Proxy inverso | Nginx en el puerto 80 hacia `127.0.0.1:3000` (solo TC-14) |
| Navegador | Cualquiera con herramientas de desarrollo; se usan F12 → Consola, Red y modo dispositivo |
| Consola SQL | `psql` conectada como `library_user`, con `SET search_path TO library, public` |

**Línea base de datos.** Toda ejecución parte de una base recién sembrada. El instalador debe
imprimir exactamente:

```
formats=30 categories=30 genres=30 authors=30 concepts=30 books=30 users=30
book_authors=37 book_genres=50 book_concepts=49 book_images=36
```

Las cuatro tablas de unión llevan más de 30 filas a propósito. Con exactamente 30 pares y 30
libros, cada libro tendría como máximo un autor y un género, y el conjunto de datos dejaría de
demostrar precisamente lo que justifica el diseño en 4FN.

**Cuentas.** `admin@library.local / Admin123!`, `laura.mendez@example.com / Demo123!` y
`maria.luna@example.com / Demo123!` (desactivada a propósito, para poder probar el rechazo).
Son públicas por diseño y deben eliminarse antes de cualquier despliegue real.

---

## 4. Cobertura exigida

| Requisito del enunciado | Casos que lo cubren |
|---|---|
| Funcionales de **login** y **logout** | TC-01, TC-02 |
| Funcionales de **búsqueda** | TC-04 |
| **Cada CRUD** | TC-05 (libros), TC-08 (formatos, categorías, géneros, autores, conceptos), TC-09 (usuarios y perfil) |
| **Autorización**: visitante, usuario registrado, administrador | TC-03 |
| **Negativas de base de datos y restricciones** | TC-10, y las partes negativas de TC-08 y TC-09 |
| **Validación de campos y archivos** | TC-11 (campos), TC-12 (archivos) |
| Relaciones **libro–autor** y **libro–género** | TC-06 |
| Relación **libro–concepto** | TC-07 |
| Creación de un **segundo administrador** | TC-09 |
| **SQL con caracteres especiales** (parametrización) | TC-13 |
| Despliegue mediante **proxy inverso** | TC-14 |
| **Navegación y usabilidad** | TC-15 |

### Trazabilidad a los requisitos del sistema

| Req. | Descripción | Casos |
|---|---|---|
| F1 | Registro e inicio de sesión | TC-01, TC-02, TC-11 |
| F2 | Catálogo con búsqueda, filtros y paginación | TC-04, TC-13 |
| F3 | Ficha con autores, géneros, conceptos e imágenes | TC-06, TC-07, TC-12 |
| F4 | CRUD de libros con sus relaciones | TC-05, TC-06, TC-11 |
| F5 | CRUD de los cinco catálogos | TC-08 |
| F6 | Gestión de usuarios y perfil | TC-02, TC-09 |
| F7 | Carga y borrado de imágenes | TC-12 |
| F8 | Un único administrador | TC-03, TC-09 |
| NF1 | Datos en 4FN | TC-06, TC-07 |
| NF2 | Integridad garantizada por el motor | TC-08, TC-09, TC-10, TC-11, TC-13 |
| NF3 | Instalación repetible | Preparación del entorno (`--reset` y recarga del seed) |
| NF5 | Renderizado en servidor, usable sin JavaScript | TC-15 |
| NF6 | Ruta de montaje configurable | TC-01, TC-14 |

**NF4** (sin dependencias de compilación) no se prueba en ejecución: se verifica por inspección
de `package.json`, que no declara bundler ni paso de build.

---

## 5. Estrategia por tipo de prueba

### 5.1 Funcionales
Recorrido completo de cada funcionalidad por la interfaz, con verificación en base de datos del
efecto real. No basta con que la pantalla diga «guardado»: se comprueba la fila.

### 5.2 De autorización
Un único caso (TC-03) recorre **la misma lista de rutas con los tres perfiles**, en una matriz de
27 combinaciones. Esta forma es más rigurosa que tres casos separados: obliga a comparar y hace
evidente cualquier ruta que un rol alcance y no debiera.

Se añade una prueba que **no pasa por la interfaz**: un `POST` de borrado lanzado desde la consola
del navegador con la sesión de un usuario sin privilegios. Es la comprobación de que la guarda
está en el router y no dentro de cada controlador.

### 5.3 Negativas de base de datos
Nueve sentencias SQL que **deben fallar**, cada una con su código esperado (`23505`, `23514`,
`23503`, `22P02`). Se ejecutan como `library_user`, es decir, con los mismos privilegios que
tendría un atacante que lograra ejecutar SQL a través de la aplicación.

Las dos más ilustrativas son `ux_users_single_admin` y `ux_book_images_one_cover`: son
restricciones **condicionales** que un `UNIQUE` normal no puede expresar y que PostgreSQL resuelve
con índices únicos parciales.

### 5.4 De validación
La validación del navegador se **desactiva a propósito** (`setAttribute('novalidate','')`) antes
de enviar los formularios. Es la única forma de probar lo que hace el servidor cuando el cliente
ya no protege, que es exactamente el escenario de un atacante con `curl`.

En archivos subidos, la comprobación decisiva no es el mensaje de error sino el **listado del
directorio** `src/public/uploads/`: ese directorio se sirve como estático, así que un archivo
escrito ahí es alcanzable por URL. Verificar solo el mensaje daría un falso positivo si el archivo
se hubiera guardado y rechazado después.

### 5.5 De parametrización
Se separan dos cosas que suelen confundirse:

- **(a)** que una carga de inyección no ejecute nada;
- **(b)** que un dato **legítimo** con apóstrofos, acentos, eñes o porcentajes se guarde y se
  busque correctamente.

Un sistema que escapa a lo bruto pasa (a) y falla (b). Uno bien parametrizado pasa los dos. Por eso
TC-13 crea un autor llamado `Brian O'Really` y un género `Ciencia ficción (100% clásica)` además de
lanzar las cargas clásicas.

Atención especial al `ORDER BY`: es un identificador, no admite parámetro `$1`, y por tanto la
parametrización **no lo protege**. Se resuelve con lista blanca cerrada. Es la grieta habitual en
aplicaciones que «ya usan consultas parametrizadas».

### 5.6 De despliegue
Comparación de las mismas rutas por el puerto directo y a través del proxy, más la comprobación de
que `client_max_body_size` supera `UPLOAD_MAX_MB`. Si no lo supera, el usuario recibe un `413` del
proxy en lugar del mensaje de validación de la aplicación.

### 5.7 De usabilidad
El punto crítico es el paso 3 de TC-15: **recorrer la aplicación entera con JavaScript
desactivado**. Si algo deja de funcionar, el requisito NF5 no se cumple, porque todo el HTML debe
llegar renderizado desde el servidor y cada acción debe ser un formulario.

---

## 6. Criterios de entrada y de salida

### Entrada
1. La aplicación arranca y responde `200` en `/library`.
2. El instalador imprime la línea base de 30 filas por tabla.
3. Existen las siete vistas, las nueve funciones y los seis disparadores:
   ```sql
   SELECT table_name FROM information_schema.views WHERE table_schema='library';
   SELECT proname FROM pg_proc WHERE pronamespace='library'::regnamespace;
   SELECT tgname FROM pg_trigger t JOIN pg_class c ON c.oid=t.tgrelid
    WHERE NOT tgisinternal AND c.relnamespace='library'::regnamespace;
   ```
4. Las cuentas de prueba existen y `maria.luna@example.com` está desactivada.

### Salida
- **Aprobado:** los 15 casos en estado APROBADA.
- **Aprobado con reservas:** falla únicamente el caso de prioridad Media (TC-15) y ninguno de
  prioridad Alta o Máxima, y cada fallo queda registrado como defecto con su reproducción.
- **Rechazado:** falla cualquier caso de prioridad **Máxima** (TC-07, TC-13) o dos o más de
  prioridad **Alta** (TC-01 a TC-06, TC-08 a TC-12, TC-14).

Reparto de prioridades: **Máxima** 2 casos · **Alta** 12 casos · **Media** 1 caso.

---

## 7. Hallazgos conocidos antes de empezar

Están documentados y **no deben contarse como fallos** de los casos donde aparecen. Si **no** los
observa, compruebe que está probando la versión correcta del código.

| Id | Descripción | Dónde se ve | Corrección pendiente |
|---|---|---|---|
| **H1** | El aviso «Sección exclusiva del administrador» se pierde cuando la redirección encadena más de un salto. `flash.js` vacía los mensajes en toda petición, también en las que responden `302` sin renderizar. La protección funciona; el aviso no llega. | TC-03 | Conservar los mensajes cuando la respuesta no renderiza una vista |
| **H2** | Un identificador no numérico en la ficha de libro devuelve `500` en vez de `404`. El valor llega a PostgreSQL, que lo rechaza con `22P02`, y el manejador general no traduce ese código. | `/library/catalog/abc` | Validar el id en el controlador, o añadir `22P02` al `switch` de `errors.js` |
| **H3** | Los XML de `apps/services/soap/` describen el catálogo anterior de 13 libros y no se regeneraron tras pasar al seed de 30. Siguen siendo documentos válidos y bien formados, pero ya no son un espejo de la base. | Inspección de `library.xml` | Regenerar el XML desde la base, o declararlo explícitamente como instantánea |

---

## 8. Gestión de la evidencia

Una captura vale como evidencia cuando muestra **el efecto**, no solo la intención. Criterios:

- Incluya siempre la **URL** en la barra de direcciones cuando la prueba dependa de la ruta.
- Para los casos que tocan la base, la captura fuerte es la que junta **la pantalla y la consola
  `psql`**: el mensaje de la aplicación al lado del error del motor demuestra la doble línea de
  defensa; el mensaje solo, no.
- Nunca capture una terminal con la cadena de conexión o una contraseña visible. Una captura
  publica la credencial igual que un archivo de texto.
- Nombre los archivos `TC-NN_descripcion.png` para que la trazabilidad sea evidente.

**Las tres capturas más representativas del conjunto**, si solo puede incluir unas pocas:

1. **TC-07** — dos fichas de libro mostrando el *mismo* concepto con definiciones distintas.
   Es la prueba del modelo de datos: demuestra que la definición pertenece al par
   *(libro, concepto)* y no al concepto. Si esa afirmación fuera falsa, la tabla `book_concepts`
   sobraría y el esquema estaría mal normalizado.
2. **TC-09** — el mensaje «Ya existe un administrador» junto al error `ux_users_single_admin` en
   `psql`. Demuestra que la regla vive en el motor y no en el controlador, donde tendría una
   condición de carrera explotable.
3. **TC-13** — la ficha del libro `El "libro" de Ñoño — 50% teoría` con su autor `Brian O'Really`.
   Demuestra que la parametrización trata los caracteres especiales como datos y no escapa a lo
   bruto.

---

## 9. Registro de defectos

Cada fallo se anota con: caso de origen, pasos mínimos de reproducción, resultado esperado,
resultado obtenido, y evidencia. Clasificación:

| Severidad | Criterio |
|---|---|
| **Crítica** | Pérdida o corrupción de datos, acceso no autorizado, o caída del servicio |
| **Alta** | Una funcionalidad del alcance no se puede completar |
| **Media** | La funcionalidad se completa pero con comportamiento incorrecto o confuso |
| **Baja** | Cosmético, o afecta solo a la presentación |

H1 y H2 son de severidad **Media**: ninguno compromete la seguridad ni la integridad de los datos,
pero ambos degradan la experiencia.

---

## 10. Automatización

Estos 15 casos son de **ejecución manual**, y esa es su función: producen evidencia visual y
obligan a mirar el sistema.

No sustituyen a una suite automatizada, que es lo que protege contra regresiones. La recomendación
priorizada, si el proyecto continúa:

1. **Integración HTTP** (`supertest`): el barrido de rutas de TC-03 y el flujo de sesión de TC-01,
   automatizados. Es lo que más defectos atrapa por línea escrita.
2. **Unitarias de modelo** contra base efímera: filtros, paginación y las funciones almacenadas.
3. **Unitarias puras**: `password.validate` y los normalizadores de `core/utils/validate.js`.
4. **Verificación del seed en CI**: recargarlo dos veces y comprobar que no duplica una sola fila.

---

## 11. Documentos relacionados

| Documento | Contenido |
|---|---|
| `CASOS_DE_PRUEBA.txt` | Los 15 casos con pasos, resultado esperado y hojas de registro |
| `apps/SEGURIDAD.txt` | Las diez prácticas de seguridad, con estado y riesgo residual |
| `db/03_all_quieries_before_stored_procedures.sql` | Inventario de las consultas que la aplicación ejecuta |
| `apps/web_monolito/README.md` | Instalación, despliegue y configuración de Nginx |
