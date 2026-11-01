"""
locust_tests/locustfile.py
=========================================================================
PRUEBAS DE RENDIMIENTO CON LOCUST
Monolito web (Node/Express) contra la arquitectura de SEIS microservicios
Flask de la Libreria en Linea, sobre la instancia de GCP.

-------------------------------------------------------------------------
0. AVISO: ESTE ARCHIVO MIDE UN DESPLIEGUE DISTINTO AL DEL 2026-10-30
-------------------------------------------------------------------------
La primera tanda (2026-10-30) se corrio contra unos procesos lanzados a
mano que NO eran el codigo del repositorio. La instancia se reinicio el
2026-11-01 y, al habilitar las unidades de systemd, lo que arranco fue el
despliegue de `/opt/library/*`, que SI es el del repositorio. El contrato
cambio en casi todo:

    /health            antes traia "service"; ahora NO lo trae
    /books?format=json antes envolvia en "libros"; ahora en "books"
    filtros del catalogo  antes en espanol; ahora en INGLES
    /authors           antes "autores"/"id_autor"; ahora "authors"/"id"
    pedidos y pagos    antes /orders y /payments; ahora /pedidos y /pagos
    /envios/<numero>   antes 404; ahora existe
    /docs/ y /metrics  antes 404 y 401; ahora 200 y 200 publico
    /session           antes 401; ahora 200 {"authenticated": false}

Por eso este archivo NO es el que produjo las evidencias de octubre: las
rutas y las aserciones se rehicieron contra el despliegue actual. La
version de octubre se conserva en el historial de git, y sus resultados
en RESULTADOS.md bajo su propio encabezado.

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
    [pedidos]   http://<IP>:5004      pedidos
    [pagos]     http://<IP>:5005      pagos

Toda peticion lleva un nombre con el prefijo del destino entre corchetes
(`name="[books] GET /books?format=json"`), que es lo que aparece en la
columna Name de la interfaz y en los CSV. Asi se puede comparar la misma
operacion -- "dame el catalogo" -- en el monolito y en el microservicio.

-------------------------------------------------------------------------
2. LA COMPARACION: QUE SE CONSIDERA "COMPARABLE"
-------------------------------------------------------------------------
El par comparable del ejercicio es el CATALOGO:

    [monolito] GET /library/catalog         -> HTML renderizado con EJS
    [books]    GET /books?format=json       -> JSON
    [books]    GET /books?format=xml        -> XML

y, como segundo par, el DETALLE de un libro:

    [monolito] GET /library/catalog/<id>    -> HTML
    [books]    GET /books/<id>?format=json  -> JSON

OJO -- UNA DIFERENCIA QUE HAY QUE TENER PRESENTE. En esta version del
monolito el catalogo EXIGE SESION (`requireLogin`): sin cookie responde
302 al formulario de login. Hay dos modos, y el `.log` de cada corrida
dice en cual se ejecuto:

  * SIN credenciales (por omision): las tareas del catalogo comprueban
    el 302. Eso mide enrutado + comprobacion de sesion, NO la consulta
    ni el renderizado, de modo que el par comparable NO es valido y la
    unica lectura real del monolito es la portada.
  * CON credenciales en el entorno (MONO_EMAIL y MONO_PASSWORD): cada
    usuario virtual inicia sesion una vez en `on_start` y a partir de
    ahi el catalogo responde 200 con HTML completo. Ahi si hay par
    comparable.

Las credenciales NUNCA se escriben en este archivo: se leen del entorno
y la cookie vive solo en memoria.

-------------------------------------------------------------------------
3. INVENTARIO DE RUTAS -- VERIFICADO EN VIVO, NO SUPUESTO
-------------------------------------------------------------------------
Comprobado con curl contra la instancia el 2026-11-01, una por una,
mirando codigo de estado Y cuerpo.

    PUBLICO (sin token) -- es con lo que se genera la carga:
      [monolito] GET /library/                   200  portada HTML
      [monolito] GET /library/auth/login         200  formulario
      [monolito] GET /library/auth/register      200  formulario
      [monolito] GET /library/catalog            302 sin sesion / 200 con ella
      [monolito] GET /library/catalog/<id>       302 sin sesion / 200 con ella
      [books]    GET /books                      200  XML por omision
      [books]    GET /books?format=json|xml      200  representacion explicita
      [books]    GET /books/<id>                 200  detalle por id
      [books]    GET /books/isbn/<isbn>          200  detalle por ISBN
      [books]    GET /books/search?q=            200  busqueda
      [books]    GET /books?<filtros>            200  title/author/genre/
                                                      year_min/year_max/
                                                      price_min/price_max
      [books]    GET /formats /categories /genres /authors   200
      [authors]  GET /authors                    200  clave JSON "authors"
      [authors]  GET /authors/<id>               200  clave JSON "id"
      [authors]  GET /authors/<id>/books         200
      [pedidos]  GET /envios/<numero>            404  publico, pero la base
                                                      no tiene ningun pedido
      LOS SEIS   GET /                           200  documento de servicio
      LOS SEIS   GET /health?format=json         200  {"status","database",...}
      LOS SEIS   GET /metrics                    200  XML, PUBLICO
      [login]    GET /session?format=json        200  {"authenticated": false}
      [login]    GET /validate-email?email=      200

    EXIGE Authorization: Bearer (401 sin token):
      [users]    GET /users   GET /roles         401
      [pedidos]  GET /pedidos                    401
      [pagos]    GET /pagos   GET /metodos       401

    AVISO SOBRE LOS PUERTOS. El enunciado lista "pagos 5002, pedidos
    5003, users 5004, autores 5005". La instancia responde al contrario.
    No es una suposicion: `GET /?format=json` de cada puerto dice que
    servicio es, y el arranque de la prueba lo vuelve a comprobar.
        5002 -> library-users-service    5003 -> library-authors-service
        5004 -> library-pedidos-service  5005 -> library-pagos-service

    POR QUE EL ARRANQUE YA NO COMPRUEBA LA IDENTIDAD EN /health: porque
    esta version no la publica ahi. Se comprueba en `GET /?format=json`,
    que es donde esta. Dejar la comprobacion donde ya no hay dato habria
    hecho fallar los siete destinos por un motivo falso.

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

    # los seis, en orden
    ./correr_perfiles.sh

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

  * Las rutas con Bearer (`/users`, `/pedidos`, `/pagos`, `/metodos`)
    se prueban por omision SIN token, exigiendo el 401: eso verifica la
    cadena completa de autorizacion -- leer la cabecera, verificar la
    firma y consultar la revocacion en Redis -- sin tocar datos.
  * LIBRARY_EMAIL / LIBRARY_PASSWORD: si estan en el entorno, el
    arranque pide un token a `POST /login` y las rutas protegidas pasan
    a probarse autenticadas. El token vive solo en memoria.
  * MONO_EMAIL / MONO_PASSWORD: si estan en el entorno, cada usuario
    virtual inicia sesion en el monolito y el catalogo se mide de
    verdad (200 + HTML) en lugar de comprobar el 302.
"""
from __future__ import annotations

import os
import random
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

# Identidad que cada microservicio declara en `GET /?format=json`. Se
# comprueba al arrancar: si un puerto contesta con otro nombre, el mapa
# de puertos cambio y las estadisticas estarian mal etiquetadas.
IDENTIDAD_ESPERADA = {
    "login": "library-login-service",
    "books": "library-books-service",
    "users": "library-users-service",
    "authors": "library-authors-service",
    "pedidos": "library-pedidos-service",
    "pagos": "library-pagos-service",
}

# El monolito vive completo bajo este prefijo (config.basePath).
BASE_MONO = "/library"


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

# Tiempo limite del SONDEO de arranque, que es otra cosa. test_start
# corre ANTES de que Locust cree un solo usuario y bloquea el arranque
# mientras dura. Con los 15 s de TIEMPO_LIMITE, cuatro destinos caidos
# suman 60 s de espera: mas que el perfil smoke entero (30 s), de modo
# que la prueba terminaba sin haber lanzado NI UNA peticion. Paso de
# verdad el 2026-11-01. El sondeo solo tiene que distinguir "contesta"
# de "no contesta", y para eso 3 s sobran.
TIEMPO_SONDEO = 3

PERFIL = os.getenv("PERFIL", "").strip().lower()

# Datos reales del catalogo. Se rellenan en test_start leyendo los
# propios servicios, para no escribir identificadores a mano.
# Destinos que CONTESTARON al arrancar. El enunciado pide que, si un
# componente no inicia, se registre el error y se siga con los demas; si
# se dejara dentro un destino caido, sus fallos se sumarian al total y
# TODOS los perfiles saldrian "degradados" por un motivo que no es la
# carga. Se excluyen sus tareas y queda dicho en el .log y en el informe.
DISPONIBLES: set = set()

CATALOGO: dict = {"isbn": [], "libros": [], "autores": []}
TOKEN: dict = {"valor": None}
MONO: dict = {"sesion": False}
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


def valida_404(respuesta):
    """
    El recurso no existe y el servicio lo dice bien.

    Se usa en `/envios/<numero>`: es la UNICA ruta publica de pedidos,
    pero la base no tiene ningun pedido, de modo que lo que se mide es
    la busqueda en PostgreSQL que termina en 404. Queda dicho en
    RESULTADOS.md; no se presenta como una lectura de negocio.
    """
    if _estado(respuesta, 404):
        respuesta.success()


def valida_salud(respuesta):
    """
    /health de un microservicio.

    200 con status ok|degraded. Un 503 es la respuesta correcta cuando
    PostgreSQL o Redis estan caidos, pero para esta prueba cuenta como
    fallo: el escenario exige que las dependencias esten en pie.

    Esta version NO publica "service" en /health -- la identidad se
    comprueba al arrancar contra `GET /?format=json`.
    """
    datos = valida_json(respuesta, claves=("status", "database"))
    if datos is None:
        return
    if datos["status"] not in ("ok", "degraded"):
        respuesta.failure(f"status='{datos['status']}'")


def valida_302(respuesta, destino_esperado):
    """
    La ruta del monolito exige sesion y redirige al formulario.

    Con allow_redirects=False el 302 es la respuesta correcta. Si se
    siguiera la redireccion, Locust registraria el 200 del formulario y
    la prueba daria por buena una pagina que no es la pedida.
    """
    if not _estado(respuesta, 302):
        return
    destino = respuesta.headers.get("Location", "")
    if destino_esperado not in destino:
        respuesta.failure(f"redirige a '{destino}' y no a "
                          f"'{destino_esperado}'")
    else:
        respuesta.success()


# =====================================================================
# Arranque: comprobar los siete destinos y leer datos reales
# =====================================================================
@events.test_start.add_listener
def preparar(environment, **_kwargs):
    """
    Smoke manual automatizado, ANTES de generar carga.

    Comprueba que los siete destinos responden, verifica que cada puerto
    es el servicio que dice ser y se trae identificadores reales para
    las tareas de detalle. Nada de esto cuenta en las estadisticas (usa
    `requests`, no el cliente de Locust). Si un destino no responde, se
    avisa y la prueba SIGUE: el enunciado pide registrar el fallo y
    continuar con lo disponible.
    """
    print(f"\n[locust] perfil={PERFIL or '(manual)'}  instancia={VM_IP}")
    print(f"[locust] umbral: p95 > {P95_UMBRAL_MS:.0f} ms  o  errores > "
          f"{ERROR_UMBRAL * 100:.0f} %")

    for destino, puerto in PUERTOS.items():
        url = (f"{base(destino)}{BASE_MONO}/" if destino == "monolito"
               else f"{base(destino)}/?format=json")
        try:
            r = requests.get(url, timeout=TIEMPO_SONDEO)
            etiqueta = ""
            if destino != "monolito":
                try:
                    declarado = r.json().get("service")
                    etiqueta = f" service={declarado}"
                    if declarado != IDENTIDAD_ESPERADA[destino]:
                        etiqueta += "  <-- NO COINCIDE con el mapa de puertos"
                except ValueError:
                    etiqueta = " (respuesta no JSON)"
            if r.status_code < 500:
                DISPONIBLES.add(destino)
            print(f"[locust]   {destino:<9} :{puerto}  HTTP {r.status_code}{etiqueta}")
        except Exception as exc:                                  # noqa: BLE001
            print(f"[locust]   {destino:<9} :{puerto}  NO RESPONDE -> "
                  f"{type(exc).__name__}")

    caidos = [d for d in PUERTOS if d not in DISPONIBLES]
    if caidos:
        UsuarioLibreria.tasks = [t for t in UsuarioLibreria.tasks
                                 if _destino_de(t) not in caidos]
        print(f"[locust] NO DISPONIBLES: {', '.join(caidos)}. Se excluyen sus "
              f"tareas del reparto y la corrida sigue con "
              f"{len(DISPONIBLES)} de {len(PUERTOS)} destinos.")
        print("[locust] AVISO: esta corrida NO mide los destinos excluidos; "
              "hay que decirlo al comparar con otras.")

    # Identificadores reales para las tareas de detalle.
    try:
        libros = requests.get(f"{base('books')}/books",
                              params={"format": "json", "limit": 200},
                              timeout=TIEMPO_SONDEO).json().get("books", [])
        CATALOGO["libros"] = [l["id"] for l in libros if l.get("id")]
        CATALOGO["isbn"] = [l["isbn"] for l in libros if l.get("isbn")]
        print(f"[locust] {len(CATALOGO['libros'])} libros reales tomados "
              f"del catalogo")
    except Exception as exc:                                      # noqa: BLE001
        print(f"[locust] AVISO: no se pudo leer el catalogo ({exc})")

    try:
        autores = requests.get(f"{base('authors')}/authors",
                               params={"format": "json", "limit": 200},
                               timeout=TIEMPO_SONDEO).json().get("authors", [])
        CATALOGO["autores"] = [a["id"] for a in autores if a.get("id")]
        print(f"[locust] {len(CATALOGO['autores'])} autores reales tomados "
              f"del servicio")
    except Exception as exc:                                      # noqa: BLE001
        print(f"[locust] AVISO: no se pudo leer autores ({exc})")

    # Autenticacion OPCIONAL de la API, solo si el entorno trae
    # credenciales. El archivo entregado no guarda ninguna.
    correo = os.getenv("LIBRARY_EMAIL")
    clave = os.getenv("LIBRARY_PASSWORD")
    if correo and clave:
        try:
            r = requests.post(f"{base('login')}/login", params={"format": "json"},
                              json={"email": correo, "password": clave},
                              timeout=TIEMPO_SONDEO)
            cuerpo = r.json() if r.ok else {}
            TOKEN["valor"] = (cuerpo.get("token") or cuerpo.get("access_token")
                              or cuerpo.get("accessToken"))
            print(f"[locust] login API: HTTP {r.status_code}, token "
                  f"{'obtenido' if TOKEN['valor'] else 'NO encontrado en la respuesta'}")
        except Exception as exc:                                  # noqa: BLE001
            print(f"[locust] login API fallido ({exc}); se sigue sin token")
    else:
        print("[locust] sin credenciales de API en el entorno: las rutas "
              "con Bearer se prueban exigiendo 401")

    MONO["sesion"] = bool(os.getenv("MONO_EMAIL") and os.getenv("MONO_PASSWORD")
                          and "monolito" in DISPONIBLES)
    if MONO["sesion"]:
        print("[locust] monolito: hay credenciales, el catalogo se medira "
              "CON sesion (200 + HTML completo)")
    else:
        print("[locust] monolito: sin credenciales, el catalogo se medira "
              "como 302 al formulario -- el par comparable NO es valido")
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
    elif QUIEBRE["motivo"]:
        print(f"[locust] punto de quiebre NO medido: {QUIEBRE['motivo']}")
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
# lectura publica de datos pesan 5 cada uno.
# =====================================================================
def _elige(secuencia, por_omision=None):
    return random.choice(secuencia) if secuencia else por_omision


# Cada tarea se llama <prefijo>_<lo que hace>, y el prefijo dice a que
# destino va. Es lo que permite retirar del reparto, en bloque, las
# tareas de un destino que no respondio al arrancar.
PREFIJO_DESTINO = {
    "mono": "monolito", "books": "books", "authors": "authors",
    "login": "login", "users": "users", "pedidos": "pedidos",
    "pagos": "pagos",
}


def _destino_de(tarea):
    return PREFIJO_DESTINO.get(getattr(tarea, "__name__", "").split("_")[0])


class UsuarioLibreria(HttpUser):
    """Un cliente que usa la libreria por sus dos caras: el sitio del
    monolito y la API de los seis microservicios."""

    host = base("monolito")        # exigido por Locust; se usan URLs absolutas
    wait_time = PAUSA

    def on_start(self):
        """
        Inicia sesion en el monolito si hay credenciales en el entorno.

        Se hace UNA vez por usuario virtual y con el cliente de Locust,
        de modo que la cookie de sesion queda en su propio `CookieJar`
        -- cada usuario virtual es una sesion distinta, como lo seria
        una persona distinta. La peticion NO se mide: lleva su propio
        nombre y pesa una sola vez en toda la corrida.
        """
        if not MONO["sesion"]:
            return
        with self.client.post(
                f"{base('monolito')}{BASE_MONO}/auth/login",
                data={"email": os.getenv("MONO_EMAIL"),
                      "password": os.getenv("MONO_PASSWORD")},
                allow_redirects=False,
                name="[monolito] POST /library/auth/login (una vez por usuario)",
                timeout=TIEMPO_LIMITE, catch_response=True) as r:
            # El inicio correcto responde 302 al catalogo; un 200 es el
            # formulario devuelto con el error, es decir, credenciales
            # malas. Conviene que se vea y no pase por bueno.
            if r.status_code == 302:
                r.success()
            else:
                r.failure(f"no inicio sesion (HTTP {r.status_code}): "
                          f"revise MONO_EMAIL y MONO_PASSWORD")

    # -----------------------------------------------------------------
    # MONOLITO :3000 (peso total 26) -- un lado del par comparable
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
        GET /library/catalog -- PAR COMPARABLE con [books] GET /books.

        La peticion mas pesada del monolito: seis consultas en paralelo
        + plantilla EJS + HTML. El marcador `book-card` es la clase CSS
        de cada libro de la rejilla: si falta, la pagina llego sin
        libros.
        """
        nombre = ("[monolito] GET /library/catalog (catalogo HTML)"
                  if MONO["sesion"]
                  else "[monolito] GET /library/catalog [302 esperado]")
        with self.client.get(f"{base('monolito')}{BASE_MONO}/catalog",
                             allow_redirects=False, name=nombre,
                             timeout=TIEMPO_LIMITE, catch_response=True) as r:
            if MONO["sesion"]:
                valida_html(r, "book-card")
            else:
                valida_302(r, "/auth/login")

    @task(6)
    def mono_detalle(self):
        """GET /library/catalog/<id> -- PAR COMPARABLE con [books] GET /books/<id>."""
        ident = _elige(CATALOGO["libros"], 1)
        nombre = ("[monolito] GET /library/catalog/<id> (detalle HTML)"
                  if MONO["sesion"]
                  else "[monolito] GET /library/catalog/<id> [302 esperado]")
        with self.client.get(f"{base('monolito')}{BASE_MONO}/catalog/{ident}",
                             allow_redirects=False, name=nombre,
                             timeout=TIEMPO_LIMITE, catch_response=True) as r:
            if not MONO["sesion"]:
                valida_302(r, "/auth/login")
            elif r.status_code in (302, 404):
                r.success()          # el libro se dio de baja durante la corrida
            else:
                valida_html(r, "<html")

    @task(4)
    def mono_busqueda(self):
        """
        GET /library/catalog?q= -- PAR COMPARABLE con [books] GET /books?<filtros>.

        Busca con ILIKE en PostgreSQL. Es el lado monolito de la
        consulta que no puede venir de cache.
        """
        nombre = ("[monolito] GET /library/catalog?q= (busqueda HTML)"
                  if MONO["sesion"]
                  else "[monolito] GET /library/catalog?q= [302 esperado]")
        with self.client.get(f"{base('monolito')}{BASE_MONO}/catalog",
                             params={"q": _elige(["base", "software", "el",
                                                  "la", "sistemas"])},
                             allow_redirects=False, name=nombre,
                             timeout=TIEMPO_LIMITE, catch_response=True) as r:
            if MONO["sesion"]:
                valida_html(r, "<html")
            else:
                valida_302(r, "/auth/login")

    @task(4)
    def mono_portada(self):
        """
        GET /library/ -- la portada.

        Hace de sustituto del /health que el monolito NO tiene: consulta
        la vista de totales del catalogo y renderiza. Con la barra
        final, porque /library sin barra responde 301.

        Con sesion iniciada la portada REDIRIGE al catalogo (lo hace el
        propio controlador), de modo que ahi el 302 es lo correcto.
        """
        with self.client.get(f"{base('monolito')}{BASE_MONO}/",
                             allow_redirects=False,
                             name="[monolito] GET /library/ (portada)",
                             timeout=TIEMPO_LIMITE, catch_response=True) as r:
            if MONO["sesion"] and r.status_code == 302:
                r.success()
            else:
                valida_html(r, "<html")

    @task(2)
    def mono_formulario(self):
        """
        GET /library/auth/register -- pagina publica. NO se envia nada.

        Linea base del monolito: renderiza una plantilla SIN consultar
        la base, de modo que separa el coste de Express+EJS del de
        PostgreSQL. Se usa el registro y no el login porque, con sesion
        iniciada, `requireGuest` redirige el de login.
        """
        with self.client.get(f"{base('monolito')}{BASE_MONO}/auth/register",
                             allow_redirects=False,
                             name="[monolito] GET /library/auth/register (formulario)",
                             timeout=TIEMPO_LIMITE, catch_response=True) as r:
            if MONO["sesion"] and r.status_code == 302:
                r.success()
            else:
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
            datos = valida_json(r, claves=("count", "total", "books"))
            if datos is not None and len(datos["books"]) != datos["count"]:
                r.failure(f"count={datos['count']} pero llegaron "
                          f"{len(datos['books'])} libros")

    @task(6)
    def books_detalle(self):
        """GET /books/<id>?format=json -- PAR COMPARABLE con el detalle del monolito."""
        ident = _elige(CATALOGO["libros"], 1)
        with self.client.get(f"{base('books')}/books/{ident}",
                             params={"format": "json"},
                             name="[books] GET /books/<id>?format=json (detalle)",
                             timeout=TIEMPO_LIMITE, catch_response=True) as r:
            if r.status_code == 404:
                r.success()      # el libro se dio de baja durante la corrida
                return
            datos = valida_json(r, claves=("book",))
            if datos is not None and datos["book"].get("id") != ident:
                r.failure(f"se pidio el libro {ident} y contesto "
                          f"{datos['book'].get('id')}")

    @task(4)
    def books_busqueda(self):
        """
        GET /books?<filtros> -- PAR COMPARABLE con la busqueda del monolito.

        Filtros en INGLES: asi los expone esta version (se comprobo con
        curl que `titulo=`, `autor=` o `genero=` se IGNORAN en silencio
        -- devuelven el catalogo entero y `filters` vacio --, que es
        peor que un error porque la asercion pasaria midiendo otra
        cosa). Cada combinacion es una clave de cache distinta, de modo
        que casi siempre es MISS y va a PostgreSQL: comparada con el
        catalogo completo (casi siempre HIT) mide lo que aporta Redis.
        """
        filtros = dict(_elige([
            {"genre": "Novela"}, {"year_min": "1990"}, {"price_max": "500"},
            {"title": "sistemas"}, {"author": "Martin"},
            {"year_min": "1900", "year_max": "1980"}, {"price_min": "200"},
        ]))
        filtros["format"] = "json"
        with self.client.get(f"{base('books')}/books", params=filtros,
                             name="[books] GET /books?<filtros> (busqueda)",
                             timeout=TIEMPO_LIMITE, catch_response=True) as r:
            datos = valida_json(r, claves=("count", "total", "books", "filters"))
            if datos is not None and datos["count"] > datos["total"]:
                r.failure(f"count={datos['count']} > total={datos['total']}")
            elif datos is not None and not datos["filters"]:
                r.failure("el servicio ignoro los filtros: 'filters' vino vacio")

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
            valida_salud(r)

    # -----------------------------------------------------------------
    # AUTHORS :5003 (peso total 14) -- la otra lectura publica real
    # -----------------------------------------------------------------
    @task(6)
    def authors_listado(self):
        """GET /authors?format=json -- coleccion bajo la clave 'authors'."""
        with self.client.get(f"{base('authors')}/authors",
                             params={"format": "json"},
                             name="[authors] GET /authors?format=json (listado)",
                             timeout=TIEMPO_LIMITE, catch_response=True) as r:
            valida_json(r, claves=("authors", "count", "total"))

    @task(4)
    def authors_detalle(self):
        """GET /authors/<id>?format=json -- el autor con sus libros."""
        ident = _elige(CATALOGO["autores"], 1)
        with self.client.get(f"{base('authors')}/authors/{ident}",
                             params={"format": "json"},
                             name="[authors] GET /authors/<id>?format=json (detalle)",
                             timeout=TIEMPO_LIMITE, catch_response=True) as r:
            if r.status_code == 404:
                r.success()
                return
            datos = valida_json(r, claves=("id", "name"))
            if datos is not None and datos["id"] != ident:
                r.failure(f"se pidio {ident} y contesto {datos['id']}")

    @task(2)
    def authors_listado_xml(self):
        """GET /authors?format=xml -- la misma coleccion en XML."""
        with self.client.get(f"{base('authors')}/authors",
                             params={"format": "xml"},
                             name="[authors] GET /authors?format=xml (listado)",
                             timeout=TIEMPO_LIMITE, catch_response=True) as r:
            valida_xml(r, "authors")

    @task(2)
    def authors_salud(self):
        with self.client.get(f"{base('authors')}/health",
                             params={"format": "json"},
                             name="[authors] GET /health",
                             timeout=TIEMPO_LIMITE, catch_response=True) as r:
            valida_salud(r)

    # -----------------------------------------------------------------
    # LOS CUATRO SERVICIOS SIN LECTURA PUBLICA DE DATOS (peso 5 cada uno)
    # login :5000 · users :5002 · pedidos :5004 · pagos :5005
    #
    # Que se mide: /health ejerce PostgreSQL y Redis; la ruta protegida
    # ejerce la cadena de autorizacion completa -- leer la cabecera,
    # verificar la firma del JWT y consultar la revocacion en Redis --
    # devolviendo 401 sin tocar datos; y /metrics, que en esta version
    # es publico, ejerce el contador interno del servicio.
    #
    # Que NO se mide: sus operaciones de negocio, que son escrituras.
    # Queda dicho en RESULTADOS.md; no se disimula.
    # -----------------------------------------------------------------
    def _salud(self, destino):
        with self.client.get(f"{base(destino)}/health", params={"format": "json"},
                             name=f"[{destino}] GET /health",
                             timeout=TIEMPO_LIMITE, catch_response=True) as r:
            valida_salud(r)

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
        """GET /metrics -- en esta version es PUBLICO y responde XML."""
        with self.client.get(f"{base(destino)}/metrics",
                             name=f"[{destino}] GET /metrics",
                             timeout=TIEMPO_LIMITE, catch_response=True) as r:
            valida_xml(r, "metrics")

    @task(2)
    def login_salud(self):
        self._salud("login")

    @task(2)
    def login_session(self):
        """
        GET /session -- en esta version responde 200 sin sesion.

        Es la comprobacion de sesion del servicio de autenticacion: mira
        la cookie, y sin ella contesta {"authenticated": false}. Ejerce
        Redis, que es donde vive la sesion.
        """
        with self.client.get(f"{base('login')}/session",
                             params={"format": "json"},
                             name="[login] GET /session",
                             timeout=TIEMPO_LIMITE, catch_response=True) as r:
            valida_json(r, claves=("authenticated",))

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

    @task(1)
    def pedidos_listado(self):
        self._protegida("pedidos", "/pedidos")

    @task(1)
    def pedidos_envio(self):
        """
        GET /envios/<numero> -- la UNICA ruta publica de pedidos.

        Es publica a proposito para que un tercero lleve la logistica.
        En esta base no hay ningun pedido, de modo que lo que se mide es
        la consulta a PostgreSQL que acaba en 404. No es una lectura de
        negocio y asi queda registrado.
        """
        with self.client.get(f"{base('pedidos')}/envios/PED-000001",
                             params={"format": "json"},
                             name="[pedidos] GET /envios/<numero> [404 esperado]",
                             timeout=TIEMPO_LIMITE, catch_response=True) as r:
            valida_404(r)

    @task(1)
    def pedidos_metricas(self):
        self._metricas("pedidos")

    @task(2)
    def pagos_salud(self):
        self._salud("pagos")

    @task(1)
    def pagos_listado(self):
        self._protegida("pagos", "/pagos")

    @task(1)
    def pagos_metodos(self):
        self._protegida("pagos", "/metodos")

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
