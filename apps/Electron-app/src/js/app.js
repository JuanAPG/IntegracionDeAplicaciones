/* =====================================================================
   app.js — Controlador de la aplicacion.

   Orquesta configuracion (localStorage), peticiones XML (via el puente
   del proceso principal), interpretacion (LibraryXml) y pintado
   (LibraryUI).

   Carga por peticion: cada pagina del catalogo es una peticion HTTP
   independiente con limit/offset. En ningun momento se descarga el
   catalogo completo para paginarlo en memoria.
   ===================================================================== */

'use strict';

(() => {
  const bridge = window.libraryBridge;

  /* --- Referencias del DOM ------------------------------------------ */
  const dom = {
    results:       document.getElementById('results'),
    catalogMeta:   document.getElementById('catalog-meta'),
    serviceOrigin: document.getElementById('service-origin'),
    status:        document.getElementById('status'),
    statusText:    document.getElementById('status-text'),
    pageSize:      document.getElementById('page-size'),

    pagination:    document.getElementById('pagination'),
    rangeStatus:   document.getElementById('range-status'),
    pageIndicator: document.getElementById('page-indicator'),
    btnPrev:       document.getElementById('btn-prev'),
    btnNext:       document.getElementById('btn-next'),
    btnRefresh:    document.getElementById('btn-refresh'),
    btnSettings:   document.getElementById('btn-settings'),

    bookDialog:      document.getElementById('book-dialog'),
    bookDialogTitle: document.getElementById('book-dialog-title'),
    bookDialogEyebrow: document.getElementById('book-dialog-eyebrow'),
    bookDialogBody:  document.getElementById('book-dialog-body'),
    bookDialogClose: document.getElementById('book-dialog-close'),

    settingsDialog:  document.getElementById('settings-dialog'),
    settingsForm:    document.getElementById('settings-form'),
    settingsClose:   document.getElementById('settings-close'),
    settingsFeedback: document.getElementById('settings-feedback'),
    inputBaseUrl:    document.getElementById('input-base-url'),
    inputEndpoint:   document.getElementById('input-endpoint'),
    errorBaseUrl:    document.getElementById('error-base-url'),
    errorEndpoint:   document.getElementById('error-endpoint'),
    urlPreview:      document.getElementById('url-preview'),
    btnReset:        document.getElementById('btn-reset'),
  };

  /* --- Estado -------------------------------------------------------- */
  const state = {
    config: LibraryConfig.load(),
    page: 0,          // base 0
    total: null,      // null = el servicio no informo el total
    received: 0,      // libros en la pagina actual
    loading: false,
    requestId: 0,     // descarta respuestas de peticiones ya superadas
  };

  /* --- Indicador de conexion ---------------------------------------- */
  /** Muestra en el encabezado el origen que se esta consultando. */
  function showOrigin() {
    const origin = state.config.baseUrl + state.config.endpoint;
    dom.serviceOrigin.textContent = origin;
    dom.serviceOrigin.title = origin;
  }

  function setStatus(stateName, text) {
    dom.status.dataset.state = stateName;
    dom.statusText.textContent = text;
  }

  /* ------------------------------------------------------------------ */
  /* Carga de una pagina                                                */
  /* ------------------------------------------------------------------ */

  async function loadPage(page) {
    const limit = state.config.pageSize;
    const offset = page * limit;
    const url = LibraryConfig.buildUrl(state.config, { limit, offset });
    const requestId = (state.requestId += 1);

    state.loading = true;
    dom.results.setAttribute('aria-busy', 'true');
    setStatus('loading', 'Consultando');
    showOrigin();
    dom.catalogMeta.textContent = `Solicitando libros ${offset + 1}-${offset + limit}…`;
    LibraryUI.renderSkeletons(dom.results, limit);
    updatePaginationControls();

    const response = await bridge.fetchXml(url);

    // Una peticion mas reciente ya esta en curso: se ignora esta.
    if (requestId !== state.requestId) return;

    state.loading = false;
    dom.results.setAttribute('aria-busy', 'false');

    if (!response.ok) {
      showFailure(response, url);
      return;
    }

    let catalog;
    try {
      catalog = LibraryXml.parseCatalog(response.body);
    } catch (error) {
      showParseFailure(error, url, response);
      return;
    }

    applyCatalog(catalog, page, response);
  }

  /** Pinta un catalogo interpretado con exito. */
  function applyCatalog(catalog, page, response) {
    state.page = page;
    state.received = catalog.books.length;
    state.total = catalog.total;

    // El servicio puede acotar el limit solicitado; se respeta el suyo.
    if (Number.isFinite(catalog.limit) && catalog.limit > 0 && catalog.limit !== state.config.pageSize) {
      state.config = LibraryConfig.save({ ...state.config, pageSize: catalog.limit });
      syncPageSizeOptions();
    }

    setStatus('ok', `Conectado (${response.elapsedMs} ms)`);

    if (catalog.books.length === 0) {
      const firstPage = page === 0;
      LibraryUI.renderState(dom.results, {
        variant: 'empty',
        iconId: 'i-search',
        title: firstPage ? 'El catalogo esta vacio' : 'Esta pagina no tiene libros',
        message: firstPage
          ? 'El servicio respondio correctamente, pero no devolvio ningun libro. Verifica que el endpoint configurado sea el del catalogo.'
          : 'Vuelve a la pagina anterior para seguir explorando el catalogo.',
        actions: firstPage
          ? [{ label: 'Abrir configuracion', primary: true, onClick: openSettings }]
          : [{ label: 'Pagina anterior', primary: true, onClick: () => loadPage(page - 1) }],
      });
    } else {
      LibraryUI.renderGrid(dom.results, catalog.books, openBook);
    }

    updateMeta(catalog);
    updatePaginationControls();
  }

  function updateMeta(catalog) {
    const total = state.total;
    const parts = [];
    parts.push(total === null ? `${catalog.books.length} libros en esta pagina`
                              : `${total} libros en el catalogo`);
    if (catalog.source) parts.push(`origen: ${catalog.source}`);
    parts.push('formato: XML');
    dom.catalogMeta.textContent = parts.join(' · ');
    showOrigin();
  }

  /* --- Errores ------------------------------------------------------- */

  function showFailure(response, url) {
    // Un 404 no es una falta de conexion: el indicador debe distinguirlos.
    const label = { timeout: 'Sin respuesta', http: `Error ${response.status}` }[response.kind]
      || 'Sin conexion';
    setStatus('error', label);
    dom.catalogMeta.textContent = 'No fue posible obtener el catalogo.';

    const hint = response.kind === 'http'
      ? 'Revisa que la ruta del endpoint exista en el servicio.'
      : 'Revisa que el equipo tenga red y que la URL base sea alcanzable.';

    LibraryUI.renderState(dom.results, {
      variant: 'error',
      iconId: 'i-alert',
      title: 'No se pudo cargar el catalogo',
      message: `${response.message} ${hint}`,
      detail: url,
      actions: [
        { label: 'Reintentar', primary: true, onClick: () => loadPage(state.page) },
        { label: 'Abrir configuracion', onClick: openSettings },
      ],
    });
    updatePaginationControls();
  }

  function showParseFailure(error, url, response) {
    setStatus('error', 'XML invalido');
    dom.catalogMeta.textContent = 'La respuesta no pudo interpretarse.';

    LibraryUI.renderState(dom.results, {
      variant: 'error',
      iconId: 'i-alert',
      title: 'La respuesta no es el XML esperado',
      message: `${error.message} La aplicacion consume unicamente XML; verifica que el endpoint devuelva el catalogo en ese formato.`,
      detail: `${url}\nContent-Type: ${response.contentType || 'desconocido'}`,
      actions: [
        { label: 'Reintentar', primary: true, onClick: () => loadPage(state.page) },
        { label: 'Abrir configuracion', onClick: openSettings },
      ],
    });
    updatePaginationControls();
  }

  /* ------------------------------------------------------------------ */
  /* Paginacion                                                         */
  /* ------------------------------------------------------------------ */

  const totalPages = () => {
    if (state.total === null) return null;
    return Math.max(1, Math.ceil(state.total / state.config.pageSize));
  };

  /**
   * Con total conocido la ultima pagina se calcula; sin el, se asume
   * que hay siguiente mientras la pagina venga llena.
   */
  function hasNextPage() {
    if (state.total === null) return state.received >= state.config.pageSize;
    return (state.page + 1) * state.config.pageSize < state.total;
  }

  function updatePaginationControls() {
    const pages = totalPages();
    const hasContent = state.received > 0 || state.page > 0;
    dom.pagination.hidden = !hasContent;

    dom.btnPrev.disabled = state.loading || state.page === 0;
    dom.btnNext.disabled = state.loading || !hasNextPage();

    dom.pageIndicator.textContent = pages === null
      ? `Pagina ${state.page + 1}`
      : `Pagina ${state.page + 1} de ${pages}`;

    if (state.received === 0) {
      dom.rangeStatus.textContent = '';
      return;
    }

    const from = state.page * state.config.pageSize + 1;
    const to = from + state.received - 1;
    dom.rangeStatus.replaceChildren(
      document.createTextNode('Mostrando '),
      LibraryUI.el('strong', { text: `${from}-${to}` }),
      document.createTextNode(state.total === null ? ' de este catalogo' : ` de ${state.total} libros`)
    );
  }

  /* ------------------------------------------------------------------ */
  /* Ficha del libro                                                    */
  /* ------------------------------------------------------------------ */

  function openBook(book) {
    dom.bookDialogTitle.textContent = book.title;
    dom.bookDialogEyebrow.textContent = LibraryUI.authorNames(book);
    LibraryUI.renderBookDetail(dom.bookDialogBody, book);
    dom.bookDialog.showModal();   // el navegador atrapa el foco y gestiona Esc
    dom.bookDialogBody.scrollTop = 0;
  }

  /* ------------------------------------------------------------------ */
  /* Configuracion                                                      */
  /* ------------------------------------------------------------------ */

  function syncPageSizeOptions() {
    const sizes = new Set([...LibraryConfig.PAGE_SIZES, state.config.pageSize]);
    const options = [...sizes].sort((a, b) => a - b);
    dom.pageSize.replaceChildren(...options.map((size) =>
      LibraryUI.el('option', {
        value: size,
        text: `${size} por pagina`,
        selected: size === state.config.pageSize,
      })
    ));
    dom.pageSize.value = String(state.config.pageSize);
  }

  function updateUrlPreview() {
    const draft = {
      baseUrl: dom.inputBaseUrl.value,
      endpoint: dom.inputEndpoint.value,
      pageSize: state.config.pageSize,
    };
    dom.urlPreview.textContent = LibraryConfig.buildUrl(draft, {
      limit: state.config.pageSize,
      offset: 0,
    });
  }

  function openSettings() {
    dom.inputBaseUrl.value = state.config.baseUrl;
    dom.inputEndpoint.value = state.config.endpoint;
    clearSettingsErrors();
    updateUrlPreview();
    dom.settingsDialog.showModal();
  }

  function clearSettingsErrors() {
    dom.errorBaseUrl.textContent = '';
    dom.errorEndpoint.textContent = '';
    dom.settingsFeedback.textContent = '';
    dom.inputBaseUrl.removeAttribute('aria-invalid');
    dom.inputEndpoint.removeAttribute('aria-invalid');
  }

  /** Valida el formulario; el error vive junto a su campo. */
  function validateSettings() {
    clearSettingsErrors();
    let valid = true;

    const baseUrl = dom.inputBaseUrl.value.trim();
    if (baseUrl === '') {
      dom.errorBaseUrl.textContent = 'Escribe la URL base del microservicio.';
      valid = false;
    } else if (!/^https?:\/\/.+/i.test(baseUrl)) {
      dom.errorBaseUrl.textContent = 'La URL debe comenzar con http:// o https://';
      valid = false;
    } else {
      try { new URL(baseUrl); } catch {
        dom.errorBaseUrl.textContent = 'La URL no tiene un formato valido.';
        valid = false;
      }
    }

    if (dom.inputEndpoint.value.trim() === '') {
      dom.errorEndpoint.textContent = 'Escribe la ruta del endpoint, por ejemplo /books';
      valid = false;
    }

    if (!valid) {
      // aria-invalid solo se anuncia con el valor explicito "true".
      if (dom.errorBaseUrl.textContent) dom.inputBaseUrl.setAttribute('aria-invalid', 'true');
      if (dom.errorEndpoint.textContent) dom.inputEndpoint.setAttribute('aria-invalid', 'true');
      (dom.errorBaseUrl.textContent ? dom.inputBaseUrl : dom.inputEndpoint).focus();
    }
    return valid;
  }

  /* ------------------------------------------------------------------ */
  /* Eventos                                                            */
  /* ------------------------------------------------------------------ */

  function bindEvents() {
    dom.btnPrev.addEventListener('click', () => {
      if (state.page > 0) loadPage(state.page - 1);
    });
    dom.btnNext.addEventListener('click', () => {
      if (hasNextPage()) loadPage(state.page + 1);
    });
    dom.btnRefresh.addEventListener('click', () => loadPage(state.page));

    // Cambiar el tamano de pagina se persiste y reinicia el recorrido.
    dom.pageSize.addEventListener('change', () => {
      state.config = LibraryConfig.save({
        ...state.config,
        pageSize: Number.parseInt(dom.pageSize.value, 10),
      });
      loadPage(0);
    });

    dom.btnSettings.addEventListener('click', openSettings);
    dom.settingsClose.addEventListener('click', () => dom.settingsDialog.close('cancel'));
    dom.bookDialogClose.addEventListener('click', () => dom.bookDialog.close());

    dom.inputBaseUrl.addEventListener('input', updateUrlPreview);
    dom.inputEndpoint.addEventListener('input', updateUrlPreview);

    dom.btnReset.addEventListener('click', () => {
      clearSettingsErrors();
      dom.inputBaseUrl.value = LibraryConfig.DEFAULTS.baseUrl;
      dom.inputEndpoint.value = LibraryConfig.DEFAULTS.endpoint;
      updateUrlPreview();
      dom.settingsFeedback.textContent = 'Valores de fabrica cargados. Guarda para aplicarlos.';
    });

    // El formulario usa method="dialog": se valida antes de dejar cerrar.
    dom.settingsForm.addEventListener('submit', (event) => {
      if (!validateSettings()) {
        event.preventDefault();
        return;
      }
      state.config = LibraryConfig.save({
        baseUrl: dom.inputBaseUrl.value,
        endpoint: dom.inputEndpoint.value,
        pageSize: state.config.pageSize,
      });
      // El dialogo se cierra solo (method="dialog"). La recarga se lanza
      // aqui mismo: requestAnimationFrame no se ejecuta si la ventana
      // esta oculta o minimizada, y la peticion quedaria pendiente.
      loadPage(0);
    });

    // Acciones del menu de la aplicacion.
    bridge.onOpenSettings(openSettings);
    bridge.onReloadCatalog(() => loadPage(state.page));

    // Las portadas enlazan a un origen externo: se abren fuera de la app.
    document.addEventListener('click', (event) => {
      const link = event.target.closest ? event.target.closest('a[href^="http"]') : null;
      if (!link) return;
      event.preventDefault();
      bridge.openExternal(link.href);
    });
  }

  /* ------------------------------------------------------------------ */
  /* Arranque                                                           */
  /* ------------------------------------------------------------------ */

  function init() {
    if (!bridge) {
      LibraryUI.renderState(dom.results, {
        variant: 'error',
        iconId: 'i-alert',
        title: 'Puente de la aplicacion no disponible',
        message: 'El proceso principal no expuso el puente de datos. Reinicia la aplicacion con npm start.',
      });
      return;
    }
    syncPageSizeOptions();
    showOrigin();
    bindEvents();
    loadPage(0);
  }

  document.addEventListener('DOMContentLoaded', init);
})();
