/* =====================================================================
   spotlight.js — foco radial que sigue al cursor
   ---------------------------------------------------------------------
   Port a JavaScript plano del componente <Spotlight> (ibelick), que en su
   version original usa React + framer-motion (useSpring / useTransform).

   Equivalencias:
     useSpring(0, { bounce: 0 })  ->  integrador de resorte criticamente
                                      amortiguado (sin rebote) sobre rAF
     useTransform(x => `${x - size/2}px`)
                                  ->  translate3d() sobre el elemento
     isHovered ? 'opacity-100' : 'opacity-0'
                                  ->  clase .is-visible

   Uso en la vista:
     <div class="hero" data-spotlight data-spotlight-size="320"> ... </div>
   El foco se inyecta como primer hijo del contenedor marcado.
   ===================================================================== */
'use strict';

(function () {
  var reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  /**
   * Resorte criticamente amortiguado: damping = 2 * sqrt(stiffness * mass).
   * Con mass = 1 y stiffness = 170 no hay rebote, igual que { bounce: 0 }.
   */
  function Spring(stiffness) {
    this.k = stiffness;
    this.c = 2 * Math.sqrt(stiffness);
    this.value = 0;
    this.target = 0;
    this.velocity = 0;
  }

  Spring.prototype.step = function (dt) {
    // Se limita el paso para que una pestana en segundo plano no dispare la simulacion.
    var h = Math.min(dt, 0.032);
    var accel = this.k * (this.target - this.value) - this.c * this.velocity;
    this.velocity += accel * h;
    this.value += this.velocity * h;
    return this.value;
  };

  Spring.prototype.settled = function () {
    return Math.abs(this.target - this.value) < 0.05 && Math.abs(this.velocity) < 0.05;
  };

  Spring.prototype.jumpTo = function (v) {
    this.value = v;
    this.target = v;
    this.velocity = 0;
  };

  function createSpotlight(parent) {
    var size = parseInt(parent.getAttribute('data-spotlight-size'), 10) || 280;

    var el = document.createElement('div');
    el.className = 'spotlight';
    el.setAttribute('aria-hidden', 'true');
    el.style.width = size + 'px';
    el.style.height = size + 'px';
    parent.insertBefore(el, parent.firstChild);

    // El contenedor padre debe recortar y posicionar el foco.
    var computed = window.getComputedStyle(parent);
    if (computed.position === 'static') parent.style.position = 'relative';
    parent.style.overflow = 'hidden';

    var x = new Spring(170);
    var y = new Spring(170);
    var half = size / 2;
    var frame = null;
    var last = 0;
    var primed = false;

    function render() {
      el.style.transform = 'translate3d(' + (x.value - half) + 'px,' + (y.value - half) + 'px,0)';
    }

    function tick(now) {
      var dt = last ? (now - last) / 1000 : 0.016;
      last = now;
      x.step(dt);
      y.step(dt);
      render();

      if (x.settled() && y.settled()) {
        frame = null;
        last = 0;
        return;
      }
      frame = window.requestAnimationFrame(tick);
    }

    function start() {
      if (frame === null) frame = window.requestAnimationFrame(tick);
    }

    function onMove(event) {
      var rect = parent.getBoundingClientRect();
      var px = event.clientX - rect.left;
      var py = event.clientY - rect.top;

      if (!primed) {
        // Primer movimiento: colocar sin animar para que no cruce la tarjeta.
        primed = true;
        x.jumpTo(px);
        y.jumpTo(py);
        render();
      }

      x.target = px;
      y.target = py;
      start();
    }

    parent.addEventListener('mousemove', onMove);
    parent.addEventListener('mouseenter', function () { el.classList.add('is-visible'); });
    parent.addEventListener('mouseleave', function () {
      el.classList.remove('is-visible');
      primed = false;
    });
  }

  function init() {
    // Un foco que persigue el cursor es decorativo: se omite si el usuario
    // pide menos movimiento, y en dispositivos sin puntero fino (tactiles).
    if (reduceMotion || !window.matchMedia('(hover: hover) and (pointer: fine)').matches) return;
    var nodes = document.querySelectorAll('[data-spotlight]');
    for (var i = 0; i < nodes.length; i++) createSpotlight(nodes[i]);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
