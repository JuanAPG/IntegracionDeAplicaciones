'use strict';

/**
 * Composicion del monolito: cada modulo aporta su propio router.
 * Todas las rutas devuelven HTML; no hay endpoints de API.
 */
const express = require('express');

const catalogRoutes = require('./catalog/catalog.routes');
const catalogController = require('./catalog/catalog.controller');
const authRoutes = require('./auth/auth.routes');
const usersRoutes = require('./users/users.routes');
const usersController = require('./users/users.controller');
const booksRoutes = require('./books/books.routes');
const authorsRoutes = require('./authors/authors.routes');
const genresRoutes = require('./genres/genres.routes');
const conceptsRoutes = require('./concepts/concepts.routes');
const formatsRoutes = require('./formats/formats.routes');
const categoriesRoutes = require('./categories/categories.routes');
const { requireAdmin } = require('../core/middlewares/auth');

const router = express.Router();

// Publico / usuarios registrados
router.get('/', catalogController.home);
router.use('/auth', authRoutes);
router.use('/catalog', catalogRoutes);

// Administracion (un unico administrador)
router.get('/admin', requireAdmin, usersController.dashboard);
router.use('/admin/books', booksRoutes);
router.use('/admin/authors', authorsRoutes);
router.use('/admin/genres', genresRoutes);
router.use('/admin/concepts', conceptsRoutes);
router.use('/admin/formats', formatsRoutes);
router.use('/admin/categories', categoriesRoutes);
router.use('/admin/users', usersRoutes);

module.exports = router;
