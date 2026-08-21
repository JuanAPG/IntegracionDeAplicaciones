'use strict';

/**
 * Modelo del modulo de usuarios.
 * FD: usuario_id -> nombre, email, password_hash, rol
 * Regla: como maximo un administrador (indice unico parcial ux_users_single_admin).
 */
const db = require('../../config/database');

const COLUMNS = 'id, full_name, email, role, is_active, created_at, updated_at';

module.exports = {
  list({ search = '', role = '', limit = 20, offset = 0 } = {}) {
    return db.many(
      `SELECT ${COLUMNS}
         FROM users
        WHERE ($1 = '' OR full_name ILIKE '%' || $1 || '%' OR email ILIKE '%' || $1 || '%')
          AND ($2 = '' OR role::text = $2)
        ORDER BY role, full_name
        LIMIT $3 OFFSET $4`,
      [search, role, limit, offset]
    );
  },

  async count({ search = '', role = '' } = {}) {
    const row = await db.one(
      `SELECT COUNT(*)::int AS total
         FROM users
        WHERE ($1 = '' OR full_name ILIKE '%' || $1 || '%' OR email ILIKE '%' || $1 || '%')
          AND ($2 = '' OR role::text = $2)`,
      [search, role]
    );
    return row.total;
  },

  findById(id) {
    return db.one(`SELECT ${COLUMNS} FROM users WHERE id = $1`, [id]);
  },

  findByEmail(email) {
    return db.one(
      `SELECT id, full_name, email, password_hash, role, is_active
         FROM users WHERE lower(email) = lower($1)`,
      [email]
    );
  },

  create({ fullName, email, passwordHash, role = 'user', isActive = true }) {
    return db.one(
      `INSERT INTO users (full_name, email, password_hash, role, is_active)
       VALUES ($1, $2, $3, $4::user_role, $5)
       RETURNING ${COLUMNS}`,
      [fullName, email, passwordHash, role, isActive]
    );
  },

  update(id, { fullName, email, role, isActive }) {
    return db.one(
      `UPDATE users
          SET full_name = $2, email = $3, role = $4::user_role, is_active = $5
        WHERE id = $1
        RETURNING ${COLUMNS}`,
      [id, fullName, email, role, isActive]
    );
  },

  updateProfile(id, { fullName, email }) {
    return db.one(
      `UPDATE users SET full_name = $2, email = $3 WHERE id = $1 RETURNING ${COLUMNS}`,
      [id, fullName, email]
    );
  },

  updatePassword(id, passwordHash) {
    return db.one(`UPDATE users SET password_hash = $2 WHERE id = $1 RETURNING id`, [id, passwordHash]);
  },

  getPasswordHash(id) {
    return db.one('SELECT password_hash FROM users WHERE id = $1', [id]);
  },

  remove(id) {
    return db.one(`DELETE FROM users WHERE id = $1 RETURNING id, full_name, role`, [id]);
  },

  async countAdmins(excludeId = null) {
    const row = await db.one(
      `SELECT COUNT(*)::int AS total FROM users
        WHERE role = 'admin' AND ($1::int IS NULL OR id <> $1::int)`,
      [excludeId]
    );
    return row.total;
  },

  async stats() {
    return db.one(
      `SELECT
         (SELECT COUNT(*) FROM users)::int      AS users,
         (SELECT COUNT(*) FROM books)::int      AS books,
         (SELECT COUNT(*) FROM authors)::int    AS authors,
         (SELECT COUNT(*) FROM genres)::int     AS genres,
         (SELECT COUNT(*) FROM concepts)::int   AS concepts,
         (SELECT COUNT(*) FROM book_images)::int AS images,
         (SELECT COUNT(*) FROM formats)::int    AS formats,
         (SELECT COUNT(*) FROM categories)::int AS categories,
         (SELECT COALESCE(SUM(stock), 0) FROM books)::int AS stock`
    );
  }
};
