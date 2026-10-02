"""
library_soap_service/soap/wsgi.py
Punto de entrada para gunicorn (funciona como paquete o como modulo suelto):

    # desde library_soap_service (paquete):
    gunicorn --workers 3 --bind 127.0.0.1:5001 soap.wsgi:application
    # desde library_soap_service/soap (compatibilidad con el deploy anterior):
    gunicorn --workers 3 --bind 127.0.0.1:5001 wsgi:application
"""
try:
    from .app import app as application
except ImportError:  # ejecutado como modulo suelto, sin paquete
    from app import app as application
