1. Desarrolla una aplicación web monolítica en Node.js en /apps/web_monolito/  que gestione una
librería en línea mediante acceso directo a PostgreSQL. La solución deberá renderizar HTML del lado del servidor, administrar
usuarios registrados, implementar CRUD del modelo normalizado (en
todas las tablas), manejar imágenes y conservar definiciones de
conceptos asociadas a cada libro.
2. Restricción arquitectónica: no se desarrollarán APIs REST, GraphQL,
SOAP ni otros servicios. No se utilizará JSON o XML como formato de
intercambio de datos. El archivo package.json existe únicamente porque
npm lo requiere para administrar el proyecto Node.js
3. Partiendo la base que todo libro tiene de ISBN, título, autor, año de publicación, género, precio, stock, formato, imágenes y conceptos definidos por libro, identifica dependencias funcionales y multivaluadas. 
4. Un libro puede tener varios autores. 
5. Un libro puede pertenecer a varios géneros. 
6. Un libro puede definir muchos conceptos y un mismo concepto puede aparecer en distintos libros con definiciones diferentes. 
7. Un libro puede tener varias imágenes. 
8. Formato y categoría son catálogos independientes. 
9. Debe existir como máximo un administrador
10. Utiliza la macro-arquitectura monolítica para el desarrollo del sistema
11. Utiliza el patrón de diseño MVC para la UI
12. Utiliza el enfoque de organización de código por módulos
13. Utiliza el esquema de base de datos para postgresql data/schema.sql
14. Crea un archivo READE.md con las instrucciones de despliegue en Linux Centos 10 stream, asumiento que tengo instalado el DBMS de Postgresql con el usuario:library_user password: 777 y base de datps library_db
---

## Requisitos de interfaz de usuario (UI)

15. Rediseña la interfaz con una identidad visual moderna, sin abandonar el
    renderizado del lado del servidor. La capa View sigue siendo EJS: **no** se
    introduce React, Next.js, TypeScript ni un paso de compilacion (bundler).
    Tailwind y shadcn/ui tampoco se instalan; su papel lo cubre una unica hoja
    de estilos propia, `src/public/css/styles.css`, organizada como sistema de
    diseño con variables CSS (tokens).

16. Sistema de diseño, tema oscuro:
    - Tokens en `:root` para superficies, texto, marca, estado, bordes,
      radios, espaciado, sombras, transiciones y tipografia.
    - Paleta: fondo `#070B16`, superficies translucidas, primario violeta
      `#7C3AED`, secundario indigo `#6366F1`, acento cian `#22D3EE`,
      exito `#34D399`, error `#F87171`.
    - Tipografia: `Outfit` para titulos y `Inter` para texto, con familias
      del sistema como respaldo.
    - Estilo glassmorphism: superficies con `backdrop-filter`, borde de
      1 px translucido y brillo superior como fuente de luz.

17. Portada publica con un hero tridimensional interactivo:
    - Escena 3D de **Spline** renderizada en un `<canvas>`.
    - Foco radial (*spotlight*) que sigue al cursor dentro del hero.
    - Tres componentes de referencia escritos originalmente en React
      (`SplineScene`, `Spotlight` y `Card` de shadcn/ui) se portan a
      JavaScript plano y CSS para no romper la restriccion del punto 2:
      `src/public/js/spline-hero.js`, `src/public/js/spotlight.js` y la clase
      `.card` de la hoja de estilos.
    - Unica dependencia nueva: `@splinetool/runtime`, que se publica como
      modulo ESM nativo y se sirve tal cual desde `node_modules` en la ruta
      estatica `/vendor/spline`. No hay bundler, ni `@splinetool/react-spline`,
      ni `framer-motion`.

18. La escena 3D es decorativa y siempre degrada con elegancia: si el
    navegador no soporta WebGL, si la escena falla al cargar o si el usuario
    activo `prefers-reduced-motion`, se muestra un orbe estatico en su lugar.
    El runtime solo se descarga cuando el hero se acerca al viewport
    (`IntersectionObserver`).

19. La aplicacion debe seguir siendo utilizable **sin JavaScript**: todo el
    HTML llega renderizado desde el servidor y cada accion es un formulario.
    Los archivos de `src/public/js/` son mejoras progresivas (menu movil,
    aparicion al hacer scroll, hero 3D) y ninguno intercambia datos con el
    servidor.

20. Accesibilidad y responsividad obligatorias:
    - Contraste de texto minimo 4.5:1 y foco visible con `:focus-visible`.
    - Objetivos tactiles de 44x44 px como minimo en botones y campos.
    - Enlace "Saltar al contenido", etiquetas visibles en todos los campos,
      texto de ayuda enlazado con `aria-describedby`, iconos decorativos con
      `aria-hidden` e iconos SVG en linea (nunca emojis).
    - Puntos de quiebre en 1024 px, 860 px y 560 px; sin desplazamiento
      horizontal; las tablas anchas se desplazan dentro de su contenedor.
    - `prefers-reduced-motion` desactiva animaciones y efectos de movimiento.
    - Las portadas reservan su espacio con `aspect-ratio` para evitar saltos
      de layout, y se cargan con `loading="lazy"`.
