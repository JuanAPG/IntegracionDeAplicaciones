'use strict';

const express = require('express');
const controller = require('./auth.controller');
const { requireLogin, requireGuest } = require('../../core/middlewares/auth');

const router = express.Router();

router.get('/login', requireGuest, controller.showLogin);
router.post('/login', requireGuest, controller.login);

router.get('/register', requireGuest, controller.showRegister);
router.post('/register', requireGuest, controller.register);

router.post('/logout', controller.logout);

router.get('/profile', requireLogin, controller.profile);
router.post('/profile', requireLogin, controller.updateProfile);
router.post('/profile/password', requireLogin, controller.changePassword);

module.exports = router;
