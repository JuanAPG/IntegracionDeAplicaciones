"""
apps/services/login/login/validators.py
Validacion de los campos de registro antes de tocar la base de datos.

El correo se valida aqui (sintaxis y longitud) y despues contra la base
(formato unico). La verificacion de propiedad se hace por sendmail con un
token (ver mailer.py y data/login_migration.sql).
"""
import re

import config

EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")
# Letras (incluidos acentos), espacios, guiones, apotrofos y puntos.
NAME_RE = re.compile(r"^[A-Za-zÁÉÍÓÚÜÑáéíóúüñ'’\-\. ]+$")

MAX_NAME = 80
MAX_EMAIL = 150
MAX_PASSWORD_BYTES = 72  # limite de bcrypt


def normalize_email(raw):
    email = (raw or "").strip().lower()
    if not email:
        raise ValueError("El email es obligatorio.")
    if len(email) > MAX_EMAIL:
        raise ValueError("El email supera los 150 caracteres.")
    if not EMAIL_RE.match(email):
        raise ValueError("El email no tiene un formato valido.")
    return email


def validate_name(raw, field, required=True):
    value = (raw or "").strip()
    value = re.sub(r"\s+", " ", value)
    if not value:
        if required:
            raise ValueError(f"El campo '{field}' es obligatorio.")
        return ""
    if len(value) > MAX_NAME:
        raise ValueError(f"El campo '{field}' supera los 80 caracteres.")
    if not NAME_RE.match(value):
        raise ValueError(f"El campo '{field}' contiene caracteres no validos.")
    return value


def validate_password(raw):
    if not raw:
        raise ValueError("La contrasena es obligatoria.")
    if len(raw) < config.PASSWORD_MIN_LENGTH:
        raise ValueError(
            f"La contrasena debe tener al menos {config.PASSWORD_MIN_LENGTH} caracteres.")
    if len(raw.encode("utf-8")) > MAX_PASSWORD_BYTES:
        raise ValueError("La contrasena supera los 72 bytes (limite de bcrypt).")
    return raw


def compose_full_name(first, paternal, maternal):
    return " ".join(p for p in (first, paternal, maternal) if p).strip()
