"""
tracking_server/entregas.py
El estado de cada entrega y como avanza.

LA DIFERENCIA MAS IMPORTANTE CON EL PROYECTO DE REFERENCIA: alli los
vehiculos circulaban EN BUCLE INFINITO -- al llegar al ultimo punto se
inventaban otra ruta y seguian para siempre. Aqui una entrega TERMINA:
al consumir el ultimo punto de la ruta el estado pasa a `entregado` y el
vehiculo se detiene. El enunciado lo pide de forma explicita: el estado
"Entregado" debe corresponder al final de la ruta y no a un cambio
arbitrario de texto.
"""
import threading
import time

import config
import rutas

# Los cinco estados del enunciado, en orden.
CONFIRMADO = "Pedido confirmado"
PREPARANDO = "Preparando pedido"
ENVIADO = "Pedido enviado"
EN_RUTA = "En ruta de entrega"
ENTREGADO = "Entregado"

ORDEN = [CONFIRMADO, PREPARANDO, ENVIADO, EN_RUTA, ENTREGADO]


class Entrega:
    """
    Una entrega en curso, atada a un codigo de rastreo.

    El avance se calcula por TIEMPO TRANSCURRIDO y no por numero de
    ticks: si el servidor se queda corto de CPU y un tick tarda 1.4 s en
    lugar de 1.0, el vehiculo recorre lo que corresponde a 1.4 s. Contar
    ticks haria que la entrega fuera mas lenta cuanto mas cargado
    estuviera el servidor, que es justo lo que no se quiere al medir
    nada.
    """

    def __init__(self, codigo, numero_pedido=None):
        self.codigo = codigo.strip().upper()
        self.numero_pedido = numero_pedido
        self.destino, self.puntos = rutas.ruta_de(self.codigo)
        self.longitud_m = rutas.longitud_total(self.puntos)

        self.indice = 0            # tramo actual de la polilinea
        self.avance_tramo = 0.0    # metros recorridos dentro del tramo
        self.recorrido_m = 0.0
        self.lat, self.lon = self.puntos[0]
        self.rumbo = rutas.rumbo(self.puntos[0], self.puntos[1]) if len(self.puntos) > 1 else 0.0
        self.velocidad_kmh = 0.0

        self.estado = CONFIRMADO
        self.creada_en = time.time()
        self.ultimo_tick = self.creada_en
        self.entregada_en = None
        self.estela = [(self.lat, self.lon)]

    # -----------------------------------------------------------------
    # Avance
    # -----------------------------------------------------------------
    def avanzar(self, ahora=None):
        """
        Mueve la entrega hasta `ahora`. Devuelve True si cambio el estado,
        para que el servidor solo difunda eventos de estado cuando los hay.
        """
        ahora = ahora if ahora is not None else time.time()
        # El tiempo de reparto corre mas rapido que el reloj: ver
        # FACTOR_TIEMPO en config.py. Todo lo que sigue razona en
        # segundos de reparto, no de reloj.
        dt = max(0.0, ahora - self.ultimo_tick) * config.FACTOR_TIEMPO
        self.ultimo_tick = ahora
        estado_previo = self.estado

        # Las fases previas a la salida SI van en segundos de reloj: son
        # cortas de por si y, aceleradas, pasarian tan rapido que nadie
        # llegaria a ver los estados "confirmado" y "preparando". Lo que
        # se acelera es el trayecto, que es lo que de verdad dura.
        edad = ahora - self.creada_en
        preparacion = config.SEGUNDOS_CONFIRMADO + config.SEGUNDOS_PREPARANDO + config.SEGUNDOS_ENVIADO

        if self.estado == ENTREGADO:
            return False

        # Los tres primeros estados son de preparacion: el vehiculo
        # todavia no se mueve del almacen.
        if edad < config.SEGUNDOS_CONFIRMADO:
            self.estado = CONFIRMADO
        elif edad < config.SEGUNDOS_CONFIRMADO + config.SEGUNDOS_PREPARANDO:
            self.estado = PREPARANDO
        elif edad < preparacion:
            self.estado = ENVIADO
        else:
            if self.estado != EN_RUTA:
                self.estado = EN_RUTA
            self._mover(dt)

        return self.estado != estado_previo

    def _mover(self, dt):
        metros = (config.VELOCIDAD_KMH / 3.6) * dt
        while metros > 0 and self.indice < len(self.puntos) - 1:
            a = self.puntos[self.indice]
            b = self.puntos[self.indice + 1]
            largo = rutas.distancia_m(a, b)
            restante = largo - self.avance_tramo

            if metros < restante:
                self.avance_tramo += metros
                self.recorrido_m += metros
                fraccion = self.avance_tramo / largo if largo > 0 else 1.0
                self.lat, self.lon = rutas.interpolar(a, b, fraccion)
                self.rumbo = rutas.rumbo(a, b)
                metros = 0
            else:
                metros -= restante
                self.recorrido_m += restante
                self.indice += 1
                self.avance_tramo = 0.0
                self.lat, self.lon = b
                if self.indice < len(self.puntos) - 1:
                    self.rumbo = rutas.rumbo(b, self.puntos[self.indice + 1])

        self.velocidad_kmh = config.VELOCIDAD_KMH

        # AQUI TERMINA LA RUTA, y con ella la entrega. No se recicla.
        if self.indice >= len(self.puntos) - 1:
            self.lat, self.lon = self.puntos[-1]
            self.estado = ENTREGADO
            self.velocidad_kmh = 0.0
            self.entregada_en = time.time()

        self._anotar_estela()

    def _anotar_estela(self):
        ultimo = self.estela[-1]
        # Solo se anota si el vehiculo se movio de verdad: sin esto, la
        # estela se llena de puntos repetidos mientras esta parado.
        if rutas.distancia_m(ultimo, (self.lat, self.lon)) >= 5:
            self.estela.append((self.lat, self.lon))
            if len(self.estela) > config.MAX_ESTELA:
                del self.estela[0:len(self.estela) - config.MAX_ESTELA]

    # -----------------------------------------------------------------
    # Lo que se publica
    # -----------------------------------------------------------------
    @property
    def progreso(self):
        if self.longitud_m <= 0:
            return 1.0
        return min(1.0, self.recorrido_m / self.longitud_m)

    @property
    def eta_segundos(self):
        if self.estado == ENTREGADO:
            return 0
        faltan_m = max(0.0, self.longitud_m - self.recorrido_m)
        return int(faltan_m / max(1.0, config.VELOCIDAD_KMH / 3.6))

    def posicion(self):
        return {
            "type": "posicion",
            "code": self.codigo,
            "orderNumber": self.numero_pedido,
            "lat": round(self.lat, 6),
            "lon": round(self.lon, 6),
            "heading": round(self.rumbo, 1),
            "speedKmh": round(self.velocidad_kmh, 1),
            "status": self.estado,
            "progress": round(self.progreso, 4),
            "etaSeconds": self.eta_segundos,
            "remainingMeters": int(max(0.0, self.longitud_m - self.recorrido_m)),
            "timestamp": time.time(),
        }

    def evento_estado(self):
        return {
            "type": "estado",
            "code": self.codigo,
            "orderNumber": self.numero_pedido,
            "status": self.estado,
            "progress": round(self.progreso, 4),
            "timestamp": time.time(),
        }

    def snapshot(self):
        """
        Todo lo que necesita un cliente que acaba de conectarse: la ruta
        completa para dibujarla, la estela ya recorrida y la posicion
        actual. Asi el mapa se pinta entero de una vez en lugar de
        aparecer poco a poco.
        """
        return {
            "type": "snapshot",
            "code": self.codigo,
            "orderNumber": self.numero_pedido,
            "status": self.estado,
            "origin": rutas.ALMACEN,
            "destination": self.destino,
            "route": [[round(p[0], 6), round(p[1], 6)] for p in self.puntos],
            "trail": [[round(p[0], 6), round(p[1], 6)] for p in self.estela],
            "lat": round(self.lat, 6),
            "lon": round(self.lon, 6),
            "heading": round(self.rumbo, 1),
            "progress": round(self.progreso, 4),
            "etaSeconds": self.eta_segundos,
            "totalMeters": int(self.longitud_m),
            "states": ORDEN,
            "timestamp": time.time(),
        }


class Registro:
    """
    Las entregas vivas, por codigo. En memoria.

    QUE SE PIERDE AL REINICIAR: el progreso de las entregas en curso. Es
    una decision consciente y no un descuido -- este servidor es un
    emisor en tiempo real, no el dueno del estado del negocio. La verdad
    de un pedido (su estado real, sus importes) vive en el microservicio
    de pedidos y en PostgreSQL. Si este proceso muere, al volver
    reconstruye la MISMA ruta para el mismo codigo, porque el destino se
    deriva del codigo y no de un sorteo.
    """

    def __init__(self):
        self._entregas = {}
        self._lock = threading.RLock()

    def obtener_o_crear(self, codigo, numero_pedido=None):
        clave = codigo.strip().upper()
        with self._lock:
            entrega = self._entregas.get(clave)
            if entrega is None:
                entrega = Entrega(clave, numero_pedido)
                self._entregas[clave] = entrega
            elif numero_pedido and not entrega.numero_pedido:
                entrega.numero_pedido = numero_pedido
            return entrega

    def obtener(self, codigo):
        with self._lock:
            return self._entregas.get(codigo.strip().upper())

    def activas(self):
        with self._lock:
            return list(self._entregas.values())

    def reiniciar(self, codigo):
        """Vuelve a empezar la entrega. Util para volver a demostrarla."""
        clave = codigo.strip().upper()
        with self._lock:
            anterior = self._entregas.pop(clave, None)
            numero = anterior.numero_pedido if anterior else None
            entrega = Entrega(clave, numero)
            self._entregas[clave] = entrega
            return entrega
