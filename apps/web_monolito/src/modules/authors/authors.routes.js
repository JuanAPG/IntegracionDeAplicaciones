'use strict';

const lookupRoutes = require('../../core/crud/lookupRoutes');
const controller = require('./authors.controller');

module.exports = lookupRoutes(controller);
