'use strict';

const lookupController = require('../../core/crud/lookupController');
const model = require('./formats.model');

const meta = {
  basePath: '/admin/formats',
  title: 'Formatos',
  singular: 'formato',
  nameLabel: 'Nombre del formato',
  usageLabel: 'Libros',
  description: 'Catalogo independiente de formatos de publicacion (relacion 1:N con libros).',
  maxLength: 50,
  protectDelete: true
};

module.exports = lookupController(model, meta);
