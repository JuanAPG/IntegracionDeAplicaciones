/* =====================================================================
   config.js — Configuracion del servicio, persistida en localStorage.

   Requisito: la URL base y el endpoint deben ser configurables desde la
   aplicacion y sobrevivir a los reinicios. Se almacena un unico objeto
   serializado bajo la clave LIBRARY_CONFIG_KEY.
   ===================================================================== */

'use strict';

const LibraryConfig = (() => {
  const STORAGE_KEY = 'library.desktop.serviceConfig';

  // El catalogo (baseUrl + endpoint) se conserva tal cual para no
  // romper la configuracion ya guardada en localStorage. Los cinco
  // servicios restantes se derivan de la misma IP cambiando el puerto,
  // y se pueden sobreescribir uno a uno.
  const DEFAULTS = Object.freeze({
    baseUrl: 'http://34.51.14.158:5001',
    endpoint: '/books',
    pageSize: 6,
    loginUrl: '',
    usersUrl: '',
    authorsUrl: '',
    pedidosUrl: '',
    pagosUrl: '',
  });

  // puerto de cada microservicio
  const PUERTOS = Object.freeze({
    login: 5000, books: 5001, users: 5002,
    authors: 5003, pedidos: 5004, pagos: 5005,
  });

  const PAGE_SIZES = [3, 6, 9, 12, 24];

  /** Normaliza y valida un objeto de configuracion parcial. */
  function normalize(raw) {
    const source = raw && typeof raw === 'object' ? raw : {};

    let baseUrl = String(source.baseUrl ?? DEFAULTS.baseUrl).trim();
    baseUrl = baseUrl.replace(/\/+$/, '');           // sin barra final
    if (!/^https?:\/\//i.test(baseUrl)) baseUrl = DEFAULTS.baseUrl;

    let endpoint = String(source.endpoint ?? DEFAULTS.endpoint).trim();
    if (endpoint === '') endpoint = DEFAULTS.endpoint;
    if (!endpoint.startsWith('/')) endpoint = '/' + endpoint;
    endpoint = endpoint.replace(/\/+$/, '') || '/';  // tolera "/books/"

    let pageSize = Number.parseInt(source.pageSize, 10);
    if (!Number.isFinite(pageSize) || pageSize < 1) pageSize = DEFAULTS.pageSize;
    if (pageSize > 100) pageSize = 100;

    const extra = {};
    for (const nombre of ['login', 'users', 'authors', 'pedidos', 'pagos']) {
      const clave = `${nombre}Url`;
      let valor = String(source[clave] ?? '').trim().replace(/\/+$/, '');
      if (valor && !/^https?:\/\//i.test(valor)) valor = '';
      extra[clave] = valor;
    }

    return { baseUrl, endpoint, pageSize, ...extra };
  }

  /**
   * URL base de un microservicio.
   *
   * Si no se configuro explicitamente, se deriva del host del catalogo
   * cambiando el puerto: los seis suelen vivir en la misma VM y asi
   * basta con configurar uno.
   */
  function serviceUrl(config, nombre) {
    const normalizado = normalize(config);
    const explicito = normalizado[`${nombre}Url`];
    if (explicito) return explicito;
    if (nombre === 'books') return normalizado.baseUrl;
    const puerto = PUERTOS[nombre];
    if (!puerto) return normalizado.baseUrl;
    try {
      const url = new URL(normalizado.baseUrl);
      url.port = String(puerto);
      return url.origin;
    } catch {
      return normalizado.baseUrl;
    }
  }

  /** Las seis URL base, resueltas. */
  function serviceUrls(config) {
    const salida = {};
    for (const nombre of Object.keys(PUERTOS)) {
      salida[nombre] = serviceUrl(config, nombre);
    }
    return salida;
  }

  /** Lee la configuracion vigente; ante cualquier dano devuelve la de fabrica. */
  function load() {
    try {
      const stored = window.localStorage.getItem(STORAGE_KEY);
      if (!stored) return { ...DEFAULTS };
      return normalize(JSON.parse(stored));
    } catch {
      return { ...DEFAULTS };
    }
  }

  /** Persiste la configuracion normalizada y la devuelve. */
  function save(raw) {
    const config = normalize(raw);
    try {
      window.localStorage.setItem(STORAGE_KEY, JSON.stringify(config));
    } catch (error) {
      console.error('No fue posible persistir la configuracion:', error);
    }
    return config;
  }

  /** Restablece los valores de fabrica. */
  function reset() {
    try {
      window.localStorage.removeItem(STORAGE_KEY);
    } catch { /* almacenamiento no disponible */ }
    return { ...DEFAULTS };
  }

  /**
   * Construye la URL completa de una peticion paginada.
   * La paginacion viaja como limit/offset, tal y como la expone el
   * microservicio Flask.
   */
  function buildUrl(config, { limit, offset } = {}) {
    const { baseUrl, endpoint } = normalize(config);
    const url = new URL(baseUrl + endpoint);
    if (Number.isFinite(limit)) url.searchParams.set('limit', String(limit));
    if (Number.isFinite(offset)) url.searchParams.set('offset', String(offset));
    return url.toString();
  }

  return { DEFAULTS, PAGE_SIZES, PUERTOS, STORAGE_KEY, load, save, reset,
           normalize, buildUrl, serviceUrl, serviceUrls };
})();
