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
  const { table } = options;

  // El uso de cada elemento (cuantos libros lo referencian) lo resuelve la
  // funcion library.fn_usage_count(entidad, id) de db/04_stored_procedures.sql.
  // Antes se construia aqui una subconsulta distinta por entidad concatenando
  // el nombre de la tabla puente: era el unico punto del sistema donde un
  // identificador viajaba dentro de una cadena SQL armada en JavaScript.
  // Ahora la entidad va como PARAMETRO y la funcion la resuelve con un CASE
  // sobre una lista cerrada; un nombre desconocido devuelve -1 sin consultar.

  return {
    table,

    async list({ search = '', limit = 50, offset = 0 } = {}) {
      return db.many(
        `SELECT t.id, t.name, library.fn_usage_count($4, t.id) AS books_count
           FROM library.${table} t
          WHERE ($1 = '' OR t.name ILIKE '%' || $1 || '%')
          ORDER BY t.name
          LIMIT $2 OFFSET $3`,
        [search, limit, offset, table]
      );
    },

    async count({ search = '' } = {}) {
      const row = await db.one(
        `SELECT COUNT(*)::int AS total FROM library.${table} t
          WHERE ($1 = '' OR t.name ILIKE '%' || $1 || '%')`,
        [search]
      );
      return row.total;
    },

    findById(id) {
      return db.one(`SELECT id, name FROM library.${table} WHERE id = $1`, [id]);
    },

    findByName(name) {
      return db.one(`SELECT id, name FROM library.${table} WHERE lower(name) = lower($1)`, [name]);
    },

    create(name) {
      return db.one(`INSERT INTO library.${table} (name) VALUES ($1) RETURNING id, name`, [name]);
    },

    update(id, name) {
      return db.one(`UPDATE library.${table} SET name = $2 WHERE id = $1 RETURNING id, name`, [id, name]);
    },

    remove(id) {
      return db.one(`DELETE FROM library.${table} WHERE id = $1 RETURNING id, name`, [id]);
    },

    async usageCount(id) {
      const row = await db.one('SELECT library.fn_usage_count($1, $2) AS total', [table, id]);
      return row && row.total > 0 ? row.total : 0;
    },

    /** Catalogo completo para poblar los <select> del formulario de libros. */
    all() {
      return db.many(`SELECT id, name FROM library.${table} ORDER BY name`);
    }
  };
};
