'use strict';

const db = require('../../config/database');

/**
 * Fabrica de modelos (capa Model del MVC) para las tablas de catalogo
 * con estructura (id, name): formats, categories, genres, authors, concepts.
 *
 * options:
 *   table          nombre de la tabla
 *   relationTable  tabla puente hacia books (para contar libros asociados)
 *   relationColumn columna de la tabla puente que apunta a esta tabla
 *   bookColumn     columna de books que apunta a esta tabla (catalogos 1:N)
 */
module.exports = function lookupModel(options) {
  const { table, relationTable = null, relationColumn = null, bookColumn = null } = options;

  const usageExpression = relationTable
    ? `(SELECT COUNT(*) FROM ${relationTable} r WHERE r.${relationColumn} = t.id)`
    : bookColumn
      ? `(SELECT COUNT(*) FROM books b WHERE b.${bookColumn} = t.id)`
      : '0';

  return {
    table,

    async list({ search = '', limit = 50, offset = 0 } = {}) {
      return db.many(
        `SELECT t.id, t.name, ${usageExpression}::int AS books_count
           FROM ${table} t
          WHERE ($1 = '' OR t.name ILIKE '%' || $1 || '%')
          ORDER BY t.name
          LIMIT $2 OFFSET $3`,
        [search, limit, offset]
      );
    },

    async count({ search = '' } = {}) {
      const row = await db.one(
        `SELECT COUNT(*)::int AS total FROM ${table} t
          WHERE ($1 = '' OR t.name ILIKE '%' || $1 || '%')`,
        [search]
      );
      return row.total;
    },

    findById(id) {
      return db.one(`SELECT id, name FROM ${table} WHERE id = $1`, [id]);
    },

    findByName(name) {
      return db.one(`SELECT id, name FROM ${table} WHERE lower(name) = lower($1)`, [name]);
    },

    create(name) {
      return db.one(`INSERT INTO ${table} (name) VALUES ($1) RETURNING id, name`, [name]);
    },

    update(id, name) {
      return db.one(`UPDATE ${table} SET name = $2 WHERE id = $1 RETURNING id, name`, [id, name]);
    },

    remove(id) {
      return db.one(`DELETE FROM ${table} WHERE id = $1 RETURNING id, name`, [id]);
    },

    async usageCount(id) {
      const row = await db.one(`SELECT ${usageExpression}::int AS total FROM ${table} t WHERE t.id = $1`, [id]);
      return row ? row.total : 0;
    },

    /** Catalogo completo para poblar los <select> del formulario de libros. */
    all() {
      return db.many(`SELECT id, name FROM ${table} ORDER BY name`);
    }
  };
};
