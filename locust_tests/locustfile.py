"""
locust_tests/locustfile.py
=========================================================================
PRUEBAS DE RENDIMIENTO CON LOCUST
Monolito web (Node/Express) contra la arquitectura de SEIS microservicios
Flask de la Libreria en Linea, sobre la instancia de GCP.

-------------------------------------------------------------------------
1. QUE MIDE ESTE ARCHIVO
-------------------------------------------------------------------------
Siete destinos a la vez desde UNA sola clase de usuario virtual, que
pide con URL absoluta a cada puerto. Las estadisticas quedan separadas
por sistema y por servicio gracias al nombre de cada peticion:

    [monolito]  http://<IP>:3000      Node + Express + EJS (HTML servido)
    [login]     http://<IP>:5000      autenticacion
    [books]     http://<IP>:5001      catalogo de libros
    [users]     http://<IP>:5002      cuentas
    [authors]   http://<IP>:5003      autores
    [pedidos]   http://<IP>:5004      pedidos (se identifica como "orders")
    [pagos]     http://<IP>:5005      pagos (se identifica como "payments")

Toda peticion lleva un nombre con el prefijo del destino entre corchetes
(`name="[books] GET /books?format=json"`), que es lo que aparece en la
columna Name de la interfaz y en los CSV. Asi se puede comparar la misma
operacion -- "dame el catalogo" -- en el monolito y en el microservicio.

-------------------------------------------------------------------------
2. LA COMPARACION: QUE SE CONSIDERA "COMPARABLE"
-------------------------------------------------------------------------
El par comparable del ejercicio es el CATALOGO, porque es la unica
operacion de negocio que los dos sistemas ofrecen sin autenticacion:

    [monolito] GET /library/libros          -> HTML completo (~16 KB)
    [books]    GET /books?format=json       -> JSON          (~19 KB)
    [books]    GET /books?format=xml        -> XML

No son identicos y conviene decirlo antes de sacar conclusiones: el
monolito RENDERIZA una plantilla EJS (consulta + plantilla + HTML) y el
microservicio SERIALIZA datos (consulta + JSON/XML). El monolito hace mas
trabajo por peticion; el microservicio paga, en cambio, la red del
cliente que luego tiene que pintar. La comparacion que si es honesta es:
cuanto tarda y cuanto aguanta cada sistema al entregar "la lista de
libros" por su via natural.

El segundo par comparable es el DETALLE de un libro por ISBN:

    [monolito] GET /library/libros/<ISBN>   -> HTML
    [books]    GET /books/<ISBN>?format=json

-------------------------------------------------------------------------
3. INVENTARIO DE RUTAS -- VERIFICADO EN VIVO, NO SUPUESTO
-------------------------------------------------------------------------
Las rutas de abajo se comprobaron una por una con curl contra la
instancia el 2026-10-30 (codigo de estado y cuerpo). Se usa la cabecera
`Allow` de una peticion OPTIONS para descubrir los metodos admitidos.
Esto importa porque la version DESPLEGADA no coincide con el codigo del
repositorio: en la instancia los recursos estan en INGLES (`/orders`,
`/payments`, `/users`) y los filtros del catalogo en ESPANOL (`titulo`,
`autor`, `genero`, `precio_min`...).

    PUBLICO (sin token) -- es con lo que se genera la carga:
      [monolito] GET /library/                 200  portada HTML
      [monolito] GET /library/libros           200  catalogo HTML
      [monolito] GET /library/libros/<ISBN>    200  detalle HTML
      [monolito] GET /library/login            200  formulario
      [monolito] GET /library/registro         200  formulario
      [books]    GET /books                    200  XML por omision
      [books]    GET /books?format=json|xml    200  representacion explicita
      [books]    GET /books/<ISBN>             200  detalle (404 si no existe)
      [books]    GET /books?<filtros>          200  titulo/autor/genero/...
      [authors]  GET /authors                  200  clave JSON "autores"
      [authors]  GET /authors/<id>             200  clave JSON "id_autor"
      LOS SEIS   GET /health?format=json       200  {"service","status","db","redis"}

    EXIGE Authorization: Bearer (401 sin token) -- NO hay lectura publica:
      [login]    GET /session                  401
      [users]    GET /users                    401
      [pedidos]  GET /orders                   401
      [pagos]    GET /payments                 401
      LOS SEIS   GET /metrics                  401

    NO EXISTEN en la version desplegada (404 comprobado):
      /docs, /openapi.json en los seis;  /envios/<numero> y /pedidos en
      pedidos;  /pagos en pagos;  /books/search, /books/isbn/<isbn>,
      /formats, /categories, /genres, /concepts, /cloud-concepts y
      /soap/clasificacion en books;  /validate-email en login;
      /health en el monolito.

    AVISO SOBRE LOS PUERTOS. El enunciado lista "pagos 5002, pedidos
    5003, users 5004, autores 5005". La instancia responde al contrario,
    y no es una suposicion: cada `GET /health` dice que servicio es.
        5002 -> {"service":"users"}     5003 -> {"service":"authors"}
        5004 -> {"service":"orders"}    5005 -> {"service":"payments"}
    Se usa el mapa REAL. El propio arranque de la prueba lo vuelve a
    comprobar y avisa si algun puerto contesta con otra identidad.

-------------------------------------------------------------------------
4. LOS PARAMETROS, UNO POR UNO
-------------------------------------------------------------------------
* usuarios (`-u`, "Number of users"): cuantos clientes virtuales hay
  dentro a la vez. Cada uno es un greenlet que repite: elegir tarea ->
  pedir -> esperar. Es CONCURRENCIA, no peticiones por segundo.

* spawn_rate (`-r`, "Ramp up"): cuantos usuarios nuevos entran por
  segundo hasta alcanzar el total. Con 20 usuarios y rampa 2 se tardan
  10 s en estar todos dentro. Arrancarlos de golpe mide el arranque, no
  el regimen estable.

* duracion (`-t`): cuanto corre la prueba. Los perfiles de abajo la
  fijan ellos mismos.

* pausa entre tareas (`wait_time`): lo que espera un usuario virtual
  entre una peticion y la siguiente. Aqui `between(1, 2)` -- entre 1 y 2
  segundos al azar. Es la pieza que mas se malinterpreta: con 5 usuarios
  y pausa de 1-2 s el techo teorico son ~3-5 peticiones/segundo, de modo
  que el RPS que se observe NO es la capacidad del servidor, sino lo que
  estos 5 clientes piden. Para medir capacidad habria que bajar la pausa
  o subir los usuarios.

* UMBRAL DE SERVICIO (el del enunciado, sin cambios):
      p95 > 1000 ms   o   errores > 5 %   ->  servicio DEGRADADO
  El p95 es el percentil 95: el 95 % de las peticiones fue mas rapido
  que ese valor. Se usa en lugar del promedio porque el promedio esconde
  justo la cola lenta que sufre el usuario.

-------------------------------------------------------------------------
5. LOS SEIS PERFILES
-------------------------------------------------------------------------
Se elige con la variable de entorno PERFIL. Con PERFIL puesto, la forma
de la carga la decide `PerfilDeCarga` (una LoadTestShape) y por eso se
IGNORAN `-u`, `-r` y `-t`: el perfil ya los lleva dentro. Sin PERFIL no
se define ninguna forma y manda la interfaz grafica o la linea de
ordenes.

    PERFIL=smoke     1 usuario, 30 s.                 Que el escenario y
                     las rutas responden. Carga minima.
    PERFIL=load      5 usuarios, rampa 1/s, 2 min.    Comportamiento con
                     la carga esperada, estable.
    PERFIL=stress    2 -> 20 usuarios por etapas,     Degradacion al
                     7 etapas de 25 s, 3 min.         pasar de lo esperado.
    PERFIL=spike     2 -> 15 de golpe, se mantiene,   Efecto del pico y
                     vuelve a 2; 2 min.               la recuperacion.
    PERFIL=soak      3 usuarios, 4 min.               Degradacion por
                     (miniatura didactica)            carga sostenida.
    PERFIL=quiebre   desde 1 usuario, +1 cada 12 s,   Cuando se incumple
                     maximo 20, limite 4 min; DEJA    el umbral.
                     de subir al incumplir el umbral.

-------------------------------------------------------------------------
6. COMO SE EJECUTA
-------------------------------------------------------------------------
    pip install locust
    cd locust_tests

    # un perfil, con evidencias (CSV + HTML) en evidencias/
    PERFIL=smoke locust --headless \
        --csv evidencias/smoke --html evidencias/smoke.html

    # interfaz grafica (sin PERFIL: los usuarios se ponen a mano)
    locust                       # -> http://localhost:8089

NO se pasa `--host`: cada clase de usuario trae el suyo, y `--host` los
sobreescribiria TODOS, mandando las siete baterias al mismo puerto. La
IP se cambia con la variable de entorno VM_IP.

La carga se genera desde el equipo local contra la instancia de GCP, que
es lo que pide el enunciado (no se apunta a localhost).

-------------------------------------------------------------------------
7. CREDENCIALES
-------------------------------------------------------------------------
Este archivo NO contiene contrasenas ni tokens, y no debe contenerlos.
Las rutas autenticadas (`/users`, `/orders`, `/payments`, `/session`) se
prueban por omision SIN token, exigiendo el 401: eso verifica la cadena
completa de autorizacion (comprobar el Bearer y la revocacion en Redis)
sin tocar datos y sin guardar secretos.

Si se exportan LIBRARY_EMAIL y LIBRARY_PASSWORD en el entorno, el
arranque pide un token a `POST /login` y anade lecturas autenticadas. El
token vive solo en memoria. En la corrida que acompana a esta entrega NO
se usaron credenciales, de modo que esas lecturas quedaron como el 401.
"""
from __future__ import annotations

import os
import time
from collections import Counter

import requests
from locust import HttpUser, LoadTestShape, between, events, task

# =====================================================================
# Destinos
# =====================================================================
# La IP de la instancia es EFIMERA: cambia en CADA reinicio de la VM.
# Se cambia con la variable de entorno VM_IP, nunca editando las clases.
# Historial comprobado: 34.51.65.207 (corridas del 2026-10-30) ->
# 34.51.14.158 -> 34.51.89.203 (reinicio del 2026-11-01).
VM_IP = os.getenv("VM_IP", "34.51.89.203")

PUERTOS = {
    "monolito": 3000,
    "login": 5000,
    "books": 5001,
    "users": 5002,
    "authors": 5003,
    "pedidos": 5004,
    "pagos": 5005,
}

# Identidad que cada microservicio declara en su /health. Se comprueba al
# arrancar: si un puerto contesta con otro nombre, el mapa de puertos
# cambio y las estadisticas estarian mal etiquetadas.
IDENTIDAD_ESPERADA = {
    "login": "login", "books": "books", "users": "users",
    "authors": "authors", "pedidos": "orders", "pagos": "payments",
}


def base(destino: str) -> str:
    return f"http://{VM_IP}:{PUERTOS[destino]}"


# =====================================================================
# Umbral de servicio (el del enunciado)
# =====================================================================
P95_UMBRAL_MS = 1000.0     # p95 por encima de 1 s -> degradado
ERROR_UMBRAL = 0.05        # mas de 5 % de errores -> degradado

# Pausa entre tareas de un mismo usuario virtual. Ver seccion 4.
PAUSA = between(1, 2)

# Tiempo limite de cada peticion. Generoso a proposito: se quiere MEDIR
# la degradacion, no cortarla antes de que se vea.
TIEMPO_LIMITE = 15

PERFIL = os.getenv("PERFIL", "").strip().lower()

# ISBN reales del catalogo. Se rellenan en test_start leyendo el propio
# servicio, para no escribir datos de prueba a mano.
CATALOGO: dict = {"isbn": ["978-0451524935"], "autores": [1]}
TOKEN: dict = {"valor": None}
QUIEBRE: dict = {"usuarios": None, "motivo": None, "segundo": None}
CACHE = Counter()


# =====================================================================
# Comprobaciones del cuerpo
#
# Locust solo marca fallo por codigo de estado o error de red. Con
# catch_response=True tambien se falla por el CONTENIDO, que es donde
# aparecen los errores de integracion: un 200 con XML cuando se pidio
# JSON, un HTML de error con estado 200, un JSON sin la clave esperada.
# =====================================================================
def _estado(respuesta, esperado):
    if respuesta.status_code == 0:
        respuesta.failure("sin respuesta: conexion rechazada, cerrada o "
                          f"agotado el limite de {TIEMPO_LIMITE} s")
        return False
    if respuesta.status_code != esperado:
        respuesta.failure(f"se esperaba {esperado} y llego "
                          f"{respuesta.status_code}: {respuesta.text[:100]}")
        return False
    return True


def valida_json(respuesta, claves=()):
    """200 + JSON analizable + las claves que promete el contrato."""
    CACHE[respuesta.headers.get("X-Cache", "(ausente)")] += 1
    if not _estado(respuesta, 200):
        return None
    if "json" not in respuesta.headers.get("Content-Type", ""):
        respuesta.failure("se pidio JSON y el Content-Type no lo es: "
                          f"{respuesta.headers.get('Content-Type')}")
        return None
    try:
        datos = respuesta.json()
    except ValueError as exc:
        respuesta.failure(f"JSON mal formado: {exc}")
        return None
    faltan = [c for c in claves if c not in datos]
    if faltan:
        respuesta.failure(f"al JSON le faltan las claves {faltan}")
        return None
    respuesta.success()
    return datos


def valida_xml(respuesta, raiz):
    """200 + prologo XML + el elemento raiz esperado al inicio."""
    CACHE[respuesta.headers.get("X-Cache", "(ausente)")] += 1
    if not _estado(respuesta, 200):
        return
    if "xml" not in respuesta.headers.get("Content-Type", ""):
        respuesta.failure("se pidio XML y el Content-Type no lo es: "
                          f"{respuesta.headers.get('Content-Type')}")
        return
    cuerpo = respuesta.text[:400]
    if not cuerpo.lstrip().startswith("<?xml"):
        respuesta.failure(f"no empieza con el prologo XML: {cuerpo[:60]}")
    elif f"<{raiz}" not in cuerpo:
        respuesta.failure(f"no aparece <{raiz}> al inicio del documento")
    else:
        respuesta.success()


def valida_html(respuesta, marcador):
    """
    200 + HTML con un marcador del contenido esperado.

    El marcador importa: el monolito, ante un fallo de datos, puede
    renderizar una pagina de error con estado 200. Sin comprobar el
    cuerpo, la prueba daria por buena una pagina que no sirve.
    """
    if not _estado(respuesta, 200):
        return
    if "html" not in respuesta.headers.get("Content-Type", ""):
        respuesta.failure("se esperaba HTML y llego "
                          f"{respuesta.headers.get('Content-Type')}")
    elif marcador.lower() not in respuesta.text.lower():
        respuesta.failure(f"el HTML no contiene '{marcador}'")
    else:
        respuesta.success()


def valida_401(respuesta):
    """
    La ruta exige Bearer: el 401 es la respuesta CORRECTA.

    No es una prueba de relleno. Ejercita la cadena completa de
    autorizacion (leer la cabecera, verificar el token, consultar la
    lista de revocacion en Redis) sin tocar datos, y bajo carga vigila
    que no se degrade a 500 ni a un 200 accidental.
    """
    if _estado(respuesta, 401):
        respuesta.success()


def valida_salud(respuesta, destino):
    """
    /health de un microservicio.

    200 con status ok|degraded. Un 503 es la respuesta correcta cuando
    PostgreSQL o Redis estan caidos, pero para esta prueba cuenta como
    fallo: el escenario exige que las dependencias esten en pie.
    """
    datos = valida_json(respuesta, claves=("status", "service"))
    if datos is None:
        return
    if datos["status"] not in ("ok", "degraded"):
        respuesta.failure(f"status='{datos['status']}'")
    elif datos["service"] != IDENTIDAD_ESPERADA[destino]:
        respuesta.failure(f"el puerto {PUERTOS[destino]} dice ser "
                          f"'{datos['service']}' y no "
                          f"'{IDENTIDAD_ESPERADA[destino]}'")


# =====================================================================
# Arranque: comprobar los siete destinos y leer datos reales
# =====================================================================
@events.test_start.add_listener
def preparar(environment, **_kwargs):
    """
    Smoke manual automatizado, ANTES de generar carga.

    Hace tres cosas, y ninguna cuenta en las estadisticas (usa
    `requests`, no el cliente de Locust): comprueba que los siete
    destinos responden, verifica que cada puerto es el servicio que dice
    ser, y se trae ISBN e identificadores reales para las tareas de
    detalle. Si un destino no responde, se avisa y la prueba SIGUE: el
    enunciado pide registrar el fallo y continuar con lo disponible.
    """
    print(f"\n[locust] perfil={PERFIL or '(manual)'}  instancia={VM_IP}")
    print(f"[locust] umbral: p95 > {P95_UMBRAL_MS:.0f} ms  o  errores > "
          f"{ERROR_UMBRAL * 100:.0f} %")

    for destino, puerto in PUERTOS.items():
        url = (f"{base(destino)}/library/" if destino == "monolito"
               else f"{base(destino)}/health?format=json")
        try:
            r = requests.get(url, timeout=TIEMPO_LIMITE)
            etiqueta = ""
            if destino != "monolito":
                try:
                    cuerpo = r.json()
                    etiqueta = f" service={cuerpo.get('service')}"
                    if cuerpo.get("service") != IDENTIDAD_ESPERADA[destino]:
                        etiqueta += "  <-- NO COINCIDE con el mapa de puertos"
                except ValueError:
                    etiqueta = " (respuesta no JSON)"
            print(f"[locust]   {destino:<9} :{puerto}  HTTP {r.status_code}{etiqueta}")
        except Exception as exc:                                  # noqa: BLE001
            print(f"[locust]   {destino:<9} :{puerto}  NO RESPONDE -> {exc}")

    # Datos reales para las tareas de detalle.
    try:
        libros = requests.get(f"{base('books')}/books",
                              params={"format": "json", "limit": 200},
                              timeout=TIEMPO_LIMITE).json().get("libros", [])
        isbns = [l["isbn"] for l in libros if l.get("isbn")]
        if isbns:
            CATALOGO["isbn"] = isbns
            print(f"[locust] {len(isbns)} ISBN reales tomados del catalogo")
    except Exception as exc:                                      # noqa: BLE001
        print(f"[locust] AVISO: no se pudo leer el catalogo ({exc}); "
              f"se usa el ISBN de respaldo")

    try:
        autores = requests.get(f"{base('authors')}/authors",
                               params={"format": "json"},
                               timeout=TIEMPO_LIMITE).json().get("autores", [])
        ids = [a["id_autor"] for a in autores if a.get("id_autor")]
        if ids:
            CATALOGO["autores"] = ids
            print(f"[locust] {len(ids)} autores reales tomados del servicio")
    except Exception as exc:                                      # noqa: BLE001
        print(f"[locust] AVISO: no se pudo leer autores ({exc})")

    # Autenticacion OPCIONAL, solo si el entorno trae credenciales. El
    # archivo entregado no guarda ninguna.
    correo = os.getenv("LIBRARY_EMAIL")
    clave = os.getenv("LIBRARY_PASSWORD")
    if correo and clave:
        try:
            r = requests.post(f"{base('login')}/login", params={"format": "json"},
                              json={"email": correo, "password": clave},
                              timeout=TIEMPO_LIMITE)
            cuerpo = r.json() if r.ok else {}
            TOKEN["valor"] = (cuerpo.get("token") or cuerpo.get("access_token")
                              or cuerpo.get("accessToken"))
            print(f"[locust] login: HTTP {r.status_code}, token "
                  f"{'obtenido' if TOKEN['valor'] else 'NO encontrado en la respuesta'}")
        except Exception as exc:                                  # noqa: BLE001
            print(f"[locust] login fallido ({exc}); se sigue sin token")
    else:
        print("[locust] sin credenciales en el entorno: las rutas "
              "autenticadas se prueban exigiendo 401")
    print()


@events.test_stop.add_listener
def cerrar(environment, **_kwargs):
    """Veredicto del umbral con los numeros reales de esta corrida."""
    total = environment.stats.total
    p95 = total.get_response_time_percentile(0.95) or 0
    fallos = total.fail_ratio
    degradado = p95 > P95_UMBRAL_MS or fallos > ERROR_UMBRAL
    print(f"\n[locust] ---- resumen de la corrida ({PERFIL or 'manual'}) ----")
    print(f"[locust] peticiones={total.num_requests}  fallos={total.num_failures} "
          f"({fallos * 100:.2f} %)  RPS medio={total.total_rps:.2f}")
    print(f"[locust] p95 global={p95:.0f} ms   mediana={total.median_response_time:.0f} ms")
    print(f"[locust] UMBRAL: {'INCUMPLIDO (degradado)' if degradado else 'cumplido'}")
    if QUIEBRE["usuarios"]:
        print(f"[locust] punto de quiebre observado: {QUIEBRE['usuarios']} usuarios "
              f"en el segundo {QUIEBRE['segundo']} por {QUIEBRE['motivo']}")
    if CACHE:
        suma = sum(CACHE.values())
        print("[locust] X-Cache -> " + ", ".join(
            f"{k}={v} ({v * 100 // suma} %)" for k, v in CACHE.most_common()))
    print()


# =====================================================================
# EL USUARIO VIRTUAL
#
# UNA sola clase que recorre los SIETE destinos, no siete clases.
# La razon es practica y se descubrio ejecutando: con siete clases y el
# smoke de 1 usuario que fija el enunciado, Locust asigna ese unico
# usuario a UNA clase y los otros seis destinos no reciben ni una
# peticion. Lo mismo pasa con los 5 usuarios del perfil load: dos
# destinos se quedaban fuera. Con una sola clase, cada usuario virtual
# elige entre todas las tareas, de modo que CUALQUIER perfil -- incluso
# el de un usuario -- ejercita los siete destinos.
#
# Las peticiones van con URL ABSOLUTA (http://IP:PUERTO/ruta) porque un
# `host` de Locust solo admite un origen y aqui hay siete. El atributo
# `host` queda puesto por exigencia de Locust, pero no se usa.
#
# El parametro `name=` es lo que agrupa las estadisticas: lleva delante
# el destino entre corchetes, de modo que la columna Name de la interfaz
# y los CSV separan monolito y microservicios, y dentro de los
# microservicios, servicio por servicio.
#
# PESOS. El par comparable pesa lo mismo en los dos lados: el bloque del
# monolito suma 26 y el de books suma 26. Los cuatro servicios sin
# lectura publica pesan 5 cada uno, porque solo tienen /health, la ruta
# protegida y /metrics.
# =====================================================================
def _elige(secuencia):
    import random
    return random.choice(secuencia)


class UsuarioLibreria(HttpUser):
    """Un cliente que usa la libreria por sus dos caras: el sitio del
    monolito y la API de los seis microservicios."""

    host = base("monolito")        # exigido por Locust; se usan URLs absolutas
    wait_time = PAUSA

    # -----------------------------------------------------------------
    # MONOLITO (peso total 26). Solo lecturas publicas: no se envia
    # ningun formulario, de modo que la prueba no crea cuentas.
    #
    # Todas van con allow_redirects=False a proposito: las rutas
    # protegidas del monolito no devuelven 401, devuelven un 302 al
    # formulario de login. Siguiendo la redireccion, Locust registraria
    # un 200 -- el del formulario -- y la prueba daria por buena una
    # pagina que no es la pedida.
    # -----------------------------------------------------------------
    @task(10)
    def mono_catalogo(self):
        """
        GET /library/libros -- PAR COMPARABLE con [books] GET /books.

        La peticion mas pesada del monolito: consulta + plantilla EJS +
        ~16.7 KB de HTML. El marcador `tarjeta-libro` es la clase CSS de
        cada libro de la rejilla: si falta, la pagina llego sin libros.
        """
        with self.client.get(f"{base('monolito')}/library/libros",
                             allow_redirects=False,
                             name="[monolito] GET /library/libros (catalogo HTML)",
                             timeout=TIEMPO_LIMITE, catch_response=True) as r:
            valida_html(r, "tarjeta-libro")

    @task(6)
    def mono_detalle(self):
        """
        GET /library/libros/<ISBN> -- PAR COMPARABLE con [books] GET /books/<ISBN>.

        El monolito desplegado resuelve el detalle por ISBN; un id
        numerico devuelve 302 al catalogo.
        """
        isbn = _elige(CATALOGO["isbn"])
        with self.client.get(f"{base('monolito')}/library/libros/{isbn}",
                             allow_redirects=False,
                             name="[monolito] GET /library/libros/<ISBN> (detalle HTML)",
                             timeout=TIEMPO_LIMITE, catch_response=True) as r:
            valida_html(r, isbn)

    @task(4)
    def mono_busqueda(self):
        """
        GET /library/libros?q= -- PAR COMPARABLE con [books] GET /books?<filtros>.

        Busca con ILIKE en PostgreSQL. Es el lado monolito de la
        consulta que no puede venir de cache.

        Los terminos estan elegidos a mano porque este `q` busca por
        TITULO o ISBN, no por autor ni por genero: se comprobo con curl
        que "orwell", "novela" o "historia" devuelven CERO resultados y
        una pagina sin tarjetas, lo que hacia fallar la asercion sin que
        el servicio tuviera nada malo. Los de abajo devuelven filas, de
        modo que la asercion sigue siendo exigente -- comprueba que de
        verdad llegaron libros -- en lugar de aflojarse para no fallar.
        """
        with self.client.get(f"{base('monolito')}/library/libros",
                             params={"q": _elige(["1984", "el", "la",
                                                  "rayuela", "cien"])},
                             allow_redirects=False,
                             name="[monolito] GET /library/libros?q= (busqueda HTML)",
                             timeout=TIEMPO_LIMITE, catch_response=True) as r:
            valida_html(r, "tarjeta-libro")

    @task(4)
    def mono_portada(self):
        """
        GET /library/ -- la portada.

        Hace de sustituto del /health que el monolito NO tiene: la
        peticion mas barata que sigue tocando la base. Con la barra
        final, porque /library sin barra responde 301.
        """
        with self.client.get(f"{base('monolito')}/library/",
                             allow_redirects=False,
                             name="[monolito] GET /library/ (portada)",
                             timeout=TIEMPO_LIMITE, catch_response=True) as r:
            valida_html(r, "<html")

    @task(2)
    def mono_formulario(self):
        """
        GET /library/login -- pagina publica. NO se envian credenciales.

        Linea base del monolito: renderiza una plantilla SIN consultar la
        base, de modo que separa el coste de Express+EJS del de PostgreSQL.
        """
        with self.client.get(f"{base('monolito')}/library/login",
                             allow_redirects=False,
                             name="[monolito] GET /library/login (formulario)",
                             timeout=TIEMPO_LIMITE, catch_response=True) as r:
            valida_html(r, "<form")

    # -----------------------------------------------------------------
    # BOOKS :5001 (peso total 26) -- el otro lado del par comparable
    # -----------------------------------------------------------------
    @task(10)
    def books_catalogo_json(self):
        """GET /books?format=json -- PAR COMPARABLE con el catalogo del monolito."""
        with self.client.get(f"{base('books')}/books", params={"format": "json"},
                             name="[books] GET /books?format=json (catalogo)",
                             timeout=TIEMPO_LIMITE, catch_response=True) as r:
            datos = valida_json(r, claves=("count", "total", "libros"))
            if datos is not None and len(datos["libros"]) != datos["count"]:
                r.failure(f"count={datos['count']} pero llegaron "
                          f"{len(datos['libros'])} libros")

    @task(6)
    def books_detalle(self):
        """GET /books/<ISBN>?format=json -- PAR COMPARABLE con el detalle del monolito."""
        isbn = _elige(CATALOGO["isbn"])
        with self.client.get(f"{base('books')}/books/{isbn}",
                             params={"format": "json"},
                             name="[books] GET /books/<ISBN>?format=json (detalle)",
                             timeout=TIEMPO_LIMITE, catch_response=True) as r:
            if r.status_code == 404:
                r.success()      # el libro se dio de baja durante la corrida
                return
            datos = valida_json(r, claves=("isbn", "title"))
            if datos is not None and datos["isbn"] != isbn:
                r.failure(f"se pidio {isbn} y contesto {datos['isbn']}")

    @task(4)
    def books_busqueda(self):
        """
        GET /books?<filtros> -- PAR COMPARABLE con la busqueda del monolito.

        Filtros en espanol (asi los expone la version desplegada). Cada
        combinacion es una clave de cache distinta, de modo que casi
        siempre es MISS y va a PostgreSQL: comparada con el catalogo
        completo (casi siempre HIT) mide lo que aporta Redis.
        """
        filtros = dict(_elige([
            {"titulo": "el"}, {"autor": "Orwell"}, {"genero": "Novela"},
            {"formato": "Tapa dura"}, {"precio_min": "200"},
            {"anio_min": "1900", "anio_max": "1980"}, {"stock_min": "5"},
        ]))
        filtros["format"] = "json"
        with self.client.get(f"{base('books')}/books", params=filtros,
                             name="[books] GET /books?<filtros> (busqueda)",
                             timeout=TIEMPO_LIMITE, catch_response=True) as r:
            datos = valida_json(r, claves=("count", "total", "libros"))
            if datos is not None and datos["count"] > datos["total"]:
                r.failure(f"count={datos['count']} > total={datos['total']}")

    @task(4)
    def books_catalogo_xml(self):
        """GET /books?format=xml -- el mismo recurso en la otra representacion."""
        with self.client.get(f"{base('books')}/books", params={"format": "xml"},
                             name="[books] GET /books?format=xml (catalogo)",
                             timeout=TIEMPO_LIMITE, catch_response=True) as r:
            valida_xml(r, "library")

    @task(2)
    def books_salud(self):
        with self.client.get(f"{base('books')}/health", params={"format": "json"},
                             name="[books] GET /health",
                             timeout=TIEMPO_LIMITE, catch_response=True) as r:
            valida_salud(r, "books")

    # -----------------------------------------------------------------
    # AUTHORS :5003 (peso total 14) -- la otra lectura publica real
    # -----------------------------------------------------------------
    @task(6)
    def authors_listado(self):
        """GET /authors?format=json -- coleccion bajo la clave 'autores'."""
        with self.client.get(f"{base('authors')}/authors",
                             params={"format": "json"},
                             name="[authors] GET /authors?format=json (listado)",
                             timeout=TIEMPO_LIMITE, catch_response=True) as r:
            valida_json(r, claves=("autores",))

    @task(4)
    def authors_detalle(self):
        """GET /authors/<id>?format=json -- el autor con sus libros."""
        ident = _elige(CATALOGO["autores"])
        with self.client.get(f"{base('authors')}/authors/{ident}",
                             params={"format": "json"},
                             name="[authors] GET /authors/<id>?format=json (detalle)",
                             timeout=TIEMPO_LIMITE, catch_response=True) as r:
            if r.status_code == 404:
                r.success()
                return
            datos = valida_json(r, claves=("id_autor",))
            if datos is not None and datos["id_autor"] != ident:
                r.failure(f"se pidio {ident} y contesto {datos['id_autor']}")

    @task(2)
    def authors_listado_xml(self):
        """GET /authors?format=xml -- la misma coleccion en XML."""
        with self.client.get(f"{base('authors')}/authors",
                             params={"format": "xml"},
                             name="[authors] GET /authors?format=xml (listado)",
                             timeout=TIEMPO_LIMITE, catch_response=True) as r:
            valida_xml(r, "autores")

    @task(2)
    def authors_salud(self):
        with self.client.get(f"{base('authors')}/health",
                             params={"format": "json"},
                             name="[authors] GET /health",
                             timeout=TIEMPO_LIMITE, catch_response=True) as r:
            valida_salud(r, "authors")

    # -----------------------------------------------------------------
    # LOS CUATRO SERVICIOS SIN LECTURA PUBLICA (peso 5 cada uno)
    # login :5000 · users :5002 · pedidos :5004 · pagos :5005
    #
    # Que se mide: /health ejerce PostgreSQL y Redis, y la ruta
    # protegida ejerce la cadena de autorizacion completa -- leer la
    # cabecera, verificar la firma del JWT y consultar la lista de
    # revocacion en Redis -- devolviendo 401 sin tocar datos. Es el
    # camino caliente de estos servicios sin crear cuentas, pedidos ni
    # cobros, que es lo que pide el enunciado al preferir lecturas que
    # no cambien datos.
    #
    # Que NO se mide: sus operaciones de negocio. Queda dicho en
    # RESULTADOS.md como limitacion; no se disimula.
    # -----------------------------------------------------------------
    def _salud(self, destino):
        with self.client.get(f"{base(destino)}/health", params={"format": "json"},
                             name=f"[{destino}] GET /health",
                             timeout=TIEMPO_LIMITE, catch_response=True) as r:
            valida_salud(r, destino)

    def _protegida(self, destino, ruta):
        cabeceras = ({"Authorization": f"Bearer {TOKEN['valor']}"}
                     if TOKEN["valor"] else {})
        etiqueta = "autenticado" if TOKEN["valor"] else "401 esperado"
        with self.client.get(f"{base(destino)}{ruta}", params={"format": "json"},
                             headers=cabeceras,
                             name=f"[{destino}] GET {ruta} [{etiqueta}]",
                             timeout=TIEMPO_LIMITE, catch_response=True) as r:
            if not TOKEN["valor"]:
                valida_401(r)
            elif r.status_code in (401, 403):
                # Token caducado o rol sin permiso: es informacion sobre
                # las credenciales, no un fallo del servicio bajo carga.
                r.success()
            else:
                valida_json(r)

    def _metricas(self, destino):
        """GET /metrics -- en la version desplegada exige token: 401 esperado."""
        with self.client.get(f"{base(destino)}/metrics",
                             name=f"[{destino}] GET /metrics [401 esperado]",
                             timeout=TIEMPO_LIMITE, catch_response=True) as r:
            valida_401(r)

    @task(2)
    def login_salud(self):
        self._salud("login")

    @task(2)
    def login_session(self):
        self._protegida("login", "/session")

    @task(1)
    def login_metricas(self):
        self._metricas("login")

    @task(2)
    def users_salud(self):
        self._salud("users")

    @task(2)
    def users_listado(self):
        self._protegida("users", "/users")

    @task(1)
    def users_metricas(self):
        self._metricas("users")

    @task(2)
    def pedidos_salud(self):
        self._salud("pedidos")

    @task(2)
    def pedidos_listado(self):
        self._protegida("pedidos", "/orders")

    @task(1)
    def pedidos_metricas(self):
        self._metricas("pedidos")

    @task(2)
    def pagos_salud(self):
        self._salud("pagos")

    @task(2)
    def pagos_listado(self):
        self._protegida("pagos", "/payments")

    @task(1)
    def pagos_metricas(self):
        self._metricas("pagos")


# =====================================================================
# Perfiles de carga
#
# Una LoadTestShape describe la forma de la carga en el tiempo: Locust
# llama a tick() cada segundo y la clase devuelve (usuarios, rampa) o
# None para terminar. Con una forma activa, -u/-r/-t se ignoran.
#
# La clase se define SOLO si PERFIL trae valor, para que sin perfil la
# interfaz grafica siga mandando.
# =====================================================================
# (segundo en que termina la etapa, usuarios, rampa)
ETAPAS = {
    # 1 usuario, 30 s. Carga minima: comprobar que las rutas responden.
    "smoke": [(30, 1, 1)],
    # 5 usuarios, rampa 1/s, 2 min. La carga "esperada".
    "load": [(120, 5, 1)],
    # 2 -> 20 por etapas de 25 s. Siete escalones para ver DONDE se
    # dobla la curva, no solo que se doble.
    "stress": [(25, 2, 1), (50, 5, 2), (75, 8, 2), (100, 11, 2),
               (125, 14, 2), (150, 17, 2), (180, 20, 2)],
    # 2 -> 15 de golpe (rampa 10/s), se mantiene 45 s, vuelve a 2 y se
    # observa la recuperacion durante 45 s mas.
    "spike": [(20, 2, 1), (30, 15, 10), (75, 15, 10), (85, 2, 10), (120, 2, 1)],
    # 3 usuarios, 4 min. Miniatura didactica de un soak.
    "soak": [(240, 3, 1)],
}

QUIEBRE_MAX_USUARIOS = 20
QUIEBRE_PASO_SEGUNDOS = 12      # +1 usuario cada 12 s -> 20 a los 228 s
QUIEBRE_LIMITE_SEGUNDOS = 240
QUIEBRE_ARRANQUE = 20           # no se juzga el umbral antes de este segundo
QUIEBRE_MIN_PETICIONES = 20     # minimo de peticiones para que el veredicto valga


if PERFIL:
    class PerfilDeCarga(LoadTestShape):
        """
        La forma de la carga del perfil elegido en PERFIL.

        Para los cinco perfiles de etapas fijas, se recorre ETAPAS. Para
        el punto de quiebre la forma es adaptativa: sube un usuario cada
        12 s y DEJA DE SUBIR en cuanto la corrida incumple el umbral
        (p95 > 1 s o errores > 5 %), manteniendo esa concurrencia hasta
        el limite de 4 minutos. Asi el numero de usuarios del momento del
        incumplimiento queda registrado, que es lo que se busca estimar.

        Aviso que conviene no olvidar al interpretarlo: esto es el punto
        de quiebre OBSERVADO en una prueba de 4 minutos, con esta pausa
        entre tareas, desde este equipo y por esta red. No es la
        capacidad maxima del sistema.
        """

        def tick(self):
            transcurrido = self.get_run_time()

            if PERFIL != "quiebre":
                for fin, usuarios, rampa in ETAPAS[PERFIL]:
                    if transcurrido < fin:
                        return (usuarios, rampa)
                return None            # termino el perfil

            # --- punto de quiebre ---
            if transcurrido > QUIEBRE_LIMITE_SEGUNDOS:
                return None

            objetivo = min(1 + int(transcurrido // QUIEBRE_PASO_SEGUNDOS),
                           QUIEBRE_MAX_USUARIOS)

            if QUIEBRE["usuarios"] is None and transcurrido > QUIEBRE_ARRANQUE:
                # TODO el calculo va dentro de un try: si consultar las
                # estadisticas lanza, Locust NO lo reporta -- mata en
                # silencio el greenlet de la forma de carga y la prueba
                # se queda corriendo para siempre con la ultima
                # concurrencia. Paso de verdad en la corrida del
                # 2026-10-30: el perfil de 4 minutos siguio 13 y hubo
                # que matarlo a mano. Una excepcion aqui no puede tumbar
                # la forma.
                try:
                    total = self.runner.environment.stats.total
                    p95 = total.get_current_response_time_percentile(0.95) or 0
                    fallos = total.fail_ratio
                    exitosas = total.num_requests - total.num_failures

                    # Si NO hay ni una peticion con exito, el destino no
                    # esta respondiendo: eso no es un punto de quiebre
                    # por saturacion, es que el servicio esta caido.
                    # Declararlo "quiebre con 2 usuarios" seria falso.
                    if total.num_requests >= QUIEBRE_MIN_PETICIONES and exitosas == 0:
                        QUIEBRE.update(usuarios=None, segundo=int(transcurrido),
                                       motivo="DESTINO CAIDO: ninguna peticion "
                                              "obtuvo respuesta; no es saturacion")
                        print(f"\n[locust] {total.num_requests} peticiones y NINGUNA "
                              f"respuesta: el destino no esta sirviendo. Se aborta "
                              f"el perfil: medir el quiebre no tiene sentido.\n",
                              flush=True)
                        return None

                    motivo = None
                    if p95 > P95_UMBRAL_MS:
                        motivo = f"p95={p95:.0f} ms > {P95_UMBRAL_MS:.0f} ms"
                    elif fallos > ERROR_UMBRAL and exitosas >= QUIEBRE_MIN_PETICIONES:
                        motivo = f"errores={fallos * 100:.1f} % > {ERROR_UMBRAL * 100:.0f} %"
                    if motivo:
                        QUIEBRE.update(usuarios=self.runner.user_count,
                                       motivo=motivo,
                                       segundo=int(transcurrido))
                        print(f"\n[locust] UMBRAL INCUMPLIDO con "
                              f"{self.runner.user_count} usuarios en el segundo "
                              f"{int(transcurrido)}: {motivo}. Se deja de subir.\n",
                              flush=True)
                except Exception as exc:                          # noqa: BLE001
                    print(f"[locust] AVISO: no se pudo evaluar el umbral "
                          f"({type(exc).__name__}: {exc}); se sigue subiendo "
                          f"la carga.", flush=True)

            if QUIEBRE["usuarios"] is not None:
                # Se mantiene la concurrencia del incumplimiento para ver
                # si se sostiene o si fue un transitorio.
                return (QUIEBRE["usuarios"], 1)
            return (objetivo, 1)
