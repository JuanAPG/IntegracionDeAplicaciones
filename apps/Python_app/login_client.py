"""Cliente del microservicio login. Siempre pide JSON (?format=json).

QUE CAMBIO CON REDIS
  * El token de acceso dura 30 MINUTOS (antes 1 h) y ya no se espera a
    que caduque: POST /refresh lo renueva antes, canjeando un refresh
    token que vive 8 h en Redis y es de UN SOLO USO (al canjearlo se
    entrega otro).
  * /logout ya no solo borra la cookie: REVOCA el token en Redis, de
    modo que deja de servir en los seis microservicios en el acto.
  * La sesion vive en Redis y la cookie solo lleva su identificador, de
    modo que una sesion se puede cerrar desde el servidor.

El token y el refresh se guardan en un TokenBox compartido con los demas
clientes (ver api_client.py), para que renovar en un sitio valga para
todos.
"""
import json
import secrets

import requests

from api_client import TokenBox, decode_claims


def _err(resp, fallback):
    try:
        data = resp.json()
    except Exception:
        data = None
    if isinstance(data, dict) and isinstance(data.get("error"), dict):
        e = data["error"]
        msg = e.get("message") or fallback
        details = e.get("details") or []
        code = e.get("code") or ""
        if details:
            msg = msg + " — " + "; ".join(str(d) for d in details[:3])
        return msg, e.get("status", resp.status_code), code
    return f"{fallback} (HTTP {resp.status_code}).", resp.status_code, ""


class LoginClient:
    def __init__(self, base_url, timeout=8, tokens=None):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({"Accept": "application/json"})
        # TokenBox compartido: si lo renueva este cliente, los de libros,
        # pedidos y pagos usan el token nuevo sin enterarse.
        self.tokens = tokens if tokens is not None else TokenBox()

    # -- compatibilidad con el codigo que ya usaba .token/.set_token ----
    @property
    def token(self):
        """El JWT Bearer actual, o None si no hay login vigente."""
        return self.tokens.access

    def set_token(self, token, refresh=None, renew_before=None):
        self.tokens.set(token, refresh, renew_before)

    @property
    def refresh_token(self):
        return self.tokens.refresh

    def token_expired(self):
        """True si el JWT ya caduco (claim exp contra la hora local; la
        verificacion de verdad la hace el servidor)."""
        if not self.tokens.access:
            return True
        return self.tokens.expired()

    def token_expiring_soon(self):
        """True si conviene renovar ya (quedan menos de renewBefore)."""
        return bool(self.tokens.access) and self.tokens.expiring_soon()

    def seconds_left(self):
        return self.tokens.seconds_left()

    @property
    def role(self):
        return self.tokens.role

    @property
    def user_id(self):
        return self.tokens.user_id

    def claims(self):
        return decode_claims(self.tokens.access)

    # -----------------------------------------------------------------
    def refresh(self):
        """
        Canjea el refresh token por un par nuevo (POST /refresh).

        Devuelve True si lo consiguio. Si falla, se limpia la sesion: el
        refresh es de un solo uso y, si el servidor lo rechaza, no hay
        nada que reintentar — hay que volver a iniciar sesion.
        """
        if not self.tokens.refresh:
            return False
        try:
            r = self.session.post(f"{self.base_url}/refresh",
                                  params={"format": "json"},
                                  json={"refreshToken": self.tokens.refresh},
                                  timeout=self.timeout)
        except requests.RequestException:
            # Sin red no se puede renovar, pero el token actual puede
            # seguir sirviendo: no se borra la sesion por un corte.
            return False
        if r.status_code != 200:
            self.tokens.clear()
            return False
        try:
            data = r.json()
        except ValueError:
            return False
        self.tokens.set(data.get("token"), data.get("refreshToken"),
                        data.get("renewBefore"))
        return bool(self.tokens.access)

    def ensure_fresh(self):
        """Renueva si al token le queda poco. Lo llaman los demas clientes."""
        if self.tokens.access and self.tokens.expiring_soon():
            return self.refresh()
        return bool(self.tokens.access)

    @staticmethod
    def new_idempotency_key():
        """Clave para que un reintento de pago no cobre dos veces."""
        return secrets.token_urlsafe(16)

    def restore_cookies(self, cookies):
        if cookies:
            try:
                from requests.utils import cookiejar_from_dict
                self.session.cookies = cookiejar_from_dict(cookies)
            except Exception:
                pass

    def snapshot_cookies(self):
        try:
            return self.session.cookies.get_dict()
        except Exception:
            return {}

    def health(self):
        try:
            r = self.session.get(f"{self.base_url}/health", params={"format": "json"},
                                 timeout=self.timeout)
        except requests.RequestException as exc:
            return False, f"Sin conexión con {self.base_url}: {exc}", None
        try:
            data = r.json() if "json" in r.headers.get("Content-Type", "") else {}
        except Exception:
            data = {}
        if r.status_code == 200:
            return True, "up", data
        msg, _, _ = _err(r, "Login no disponible")
        # El 503 de login con cuerpo suele ser "Redis caido": el
        # servicio responde, pero no puede abrir ni cerrar sesiones.
        if r.status_code == 503 and isinstance(data, dict):
            # Accesible pero degradado (p. ej. sin PostgreSQL): el cuerpo trae
            # {"status": "error", ...} en vez de dejar data en None.
            data = {"status": "error", "degraded": True,
                    "message": data.get("message", msg)}
            return False, msg, data
        return False, msg, None

    def validate_email(self, email):
        try:
            r = self.session.get(f"{self.base_url}/validate-email",
                                 params={"email": email, "format": "json"}, timeout=self.timeout)
        except requests.RequestException as exc:
            return False, f"Sin conexión: {exc}", None
        try:
            data = r.json()
        except Exception:
            return False, "Respuesta no válida del servicio.", None
        return True, "", data

    def register(self, nombre, apellido_paterno, email, password, apellido_materno=""):
        payload = {"nombre": nombre, "apellidoPaterno": apellido_paterno,
                   "email": email, "password": password}
        if apellido_materno:
            payload["apellidoMaterno"] = apellido_materno
        try:
            r = self.session.post(f"{self.base_url}/register", params={"format": "json"},
                                  json=payload, timeout=self.timeout)
        except requests.RequestException as exc:
            return False, f"Sin conexión: {exc}", None, ""
        if r.status_code == 201:
            try:
                data = r.json()
            except Exception:
                data = {}
            ev = (data.get("emailVerification") or {})
            extra = "" if ev.get("sent") else " Revisa tu correo para verificar la cuenta."
            return True, "Registro exitoso." + extra, data, ""
        msg, _, code = _err(r, "No se pudo registrar")
        if r.status_code == 409:
            msg = "Ese correo ya está registrado. Usa Iniciar sesión."
        return False, msg, None, code

    def verify(self, token):
        """Canjea el token de verificación (GET /verify?token=)."""
        token = (token or "").strip()
        if not token:
            return False, "Pega el token que llegó a tu correo.", None
        try:
            r = self.session.get(f"{self.base_url}/verify",
                                 params={"token": token, "format": "json"},
                                 timeout=self.timeout)
        except requests.RequestException as exc:
            return False, f"Sin conexión: {exc}", None
        if r.status_code == 200:
            try:
                data = r.json()
            except Exception:
                data = {}
            user = data.get("user", {}) if isinstance(data, dict) else {}
            return True, "Correo verificado. Ya puedes iniciar sesión.", user
        msg, status, _code = _err(r, "No se pudo verificar")
        if status == 404:
            msg = "Ese token no existe o ya fue reemplazado por uno nuevo."
        elif status == 410:
            msg = ("Ese token ya se usó o expiró. Si expiró (48 h), regístrate "
                   "de nuevo para recibir otro.")
        return False, msg, None

    def login(self, email, password):
        try:
            r = self.session.post(f"{self.base_url}/login", params={"format": "json"},
                                  json={"email": email, "password": password},
                                  timeout=self.timeout)
        except requests.RequestException as exc:
            return False, f"Sin conexión: {exc}", None, ""
        if r.status_code == 200:
            try:
                data = r.json()
            except Exception:
                data = {}
            # Se guardan los DOS: el de acceso (30 min) y el refresh (8 h).
            self.tokens.set(data.get("token"), data.get("refreshToken"),
                            data.get("renewBefore"))
            return True, "Sesión iniciada.", data.get("user", {}), ""
        self.tokens.clear()
        msg, status, code = _err(r, "No se pudo iniciar sesión")
        if status == 401:
            msg = "Usuario no encontrado o credenciales inválidas."
        elif status == 403 or code == "email_not_verified":
            msg = "El correo aún no está verificado. Abre el enlace que llegó por correo (/verify)."
        return False, msg, None, code

    def logout(self):
        """
        Cierra la sesion en el servidor.

        Se manda el Bearer ademas de la cookie: asi el servidor REVOCA el
        jti en Redis y el token deja de servir en los seis
        microservicios de inmediato, en vez de seguir siendo valido hasta
        30 minutos despues. Si la llamada falla (sin red), se limpia
        igualmente del lado del cliente.
        """
        headers = {}
        if self.tokens.access:
            headers["Authorization"] = f"Bearer {self.tokens.access}"
        try:
            self.session.post(f"{self.base_url}/logout",
                              params={"format": "json"}, headers=headers,
                              timeout=self.timeout)
        except requests.RequestException:
            pass
        self.tokens.clear()
        try:
            self.session.cookies.clear()
        except Exception:
            pass

    def get_session(self):
        try:
            r = self.session.get(f"{self.base_url}/session", params={"format": "json"},
                                 timeout=self.timeout)
        except requests.RequestException as exc:
            return False, f"Sin conexión: {exc}", None
        try:
            data = r.json()
        except Exception:
            return False, "Respuesta no válida del servicio.", None
        if data.get("authenticated"):
            return True, "", data.get("user", {})
        return False, "Sin sesión.", None
