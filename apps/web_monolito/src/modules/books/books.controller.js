'use strict';

/** Controlador CRUD de libros y de sus relaciones (autores, generos, conceptos, imagenes). */
const asyncHandler = require('../../core/utils/asyncHandler');
const { str, requiredStr, intOrNull, numberOrNull, intArray } = require('../../core/utils/validate');
const { removeUploadedFile } = require('../../core/middlewares/upload');
const config = require('../../config/env');

const model = require('./books.model');
const authors = require('../authors/authors.model');
const genres = require('../genres/genres.model');
const concepts = require('../concepts/concepts.model');
const formats = require('../formats/formats.model');
const categories = require('../categories/categories.model');

const BASE = `${config.basePath}/admin/books`;

/** Convierte un texto "A, B, C" en ids, creando los registros que no existan. */
const resolveNames = async (rawText, lookup) => {
  const names = str(rawText).split(',').map((n) => n.trim()).filter(Boolean);
  const ids = [];
  for (const name of names) {
    const found = await lookup.findByName(name);
    const record = found || (await lookup.create(name));
    ids.push(record.id);
  }
  return ids;
};

/** Lee y valida el formulario de alta/edicion de libro. */
const readBookForm = (body) => {
  const errors = [];
  const data = {
    isbn: requiredStr(body.isbn, 'ISBN', errors, 20),
    title: requiredStr(body.title, 'Titulo', errors, 255),
    year: intOrNull(body.publication_year),
    price: numberOrNull(body.price),
    stock: intOrNull(body.stock),
    formatId: intOrNull(body.format_id),
    categoryId: intOrNull(body.category_id)
  };

  const currentYear = new Date().getFullYear() + 1;
  if (data.year === null || data.year < 1 || data.year > currentYear) {
    errors.push(`El ano de publicacion debe estar entre 1 y ${currentYear}.`);
  }
  if (data.price === null || data.price < 0) errors.push('El precio debe ser un numero mayor o igual a 0.');
  if (data.stock === null || data.stock < 0) errors.push('El stock debe ser un entero mayor o igual a 0.');
  if (!data.formatId) errors.push('Debe seleccionar un formato.');
  if (!data.categoryId) errors.push('Debe seleccionar una categoria.');

  return { data, errors };
};

const readFilters = (query) => ({
  search: str(query.q),
  genreId: intOrNull(query.genre),
  authorId: intOrNull(query.author),
  formatId: intOrNull(query.format),
  categoryId: intOrNull(query.category)
});

const buildQueryString = (query, exclude = ['page']) => {
  const parts = [];
  Object.keys(query).forEach((key) => {
    if (exclude.includes(key)) return;
    const value = str(query[key]);
    if (value) parts.push(`${encodeURIComponent(key)}=${encodeURIComponent(value)}`);
  });
  return parts.length ? `?${parts.join('&')}` : '';
};

// ---------------------------------------------------------------------
// Listado y formularios
// ---------------------------------------------------------------------
const index = asyncHandler(async (req, res) => {
  const filters = readFilters(req.query);
  const order = str(req.query.order) || 'recent';
  const page = Math.max(1, Number.parseInt(req.query.page, 10) || 1);
  const pageSize = config.pagination.pageSize * 2;

  const [total, items, formatList, categoryList, genreList] = await Promise.all([
    model.count(filters),
    model.list(filters, { limit: pageSize, offset: (page - 1) * pageSize, order }),
    formats.all(),
    categories.all(),
    genres.all()
  ]);

  res.page('books/views/list', {
    title: 'Libros',
    items,
    total,
    filters,
    order,
    formatList,
    categoryList,
    genreList,
    query: req.query,
    pagination: {
      page,
      totalPages: Math.max(1, Math.ceil(total / pageSize)),
      baseUrl: `${BASE}${buildQueryString(req.query)}`
    }
  });
});

const loadFormCatalogs = () => Promise.all([formats.all(), categories.all(), authors.all(), genres.all()]);

const newForm = asyncHandler(async (req, res) => {
  const [formatList, categoryList, authorList, genreList] = await loadFormCatalogs();
  res.page('books/views/form', {
    title: 'Nuevo libro',
    book: {
      id: null, isbn: '', title: '', publication_year: new Date().getFullYear(),
      price: '0.00', stock: 0, format_id: null, category_id: null,
      authors: [], genres: [], concepts: [], images: []
    },
    formatList, categoryList, authorList, genreList,
    conceptList: []
  });
});

const create = asyncHandler(async (req, res) => {
  const { data, errors } = readBookForm(req.body);
  if (errors.length) {
    req.flash('error', errors);
    return res.redirect(`${BASE}/new`);
  }
  if (await model.findByIsbn(data.isbn)) {
    req.flash('error', `Ya existe un libro registrado con el ISBN ${data.isbn}.`);
    return res.redirect(`${BASE}/new`);
  }

  const authorIds = intArray(req.body.author_ids).concat(await resolveNames(req.body.new_authors, authors));
  const genreIds = intArray(req.body.genre_ids).concat(await resolveNames(req.body.new_genres, genres));

  const bookId = await model.create(data, { authorIds, genreIds, concepts: [] });
  req.flash('success', `Libro "${data.title}" creado. Agregue sus imagenes y conceptos.`);
  return res.redirect(`${BASE}/${bookId}/edit`);
});

const editForm = asyncHandler(async (req, res) => {
  const book = await model.findFull(req.params.id);
  if (!book) {
    req.flash('error', 'Libro no encontrado.');
    return res.redirect(BASE);
  }
  const [formatList, categoryList, authorList, genreList] = await loadFormCatalogs();
  const conceptList = await concepts.all();

  return res.page('books/views/form', {
    title: `Editar: ${book.title}`,
    book,
    formatList, categoryList, authorList, genreList, conceptList
  });
});

const update = asyncHandler(async (req, res) => {
  const id = Number.parseInt(req.params.id, 10);
  const { data, errors } = readBookForm(req.body);
  if (errors.length) {
    req.flash('error', errors);
    return res.redirect(`${BASE}/${id}/edit`);
  }

  const duplicate = await model.findByIsbn(data.isbn);
  if (duplicate && duplicate.id !== id) {
    req.flash('error', `El ISBN ${data.isbn} ya pertenece a otro libro.`);
    return res.redirect(`${BASE}/${id}/edit`);
  }

  const authorIds = intArray(req.body.author_ids).concat(await resolveNames(req.body.new_authors, authors));
  const genreIds = intArray(req.body.genre_ids).concat(await resolveNames(req.body.new_genres, genres));

  // Los conceptos se administran con sus propios formularios (addConcept /
  // updateConcept / removeConcept); aqui solo se conservan tal como estan.
  const existing = await model.conceptsOf(id);
  const keptConcepts = existing.map((c) => ({ conceptId: c.concept_id, definition: c.definition }));

  const ok = await model.update(id, data, { authorIds, genreIds, concepts: keptConcepts });
  if (!ok) {
    req.flash('error', 'Libro no encontrado.');
    return res.redirect(BASE);
  }

  req.flash('success', `Libro "${data.title}" actualizado.`);
  return res.redirect(`${BASE}/${id}/edit`);
});

const destroy = asyncHandler(async (req, res) => {
  const images = await model.imagesOf(req.params.id);
  const removed = await model.remove(req.params.id);
  if (!removed) {
    req.flash('error', 'Libro no encontrado.');
    return res.redirect(BASE);
  }
  images.forEach((image) => removeUploadedFile(image.url));
  req.flash('success', `Libro "${removed.title}" eliminado junto con sus autores, generos, conceptos e imagenes.`);
  return res.redirect(BASE);
});

// ---------------------------------------------------------------------
// Relacion libro-concepto: (libro, concepto) -> definicion
// ---------------------------------------------------------------------
const addConcept = asyncHandler(async (req, res) => {
  const bookId = Number.parseInt(req.params.id, 10);
  const errors = [];
  const definition = requiredStr(req.body.definition, 'Definicion', errors, 5000);
  let conceptId = intOrNull(req.body.concept_id);
  const newName = str(req.body.new_concept);

  if (!conceptId && !newName) errors.push('Seleccione un concepto existente o escriba uno nuevo.');
  if (errors.length) {
    req.flash('error', errors);
    return res.redirect(`${BASE}/${bookId}/edit`);
  }

  if (!conceptId) {
    const found = await concepts.findByName(newName);
    conceptId = (found || (await concepts.create(newName))).id;
  }

  await model.upsertConcept(bookId, conceptId, definition);
  req.flash('success', 'Definicion del concepto guardada para este libro.');
  return res.redirect(`${BASE}/${bookId}/edit`);
});

const updateConcept = asyncHandler(async (req, res) => {
  const bookId = Number.parseInt(req.params.id, 10);
  const conceptId = Number.parseInt(req.params.conceptId, 10);
  const errors = [];
  const definition = requiredStr(req.body.definition, 'Definicion', errors, 5000);
  if (errors.length) {
    req.flash('error', errors);
    return res.redirect(`${BASE}/${bookId}/edit`);
  }
  await model.upsertConcept(bookId, conceptId, definition);
  req.flash('success', 'Definicion actualizada.');
  return res.redirect(`${BASE}/${bookId}/edit`);
});

const removeConcept = asyncHandler(async (req, res) => {
  const bookId = Number.parseInt(req.params.id, 10);
  const conceptId = Number.parseInt(req.params.conceptId, 10);
  const removed = await model.removeConcept(bookId, conceptId);
  req.flash(removed ? 'success' : 'error', removed
    ? 'Concepto retirado del libro.'
    : 'El concepto no estaba asociado a este libro.');
  return res.redirect(`${BASE}/${bookId}/edit`);
});

// ---------------------------------------------------------------------
// Imagenes del libro
// ---------------------------------------------------------------------
const uploadImage = asyncHandler(async (req, res) => {
  const bookId = Number.parseInt(req.params.id, 10);
  if (req.fileValidationError) {
    req.flash('error', req.fileValidationError);
    return res.redirect(`${BASE}/${bookId}/edit`);
  }
  if (!req.file) {
    req.flash('error', 'Seleccione un archivo de imagen.');
    return res.redirect(`${BASE}/${bookId}/edit`);
  }
  const book = await model.findById(bookId);
  if (!book) {
    removeUploadedFile(`${config.uploads.publicPath}/${req.file.filename}`);
    req.flash('error', 'Libro no encontrado.');
    return res.redirect(BASE);
  }

  const url = `${config.uploads.publicPath}/${req.file.filename}`;
  const existing = await model.imagesOf(bookId);
  const isCover = req.body.is_cover === 'on' || existing.length === 0;

  await model.addImage(bookId, url, isCover);
  req.flash('success', 'Imagen cargada correctamente.');
  return res.redirect(`${BASE}/${bookId}/edit`);
});

const setCover = asyncHandler(async (req, res) => {
  const bookId = Number.parseInt(req.params.id, 10);
  const updated = await model.setCover(bookId, Number.parseInt(req.params.imageId, 10));
  req.flash(updated ? 'success' : 'error', updated ? 'Portada actualizada.' : 'Imagen no encontrada.');
  return res.redirect(`${BASE}/${bookId}/edit`);
});

const removeImage = asyncHandler(async (req, res) => {
  const bookId = Number.parseInt(req.params.id, 10);
  const removed = await model.removeImage(Number.parseInt(req.params.imageId, 10));
  if (!removed) {
    req.flash('error', 'Imagen no encontrada.');
    return res.redirect(`${BASE}/${bookId}/edit`);
  }
  removeUploadedFile(removed.url);
  req.flash('success', 'Imagen eliminada.');
  return res.redirect(`${BASE}/${bookId}/edit`);
});

module.exports = {
  index, newForm, create, editForm, update, destroy,
  addConcept, updateConcept, removeConcept,
  uploadImage, setCover, removeImage
};
