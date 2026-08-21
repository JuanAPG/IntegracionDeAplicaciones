'use strict';

// Catalogo independiente: categories (Ficcion, Tecnico, Infantil, ...)
const lookupModel = require('../../core/crud/lookupModel');

module.exports = lookupModel({ table: 'categories', bookColumn: 'category_id' });
