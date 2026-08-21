'use strict';

/** Error de aplicacion con codigo HTTP asociado. */
class HttpError extends Error {
  constructor(status, message) {
    super(message);
    this.status = status;
  }
}

const notFound = (message = 'Recurso no encontrado') => new HttpError(404, message);
const badRequest = (message = 'Solicitud invalida') => new HttpError(400, message);
const forbidden = (message = 'No tiene permisos para esta operacion') => new HttpError(403, message);

module.exports = { HttpError, notFound, badRequest, forbidden };
