'use strict';

/** Guardas de acceso basadas en la sesion del usuario. */

const config = require('../../config/env');

const requireLogin = (req, res, next) => {
  if (!req.session.user) {
    req.flash('error', 'Debe iniciar sesion para continuar.');
    req.session.returnTo = req.originalUrl;
    return res.redirect(`${config.basePath}/auth/login`);
  }
  return next();
};

const requireAdmin = (req, res, next) => {
  if (!req.session.user) {
    req.flash('error', 'Debe iniciar sesion para continuar.');
    req.session.returnTo = req.originalUrl;
    return res.redirect(`${config.basePath}/auth/login`);
  }
  if (req.session.user.role !== 'admin') {
    req.flash('error', 'Seccion exclusiva del administrador.');
    return res.redirect(config.basePath || '/');
  }
  return next();
};

const requireGuest = (req, res, next) => {
  if (req.session.user) return res.redirect(config.basePath || '/');
  return next();
};

module.exports = { requireLogin, requireAdmin, requireGuest };
