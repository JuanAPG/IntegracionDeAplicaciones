'use strict';

/**
 * Acceso directo a PostgreSQL mediante un pool de conexiones (pg).
 * Toda consulta de la aplicacion pasa por este modulo.
 */
const { Pool } = require('pg');
const config = require('./env');

const pool = new Pool({
  host: config.db.host,
  port: config.db.port,
  database: config.db.database,
  user: config.db.user,
  password: config.db.password,
  max: 10,
  idleTimeoutMillis: 30000,
  // Toda conexion del pool trabaja sobre el esquema del modelo normalizado.
  options: `-c search_path=${config.db.schema},public`
});

pool.on('error', (err) => {
  console.error('[db] Error inesperado en el pool de PostgreSQL:', err.message);
});

/** Ejecuta una consulta parametrizada. */
const query = (text, params) => pool.query(text, params);

/** Devuelve la primera fila o null. */
const one = async (text, params) => {
  const { rows } = await pool.query(text, params);
  return rows[0] || null;
};

/** Devuelve todas las filas. */
const many = async (text, params) => {
  const { rows } = await pool.query(text, params);
  return rows;
};

/**
 * Ejecuta un bloque dentro de una transaccion.
 * Se usa en libros, donde una operacion toca varias tablas del modelo.
 */
const transaction = async (callback) => {
  const client = await pool.connect();
  try {
    await client.query('BEGIN');
    const result = await callback(client);
    await client.query('COMMIT');
    return result;
  } catch (error) {
    await client.query('ROLLBACK');
    throw error;
  } finally {
    client.release();
  }
};

module.exports = { pool, query, one, many, transaction };
