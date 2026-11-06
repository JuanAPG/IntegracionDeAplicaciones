"""
tracking_server/config.py
Configuracion del servidor de rastreo. Todo por variables de entorno:
ninguna credencial escrita en el codigo.
"""
import os


def _entero(nombre, por_omision):
    try:
        return int(os.getenv(nombre, "").strip() or por_omision)
    except ValueError:
        return por_omision


def _booleano(nombre, por_omision):
    valor = (os.getenv(nombre) or "").strip().lower()
    if not valor:
        return por_omision
    return valor in ("1", "true", "yes", "si", "on")


# ---------------------------------------------------------------------
# Servidor
# ---------------------------------------------------------------------
HOST = os.getenv("HOST", "0.0.0.0")
PORT = _entero("PORT", 5900)
DEBUG = _booleano("DEBUG", False)

# ---------------------------------------------------------------------
# Autenticacion
#
# El MISMO secreto HS256 que usan los seis microservicios. Se acepta el
# nombre anterior JWT_SECRET por compatibilidad, igual que hacen ellos.
# Sin secreto configurado, este servidor NO puede verificar firmas; en
# ese caso se niega a arrancar en modo autenticado en lugar de aceptar
# cualquier token, que seria peor que no pedir ninguno.
# ---------------------------------------------------------------------
JWT_SECRET = os.getenv("JWT_SECRET_KEY") or os.getenv("JWT_SECRET") or ""
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
JWT_ISSUER = os.getenv("JWT_ISSUER", "library-login-service")

# Con REQUIRE_AUTH=false el rastreo queda abierto. Solo para demostrar
# el mapa sin levantar los microservicios; NUNCA en un despliegue real.
REQUIRE_AUTH = _booleano("REQUIRE_AUTH", True)

# ---------------------------------------------------------------------
# El microservicio de pedidos es quien decide de quien es cada pedido.
#
# Este servidor NO tiene base de datos ni sabe de quien es nada: para
# autorizar un rastreo le pregunta al servicio de pedidos usando el
# MISMO token del usuario. Si el servicio responde 200, es su pedido; si
# responde 403 o 404, no lo es. Asi la regla de propiedad vive en un solo
# sitio y no se duplica aqui, donde se quedaria desactualizada.
# ---------------------------------------------------------------------
PEDIDOS_URL = os.getenv("PEDIDOS_URL", "http://34.51.89.203:5004")
PEDIDOS_TIMEOUT = _entero("PEDIDOS_TIMEOUT", 8)

# ---------------------------------------------------------------------
# Simulacion
# ---------------------------------------------------------------------
# Cada cuantos segundos avanza el vehiculo y se emite su posicion.
INTERVALO_S = float(os.getenv("INTERVALO_S", "1.0"))
# Velocidad del reparto en km/h. 35 es una velocidad urbana creible.
VELOCIDAD_KMH = float(os.getenv("VELOCIDAD_KMH", "35"))

# ACELERACION DE LA SIMULACION. La ruta mas larga del catalogo de
# destinos mide 16.8 km; a 35 km/h son 29 minutos reales, demasiado para
# ensenar una entrega completa. Con el factor en 10, cada segundo de
# reloj avanza 10 segundos de reparto y esa misma ruta se recorre en
# menos de 3 minutos.
#
# Se hace asi, y no subiendo la velocidad a 350 km/h, porque es honesto:
# el vehiculo circula a una velocidad urbana creible y lo que se acelera
# es el RELOJ, que es justo lo que hace cualquier simulador. La interfaz
# lo dice en pantalla ("simulacion acelerada x10") para que nadie crea
# que el reparto tarda tres minutos en la vida real.
FACTOR_TIEMPO = float(os.getenv("FACTOR_TIEMPO", "10"))
# Segundos que el pedido pasa en cada estado previo a la salida. Cortos
# a proposito: es una demostracion, no una espera real de dos dias.
SEGUNDOS_CONFIRMADO = float(os.getenv("SEGUNDOS_CONFIRMADO", "4"))
SEGUNDOS_PREPARANDO = float(os.getenv("SEGUNDOS_PREPARANDO", "8"))
SEGUNDOS_ENVIADO = float(os.getenv("SEGUNDOS_ENVIADO", "4"))
# Cuantos puntos del recorrido se conservan para dibujar la estela.
MAX_ESTELA = _entero("MAX_ESTELA", 400)
