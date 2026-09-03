"""
library_soap_service/soap/db.py
Acceso a PostgreSQL: pool de conexiones y utilidades de transaccion.

El pool se crea de forma perezosa (en la primera consulta) para que el
proceso pueda arrancar aunque la base de datos todavia no este disponible;
asi /health puede informar el fallo en lugar de morir al importar.
"""
import threading
from contextlib import contextmanager

import psycopg2
import psycopg2.extras
from psycopg2 import pool as pg_pool

import config

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


@contextmanager
def connection():
    """Presta una conexion del pool y la devuelve siempre."""
    pool = get_pool()
    try:
        conn = pool.getconn()
    except psycopg2.Error as exc:
        raise DatabaseUnavailable(str(exc).strip()) from exc
    try:
        yield conn
    finally:
        pool.putconn(conn)


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
            conn.rollback()
            raise
        finally:
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
