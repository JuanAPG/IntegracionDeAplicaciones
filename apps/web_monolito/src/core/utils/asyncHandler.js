'use strict';

/**
 * Envuelve un controlador asincrono para que cualquier rechazo
 * llegue al middleware de errores sin repetir try/catch.
 */
module.exports = (fn) => (req, res, next) => Promise.resolve(fn(req, res, next)).catch(next);
