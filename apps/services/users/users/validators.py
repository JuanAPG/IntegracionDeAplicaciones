"""
apps/services/users/users/validators.py
Validacion de los campos antes de tocar la base de datos.

Son las MISMAS reglas que aplica el microservicio de login en su
validators.py (correo, nombres, longitud de contrasena), a proposito: si
el alta por login y el alta administrativa por aqui admitieran cosas
distintas, la base acabaria con dos clases de cuentas.
"""
import re

EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")
NAME_RE = re.compile(r"^[A-Za-zÁÉÍÓÚÜÑáéíóúüñ'’\-\. ]+$")
# Un permiso es "recurso:accion", o el comodin "*" del rol admin.
PERMISSION_RE = re.compile(r"^(\*|[a-z][a-z0-9_]*:[a-z][a-z0-9_]*)$")
ROLE_NAME_RE = re.compile(r"^[a-z][a-z0-9_]{1,39}$")

MAX_NAME = 80
MAX_EMAIL = 150
MAX_PASSWORD_BYTES = 72          # limite de bcrypt
MIN_PASSWORD = 6


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
    value = re.sub(r"\s+", " ", (raw or "").strip())
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
    if len(raw) < MIN_PASSWORD:
        raise ValueError(f"La contrasena debe tener al menos {MIN_PASSWORD} caracteres.")
    if len(raw.encode("utf-8")) > MAX_PASSWORD_BYTES:
        raise ValueError("La contrasena supera los 72 bytes (limite de bcrypt).")
    return raw


def validate_role_name(raw):
    value = (raw or "").strip().lower()
    if not ROLE_NAME_RE.match(value):
        raise ValueError("El nombre del rol debe ser minusculas, sin espacios, "
                         "de 2 a 40 caracteres (por ejemplo 'almacen').")
    return value


def validate_permission(raw):
    value = (raw or "").strip().lower()
    if not PERMISSION_RE.match(value):
        raise ValueError(f"El permiso '{raw}' no tiene la forma 'recurso:accion' "
                         "(por ejemplo 'orders:write') ni es el comodin '*'.")
    return value


def compose_full_name(first, paternal, maternal):
    return " ".join(part for part in (first, paternal, maternal) if part).strip()


def as_bool(raw, field):
    """Convierte 'true'/'1'/'si' a booleano, o lanza con un mensaje claro."""
    if isinstance(raw, bool):
        return raw
    value = str(raw).strip().lower()
    if value in ("1", "true", "yes", "si", "on"):
        return True
    if value in ("0", "false", "no", "off"):
        return False
    raise ValueError(f"El campo '{field}' debe ser true o false.")
