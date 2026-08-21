'use strict';

const express = require('express');
const controller = require('./books.controller');
const { requireAdmin } = require('../../core/middlewares/auth');
const { upload } = require('../../core/middlewares/upload');

const router = express.Router();
router.use(requireAdmin);

// Libro
router.get('/', controller.index);
router.get('/new', controller.newForm);
router.post('/', controller.create);
router.get('/:id/edit', controller.editForm);
router.post('/:id', controller.update);
router.post('/:id/delete', controller.destroy);

// Relacion libro-concepto (definicion propia por libro)
router.post('/:id/concepts', controller.addConcept);
router.post('/:id/concepts/:conceptId', controller.updateConcept);
router.post('/:id/concepts/:conceptId/delete', controller.removeConcept);

// Imagenes (formularios multipart/form-data)
router.post('/:id/images', upload.single('image'), controller.uploadImage);
router.post('/:id/images/:imageId/cover', controller.setCover);
router.post('/:id/images/:imageId/delete', controller.removeImage);

module.exports = router;
