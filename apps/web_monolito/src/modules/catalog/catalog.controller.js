'use strict';

/**
 * Controlador del catalogo para usuarios registrados.
 * Reutiliza el modelo del modulo de libros (solo lectura).
 */
const asyncHandler = require('../../core/utils/asyncHandler');
const { str, intOrNull } = require('../../core/utils/validate');
const config = require('../../config/env');

const books = require('../books/books.model');
const authors = require('../authors/authors.model');
const genres = require('../genres/genres.model');
const formats = require('../formats/formats.model');
const categories = require('../categories/categories.model');

/**
 * Pagina de bienvenida publica.
 *
 * Solo publica totales agregados: el catalogo en si sigue reservado a
 * usuarios con sesion activa (requireLogin en catalog.routes).
 * Si PostgreSQL no responde, la portada se muestra igualmente sin cifras.
 */
const home = asyncHandler(async (req, res) => {
  if (req.session.user) {
    return res.redirect(`${config.basePath}${req.session.user.role === 'admin' ? '/admin' : '/catalog'}`);
  }

  // Las cifras salen de la vista library.v_catalog_stats: una sola fila y
  // una sola consulta, en lugar de cuatro conteos en paralelo.
  let highlights = null;
  try {
    highlights = await books.stats();
  } catch (err) {
    highlights = null;
  }

  return res.page('catalog/views/home', {
    title: 'Bienvenido',
    highlights,
    hasSpline: true
  });
});

const index = asyncHandler(async (req, res) => {
  const filters = {
    search: str(req.query.q),
    genreId: intOrNull(req.query.genre),
    authorId: intOrNull(req.query.author),
    formatId: intOrNull(req.query.format),
    categoryId: intOrNull(req.query.category),
    onlyAvailable: req.query.available === '1'
  };
  const order = str(req.query.order) || 'recent';
  const page = Math.max(1, Number.parseInt(req.query.page, 10) || 1);
  const pageSize = config.pagination.pageSize + 2;

  const [total, items, genreList, authorList, formatList, categoryList] = await Promise.all([
    books.count(filters),
    books.list(filters, { limit: pageSize, offset: (page - 1) * pageSize, order }),
    genres.all(), authors.all(), formats.all(), categories.all()
  ]);

  const params = [];
  Object.keys(req.query).forEach((key) => {
    if (key === 'page') return;
    const value = str(req.query[key]);
    if (value) params.push(`${encodeURIComponent(key)}=${encodeURIComponent(value)}`);
  });

  res.page('catalog/views/list', {
    title: 'Catalogo',
    items, total, filters, order,
    genreList, authorList, formatList, categoryList,
    pagination: {
      page,
      totalPages: Math.max(1, Math.ceil(total / pageSize)),
      baseUrl: `${config.basePath}/catalog${params.length ? `?${params.join('&')}` : ''}`
    }
  });
});

const show = asyncHandler(async (req, res) => {
  const book = await books.findFull(req.params.id);
  if (!book) {
    req.flash('error', 'El libro solicitado no existe.');
    return res.redirect(`${config.basePath}/catalog`);
  }
  const cover = book.images.find((image) => image.is_cover) || book.images[0] || null;
  return res.page('catalog/views/show', { title: book.title, book, cover });
});

module.exports = { home, index, show };
