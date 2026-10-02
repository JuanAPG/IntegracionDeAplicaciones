"""
apps/services/escritorio/http_logger.py
Logger de trafico HTTP para la consola.

Imprime cada peticion y respuesta con formato legible, resaltando
el token Bearer en los encabezados. Util para depuracion en desarrollo.

Uso:
    from http_logger import log_request, log_response

    log_request("POST", "http://localhost:5000/login", headers, body)
    log_response(200, response_headers, response_body)
"""
import json


def _format_headers(headers, highlight_auth=True):
    """Formatea encabezados HTTP, mostrando el token Bearer completo."""
    lines = []
    for key, value in headers.items():
        if highlight_auth and key.lower() == "authorization" and value.startswith("Bearer "):
            lines.append(f"  {key}: {value}")
        else:
            lines.append(f"  {key}: {value}")
    return "\n".join(lines)


def _format_body(body):
    """Formatea el cuerpo de la peticion/respuesta como JSON pretty-print."""
    if body is None:
        return "  (sin cuerpo)"
    if isinstance(body, (dict, list)):
        return json.dumps(body, indent=2, ensure_ascii=False)
    if isinstance(body, bytes):
        try:
            return body.decode("utf-8")
        except UnicodeDecodeError:
            return f"  ({len(body)} bytes binarios)"
    return str(body)


def log_request(method, url, headers=None, body=None):
    """Imprime una peticion HTTP saliente en consola.

    Args:
        method: Metodo HTTP (GET, POST, PUT, PATCH, DELETE)
        url: URL completa
        headers: Diccionario de encabezados (opcional)
        body: Cuerpo de la peticion (opcional)
    """
    print("\n" + "=" * 70)
    print(f">>> PETICION {method.upper()}")
    print(f"    URL: {url}")
    if headers:
        print("    Encabezados:")
        print(_format_headers(headers))
    if body:
        print("    Cuerpo:")
        print(f"    {_format_body(body)}")
    print("=" * 70)


def log_response(status_code, headers=None, body=None):
    """Imprime una respuesta HTTP entrante en consola.

    Args:
        status_code: Codigo de estado HTTP (200, 401, 403, etc.)
        headers: Diccionario de encabezados de respuesta (opcional)
        body: Cuerpo de la respuesta (opcional)
    """
    print("\n" + "-" * 70)
    print(f"<<< RESPUESTA {status_code}")
    if headers:
        print("    Encabezados:")
        print(_format_headers(dict(headers), highlight_auth=False))
    if body:
        print("    Cuerpo:")
        print(f"    {_format_body(body)}")
    print("-" * 70 + "\n")
