'use strict';

const bcrypt = require('bcryptjs');

const ROUNDS = 10;
const MIN_LENGTH = 6;

const hash = (plain) => bcrypt.hash(plain, ROUNDS);
const verify = (plain, storedHash) => bcrypt.compare(plain, storedHash);

/** Valida la robustez minima exigida a las contrasenas. */
const validate = (plain, confirmation, errors, { requireConfirmation = true } = {}) => {
  if (!plain || plain.length < MIN_LENGTH) {
    errors.push(`La contrasena debe tener al menos ${MIN_LENGTH} caracteres.`);
  }
  if (requireConfirmation && plain !== confirmation) {
    errors.push('La confirmacion de la contrasena no coincide.');
  }
  return plain;
};

module.exports = { hash, verify, validate, MIN_LENGTH };
