'use strict';

const lookupController = require('../../core/crud/lookupController');
const model = require('./genres.model');

const meta = {
  basePath: '/admin/genres',
  title: 'Generos',
  singular: 'genero',
  nameLabel: 'Nombre del genero',
  usageLabel: 'Libros',
  description: 'Un libro puede pertenecer a varios generos (tabla puente book_genres).',
  maxLength: 80,
  protectDelete: false
};

module.exports = lookupController(model, meta);
