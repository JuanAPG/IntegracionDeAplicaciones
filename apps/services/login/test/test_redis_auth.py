"""
test/test_redis_auth.py
Pruebas de la capa de Redis en el microservicio de login, SIN PostgreSQL
y SIN servidor Redis: el repositorio se simula y Redis se sustituye por
el doble en memoria de library_common.testing (que si respeta los TTL).

Cubre lo que el enunciado pide y lo que es facil creer que funciona sin
que funcione:

  1. El token de acceso dura 30 minutos y lleva user_id, role_id y jti.
  2. La sesion y el refresh viven en Redis con TTL; el refresh solo como
     hash SHA-256.
  3. /refresh ROTA: el refresh viejo deja de servir y el token de acceso
     anterior queda REVOCADO en el acto.
  4. /logout revoca el jti: el token deja de servir antes de caducar.
  5. Fallo SEGURO: con Redis caido, /login, /refresh y /session devuelven
     503 en lugar de emitir o aceptar credenciales no revocables.
  6. Un token caducado, con otra firma o con alg=none se rechaza con 401.

Uso (desde apps/services/login):
    python test/test_redis_auth.py
"""
import os
import sys
from datetime import datetime, timedelta, timezone

os.environ.setdefault("SECRET_KEY", "secreto-de-pruebas")
os.environ.setdefault("JWT_SECRET_KEY", "secreto-jwt-de-pruebas-suficientemente-largo")
os.environ.setdefault("REDIS_URL", "redis://:prueba@localhost:6379/0")

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

import bcrypt  # noqa: E402
import jwt as pyjwt  # noqa: E402

import login.shared as shared  # noqa: E402
from library_common import testing as redis_testing  # noqa: E402

FAKE = redis_testing.install(shared.store)

import login.app as appmod  # noqa: E402
import login.config as config  # noqa: E402
import login.db as dbmod  # noqa: E402
import login.sessions as session_box  # noqa: E402
import login.users_repository as repo  # noqa: E402
from library_common.errors import RedisUnavailable, Unauthorized  # noqa: E402

# ---------------------------------------------------------------------
# Cuenta simulada (lo que devolveria PostgreSQL)
# ---------------------------------------------------------------------
HASH = bcrypt.hashpw(b"Secreto123", bcrypt.gensalt(4)).decode()
CUENTA = {
    "id": 7, "first_name": "Ada", "last_name_paternal": "Lovelace",
    "last_name_maternal": "Byron", "full_name": "Ada Lovelace Byron",
    "email": "ada@ejemplo.mx", "role": "user", "role_id": 2,
    "email_verified": True, "is_active": True,
    "created_at": datetime.now(timezone.utc), "updated_at": None,
    "last_login_at": None, "password_hash": HASH,
}
ESTADO = {"activa": True, "role_id": 2, "role": "user"}


def _cuenta():
    row = dict(CUENTA)
    row["is_active"] = ESTADO["activa"]
    row["role_id"] = ESTADO["role_id"]
    row["role"] = ESTADO["role"]
    return row


repo.get_by_email = lambda email: _cuenta() if email.lower() == CUENTA["email"] else None
repo.get_by_id = lambda uid: _cuenta() if int(uid) == CUENTA["id"] else None
repo.set_last_login = lambda uid: None
dbmod.ping = lambda: {"db": "library_db", "usr": "library_user",
                      "version": "PostgreSQL 16 on test"}
shared.resolver.permissions_of = lambda role_id: frozenset(
    {"*"} if int(role_id) == 1 else set())

client = appmod.app.test_client()
PASSED, FAILED = 0, 0


def check(name, cond, extra=""):
    global PASSED, FAILED
    if cond:
        PASSED += 1
        print(f"  OK    {name}")
    else:
        FAILED += 1
        print(f"  FALLA {name} {extra}")


def hacer_login(cliente=None):
    c = cliente or client
    r = c.post("/login?format=json",
               json={"email": CUENTA["email"], "password": "Secreto123"})
    return r, (r.get_json() if r.status_code == 200 else {})


def claims_de(token):
    return pyjwt.decode(token, options={"verify_signature": False})


# =====================================================================
print("1. Token de acceso de 30 minutos con los claims del enunciado")
r, data = hacer_login()
check("login 200", r.status_code == 200, r.get_data(as_text=True)[:200])
check("expiresIn = 1800 s (30 min)", data.get("expiresIn") == 1800, str(data.get("expiresIn")))
claims = claims_de(data["token"])
check("claims user_id y role_id",
      claims.get("user_id") == 7 and claims.get("role_id") == 2,
      str({k: claims.get(k) for k in ("user_id", "role_id")}))
check("claims jti, sid, iss, typ",
      bool(claims.get("jti")) and bool(claims.get("sid"))
      and claims.get("iss") == config.JWT_ISSUER and claims.get("typ") == "access")
check("exp - iat = 1800", claims["exp"] - claims["iat"] == 1800)
check("algoritmo HS256",
      pyjwt.get_unverified_header(data["token"])["alg"] == "HS256")

print("2. Sesion y refresh en Redis, con TTL")
sid = claims["sid"]
check("clave session:<sid> existe", FAKE.exists(f"session:{sid}") == 1,
      str(FAKE.keys_matching("session:*")))
check("TTL de la sesion ~8 h", 28000 < FAKE.ttl(f"session:{sid}") <= 28800,
      str(FAKE.ttl(f"session:{sid}")))
check("clave refresh:<sha256> existe", len(FAKE.keys_matching("refresh:*")) == 1)
check("el refresh en claro NO esta en Redis",
      data["refreshToken"] not in str(FAKE.snapshot()))
check("la contrasena NO esta en Redis",
      "Secreto123" not in str(FAKE.snapshot()) and HASH not in str(FAKE.snapshot()))

print("3. /refresh rota los tokens y revoca el anterior")
viejo_token, viejo_refresh, viejo_jti = data["token"], data["refreshToken"], claims["jti"]
r = client.post("/refresh?format=json", json={"refreshToken": viejo_refresh})
nuevo = r.get_json()
check("refresh 200", r.status_code == 200, r.get_data(as_text=True)[:200])
check("entrega un token de acceso distinto", nuevo.get("token") != viejo_token)
check("entrega un refresh distinto (rotacion)",
      nuevo.get("refreshToken") != viejo_refresh)
check("el refresh viejo ya NO sirve (un solo uso)",
      client.post("/refresh?format=json",
                  json={"refreshToken": viejo_refresh}).status_code == 401)
check("el token de acceso viejo quedo REVOCADO",
      FAKE.exists(f"jwt:revoked:{viejo_jti}") == 1,
      str(FAKE.keys_matching("jwt:revoked:*")))
try:
    shared.codec.decode(viejo_token)
    check("un verificador rechaza el token revocado", False, "lo acepto")
except Unauthorized as exc:
    check("un verificador rechaza el token revocado", "revoc" in exc.message.lower(),
          exc.message)
check("el token nuevo SI lo acepta un verificador",
      shared.codec.decode(nuevo["token"])["user_id"] == 7)
check("la sesion sigue siendo la misma (mismo sid)",
      claims_de(nuevo["token"])["sid"] == sid)

print("4. Refresh invalido, ausente y de cuenta desactivada")
check("refresh inexistente -> 401",
      client.post("/refresh?format=json", json={"refreshToken": "no-existe"}).status_code == 401)
check("refresh ausente -> 400",
      client.post("/refresh?format=json", json={}).status_code == 400)
ESTADO["activa"] = False
check("cuenta desactivada -> 401",
      client.post("/refresh?format=json",
                  json={"refreshToken": nuevo["refreshToken"]}).status_code == 401)
ESTADO["activa"] = True

print("5. /logout revoca el token de acceso")
r, data = hacer_login()
token, jti = data["token"], claims_de(data["token"])["jti"]
sid = claims_de(data["token"])["sid"]
check("el token sirve antes del logout", shared.codec.decode(token)["user_id"] == 7)
r = client.post("/logout?format=json", headers={"Authorization": f"Bearer {token}"})
cuerpo = r.get_json()
check("logout 200", r.status_code == 200 and cuerpo["authenticated"] is False)
check("logout informa que revoco y limpio",
      cuerpo.get("accessRevoked") is True and cuerpo.get("sessionRemoved") is True
      and cuerpo.get("refreshRemoved") is True, str(cuerpo))
check("la sesion se borro de Redis", FAKE.exists(f"session:{sid}") == 0)
check("el jti quedo en la lista de revocacion",
      FAKE.exists(f"jwt:revoked:{jti}") == 1)
try:
    shared.codec.decode(token)
    check("el token deja de servir en el acto", False, "lo acepto")
except Unauthorized:
    check("el token deja de servir en el acto", True)
check("logout sin sesion sigue siendo 200 (idempotente)",
      client.post("/logout?format=json").status_code == 200)

print("6. /logout con el token por Bearer, sin cookie")
otro = appmod.app.test_client()
_r, data = hacer_login(otro)
token = data["token"]
sin_cookie = appmod.app.test_client()
r = sin_cookie.post("/logout?format=json", headers={"Authorization": f"Bearer {token}"})
check("cierra la sesion de un cliente sin cookies",
      r.status_code == 200 and r.get_json().get("accessRevoked") is True,
      str(r.get_json()))

print("7. Caducidad: la sesion se renueva al usarse y muere sola")
_r, data = hacer_login()
sid = claims_de(data["token"])["sid"]
FAKE.advance(7 * 3600)                      # 7 h de las 8
r = client.get("/session?format=json")
check("a las 7 h la sesion sigue viva", r.get_json().get("authenticated") is True)
FAKE.advance(7 * 3600)                      # 7 h mas desde la renovacion
r = client.get("/session?format=json")
check("consultarla renovo el TTL (ventana deslizante)",
      r.get_json().get("authenticated") is True)
FAKE.advance(config.SESSION_TTL + 60)
r = client.get("/session?format=json")
check("sin uso, la sesion caduca sola",
      r.get_json().get("authenticated") is False, str(r.get_json()))

print("8. Tokens invalidos: 401, nunca 403")
_r, data = hacer_login()
bueno = data["token"]
casos = [
    ("firma ajena", pyjwt.encode(claims_de(bueno), "otro-secreto", algorithm="HS256")),
    ("alg none", pyjwt.encode(claims_de(bueno), key="", algorithm="none")),
    ("basura", "esto.no.es"),
]
for nombre, malo in casos:
    try:
        shared.codec.decode(malo)
        check(f"{nombre} -> rechazado", False, "lo acepto")
    except Unauthorized as exc:
        check(f"{nombre} -> 401 {exc.code}", exc.status == 401)
caducado = pyjwt.encode(
    {**claims_de(bueno),
     "exp": datetime.now(timezone.utc) - timedelta(minutes=1),
     "iat": datetime.now(timezone.utc) - timedelta(minutes=31)},
    config.JWT_SECRET, algorithm="HS256")
try:
    shared.codec.decode(caducado)
    check("token caducado -> rechazado", False, "lo acepto")
except Unauthorized as exc:
    check("token caducado -> 401", exc.status == 401 and "expir" in exc.message.lower(),
          exc.message)
sin_claims = pyjwt.encode({"sub": "7", "exp": datetime.now(timezone.utc) + timedelta(minutes=5),
                           "iat": datetime.now(timezone.utc), "iss": config.JWT_ISSUER},
                          config.JWT_SECRET, algorithm="HS256")
try:
    shared.codec.decode(sin_claims)
    check("token sin user_id/role_id/jti -> rechazado", False, "lo acepto")
except Unauthorized as exc:
    check("token sin user_id/role_id/jti -> 401", exc.status == 401, exc.message)

print("9. /health y /metrics informan de Redis")
r = client.get("/health?format=json")
cuerpo = r.get_json()
check("health 200 con Redis arriba", r.status_code == 200
      and cuerpo["redis"]["status"] == "ok", str(cuerpo.get("redis")))
check("health publica los TTL vigentes",
      cuerpo.get("jwtAccessTtl") == 1800 and cuerpo.get("jwtRefreshTtl") == 28800)
check("health NO publica la clave de Redis",
      "prueba" not in str(cuerpo.get("redis")), str(cuerpo.get("redis")))
r = client.get("/metrics?format=json")
cuerpo = r.get_json()
check("metrics trae contadores", r.status_code == 200
      and cuerpo["counters"].get("jwt.issued", 0) > 0, str(cuerpo)[:200])
check("metrics cuenta los tokens revocados",
      cuerpo["counters"].get("jwt.revoked", 0) > 0)
check("metrics trae el estado del servidor Redis",
      cuerpo.get("redis", {}).get("version") is not None)

print("10. FALLO SEGURO: Redis caido")
redis_testing.break_store(shared.store)
r = client.post("/login?format=json",
                json={"email": CUENTA["email"], "password": "Secreto123"})
check("login con Redis caido -> 503 (no emite credencial irrevocable)",
      r.status_code == 503 and r.get_json()["error"]["code"] == "redis_unavailable",
      f"{r.status_code} {r.get_data(as_text=True)[:160]}")
r = client.post("/refresh?format=json", json={"refreshToken": "lo-que-sea"})
check("refresh con Redis caido -> 503", r.status_code == 503)
r = client.get("/session?format=json")
check("session con Redis caido -> 503", r.status_code == 503)
r = client.get("/health?format=json")
check("health con Redis caido -> 503 y lo dice",
      r.status_code == 503 and r.get_json()["redis"]["status"] == "error",
      str(r.get_json().get("redis")))
try:
    shared.codec.decode(bueno)
    check("verificar un token sin poder consultar la revocacion -> falla", False,
          "lo acepto a ciegas")
except RedisUnavailable as exc:
    check("verificar un token sin poder consultar la revocacion -> 503",
          exc.status == 503)
check("el error 503 NO filtra la clave de Redis",
      "prueba" not in r.get_data(as_text=True), r.get_data(as_text=True)[:200])

# Redis vuelve: el servicio se recupera sin reiniciar.
redis_testing.install(shared.store, FAKE)
r = client.post("/login?format=json",
                json={"email": CUENTA["email"], "password": "Secreto123"})
check("cuando Redis vuelve, el login funciona de nuevo", r.status_code == 200,
      r.get_data(as_text=True)[:160])

print(f"\nResultado: {PASSED} OK, {FAILED} fallos")
sys.exit(1 if FAILED else 0)
