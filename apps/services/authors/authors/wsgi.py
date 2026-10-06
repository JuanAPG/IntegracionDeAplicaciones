"""
apps/services/authors/authors/wsgi.py
Punto de entrada para gunicorn:

    # desde apps/services/authors (paquete):
    gunicorn --workers 3 --bind 127.0.0.1:5003 authors.wsgi:application
    # desde apps/services/authors/authors (modulo suelto):
    gunicorn --workers 3 --bind 127.0.0.1:5003 wsgi:application
"""
try:
    from .app import app as application
except ImportError:  # ejecutado como modulo suelto, sin paquete
    from app import app as application
