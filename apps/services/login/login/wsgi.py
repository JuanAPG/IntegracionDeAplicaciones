"""
apps/services/login/login/wsgi.py
Punto de entrada para gunicorn (funciona como paquete o como modulo suelto):

    # desde apps/services/login (paquete):
    gunicorn --workers 3 --bind 127.0.0.1:5000 login.wsgi:application
    # desde apps/services/login/login (compatibilidad con el deploy anterior):
    gunicorn --workers 3 --bind 127.0.0.1:5000 wsgi:application
"""
try:
    from .app import app as application
except ImportError:  # ejecutado como modulo suelto, sin paquete
    from app import app as application
