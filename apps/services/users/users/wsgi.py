"""
apps/services/users/users/wsgi.py
Punto de entrada para gunicorn:

    # desde apps/services/users (paquete):
    gunicorn --workers 3 --bind 127.0.0.1:5002 users.wsgi:application
    # desde apps/services/users/users (modulo suelto):
    gunicorn --workers 3 --bind 127.0.0.1:5002 wsgi:application
"""
try:
    from .app import app as application
except ImportError:  # ejecutado como modulo suelto, sin paquete
    from app import app as application
