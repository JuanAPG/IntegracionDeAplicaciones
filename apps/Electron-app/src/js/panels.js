/* =====================================================================
   panels.js — Paneles de sesion, pedidos y rastreo de envio.

   Construye su propio DOM (dialogos nativos <dialog>) en lugar de pedir
   marcado en index.html, para no tocar la plantilla del catalogo mas
   que para anadir tres botones. El estilo se apoya en las clases que ya
   define styles.css (btn, dialog, field, chip).

   Que hay aqui
     Sesion    iniciar y cerrar sesion. Al cerrar, el servidor REVOCA el
               token en Redis: deja de servir en los seis servicios.
     Pedidos   los del usuario, con detalle y cancelacion. Crear pedido
               se hace desde el catalogo (boton «Pedir» de cada libro).
     Envio     rastreo PUBLICO por numero de pedido. Funciona SIN
               sesion: es el endpoint pensado para que un tercero lleve
               su logistica, y solo devuelve el estado del envio.
   ===================================================================== */

'use strict';

const LibraryPanels = (() => {
  const { el } = LibraryUI;

  let getConfig = () => LibraryConfig.load();
  let onOrderPlaced = () => {};

  function init({ config, onPlaced }) {
    if (typeof config === 'function') getConfig = config;
    if (typeof onPlaced === 'function') onOrderPlaced = onPlaced;
  }

  /* ------------------------------------------------------------------ */
  /* Utilidades                                                         */
  /* ------------------------------------------------------------------ */

  function money(value, currency = 'MXN') {
    if (value === null || value === undefined || Number.isNaN(Number(value))) return '—';
    return `${Number(value).toLocaleString('es-MX', {
      minimumFractionDigits: 2, maximumFractionDigits: 2 })} ${currency}`;
  }

  function stamp(value) {
    return value ? String(value).slice(0, 19).replace('T', ' ') : '—';
  }

  /** Dialogo con cabecera, cuerpo y pie. Devuelve {dialog, body, footer}. */
  function makeDialog(title, subtitle = '') {
    const body = el('div', { class: 'dialog__body' });
    const footer = el('footer', { class: 'dialog__footer' });
    const close = el('button', {
      type: 'button', class: 'btn btn--ghost btn--icon dialog__close',
      'aria-label': 'Cerrar', text: '✕',
    });
    const dialog = el('dialog', { class: 'dialog' }, [
      el('header', { class: 'dialog__header' }, [
        el('div', { class: 'dialog__heading' }, [
          el('p', { class: 'dialog__eyebrow', text: subtitle }),
          el('h2', { text: title }),
        ]),
        close,
      ]),
      body,
      footer,
    ]);
    close.addEventListener('click', () => dialog.close());
    dialog.addEventListener('close', () => dialog.remove());
    document.body.appendChild(dialog);
    return { dialog, body, footer };
  }

  function notice(parent, text, variant = 'info') {
    const colores = { info: '#9AA4B2', ok: '#4ADE80', error: '#F87171' };
    const nodo = el('p', { text, style: `color:${colores[variant] || colores.info}` });
    parent.appendChild(nodo);
    return nodo;
  }

  function field(label, attrs = {}) {
    const input = el('input', { class: 'input', ...attrs });
    const wrap = el('div', { class: 'field' }, [
      el('label', { class: 'field__label', text: label }), input,
    ]);
    return { wrap, input };
  }

  /* ------------------------------------------------------------------ */
  /* Sesion                                                             */
  /* ------------------------------------------------------------------ */

  function openLogin() {
    const { dialog, body, footer } = makeDialog(
      'Iniciar sesion', 'Microservicio de autenticacion');

    const correo = field('Correo', { type: 'email', autocomplete: 'username' });
    const clave = field('Contrasena', { type: 'password', autocomplete: 'current-password' });
    body.append(correo.wrap, clave.wrap);
    const mensaje = notice(body,
      'El token de acceso dura 30 minutos y se renueva solo. Al cerrar sesion '
      + 'se revoca en el servidor.', 'info');

    const entrar = el('button', { type: 'button', class: 'btn btn--primary',
                                  text: 'Entrar' });
    footer.append(
      el('button', { type: 'button', class: 'btn btn--ghost', text: 'Cancelar' }),
      entrar);
    footer.firstChild.addEventListener('click', () => dialog.close());

    async function submit() {
      entrar.disabled = true;
      mensaje.textContent = 'Verificando credenciales…';
      mensaje.style.color = '#9AA4B2';
      const base = LibraryServices.urls(getConfig()).login;
      const r = await LibraryAuth.login(base, correo.input.value.trim(),
                                        clave.input.value);
      if (!r.ok) {
        mensaje.textContent = r.message;
        mensaje.style.color = '#F87171';
        entrar.disabled = false;
        return;
      }
      dialog.close();
    }

    entrar.addEventListener('click', submit);
    clave.input.addEventListener('keydown', (e) => { if (e.key === 'Enter') submit(); });
    dialog.showModal();
    correo.input.focus();
  }

  async function doLogout() {
    const base = LibraryServices.urls(getConfig()).login;
    await LibraryAuth.logout(base);
  }

  /* ------------------------------------------------------------------ */
  /* Pedidos                                                            */
  /* ------------------------------------------------------------------ */

  async function openOrders() {
    if (!LibraryAuth.isAuthenticated()) {
      openLogin();
      return;
    }
    const { dialog, body, footer } = makeDialog('Mis pedidos', 'Microservicio de pedidos');
    const lista = el('div');
    const estado = notice(body, 'Cargando pedidos…');
    body.appendChild(lista);

    const verTodos = LibraryAuth.can('admin', 'staff');
    let todos = false;
    if (verTodos) {
      const toggle = el('button', { type: 'button', class: 'btn btn--ghost',
                                    text: 'Ver los de todos' });
      toggle.addEventListener('click', async () => {
        todos = !todos;
        toggle.textContent = todos ? 'Ver solo los mios' : 'Ver los de todos';
        await cargar();
      });
      footer.appendChild(toggle);
    }
    const cerrar = el('button', { type: 'button', class: 'btn btn--primary',
                                  text: 'Cerrar' });
    cerrar.addEventListener('click', () => dialog.close());
    footer.appendChild(cerrar);

    async function cargar() {
      estado.textContent = 'Cargando pedidos…';
      estado.style.color = '#9AA4B2';
      lista.replaceChildren();
      const r = await LibraryServices.listOrders(getConfig(), { all: todos });
      if (!r.ok) {
        estado.textContent = r.message;
        estado.style.color = '#F87171';
        return;
      }
      const pedidos = r.data.orders || [];
      estado.textContent = pedidos.length
        ? `${r.data.total ?? pedidos.length} pedido(s).`
        : 'Todavia no tienes pedidos. Usa «Pedir» en una ficha del catalogo.';
      pedidos.forEach((pedido) => lista.appendChild(orderCard(pedido, cargar)));
    }

    dialog.showModal();
    await cargar();
  }

  function orderCard(pedido, reload) {
    const chips = el('div', { class: 'chips' }, [
      el('span', { class: 'chip chip--primary', text: pedido.status }),
      el('span', { class: 'chip', text: `${pedido.itemCount ?? 0} pieza(s)` }),
      el('span', { class: 'chip', text: money(pedido.total, pedido.currency) }),
    ]);
    if (pedido.shipping && pedido.shipping.trackingCode) {
      chips.appendChild(el('span', { class: 'chip',
                                     text: `guia ${pedido.shipping.trackingCode}` }));
    }

    const acciones = el('div', { class: 'chips' });
    const cancelable = ['pendiente', 'pagado'].includes(pedido.status);
    if (cancelable) {
      const btn = el('button', { type: 'button', class: 'btn btn--ghost',
                                 text: 'Cancelar' });
      btn.addEventListener('click', async () => {
        btn.disabled = true;
        const r = await LibraryServices.cancelOrder(
          getConfig(), pedido.id, 'cancelado desde la app de escritorio');
        if (!r.ok) {
          window.alert(r.message);
          btn.disabled = false;
          return;
        }
        await reload();
      });
      acciones.appendChild(btn);
    }
    if (pedido.status !== 'cancelado'
        && (pedido.paidAmount ?? 0) < (pedido.total ?? 0)) {
      const btn = el('button', { type: 'button', class: 'btn btn--primary',
                                 text: 'Pagar' });
      btn.addEventListener('click', () => openPayment(pedido, reload));
      acciones.appendChild(btn);
    }

    const lineas = el('ul', { class: 'panel-list' },
      (pedido.lines || []).map((l) => el('li', {
        text: `${l.quantity} × ${l.title} — ${money(l.lineTotal, pedido.currency)}`,
      })));

    return el('article', { class: 'panel-card' }, [
      el('h3', { text: pedido.orderNumber }),
      el('p', { class: 'panel-card__meta', text: `Realizado ${stamp(pedido.placedAt)}` }),
      chips,
      lineas,
      acciones,
    ]);
  }

  /* ------------------------------------------------------------------ */
  /* Pagos                                                              */
  /* ------------------------------------------------------------------ */

  async function openPayment(pedido, reload) {
    const { dialog, body, footer } = makeDialog(
      `Pagar ${pedido.orderNumber}`, 'Microservicio de pagos');
    const saldoTexto = notice(body, 'Consultando saldo…');

    const importe = field('Importe', { type: 'number', step: '0.01', min: '0.01' });
    const metodo = el('select', { class: 'input' });
    const metodoWrap = el('div', { class: 'field' }, [
      el('label', { class: 'field__label', text: 'Metodo' }), metodo,
    ]);
    const codigo = field('Codigo de autorizacion (opcional)', { type: 'text' });
    const last4 = field('Ultimos 4 digitos (opcional)', {
      type: 'text', maxlength: '4', inputmode: 'numeric' });
    body.append(importe.wrap, metodoWrap, codigo.wrap, last4.wrap);
    notice(body,
      'Esta aplicacion NO envia numeros de tarjeta: el servicio rechaza '
      + 'cualquier campo de ese tipo. Solo viaja la referencia de la pasarela.',
      'info');
    const mensaje = notice(body, '');

    // Clave fija para ESTE dialogo: si se pulsa dos veces, el servidor
    // devuelve el mismo pago en lugar de cobrar otra vez.
    const idempotencyKey = LibraryServices.newIdempotencyKey();

    const pagar = el('button', { type: 'button', class: 'btn btn--primary',
                                 text: 'Registrar pago' });
    footer.append(
      el('button', { type: 'button', class: 'btn btn--ghost', text: 'Cancelar' }),
      pagar);
    footer.firstChild.addEventListener('click', () => dialog.close());
    dialog.showModal();

    const metodos = await LibraryServices.paymentMethods(getConfig());
    if (metodos.ok) {
      (metodos.data || []).forEach((m) => metodo.appendChild(
        el('option', { value: m.name, text: m.name })));
    } else {
      metodo.appendChild(el('option', { value: 'efectivo', text: 'efectivo' }));
      metodo.appendChild(el('option', { value: 'tarjeta', text: 'tarjeta' }));
    }

    const saldo = await LibraryServices.orderBalance(getConfig(), pedido.id);
    if (saldo.ok) {
      const d = saldo.data;
      saldoTexto.textContent =
        `Total ${money(d.total, d.currency)} · cobrado ${money(d.paid, d.currency)} `
        + `· falta ${money(d.balance, d.currency)}`;
      if (d.balance) importe.input.value = Number(d.balance).toFixed(2);
    } else {
      saldoTexto.textContent = saldo.message;
      saldoTexto.style.color = '#F87171';
    }

    pagar.addEventListener('click', async () => {
      pagar.disabled = true;
      mensaje.textContent = 'Registrando…';
      mensaje.style.color = '#9AA4B2';
      const r = await LibraryServices.registerPayment(getConfig(), {
        orderId: pedido.id,
        amount: importe.input.value,
        method: metodo.value,
        idempotencyKey,
        authorizationCode: codigo.input.value.trim(),
        cardLast4: last4.input.value.trim(),
      });
      if (!r.ok) {
        mensaje.textContent = r.message;
        mensaje.style.color = '#F87171';
        pagar.disabled = false;
        return;
      }
      dialog.close();
      const repetido = r.data.idempotentReplay
        ? ' (ya existia: no se cobro dos veces)' : '';
      window.alert(`Pago ${r.data.reference} registrado como `
                   + `«${r.data.status}»${repetido}.`);
      if (reload) await reload();
    });
  }

  /* ------------------------------------------------------------------ */
  /* Pedir un libro desde el catalogo                                   */
  /* ------------------------------------------------------------------ */

  function openOrderForBook(book) {
    if (!LibraryAuth.isAuthenticated()) {
      openLogin();
      return;
    }
    const { dialog, body, footer } = makeDialog(
      'Pedir este libro', book.title || '');

    const cantidad = field('Cantidad', {
      type: 'number', min: '1', max: String(Math.max(book.stock || 1, 1)), value: '1' });
    const direccion = field('Direccion de envio (opcional)', { type: 'text' });
    body.append(cantidad.wrap, direccion.wrap);
    notice(body,
      `Disponibles: ${book.stock ?? '—'}. El precio lo congela el servidor desde `
      + 'el catalogo, de modo que el total definitivo lo calcula el.', 'info');
    const mensaje = notice(body, '');

    const crear = el('button', { type: 'button', class: 'btn btn--primary',
                                 text: 'Crear pedido' });
    footer.append(
      el('button', { type: 'button', class: 'btn btn--ghost', text: 'Cancelar' }),
      crear);
    footer.firstChild.addEventListener('click', () => dialog.close());

    crear.addEventListener('click', async () => {
      crear.disabled = true;
      mensaje.textContent = 'Creando pedido…';
      mensaje.style.color = '#9AA4B2';
      const r = await LibraryServices.createOrder(
        getConfig(),
        [{ bookId: book.id, quantity: Number(cantidad.input.value || 1) }],
        { address: direccion.input.value.trim() });
      if (!r.ok) {
        mensaje.textContent = r.message;
        mensaje.style.color = '#F87171';
        crear.disabled = false;
        return;
      }
      dialog.close();
      window.alert(`Pedido ${r.data.orderNumber} creado por `
                   + `${money(r.data.total, r.data.currency)}.`);
      onOrderPlaced();          // el stock cambio: el catalogo se recarga
    });

    dialog.showModal();
    cantidad.input.focus();
  }

  /* ------------------------------------------------------------------ */
  /* Rastreo publico del envio                                          */
  /* ------------------------------------------------------------------ */

  function openTracking() {
    const { dialog, body, footer } = makeDialog(
      'Rastrear envio', 'Consulta publica: no necesita sesion');

    const numero = field('Numero de pedido', { type: 'text', value: 'PED-',
                                               placeholder: 'PED-000123' });
    body.appendChild(numero.wrap);
    notice(body,
      'Es el mismo endpoint que usaria una paqueteria para seguir el paquete, '
      + 'y por eso solo devuelve el estado del envio: ni cliente, ni importes, '
      + 'ni que libros lleva.', 'info');
    const resultado = el('div');
    body.appendChild(resultado);

    const consultar = el('button', { type: 'button', class: 'btn btn--primary',
                                     text: 'Consultar' });
    footer.append(
      el('button', { type: 'button', class: 'btn btn--ghost', text: 'Cerrar' }),
      consultar);
    footer.firstChild.addEventListener('click', () => dialog.close());

    async function buscar() {
      consultar.disabled = true;
      resultado.replaceChildren(el('p', { text: 'Consultando…' }));
      const r = await LibraryServices.trackShipment(getConfig(), numero.input.value);
      consultar.disabled = false;
      if (!r.ok) {
        resultado.replaceChildren(
          el('p', { text: r.message, style: 'color:#F87171' }));
        return;
      }
      const envio = r.data;
      resultado.replaceChildren(el('article', { class: 'panel-card' }, [
        el('h3', { text: envio.orderNumber }),
        el('div', { class: 'chips' }, [
          el('span', { class: 'chip chip--primary', text: envio.status }),
          el('span', { class: 'chip', text: `${envio.itemCount ?? 0} pieza(s)` }),
        ]),
        el('ul', { class: 'panel-list' }, [
          el('li', { text: `Paqueteria: ${envio.carrier || '—'}` }),
          el('li', { text: `Guia: ${envio.trackingCode || '—'}` }),
          el('li', { text: `Realizado: ${stamp(envio.placedAt)}` }),
          el('li', { text: `Enviado: ${stamp(envio.shippedAt)}` }),
          el('li', { text: `Entregado: ${stamp(envio.deliveredAt)}` }),
        ]),
      ]));
    }

    consultar.addEventListener('click', buscar);
    numero.input.addEventListener('keydown', (e) => { if (e.key === 'Enter') buscar(); });
    dialog.showModal();
    numero.input.focus();
    numero.input.setSelectionRange(4, 4);
  }

  return { init, openLogin, doLogout, openOrders, openTracking,
           openOrderForBook, openPayment, money, stamp };
})();
