/* =====================================================================
   auth.js — Sesion del usuario en la aplicacion de escritorio.

   QUE GUARDA Y DONDE
     localStorage: el token de acceso (30 min), el refresh (8 h) y los
     datos publicos del usuario. NUNCA la contrasena.

   RENOVACION
     El token de acceso dura 30 minutos. En vez de obligar a iniciar
     sesion cada media hora, se canjea el refresh con POST /refresh:
       * antes de cualquier peticion, si quedan menos de 5 minutos;
       * y si una peticion devuelve 401, se renueva UNA vez y se
         reintenta. Un segundo 401 es sesion perdida de verdad.
     El refresh es de UN SOLO USO: al canjearlo el servidor entrega otro,
     de modo que hay que guardar siempre el nuevo.

   CIERRE
     POST /logout manda el Bearer para que el servidor REVOQUE el token
     en Redis. A partir de ese momento deja de servir en los seis
     microservicios, sin esperar a que caduque.

   SOBRE EL FORMATO
     Toda la aplicacion habla XML con los servicios. /login y /refresh
     son la excepcion: su XML no publica los tokens (a proposito), de
     modo que esos dos se piden en JSON. Esta anotado en main.js.
   ===================================================================== */

'use strict';

const LibraryAuth = (() => {
  const STORAGE_KEY = 'library.desktop.session';
  const RENEW_BEFORE_DEFAULT = 300;      // segundos

  let state = { access: null, refresh: null, user: null, renewBefore: RENEW_BEFORE_DEFAULT };
  const listeners = new Set();

  /* --- persistencia -------------------------------------------------- */
  function load() {
    try {
      const raw = window.localStorage.getItem(STORAGE_KEY);
      if (raw) state = { ...state, ...JSON.parse(raw) };
    } catch { /* almacenamiento no disponible o danado */ }
    return state;
  }

  function persist() {
    try {
      window.localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
    } catch { /* sin almacenamiento: la sesion dura lo que la ventana */ }
    listeners.forEach((fn) => { try { fn(snapshot()); } catch { /* ignora */ } });
  }

  function onChange(fn) { listeners.add(fn); return () => listeners.delete(fn); }

  /* --- lectura del token --------------------------------------------- */
  /** Claims del JWT SIN verificar la firma: eso lo hace el servidor.
      Aqui solo se mira 'exp' para saber cuando renovar y 'role' para
      decidir que botones mostrar. */
  function claims() {
    if (!state.access) return {};
    try {
      const parte = state.access.split('.')[1];
      const texto = atob(parte.replace(/-/g, '+').replace(/_/g, '/'));
      return JSON.parse(texto);
    } catch { return {}; }
  }

  function secondsLeft() {
    const exp = claims().exp;
    if (!exp) return null;
    return Math.floor(exp - Date.now() / 1000);
  }

  function isAuthenticated() { return Boolean(state.access) && (secondsLeft() ?? 1) > 0; }
  function expiringSoon() {
    const left = secondsLeft();
    return left !== null && left <= (state.renewBefore || RENEW_BEFORE_DEFAULT);
  }

  function snapshot() {
    const c = claims();
    return {
      authenticated: isAuthenticated(),
      user: state.user,
      role: c.role || null,
      roleId: c.role_id ?? null,
      userId: c.user_id ?? null,
      secondsLeft: secondsLeft(),
    };
  }

  /** Pista para la interfaz; la autorizacion real la aplica el servidor. */
  function can(...roles) {
    const rol = (claims().role || '').toLowerCase();
    return roles.map((r) => r.toLowerCase()).includes(rol);
  }

  /* --- operaciones ---------------------------------------------------- */
  async function login(baseUrl, email, password) {
    const response = await window.libraryBridge.request({
      url: `${baseUrl}/login?format=json`,
      method: 'POST',
      accept: 'json',
      body: { email, password },
    });
    if (!response.ok) return { ok: false, message: errorMessage(response) };
    let data;
    try { data = JSON.parse(response.body); }
    catch { return { ok: false, message: 'La respuesta de login no era JSON valido.' }; }

    state.access = data.token || null;
    state.refresh = data.refreshToken || null;
    state.user = data.user || null;
    state.renewBefore = data.renewBefore || RENEW_BEFORE_DEFAULT;
    persist();
    return { ok: true, user: state.user };
  }

  async function refresh(baseUrl) {
    if (!state.refresh) return false;
    const response = await window.libraryBridge.request({
      url: `${baseUrl}/refresh?format=json`,
      method: 'POST',
      accept: 'json',
      body: { refreshToken: state.refresh },
    });
    if (!response.ok) {
      // El refresh es de un solo uso: si el servidor lo rechaza, no hay
      // nada que reintentar. Excepcion: un fallo de red no invalida la
      // sesion, solo impide renovar ahora.
      if (response.kind === 'http') clear();
      return false;
    }
    try {
      const data = JSON.parse(response.body);
      state.access = data.token || null;
      state.refresh = data.refreshToken || null;
      state.renewBefore = data.renewBefore || state.renewBefore;
      if (data.user) state.user = data.user;
      persist();
      return Boolean(state.access);
    } catch { return false; }
  }

  async function logout(baseUrl) {
    if (state.access) {
      // Se manda el Bearer para que el servidor revoque el jti en Redis.
      await window.libraryBridge.request({
        url: `${baseUrl}/logout?format=json`,
        method: 'POST',
        accept: 'json',
        token: state.access,
      });
    }
    clear();
  }

  function clear() {
    state = { access: null, refresh: null, user: null, renewBefore: RENEW_BEFORE_DEFAULT };
    try { window.localStorage.removeItem(STORAGE_KEY); } catch { /* ignora */ }
    listeners.forEach((fn) => { try { fn(snapshot()); } catch { /* ignora */ } });
  }

  /**
   * Peticion autenticada con renovacion y UN reintento ante 401.
   *
   * loginBase hace falta para poder renovar: el token lo emite el
   * servicio de login, no aquel al que se esta llamando.
   */
  async function request(loginBase, options) {
    if (isAuthenticated() && expiringSoon()) await refresh(loginBase);

    const enviar = () => window.libraryBridge.request({
      ...options,
      token: options.anonymous ? undefined : state.access,
    });

    let response = await enviar();
    if (response.status === 401 && !options.anonymous && state.refresh) {
      if (await refresh(loginBase)) response = await enviar();
    }
    return response;
  }

  /** Traduce el sobre de error a una frase que dice QUE HACER. */
  function errorMessage(response) {
    if (!response) return 'Sin respuesta del servicio.';
    if (response.kind === 'network' || response.kind === 'timeout' || response.kind === 'url') {
      return response.message;
    }
    let detalle = '';
    try {
      const cuerpo = JSON.parse(response.body);
      if (cuerpo && cuerpo.error) {
        detalle = cuerpo.error.message || '';
        const extra = (cuerpo.error.details || []).slice(0, 2).join('; ');
        if (extra) detalle += ` — ${extra}`;
      }
    } catch {
      // Respuesta en XML: se saca el <message> sin montar un DOM entero.
      const m = /<message>([\s\S]*?)<\/message>/.exec(response.body || '');
      if (m) detalle = m[1].trim();
    }
    const base = detalle || response.message || 'La operacion fallo.';
    if (response.status === 401) {
      return `Tu sesion caduco o se cerro desde otro sitio. Vuelve a iniciar sesion. — ${base}`;
    }
    if (response.status === 403) {
      return `Tu cuenta no tiene permiso para esto. — ${base}`;
    }
    if (response.status === 503) {
      return `El servicio no esta disponible (base de datos o Redis caidos). — ${base}`;
    }
    return base;
  }

  load();
  return {
    load, snapshot, onChange, claims, isAuthenticated, expiringSoon,
    secondsLeft, can, login, refresh, logout, clear, request, errorMessage,
  };
})();
