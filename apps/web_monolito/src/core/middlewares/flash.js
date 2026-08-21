'use strict';

/**
 * Mensajes flash minimos basados en la sesion.
 * Evita dependencias externas y no expone ningun formato de intercambio de datos.
 */
module.exports = (req, res, next) => {
  if (!req.session.flash) req.session.flash = { success: [], error: [], info: [] };

  req.flash = (type, message) => {
    if (!req.session.flash[type]) req.session.flash[type] = [];
    if (Array.isArray(message)) req.session.flash[type].push(...message);
    else req.session.flash[type].push(message);
  };

  res.locals.flash = req.session.flash;
  req.session.flash = { success: [], error: [], info: [] };

  next();
};
