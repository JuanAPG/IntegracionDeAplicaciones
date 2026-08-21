'use strict';

const path = require('path');
const express = require('express');
const session = require('express-session');

const config = require('./config/env');
const flash = require('./core/middlewares/flash');
const locals = require('./core/middlewares/locals');
const { notFoundHandler, errorHandler } = require('./core/middlewares/errors');
const routes = require('./modules');

const app = express();

// --- Vistas (capa View del patron MVC) --------------------------------
// Se registran dos raices: los modulos (vistas propias de cada modulo)
// y views/ (layout y parciales compartidos).
app.set('view engine', 'ejs');
app.set('views', [path.join(__dirname, 'modules'), path.join(__dirname, 'views')]);

// --- Entrada de datos --------------------------------------------------
// Solo formularios HTML (urlencoded / multipart). No se habilita express.json():
// la aplicacion no intercambia datos en JSON ni XML.
app.use(express.urlencoded({ extended: false }));

// --- Archivos estaticos (CSS e imagenes cargadas) ----------------------
app.use(express.static(path.join(__dirname, 'public')));

// --- Sesion de usuarios registrados ------------------------------------
app.use(session({
  name: 'library.sid',
  secret: config.session.secret,
  resave: false,
  saveUninitialized: false,
  cookie: {
    httpOnly: true,
    sameSite: 'lax',
    maxAge: config.session.maxAge
  }
}));

app.use(flash);
app.use(locals);

// --- Rutas por modulo ---------------------------------------------------
app.use('/', routes);

app.use(notFoundHandler);
app.use(errorHandler);

module.exports = app;
