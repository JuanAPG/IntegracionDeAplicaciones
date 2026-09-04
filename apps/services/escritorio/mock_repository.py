"""
apps/services/escritorio/mock_repository.py
Sustituto EN MEMORIA de library_soap_service/soap/clasificacion_repository.py,
solo para poder correr y demostrar la GUI en una maquina sin PostgreSQL
instalado (por ejemplo tu laptop, cuando el modulo SOAP real solo esta
desplegado en la VM). Implementa el MISMO contrato -- mismos nombres de
funcion, mismos tipos de retorno, las mismas excepciones de errors.py
(ValidationError/NotFound/Conflict) -- para que mock_soap_server.py
pueda darselo a soap_endpoint.py sin que ese modulo note la diferencia.

Los datos viven en variables de modulo (listas/dicts en RAM): se
reinician cada vez que se arranca mock_soap_server.py. Es justamente lo
que lo hace "replicable" para una demo -- estado predecible, sin
depender de una base de datos externa -- y por lo que NUNCA debe usarse
como reemplazo del modulo SOAP real (no persiste nada, no es seguro
para concurrencia, y sus credenciales de WS-Security son de PRUEBA).
"""
from errors import Conflict, NotFound, ValidationError

MODELOS_SERVICIO_VALIDOS = ("IaaS", "PaaS", "SaaS", "FaaS", "N/A")

# Catalogo semilla: (isbn, titulo, categoria, concepto). Equivalente en
# memoria a books + categories + concepts + book_concepts del monolito.
CATALOGO = [
    ("978-0133970777", "Fundamentos de Sistemas de Bases de Datos", "Academico", "Normalizacion"),
    ("978-1491950357", "Building Microservices", "Tecnico", "Microservicio"),
    ("978-0132350884", "Clean Code", "Ingenieria de Software", "Principios SOLID"),
    ("978-0262035613", "Deep Learning", "Inteligencia Artificial", "Redes Neuronales"),
]

# Credencial de PRUEBA para ObtenerEstadisticasPorModelo (WS-Security).
# NUNCA es la credencial real del modulo SOAP en produccion.
CREDENCIALES_DEMO = {"admin_demo": "demo-2026"}

# email -> {concepto_nombre: modelo_servicio}
_clasificaciones = {}
# (tipo_cliente, identificador) -> peticiones_atendidas
_clientes_servidos = {}


def conceptos_pendientes(email, limite):
    ya_clasificados = _clasificaciones.get(email, {})
    pendientes = [
        {"referencia_libro": isbn, "referencia_concepto": concepto,
         "titulo_libro": titulo, "nombre_categoria": categoria, "nombre_concepto": concepto}
        for isbn, titulo, categoria, concepto in CATALOGO
        if concepto not in ya_clasificados
    ]
    return pendientes[:limite]


def registrar_clasificacion(email, isbn, concepto_nombre, modelo_servicio):
    if modelo_servicio not in MODELOS_SERVICIO_VALIDOS:
        raise ValidationError(
            f"El modelo de servicio '{modelo_servicio}' no es valido. "
            f"Valores permitidos: {', '.join(MODELOS_SERVICIO_VALIDOS)}.",
            code="modelo_invalido")

    if not any(isbn == c[0] for c in CATALOGO):
        raise NotFound(f"No existe un libro con ISBN '{isbn}'.", code="libro_inexistente")

    if not any(concepto_nombre == c[3] for c in CATALOGO):
        raise NotFound(f"No existe el concepto '{concepto_nombre}'.", code="concepto_inexistente")

    clasificados = _clasificaciones.setdefault(email, {})
    if concepto_nombre in clasificados:
        raise Conflict(
            f"El clasificador '{email}' ya habia registrado el concepto '{concepto_nombre}'.",
            code="clasificacion_duplicada")

    clasificados[concepto_nombre] = modelo_servicio
    return "Clasificacion guardada exitosamente."


def progreso_usuario(email):
    total_conceptos = len({c[3] for c in CATALOGO})
    clasificados = len(_clasificaciones.get(email, {}))
    return clasificados, total_conceptos - clasificados


def registrar_cliente_servido(tipo_cliente, identificador):
    key = (tipo_cliente, identificador)
    _clientes_servidos[key] = _clientes_servidos.get(key, 0) + 1


def verificar_credencial_soap(username, password):
    return CREDENCIALES_DEMO.get(username) == password


def estadisticas_por_modelo():
    conteo = {m: 0 for m in ("IaaS", "PaaS", "SaaS", "FaaS")}
    for clasificados in _clasificaciones.values():
        for modelo in clasificados.values():
            if modelo in conteo:
                conteo[modelo] += 1
    return conteo
