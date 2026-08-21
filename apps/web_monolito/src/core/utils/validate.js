'use strict';

/** Utilidades de validacion y normalizacion de datos recibidos por formulario. */

const str = (value) => (typeof value === 'string' ? value.trim() : '');

const requiredStr = (value, field, errors, max = 255) => {
  const v = str(value);
  if (!v) errors.push(`El campo "${field}" es obligatorio.`);
  else if (v.length > max) errors.push(`El campo "${field}" excede ${max} caracteres.`);
  return v;
};

const intOrNull = (value) => {
  const n = Number.parseInt(value, 10);
  return Number.isNaN(n) ? null : n;
};

const numberOrNull = (value) => {
  const n = Number.parseFloat(value);
  return Number.isNaN(n) ? null : n;
};

/** Normaliza un campo multiple de formulario a un arreglo de enteros unicos. */
const intArray = (value) => {
  if (value === undefined || value === null) return [];
  const list = Array.isArray(value) ? value : [value];
  const result = [];
  for (const item of list) {
    const n = Number.parseInt(item, 10);
    if (!Number.isNaN(n) && !result.includes(n)) result.push(n);
  }
  return result;
};

/** Normaliza un campo multiple a arreglo de cadenas (respeta el orden del formulario). */
const strArray = (value) => {
  if (value === undefined || value === null) return [];
  const list = Array.isArray(value) ? value : [value];
  return list.map((item) => str(item));
};

const isEmail = (value) => /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/.test(str(value));

module.exports = { str, requiredStr, intOrNull, numberOrNull, intArray, strArray, isEmail };
