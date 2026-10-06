"""
apps/services/login/login/_bootstrap.py
Deja importable el paquete compartido packages/library_common.

Lo normal es instalarlo en el venv del servicio:

    pip install -e packages/library_common

Pero si alguien arranca el servicio sin ese paso (una copia recien
clonada, una prueba rapida), este modulo localiza el paquete dentro del
repo y lo anade a sys.path. Es la misma clase de respaldo que ya tiene
login/wsgi.py con su try/except ImportError: que el servicio arranque sin
ceremonias y falle con un mensaje claro si de verdad no esta.
"""
import os
import sys


def _ensure_library_common():
    try:
        import library_common  # noqa: F401
        return
    except ImportError:
        pass

    here = os.path.abspath(__file__)
    # Sube hasta encontrar packages/library_common dentro del repo.
    path = here
    for _ in range(8):
        path = os.path.dirname(path)
        candidate = os.path.join(path, "packages", "library_common")
        if os.path.isdir(os.path.join(candidate, "library_common")):
            if candidate not in sys.path:
                sys.path.insert(0, candidate)
            return

    raise ImportError(
        "No se encontro el paquete compartido 'library_common'. "
        "Instalelo en el venv del servicio con:\n"
        "    pip install -e packages/library_common\n"
        "(en el despliegue: pip install -e /opt/library/packages/library_common)")


_ensure_library_common()
