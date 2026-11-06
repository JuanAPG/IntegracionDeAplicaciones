"""
tracking_server/rutas.py
Las rutas de reparto por calles reales de Monterrey.

DE DONDE SALEN LAS COORDENADAS. No estan escritas a mano ni son lineas
rectas: `rutas_monterrey.json` son 120 tramos entre 16 puntos de la
ciudad, calculados en su dia con OSRM (el motor de ruteo de
OpenStreetMap) y cacheados. Cada tramo trae la polilinea completa punto
por punto, de modo que el vehiculo circula por calles y no atraviesa
manzanas. El archivo viene del proyecto de rastreo GPS que el enunciado
da como referencia; aqui se reutiliza en lugar de volver a pedirselo a
OSRM en caliente, que ademas dejaria la aplicacion colgada esperando una
respuesta HTTP.

POR QUE LA RUTA ES DETERMINISTA POR CODIGO. El enunciado lo pide
expresamente: no basta con ensenar siempre el mismo vehiculo por la
misma ruta. Aqui el destino se deriva del codigo de rastreo con un hash
estable, asi que LIB-MTY-2026-000042 siempre va al mismo sitio, y dos
pedidos distintos van a sitios distintos. Si se reinicia el servidor, el
mismo codigo reconstruye la misma ruta.
"""
import hashlib
import json
import math
import os

_ARCHIVO = os.path.join(os.path.dirname(__file__), "rutas_monterrey.json")

# El almacen de la libreria. Fijo: todas las entregas salen de aqui.
ALMACEN = "Parque Fundidora"

# Coordenadas de los puntos de la ciudad, tomadas del proyecto de
# referencia. Solo los 16 que son ruteables: se excluyeron a proposito
# el Cerro de la Silla (es un cerro, el ruteador engancha a 1.2 km) y el
# aeropuerto (la terminal queda a 600 m de la vialidad).
LANDMARKS = {
    "Macroplaza": (25.6714, -100.3089),
    "Parque Fundidora": (25.6793, -100.2847),
    "San Pedro Garza García": (25.6500, -100.3600),
    "UDEM": (25.6558, -100.4106),
    "Tec de Monterrey": (25.6514, -100.2895),
    "Guadalupe": (25.6775, -100.2597),
    "Santa Catarina": (25.6733, -100.4583),
    "Escobedo": (25.7933, -100.3167),
    "Apodaca": (25.7811, -100.1886),
    "Estadio BBVA": (25.6692, -100.2447),
    "Cumbres": (25.7333, -100.3833),
    "Mitras": (25.7017, -100.3647),
    "Linda Vista": (25.6889, -100.2342),
    "San Nicolás": (25.7417, -100.2825),
    "Valle Oriente": (25.6386, -100.3350),
    "Obispado": (25.6742, -100.3344),
}

# Destinos posibles de una entrega: todos menos el propio almacen.
DESTINOS = sorted(nombre for nombre in LANDMARKS if nombre != ALMACEN)

with open(_ARCHIVO, encoding="utf-8") as _f:
    _TRAMOS = json.load(_f)["tramos"]


def _puntos(origen, destino):
    """
    La polilinea entre dos puntos.

    La cache guarda solo un sentido (A|B); el contrario se obtiene
    invirtiendo la lista, que es exactamente la misma calle al reves.
    """
    directo = _TRAMOS.get(f"{origen}|{destino}")
    if directo:
        return [tuple(p) for p in directo["puntos"]]
    inverso = _TRAMOS.get(f"{destino}|{origen}")
    if inverso:
        return [tuple(p) for p in reversed(inverso["puntos"])]
    # No deberia pasar con los 16 ruteables (estan los 120 pares), pero
    # si pasara, mas vale una recta avisada que un error opaco.
    return [LANDMARKS[origen], LANDMARKS[destino]]


def destino_de(codigo):
    """
    El destino que le toca a un codigo de rastreo.

    SHA-256 del codigo en lugar de hash() de Python: hash() de las
    cadenas esta aleatorizado por proceso (PYTHONHASHSEED), de modo que
    el mismo codigo daria un destino distinto tras reiniciar. Con
    SHA-256 el resultado es el mismo siempre y en cualquier maquina.
    """
    digest = hashlib.sha256(codigo.strip().upper().encode("utf-8")).digest()
    return DESTINOS[int.from_bytes(digest[:4], "big") % len(DESTINOS)]


def ruta_de(codigo):
    """Devuelve (nombre_destino, lista de puntos) para un codigo."""
    destino = destino_de(codigo)
    return destino, _puntos(ALMACEN, destino)


def distancia_m(a, b):
    """Distancia en metros entre dos (lat, lon), por circulo maximo."""
    radio = 6371008.8
    lat1, lon1 = math.radians(a[0]), math.radians(a[1])
    lat2, lon2 = math.radians(b[0]), math.radians(b[1])
    dlat, dlon = lat2 - lat1, lon2 - lon1
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * radio * math.asin(min(1.0, math.sqrt(h)))


def rumbo(a, b):
    """Rumbo en grados (0 = norte) de a hacia b, para orientar el icono."""
    lat1, lat2 = math.radians(a[0]), math.radians(b[0])
    dlon = math.radians(b[1] - a[1])
    y = math.sin(dlon) * math.cos(lat2)
    x = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(dlon)
    return (math.degrees(math.atan2(y, x)) + 360) % 360


def interpolar(a, b, fraccion):
    """Un punto entre a y b. Con tramos cortos, lineal basta."""
    return (a[0] + (b[0] - a[0]) * fraccion, a[1] + (b[1] - a[1]) * fraccion)


def longitud_total(puntos):
    return sum(distancia_m(puntos[i], puntos[i + 1]) for i in range(len(puntos) - 1))
