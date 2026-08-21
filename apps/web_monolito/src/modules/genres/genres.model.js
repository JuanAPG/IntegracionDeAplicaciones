'use strict';

// Generos: dependencia multivaluada libro ->> genero, resuelta con book_genres.
const lookupModel = require('../../core/crud/lookupModel');

module.exports = lookupModel({
  table: 'genres',
  relationTable: 'book_genres',
  relationColumn: 'genre_id'
});
