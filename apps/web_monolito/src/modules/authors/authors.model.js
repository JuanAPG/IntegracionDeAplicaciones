'use strict';

// Autores: dependencia multivaluada libro ->> autor, resuelta con book_authors.
const lookupModel = require('../../core/crud/lookupModel');

module.exports = lookupModel({
  table: 'authors',
  relationTable: 'book_authors',
  relationColumn: 'author_id'
});
