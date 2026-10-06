"""
apps/services/login/login/sessions.py
Sesiones y refresh tokens en Redis.

QUE VIVE DONDE
    PostgreSQL   la cuenta: correo, hash de la contrasena, rol, estado.
                 Es la fuente principal y sobrevive a todo.
    Redis        la SESION y el REFRESH TOKEN, con TTL. Son efimeros a
                 proposito: si se pierden, el usuario vuelve a iniciar
                 sesion; no se pierde ningun dato del negocio.
    La cookie    solo el identificador de sesion (sid). El estado ya no
                 viaja en la cookie, y por eso ahora una sesion se puede
                 CERRAR del lado del servidor.

CLAVES
    session:<sid>       {user_id, email, role, role_id, access_jti,
                         refresh_hash, created_at, last_seen}   TTL 8 h
    refresh:<sha256>    {sid, user_id}                          TTL 8 h
    jwt:revoked:<jti>   {reason, at}            TTL = lo que le quede al token

CICLO DE VIDA
    POST /login     crea sid, guarda la sesion, emite access (30 min) +
                    refresh (8 h) y devuelve ambos.
    POST /refresh   canjea el refresh (UN SOLO USO, se borra al leerlo),
                    revoca el access anterior, emite un par nuevo y
                    renueva la sesion. Es la rotacion de tokens.
    POST /logout    revoca el access vigente, borra el refresh y borra la
                    sesion. El token deja de servir en los seis
                    microservicios de inmediato, porque todos consultan
                    jwt:revoked:<jti>.

El refresh token NO es un JWT: es opaco (32 bytes aleatorios) y de el en
Redis solo vive el SHA-256, igual que los tokens de verificacion de
correo. Leer Redis no da tokens usables.
"""
import logging
import secrets
from datetime import datetime, timezone

from . import config
from .shared import codec, store

log = logging.getLogger("library.login.sessions")


def _now():
    return datetime.now(timezone.utc).isoformat()


def new_sid():
    return secrets.token_urlsafe(24)


def new_refresh_token():
    return secrets.token_urlsafe(32)


def open_session(user_row, role_id=None):
    """
    Abre una sesion para una cuenta ya autenticada.

    Devuelve (sid, access_token, refresh_token, claims). Si Redis no
    responde, lanza RedisUnavailable (503): sin sesion ni posibilidad de
    revocar, iniciar sesion seria emitir una credencial que no se puede
    retirar, de modo que se falla de forma segura en lugar de continuar.
    """
    sid = new_sid()
    refresh_token = new_refresh_token()
    resolved_role_id = int(role_id if role_id is not None
                           else user_row.get("role_id") or 2)

    access_token, claims = codec.issue_access_token(
        user_id=user_row["id"],
        email=user_row["email"],
        role=user_row.get("role") or "user",
        role_id=resolved_role_id,
        sid=sid)

    record = {
        "sid": sid,
        "user_id": user_row["id"],
        "email": user_row["email"],
        "role": user_row.get("role") or "user",
        "role_id": resolved_role_id,
        "access_jti": claims["jti"],
        "refresh_hash": store.hash_token(refresh_token),
        "created_at": _now(),
        "last_seen": _now(),
    }
    store.save_session(sid, record, config.SESSION_TTL)
    store.save_refresh(refresh_token,
                       {"sid": sid, "user_id": user_row["id"], "issued_at": _now()},
                       config.JWT_REFRESH_TTL)
    # Indice user:sessions:<id>: permite que el microservicio de usuarios
    # cierre TODAS las sesiones de una cuenta cuando la desactiva o le
    # cambia el rol, sin esperar los 30 minutos del token.
    store.track_session(user_row["id"], sid, config.SESSION_TTL)
    log.info("Sesion abierta para user_id=%s (sid de %s caracteres)",
             user_row["id"], len(sid))
    return sid, access_token, refresh_token, claims


def read_session(sid, touch=True):
    """
    Devuelve la sesion y, si touch, renueva su TTL (ventana deslizante:
    vive mientras se use). None si no existe o ya caduco.
    """
    if not sid:
        return None
    return store.load_session(sid, config.SESSION_TTL if touch else None)


def rotate(raw_refresh, user_row):
    """
    Canjea un refresh token por un par nuevo.

    El token se consume de forma ATOMICA (se lee y se borra en el mismo
    paso), de modo que un refresh solo sirve una vez: si alguien lo
    reutiliza —porque lo robo— ya no vale, y el legitimo tampoco, lo que
    deja rastro del incidente en lugar de permitirlo en silencio.

    Devuelve (sid, access_token, refresh_token, claims) o None si el
    token no existe, ya se uso o caduco.
    """
    record = store.consume_refresh(raw_refresh)
    if not isinstance(record, dict):
        return None

    sid = record.get("sid")
    session_record = store.load_session(sid) if sid else None
    if not isinstance(session_record, dict):
        # La sesion ya se cerro (logout) aunque el refresh siguiera vivo.
        return None
    if int(session_record.get("user_id", 0)) != int(user_row["id"]):
        log.warning("Refresh token de otra cuenta: se descarta")
        return None

    # El token de acceso anterior deja de servir en el acto: si no se
    # revocara, seguiria siendo valido hasta 30 minutos despues de la
    # rotacion.
    previous_jti = session_record.get("access_jti")
    if previous_jti:
        store.revoke_jti(previous_jti, config.JWT_ACCESS_TTL, reason="refresh")

    refresh_token = new_refresh_token()
    access_token, claims = codec.issue_access_token(
        user_id=user_row["id"],
        email=user_row["email"],
        role=user_row.get("role") or "user",
        role_id=int(user_row.get("role_id") or session_record.get("role_id") or 2),
        sid=sid)

    session_record.update({
        "access_jti": claims["jti"],
        "refresh_hash": store.hash_token(refresh_token),
        "role": user_row.get("role") or session_record.get("role"),
        "role_id": int(user_row.get("role_id") or session_record.get("role_id") or 2),
        "last_seen": _now(),
    })
    store.save_session(sid, session_record, config.SESSION_TTL)
    store.save_refresh(refresh_token,
                       {"sid": sid, "user_id": user_row["id"], "issued_at": _now()},
                       config.JWT_REFRESH_TTL)
    store.track_session(user_row["id"], sid, config.SESSION_TTL)
    log.info("Tokens rotados para user_id=%s", user_row["id"])
    return sid, access_token, refresh_token, claims


def close_session(sid, access_claims=None):
    """
    Cierra una sesion: revoca el token de acceso, borra el refresh y
    borra la sesion.

    Devuelve lo que de verdad se hizo, para que /logout pueda informarlo
    (un logout sin sesion abierta sigue respondiendo 200: es idempotente).
    """
    done = {"sessionRemoved": False, "accessRevoked": False, "refreshRemoved": False}

    session_record = store.load_session(sid, None) if sid else None
    if isinstance(session_record, dict):
        stored_jti = session_record.get("access_jti")
        if stored_jti:
            store.revoke_jti(stored_jti, config.JWT_ACCESS_TTL, reason="logout")
            done["accessRevoked"] = True
        refresh_hash = session_record.get("refresh_hash")
        if refresh_hash:
            store.strict_delete(store.refresh_key(refresh_hash, hashed=True))
            done["refreshRemoved"] = True
        store.drop_session(sid)
        user_id = session_record.get("user_id")
        if user_id is not None:
            store.untrack_session(user_id, sid)
        done["sessionRemoved"] = True

    # El token con el que se llamo a /logout puede ser mas nuevo que el
    # anotado en la sesion (una rotacion que no alcanzo a guardarse): se
    # revoca tambien, para no dejar ninguno vivo.
    if access_claims:
        jti = access_claims.get("jti")
        if jti and jti != (session_record or {}).get("access_jti"):
            store.revoke_jti(jti, codec.seconds_left(access_claims), reason="logout")
            done["accessRevoked"] = True

    return done


def revoke_all_for_user(user_id):
    """
    Cierra TODAS las sesiones de un usuario y revoca sus tokens.

    La implementacion vive en el store compartido, de modo que el
    microservicio de usuarios puede hacer exactamente lo mismo sin
    importar este modulo: los dos operan sobre las mismas claves de
    Redis, que es lo que hace que la revocacion sea global.
    """
    return store.revoke_user_sessions(user_id, config.JWT_ACCESS_TTL)


def expires_in(claims):
    """Segundos que le quedan al token de acceso."""
    return codec.seconds_left(claims)
