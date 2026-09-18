"""
apps/services/login/login/db.py
Acceso a PostgreSQL con Psycopg 3: pool de conexiones y transacciones.

El pool se crea de forma perezosa (en la primera consulta) para que el
proceso pueda arrancar aunque la base de datos todavia no este disponible;
asi /health puede informar el fallo en lugar de morir al importar.
"""
import threading
from contextlib import contextmanager

import config

_pool = None
_lock = threading.Lock()


class DatabaseUnavailable(RuntimeError):
    """No se pudo abrir/obtener una conexion con PostgreSQL."""


def _conninfo():
    return (
        f"host={config.PGHOST} port={config.PGPORT} "
        f"dbname={config.PGDATABASE} user={config.PGUSER} "
        f"password={config.PGPASSWORD} "
        f"connect_timeout={config.DB_CONNECT_TIMEOUT} "
        f"options='-c search_path={config.PGSCHEMA},public' "
        "application_name=library-login-service"
    )


def get_pool():
    global _pool
    if _pool is None:
        with _lock:
            if _pool is None:
                try:
                    from psycopg_pool import ConnectionPool
                    from psycopg.rows import dict_row

                    _pool = ConnectionPool(
                        _conninfo(),
                        min_size=config.DB_POOL_MIN,
                        max_size=config.DB_POOL_MAX,
                        kwargs={"row_factory": dict_row},
                        timeout=config.DB_CONNECT_TIMEOUT,
                    )
                except Exception as exc:  # noqa: BLE001 - se reporta al cliente
                    raise DatabaseUnavailable(str(exc).strip()) from exc
    return _pool


@contextmanager
def connection():
    """Presta una conexion del pool y la devuelve siempre."""
    try:
        pool = get_pool()
    except Exception as exc:
        raise DatabaseUnavailable(str(exc).strip()) from exc
    try:
        with pool.connection() as conn:
            yield conn
    except DatabaseUnavailable:
        raise
    except Exception as exc:  # noqa: BLE001 - se reporta al cliente
        raise DatabaseUnavailable(str(exc).strip()) from exc


@contextmanager
def cursor(commit=False):
    """
    Cursor de diccionarios dentro de una transaccion.

    commit=False -> solo lectura (revierte al salir, para no dejar
                    transacciones abiertas).
    commit=True  -> confirma al salir sin error, revierte ante excepcion.
    """
    with connection() as conn:
        with conn.cursor() as cur:
            try:
                yield cur
            except Exception:
                conn.rollback()
                raise
            else:
                if commit:
                    conn.commit()
                else:
                    conn.rollback()


def ping():
    """Comprobacion de vida usada por /health."""
    with cursor() as cur:
        cur.execute("SELECT current_database() AS db, current_user AS usr, version() AS version")
        return cur.fetchone()


def close_pool():
    global _pool
    if _pool is not None:
        _pool.close()
        _pool = None
