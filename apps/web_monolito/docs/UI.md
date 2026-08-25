# Sistema de diseño de la interfaz

Documenta el rediseño de la capa View del monolito: que se instalo, donde vive
cada pieza y como se portaron a JavaScript plano tres componentes que en su
origen estaban escritos en React.

---

## 1. Por que no hay React, Tailwind ni shadcn/ui

El punto 2 de `01-prompt_WebMonolito.md` fija la restriccion arquitectonica del
proyecto: **HTML renderizado en el servidor, sin APIs REST/GraphQL/SOAP y sin
JSON o XML como formato de intercambio**. La capa View es EJS y la macro
arquitectura es monolitica (punto 10), con MVC (punto 11).

Introducir React, TypeScript, Tailwind y shadcn/ui implicaria:

- un segundo runtime de interfaz que renderiza en el cliente, no en el servidor;
- un paso de compilacion (Vite/Next + PostCSS) fuera del proceso Node.js unico;
- y, para que los componentes de React vieran los datos, un canal de datos
  cliente-servidor, es decir exactamente la API JSON que el enunciado prohibe.

Por eso **no existe la carpeta `components/ui/`** que asume el flujo de trabajo
de shadcn: no hay componentes de React que alojar. Su equivalente funcional en
este proyecto es:

| Convencion shadcn (React) | Equivalente en este monolito |
|---|---|
| `components/ui/*.tsx` | `src/views/partials/*.ejs` (navbar, footer, mensajes, paginacion) y las clases del sistema de diseño |
| `app/globals.css` con `@layer base` y variables de tema | `src/public/css/styles.css`, seccion **01. Tokens de diseño** |
| `tailwind.config.ts` (escalas de color, espaciado, tipografia) | Variables CSS en `:root` del mismo archivo |
| `lib/utils.ts` (`cn()` para componer clases) | Innecesario: las clases se componen en la plantilla EJS |
| `npx shadcn@latest add card` | La clase `.card` (seccion **08. Superficies**) |

Si en el futuro el proyecto dejara de estar sujeto a esta restriccion, la ruta
de migracion seria: `npx shadcn@latest init` en un paquete aparte
(`apps/web_spa/`), con su propio `tsconfig.json`, `tailwind.config.ts` y
`components/ui/`, consumiendo el monolito por una API nueva. Mezclar ambos
enfoques dentro de `apps/web_monolito/` es lo que romperia el enunciado.

---

## 2. Dependencia nueva

Solo una:

```bash
npm install @splinetool/runtime
```

`@splinetool/runtime` es el motor 3D que `@splinetool/react-spline` envuelve.
Se publica como **ESM nativo**, asi que se sirve tal cual desde `node_modules`,
sin bundler, montado en `src/app.js`:

```js
app.use(
  '/vendor/spline',
  express.static(path.join(require.resolve('@splinetool/runtime'), '..'), {
    immutable: true,
    maxAge: '30d'
  })
);
```

Deliberadamente **no** se instalaron `@splinetool/react-spline` (necesita React)
ni `framer-motion` (necesita React); sus dos aportes —carga diferida de la
escena y muelle de animacion— se reimplementaron en 60 lineas de JavaScript.

---

## 3. Los tres componentes de React y su port

### 3.1 `SplineScene` → `src/public/js/spline-hero.js`

```tsx
// Original (React)
const Spline = lazy(() => import('@splinetool/react-spline'))

export function SplineScene({ scene, className }) {
  return (
    <Suspense fallback={<span className="loader" />}>
      <Spline scene={scene} className={className} />
    </Suspense>
  )
}
```

| Concepto de React | Equivalente sin framework |
|---|---|
| `lazy(() => import(...))` | `await import('/vendor/spline/runtime.js')` |
| `<Suspense fallback>` | `.scene-fallback` visible hasta que `app.load()` resuelve |
| prop `scene` | atributo `data-spline-scene` en el `<canvas>` |
| prop `className` | clases del `<canvas>` en la plantilla |

Mejoras añadidas sobre el original:

- **Carga diferida real**: el runtime (~1 MB) solo se descarga cuando el hero
  entra en el viewport (`IntersectionObserver`, `rootMargin: 200px`).
- **Deteccion de WebGL** antes de descargar nada.
- **Respeto de `prefers-reduced-motion`**: no se carga la escena.
- **Degradacion**: en cualquiera de los tres casos anteriores, y ante un fallo
  de carga, aparece un orbe animado en CSS (`.scene-orb`). La pagina nunca se
  rompe por la escena, que es puramente decorativa (`aria-hidden`).

### 3.2 `Spotlight` (ibelick) → `src/public/js/spotlight.js`

```tsx
// Original (React + framer-motion)
const mouseX = useSpring(0, { bounce: 0 });
const spotlightLeft = useTransform(mouseX, (x) => `${x - size / 2}px`);
```

| Concepto de framer-motion | Equivalente sin framework |
|---|---|
| `useSpring(0, { bounce: 0 })` | Integrador de resorte **criticamente amortiguado** sobre `requestAnimationFrame`: `damping = 2 * sqrt(stiffness)` con `mass = 1`, que es justo la condicion de "sin rebote" |
| `useTransform(x => ...)` + `style.left/top` | `transform: translate3d(...)` (compuesto en GPU, no provoca reflow) |
| `isHovered ? 'opacity-100' : 'opacity-0'` | clase `.is-visible` |
| `useEffect` que fija `position/overflow` del padre | mismo ajuste en `createSpotlight()` |

Correcciones respecto al original:

- El bucle de animacion **se detiene** cuando el resorte se asienta, en lugar
  de correr indefinidamente.
- El paso de integracion se acota (`min(dt, 32ms)`) para que una pestaña en
  segundo plano no dispare la simulacion al volver al primer plano.
- Al entrar el cursor, el foco se coloca sin animar, evitando el barrido
  diagonal que hace el original desde la esquina superior izquierda.
- No se instala en dispositivos tactiles ni con `prefers-reduced-motion`.
- El original registra los listeners de `mouseenter`/`mouseleave` con funciones
  anonimas y luego intenta quitarlos con **otras** funciones anonimas, por lo
  que nunca se liberan; aqui el ciclo de vida coincide con el de la pagina.

Uso en la plantilla:

```html
<section class="hero" data-spotlight data-spotlight-size="340"> ... </section>
```

### 3.3 `Card` (shadcn/ui) → clase `.card`

`Card`, `CardHeader`, `CardTitle`, `CardDescription`, `CardContent` y
`CardFooter` son, en la practica, seis `<div>` con clases de Tailwind. En EJS
el equivalente directo es marcado semantico mas la clase `.card`:

| shadcn | Aqui |
|---|---|
| `<Card>` | `<div class="card">` (o `<article class="card">`) |
| `<CardHeader>` / `<CardTitle>` | `<h2>` dentro de `.card` |
| `<CardDescription>` | `<p class="lead">` |
| `<CardContent>` | contenido directo de `.card` |
| `<CardFooter>` | `<div class="form-actions">` o `.book-card-foot` |

---

## 4. Archivos del rediseño

```
src/
├── app.js                          + ruta estatica /vendor/spline
├── public/
│   ├── css/styles.css              Sistema de diseño completo (18 secciones)
│   └── js/
│       ├── ui.js                   Menu movil, aparicion al scroll (progresivo)
│       ├── spotlight.js            Port de <Spotlight>
│       └── spline-hero.js          Port de <SplineScene>  (type="module")
├── views/
│   ├── layout.ejs                  Fuentes, favicon SVG, skip-link, scripts
│   ├── error.ejs
│   └── partials/                   navbar, footer, messages, pagination
└── modules/*/views/*.ejs           Todas las vistas de modulo, restiladas
```

Los scripts del hero solo se incluyen en las paginas que los necesitan, mediante
la variable `hasSpline` que el controlador pasa a `res.page()`:

```js
res.page('catalog/views/home', { title: 'Bienvenido', highlights, hasSpline: true });
```

---

## 5. Tokens principales

| Token | Valor | Uso |
|---|---|---|
| `--bg` | `#070B16` | Fondo de la pagina |
| `--surface` | `rgba(21,28,49,.72)` | Tarjetas translucidas |
| `--text` / `--muted` | `#F1F5F9` / `#98A5BD` | Texto principal y secundario |
| `--primary` / `--secondary` | `#7C3AED` / `#6366F1` | Marca, botones, foco |
| `--accent` | `#22D3EE` | Antetitulos y detalles |
| `--success` / `--danger` | `#34D399` / `#F87171` | Precio y stock, errores |
| `--border` | `rgba(255,255,255,.09)` | Bordes de vidrio |
| `--r-sm … --r-xl` | 8 / 12 / 18 / 26 px | Radios |
| `--space-1 … --space-8` | 4 … 64 px | Escala de espaciado |
| `--t-fast / --t-base / --t-slow` | 140 / 220 / 320 ms | Duraciones |

El tema es **oscuro unico**: `color-scheme: dark` evita que el navegador
reinterprete los controles nativos, y la portada 3D esta construida sobre fondo
negro, de modo que un tema claro alterno romperia la continuidad visual.

---

## 6. Accesibilidad

- Enlace **"Saltar al contenido"** como primer elemento enfocable.
- `:focus-visible` con anillo de 2 px; nunca se elimina el indicador de foco.
- Contraste: `#F1F5F9` sobre `#070B16` ≈ 17:1; `--muted` sobre superficie ≈ 7:1.
  Ambos superan el minimo AA de 4.5:1.
- Botones y campos con altura minima de 44 px (`.btn-sm` baja a 36 px, reservado
  para acciones de tabla, siempre acompañadas de texto).
- Iconos SVG en linea de Lucide, con `aria-hidden="true"`. Sin emojis.
- Los mensajes flash viven en un contenedor `role="status" aria-live="polite"`.
- Las ayudas de campo se enlazan con `aria-describedby`.
- Las portadas declaran `aspect-ratio`, de modo que reservan su espacio antes de
  cargar y no desplazan el contenido (CLS).
- `prefers-reduced-motion: reduce` anula animaciones, transiciones, el spotlight
  y la escena 3D.

---

## 7. Vista previa local

Para revisar todas las pantallas sin levantar PostgreSQL existe un generador de
paginas estaticas con datos de prueba. La carpeta resultante esta excluida de
git y puede borrarse en cualquier momento:

```bash
npm start                                   # o npm run dev
# http://localhost:3000/__preview__/        indice con las 19 pantallas
rm -rf src/public/__preview__               # eliminarla
```
