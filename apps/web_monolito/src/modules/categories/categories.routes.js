'use strict';

const lookupRoutes = require('../../core/crud/lookupRoutes');
const controller = require('./categories.controller');

module.exports = lookupRoutes(controller);
