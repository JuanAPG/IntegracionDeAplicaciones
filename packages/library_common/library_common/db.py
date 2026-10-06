"""
packages/library_common/library_common/db.py
Acceso a PostgreSQL con Psycopg 3: pool de conexiones y transacciones.

Es el db.py del microservicio de login, generalizado para que los cuatro
servicios nuevos lo compartan. PostgreSQL sigue siendo la FUENTE
PRINCIPAL de datos: Redis solo guarda estado efimero.

El pool se crea de forma perezosa (en la primera consulta) para que el
proceso arranque aunque la base todavia no este disponible; asi /health
puede informar el fallo en lugar de morir al importar.

Todo el SQL de los servicios usa parametros (%s): nunca se concatena un
valor del usuario dentro de una consulta.
"""
import logging
import threading
from contextlib import contextmanager

from . import metrics
from .errors import DatabaseUnavailable

log = logging.getLogger("library.db")


class Database:
    def __init__(self, *, host="localhost", port=5432, dbname="library_db",
                 user="library_user", password="", schema="library",
                 pool_min=1, pool_max=10, connect_timeout=5,
                 application_name="library-service"):
        self.host = host
        self.port = port
        self.dbname = dbname
        self.user = user
        self.password = password
        self.schema = schema
        self.pool_min = pool_min
        self.pool_max = pool_max
        self.connect_timeout = connect_timeout
        self.application_name = application_name
        self._pool = None
        self._lock = threading.Lock()

    @property
    def target(self):
        """Destino legible para los mensajes de error. Sin la contrasena."""
        return f"{self.user}@{self.host}:{self.port}/{self.dbname}"

    def _conninfo(self):
        return (
            f"host={self.host} port={self.port} dbname={self.dbname} "
            f"user={self.user} password={self.password} "
            f"connect_timeout={self.connect_timeout} "
            f"options='-c search_path={self.schema},public' "
            f"application_name={self.application_name}"
        )

    def pool(self):
        if self._pool is None:
            with self._lock:
                if self._pool is None:
                    try:
                        from psycopg.rows import dict_row
                        from psycopg_pool import ConnectionPool

                        self._pool = ConnectionPool(
                            self._conninfo(),
                            min_size=self.pool_min,
                            max_size=self.pool_max,
                            kwargs={"row_factory": dict_row},
                            timeout=self.connect_timeout,
                            open=True,
                        )
                    except Exception as exc:           # noqa: BLE001
                        raise DatabaseUnavailable(
                            "No hay conexion con PostgreSQL.",
                            [str(exc).strip(), f"Destino actual: {self.target}."]) from exc
        return self._pool

    @contextmanager
    def connection(self):
        try:
            pool = self.pool()
        except DatabaseUnavailable:
            raise
        except Exception as exc:                       # noqa: BLE001
            raise DatabaseUnavailable("No hay conexion con PostgreSQL.",
                                      [str(exc).strip()]) from exc
        try:
            with pool.connection() as conn:
                yield conn
        except DatabaseUnavailable:
            raise
        except Exception as exc:                       # noqa: BLE001
            metrics.incr("db.error")
            raise DatabaseUnavailable(
                "No hay conexion con PostgreSQL.",
                [str(exc).strip(), f"Destino actual: {self.target}."]) from exc

    @contextmanager
    def cursor(self, commit=False):
        """
        Cursor de diccionarios dentro de una transaccion.

        commit=False -> solo lectura (revierte al salir, para no dejar
                        transacciones abiertas en el servidor).
        commit=True  -> confirma al salir sin error, revierte ante excepcion.
        """
        with self.connection() as conn:
            with conn.cursor() as cur:
                try:
                    with metrics.timed("db.query"):
                        yield cur
                except Exception:
                    conn.rollback()
                    raise
                else:
                    if commit:
                        conn.commit()
                    else:
                        conn.rollback()

    def ping(self):
        """Comprobacion de vida usada por /health."""
        with self.cursor() as cur:
            cur.execute("SELECT current_database() AS db, current_user AS usr, "
                        "version() AS version")
            return cur.fetchone()

    def health(self):
        """Bloque de estado que cada servicio incrusta en su /health."""
        try:
            info = self.ping()
            return True, {"status": "ok", "database": info["db"],
                          "user": info["usr"], "schema": self.schema,
                          "server": info["version"].split(" on ")[0]}
        except Exception as exc:                       # noqa: BLE001
            return False, {"status": "error", "database": self.dbname,
                           "message": str(exc).strip()}

    def close(self):
        if self._pool is not None:
            self._pool.close()
            self._pool = None


def is_unique_violation(exc):
    """True si la excepcion es una violacion de restriccion UNIQUE."""
    code = getattr(exc, "sqlstate", None) or getattr(
        getattr(exc, "diag", None), "sqlstate", None)
    if code == "23505":
        return True
    text = str(exc).lower()
    return "unique" in text or "duplicate key" in text


def is_foreign_key_violation(exc):
    code = getattr(exc, "sqlstate", None) or getattr(
        getattr(exc, "diag", None), "sqlstate", None)
    if code == "23503":
        return True
    return "foreign key" in str(exc).lower()


def raised_message(exc):
    """
    Texto de un RAISE EXCEPTION de PL/pgSQL, sin el prefijo tecnico.

    Los procedimientos almacenados validan reglas de negocio y las
    comunican con RAISE EXCEPTION; esto recupera el mensaje legible para
    devolverlo al cliente.
    """
    text = str(exc).strip()
    for line in text.splitlines():
        line = line.strip()
        if line and not line.upper().startswith(("CONTEXT:", "DETAIL:", "HINT:")):
            return line
    return text
