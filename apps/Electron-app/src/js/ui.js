/* =====================================================================
   ui.js — Capa de presentacion (View).

   Todo el DOM se construye con createElement y textContent. Los datos
   provienen de un XML remoto, de modo que nunca se interpolan como HTML.

   Reglas de UI/UX aplicadas:
     * Los esqueletos de carga replican la forma de la tarjeta real para
       que la rejilla no salte al llegar los datos.
     * Estados vacios y de error con mensaje util y accion de reintento.
     * Iconos SVG en linea, decorativos (aria-hidden).
     * Las portadas se cargan de forma diferida y reservan su espacio.
   ===================================================================== */

'use strict';

const LibraryUI = (() => {
  const SVG_NS = 'http://www.w3.org/2000/svg';

  /* --- Constructores ------------------------------------------------ */

  /** Crea un elemento con atributos y descendientes en una sola llamada. */
  function el(tag, attrs = {}, children = []) {
    const node = document.createElement(tag);

    for (const [key, value] of Object.entries(attrs)) {
      if (value === null || value === undefined || value === false) continue;
      if (key === 'class') node.className = value;
      else if (key === 'text') node.textContent = value;
      else if (key === 'dataset') Object.assign(node.dataset, value);
      else if (key.startsWith('on') && typeof value === 'function') {
        node.addEventListener(key.slice(2).toLowerCase(), value);
      } else node.setAttribute(key, value === true ? '' : String(value));
    }

    for (const child of [].concat(children)) {
      if (child === null || child === undefined || child === false) continue;
      node.append(typeof child === 'string' ? document.createTextNode(child) : child);
    }
    return node;
  }

  /** Icono decorativo tomado del sprite SVG de index.html. */
  function icon(id, className = 'btn__icon') {
    const svg = document.createElementNS(SVG_NS, 'svg');
    svg.setAttribute('viewBox', '0 0 24 24');
    svg.setAttribute('aria-hidden', 'true');
    svg.setAttribute('focusable', 'false');
    if (className) svg.setAttribute('class', className);
    const use = document.createElementNS(SVG_NS, 'use');
    use.setAttribute('href', '#' + id);
    svg.append(use);
    return svg;
  }

  /* --- Formato ------------------------------------------------------ */

  const formatPrice = (book) => {
    if (book.price === null) return book.priceRaw || 'Sin precio';
    return book.price.toLocaleString('es-MX', {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    });
  };

  /** Nivel de existencias: color + texto, nunca solo color. */
  function stockInfo(stock) {
    if (stock <= 0) return { level: 'out', label: 'Agotado' };
    if (stock <= 5) return { level: 'low', label: `${stock} en stock` };
    return { level: 'ok', label: `${stock} en stock` };
  }

  const coverOf = (book) =>
    book.images.find((img) => img.isCover) || book.images[0] || null;

  const authorNames = (book) =>
    book.authors.length ? book.authors.map((a) => a.name).join(', ') : 'Autor no registrado';

  /* --- Portadas ----------------------------------------------------- */

  /**
   * Contenedor de portada con espacio reservado por aspect-ratio.
   * Si la imagen falla, se sustituye por el marcador de posicion en
   * lugar de dejar un hueco roto.
   */
  function coverFigure(book, className) {
    const cover = coverOf(book);
    const box = el('div', { class: className });
    const fallback = el('span', { class: 'cover-fallback' }, [icon('i-book', '')]);

    if (!cover) {
      box.append(fallback);
      return box;
    }

    const img = el('img', {
      src: cover.url,
      alt: `Portada de ${book.title}`,
      loading: 'lazy',
      decoding: 'async',
    });

    const showFallback = () => {
      img.remove();
      if (!box.contains(fallback)) box.append(fallback);
    };

    // Una portada ausente no siempre falla de forma limpia: el servidor
    // de imagenes puede responder 302 con cero bytes, en cuyo caso no se
    // dispara "error" y la imagen simplemente no decodifica. Por eso se
    // comprueba tambien el ancho real una vez terminada la carga.
    const verify = () => { if (!img.naturalWidth) showFallback(); };

    img.addEventListener('error', showFallback, { once: true });
    img.addEventListener('load', verify, { once: true });

    box.append(img);
    if (img.complete) verify();   // la imagen ya estaba en cache
    return box;
  }

  /* --- Tarjeta del catalogo ----------------------------------------- */

  /**
   * La tarjeta completa es un <button>: rol, foco y activacion con
   * teclado los aporta el navegador.
   */
  function bookCard(book, onSelect) {
    const stock = stockInfo(book.stock);
    const genres = book.genres.slice(0, 2);
    const extraGenres = book.genres.length - genres.length;

    const cover = coverFigure(book, 'book-card__cover');
    cover.append(el('span', {
      class: 'book-card__badge',
      dataset: { stock: stock.level },
      text: stock.label,
    }));

    return el('button', {
      type: 'button',
      class: 'book-card',
      'aria-label': `Ver la ficha de ${book.title}`,
      onclick: () => onSelect(book),
    }, [
      cover,
      el('h3', { class: 'book-card__title', text: book.title }),
      el('p', { class: 'book-card__authors', text: authorNames(book) }),
      el('ul', { class: 'chips' }, [
        el('li', { class: 'chip chip--accent', text: book.format || 'Formato n/d' }),
        ...genres.map((g) => el('li', { class: 'chip', text: g.name })),
        extraGenres > 0 ? el('li', { class: 'chip', text: `+${extraGenres}` }) : null,
      ]),
      el('div', { class: 'book-card__foot' }, [
        el('p', { class: 'price' }, [
          formatPrice(book),
          el('span', { class: 'price__currency', text: book.currency || '' }),
        ]),
        el('span', { class: 'chip', text: book.publicationYear || 's/f' }),
      ]),
    ]);
  }

  /* --- Renderizadores de la rejilla --------------------------------- */

  /** Esqueletos con la forma exacta de la tarjeta: sin salto de layout. */
  function renderSkeletons(container, count) {
    const list = el('div', { class: 'grid' });
    for (let i = 0; i < count; i += 1) {
      list.append(el('div', { class: 'skeleton' }, [
        el('div', { class: 'skeleton__block skeleton__cover' }),
        el('div', { class: 'skeleton__block skeleton__line' }),
        el('div', { class: 'skeleton__block skeleton__line skeleton__line--short' }),
      ]));
    }
    container.replaceChildren(list);
  }

  function renderGrid(container, books, onSelect) {
    const list = el('ul', { class: 'grid' });
    books.forEach((book) => list.append(el('li', {}, [bookCard(book, onSelect)])));
    container.replaceChildren(list);
  }

  /**
   * Estado informativo o de error. Siempre ofrece una salida: el error
   * nunca se queda sin camino de recuperacion.
   */
  function renderState(container, { variant = 'info', iconId, title, message, detail, actions = [] }) {
    const buttons = actions.map((action) =>
      el('button', {
        type: 'button',
        class: action.primary ? 'btn btn--primary' : 'btn btn--ghost',
        text: action.label,
        onclick: action.onClick,
      })
    );

    container.replaceChildren(el('section', {
      class: `state state--${variant}`,
      role: variant === 'error' ? 'alert' : null,
    }, [
      el('span', { class: 'state__icon' }, [icon(iconId || 'i-search', '')]),
      el('h3', { class: 'state__title', text: title }),
      el('p', { class: 'state__message', text: message }),
      detail ? el('p', { class: 'state__detail mono', text: detail }) : null,
      buttons.length ? el('div', { class: 'state__actions' }, buttons) : null,
    ]));
  }

  /* --- Ficha completa del libro ------------------------------------- */

  const spec = (label, value) =>
    el('div', { class: 'specs__item' }, [
      el('dt', { class: 'specs__label', text: label }),
      el('dd', { class: 'specs__value', text: value || 'No disponible' }),
    ]);

  const sectionTitle = (iconId, label) =>
    el('h4', { class: 'section__title' }, [icon(iconId, ''), label]);

  /** Galeria con miniaturas conmutables (aria-pressed refleja la activa). */
  function gallery(book) {
    const box = coverFigure(book, 'detail__cover');
    const wrap = el('div', { class: 'detail__gallery' }, [box]);
    if (book.images.length < 2) return wrap;

    const thumbs = el('div', { class: 'detail__thumbs' });
    book.images.forEach((image, index) => {
      const button = el('button', {
        type: 'button',
        class: 'detail__thumb',
        'aria-pressed': index === 0 ? 'true' : 'false',
        'aria-label': `Mostrar imagen ${index + 1} de ${book.images.length}`,
      }, [el('img', { src: image.url, alt: '', loading: 'lazy' })]);

      button.addEventListener('click', () => {
        const main = box.querySelector('img');
        if (main) main.src = image.url;
        thumbs.querySelectorAll('.detail__thumb')
          .forEach((t) => t.setAttribute('aria-pressed', t === button ? 'true' : 'false'));
      });
      thumbs.append(button);
    });

    wrap.append(thumbs);
    return wrap;
  }

  function renderBookDetail(container, book) {
    const stock = stockInfo(book.stock);

    const details = el('div', { class: 'detail__main' }, [
      el('dl', { class: 'specs' }, [
        spec('ISBN', book.isbn),
        spec('Ano de publicacion', book.publicationYear),
        spec('Precio', `${formatPrice(book)} ${book.currency}`.trim()),
        spec('Existencias', stock.label),
        spec('Formato', book.format),
        spec('Categoria', book.category),
      ]),

      el('section', { class: 'section' }, [
        sectionTitle('i-users', book.authors.length === 1 ? 'Autor' : 'Autores'),
        book.authors.length
          ? el('ul', { class: 'chips' },
              book.authors.map((a) => el('li', { class: 'chip chip--primary', text: a.name })))
          : el('p', { class: 'empty-note', text: 'El libro no tiene autores registrados.' }),
      ]),

      el('section', { class: 'section' }, [
        sectionTitle('i-tag', book.genres.length === 1 ? 'Genero' : 'Generos'),
        book.genres.length
          ? el('ul', { class: 'chips' },
              book.genres.map((g) => el('li', { class: 'chip', text: g.name })))
          : el('p', { class: 'empty-note', text: 'El libro no tiene generos asignados.' }),
      ]),

      el('section', { class: 'section' }, [
        sectionTitle('i-lightbulb', `Conceptos definidos (${book.concepts.length})`),
        book.concepts.length
          ? el('div', { class: 'concepts' }, book.concepts.map((c) =>
              el('article', { class: 'concept' }, [
                el('h5', { class: 'concept__name', text: c.name }),
                el('p', { class: 'concept__definition', text: c.definition || 'Sin definicion registrada.' }),
              ])))
          : el('p', { class: 'empty-note', text: 'Este libro no define conceptos.' }),
      ]),

      el('section', { class: 'section' }, [
        sectionTitle('i-image', `Imagenes (${book.images.length})`),
        book.images.length
          ? el('ul', { class: 'chips' }, book.images.map((img, i) =>
              el('li', { class: img.isCover ? 'chip chip--accent' : 'chip',
                         text: img.isCover ? 'Portada' : `Imagen ${i + 1}` })))
          : el('p', { class: 'empty-note', text: 'El libro no tiene imagenes registradas.' }),
      ]),
    ]);

    container.replaceChildren(el('div', { class: 'detail' }, [gallery(book), details]));
  }

  return { el, icon, renderSkeletons, renderGrid, renderState, renderBookDetail, authorNames };
})();
