'use strict';

/** Controlador CRUD de usuarios (solo administrador). */
const asyncHandler = require('../../core/utils/asyncHandler');
const password = require('../../core/utils/password');
const { str, requiredStr, isEmail } = require('../../core/utils/validate');
const config = require('../../config/env');
const model = require('./users.model');

const BASE = '/admin/users';

const index = asyncHandler(async (req, res) => {
  const search = str(req.query.q);
  const role = ['admin', 'user'].includes(str(req.query.role)) ? str(req.query.role) : '';
  const page = Math.max(1, Number.parseInt(req.query.page, 10) || 1);
  const pageSize = config.pagination.pageSize * 2;

  const total = await model.count({ search, role });
  const items = await model.list({ search, role, limit: pageSize, offset: (page - 1) * pageSize });

  const params = [];
  if (search) params.push(`q=${encodeURIComponent(search)}`);
  if (role) params.push(`role=${role}`);

  res.page('users/views/list', {
    title: 'Usuarios',
    items,
    search,
    role,
    total,
    pagination: {
      page,
      totalPages: Math.max(1, Math.ceil(total / pageSize)),
      baseUrl: `${BASE}${params.length ? `?${params.join('&')}` : ''}`
    }
  });
});

const newForm = asyncHandler(async (req, res) => {
  const adminCount = await model.countAdmins();
  res.page('users/views/form', {
    title: 'Nuevo usuario',
    user: { id: null, full_name: '', email: '', role: 'user', is_active: true },
    adminExists: adminCount > 0
  });
});

const readForm = (body) => ({
  fullName: str(body.full_name),
  email: str(body.email),
  role: body.role === 'admin' ? 'admin' : 'user',
  isActive: body.is_active === 'on' || body.is_active === '1'
});

const create = asyncHandler(async (req, res) => {
  const errors = [];
  const data = readForm(req.body);
  requiredStr(data.fullName, 'Nombre completo', errors, 150);
  requiredStr(data.email, 'Correo electronico', errors, 150);
  if (data.email && !isEmail(data.email)) errors.push('El correo electronico no tiene un formato valido.');
  password.validate(str(req.body.password), str(req.body.password_confirmation), errors);

  if (data.role === 'admin' && (await model.countAdmins()) > 0) {
    errors.push('Ya existe un administrador. El sistema admite como maximo uno.');
  }
  if (await model.findByEmail(data.email)) {
    errors.push('Ya existe un usuario con ese correo.');
  }

  if (errors.length) {
    req.flash('error', errors);
    return res.redirect(`${BASE}/new`);
  }

  const created = await model.create({
    fullName: data.fullName,
    email: data.email,
    passwordHash: await password.hash(str(req.body.password)),
    role: data.role,
    isActive: data.isActive
  });

  req.flash('success', `Usuario "${created.full_name}" creado.`);
  return res.redirect(BASE);
});

const editForm = asyncHandler(async (req, res) => {
  const user = await model.findById(req.params.id);
  if (!user) {
    req.flash('error', 'Usuario no encontrado.');
    return res.redirect(BASE);
  }
  const adminCount = await model.countAdmins(user.id);
  return res.page('users/views/form', { title: 'Editar usuario', user, adminExists: adminCount > 0 });
});

const update = asyncHandler(async (req, res) => {
  const id = Number.parseInt(req.params.id, 10);
  const errors = [];
  const data = readForm(req.body);
  requiredStr(data.fullName, 'Nombre completo', errors, 150);
  requiredStr(data.email, 'Correo electronico', errors, 150);
  if (data.email && !isEmail(data.email)) errors.push('El correo electronico no tiene un formato valido.');

  const current = await model.findById(id);
  if (!current) {
    req.flash('error', 'Usuario no encontrado.');
    return res.redirect(BASE);
  }

  if (data.role === 'admin' && current.role !== 'admin' && (await model.countAdmins(id)) > 0) {
    errors.push('Ya existe un administrador. El sistema admite como maximo uno.');
  }
  if (current.role === 'admin' && data.role !== 'admin' && (await model.countAdmins(id)) === 0) {
    errors.push('No se puede degradar al unico administrador del sistema.');
  }
  if (current.role === 'admin' && !data.isActive) {
    errors.push('No se puede desactivar la cuenta del administrador.');
  }

  if (errors.length) {
    req.flash('error', errors);
    return res.redirect(`${BASE}/${id}/edit`);
  }

  const updated = await model.update(id, data);
  if (req.session.user.id === updated.id) {
    req.session.user = {
      id: updated.id,
      full_name: updated.full_name,
      email: updated.email,
      role: updated.role
    };
  }
  req.flash('success', `Usuario "${updated.full_name}" actualizado.`);
  return res.redirect(BASE);
});

const resetPassword = asyncHandler(async (req, res) => {
  const id = Number.parseInt(req.params.id, 10);
  const errors = [];
  const next = str(req.body.password);
  password.validate(next, str(req.body.password_confirmation), errors);

  if (errors.length) {
    req.flash('error', errors);
    return res.redirect(`${BASE}/${id}/edit`);
  }

  const target = await model.findById(id);
  if (!target) {
    req.flash('error', 'Usuario no encontrado.');
    return res.redirect(BASE);
  }

  await model.updatePassword(id, await password.hash(next));
  req.flash('success', `Contrasena de "${target.full_name}" restablecida.`);
  return res.redirect(BASE);
});

const destroy = asyncHandler(async (req, res) => {
  const id = Number.parseInt(req.params.id, 10);
  if (id === req.session.user.id) {
    req.flash('error', 'No puede eliminar su propia cuenta mientras la sesion esta activa.');
    return res.redirect(BASE);
  }
  const target = await model.findById(id);
  if (!target) {
    req.flash('error', 'Usuario no encontrado.');
    return res.redirect(BASE);
  }
  if (target.role === 'admin') {
    req.flash('error', 'No se puede eliminar la cuenta del administrador.');
    return res.redirect(BASE);
  }
  await model.remove(id);
  req.flash('success', `Usuario "${target.full_name}" eliminado.`);
  return res.redirect(BASE);
});

/** Panel de administracion con el resumen de todas las tablas del modelo. */
const dashboard = asyncHandler(async (req, res) => {
  const stats = await model.stats();
  res.page('users/views/dashboard', { title: 'Panel de administracion', stats });
});

module.exports = { index, newForm, create, editForm, update, resetPassword, destroy, dashboard };
