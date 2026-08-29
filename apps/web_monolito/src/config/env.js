'use strict';

/**
 * Configuracion central de la aplicacion.
 * Carga variables de entorno desde .env (si existe) y expone valores tipados.
 */
require('dotenv').config();

const toInt = (value, fallback) => {
  const parsed = Number.parseInt(value, 10);
  return Number.isNaN(parsed) ? fallback : parsed;
};

module.exports = {
  env: process.env.NODE_ENV || 'development',
  port: toInt(process.env.PORT, 3000),

  // Prefijo bajo el que se monta toda la aplicacion. La pagina de inicio es
  // http://localhost:<port><basePath>. Se normaliza a "/algo" sin barra final
  // para poder concatenarlo sin generar dobles barras.
  basePath: (() => {
    const raw = process.env.BASE_PATH || '/library';
    const clean = `/${raw.replace(/^\/+|\/+$/g, '')}`;
    return clean === '/' ? '' : clean;
  })(),

  db: {
    host: process.env.PGHOST || 'localhost',
    port: toInt(process.env.PGPORT, 5432),
    database: process.env.PGDATABASE || 'library_db',
    user: process.env.PGUSER || 'library_user',
    password: process.env.PGPASSWORD || '777',
    schema: process.env.PGSCHEMA || 'library'
  },

  session: {
    secret: process.env.SESSION_SECRET || 'library-dev-secret',
    // 8 horas
    maxAge: 1000 * 60 * 60 * 8
  },

  admin: {
    name: process.env.ADMIN_NAME || 'Administrador',
    email: process.env.ADMIN_EMAIL || 'admin@library.local',
    password: process.env.ADMIN_PASSWORD || 'Admin123!'
  },

  uploads: {
    maxBytes: toInt(process.env.UPLOAD_MAX_MB, 5) * 1024 * 1024,
    publicPath: '/uploads',
    allowedMime: ['image/jpeg', 'image/png', 'image/webp', 'image/gif']
  },

  pagination: {
    pageSize: 10
  }
};
