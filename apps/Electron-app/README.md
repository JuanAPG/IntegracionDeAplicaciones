# Libreria en Linea — Aplicacion de escritorio (Electron)

Aplicacion de escritorio que muestra el catalogo de libros consumiendo
**exclusivamente XML** del microservicio Flask del proyecto.

Cada libro se presenta con su **ISBN, titulo, autores, ano de publicacion,
generos, precio, existencias, formato, imagenes y los conceptos definidos
por libro** (con su definicion). El catalogo se recorre con **paginacion y
carga por peticion**: cada pagina es una peticion HTTP independiente
(`limit` / `offset`); en ningun momento se descarga el catalogo completo.

La **URL base** y el **endpoint** son configurables desde la propia
aplicacion y se conservan en **localStorage**, de modo que sobreviven al
cierre del programa.

---

## 1. Requisitos

| Requisito | Version | Notas |
|-----------|---------|-------|
| Windows | 11 (x64 o ARM64) | Tambien funciona en macOS ARM y Linux |
| Node.js | 20 LTS o superior | Incluye npm |
| Microservicio | En ejecucion y alcanzable | Por omision `http://34.51.18.197:5001` |

Comprueba que Node.js este instalado abriendo **PowerShell**:

```powershell
node --version
npm --version
```

Si el comando no se reconoce, instala Node.js desde
<https://nodejs.org/en/download> (instalador *Windows Installer .msi*,
version LTS) y **cierra y vuelve a abrir PowerShell** para que el `PATH`
se actualice.

---

## 2. Ejecucion en Windows 11

### Paso 1 — Obtener el codigo

Si el repositorio aun no esta en el equipo:

```powershell
git clone <url-del-repositorio> library
```

### Paso 2 — Situarse en la carpeta de la aplicacion

```powershell
cd library\apps\Electron-app
```

> Las rutas en Windows usan `\`. Si la ruta contiene espacios, enciarrala
> entre comillas: `cd "C:\Users\TuUsuario\library\apps\Electron-app"`.

### Paso 3 — Instalar las dependencias

```powershell
npm install
```

Descarga Electron (~150 MB) en `node_modules`. Solo hace falta la primera
vez. Si npm bloquea el script de instalacion de Electron, autorizalo con:

```powershell
npm approve-scripts electron
npm install
```

### Paso 4 — Iniciar la aplicacion

```powershell
npm start
```

Se abre la ventana **Libreria en Linea** y el catalogo se carga de
inmediato. Para abrir tambien las herramientas de desarrollo:

```powershell
npm run dev
```

---

## 3. Uso

| Accion | Como |
|--------|------|
| Ver la ficha completa de un libro | Clic en su tarjeta (o `Tab` + `Enter`) |
| Cerrar la ficha | Boton `X` o tecla `Esc` |
| Cambiar de pagina | Botones **Anterior** / **Siguiente** |
| Libros por pagina | Selector **Libros por pagina** (3 a 24) |
| Recargar el catalogo | Boton de recarga o `Ctrl + R` |
| Configurar el servicio | Boton **Configuracion** o `Ctrl + ,` |

La ficha de cada libro muestra la galeria de imagenes, la ficha tecnica
(ISBN, ano, precio, existencias, formato y categoria), los autores, los
generos y **cada concepto con su definicion**.

---

## 4. Configuracion del origen de datos

Abre **Configuracion** (`Ctrl + ,`) y ajusta:

- **URL base del microservicio** — protocolo, servidor y puerto.
  Ejemplo: `http://34.51.18.197:5001`
- **Endpoint del catalogo** — ruta que devuelve el XML de libros.
  Ejemplo: `/books`

El dialogo muestra en vivo la peticion resultante, por ejemplo:

```
http://34.51.18.197:5001/books?limit=6&offset=0
```

Pulsa **Guardar y recargar** para aplicarla. La configuracion se guarda en
`localStorage` bajo la clave `library.desktop.serviceConfig` y se restaura
en el siguiente arranque. **Valores de fabrica** repone los datos
originales (hay que guardar para aplicarlos).

Si el microservicio corre en la misma maquina, usa `http://localhost:5001`.

---

## 5. Contrato de datos

La aplicacion espera el XML del catalogo en el espacio de nombres
`urn:library:catalog:1.0`:

```xml
<library xmlns="urn:library:catalog:1.0">
  <books count="6" total="14" limit="6" offset="0">
    <book id="1" isbn="978-0133970777">
      <title>Fundamentos de Sistemas de Bases de Datos</title>
      <publicationYear>2016</publicationYear>
      <price currency="MXN">1250.00</price>
      <stock>12</stock>
      <format ref="4">Pasta dura</format>
      <category ref="5">Academico</category>
      <authors count="2"><author ref="1">Ramez Elmasri</author></authors>
      <genres count="2"><genre ref="1">Bases de datos</genre></genres>
      <concepts count="4">
        <concept ref="1">
          <name>Normalizacion</name>
          <definition>Proceso de descomposicion de relaciones…</definition>
        </concept>
      </concepts>
      <images count="2">
        <image id="9" isCover="true">https://…-L.jpg</image>
      </images>
    </book>
  </books>
</library>
```

Los atributos `total`, `limit` y `offset` de `<books>` alimentan la
paginacion. Si un endpoint alterno no declara `total`, la aplicacion sigue
funcionando y habilita **Siguiente** mientras la pagina llegue completa.

---

## 6. Estructura del proyecto

```
apps/Electron-app/
├── package.json          Dependencias y scripts (start, dev)
├── main.js               Proceso principal: ventana, menu y cliente HTTP
├── preload.js            Puente seguro (contextBridge) con el renderer
└── src/
    ├── index.html        Estructura de la interfaz e iconos SVG
    ├── css/styles.css    Sistema de diseno (tema oscuro, glassmorphism)
    └── js/
        ├── config.js     Configuracion persistida en localStorage
        ├── xml.js        Interpretacion del XML con DOMParser
        ├── ui.js         Capa de presentacion (View)
        └── app.js        Controlador: estado, paginacion y eventos
```

**Solo XML.** El proceso principal descarga el documento con
`Accept: application/xml` y entrega el texto sin interpretar; el renderer
lo convierte a objetos con `DOMParser`. No existe ninguna ruta de codigo
que lea JSON del microservicio.

**Seguridad.** El renderer corre con `contextIsolation: true`,
`nodeIntegration: false` y `sandbox: true`. Toda la red pasa por el proceso
principal, de modo que la politica de contenido declara `connect-src 'none'`.

**Accesibilidad.** Navegacion completa por teclado con foco visible,
objetivos de 44x44 px, contraste de texto >= 4.5:1, dialogos nativos
`<dialog>` (foco atrapado y `Esc`), errores anunciados con `role="alert"`
y respeto por `prefers-reduced-motion` y el modo de alto contraste de
Windows.

---

## 7. Solucion de problemas

| Sintoma | Causa probable | Solucion |
|---------|----------------|----------|
| **No se pudo cargar el catalogo** / *Sin conexion* | El microservicio no responde | Verifica la URL base en Configuracion y que el servicio este activo |
| **Error 404** | El endpoint no existe | Corrige la ruta en Configuracion (suele ser `/books`) |
| **La respuesta no es el XML esperado** | El endpoint no devuelve el catalogo | Apunta al endpoint del catalogo, no a `/docs` ni a `/health` |
| Las portadas no se ven | Sin salida a Internet | Las imagenes son remotas; el resto del catalogo funciona igual |
| `npm start` no responde | Dependencias incompletas | Borra `node_modules` y repite `npm install` |
| `'npm' no se reconoce…` | Node.js no esta en el `PATH` | Reinstala Node.js y reabre PowerShell |

Comprueba el servicio desde PowerShell sin salir de la terminal:

```powershell
curl.exe "http://34.51.18.197:5001/books?limit=1&offset=0"
```

Debe responder un documento XML que empiece con `<?xml version="1.0"…`.
