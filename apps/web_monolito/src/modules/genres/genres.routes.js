'use strict';

const lookupRoutes = require('../../core/crud/lookupRoutes');
const controller = require('./genres.controller');

module.exports = lookupRoutes(controller);
