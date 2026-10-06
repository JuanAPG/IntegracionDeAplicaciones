"""
apps/services/pedidos/pedidos/wsgi.py
Punto de entrada para gunicorn:

    # desde apps/services/pedidos (paquete):
    gunicorn --workers 3 --bind 127.0.0.1:5004 pedidos.wsgi:application
    # desde apps/services/pedidos/pedidos (modulo suelto):
    gunicorn --workers 3 --bind 127.0.0.1:5004 wsgi:application
"""
try:
    from .app import app as application
except ImportError:  # ejecutado como modulo suelto, sin paquete
    from app import app as application
