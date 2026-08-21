'use strict';

const multer = require('multer');
const config = require('../../config/env');

/** Rutas no encontradas: se responde con HTML, nunca con JSON. */
const notFoundHandler = (req, res) => {
  res.status(404);
  res.page('error', {
    title: 'Pagina no encontrada',
    status: 404,
    message: `No existe la pagina solicitada: ${req.originalUrl}`,
    detail: null
  });
};

/** Manejador general de errores. Traduce errores de PostgreSQL a mensajes de negocio. */
// eslint-disable-next-line no-unused-vars
const errorHandler = (err, req, res, next) => {
  let status = err.status || 500;
  let message = err.message || 'Ocurrio un error inesperado.';

  if (err instanceof multer.MulterError) {
    status = 400;
    message = err.code === 'LIMIT_FILE_SIZE'
      ? `La imagen supera el tamano maximo permitido (${Math.round(config.uploads.maxBytes / (1024 * 1024))} MB).`
      : `Error al cargar el archivo: ${err.message}`;
  }

  switch (err.code) {
    case '23505': // unique_violation
      status = 400;
      message = err.constraint === 'ux_users_single_admin'
        ? 'Ya existe un administrador en el sistema. Solo se permite uno.'
        : 'El registro ya existe (valor duplicado en un campo unico).';
      break;
    case '23503': // foreign_key_violation
      status = 400;
      message = 'No se puede completar la operacion: el registro esta referenciado por otros datos.';
      break;
    case '23514': // check_violation
      status = 400;
      message = 'Alguno de los valores enviados no cumple las reglas de validacion de la base de datos.';
      break;
    case '3D000':
    case '28P01':
    case 'ECONNREFUSED':
      status = 500;
      message = 'No fue posible conectar con PostgreSQL. Verifique el servicio y las credenciales en .env';
      break;
    default:
      break;
  }

  if (status >= 500) console.error('[error]', err);

  res.status(status);
  res.page('error', {
    title: `Error ${status}`,
    status,
    message,
    detail: config.env === 'production' ? null : err.stack
  });
};

module.exports = { notFoundHandler, errorHandler };
