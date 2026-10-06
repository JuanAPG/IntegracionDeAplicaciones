"""
apps/services/login/login/serializers.py
Representacion de la respuesta en los dos formatos que habla el servicio:
JSON y XML (ElementTree, nunca cadenas formateadas a mano).

El XML usa el espacio de nombres urn:library:auth:1.0, orientado a la
cuenta: <user> como agregado con nombre normalizado y estado de
verificacion del correo.
"""
from datetime import datetime, timezone
from xml.etree import ElementTree

from . import config

NS = config.XML_NAMESPACE


def _iso(value):
    return value.isoformat() if hasattr(value, "isoformat") else value


# ---------------------------------------------------------------------
# XML
# ---------------------------------------------------------------------
def _sub(parent, tag, text=None, **attrs):
    element = ElementTree.SubElement(
        parent, tag, {k: str(v) for k, v in attrs.items() if v is not None})
    if text is not None:
        element.text = str(text)
    return element


def _field(row, *names, default=""):
    """
    Primer nombre presente, con valor no nulo.

    <user> se construye a veces desde la FILA de PostgreSQL
    (first_name, email_verified) y a veces desde el diccionario publico
    en camelCase que devuelve users_repository.public_user (nombre,
    emailVerified). Aceptar las dos formas evita que el XML salga con
    los nombres vacios segun por donde se haya llamado.
    """
    for name in names:
        if name in row and row[name] is not None:
            return row[name]
    return default


def user_element(row, parent=None):
    """Construye el elemento <user>."""
    if parent is None:
        user = ElementTree.Element("user", {"xmlns": NS})
    else:
        user = ElementTree.SubElement(parent, "user")
    _sub(user, "id", _field(row, "id"))
    names = _sub(user, "names")
    _sub(names, "nombre", _field(row, "first_name", "nombre"))
    _sub(names, "apellidoPaterno", _field(row, "last_name_paternal", "apellidoPaterno"))
    _sub(names, "apellidoMaterno", _field(row, "last_name_maternal", "apellidoMaterno"))
    _sub(names, "fullName", _field(row, "full_name", "fullName"))
    _sub(user, "email", _field(row, "email"))
    _sub(user, "role", _field(row, "role"))
    # role_id viaja en el JWT y se publica tambien aqui, para que un
    # cliente que solo habla XML (la app Electron) pueda leer el rol.
    _sub(user, "roleId", _field(row, "role_id", "roleId"))
    _sub(user, "emailVerified",
         "true" if _field(row, "email_verified", "emailVerified") else "false")
    _sub(user, "isActive",
         "false" if _field(row, "is_active", "isActive", default=True) is False
         else "true")
    return user


def dict_element(tag, payload):
    """Serializa un diccionario simple a XML."""
    root = ElementTree.Element(tag, {"xmlns": NS})
    _fill(root, payload)
    return root


def _fill(parent, payload):
    if isinstance(payload, dict):
        for key, value in payload.items():
            if isinstance(value, dict):
                if key == "user" and "email" in value:
                    user_element(value, parent=parent)
                else:
                    _fill(ElementTree.SubElement(parent, key), value)
            elif isinstance(value, list):
                node = _sub(parent, key, count=len(value))
                for item in value:
                    child = ElementTree.SubElement(node, _singular(key))
                    _fill(child, item)
            else:
                _sub(parent, key, _scalar(value))
    else:
        parent.text = _scalar(payload)


def _singular(name):
    if name.endswith("ies"):
        return name[:-3] + "y"
    return name[:-1] if name.endswith("s") else "item"


def _scalar(value):
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return ""
    return str(_iso(value))


def error_element(status, code, message, details=None):
    root = ElementTree.Element("error", {"xmlns": NS, "status": str(status), "code": code})
    _sub(root, "message", message)
    if details:
        node = _sub(root, "details", count=len(details))
        for detail in details:
            _sub(node, "detail", detail)
    return root


def to_xml_bytes(element):
    """Serializa con declaracion XML y sangrado legible."""
    ElementTree.indent(element, space="  ")
    body = ElementTree.tostring(element, encoding="unicode")
    return ('<?xml version="1.0" encoding="UTF-8"?>\n' + body + "\n").encode("utf-8")


def generated_at():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
