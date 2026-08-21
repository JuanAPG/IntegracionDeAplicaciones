'use strict';

const lookupController = require('../../core/crud/lookupController');
const model = require('./categories.model');

const meta = {
  basePath: '/admin/categories',
  title: 'Categorias',
  singular: 'categoria',
  nameLabel: 'Nombre de la categoria',
  usageLabel: 'Libros',
  description: 'Catalogo independiente de categorias (relacion 1:N con libros).',
  maxLength: 80,
  protectDelete: true
};

module.exports = lookupController(model, meta);
