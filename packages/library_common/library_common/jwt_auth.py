"""
packages/library_common/library_common/jwt_auth.py
Emision y verificacion de JWT, y decoradores de autorizacion.

El EMISOR es solo el microservicio login. Los demas unicamente verifican,
con el mismo JWT_SECRET_KEY del .env de la raiz (nunca escrito en el
codigo) y el mismo algoritmo HS256.

Claims del token de acceso
--------------------------
    sub        id del usuario como cadena (claim estandar)
    user_id    id del usuario como entero (lo exige el enunciado)
    role_id    id del rol en library.roles (lo exige el enunciado)
    role       nombre del rol (admin/staff/user), por legibilidad
    email      correo de la cuenta
    sid        id de la sesion en Redis, para poder cerrarla
    jti        identificador unico del token -> clave de revocacion
    typ        "access" (los refresh NO son JWT: son opacos y viven en Redis)
    iss        emisor
    iat / exp  emision y vencimiento (30 minutos por omision)

Lo que se verifica en CADA peticion, en este orden
--------------------------------------------------
    1. que el encabezado sea exactamente "Authorization: Bearer <token>"
    2. que el algoritmo del encabezado del token sea el esperado (HS256):
       se rechaza "none" y cualquier intento de confundir el algoritmo
    3. la firma, con el secreto compartido
    4. el vencimiento (exp) y el emisor (iss)
    5. que esten presentes los claims obligatorios
    6. que el jti NO este en la lista de revocacion de Redis

Codigos de respuesta
--------------------
    401  token ausente, malformado, invalido, vencido o revocado
    403  token valido pero el rol no tiene permiso para la operacion
    503  no se pudo consultar la lista de revocacion (fallo seguro)
"""
import functools
import logging
import uuid
from datetime import datetime, timedelta, timezone

import jwt
from flask import g, request

from . import metrics
from .errors import Forbidden, Unauthorized

log = logging.getLogger("library.auth")

# Claims sin los cuales un token no se considera valido.
REQUIRED_CLAIMS = ("sub", "user_id", "role_id", "jti", "iat", "exp")


class JwtCodec:
    """
    Emite y verifica los JWT de la libreria.

    store  RedisStore compartido; se usa para la lista de revocacion.
           Si es None, la verificacion de revocacion no se puede hacer y
           el token se rechaza (fallo seguro), salvo que el servicio
           declare explicitamente que no la necesita.
    """

    def __init__(self, secret, algorithm="HS256", *, issuer="library-login-service",
                 access_ttl_seconds=1800, leeway_seconds=10, store=None):
        self.secret = secret or ""
        self.algorithm = algorithm or "HS256"
        self.issuer = issuer
        self.access_ttl = int(access_ttl_seconds)
        self.leeway = int(leeway_seconds)
        self.store = store

    @property
    def configured(self):
        from . import env
        return env.is_real(self.secret)

    # -----------------------------------------------------------------
    # Emision (solo login la usa)
    # -----------------------------------------------------------------
    def issue_access_token(self, *, user_id, email, role, role_id, sid=None,
                           ttl_seconds=None):
        """
        Devuelve (token, claims). El jti es nuevo en cada emision: es lo
        que permite revocar ESTE token sin tocar los demas del usuario.
        """
        now = datetime.now(timezone.utc)
        ttl = int(ttl_seconds or self.access_ttl)
        claims = {
            "sub": str(user_id),
            "user_id": int(user_id),
            "role_id": int(role_id),
            "role": role,
            "email": email,
            "sid": sid,
            "jti": uuid.uuid4().hex,
            "typ": "access",
            "iss": self.issuer,
            "iat": now,
            "exp": now + timedelta(seconds=ttl),
        }
        token = jwt.encode(claims, self.secret, algorithm=self.algorithm)
        if isinstance(token, bytes):                   # PyJWT 1.x devolvia bytes
            token = token.decode("utf-8")
        metrics.incr("jwt.issued")
        # Se registra la emision SIN el token y SIN el correo completo.
        log.info("JWT emitido para user_id=%s role_id=%s ttl=%ss", user_id, role_id, ttl)
        return token, claims

    # -----------------------------------------------------------------
    # Verificacion
    # -----------------------------------------------------------------
    def decode(self, token, *, expected_type="access", check_revocation=True):
        """
        Verifica un token y devuelve sus claims.

        Lanza Unauthorized (401) si el token no sirve, o RedisUnavailable
        (503) si no se pudo consultar la lista de revocacion.
        """
        if not self.configured:
            # Sin secreto real cualquier firma seria falsificable: no se
            # acepta ningun token en lugar de aceptar todos.
            raise Unauthorized(
                "El servicio no tiene JWT_SECRET_KEY configurado; no puede "
                "verificar tokens.",
                ["Fije JWT_SECRET_KEY en el .env de la raiz, igual en todos "
                 "los microservicios."])

        # 1. Algoritmo declarado en el encabezado del propio token. Se
        #    comprueba antes de decodificar para dejar constancia de que
        #    "alg: none" y la confusion de algoritmos quedan rechazadas.
        try:
            header = jwt.get_unverified_header(token)
        except jwt.InvalidTokenError as exc:
            metrics.incr("jwt.rejected.malformed")
            raise Unauthorized("Token malformado.", [str(exc).strip()]) from exc
        if header.get("alg") != self.algorithm:
            metrics.incr("jwt.rejected.algorithm")
            raise Unauthorized(
                f"Algoritmo de token no admitido: se exige {self.algorithm}.",
                [f"El token declara '{header.get('alg')}'."])

        # 2. Firma, vencimiento, emisor y claims obligatorios.
        try:
            claims = jwt.decode(
                token,
                self.secret,
                algorithms=[self.algorithm],
                issuer=self.issuer,
                leeway=self.leeway,
                options={"require": list(REQUIRED_CLAIMS),
                         "verify_signature": True,
                         "verify_exp": True,
                         "verify_iat": True,
                         "verify_iss": True},
            )
        except jwt.ExpiredSignatureError as exc:
            metrics.incr("jwt.rejected.expired")
            raise Unauthorized(
                "El token ha expirado.",
                ["Renuevelo con POST /refresh antes de que caduque, o "
                 "vuelva a iniciar sesion."]) from exc
        except jwt.MissingRequiredClaimError as exc:
            metrics.incr("jwt.rejected.claims")
            raise Unauthorized(f"El token no trae el claim obligatorio "
                               f"'{exc.claim}'.") from exc
        except jwt.InvalidIssuerError as exc:
            metrics.incr("jwt.rejected.issuer")
            raise Unauthorized("El token no fue emitido por este sistema.") from exc
        except jwt.InvalidSignatureError as exc:
            metrics.incr("jwt.rejected.signature")
            raise Unauthorized("La firma del token no es valida.") from exc
        except jwt.InvalidTokenError as exc:
            metrics.incr("jwt.rejected.invalid")
            raise Unauthorized("Token invalido.", [str(exc).strip()]) from exc

        # 3. Tipo de token: un refresh jamas sirve como token de acceso.
        if expected_type and claims.get("typ", "access") != expected_type:
            metrics.incr("jwt.rejected.type")
            raise Unauthorized(
                f"Se esperaba un token de tipo '{expected_type}'.")

        # 4. Lista de revocacion en Redis. Si Redis no responde, is_revoked
        #    lanza RedisUnavailable (503): ante la duda NO se acepta el
        #    token, en lugar de honrar una credencial posiblemente revocada.
        if check_revocation:
            if self.store is None:
                raise Unauthorized(
                    "El servicio no puede comprobar la lista de revocacion.",
                    ["Fije REDIS_URL en el .env de la raiz."])
            if self.store.is_revoked(claims["jti"]):
                metrics.incr("jwt.rejected.revoked")
                log.info("Token revocado rechazado: user_id=%s", claims.get("user_id"))
                raise Unauthorized(
                    "El token fue revocado (se cerro la sesion).",
                    ["Inicie sesion de nuevo para obtener un token valido."])

        metrics.incr("jwt.accepted")
        return claims

    def seconds_left(self, claims):
        """Vida restante del token, para fijar el TTL de la revocacion."""
        exp = claims.get("exp")
        if not exp:
            return self.access_ttl
        if isinstance(exp, datetime):
            exp = int(exp.timestamp())
        left = int(exp) - int(datetime.now(timezone.utc).timestamp())
        return max(left, 1)


# ---------------------------------------------------------------------
# Lectura del encabezado
# ---------------------------------------------------------------------
def bearer_token(required=True):
    """
    Extrae el token de "Authorization: Bearer <token>".

    Se exige exactamente ese esquema: ni "Token ", ni el token a secas,
    ni el token por parametro de consulta (acabaria en los registros del
    servidor y en el historial del navegador).
    """
    header = request.headers.get("Authorization", "")
    if not header:
        if not required:
            return None
        metrics.incr("jwt.rejected.missing")
        raise Unauthorized(
            "Falta el encabezado Authorization.",
            ["Formato esperado: Authorization: Bearer <token>."])
    scheme, _, value = header.partition(" ")
    if scheme.lower() != "bearer" or not value.strip():
        metrics.incr("jwt.rejected.malformed")
        raise Unauthorized(
            "Encabezado Authorization malformado.",
            ["Formato esperado: Authorization: Bearer <token>."])
    return value.strip()


# ---------------------------------------------------------------------
# Identidad de la peticion
# ---------------------------------------------------------------------
class Identity:
    """Quien hace la peticion, ya verificado."""

    __slots__ = ("user_id", "role_id", "role", "email", "sid", "jti", "claims",
                 "permissions")

    def __init__(self, claims, permissions=frozenset()):
        self.claims = claims
        self.user_id = int(claims["user_id"])
        self.role_id = int(claims["role_id"])
        self.role = claims.get("role") or ""
        self.email = claims.get("email") or ""
        self.sid = claims.get("sid")
        self.jti = claims.get("jti")
        self.permissions = frozenset(permissions)

    def has(self, permission):
        return "*" in self.permissions or permission in self.permissions

    def is_self(self, user_id):
        try:
            return self.user_id == int(user_id)
        except (TypeError, ValueError):
            return False

    def __repr__(self):            # sin correo ni jti: esto puede acabar en un log
        return f"<Identity user_id={self.user_id} role_id={self.role_id}>"


def current_identity():
    """La identidad verificada de esta peticion, o None si es anonima."""
    return getattr(g, "identity", None)


# ---------------------------------------------------------------------
# Decoradores de autorizacion
# ---------------------------------------------------------------------
def make_auth(codec, permissions_of_role=None):
    """
    Construye los decoradores del servicio.

    codec                JwtCodec ya configurado.
    permissions_of_role  funcion role_id -> conjunto de permisos. Si es
                         None, la autorizacion se decide solo por el
                         nombre del rol.

    Devuelve (token_required, permission_required, roles_required,
              optional_token).
    """

    def _authenticate():
        token = bearer_token(required=True)
        claims = codec.decode(token)
        perms = permissions_of_role(claims["role_id"]) if permissions_of_role else frozenset()
        identity = Identity(claims, perms)
        g.identity = identity
        return identity

    def token_required(view):
        """Exige un JWT valido. Para POST/PUT/PATCH/DELETE."""
        @functools.wraps(view)
        def wrapper(*args, **kwargs):
            _authenticate()
            return view(*args, **kwargs)
        return wrapper

    def optional_token(view):
        """
        Acepta la peticion con o sin token. Si viene uno, se verifica de
        verdad (un token invalido sigue siendo 401) y queda disponible en
        current_identity() para que la ruta decida cuanto mostrar.
        """
        @functools.wraps(view)
        def wrapper(*args, **kwargs):
            if request.headers.get("Authorization"):
                _authenticate()
            else:
                g.identity = None
            return view(*args, **kwargs)
        return wrapper

    def permission_required(*needed):
        """
        Exige un JWT valido Y que el rol tenga todos los permisos dados.
        401 si el token no sirve; 403 si sirve pero el rol no alcanza.
        """
        def decorator(view):
            @functools.wraps(view)
            def wrapper(*args, **kwargs):
                identity = _authenticate()
                missing = [p for p in needed if not identity.has(p)]
                if missing:
                    metrics.incr("authz.denied")
                    log.info("Permiso denegado: user_id=%s role_id=%s requiere %s",
                             identity.user_id, identity.role_id, ", ".join(missing))
                    raise Forbidden(
                        "Su rol no tiene permiso para esta operacion.",
                        [f"Permiso requerido: {', '.join(missing)}.",
                         f"Rol actual: {identity.role or identity.role_id}."])
                return view(*args, **kwargs)
            return wrapper
        return decorator

    def roles_required(*names):
        """Exige que el nombre del rol este entre los indicados."""
        allowed = {n.lower() for n in names}

        def decorator(view):
            @functools.wraps(view)
            def wrapper(*args, **kwargs):
                identity = _authenticate()
                if (identity.role or "").lower() not in allowed:
                    metrics.incr("authz.denied")
                    raise Forbidden(
                        "Su rol no tiene permiso para esta operacion.",
                        [f"Roles autorizados: {', '.join(sorted(allowed))}.",
                         f"Rol actual: {identity.role or identity.role_id}."])
                return view(*args, **kwargs)
            return wrapper
        return decorator

    return token_required, permission_required, roles_required, optional_token
