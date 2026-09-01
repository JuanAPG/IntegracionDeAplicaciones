"""
soap/payloads.py
Lectura y validacion del cuerpo de las peticiones de escritura.

El servicio acepta el libro en JSON o en XML. El XML de entrada usa el
mismo diseno que apps/services/soap/library.xml (elemento <book>), de modo
que una respuesta del servicio puede reenviarse tal cual como peticion.

La salida de este modulo es siempre un diccionario "normalizado":

    {
      "isbn": str, "title": str, "publication_year": int,
      "price": Decimal, "stock": int,
      "format": <id int | nombre str>, "category": <id int | nombre str>,
      "authors":  [ {"ref": int|None, "name": str}, ... ],
      "genres":   [ {"ref": int|None, "name": str}, ... ],
      "concepts": [ {"ref": int|None, "name": str, "definition": str}, ... ],
      "images":   [ {"url": str, "is_cover": bool}, ... ],
    }

Solo aparecen las claves presentes en la peticion: eso permite que PATCH
modifique unicamente lo enviado y que PUT valide lo obligatorio.
"""
import re
from decimal import Decimal, InvalidOperation
from xml.etree import ElementTree

from errors import UnsupportedMedia, ValidationError

# Campos escalares con sus alias aceptados (camelCase del XML y snake_case).
SCALAR_ALIASES = {
    "isbn": ("isbn",),
    "title": ("title", "titulo"),
    "publication_year": ("publication_year", "publicationYear", "year", "anio"),
    "price": ("price", "precio"),
    "stock": ("stock", "existencias"),
    "format": ("format", "format_id", "formatId", "formato"),
    "category": ("category", "category_id", "categoryId", "categoria"),
}

COLLECTION_ALIASES = {
    "authors": ("authors", "autores"),
    "genres": ("genres", "generos"),
    "concepts": ("concepts", "conceptos"),
    "images": ("images", "imagenes"),
}

REQUIRED_ON_CREATE = ("isbn", "title", "publication_year", "price", "format", "category")

_TRUE = ("1", "true", "yes", "on", "si", "t")
_FALSE = ("0", "false", "no", "off", "f")


# ---------------------------------------------------------------------
# Utilidades de conversion
# ---------------------------------------------------------------------
def _text(value, field, max_len=None, required=True):
    if value is None:
        if required:
            raise ValidationError(f"El campo '{field}' es obligatorio.")
        return None
    text = str(value).strip()
    if not text:
        if required:
            raise ValidationError(f"El campo '{field}' no puede estar vacio.")
        return None
    if max_len and len(text) > max_len:
        raise ValidationError(f"El campo '{field}' excede {max_len} caracteres.")
    return text


def _int(value, field, minimum=None, maximum=None):
    try:
        number = int(str(value).strip())
    except (TypeError, ValueError):
        raise ValidationError(f"El campo '{field}' debe ser un numero entero.")
    if minimum is not None and number < minimum:
        raise ValidationError(f"El campo '{field}' debe ser mayor o igual a {minimum}.")
    if maximum is not None and number > maximum:
        raise ValidationError(f"El campo '{field}' debe ser menor o igual a {maximum}.")
    return number


def _decimal(value, field, minimum=None):
    try:
        number = Decimal(str(value).strip())
    except (InvalidOperation, TypeError, ValueError):
        raise ValidationError(f"El campo '{field}' debe ser un numero decimal.")
    if minimum is not None and number < minimum:
        raise ValidationError(f"El campo '{field}' debe ser mayor o igual a {minimum}.")
    return number.quantize(Decimal("0.01"))


def _boolean(value, default=False):
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in _TRUE:
        return True
    if text in _FALSE:
        return False
    return default


def _ref(value):
    """Convierte el atributo ref/id de un catalogo a entero, si viene."""
    if value in (None, ""):
        return None
    try:
        return int(str(value).strip())
    except ValueError:
        return None


def _first(source, aliases):
    for alias in aliases:
        if alias in source:
            return True, source[alias]
    return False, None


# ---------------------------------------------------------------------
# Normalizacion de colecciones
# ---------------------------------------------------------------------
def _named_items(raw, field):
    """
    Acepta ["Isaac Asimov"], [{"name": "..."}], [{"ref": 5}] o
    [{"ref": 5, "name": "..."}] y devuelve [{"ref":..., "name":...}].
    """
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise ValidationError(f"El campo '{field}' debe ser una lista.")
    items, seen = [], set()
    for entry in raw:
        if isinstance(entry, str):
            ref, name = None, _text(entry, field, 150)
        elif isinstance(entry, dict):
            ref = _ref(entry.get("ref", entry.get("id")))
            name = _text(entry.get("name", entry.get("nombre")), field, 150,
                         required=ref is None)
        else:
            raise ValidationError(f"Elemento invalido en '{field}'.")
        key = (ref, (name or "").lower())
        if key in seen:
            continue
        seen.add(key)
        items.append({"ref": ref, "name": name})
    return items


def _concept_items(raw):
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise ValidationError("El campo 'concepts' debe ser una lista.")
    items, seen = [], set()
    for entry in raw:
        if not isinstance(entry, dict):
            raise ValidationError(
                "Cada concepto debe ser un objeto con 'name' y 'definition'.")
        ref = _ref(entry.get("ref", entry.get("id")))
        name = _text(entry.get("name", entry.get("nombre")), "concepts.name", 150,
                     required=ref is None)
        definition = _text(entry.get("definition", entry.get("definicion")),
                           "concepts.definition")
        key = (ref, (name or "").lower())
        if key in seen:
            raise ValidationError(
                f"El concepto '{name or ref}' esta repetido en el libro; "
                "la clave (book_id, concept_id) es unica.")
        seen.add(key)
        items.append({"ref": ref, "name": name, "definition": definition})
    return items


def _image_items(raw):
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise ValidationError("El campo 'images' debe ser una lista.")
    items, covers = [], 0
    for entry in raw:
        if isinstance(entry, str):
            url, is_cover = _text(entry, "images.url", 500), False
        elif isinstance(entry, dict):
            url = _text(entry.get("url"), "images.url", 500)
            is_cover = _boolean(entry.get("is_cover", entry.get("isCover")))
        else:
            raise ValidationError("Elemento invalido en 'images'.")
        covers += 1 if is_cover else 0
        items.append({"url": url, "is_cover": is_cover})
    if covers > 1:
        raise ValidationError(
            "Solo una imagen puede marcarse como portada (indice ux_book_images_one_cover).")
    return items


# ---------------------------------------------------------------------
# Entrada JSON
# ---------------------------------------------------------------------
def _from_mapping(source):
    if not isinstance(source, dict):
        raise ValidationError("El cuerpo debe ser un objeto JSON con los datos del libro.")
    # Tolera que el libro venga envuelto: {"book": {...}}
    if "book" in source and isinstance(source["book"], dict):
        source = source["book"]

    data = {}
    for field, aliases in SCALAR_ALIASES.items():
        present, value = _first(source, aliases)
        if present:
            data[field] = value

    for field, aliases in COLLECTION_ALIASES.items():
        present, value = _first(source, aliases)
        if present:
            data[field] = value
    return data


# ---------------------------------------------------------------------
# Entrada XML (mismo diseno que apps/services/soap/library.xml)
# ---------------------------------------------------------------------
def _strip_ns(tag):
    return tag.split("}", 1)[1] if "}" in tag else tag


def _children(element):
    """Diccionario {nombre_local: elemento} de los hijos directos."""
    return {_strip_ns(child.tag): child for child in element}


def _from_xml(raw_body):
    try:
        root = ElementTree.fromstring(raw_body)
    except ElementTree.ParseError as exc:
        raise ValidationError(f"XML mal formado: {exc}")

    if _strip_ns(root.tag) == "library":
        books = [el for el in root.iter() if _strip_ns(el.tag) == "book"]
        if not books:
            raise ValidationError("El documento <library> no contiene ningun <book>.")
        if len(books) > 1:
            raise ValidationError("Envie un solo <book> por peticion.")
        root = books[0]
    if _strip_ns(root.tag) != "book":
        raise ValidationError("El elemento raiz debe ser <book> (o <library> con un <book>).")

    data = {}
    if root.get("isbn"):
        data["isbn"] = root.get("isbn")

    nodes = _children(root)

    def text_of(name):
        node = nodes.get(name)
        return node.text.strip() if node is not None and node.text else None

    for xml_name, field in (("isbn", "isbn"), ("title", "title"),
                            ("publicationYear", "publication_year"),
                            ("price", "price"), ("stock", "stock")):
        if xml_name in nodes:
            data[field] = text_of(xml_name)

    # <format ref="4">Pasta dura</format>: gana el ref cuando esta presente.
    for xml_name, field in (("format", "format"), ("category", "category")):
        node = nodes.get(xml_name)
        if node is not None:
            data[field] = node.get("ref") or (node.text.strip() if node.text else None)

    def collection(wrapper_name, item_name):
        wrapper = nodes.get(wrapper_name)
        if wrapper is None:
            return None
        return [el for el in wrapper if _strip_ns(el.tag) == item_name]

    authors = collection("authors", "author")
    if authors is not None:
        data["authors"] = [{"ref": el.get("ref"),
                            "name": (el.text or "").strip()} for el in authors]

    genres = collection("genres", "genre")
    if genres is not None:
        data["genres"] = [{"ref": el.get("ref"),
                           "name": (el.text or "").strip()} for el in genres]

    concepts = collection("concepts", "concept")
    if concepts is not None:
        parsed = []
        for el in concepts:
            sub = _children(el)
            name_node, def_node = sub.get("name"), sub.get("definition")
            parsed.append({
                "ref": el.get("ref"),
                "name": (name_node.text or "").strip() if name_node is not None else None,
                "definition": (def_node.text or "").strip() if def_node is not None else None,
            })
        data["concepts"] = parsed

    images = collection("images", "image")
    if images is not None:
        data["images"] = [{"url": (el.text or "").strip(),
                           "isCover": el.get("isCover")} for el in images]
    return data


# ---------------------------------------------------------------------
# Punto de entrada
# ---------------------------------------------------------------------
def read_book_payload(request, partial=False):
    """
    Lee el cuerpo de la peticion (JSON o XML) y devuelve el diccionario
    normalizado. partial=True (PATCH) no exige los campos obligatorios.
    """
    content_type = (request.mimetype or "").lower()
    raw = request.get_data()

    if not raw.strip():
        raise ValidationError("La peticion no trae cuerpo.")

    if "xml" in content_type:
        source = _from_xml(raw)
    elif "json" in content_type or not content_type:
        parsed = request.get_json(silent=True)
        if parsed is None:
            # Un cuerpo que empieza por '<' casi siempre es XML mal etiquetado.
            if raw.lstrip()[:1] == b"<":
                source = _from_xml(raw)
            else:
                raise ValidationError("El cuerpo no es JSON valido.")
        else:
            source = _from_mapping(parsed)
    elif "x-www-form-urlencoded" in content_type or "form-data" in content_type:
        source = _from_mapping(request.form.to_dict(flat=True))
    else:
        raise UnsupportedMedia(
            f"Content-Type '{request.mimetype}' no soportado. "
            "Use application/json o application/xml.")

    return validate(source, partial=partial)


def validate(source, partial=False):
    """Convierte y valida el diccionario crudo ya extraido del cuerpo."""
    data = {}

    if "isbn" in source:
        isbn = _text(source["isbn"], "isbn", 20)
        if not re.fullmatch(r"[0-9Xx\-\s]{10,20}", isbn):
            raise ValidationError(
                "El campo 'isbn' solo admite digitos, guiones y hasta 20 caracteres.")
        data["isbn"] = isbn
    if "title" in source:
        data["title"] = _text(source["title"], "title", 255)
    if "publication_year" in source:
        data["publication_year"] = _int(source["publication_year"],
                                        "publicationYear", minimum=1, maximum=2999)
    if "price" in source:
        data["price"] = _decimal(source["price"], "price", minimum=Decimal("0"))
    if "stock" in source:
        data["stock"] = _int(source["stock"], "stock", minimum=0)
    if "format" in source:
        data["format"] = _text(source["format"], "format", 50)
    if "category" in source:
        data["category"] = _text(source["category"], "category", 80)

    if "authors" in source:
        data["authors"] = _named_items(source["authors"], "authors")
    if "genres" in source:
        data["genres"] = _named_items(source["genres"], "genres")
    if "concepts" in source:
        data["concepts"] = _concept_items(source["concepts"])
    if "images" in source:
        data["images"] = _image_items(source["images"])

    if not partial:
        faltantes = [f for f in REQUIRED_ON_CREATE if f not in data]
        if faltantes:
            raise ValidationError(
                "Faltan campos obligatorios.",
                details=[f"'{f}' es obligatorio." for f in faltantes])
        data.setdefault("stock", 0)
    elif not data:
        raise ValidationError("No se envio ningun campo modificable.")

    return data
