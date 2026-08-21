'use strict';

/**
 * Controlador de autenticacion: registro, inicio y cierre de sesion y perfil.
 * Todas las respuestas son HTML renderizado en el servidor.
 */
const asyncHandler = require('../../core/utils/asyncHandler');
const password = require('../../core/utils/password');
const { str, requiredStr, isEmail } = require('../../core/utils/validate');
const users = require('../users/users.model');

const sessionUser = (user) => ({
  id: user.id,
  full_name: user.full_name,
  email: user.email,
  role: user.role
});

const showLogin = (req, res) => {
  res.page('auth/views/login', { title: 'Iniciar sesion', form: { email: '' } });
};

const login = asyncHandler(async (req, res) => {
  const email = str(req.body.email);
  const plain = str(req.body.password);

  const user = await users.findByEmail(email);
  if (!user || !(await password.verify(plain, user.password_hash))) {
    req.flash('error', 'Correo o contrasena incorrectos.');
    return res.redirect('/auth/login');
  }
  if (!user.is_active) {
    req.flash('error', 'La cuenta esta desactivada. Contacte al administrador.');
    return res.redirect('/auth/login');
  }

  const redirectTo = req.session.returnTo || (user.role === 'admin' ? '/admin' : '/catalog');
  return req.session.regenerate((err) => {
    if (err) {
      req.flash('error', 'No fue posible iniciar la sesion.');
      return res.redirect('/auth/login');
    }
    req.session.user = sessionUser(user);
    req.session.flash = { success: [`Bienvenido, ${user.full_name}.`], error: [], info: [] };
    return res.redirect(redirectTo);
  });
});

const showRegister = (req, res) => {
  res.page('auth/views/register', { title: 'Crear cuenta', form: { full_name: '', email: '' } });
};

const register = asyncHandler(async (req, res) => {
  const errors = [];
  const fullName = requiredStr(req.body.full_name, 'Nombre completo', errors, 150);
  const email = requiredStr(req.body.email, 'Correo electronico', errors, 150);
  if (email && !isEmail(email)) errors.push('El correo electronico no tiene un formato valido.');
  password.validate(str(req.body.password), str(req.body.password_confirmation), errors);

  if (errors.length) {
    req.flash('error', errors);
    return res.redirect('/auth/register');
  }

  const existing = await users.findByEmail(email);
  if (existing) {
    req.flash('error', 'Ya existe una cuenta registrada con ese correo.');
    return res.redirect('/auth/register');
  }

  // El registro publico siempre crea usuarios con rol "user":
  // el sistema admite como maximo un administrador, creado en la instalacion.
  const created = await users.create({
    fullName,
    email,
    passwordHash: await password.hash(str(req.body.password)),
    role: 'user'
  });

  req.session.user = sessionUser(created);
  req.flash('success', `Cuenta creada. Bienvenido, ${created.full_name}.`);
  return res.redirect('/catalog');
});

const logout = (req, res) => {
  req.session.destroy(() => res.redirect('/auth/login'));
};

const profile = asyncHandler(async (req, res) => {
  const user = await users.findById(req.session.user.id);
  res.page('auth/views/profile', { title: 'Mi perfil', user });
});

const updateProfile = asyncHandler(async (req, res) => {
  const errors = [];
  const fullName = requiredStr(req.body.full_name, 'Nombre completo', errors, 150);
  const email = requiredStr(req.body.email, 'Correo electronico', errors, 150);
  if (email && !isEmail(email)) errors.push('El correo electronico no tiene un formato valido.');

  if (errors.length) {
    req.flash('error', errors);
    return res.redirect('/auth/profile');
  }

  const updated = await users.updateProfile(req.session.user.id, { fullName, email });
  req.session.user = sessionUser(updated);
  req.flash('success', 'Datos de perfil actualizados.');
  return res.redirect('/auth/profile');
});

const changePassword = asyncHandler(async (req, res) => {
  const errors = [];
  const current = str(req.body.current_password);
  const next = str(req.body.password);
  password.validate(next, str(req.body.password_confirmation), errors);

  const stored = await users.getPasswordHash(req.session.user.id);
  if (!stored || !(await password.verify(current, stored.password_hash))) {
    errors.push('La contrasena actual es incorrecta.');
  }

  if (errors.length) {
    req.flash('error', errors);
    return res.redirect('/auth/profile');
  }

  await users.updatePassword(req.session.user.id, await password.hash(next));
  req.flash('success', 'Contrasena actualizada.');
  return res.redirect('/auth/profile');
});

module.exports = { showLogin, login, showRegister, register, logout, profile, updateProfile, changePassword };
