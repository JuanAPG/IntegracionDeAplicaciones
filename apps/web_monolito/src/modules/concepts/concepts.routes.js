'use strict';

const lookupRoutes = require('../../core/crud/lookupRoutes');
const controller = require('./concepts.controller');

// Ruta adicional del modulo: detalle con las definiciones por libro.
module.exports = lookupRoutes(controller, (router) => {
  router.get('/:id', controller.show);
});
