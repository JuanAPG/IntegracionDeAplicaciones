"""
soap/wsgi.py
Punto de entrada para gunicorn:

    gunicorn --workers 3 --bind 127.0.0.1:5001 wsgi:application
"""
from app import app as application
