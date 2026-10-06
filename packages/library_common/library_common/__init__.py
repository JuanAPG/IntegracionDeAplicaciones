"""
packages/library_common/library_common/__init__.py
Capa compartida de la libreria en linea.

Seis microservicios (login, books, users, authors, pedidos, pagos) hablan
el mismo idioma: Redis para sesiones/revocacion/cache, JWT HS256 con el
mismo secreto, negociacion XML/JSON y el mismo formato de error. Todo eso
vive aqui una sola vez.

Submodulos:
    env           lectura de .env (raiz + servicio) y conversion de tipos
    errors        excepciones de API -> codigos HTTP
    metrics       contadores en proceso que alimentan /metrics
    redis_store   conexion a Redis, sesiones, refresh, revocacion, cache, locks
    jwt_auth      emision y verificacion de JWT, decoradores de autorizacion
    roles         resolucion de permisos por rol (PostgreSQL + cache en Redis)
    negotiation   ?format=/?output=/Accept -> XML o JSON
    serializers   el mismo recurso como XML (ElementTree) o como JSON
    db            pool de PostgreSQL con Psycopg 3
    flask_support manejadores de error y endpoints comunes (/health, /metrics)
"""

__version__ = "1.0.0"
