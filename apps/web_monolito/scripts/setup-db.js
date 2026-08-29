'use strict';

/**
 * Instalacion de la base de datos.
 *
 *   node scripts/setup-db.js              crea el esquema (si no existe), carga
 *                                         datos de demostracion y el administrador
 *   node scripts/setup-db.js --reset      elimina el esquema library y lo recrea
 *   node scripts/setup-db.js --seed-only  solo datos de demostracion + administrador
 *   node scripts/setup-db.js --no-demo    esquema y administrador, sin datos de demo
 */
const fs = require('fs');
const path = require('path');

const config = require('../src/config/env');
const db = require('../src/config/database');
const password = require('../src/core/utils/password');

const SCHEMA_FILE = path.resolve(__dirname, '..', '..', '..', 'data', 'schema.sql');
const SEED_FILE = path.resolve(__dirname, '..', '..', '..', 'data', 'seed.sql');

const args = process.argv.slice(2);
const has = (flag) => args.includes(flag);

const log = (message) => console.log(`[setup-db] ${message}`);

async function schemaExists() {
  const row = await db.one(
    'SELECT 1 AS found FROM information_schema.schemata WHERE schema_name = $1',
    [config.db.schema]
  );
  return Boolean(row);
}

async function applySchema() {
  if (!fs.existsSync(SCHEMA_FILE)) {
    throw new Error(`No se encontro el archivo de esquema: ${SCHEMA_FILE}`);
  }

  if (has('--reset')) {
    log(`Eliminando el esquema "${config.db.schema}" (--reset)...`);
    await db.query(`DROP SCHEMA IF EXISTS ${config.db.schema} CASCADE`);
  } else if (await schemaExists()) {
    log(`El esquema "${config.db.schema}" ya existe; se omite la creacion (use --reset para recrearlo).`);
    return;
  }

  log(`Aplicando ${SCHEMA_FILE}...`);
  await db.query(fs.readFileSync(SCHEMA_FILE, 'utf8'));
  log('Esquema creado.');
}

async function applySeed() {
  if (has('--no-demo')) {
    log('Datos de demostracion omitidos (--no-demo).');
    return;
  }
  if (!fs.existsSync(SEED_FILE)) {
    throw new Error(`No se encontro el archivo de datos: ${SEED_FILE}`);
  }
  log(`Cargando datos de demostracion desde ${SEED_FILE}...`);
  await db.query(fs.readFileSync(SEED_FILE, 'utf8'));
  log('Datos de demostracion cargados.');
}

async function ensureAdmin() {
  // Tabla calificada con el esquema: este script tambien se ejecuta contra
  // bases en la nube detras de un pooler (PgBouncer en modo transaction),
  // donde el parametro de arranque "options -c search_path=..." del pool no
  // siempre llega y las referencias sin calificar fallan.
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

(async () => {
  try {
    log(`Conectando a ${config.db.database}@${config.db.host}:${config.db.port} como ${config.db.user}...`);
    if (!has('--seed-only')) await applySchema();
    // No se fija search_path aqui: el pool entrega una conexion cualquiera y
    // el ajuste no alcanzaria a las consultas siguientes. Tanto data/seed.sql
    // como ensureAdmin() califican sus tablas con el esquema.
    await applySeed();
    await ensureAdmin();
    log('Instalacion completada.');
    process.exitCode = 0;
  } catch (error) {
    console.error('[setup-db] ERROR:', error.message);
    if (/permission denied to create extension/i.test(error.message)) {
      console.error('[setup-db] Ejecute como superusuario:  psql -d library_db -c "CREATE EXTENSION IF NOT EXISTS pgcrypto;"');
    }
    if (/permission denied for database/i.test(error.message)) {
      console.error('[setup-db] Otorgue permisos:  psql -d library_db -c "GRANT CREATE ON DATABASE library_db TO library_user;"');
    }
    process.exitCode = 1;
  } finally {
    await db.pool.end();
  }
})();
