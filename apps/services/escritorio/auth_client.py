"""
apps/services/escritorio/auth_client.py
Cliente de autenticacion JWT para el microservicio login.

Almacena el token en memoria durante la sesion. Disenado para que futuros
modulos (books_client.py, etc.) puedan reutilizarlo:

    auth = AuthClient("http://localhost:5000")
    auth.login("user@example.com", "password")
    headers = auth.get_auth_header()  # {"Authorization": "Bearer <token>"}
"""
import requests


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
            requests.HTTPError: Si las credenciales son invalidas (401)
            requests.RequestException: Si hay error de red
        """
        url = f"{self.base_url}/login"
        response = requests.post(
            url,
            json={"email": email, "password": password},
            headers={"Accept": "application/json"},
            timeout=self.timeout,
        )
        response.raise_for_status()
        data = response.json()

        self._token = data.get("token")
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

    def logout(self):
        """Elimina el token almacenado (logout local, sin llamar al servidor)."""
        self._token = None
        self._email = None
