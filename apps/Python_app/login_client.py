"""Cliente del microservicio login. Siempre pide JSON (?format=json)."""
import requests


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
    def __init__(self, base_url, timeout=8):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({"Accept": "application/json"})

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
            return True, "Sesión iniciada.", data.get("user", {}), ""
        msg, status, code = _err(r, "No se pudo iniciar sesión")
        if status == 401:
            msg = "Usuario no encontrado o credenciales inválidas."
        elif status == 403 or code == "email_not_verified":
            msg = "El correo aún no está verificado. Abre el enlace que llegó por correo (/verify)."
        return False, msg, None, code

    def logout(self):
        try:
            self.session.post(f"{self.base_url}/logout", params={"format": "json"},
                              timeout=self.timeout)
        except requests.RequestException:
            pass
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
