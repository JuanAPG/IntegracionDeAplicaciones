"""
apps/Python_app/api_client.py
Base comun de los clientes HTTP de la aplicacion de escritorio.

QUE RESUELVE
  1. Un solo sitio donde se arma Authorization: Bearer <token>.
  2. RENOVACION AUTOMATICA. El token de acceso dura 30 minutos. En lugar
     de hacer que el usuario vuelva a iniciar sesion cada media hora, el
     cliente renueva con POST /refresh:
       * antes de una escritura, si al token le quedan menos de 5 min;
       * y si una peticion devuelve 401, se renueva UNA vez y se
         reintenta. Un segundo 401 ya es sesion perdida de verdad.
  3. Traduccion de los errores del servidor a frases en claro, con la
     distincion que importa:
       401 = tu sesion ya no vale, vuelve a entrar
       403 = tu sesion vale pero tu rol no alcanza
       503 = el servicio o Redis estan caidos; no es culpa tuya

Todos los servicios piden JSON explicitamente: ?output=json para libros
(donde ?format= es un filtro de busqueda) y ?format=json para los demas.
"""
import base64
import json
import time

import requests

# Margen con el que se renueva antes de caducar (lo publica el servidor
# en "renewBefore"; este es el valor de respaldo).
RENEW_BEFORE_DEFAULT = 300


def decode_claims(token):
    """Claims del JWT SIN verificar la firma (eso lo hace el servidor).

    Aqui solo se mira 'exp' para saber cuando renovar, y 'role'/'role_id'
    para decidir que botones mostrar. La autorizacion de verdad la
    aplica cada microservicio.
    """
    if not token:
        return {}
    try:
        payload = token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        return json.loads(base64.urlsafe_b64decode(payload))
    except Exception:                                   # noqa: BLE001
        return {}


class TokenBox:
    """
    El token compartido por todos los clientes.

    Vive en un solo objeto para que, cuando uno renueve, los demas usen
    el token nuevo sin tener que avisarles uno por uno.
    """

    def __init__(self, on_change=None):
        self.access = None
        self.refresh = None
        self.renew_before = RENEW_BEFORE_DEFAULT
        self.on_change = on_change          # fn(access, refresh) -> persiste

    def set(self, access, refresh=None, renew_before=None):
        self.access = access or None
        if refresh is not None:
            self.refresh = refresh or None
        if renew_before:
            self.renew_before = int(renew_before)
        if self.on_change:
            self.on_change(self.access, self.refresh)

    def clear(self):
        self.access = None
        self.refresh = None
        if self.on_change:
            self.on_change(None, None)

    @property
    def claims(self):
        return decode_claims(self.access)

    def seconds_left(self):
        """Segundos que le quedan al token, o None si no se puede saber."""
        exp = self.claims.get("exp")
        if not exp:
            return None
        return int(exp) - int(time.time())

    def expired(self):
        left = self.seconds_left()
        return left is not None and left <= 0

    def expiring_soon(self):
        left = self.seconds_left()
        return left is not None and left <= self.renew_before

    @property
    def role(self):
        return self.claims.get("role") or ""

    @property
    def role_id(self):
        return self.claims.get("role_id")

    @property
    def user_id(self):
        return self.claims.get("user_id")

    def can(self, *roles):
        """Pista para la interfaz. La decision real la toma el servidor."""
        return self.role in roles


class ApiError(Exception):
    """Error de un servicio, ya traducido a una frase util."""

    def __init__(self, message, status=0, code="", details=None):
        super().__init__(message)
        self.message = message
        self.status = status
        self.code = code
        self.details = details or []


def parse_error(response, fallback):
    """Extrae {"error": {...}} y lo convierte en un mensaje legible."""
    try:
        data = response.json()
    except Exception:                                   # noqa: BLE001
        data = None
    if isinstance(data, dict) and isinstance(data.get("error"), dict):
        bloque = data["error"]
        mensaje = bloque.get("message") or fallback
        detalles = [str(d) for d in (bloque.get("details") or [])]
        if detalles:
            mensaje = mensaje + " — " + "; ".join(detalles[:3])
        return ApiError(mensaje, bloque.get("status", response.status_code),
                        bloque.get("code", ""), detalles)
    return ApiError(f"{fallback} (HTTP {response.status_code}).",
                    response.status_code)


class ApiClient:
    """
    Cliente base de un microservicio.

    base_url     http://IP:PUERTO
    tokens       TokenBox compartido
    refresher    funcion sin argumentos que renueva el token y devuelve
                 True si lo consiguio. La provee LoginClient.
    format_param "format" para casi todos, "output" para libros.
    """

    SERVICE = "servicio"

    def __init__(self, base_url, tokens, timeout=8, refresher=None,
                 format_param="format"):
        self.base_url = (base_url or "").rstrip("/")
        self.tokens = tokens
        self.timeout = timeout
        self.refresher = refresher
        self.format_param = format_param
        self.session = requests.Session()
        self.session.headers.update({"Accept": "application/json"})

    # -----------------------------------------------------------------
    def _headers(self, with_auth):
        if with_auth and self.tokens.access:
            return {"Authorization": f"Bearer {self.tokens.access}"}
        return {}

    def _params(self, params):
        p = dict(params or {})
        p.setdefault(self.format_param, "json")
        return p

    def _renew_if_needed(self):
        """Renueva antes de caducar, para no gastar un 401 en averiguarlo."""
        if self.refresher and self.tokens.refresh and self.tokens.expiring_soon():
            self.refresher()

    def request(self, method, path, *, params=None, json_body=None,
                auth=True, fallback="La operacion fallo", retry=True):
        """
        Hace la peticion y devuelve (ok, datos_o_None, error_o_None).

        Nunca lanza por un fallo de red: lo convierte en ApiError, para
        que la interfaz siempre tenga algo que mostrar.
        """
        if auth:
            self._renew_if_needed()
        url = f"{self.base_url}{path}"
        try:
            response = self.session.request(
                method, url, params=self._params(params), json=json_body,
                headers=self._headers(auth), timeout=self.timeout)
        except requests.Timeout:
            return False, None, ApiError(
                f"{self.SERVICE}: se agoto el tiempo de espera ({self.timeout} s).")
        except requests.RequestException as exc:
            return False, None, ApiError(
                f"{self.SERVICE}: sin conexion con {self.base_url} ({exc}).")

        # 401 -> el token ya no vale. Se renueva UNA vez y se reintenta;
        # un segundo 401 significa que la sesion se perdio de verdad.
        if response.status_code == 401 and auth and retry and self.refresher \
                and self.tokens.refresh:
            if self.refresher():
                return self.request(method, path, params=params,
                                    json_body=json_body, auth=auth,
                                    fallback=fallback, retry=False)

        if response.status_code in (200, 201, 204):
            if response.status_code == 204 or not (response.content or b"").strip():
                return True, {}, None
            try:
                return True, response.json(), None
            except ValueError:
                return False, None, ApiError(
                    f"{self.SERVICE}: la respuesta no era JSON valido.")

        error = parse_error(response, fallback)
        # Mensajes que dicen QUE HACER, no solo que fallo.
        if error.status == 401:
            error.message = ("Tu sesion caduco o se cerro desde otro sitio. "
                             "Vuelve a iniciar sesion. — " + error.message)
        elif error.status == 403:
            error.message = ("Tu cuenta no tiene permiso para esto. — "
                             + error.message)
        elif error.status == 503:
            error.message = (f"{self.SERVICE} no esta disponible ahora mismo "
                             "(base de datos o Redis caidos). — " + error.message)
        return False, None, error

    # Atajos
    def get(self, path, params=None, auth=True, fallback="No se pudo consultar"):
        return self.request("GET", path, params=params, auth=auth, fallback=fallback)

    def post(self, path, body=None, params=None, fallback="No se pudo crear"):
        return self.request("POST", path, params=params, json_body=body,
                            fallback=fallback)

    def put(self, path, body=None, params=None, fallback="No se pudo actualizar"):
        return self.request("PUT", path, params=params, json_body=body,
                            fallback=fallback)

    def patch(self, path, body=None, params=None, fallback="No se pudo actualizar"):
        return self.request("PATCH", path, params=params, json_body=body,
                            fallback=fallback)

    def delete(self, path, body=None, params=None, fallback="No se pudo eliminar"):
        return self.request("DELETE", path, params=params, json_body=body,
                            fallback=fallback)

    # -----------------------------------------------------------------
    def health(self):
        """
        (ok, mensaje, datos) para el semaforo.

        /health es publico en los seis servicios, de modo que el semaforo
        funciona aunque no haya sesion abierta.
        """
        ok, data, error = self.get("/health", auth=False,
                                   fallback=f"{self.SERVICE} no disponible")
        if ok:
            return True, "up", data
        # Un 503 CON cuerpo significa accesible pero degradado: es
        # amarillo, no rojo, y el semaforo necesita distinguirlo.
        if error.status == 503 and error.details:
            return False, error.message, {"status": "error", "degraded": True,
                                          "message": error.message}
        return False, error.message, None
