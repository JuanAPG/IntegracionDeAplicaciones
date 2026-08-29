'use strict';

const config = require('../../config/env');

/**
 * Variables disponibles en todas las vistas y helper de renderizado con layout.
 * res.page(vista, datos) -> renderiza la vista del modulo dentro de views/layout.ejs
 */
module.exports = (req, res, next) => {
  res.locals.currentUser = req.session.user || null;
  res.locals.isAdmin = Boolean(req.session.user && req.session.user.role === 'admin');
  res.locals.appName = 'Libreria en Linea';
  res.locals.uploadsPath = config.uploads.publicPath;

  // Prefijo de montaje: las vistas anteponen <%= base %> a cada enlace
  // interno, de modo que cambiar BASE_PATH no obliga a tocar ninguna vista.
  res.locals.base = config.basePath;

  // currentPath se expone SIN el prefijo para que el resaltado del menu
  // siga comparando contra rutas del router ('/catalog', '/admin', ...).
  const fullPath = req.originalUrl.split('?')[0];
  res.locals.currentPath =
    config.basePath && fullPath.startsWith(config.basePath)
      ? fullPath.slice(config.basePath.length) || '/'
      : fullPath;

  // Las imagenes mezclan rutas propias ('/uploads/x.jpg', servidas bajo el
  // prefijo) con URL externas absolutas ('https://...'), que no se tocan.
  res.locals.asset = (url) =>
    typeof url === 'string' && url.startsWith('/') ? `${config.basePath}${url}` : url;

  res.page = (view, data = {}) => {
    res.render(view, data, (err, body) => {
      if (err) return next(err);
      return res.render('layout', Object.assign({ title: res.locals.appName, body }, data));
    });
  };

  next();
};
