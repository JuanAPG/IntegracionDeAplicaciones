"""
packages/library_common/library_common/serializers.py
El mismo recurso en los dos formatos que hablan los servicios: JSON y XML.

El XML se construye con ElementTree, nunca con cadenas formateadas a
mano, para que el escapado de &, < y > sea responsabilidad de la
biblioteca y no del programador.

Es la generalizacion de los serializers que ya tenian login y books: el
espacio de nombres se recibe por parametro para que cada servicio use el
suyo (urn:library:auth:1.0, urn:library:catalog:1.0, ...).
"""
from datetime import date, datetime, timezone
from decimal import Decimal
from xml.etree import ElementTree

# Plurales irregulares que aparecen en el dominio: el nombre del elemento
# hijo de una lista se obtiene del singular de la etiqueta que la contiene.
IRREGULAR = {
    "children": "child",
    "people": "person",
    "data": "item",
    "lines": "line",
    "payments": "payment",
    "orders": "order",
    "roles": "role",
    "permissions": "permission",
    "users": "user",
    "authors": "author",
    "books": "book",
    "warnings": "warning",
    "details": "detail",
    "endpoints": "endpoint",
    "formats": "format",
}


def scalar(value):
    """Convierte un valor de Python al texto que va dentro de un elemento."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return ""
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return str(value)


def singular(name):
    if name in IRREGULAR:
        return IRREGULAR[name]
    if name.endswith("ies"):
        return name[:-3] + "y"
    if name.endswith("ses"):
        return name[:-2]
    return name[:-1] if name.endswith("s") else "item"


def sub(parent, tag, text=None, **attrs):
    element = ElementTree.SubElement(
        parent, tag, {k: str(v) for k, v in attrs.items() if v is not None})
    if text is not None:
        element.text = scalar(text)
    return element


def fill(parent, payload):
    """Vuelca un diccionario/lista/escalar dentro de un elemento."""
    if isinstance(payload, dict):
        for key, value in payload.items():
            if isinstance(value, dict):
                fill(ElementTree.SubElement(parent, key), value)
            elif isinstance(value, list):
                node = sub(parent, key, count=len(value))
                for item in value:
                    child = ElementTree.SubElement(node, singular(key))
                    fill(child, item)
            else:
                sub(parent, key, scalar(value))
    elif isinstance(payload, list):
        for item in payload:
            fill(ElementTree.SubElement(parent, "item"), item)
    else:
        parent.text = scalar(payload)


def dict_element(tag, payload, namespace, **attrs):
    """Serializa un diccionario a un arbol XML con el namespace del servicio."""
    root = ElementTree.Element(tag, {"xmlns": namespace,
                                     **{k: str(v) for k, v in attrs.items()
                                        if v is not None}})
    fill(root, payload)
    return root


def collection_element(tag, item_tag, rows, namespace, *, total=None,
                       limit=None, offset=None, **attrs):
    """
    Elemento de coleccion con los datos de paginacion como atributos,
    siguiendo la forma que ya usa el microservicio de libros:

        <orders xmlns="..." count="2" total="37" limit="50" offset="0">
    """
    root = ElementTree.Element(tag, {
        "xmlns": namespace,
        "count": str(len(rows)),
        **({"total": str(total)} if total is not None else {}),
        **({"limit": str(limit)} if limit is not None else {}),
        **({"offset": str(offset)} if offset is not None else {}),
        **{k: str(v) for k, v in attrs.items() if v is not None},
    })
    for row in rows:
        fill(ElementTree.SubElement(root, item_tag), row)
    return root


def error_element(status, code, message, details, namespace):
    root = ElementTree.Element("error", {"xmlns": namespace,
                                         "status": str(status), "code": code})
    sub(root, "message", message)
    if details:
        node = sub(root, "details", count=len(details))
        for detail in details:
            sub(node, "detail", detail)
    return root


def to_xml_bytes(element):
    """Serializa con declaracion XML y sangrado legible."""
    ElementTree.indent(element, space="  ")
    body = ElementTree.tostring(element, encoding="unicode")
    return ('<?xml version="1.0" encoding="UTF-8"?>\n' + body + "\n").encode("utf-8")


def generated_at():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
