'use strict';

/** Guardas de acceso basadas en la sesion del usuario. */

const requireLogin = (req, res, next) => {
  if (!req.session.user) {
    req.flash('error', 'Debe iniciar sesion para continuar.');
    req.session.returnTo = req.originalUrl;
    return res.redirect('/auth/login');
  }
  return next();
};

const requireAdmin = (req, res, next) => {
  if (!req.session.user) {
    req.flash('error', 'Debe iniciar sesion para continuar.');
    req.session.returnTo = req.originalUrl;
    return res.redirect('/auth/login');
  }
  if (req.session.user.role !== 'admin') {
    req.flash('error', 'Seccion exclusiva del administrador.');
    return res.redirect('/');
  }
  return next();
};

const requireGuest = (req, res, next) => {
  if (req.session.user) return res.redirect('/');
  return next();
};

module.exports = { requireLogin, requireAdmin, requireGuest };
