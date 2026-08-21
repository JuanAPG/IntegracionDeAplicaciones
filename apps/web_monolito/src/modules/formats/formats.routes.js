'use strict';

const lookupRoutes = require('../../core/crud/lookupRoutes');
const controller = require('./formats.controller');

module.exports = lookupRoutes(controller);
