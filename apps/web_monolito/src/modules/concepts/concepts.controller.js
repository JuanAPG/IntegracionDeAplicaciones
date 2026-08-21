'use strict';

const lookupController = require('../../core/crud/lookupController');
const asyncHandler = require('../../core/utils/asyncHandler');
const model = require('./concepts.model');

const meta = {
  basePath: '/admin/concepts',
  title: 'Conceptos',
  singular: 'concepto',
  nameLabel: 'Nombre del concepto',
  usageLabel: 'Definiciones',
  description: 'Un concepto puede aparecer en varios libros con una definicion distinta en cada uno.',
  maxLength: 150,
  protectDelete: false,
  detailPath: true
};

const controller = lookupController(model, meta);

/** Vista propia del modulo: muestra la definicion del concepto en cada libro. */
controller.show = asyncHandler(async (req, res) => {
  const concept = await model.findById(req.params.id);
  if (!concept) {
    req.flash('error', 'Concepto no encontrado.');
    return res.redirect(meta.basePath);
  }
  const definitions = await model.definitionsByConcept(concept.id);
  return res.page('concepts/views/show', {
    title: `Concepto: ${concept.name}`,
    meta,
    concept,
    definitions
  });
});

module.exports = controller;
