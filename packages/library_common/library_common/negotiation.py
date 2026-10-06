"""
packages/library_common/library_common/negotiation.py
Negociacion de contenido: el cliente elige XML o JSON y el servicio
responde el mismo recurso en el formato pedido.

Prioridad, igual en los seis servicios:
    1. ?output= / ?_format= / ?format=   (lo explicito manda)
    2. cabecera Accept
    3. DEFAULT_FORMAT del .env (XML por omision, como exige el enunciado)

Sobre ?format=: en el microservicio de LIBROS tambien es un filtro de
busqueda (formato Fisico/Digital/Audiolibro), de modo que alli solo vale
como negociacion si su valor es xml|json. Por eso el parametro
recomendado es ?output=, que no tiene esa ambiguedad; los clientes de
escritorio ya lo usan asi.
"""
from flask import Response, jsonify, request

from . import serializers

REPRESENTATIONS = {
    "xml": True, "application/xml": True, "text/xml": True,
    "json": False, "application/json": False,
}


class Negotiator:
    """Responde en XML o JSON segun lo pedido, con el namespace del servicio."""

    def __init__(self, namespace, default_format="xml"):
        self.namespace = namespace
        self.default_xml = (default_format or "xml").lower() == "xml"

    def requested(self):
        """True/False (xml/json) si el cliente lo pidio explicitamente, o None."""
        for name in ("output", "_format", "format"):
            value = (request.args.get(name) or "").strip().lower()
            if value in REPRESENTATIONS:
                return REPRESENTATIONS[value]
        return None

    def wants_xml(self):
        explicit = self.requested()
        if explicit is not None:
            return explicit
        accept = request.headers.get("Accept", "")
        if accept and "*/*" not in accept:
            xml_pos = min((accept.find(t) for t in ("application/xml", "text/xml")
                           if t in accept), default=-1)
            json_pos = accept.find("application/json")
            if xml_pos >= 0 and (json_pos < 0 or xml_pos < json_pos):
                return True
            if json_pos >= 0:
                return False
        return self.default_xml

    def respond(self, payload, element, status=200, headers=None):
        if self.wants_xml():
            response = Response(serializers.to_xml_bytes(element),
                                status=status, mimetype="application/xml")
        else:
            response = jsonify(payload)
            response.status_code = status
        for key, value in (headers or {}).items():
            response.headers[key] = value
        return response

    # Atajos que evitan repetir el namespace en cada ruta.
    def dict_response(self, tag, payload, status=200, headers=None, **attrs):
        return self.respond(payload,
                            serializers.dict_element(tag, payload, self.namespace, **attrs),
                            status=status, headers=headers)

    def collection_response(self, tag, item_tag, rows, payload, *, total=None,
                            limit=None, offset=None, status=200, headers=None):
        element = serializers.collection_element(
            tag, item_tag, rows, self.namespace,
            total=total, limit=limit, offset=offset)
        return self.respond(payload, element, status=status, headers=headers)

    def error_response(self, status, code, message, details=None):
        payload = {"error": {"status": status, "code": code, "message": message,
                             "details": details or []}}
        element = serializers.error_element(status, code, message, details,
                                            self.namespace)
        return self.respond(payload, element, status=status)
