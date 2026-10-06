"""
packages/library_common/library_common/logging_support.py
Registro de actividad sin secretos.

Requisito del enunciado: no guardar contrasenas ni tokens en los logs.
Confiar en "acuerdate de no registrarlo" no es un control; este filtro lo
vuelve mecanico. Se instala en el logger raiz, de modo que cubre tambien
el log de acceso de Werkzeug y cualquier traza de una biblioteca de
terceros.

Lo que tacha:
  * Authorization: Bearer <token>        -> Bearer ***
  * cualquier JWT suelto (a.b.c en base64url)
  * "password": "...", password=..., contrasena=...
  * refresh tokens y la contrasena de una URL (redis://:x@host)
"""
import logging
import re

PATTERNS = (
    # Encabezado Authorization completo.
    (re.compile(r"(?i)\b(bearer)\s+[A-Za-z0-9._~+/=-]{8,}"), r"\1 ***"),
    # Un JWT suelto: tres segmentos base64url separados por punto.
    (re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b"),
     "***jwt***"),
    # password / contrasena / secret / token en JSON o en pares clave=valor.
    (re.compile(r"(?i)(\"(?:password|contrasena|secret|token|refresh_token|refreshToken|authorization|apiKey|api_key)\"\s*:\s*\")[^\"]*"),
     r"\1***"),
    (re.compile(r"(?i)\b(\w*(?:password|contrasena|passwd|secret|token|apikey|api_key)\w*)\s*=\s*[^\s,&;)]+"),
     r"\1=***"),
    # Contrasena dentro de una URL: esquema://usuario:contrasena@host
    (re.compile(r"://([^:/@\s]*):([^@/\s]+)@"), r"://\1:***@"),
)


class SecretRedactingFilter(logging.Filter):
    """Tacha secretos del mensaje y de sus argumentos antes de escribirlo."""

    def filter(self, record):
        try:
            if isinstance(record.msg, str):
                record.msg = redact(record.msg)
            if record.args:
                if isinstance(record.args, dict):
                    record.args = {k: _redact_value(v) for k, v in record.args.items()}
                else:
                    record.args = tuple(_redact_value(a) for a in record.args)
        except Exception:                              # noqa: BLE001
            # Un filtro de log nunca debe tumbar la peticion que lo invoca.
            pass
        return True


def _redact_value(value):
    return redact(value) if isinstance(value, str) else value


def redact(text):
    for pattern, replacement in PATTERNS:
        text = pattern.sub(replacement, text)
    return text


def configure(level=logging.INFO, service="library"):
    """
    Deja el registro listo: formato comun, nivel y filtro de secretos en
    TODOS los manejadores (incluidos los que anada Flask o gunicorn).
    """
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)-7s [" + service + "] %(name)s: %(message)s")
    secret_filter = SecretRedactingFilter()
    root = logging.getLogger()
    root.addFilter(secret_filter)
    for handler in root.handlers:
        handler.addFilter(secret_filter)
    # gunicorn y werkzeug crean sus propios manejadores.
    for name in ("werkzeug", "gunicorn.error", "gunicorn.access"):
        for handler in logging.getLogger(name).handlers:
            handler.addFilter(secret_filter)
    return logging.getLogger(f"library.{service}")
