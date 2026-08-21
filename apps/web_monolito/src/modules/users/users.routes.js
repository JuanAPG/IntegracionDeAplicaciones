'use strict';

const express = require('express');
const controller = require('./users.controller');
const { requireAdmin } = require('../../core/middlewares/auth');

const router = express.Router();
router.use(requireAdmin);

router.get('/', controller.index);
router.get('/new', controller.newForm);
router.post('/', controller.create);
router.get('/:id/edit', controller.editForm);
router.post('/:id', controller.update);
router.post('/:id/password', controller.resetPassword);
router.post('/:id/delete', controller.destroy);

module.exports = router;
