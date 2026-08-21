'use strict';

const express = require('express');
const { requireAdmin } = require('../middlewares/auth');

/**
 * Rutas estandar de un catalogo. Se usan solo verbos GET y POST de formularios
 * HTML (no hay endpoints tipo REST ni respuestas JSON).
 */
module.exports = function lookupRoutes(controller, extra) {
  const router = express.Router();
  router.use(requireAdmin);

  router.get('/', controller.index);
  router.get('/new', controller.newForm);
  router.post('/', controller.create);
  if (typeof extra === 'function') extra(router);
  router.get('/:id/edit', controller.editForm);
  router.post('/:id', controller.update);
  router.post('/:id/delete', controller.destroy);

  return router;
};
