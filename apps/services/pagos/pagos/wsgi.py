"""
apps/services/pagos/pagos/wsgi.py
Punto de entrada para gunicorn:

    # desde apps/services/pagos (paquete):
    gunicorn --workers 3 --bind 127.0.0.1:5005 pagos.wsgi:application
    # desde apps/services/pagos/pagos (modulo suelto):
    gunicorn --workers 3 --bind 127.0.0.1:5005 wsgi:application
"""
try:
    from .app import app as application
except ImportError:  # ejecutado como modulo suelto, sin paquete
    from app import app as application
