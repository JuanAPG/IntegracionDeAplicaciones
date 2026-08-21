'use strict';

/**
 * Carga de imagenes de libros mediante formularios multipart/form-data.
 * Los archivos se guardan en el sistema de archivos y la ruta publica
 * se persiste en la tabla book_images.
 */
const path = require('path');
const fs = require('fs');
const crypto = require('crypto');
const multer = require('multer');
const config = require('../../config/env');

const uploadDir = path.join(__dirname, '..', '..', 'public', 'uploads');
fs.mkdirSync(uploadDir, { recursive: true });

const storage = multer.diskStorage({
  destination: (req, file, cb) => cb(null, uploadDir),
  filename: (req, file, cb) => {
    const ext = (path.extname(file.originalname) || '.jpg').toLowerCase();
    const name = `${Date.now()}-${crypto.randomBytes(6).toString('hex')}${ext}`;
    cb(null, name);
  }
});

// Un archivo no permitido no es un error del servidor: se marca en la peticion
// para que el controlador lo informe como un mensaje de validacion mas.
const fileFilter = (req, file, cb) => {
  if (!config.uploads.allowedMime.includes(file.mimetype)) {
    req.fileValidationError = 'Formato de imagen no permitido (use JPG, PNG, WEBP o GIF).';
    return cb(null, false);
  }
  return cb(null, true);
};

const upload = multer({
  storage,
  fileFilter,
  limits: { fileSize: config.uploads.maxBytes }
});

/** Elimina del disco un archivo previamente subido a partir de su ruta publica. */
const removeUploadedFile = (publicUrl) => {
  if (!publicUrl || !publicUrl.startsWith(`${config.uploads.publicPath}/`)) return;
  const filename = path.basename(publicUrl);
  const target = path.join(uploadDir, filename);
  fs.promises.unlink(target).catch(() => {});
};

module.exports = { upload, uploadDir, removeUploadedFile };
