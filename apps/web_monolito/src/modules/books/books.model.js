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
 */
const db = require('../../config/database');

const ORDERS = {
  recent: 'b.created_at DESC, b.id DESC',
  title: 'b.title ASC',
  price_asc: 'b.price ASC, b.title ASC',
  price_desc: 'b.price DESC, b.title ASC',
  year_desc: 'b.publication_year DESC, b.title ASC'
};

/** Construye el WHERE dinamico compartido por list() y count(). */
const buildFilters = (filters = {}) => {
  const clauses = [];
  const params = [];

  if (filters.search) {
    params.push(`%${filters.search}%`);
    const i = params.length;
    clauses.push(`(b.title ILIKE $${i} OR b.isbn ILIKE $${i}
                   OR EXISTS (SELECT 1 FROM book_authors ba JOIN authors a ON a.id = ba.author_id
                               WHERE ba.book_id = b.id AND a.name ILIKE $${i}))`);
  }
  if (filters.genreId) {
    params.push(filters.genreId);
    clauses.push(`EXISTS (SELECT 1 FROM book_genres bg WHERE bg.book_id = b.id AND bg.genre_id = $${params.length})`);
  }
  if (filters.authorId) {
    params.push(filters.authorId);
    clauses.push(`EXISTS (SELECT 1 FROM book_authors ba WHERE ba.book_id = b.id AND ba.author_id = $${params.length})`);
  }
  if (filters.formatId) {
    params.push(filters.formatId);
    clauses.push(`b.format_id = $${params.length}`);
  }
  if (filters.categoryId) {
    params.push(filters.categoryId);
    clauses.push(`b.category_id = $${params.length}`);
  }
  if (filters.onlyAvailable) {
    clauses.push('b.stock > 0');
  }

  return { where: clauses.length ? `WHERE ${clauses.join(' AND ')}` : '', params };
};

const AUTHORS_AGG = `COALESCE((SELECT string_agg(a.name, ', ' ORDER BY a.name)
                                 FROM book_authors ba JOIN authors a ON a.id = ba.author_id
                                WHERE ba.book_id = b.id), '') AS authors`;

const GENRES_AGG = `COALESCE((SELECT string_agg(g.name, ', ' ORDER BY g.name)
                                FROM book_genres bg JOIN genres g ON g.id = bg.genre_id
                               WHERE bg.book_id = b.id), '') AS genres`;

const COVER = `(SELECT i.url FROM book_images i
                 WHERE i.book_id = b.id
                 ORDER BY i.is_cover DESC, i.id ASC LIMIT 1) AS cover_url`;

module.exports = {
  async list(filters = {}, { limit = 12, offset = 0, order = 'recent' } = {}) {
    const { where, params } = buildFilters(filters);
    const orderBy = ORDERS[order] || ORDERS.recent;
    params.push(limit, offset);

    return db.many(
      `SELECT b.id, b.isbn, b.title, b.publication_year, b.price, b.stock,
              f.name AS format_name, c.name AS category_name,
              ${AUTHORS_AGG}, ${GENRES_AGG}, ${COVER},
              (SELECT COUNT(*) FROM book_concepts bc WHERE bc.book_id = b.id)::int AS concepts_count,
              (SELECT COUNT(*) FROM book_images bi WHERE bi.book_id = b.id)::int AS images_count
         FROM books b
         JOIN formats f    ON f.id = b.format_id
         JOIN categories c ON c.id = b.category_id
         ${where}
        ORDER BY ${orderBy}
        LIMIT $${params.length - 1} OFFSET $${params.length}`,
      params
    );
  },

  async count(filters = {}) {
    const { where, params } = buildFilters(filters);
    const row = await db.one(`SELECT COUNT(*)::int AS total FROM books b ${where}`, params);
    return row.total;
  },

  findById(id) {
    return db.one(
      `SELECT b.*, f.name AS format_name, c.name AS category_name
         FROM books b
         JOIN formats f    ON f.id = b.format_id
         JOIN categories c ON c.id = b.category_id
        WHERE b.id = $1`,
      [id]
    );
  },

  findByIsbn(isbn) {
    return db.one('SELECT id, isbn, title FROM books WHERE isbn = $1', [isbn]);
  },

  // ---- Relaciones multivaluadas ---------------------------------------
  authorsOf(bookId) {
    return db.many(
      `SELECT a.id, a.name FROM book_authors ba JOIN authors a ON a.id = ba.author_id
        WHERE ba.book_id = $1 ORDER BY a.name`,
      [bookId]
    );
  },

  genresOf(bookId) {
    return db.many(
      `SELECT g.id, g.name FROM book_genres bg JOIN genres g ON g.id = bg.genre_id
        WHERE bg.book_id = $1 ORDER BY g.name`,
      [bookId]
    );
  },

  conceptsOf(bookId) {
    return db.many(
      `SELECT c.id AS concept_id, c.name, bc.definition
         FROM book_concepts bc JOIN concepts c ON c.id = bc.concept_id
        WHERE bc.book_id = $1 ORDER BY c.name`,
      [bookId]
    );
  },

  imagesOf(bookId) {
    return db.many(
      `SELECT id, book_id, url, is_cover, created_at FROM book_images
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
   * Alta de un libro y de todas sus relaciones dentro de una sola transaccion.
   * relations = { authorIds, genreIds, concepts: [{conceptId, definition}] }
   */
  create(data, relations) {
    return db.transaction(async (client) => {
      const { rows } = await client.query(
        `INSERT INTO books (isbn, title, publication_year, price, stock, format_id, category_id)
         VALUES ($1, $2, $3, $4, $5, $6, $7) RETURNING id`,
        [data.isbn, data.title, data.year, data.price, data.stock, data.formatId, data.categoryId]
      );
      const bookId = rows[0].id;
      await replaceRelations(client, bookId, relations);
      return bookId;
    });
  },

  update(id, data, relations) {
    return db.transaction(async (client) => {
      const { rowCount } = await client.query(
        `UPDATE books
            SET isbn = $2, title = $3, publication_year = $4, price = $5,
                stock = $6, format_id = $7, category_id = $8
          WHERE id = $1`,
        [id, data.isbn, data.title, data.year, data.price, data.stock, data.formatId, data.categoryId]
      );
      if (!rowCount) return false;
      await replaceRelations(client, id, relations);
      return true;
    });
  },

  /** El borrado en cascada del esquema elimina autores, generos, conceptos e imagenes. */
  remove(id) {
    return db.one('DELETE FROM books WHERE id = $1 RETURNING id, title', [id]);
  },

  // ---- CRUD de la relacion libro-concepto ------------------------------
  upsertConcept(bookId, conceptId, definition) {
    return db.one(
      `INSERT INTO book_concepts (book_id, concept_id, definition)
       VALUES ($1, $2, $3)
       ON CONFLICT (book_id, concept_id) DO UPDATE SET definition = EXCLUDED.definition
       RETURNING book_id, concept_id`,
      [bookId, conceptId, definition]
    );
  },

  removeConcept(bookId, conceptId) {
    return db.one(
      'DELETE FROM book_concepts WHERE book_id = $1 AND concept_id = $2 RETURNING concept_id',
      [bookId, conceptId]
    );
  },

  // ---- CRUD de imagenes -------------------------------------------------
  addImage(bookId, url, isCover = false) {
    return db.transaction(async (client) => {
      if (isCover) {
        await client.query('UPDATE book_images SET is_cover = FALSE WHERE book_id = $1', [bookId]);
      }
      const { rows } = await client.query(
        `INSERT INTO book_images (book_id, url, is_cover)
         VALUES ($1, $2, $3) RETURNING id, url, is_cover`,
        [bookId, url, isCover]
      );
      return rows[0];
    });
  },

  findImage(imageId) {
    return db.one('SELECT id, book_id, url, is_cover FROM book_images WHERE id = $1', [imageId]);
  },

  setCover(bookId, imageId) {
    return db.transaction(async (client) => {
      await client.query('UPDATE book_images SET is_cover = FALSE WHERE book_id = $1', [bookId]);
      const { rows } = await client.query(
        'UPDATE book_images SET is_cover = TRUE WHERE id = $1 AND book_id = $2 RETURNING id',
        [imageId, bookId]
      );
      return rows[0] || null;
    });
  },

  removeImage(imageId) {
    return db.one('DELETE FROM book_images WHERE id = $1 RETURNING id, book_id, url', [imageId]);
  }
};

/** Reescribe las relaciones multivaluadas del libro dentro de la transaccion activa. */
async function replaceRelations(client, bookId, relations = {}) {
  const { authorIds = [], genreIds = [], concepts = [] } = relations;

  await client.query('DELETE FROM book_authors WHERE book_id = $1', [bookId]);
  for (const authorId of authorIds) {
    await client.query(
      'INSERT INTO book_authors (book_id, author_id) VALUES ($1, $2) ON CONFLICT DO NOTHING',
      [bookId, authorId]
    );
  }

  await client.query('DELETE FROM book_genres WHERE book_id = $1', [bookId]);
  for (const genreId of genreIds) {
    await client.query(
      'INSERT INTO book_genres (book_id, genre_id) VALUES ($1, $2) ON CONFLICT DO NOTHING',
      [bookId, genreId]
    );
  }

  const keptConceptIds = concepts.map((c) => c.conceptId);
  if (keptConceptIds.length) {
    await client.query(
      'DELETE FROM book_concepts WHERE book_id = $1 AND concept_id <> ALL($2::int[])',
      [bookId, keptConceptIds]
    );
  } else {
    await client.query('DELETE FROM book_concepts WHERE book_id = $1', [bookId]);
  }
  for (const concept of concepts) {
    await client.query(
      `INSERT INTO book_concepts (book_id, concept_id, definition)
       VALUES ($1, $2, $3)
       ON CONFLICT (book_id, concept_id) DO UPDATE SET definition = EXCLUDED.definition`,
      [bookId, concept.conceptId, concept.definition]
    );
  }
}
