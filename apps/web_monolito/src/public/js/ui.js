/* =====================================================================
   ui.js — mejoras progresivas de la interfaz
   ---------------------------------------------------------------------
   Todo lo que hay aqui es opcional: la aplicacion funciona sin JavaScript
   porque el HTML se renderiza completo en el servidor. Este archivo solo
   agrega comodidades de navegacion y animacion.
   ===================================================================== */
'use strict';

(function () {
  var reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  /* --- Menu de navegacion en pantallas pequenas -------------------- */
  function initNav() {
    var toggle = document.querySelector('[data-nav-toggle]');
    var links = document.getElementById('nav-links');
    if (!toggle || !links) return;

    toggle.addEventListener('click', function () {
      var open = links.classList.toggle('is-open');
      toggle.setAttribute('aria-expanded', open ? 'true' : 'false');
    });

    // Al volver a escritorio se limpia el estado del menu movil.
    window.matchMedia('(min-width: 861px)').addEventListener('change', function (e) {
      if (!e.matches) return;
      links.classList.remove('is-open');
      toggle.setAttribute('aria-expanded', 'false');
    });
  }

  /* --- Aparicion escalonada al entrar en pantalla ------------------ */
  function initReveal() {
    var nodes = document.querySelectorAll('[data-reveal]');
    if (!nodes.length) return;

    if (reduceMotion || !('IntersectionObserver' in window)) {
      for (var i = 0; i < nodes.length; i++) nodes[i].classList.add('is-visible');
      return;
    }

    var observer = new IntersectionObserver(function (entries) {
      var shown = 0;
      entries.forEach(function (entry) {
        if (!entry.isIntersecting) return;
        // 60 ms entre elementos: onda corta, sin retrasar la lectura.
        entry.target.style.setProperty('--reveal-delay', Math.min(shown * 60, 300) + 'ms');
        entry.target.classList.add('is-visible');
        observer.unobserve(entry.target);
        shown++;
      });
    }, { rootMargin: '0px 0px -8% 0px', threshold: 0.06 });

    for (var j = 0; j < nodes.length; j++) observer.observe(nodes[j]);
  }

  /* --- Envio automatico de filtros al cambiar un desplegable ------- */
  function initAutoFilters() {
    var forms = document.querySelectorAll('form[data-auto-filter]');
    for (var i = 0; i < forms.length; i++) {
      forms[i].addEventListener('change', function (event) {
        if (event.target.tagName !== 'SELECT' && event.target.type !== 'checkbox') return;
        event.currentTarget.submit();
      });
    }
  }

  function init() {
    initNav();
    initReveal();
    initAutoFilters();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
