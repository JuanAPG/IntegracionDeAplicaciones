'use strict';

const express = require('express');
const controller = require('./catalog.controller');
const { requireLogin } = require('../../core/middlewares/auth');

const router = express.Router();

// El catalogo esta reservado a usuarios registrados con sesion activa.
router.get('/', requireLogin, controller.index);
router.get('/:id', requireLogin, controller.show);

module.exports = router;
