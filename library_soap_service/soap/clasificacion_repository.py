"""
library_soap_service/soap/clasificacion_repository.py
Capa de acceso a datos del modulo de clasificacion en la nube.

Toda la logica de negocio que toca la base -- resolver o dar de alta al
clasificador, calcular pendientes, registrar una clasificacion, llevar
la bitacora de clientes servidos -- vive en PostgreSQL como vistas y
funciones/procedimientos almacenados (sql/soap_module.sql). Esta capa
NO arma sentencias SQL: solo llama a esas funciones con parametros
enlazados (%s) y traduce filas a estructuras Python. Ninguna entrada
del cliente SOAP se concatena en una cadena SQL.

Atomicidad y rollback
  * db.cursor(commit=True) abre una transaccion por llamada: si algo
    lanza dentro del bloque `with`, db.py hace ROLLBACK completo y
    relanza (ver db.py); si termina sin excepcion, hace COMMIT.
  * sp_registrar_clasificacion, la unica operacion que puede escribir en
    dos tablas en la misma llamada (clasificadores y
    clasificaciones_cloud), es ademas atomica DENTRO de PostgreSQL: usa
    un SAVEPOINT implicito para poder devolver el resultado sin perder
    el alta del clasificador ni arrastrar a toda la transaccion. Ver el
    comentario de esa funcion en soap_module.sql.

Errores de negocio
  Esta capa NO devuelve pares (exito, mensaje): traduce cada falla
  conocida a una excepcion de errors.py (ValidationError/NotFound/
  Conflict), la misma jerarquia que ya usa books_repository.py para la
  API REST/XML. soap_endpoint.py las atrapa y arma el SOAP Fault con la
  categoria correcta (ver la tabla de casos en ese modulo).
"""
import db
from errors import Conflict, NotFound, ValidationError

MODELOS_SERVICIO_VALIDOS = ("IaaS", "PaaS", "SaaS", "FaaS", "N/A")

# codigo_error que puede devolver sp_registrar_clasificacion (ver
# soap_module.sql) -> (clase de excepcion, codigo legible para el Fault).
_ERRORES_REGISTRO = {
    "LIBRO_INEXISTENTE": (NotFound, "libro_inexistente"),
    "CONCEPTO_INEXISTENTE": (NotFound, "concepto_inexistente"),
    "DUPLICADO": (Conflict, "clasificacion_duplicada"),
    "MODELO_INVALIDO": (ValidationError, "modelo_invalido"),
}


def conceptos_pendientes(email, limite):
    with db.cursor(commit=True) as cur:
        cur.execute("SELECT * FROM library.sp_conceptos_pendientes(%s, %s)", (email, limite))
        rows = cur.fetchall()
    return [dict(row) for row in rows]


def registrar_clasificacion(email, isbn, concepto_nombre, modelo_servicio):
    """
    Devuelve el mensaje de exito, o lanza ValidationError/NotFound/Conflict.

    El modelo se valida aqui primero (sin ir a la base) para no dar de
    alta un clasificador ni abrir una transaccion por una peticion que ya
    se sabe invalida; libro, concepto y duplicado los resuelve el
    procedimiento almacenado, que es quien conoce el estado real de la
    base dentro de la misma transaccion atomica.
    """
    if modelo_servicio not in MODELOS_SERVICIO_VALIDOS:
        raise ValidationError(
            f"El modelo de servicio '{modelo_servicio}' no es valido. "
            f"Valores permitidos: {', '.join(MODELOS_SERVICIO_VALIDOS)}.",
            code="modelo_invalido")

    with db.cursor(commit=True) as cur:
        cur.execute(
            "SELECT * FROM library.sp_registrar_clasificacion(%s, %s, %s, %s)",
            (email, isbn, concepto_nombre, modelo_servicio))
        row = cur.fetchone()

    if row["exito"]:
        return row["mensaje"]

    exc_class, codigo = _ERRORES_REGISTRO.get(row["codigo_error"], (ValidationError, "error_negocio"))
    raise exc_class(row["mensaje"], code=codigo)


def progreso_usuario(email):
    """Devuelve (total_clasificados, total_pendientes)."""
    with db.cursor(commit=True) as cur:
        cur.execute("SELECT * FROM library.sp_progreso_usuario(%s)", (email,))
        row = cur.fetchone()
    return row["total_clasificados"], row["total_pendientes"]


def registrar_cliente_servido(tipo_cliente, identificador):
    """
    Bitacora best-effort de que cliente de escritorio hizo la peticion
    (tipo_cliente/identificador viajan en un encabezado SOAP opcional,
    ver soap_endpoint.py). Un fallo aqui no debe tumbar la operacion de
    negocio que pidio el cliente.
    """
    with db.cursor(commit=True) as cur:
        cur.execute("SELECT library.sp_registrar_cliente_servido(%s, %s)",
                    (tipo_cliente, identificador))
