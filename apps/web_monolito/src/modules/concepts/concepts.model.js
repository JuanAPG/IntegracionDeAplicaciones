'use strict';

/**
 * Conceptos: un mismo concepto puede aparecer en distintos libros con
 * definiciones diferentes. El nombre vive en concepts y la definicion
 * depende del par (libro, concepto) en book_concepts.
 */
const db = require('../../config/database');
const lookupModel = require('../../core/crud/lookupModel');

const base = lookupModel({
  table: 'concepts',
  relationTable: 'book_concepts',
  relationColumn: 'concept_id'
});

/** Definiciones registradas para un concepto, libro por libro. */
base.definitionsByConcept = (conceptId) => db.many(
  `SELECT b.id AS book_id, b.title, b.isbn, bc.definition
     FROM book_concepts bc
     JOIN books b ON b.id = bc.book_id
    WHERE bc.concept_id = $1
    ORDER BY b.title`,
  [conceptId]
);

module.exports = base;
