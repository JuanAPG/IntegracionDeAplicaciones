'use strict';

/**
 * Punto de entrada del monolito.
 * Un unico proceso Node.js sirve HTML renderizado en el servidor y accede
 * directamente a PostgreSQL. No expone APIs REST/GraphQL/SOAP.
 */
const app = require('./src/app');
const config = require('./src/config/env');
const { pool } = require('./src/config/database');

const server = app.listen(config.port, () => {
  console.log(`[web_monolito] Servidor HTML escuchando en http://localhost:${config.port}`);
  console.log(`[web_monolito] Base de datos: ${config.db.database}@${config.db.host}:${config.db.port} (esquema ${config.db.schema})`);
});

const shutdown = (signal) => {
  console.log(`\n[web_monolito] ${signal} recibido, cerrando...`);
  server.close(() => {
    pool.end().finally(() => process.exit(0));
  });
};

process.on('SIGINT', () => shutdown('SIGINT'));
process.on('SIGTERM', () => shutdown('SIGTERM'));
