'use strict';

const lookupController = require('../../core/crud/lookupController');
const model = require('./authors.model');
const config = require('../../config/env');

const meta = {
  basePath: `${config.basePath}/admin/authors`,
  title: 'Autores',
  singular: 'autor',
  nameLabel: 'Nombre del autor',
  usageLabel: 'Libros',
  description: 'Un libro puede tener varios autores (tabla puente book_authors).',
  maxLength: 150,
  protectDelete: false
};

module.exports = lookupController(model, meta);
