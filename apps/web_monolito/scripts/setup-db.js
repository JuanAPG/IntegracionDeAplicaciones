'use strict';

/**
 * Instalacion de la base de datos a partir de los scripts de db/.
 *
 *   node scripts/setup-db.js              aplica estructura y objetos (si faltan),
 *                                         carga datos y asegura el administrador
 *   node scripts/setup-db.js --reset      elimina el esquema library y lo recrea
 *   node scripts/setup-db.js --seed-only  solo datos + administrador
 *   node scripts/setup-db.js --no-demo    estructura y administrador, sin datos
 *
 * ---------------------------------------------------------------------
 * ORDEN DE CARGA  (no es el orden numerico, y hay un motivo para cada paso)
 *
 *   01_schema.sql        tablas, tipos, restricciones e indices
 *   06_views.sql         vistas: solo dependen de las tablas
 *   04_stored_procedures funciones: fn_search_books devuelve
 *                        SETOF v_books_catalog, asi que las vistas
 *                        tienen que existir antes
 *   05_triggers.sql      disparadores: se crean ANTES de cargar datos
 *                        para que el seed pase por ellos
 *   02_seed_*.sql        datos de demostracion
 *
 * NO se ejecutan:
 *   00_create_database.sql  requiere superusuario y se lanza a mano una
 *                           sola vez:  psql -U postgres -f db/00_create_database.sql
 *   03_all_quieries_*.sql   es documentacion: el inventario de consultas
 *                           previo a las funciones almacenadas.
 * ---------------------------------------------------------------------
 */
const fs = require('fs');
const path = require('path');

const config = require('../src/config/env');
const db = require('../src/config/database');
const password = require('../src/core/utils/password');

const DB_DIR = path.resolve(__dirname, '..', '..', '..', 'db');

/** Archivos que aplica el instalador, en orden de dependencia. */
const STRUCTURE_FILES = [
  { file: '01_schema.sql',           label: 'estructura (tablas, restricciones, indices)' },
  { file: '06_views.sql',            label: 'vistas' },
  { file: '04_stored_procedures.sql', label: 'funciones y procedimientos' },
  { file: '05_triggers.sql',         label: 'disparadores' }
];
const SEED_FILE = '02_seed_30_per_table.sql';

/** Archivos que existen pero NO ejecuta el instalador, y por que. */
const SKIPPED = [
  ['00_create_database.sql', 'requiere superusuario; ejecutelo con psql -U postgres'],
  ['03_all_quieries_before_stored_procedures.sql', 'es documentacion, no se ejecuta']
];

const args = process.argv.slice(2);
const has = (flag) => args.includes(flag);
const log = (message) => console.log(`[setup-db] ${message}`);

const readSql = (name) => {
  const full = path.join(DB_DIR, name);
  if (!fs.existsSync(full)) throw new Error(`No se encontro el script: ${full}`);
  return fs.readFileSync(full, 'utf8');
};

async function schemaExists() {
  const row = await db.one(
    'SELECT 1 AS found FROM information_schema.schemata WHERE schema_name = $1',
    [config.db.schema]
  );
  return Boolean(row);
}

async function applyStructure() {
  if (has('--reset')) {
    log(`Eliminando el esquema "${config.db.schema}" (--reset)...`);
    await db.query(`DROP SCHEMA IF EXISTS ${config.db.schema} CASCADE`);
  } else if (await schemaExists()) {
    log(`El esquema "${config.db.schema}" ya existe; se reaplican vistas, funciones y disparadores.`);
    // 01_schema.sql usa CREATE ... IF NOT EXISTS y los demas usan
    // CREATE OR REPLACE, de modo que reaplicarlos es seguro e idempotente.
  }

  for (const { file, label } of STRUCTURE_FILES) {
    log(`Aplicando db/${file}  (${label})...`);
    await db.query(readSql(file));
  }
  log('Estructura y objetos programables al dia.');
}

async function applySeed() {
  if (has('--no-demo')) {
    log('Datos de demostracion omitidos (--no-demo).');
    return;
  }
  log(`Cargando db/${SEED_FILE} (30 filas por tabla, idempotente)...`);
  await db.query(readSql(SEED_FILE));
  log('Datos de demostracion cargados.');
}

/**
 * El seed ya incluye un administrador con hash bcrypt. Esta funcion es la
 * red de seguridad para las instalaciones con --no-demo, y respeta el
 * indice ux_users_single_admin: si ya hay uno, no crea otro.
 */
async function ensureAdmin() {
  const usersTable = `${config.db.schema}.users`;
  const existing = await db.one(`SELECT id, email FROM ${usersTable} WHERE role = 'admin'`);
  if (existing) {
    log(`Ya existe un administrador (${existing.email}); no se crea otro.`);
    return;
  }
  const hash = await password.hash(config.admin.password);
  await db.query(
    `INSERT INTO ${usersTable} (full_name, email, password_hash, role)
     VALUES ($1, $2, $3, 'admin')`,
    [config.admin.name, config.admin.email, hash]
  );
  log(`Administrador creado: ${config.admin.email}`);
  log('Cambie la contrasena despues del primer inicio de sesion.');
}

/** Resumen de filas por tabla: confirma que la carga hizo lo esperado. */
async function report() {
  const rows = await db.many(`
    SELECT 'formats' AS tabla, count(*)::int AS filas FROM ${config.db.schema}.formats
    UNION ALL SELECT 'categories',    count(*)::int FROM ${config.db.schema}.categories
    UNION ALL SELECT 'genres',        count(*)::int FROM ${config.db.schema}.genres
    UNION ALL SELECT 'authors',       count(*)::int FROM ${config.db.schema}.authors
    UNION ALL SELECT 'concepts',      count(*)::int FROM ${config.db.schema}.concepts
    UNION ALL SELECT 'books',         count(*)::int FROM ${config.db.schema}.books
    UNION ALL SELECT 'users',         count(*)::int FROM ${config.db.schema}.users
    UNION ALL SELECT 'book_authors',  count(*)::int FROM ${config.db.schema}.book_authors
    UNION ALL SELECT 'book_genres',   count(*)::int FROM ${config.db.schema}.book_genres
    UNION ALL SELECT 'book_concepts', count(*)::int FROM ${config.db.schema}.book_concepts
    UNION ALL SELECT 'book_images',   count(*)::int FROM ${config.db.schema}.book_images
  `);
  log('Filas por tabla: ' + rows.map((r) => `${r.tabla}=${r.filas}`).join('  '));
}

(async () => {
  try {
    log(`Conectando a ${config.db.database}@${config.db.host}:${config.db.port} como ${config.db.user}...`);
    log(`Scripts en ${DB_DIR}`);
    SKIPPED.forEach(([file, why]) => log(`  (se omite db/${file}: ${why})`));

    if (!has('--seed-only')) await applyStructure();
    await applySeed();
    await ensureAdmin();
    await report();
    log('Instalacion completada.');
    process.exitCode = 0;
  } catch (error) {
    console.error('[setup-db] ERROR:', error.message);
    if (/permission denied to create extension/i.test(error.message)) {
      console.error('[setup-db] Ejecute primero:  psql -U postgres -f db/00_create_database.sql');
    }
    if (/permission denied for database/i.test(error.message)) {
      console.error('[setup-db] Otorgue permisos:  GRANT CREATE ON DATABASE library_db TO library_user;');
    }
    process.exitCode = 1;
  } finally {
    await db.pool.end();
  }
})();
