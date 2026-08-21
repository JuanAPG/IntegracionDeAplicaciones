'use strict';

// Catalogo independiente: formats (Fisico, Digital, Audiolibro, ...)
const lookupModel = require('../../core/crud/lookupModel');

module.exports = lookupModel({ table: 'formats', bookColumn: 'format_id' });
