"""
apps/services/escritorio/http_logger.py
Logger de trafico HTTP para la consola.

Imprime cada peticion y respuesta con formato legible. Por seguridad, el
token Bearer se muestra redactado salvo que se pida explicito (el token
completo nunca debe quedar en logs ni capturas):

    log_request("POST", url, headers, body)              # redactado
    log_request("POST", url, headers, body, full=True)   # token completo
    LOGIN_DEBUG_FULL_TOKEN=1 python Ejercicio1.py        # siempre completo
"""
import json
import os


def _redact(value):
    """Muestra solo el encabezado del token para depurar sin filtrarlo."""
    scheme, _, token = value.partition(" ")
    if not token:
        return value
    return f"{scheme} {token[:12]}…({len(token)} chars, redactado)"


def _format_headers(headers, highlight_auth=True, full=False):
    """Formatea encabezados HTTP, redactando el token Bearer por omision."""
    show_full = full or os.getenv("LOGIN_DEBUG_FULL_TOKEN", "") == "1"
    lines = []
    for key, value in headers.items():
        if highlight_auth and key.lower() == "authorization" and value.startswith("Bearer "):
            lines.append(f"  {key}: {value if show_full else _redact(value)}")
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


def log_request(method, url, headers=None, body=None, full=False):
    """Imprime una peticion HTTP saliente en consola.

    Args:
        method: Metodo HTTP (GET, POST, PUT, PATCH, DELETE)
        url: URL completa
        headers: Diccionario de encabezados (opcional)
        body: Cuerpo de la peticion (opcional)
        full: True para mostrar el token Bearer completo (solo depuracion)
    """
    print("\n" + "=" * 70)
    print(f">>> PETICION {method.upper()}")
    print(f"    URL: {url}")
    if headers:
        print("    Encabezados:")
        print(_format_headers(headers, full=full))
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
