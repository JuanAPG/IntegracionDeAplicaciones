'use strict';

const asyncHandler = require('../utils/asyncHandler');
const { requiredStr, str } = require('../utils/validate');
const config = require('../../config/env');

/**
 * Fabrica de controladores (capa Controller del MVC) para catalogos (id, name).
 * Renderiza las vistas compartidas views/lookup/*.ejs.
 *
 * meta:
 *   basePath   ruta base del modulo, por ejemplo /admin/genres
 *   title      titulo en plural
 *   singular   nombre en singular para los mensajes
 *   nameLabel  etiqueta del campo
 *   usageLabel encabezado de la columna de uso
 *   protectDelete  true si la BD impide borrar cuando hay referencias
 */
module.exports = function lookupController(model, meta) {
  const pageSize = config.pagination.pageSize * 2;

  const index = asyncHandler(async (req, res) => {
    const search = str(req.query.q);
    const page = Math.max(1, Number.parseInt(req.query.page, 10) || 1);
    const total = await model.count({ search });
    const items = await model.list({ search, limit: pageSize, offset: (page - 1) * pageSize });

    res.page('lookup/list', {
      title: meta.title,
      meta,
      items,
      search,
      pagination: {
        page,
        totalPages: Math.max(1, Math.ceil(total / pageSize)),
        baseUrl: `${meta.basePath}${search ? `?q=${encodeURIComponent(search)}` : ''}`
      },
      total
    });
  });

  const newForm = (req, res) => {
    res.page('lookup/form', { title: `Nuevo ${meta.singular}`, meta, item: { id: null, name: '' } });
  };

  const create = asyncHandler(async (req, res) => {
    const errors = [];
    const name = requiredStr(req.body.name, meta.nameLabel, errors, meta.maxLength || 150);
    if (errors.length) {
      req.flash('error', errors);
      return res.redirect(`${meta.basePath}/new`);
    }
    const created = await model.create(name);
    req.flash('success', `${meta.singular} "${created.name}" creado correctamente.`);
    return res.redirect(meta.basePath);
  });

  const editForm = asyncHandler(async (req, res) => {
    const item = await model.findById(req.params.id);
    if (!item) {
      req.flash('error', `${meta.singular} no encontrado.`);
      return res.redirect(meta.basePath);
    }
    return res.page('lookup/form', { title: `Editar ${meta.singular}`, meta, item });
  });

  const update = asyncHandler(async (req, res) => {
    const errors = [];
    const name = requiredStr(req.body.name, meta.nameLabel, errors, meta.maxLength || 150);
    if (errors.length) {
      req.flash('error', errors);
      return res.redirect(`${meta.basePath}/${req.params.id}/edit`);
    }
    const updated = await model.update(req.params.id, name);
    if (!updated) {
      req.flash('error', `${meta.singular} no encontrado.`);
      return res.redirect(meta.basePath);
    }
    req.flash('success', `${meta.singular} "${updated.name}" actualizado.`);
    return res.redirect(meta.basePath);
  });

  const destroy = asyncHandler(async (req, res) => {
    const usage = await model.usageCount(req.params.id);
    if (usage > 0 && meta.protectDelete) {
      req.flash('error', `No se puede eliminar: el registro esta asociado a ${usage} libro(s).`);
      return res.redirect(meta.basePath);
    }
    const removed = await model.remove(req.params.id);
    if (!removed) {
      req.flash('error', `${meta.singular} no encontrado.`);
      return res.redirect(meta.basePath);
    }
    req.flash('success', `${meta.singular} "${removed.name}" eliminado.`);
    return res.redirect(meta.basePath);
  });

  return { index, newForm, create, editForm, update, destroy };
};
