"""
library_soap_service/soap/serializers.py
Representacion de la respuesta en los dos formatos que habla el servicio.

El XML reproduce exactamente el diseno de apps/services/soap/library.xml:
orientado a libros, con <book> como raiz agregada, las dependencias
multivaluadas en envoltorios repetidos (<authors>, <genres>, <concepts>,
<images>) y el id de catalogo conservado en el atributo "ref".
"""
from datetime import datetime, timezone
from decimal import Decimal
from xml.etree import ElementTree

import config

NS = config.XML_NAMESPACE


def _iso(value):
    return value.isoformat() if hasattr(value, "isoformat") else value


def _money(value):
    """NUMERIC(10,2) -> cadena con dos decimales, como en el XML de origen."""
    if value is None:
        return None
    return f"{Decimal(str(value)):.2f}"


# ---------------------------------------------------------------------
# JSON
# ---------------------------------------------------------------------
def book_to_dict(row):
    """Fila de books_repository -> diccionario JSON en camelCase."""
    return {
        "id": row["id"],
        "isbn": row["isbn"],
        "title": row["title"],
        "publicationYear": row["publication_year"],
        "price": float(row["price"]) if row["price"] is not None else None,
        "currency": config.CURRENCY,
        "stock": row["stock"],
        "format": {"ref": row["format_id"], "name": row["format_name"]},
        "category": {"ref": row["category_id"], "name": row["category_name"]},
        "authors": [{"ref": a["id"], "name": a["name"]} for a in row["authors"]],
        "genres": [{"ref": g["id"], "name": g["name"]} for g in row["genres"]],
        "concepts": [{"ref": c["id"], "name": c["name"], "definition": c["definition"]}
                     for c in row["concepts"]],
        "images": [{"id": i["id"], "url": i["url"], "isCover": i["is_cover"]}
                   for i in row["images"]],
        "createdAt": _iso(row.get("created_at")),
        "updatedAt": _iso(row.get("updated_at")),
    }


def collection_to_dict(rows, total, limit, offset, filters=None):
    return {
        "library": {
            "version": config.XML_VERSION,
            "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "source": config.PGDATABASE,
            "schema": config.PGSCHEMA,
        },
        "count": len(rows),
        "total": total,
        "limit": limit,
        "offset": offset,
        "filters": filters or {},
        "books": [book_to_dict(row) for row in rows],
    }


# ---------------------------------------------------------------------
# XML
# ---------------------------------------------------------------------
def _sub(parent, tag, text=None, **attrs):
    element = ElementTree.SubElement(
        parent, tag, {k: str(v) for k, v in attrs.items() if v is not None})
    if text is not None:
        element.text = str(text)
    return element


def book_element(row, parent=None):
    """Construye el elemento <book> del diseno de library.xml."""
    attrs = {"id": str(row["id"]), "isbn": row["isbn"]}
    if parent is None:
        attrs["xmlns"] = NS
        book = ElementTree.Element("book", attrs)
    else:
        book = ElementTree.SubElement(parent, "book", attrs)

    _sub(book, "title", row["title"])
    _sub(book, "publicationYear", row["publication_year"])
    _sub(book, "price", _money(row["price"]), currency=config.CURRENCY)
    _sub(book, "stock", row["stock"])
    _sub(book, "format", row["format_name"], ref=row["format_id"])
    _sub(book, "category", row["category_name"], ref=row["category_id"])

    authors = _sub(book, "authors", count=len(row["authors"]))
    for author in row["authors"]:
        _sub(authors, "author", author["name"], ref=author["id"])

    genres = _sub(book, "genres", count=len(row["genres"]))
    for genre in row["genres"]:
        _sub(genres, "genre", genre["name"], ref=genre["id"])

    concepts = _sub(book, "concepts", count=len(row["concepts"]))
    for concept in row["concepts"]:
        node = _sub(concepts, "concept", ref=concept["id"])
        _sub(node, "name", concept["name"])
        # (book, concept) -> definition: la definicion vive dentro del libro.
        _sub(node, "definition", concept["definition"])

    images = _sub(book, "images", count=len(row["images"]))
    for image in row["images"]:
        _sub(images, "image", image["url"], id=image["id"],
             isCover="true" if image["is_cover"] else "false")

    return book


def library_element(rows, total=None, limit=None, offset=None):
    root = ElementTree.Element("library", {
        "xmlns": NS,
        "version": config.XML_VERSION,
        "generatedAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": config.PGDATABASE,
        "schema": config.PGSCHEMA,
    })
    attrs = {"count": str(len(rows))}
    if total is not None:
        attrs["total"] = str(total)
    if limit is not None:
        attrs["limit"] = str(limit)
    if offset is not None:
        attrs["offset"] = str(offset)
    books = ElementTree.SubElement(root, "books", attrs)
    for row in rows:
        book_element(row, parent=books)
    return root


def error_element(status, code, message, details=None):
    root = ElementTree.Element("error", {"xmlns": NS, "status": str(status), "code": code})
    _sub(root, "message", message)
    if details:
        node = _sub(root, "details", count=len(details))
        for detail in details:
            _sub(node, "detail", detail)
    return root


def catalog_element(tag, item_tag, rows):
    """
    Catalogo en el mismo estilo que library.xml: el id en el atributo "ref"
    y el nombre como texto.

        <formats count="4"><format ref="1">Fisico</format>...</formats>
    """
    root = ElementTree.Element(tag, {"xmlns": NS, "count": str(len(rows))})
    for row in rows:
        _sub(root, item_tag, row["name"], ref=row["id"])
    return root


def dict_element(tag, payload):
    """Serializa un diccionario simple (health, catalogos, borrado) a XML."""
    root = ElementTree.Element(tag, {"xmlns": NS})
    _fill(root, payload)
    return root


def _fill(parent, payload):
    if isinstance(payload, dict):
        for key, value in payload.items():
            if isinstance(value, list):
                node = _sub(parent, key, count=len(value))
                for item in value:
                    child = ElementTree.SubElement(node, _singular(key))
                    _fill(child, item)
            elif isinstance(value, dict):
                _fill(ElementTree.SubElement(parent, key), value)
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


def to_xml_bytes(element):
    """Serializa con declaracion XML y sangrado legible."""
    ElementTree.indent(element, space="  ")
    body = ElementTree.tostring(element, encoding="unicode")
    return ('<?xml version="1.0" encoding="UTF-8"?>\n' + body + "\n").encode("utf-8")
