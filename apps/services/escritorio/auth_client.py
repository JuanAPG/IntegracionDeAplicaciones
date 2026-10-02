"""
apps/services/escritorio/auth_client.py
Cliente de autenticacion JWT para el microservicio login.

Almacena el token en memoria durante la sesion. Disenado para que futuros
modulos (books_client.py, etc.) puedan reutilizarlo:

    auth = AuthClient("http://localhost:5000")
    auth.login("user@example.com", "password")
    headers = auth.get_auth_header()  # {"Authorization": "Bearer <token>"}
"""
import base64
import json

import requests


def _server_message(response, fallback):
    """Extrae el mensaje fino del microservicio (JSON {"error": {...}})."""
    try:
        data = response.json()
    except Exception:
        data = None
    if isinstance(data, dict) and isinstance(data.get("error"), dict):
        err = data["error"]
        msg = err.get("message") or fallback
        details = [str(d) for d in (err.get("details") or [])[:2]]
        if details:
            msg += " — " + "; ".join(details)
        return f"{msg} (HTTP {response.status_code})."
    return f"{fallback} (HTTP {response.status_code})."


class AuthClient:
    """Gestiona el ciclo de vida del token JWT en el cliente de escritorio."""

    def __init__(self, base_url, timeout=10):
        """
        Args:
            base_url: URL base del microservicio login (ej. "http://localhost:5000")
            timeout: Timeout en segundos para las peticiones HTTP
        """
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._token = None
        self._email = None

    @property
    def token(self):
        """El token JWT almacenado, o None si no se ha autenticado."""
        return self._token

    @property
    def email(self):
        """El email del usuario autenticado, o None."""
        return self._email

    def is_authenticated(self):
        """True si hay un token almacenado."""
        return self._token is not None

    def login(self, email, password):
        """Autentica contra el microservicio login y almacena el token JWT.

        Args:
            email: Correo del usuario
            password: Contrasena

        Returns:
            dict: Datos del usuario autenticado

        Raises:
            requests.HTTPError: Con el mensaje del servidor (401 credenciales,
                403 correo sin verificar) en lugar del texto generico.
            requests.RequestException: Si hay error de red
        """
        url = f"{self.base_url}/login"
        try:
            response = requests.post(
                url,
                json={"email": email, "password": password},
                headers={"Accept": "application/json"},
                timeout=self.timeout,
            )
        except requests.RequestException as exc:
            raise requests.ConnectionError(
                f"Sin conexion con {self.base_url}: {exc}") from exc
        if response.status_code != 200:
            raise requests.HTTPError(
                _server_message(response, "No se pudo iniciar sesion"),
                response=response)
        data = response.json()

        token = data.get("token")
        if not token:
            raise requests.HTTPError(
                "El servidor no devolvio token JWT.", response=response)
        self._token = token
        self._email = data.get("user", {}).get("email", email)
        return data

    def get_auth_header(self):
        """Devuelve el encabezado Authorization con el token Bearer.

        Returns:
            dict: {"Authorization": "Bearer <token>"} o {} si no hay token
        """
        if not self._token:
            return {}
        return {"Authorization": f"Bearer {self._token}"}

    def token_expiry(self):
        """Hora de expiracion (epoch) del claim exp, o None si no se lee."""
        if not self._token:
            return None
        try:
            payload = self._token.split(".")[1]
            payload += "=" * (-len(payload) % 4)
            return json.loads(base64.urlsafe_b64decode(payload)).get("exp")
        except Exception:
            return None

    def is_expired(self):
        """True si el token ya expiro (comparado contra la hora local)."""
        import time
        exp = self.token_expiry()
        return exp is not None and exp <= int(time.time())

    def logout(self):
        """Elimina el token almacenado (logout local, sin llamar al servidor)."""
        self._token = None
        self._email = None
