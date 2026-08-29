/* =====================================================================
   spline-hero.js — escena 3D interactiva de Spline
   ---------------------------------------------------------------------
   Port a JavaScript plano del componente <SplineScene> (React), que en su
   version original envuelve @splinetool/react-spline dentro de <Suspense>.

   Equivalencias:
     lazy(() => import('@splinetool/react-spline'))
                        ->  import() dinamico del runtime servido en
                            <base>/vendor/spline/runtime.js (ESM, sin bundler)
     <Suspense fallback={<span class="loader"/>}>
                        ->  .scene-fallback visible hasta que la escena
                            termina de cargar
     prop `scene`       ->  atributo data-spline-scene del <canvas>

   Este archivo se carga con <script type="module" defer> y no envia ni
   recibe datos de la aplicacion: solo dibuja la escena en un <canvas>.
   ===================================================================== */

// Las rutas se derivan de la posicion de ESTE modulo (import.meta.url), no de
// la raiz del dominio: asi funcionan igual montada la aplicacion en / que bajo
// un prefijo como /library, sin que el JS de cliente necesite conocerlo.
// Este archivo se sirve en <base>/js/spline-hero.js, luego '../' es <base>/.
const ASSET_BASE = new URL('../', import.meta.url);

const RUNTIME_URL = new URL('vendor/spline/runtime.js', ASSET_BASE).href;

// Sin wasmPath el runtime descarga sus binarios .wasm desde el CDN de Spline.
// Apuntandolo a la misma ruta estatica, el despliegue no depende de terceros.
const WASM_PATH = new URL('vendor/spline/', ASSET_BASE).href;

const prefersReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

/** Verifica soporte de WebGL antes de descargar ~1 MB de runtime. */
function supportsWebGL() {
  try {
    const canvas = document.createElement('canvas');
    return Boolean(
      window.WebGLRenderingContext &&
      (canvas.getContext('webgl2') || canvas.getContext('webgl'))
    );
  } catch (err) {
    return false;
  }
}

/** Sustituye el indicador de carga por el orbe estatico de respaldo. */
function showStaticFallback(scene, reason) {
  const fallback = scene.querySelector('.scene-fallback');
  if (!fallback) return;
  fallback.innerHTML = '<div class="scene-orb"></div>';
  fallback.setAttribute('data-fallback-reason', reason);
}

async function loadScene(canvas) {
  const url = canvas.getAttribute('data-spline-scene');
  const scene = canvas.closest('.hero-scene') || canvas.parentElement;
  if (!url) return;

  try {
    const { Application } = await import(RUNTIME_URL);
    const app = new Application(canvas, { wasmPath: WASM_PATH });
    await app.load(url);

    scene.classList.add('is-ready');
    canvas.removeAttribute('aria-busy');

    // El indicador se retira del DOM una vez terminada la transicion.
    window.setTimeout(() => {
      const fallback = scene.querySelector('.scene-fallback');
      if (fallback) fallback.hidden = true;
    }, 400);
  } catch (err) {
    // La escena es decorativa: un fallo nunca debe romper la pagina.
    console.warn('[spline] no se pudo cargar la escena 3D:', err);
    showStaticFallback(scene, 'error');
    canvas.remove();
  }
}

function init() {
  const canvases = document.querySelectorAll('canvas[data-spline-scene]');
  if (!canvases.length) return;

  canvases.forEach((canvas) => {
    const scene = canvas.closest('.hero-scene') || canvas.parentElement;

    if (prefersReducedMotion) {
      showStaticFallback(scene, 'reduced-motion');
      canvas.remove();
      return;
    }
    if (!supportsWebGL()) {
      showStaticFallback(scene, 'no-webgl');
      canvas.remove();
      return;
    }

    // Solo se descarga el runtime cuando el hero esta cerca del viewport.
    if (!('IntersectionObserver' in window)) {
      loadScene(canvas);
      return;
    }
    const observer = new IntersectionObserver((entries) => {
      entries.forEach((entry) => {
        if (!entry.isIntersecting) return;
        observer.disconnect();
        loadScene(canvas);
      });
    }, { rootMargin: '200px' });
    observer.observe(scene);
  });
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', init);
} else {
  init();
}
