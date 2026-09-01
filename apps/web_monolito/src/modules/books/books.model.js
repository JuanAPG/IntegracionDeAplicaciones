'use strict';

/**
 * Modelo del modulo de libros.
 *
 * Dependencias funcionales:
 *   ISBN -> titulo, ano, precio, stock, formato, categoria
 * Dependencias multivaluadas (tablas propias):
 *   libro ->> autor              (book_authors)
 *   libro ->> genero             (book_genres)
 *   libro ->> imagen             (book_images)
 *   libro ->> (concepto, def.)   (book_concepts, con definicion por par)
 *
 * ---------------------------------------------------------------------
 * REPARTO CON LA BASE DE DATOS
 *
 *   LECTURA   sobre la vista library.v_books_catalog (db/06_views.sql),
 *             que ya reune autores, generos, portada y conteos. Este
 *             modelo solo compone el WHERE y elige el ORDER BY.
 *
 *   ESCRITURA que toca varias tablas -> funciones almacenadas
 *             (db/04_stored_procedures.sql): sp_create_book,
 *             sp_update_book, sp_upsert_book_concept, sp_set_cover.
 *             La atomicidad la garantiza el motor y cada alta es un
 *             unico viaje de red en lugar de 3 + N.
 *
 *   El inventario de como estaban escritas antes estas consultas esta
 *   en db/03_all_quieries_before_stored_procedures.sql.
 * ---------------------------------------------------------------------
 */
const db = require('../../config/database');

/**
 * Lista blanca de ordenamientos.
 * El ORDER BY es un IDENTIFICADOR y no admite parametro $1, de modo que
 * es el unico fragmento que no se puede parametrizar. Se resuelve aqui
 * con una lista cerrada: un valor arbitrario en ?order= cae en el valor
 * por defecto y nunca llega al SQL.
 * Las columnas son las de la vista, sin prefijo de tabla.
 */
const ORDERS = {
  recent: 'created_at DESC, id DESC',
  title: 'title ASC',
  price_asc: 'price ASC, title ASC',
  price_desc: 'price DESC, title ASC',
  year_desc: 'publication_year DESC, title ASC'
};

/**
 * Construye el WHERE dinamico compartido por list() y count().
 * Todas las columnas referenciadas pertenecen a v_books_catalog.
 */
const buildFilters = (filters = {}) => {
  const clauses = [];
  const params = [];

  if (filters.search) {
    params.push(`%${filters.search}%`);
    const i = params.length;
    // La vista ya trae los autores agregados como texto: la busqueda por
    // autor deja de necesitar un EXISTS con subconsulta.
    clauses.push(`(v.title ILIKE $${i} OR v.isbn ILIKE $${i} OR v.authors ILIKE $${i})`);
  }
  if (filters.genreId) {
    params.push(filters.genreId);
    clauses.push(`$${params.length} = ANY (v.genre_ids)`);
  }
  if (filters.authorId) {
    params.push(filters.authorId);
    clauses.push(`$${params.length} = ANY (v.author_ids)`);
  }
  if (filters.formatId) {
    params.push(filters.formatId);
    clauses.push(`v.format_id = $${params.length}`);
  }
  if (filters.categoryId) {
    params.push(filters.categoryId);
    clauses.push(`v.category_id = $${params.length}`);
  }
  if (filters.onlyAvailable) {
    clauses.push('v.stock > 0');
  }

  return { where: clauses.length ? `WHERE ${clauses.join(' AND ')}` : '', params };
};

module.exports = {
  /** Listado del catalogo. Toda la agregacion vive en la vista. */
  async list(filters = {}, { limit = 12, offset = 0, order = 'recent' } = {}) {
    const { where, params } = buildFilters(filters);
    const orderBy = ORDERS[order] || ORDERS.recent;
    params.push(limit, offset);

    return db.many(
      `SELECT v.id, v.isbn, v.title, v.publication_year, v.price, v.stock,
              v.format_name, v.category_name, v.authors, v.genres,
              v.cover_url, v.concepts_count, v.images_count
         FROM library.v_books_catalog v
         ${where}
        ORDER BY ${orderBy}
        LIMIT $${params.length - 1} OFFSET $${params.length}`,
      params
    );
  },

  /**
   * Total de resultados para la paginacion.
   * Se cuenta sobre la misma vista para que el WHERE sea literalmente el
   * mismo que el del listado: dos expresiones distintas acaban
   * divergiendo y produciendo una paginacion que no cuadra con la lista.
   */
  async count(filters = {}) {
    const { where, params } = buildFilters(filters);
    const row = await db.one(
      `SELECT COUNT(*)::int AS total FROM library.v_books_catalog v ${where}`,
      params
    );
    return row.total;
  },

  /** Cifras agregadas de la portada publica (una fila, una consulta). */
  stats() {
    return db.one('SELECT * FROM library.v_catalog_stats');
  },

  findById(id) {
    return db.one(
      `SELECT b.*, f.name AS format_name, c.name AS category_name
         FROM library.books b
         JOIN library.formats f    ON f.id = b.format_id
         JOIN library.categories c ON c.id = b.category_id
        WHERE b.id = $1`,
      [id]
    );
  },

  /**
   * Busqueda por ISBN para detectar duplicados.
   * Se normaliza igual que en el disparador trg_books_normalize
   * (upper + btrim): de otro modo " 978-x " se veria como un ISBN nuevo
   * y el UNIQUE lo rechazaria despues con un error menos claro.
   */
  findByIsbn(isbn) {
    return db.one(
      'SELECT id, isbn, title FROM library.books WHERE isbn = upper(btrim($1))',
      [isbn]
    );
  },

  // ---- Relaciones multivaluadas ---------------------------------------
  authorsOf(bookId) {
    return db.many(
      `SELECT a.id, a.name
         FROM library.book_authors ba
         JOIN library.authors a ON a.id = ba.author_id
        WHERE ba.book_id = $1 ORDER BY a.name`,
      [bookId]
    );
  },

  genresOf(bookId) {
    return db.many(
      `SELECT g.id, g.name
         FROM library.book_genres bg
         JOIN library.genres g ON g.id = bg.genre_id
        WHERE bg.book_id = $1 ORDER BY g.name`,
      [bookId]
    );
  },

  /** (libro, concepto) -> definicion: la relacion central del modelo. */
  conceptsOf(bookId) {
    return db.many(
      `SELECT concept_id, concept_name AS name, definition
         FROM library.v_book_concepts
        WHERE book_id = $1 ORDER BY concept_name`,
      [bookId]
    );
  },

  imagesOf(bookId) {
    return db.many(
      `SELECT id, book_id, url, is_cover, created_at FROM library.book_images
        WHERE book_id = $1 ORDER BY is_cover DESC, id ASC`,
      [bookId]
    );
  },

  /** Carga el libro con todas sus relaciones (vista de detalle y edicion). */
  async findFull(id) {
    const book = await this.findById(id);
    if (!book) return null;
    const [authors, genres, concepts, images] = await Promise.all([
      this.authorsOf(id), this.genresOf(id), this.conceptsOf(id), this.imagesOf(id)
    ]);
    return Object.assign(book, { authors, genres, concepts, images });
  },

  // ---- Escritura -------------------------------------------------------
  /**
   * Alta del libro y de sus relaciones en UNA sola operacion atomica.
   * relations = { authorIds, genreIds }
   */
  async create(data, relations = {}) {
    const row = await db.one(
      `SELECT library.sp_create_book(
                $1::varchar, $2::varchar, $3::smallint, $4::numeric, $5::int,
                $6::int, $7::int, $8::int[], $9::int[]
              ) AS id`,
      [data.isbn, data.title, data.year, data.price, data.stock,
       data.formatId, data.categoryId,
       relations.authorIds || [], relations.genreIds || []]
    );
    return row.id;
  },

  /**
   * Edicion del libro y reescritura de autores y generos.
   * Las definiciones de conceptos NO se tocan: tienen sus propios
   * formularios (addConcept / updateConcept / removeConcept).
   * Devuelve false si el libro no existe.
   */
  async update(id, data, relations = {}) {
    const row = await db.one(
      `SELECT library.sp_update_book(
                $1::int, $2::varchar, $3::varchar, $4::smallint, $5::numeric,
                $6::int, $7::int, $8::int, $9::int[], $10::int[]
              ) AS ok`,
      [id, data.isbn, data.title, data.year, data.price, data.stock,
       data.formatId, data.categoryId,
       relations.authorIds || [], relations.genreIds || []]
    );
    return row.ok === true;
  },

  /** El borrado en cascada del esquema elimina autores, generos, conceptos e imagenes. */
  remove(id) {
    return db.one('DELETE FROM library.books WHERE id = $1 RETURNING id, title', [id]);
  },

  // ---- CRUD de la relacion libro-concepto ------------------------------
  async upsertConcept(bookId, conceptId, definition) {
    await db.query(
      'SELECT library.sp_upsert_book_concept($1::int, $2::int, $3::text)',
      [bookId, conceptId, definition]
    );
    return { book_id: bookId, concept_id: conceptId };
  },

  removeConcept(bookId, conceptId) {
    return db.one(
      'DELETE FROM library.book_concepts WHERE book_id = $1 AND concept_id = $2 RETURNING concept_id',
      [bookId, conceptId]
    );
  },

  // ---- CRUD de imagenes -------------------------------------------------
  /**
   * Alta de imagen. Si se pide como portada, la funcion degrada la
   * anterior en la misma operacion: el indice unico parcial
   * ux_book_images_one_cover rechazaria dos portadas simultaneas.
   * Si el libro no tenia ninguna imagen, el disparador
   * trg_book_images_first_cover la marca como portada automaticamente.
   */
  async addImage(bookId, url, isCover = false) {
    return db.one(
      'SELECT * FROM library.sp_add_book_image($1::int, $2::varchar, $3::boolean)',
      [bookId, url, isCover]
    );
  },

  findImage(imageId) {
    return db.one('SELECT id, book_id, url, is_cover FROM library.book_images WHERE id = $1', [imageId]);
  },

  /** Devuelve el id promovido, o null si la imagen no es de ese libro. */
  async setCover(bookId, imageId) {
    const row = await db.one('SELECT library.sp_set_cover($1::int, $2::int) AS id', [bookId, imageId]);
    return row && row.id ? { id: row.id } : null;
  },

  removeImage(imageId) {
    return db.one('DELETE FROM library.book_images WHERE id = $1 RETURNING id, book_id, url', [imageId]);
  }
};
