/* =====================================================================
   services.js — Llamadas a los microservicios desde el renderer.

   Todas pasan por LibraryAuth.request, que anade el Bearer, renueva el
   token antes de que caduque (30 min) y reintenta una vez ante un 401.
   La respuesta llega como TEXTO XML y se interpreta con LibraryXml: la
   aplicacion sigue siendo XML de punta a punta, salvo /login y /refresh
   (ver la nota en main.js y en auth.js).

   Cada funcion devuelve { ok, data, message } para que la interfaz no
   tenga que mirar codigos HTTP.
   ===================================================================== */

'use strict';

const LibraryServices = (() => {

  function urls(config) {
    return LibraryConfig.serviceUrls(config);
  }

  /** Ejecuta y traduce: XML -> objeto, o un mensaje de error utilizable. */
  async function call(config, { service, path, method = 'GET', body,
                                anonymous = false, parse }) {
    const base = urls(config)[service];
    const response = await LibraryAuth.request(urls(config).login, {
      url: `${base}${path}`,
      method,
      body,
      anonymous,
    });
    if (!response.ok) {
      return { ok: false, data: null, message: LibraryAuth.errorMessage(response),
               status: response.status };
    }
    if (!parse) return { ok: true, data: null, message: '', response };
    try {
      return { ok: true, data: parse(response.body), message: '', response };
    } catch (error) {
      return { ok: false, data: null,
               message: `El servicio respondio algo que no se pudo interpretar: ${error.message}` };
    }
  }

  /* --- Pedidos ------------------------------------------------------- */

  /**
   * Rastreo PUBLICO del envio. anonymous: true a proposito — el endpoint
   * no pide token y asi funciona tambien sin sesion, que es justo para
   * lo que existe (que una paqueteria siga el paquete).
   */
  function trackShipment(config, orderNumber) {
    const numero = String(orderNumber || '').trim().toUpperCase();
    if (!numero) {
      return Promise.resolve({ ok: false, data: null,
                               message: 'Escribe un numero de pedido.' });
    }
    return call(config, {
      service: 'pedidos',
      path: `/envios/${encodeURIComponent(numero)}`,
      anonymous: true,
      parse: LibraryXml.parseShipment,
    });
  }

  function listOrders(config, { status = '', all = false, limit = 25, offset = 0 } = {}) {
    const params = new URLSearchParams({ limit: String(limit), offset: String(offset) });
    if (status) params.set('status', status);
    if (all) params.set('all', 'true');
    return call(config, {
      service: 'pedidos',
      path: `/pedidos?${params.toString()}`,
      parse: LibraryXml.parseOrders,
    });
  }

  function getOrder(config, orderId) {
    return call(config, {
      service: 'pedidos',
      path: `/pedidos/${orderId}`,
      parse: LibraryXml.parseOrder,
    });
  }

  /** El precio NO se manda: lo congela el servidor desde el catalogo. */
  function createOrder(config, lines, { shippingCost = 0, address = '' } = {}) {
    const body = {
      lines: lines.map(({ bookId, quantity }) => ({
        bookId: Number(bookId), quantity: Number(quantity),
      })),
    };
    if (shippingCost) body.shippingCost = Number(shippingCost);
    if (address) body.shippingAddress = address;
    return call(config, {
      service: 'pedidos', path: '/pedidos', method: 'POST', body,
      parse: LibraryXml.parseOrder,
    });
  }

  function cancelOrder(config, orderId, reason = '') {
    return call(config, {
      service: 'pedidos', path: `/pedidos/${orderId}`, method: 'DELETE',
      body: reason ? { reason } : undefined,
      parse: LibraryXml.parseOrder,
    });
  }

  function changeOrderStatus(config, orderId, status, extra = {}) {
    return call(config, {
      service: 'pedidos', path: `/pedidos/${orderId}/estado`, method: 'PUT',
      body: { status, ...extra },
      parse: LibraryXml.parseOrder,
    });
  }

  /* --- Pagos --------------------------------------------------------- */

  function paymentMethods(config) {
    return call(config, {
      service: 'pagos', path: '/metodos', parse: LibraryXml.parseMethods,
    });
  }

  function orderBalance(config, orderId) {
    return call(config, {
      service: 'pagos', path: `/pedidos/${orderId}/saldo`,
      parse: LibraryXml.parseBalance,
    });
  }

  /**
   * Registra un pago.
   *
   * idempotencyKey evita el cobro doble si el usuario pulsa dos veces o
   * la peticion se reintenta: el servidor devuelve el pago que ya
   * existia en lugar de crear otro.
   */
  function registerPayment(config, { orderId, amount, method, idempotencyKey,
                                     authorizationCode = '', cardLast4 = '' }) {
    const body = { orderId: Number(orderId), amount: Number(amount) };
    if (method) body.method = method;
    if (idempotencyKey) body.idempotencyKey = idempotencyKey;
    if (authorizationCode) body.authorizationCode = authorizationCode;
    if (cardLast4) body.cardLast4 = cardLast4;
    return call(config, {
      service: 'pagos', path: '/pagos', method: 'POST', body,
      parse: LibraryXml.parsePayment,
    });
  }

  /* --- Estado de los servicios --------------------------------------- */

  /** /health es publico en los seis: el semaforo funciona sin sesion. */
  async function health(config, service) {
    const result = await call(config, {
      service, path: '/health', anonymous: true, parse: LibraryXml.parseHealth,
    });
    if (!result.ok) return { service, state: 'down', detail: result.message };
    const data = result.data || {};
    const degradado = data.status !== 'ok'
      || (data.redisStatus && data.redisStatus !== 'ok')
      || data.jwt === 'missing_secret'
      || (data.warnings && data.warnings.length > 0);
    return {
      service,
      state: degradado ? 'degraded' : 'up',
      detail: degradado
        ? (data.redisStatus && data.redisStatus !== 'ok'
            ? 'Redis caido' : (data.warnings || [])[0] || data.status)
        : 'up',
    };
  }

  function healthAll(config) {
    return Promise.all(
      Object.keys(LibraryConfig.PUERTOS).map((s) => health(config, s)));
  }

  /** Clave de idempotencia para un pago. */
  function newIdempotencyKey() {
    const bytes = new Uint8Array(16);
    (window.crypto || {}).getRandomValues?.(bytes);
    return Array.from(bytes).map((b) => b.toString(16).padStart(2, '0')).join('');
  }

  return {
    trackShipment, listOrders, getOrder, createOrder, cancelOrder,
    changeOrderStatus, paymentMethods, orderBalance, registerPayment,
    health, healthAll, newIdempotencyKey, urls,
  };
})();
