"""
library_soap_service/soap/db.py
Acceso a PostgreSQL: pool de conexiones y utilidades de transaccion.

El pool se crea de forma perezosa (en la primera consulta) para que el
proceso pueda arrancar aunque la base de datos todavia no este disponible;
asi /health puede informar el fallo en lugar de morir al importar.

CONEXIONES MUERTAS
  Tras reiniciar PostgreSQL, las conexiones guardadas en el pool siguen
  pareciendo abiertas hasta que se usan. Por eso cada conexion se prueba
  (SELECT 1) antes de prestarla y se descarta si no responde; y una que
  se rompe a media consulta se cierra en lugar de volver al pool.
  Un fallo de CONEXION (OperationalError/InterfaceError) es un 503
  (DatabaseUnavailable); los errores de la consulta se propagan tal cual.
"""
import threading
from contextlib import contextmanager

import psycopg2
import psycopg2.extras
from psycopg2 import pool as pg_pool

from . import config

_pool = None
_lock = threading.Lock()


class DatabaseUnavailable(RuntimeError):
    """No se pudo abrir/obtener una conexion con PostgreSQL."""


def _dsn_kwargs():
    return dict(
        host=config.PGHOST,
        port=config.PGPORT,
        dbname=config.PGDATABASE,
        user=config.PGUSER,
        password=config.PGPASSWORD,
        connect_timeout=config.DB_CONNECT_TIMEOUT,
        # El esquema del proyecto no es "public": se fija en la conexion
        # para que las consultas puedan escribir los nombres sin calificar.
        options=f"-c search_path={config.PGSCHEMA},public",
        application_name="library-soap-service",
    )


def get_pool():
    global _pool
    if _pool is None:
        with _lock:
            if _pool is None:
                try:
                    _pool = pg_pool.ThreadedConnectionPool(
                        config.DB_POOL_MIN, config.DB_POOL_MAX, **_dsn_kwargs()
                    )
                except psycopg2.Error as exc:
                    raise DatabaseUnavailable(str(exc).strip()) from exc
    return _pool


_CONNECTION_ERRORS = (psycopg2.OperationalError, psycopg2.InterfaceError)


def _alive(conn):
    """True si la conexion responde. Deja la conexion sin transaccion abierta."""
    if conn.closed:
        return False
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT 1")
        conn.rollback()
        return True
    except _CONNECTION_ERRORS:
        return False


def _checkout(pool):
    """
    Una conexion VIVA del pool. Las muertas se cierran y se descartan; se
    intenta tantas veces como conexiones puede guardar el pool, mas una
    nueva.
    """
    last = None
    for _ in range(config.DB_POOL_MAX + 1):
        try:
            conn = pool.getconn()
        except psycopg2.Error as exc:
            raise DatabaseUnavailable(str(exc).strip()) from exc
        if _alive(conn):
            return conn
        last = "la conexion del pool no responde"
        pool.putconn(conn, close=True)
    raise DatabaseUnavailable(last or "sin conexion")


@contextmanager
def connection():
    """Presta una conexion viva del pool y la devuelve siempre."""
    pool = get_pool()
    conn = _checkout(pool)
    try:
        yield conn
    except _CONNECTION_ERRORS as exc:
        raise DatabaseUnavailable(str(exc).strip()) from exc
    finally:
        # Una conexion rota no vuelve al pool: se cierra.
        pool.putconn(conn, close=bool(conn.closed))


@contextmanager
def cursor(commit=False):
    """
    Cursor de diccionarios dentro de una transaccion.

    commit=False -> solo lectura (se hace rollback al salir, para no dejar
                    transacciones "idle in transaction").
    commit=True  -> confirma al salir sin error, revierte ante excepcion.
    """
    with connection() as conn:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        try:
            yield cur
            if commit:
                conn.commit()
            else:
                conn.rollback()
        except Exception:
            # Con la conexion rota, el rollback fallaria y taparia el
            # error original.
            if not conn.closed:
                try:
                    conn.rollback()
                except _CONNECTION_ERRORS:
                    pass
            raise
        finally:
            if not cur.closed:
                cur.close()


def ping():
    """Comprobacion de vida usada por /health."""
    with cursor() as cur:
        cur.execute("SELECT current_database() AS db, current_user AS usr, version() AS version")
        return cur.fetchone()


def close_pool():
    global _pool
    if _pool is not None:
        _pool.closeall()
        _pool = None
