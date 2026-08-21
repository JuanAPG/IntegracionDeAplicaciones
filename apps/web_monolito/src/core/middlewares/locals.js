'use strict';

const config = require('../../config/env');

/**
 * Variables disponibles en todas las vistas y helper de renderizado con layout.
 * res.page(vista, datos) -> renderiza la vista del modulo dentro de views/layout.ejs
 */
module.exports = (req, res, next) => {
  res.locals.currentUser = req.session.user || null;
  res.locals.isAdmin = Boolean(req.session.user && req.session.user.role === 'admin');
  res.locals.currentPath = req.originalUrl.split('?')[0];
  res.locals.appName = 'Libreria en Linea';
  res.locals.uploadsPath = config.uploads.publicPath;

  res.page = (view, data = {}) => {
    res.render(view, data, (err, body) => {
      if (err) return next(err);
      return res.render('layout', Object.assign({ title: res.locals.appName, body }, data));
    });
  };

  next();
};
