/* =====================================================================
   xml.js — Traduccion del documento XML del microservicio a objetos.

   La aplicacion consume EXCLUSIVAMENTE XML: el texto crudo que entrega
   el proceso principal se interpreta aqui con DOMParser. No existe
   ninguna ruta de codigo que lea JSON del servicio.

   Estructura esperada (urn:library:catalog:1.0):

     <library>
       <books count total limit offset>
         <book id isbn>
           <title/> <publicationYear/> <price currency/> <stock/>
           <format ref/> <category ref/>
           <authors><author ref/></authors>
           <genres><genre ref/></genres>
           <concepts><concept ref><name/><definition/></concept></concepts>
           <images><image id isCover/></images>
         </book>
       </books>
     </library>

   El recorrido se hace por nombre local, ignorando el prefijo de
   espacio de nombres, para tolerar endpoints equivalentes servidos con
   otro namespace.
   ===================================================================== */

'use strict';

const LibraryXml = (() => {

  /** Error de interpretacion del documento, distinguible del de red. */
  class XmlParseError extends Error {
    constructor(message) {
      super(message);
      this.name = 'XmlParseError';
    }
  }

  /* --- Utilidades de recorrido ------------------------------------- */

  const children = (node, localName) =>
    node ? Array.from(node.children).filter((el) => el.localName === localName) : [];

  const child = (node, localName) => children(node, localName)[0] || null;

  /** Primer descendiente con ese nombre local, a cualquier profundidad. */
  function descendant(node, localName) {
    if (!node) return null;
    if (node.localName === localName) return node;
    for (const el of node.querySelectorAll('*')) {
      if (el.localName === localName) return el;
    }
    return null;
  }

  const text = (node) => (node && node.textContent ? node.textContent.trim() : '');

  const textOf = (parent, localName) => text(child(parent, localName));

  function intAttr(node, name) {
    if (!node) return null;
    const value = Number.parseInt(node.getAttribute(name), 10);
    return Number.isFinite(value) ? value : null;
  }

  /* --- Parseo ------------------------------------------------------- */

  /** Convierte texto XML en un Document, o lanza XmlParseError. */
  function toDocument(xmlText) {
    if (typeof xmlText !== 'string' || xmlText.trim() === '') {
      throw new XmlParseError('El servicio devolvio una respuesta vacia.');
    }

    const doc = new DOMParser().parseFromString(xmlText, 'application/xml');
    const failure = doc.querySelector('parsererror');
    if (failure) {
      throw new XmlParseError('La respuesta no es un documento XML valido.');
    }
    return doc;
  }

  /** Extrae un <book> completo. */
  function parseBook(node) {
    const priceEl = child(node, 'price');
    const formatEl = child(node, 'format');
    const categoryEl = child(node, 'category');

    const rawPrice = text(priceEl);
    const parsedPrice = Number.parseFloat(rawPrice);

    return {
      id: intAttr(node, 'id'),
      isbn: node.getAttribute('isbn') || '',
      title: textOf(node, 'title') || 'Sin titulo',
      publicationYear: textOf(node, 'publicationYear'),
      price: Number.isFinite(parsedPrice) ? parsedPrice : null,
      priceRaw: rawPrice,
      currency: (priceEl && priceEl.getAttribute('currency')) || '',
      stock: Number.parseInt(textOf(node, 'stock'), 10) || 0,
      format: text(formatEl),
      formatRef: intAttr(formatEl, 'ref'),
      category: text(categoryEl),
      categoryRef: intAttr(categoryEl, 'ref'),

      authors: children(child(node, 'authors'), 'author')
        .map((el) => ({ ref: intAttr(el, 'ref'), name: text(el) }))
        .filter((a) => a.name !== ''),

      genres: children(child(node, 'genres'), 'genre')
        .map((el) => ({ ref: intAttr(el, 'ref'), name: text(el) }))
        .filter((g) => g.name !== ''),

      concepts: children(child(node, 'concepts'), 'concept')
        .map((el) => ({
          ref: intAttr(el, 'ref'),
          name: textOf(el, 'name'),
          definition: textOf(el, 'definition'),
        }))
        .filter((c) => c.name !== ''),

      images: children(child(node, 'images'), 'image')
        .map((el) => ({
          id: intAttr(el, 'id'),
          url: text(el),
          isCover: (el.getAttribute('isCover') || '').toLowerCase() === 'true',
        }))
        .filter((img) => /^https?:\/\//i.test(img.url)),
    };
  }

  /**
   * Interpreta la respuesta de un endpoint de catalogo.
   * Devuelve { books, count, total, limit, offset }.
   *
   * Si el documento no declara el atributo "total" (endpoint alterno),
   * se informa total = null y la paginacion se deduce del tamano de la
   * pagina recibida.
   */
  function parseCatalog(xmlText) {
    const doc = toDocument(xmlText);
    const root = doc.documentElement;

    // Un <error> del servicio se reporta como tal, no como catalogo vacio.
    if (root && root.localName === 'error') {
      const message = textOf(root, 'message') || text(root) || 'El servicio devolvio un error.';
      throw new XmlParseError(message);
    }

    const booksEl = descendant(root, 'books');
    if (!booksEl) {
      throw new XmlParseError(
        'El XML recibido no contiene un elemento <books>. Revisa el endpoint configurado.'
      );
    }

    const books = children(booksEl, 'book').map(parseBook);

    return {
      books,
      count: intAttr(booksEl, 'count') ?? books.length,
      total: intAttr(booksEl, 'total'),
      limit: intAttr(booksEl, 'limit'),
      offset: intAttr(booksEl, 'offset') ?? 0,
      generatedAt: (root && root.getAttribute('generatedAt')) || '',
      source: (root && root.getAttribute('source')) || '',
    };
  }

  /* ------------------------------------------------------------------ */
  /* Pedidos, envios y pagos (urn:library:orders / :payments)            */
  /*                                                                     */
  /* Mismo principio que el catalogo: el servicio responde XML y aqui se */
  /* interpreta. Los microservicios nuevos serializan sus diccionarios   */
  /* con la misma forma —un elemento por clave, en camelCase— de modo    */
  /* que basta leer por nombre local.                                    */
  /* ------------------------------------------------------------------ */

  /** Elemento plano -> objeto { clave: texto }. */
  function flatten(node) {
    const out = {};
    if (!node) return out;
    for (const el of Array.from(node.children)) {
      out[el.localName] = el.children.length ? flatten(el) : text(el);
    }
    return out;
  }

  /**
   * Rastreo PUBLICO de un envio: <shipment>.
   *
   * Es lo unico del par pedidos/pagos que se sirve sin token, pensado
   * para que una paqueteria siga el paquete. No trae cliente, ni
   * importes, ni que libros lleva: si algun dia apareciera algo de eso,
   * seria un fallo del servidor, no de este parser.
   */
  function parseShipment(xmlText) {
    const doc = toDocument(xmlText);
    const root = doc.documentElement;
    if (!root || root.localName === 'error') {
      throw new XmlParseError('El servicio no devolvio un envio.');
    }
    const plano = flatten(root);
    return {
      orderNumber: plano.orderNumber || '',
      status: plano.status || '',
      carrier: plano.carrier || '',
      trackingCode: plano.trackingCode || '',
      itemCount: intOf(plano.itemCount),
      placedAt: plano.placedAt || '',
      shippedAt: plano.shippedAt || '',
      deliveredAt: plano.deliveredAt || '',
    };
  }

  /** Coleccion <orders count total limit offset><order>…</order></orders>. */
  function parseOrders(xmlText) {
    const doc = toDocument(xmlText);
    const root = doc.documentElement;
    if (!root || root.localName === 'error') {
      throw new XmlParseError('El servicio no devolvio pedidos.');
    }
    const ordersEl = root.localName === 'orders' ? root : descendant(root, 'orders');
    const nodos = children(ordersEl, 'order');
    return {
      orders: nodos.map(readOrder),
      count: intAttr(ordersEl, 'count') ?? nodos.length,
      total: intAttr(ordersEl, 'total'),
      limit: intAttr(ordersEl, 'limit'),
      offset: intAttr(ordersEl, 'offset') ?? 0,
    };
  }

  /** Un pedido suelto: <order>…</order>. */
  function parseOrder(xmlText) {
    const doc = toDocument(xmlText);
    const root = doc.documentElement;
    if (!root || root.localName === 'error') {
      throw new XmlParseError('El servicio no devolvio un pedido.');
    }
    return readOrder(root);
  }

  function readOrder(node) {
    const plano = flatten(node);
    const envio = plano.shipping || {};
    const usuario = plano.user || {};
    const lineasEl = child(node, 'lines');
    return {
      id: intOf(plano.id),
      orderNumber: plano.orderNumber || '',
      status: plano.status || '',
      currency: plano.currency || '',
      subtotal: numberOf(plano.subtotal),
      shippingCost: numberOf(plano.shippingCost),
      total: numberOf(plano.total),
      paidAmount: numberOf(plano.paidAmount),
      itemCount: intOf(plano.itemCount),
      lineCount: intOf(plano.lineCount),
      placedAt: plano.placedAt || '',
      user: { id: intOf(usuario.id), email: usuario.email || '',
              name: usuario.name || '' },
      shipping: { carrier: envio.carrier || '', trackingCode: envio.trackingCode || '' },
      lines: children(lineasEl, 'line').map((el) => {
        const l = flatten(el);
        return {
          bookId: intOf(l.bookId), isbn: l.isbn || '', title: l.title || '',
          quantity: intOf(l.quantity), unitPrice: numberOf(l.unitPrice),
          lineTotal: numberOf(l.lineTotal),
        };
      }),
    };
  }

  /** Coleccion de metodos de pago: <methods><method>…</method></methods>. */
  function parseMethods(xmlText) {
    const doc = toDocument(xmlText);
    const root = doc.documentElement;
    if (!root || root.localName === 'error') {
      throw new XmlParseError('El servicio no devolvio metodos de pago.');
    }
    const el = root.localName === 'methods' ? root : descendant(root, 'methods');
    return children(el, 'method').map((m) => {
      const plano = flatten(m);
      return { id: intOf(plano.id), name: plano.name || '',
               description: plano.description || '',
               requiresAuthorization: plano.requiresAuthorization === 'true' };
    });
  }

  /** Un pago: <payment>…</payment>. */
  function parsePayment(xmlText) {
    const doc = toDocument(xmlText);
    const root = doc.documentElement;
    if (!root || root.localName === 'error') {
      throw new XmlParseError('El servicio no devolvio un pago.');
    }
    const plano = flatten(root);
    const pedido = plano.order || {};
    const metodo = plano.method || {};
    return {
      id: intOf(plano.id), reference: plano.reference || '',
      status: plano.status || '', amount: numberOf(plano.amount),
      currency: plano.currency || '',
      method: { id: intOf(metodo.id), name: metodo.name || '' },
      order: { id: intOf(pedido.id), number: pedido.number || '',
               status: pedido.status || '' },
      idempotentReplay: plano.idempotentReplay === 'true',
    };
  }

  /** Saldo de un pedido: <balance>…</balance>. */
  function parseBalance(xmlText) {
    const plano = flatten(toDocument(xmlText).documentElement);
    return {
      orderNumber: plano.orderNumber || '', orderStatus: plano.orderStatus || '',
      total: numberOf(plano.total), paid: numberOf(plano.paid),
      committed: numberOf(plano.committed), balance: numberOf(plano.balance),
      currency: plano.currency || '',
    };
  }

  /** Bloque <health> de cualquiera de los seis servicios. */
  function parseHealth(xmlText) {
    const plano = flatten(toDocument(xmlText).documentElement);
    const redis = plano.redis || {};
    return {
      status: plano.status || '', database: plano.database || '',
      jwt: plano.jwt || '', redisStatus: redis.status || '',
      warnings: Object.values(plano.warnings || {}),
    };
  }

  function intOf(value) {
    const n = Number.parseInt(value, 10);
    return Number.isFinite(n) ? n : null;
  }

  function numberOf(value) {
    const n = Number.parseFloat(value);
    return Number.isFinite(n) ? n : null;
  }

  return {
    parseCatalog, parseBook, toDocument, XmlParseError,
    parseShipment, parseOrders, parseOrder, parseMethods, parsePayment,
    parseBalance, parseHealth, flatten,
  };
})();
