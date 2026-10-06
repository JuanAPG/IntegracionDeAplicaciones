"""
test/test_users_mocked.py
Pruebas del microservicio de usuarios SIN PostgreSQL y SIN servidor
Redis: el repositorio se simula y Redis se sustituye por el doble en
memoria de library_common.testing.

Lo que cubre:
  1. Ninguna lectura es publica: sin token, 401.
  2. Autorizacion de grano fino: el propio usuario opera sobre lo suyo;
     para lo ajeno hacen falta permisos (403 si el rol no alcanza).
  3. Alta, reemplazo, cambio parcial y baja LOGICA de cuentas.
  4. password_hash NUNCA sale en una respuesta, ni en XML ni en JSON.
  5. Cambiar contrasena exige la actual si es la propia cuenta.
  6. Cambiar el correo lo deja SIN verificar.
  7. Cambiar rol, contrasena, correo o desactivar REVOCA las sesiones
     del usuario en Redis.
  8. No se puede dejar el sistema sin ningun administrador activo.
  9. Los permisos de un rol se reemplazan e invalidan el cache de Redis.
 10. XML y JSON para el mismo recurso.

Uso (desde apps/services/users):
    python test/test_users_mocked.py
"""
import os
import sys
from datetime import datetime, timezone

os.environ.setdefault("JWT_SECRET_KEY", "secreto-jwt-de-pruebas-suficientemente-largo")
os.environ.setdefault("REDIS_URL", "redis://:prueba@localhost:6379/0")
os.environ.setdefault("DEFAULT_FORMAT", "xml")

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

import users.shared as shared  # noqa: E402
from library_common import testing as redis_testing  # noqa: E402

FAKE = redis_testing.install(shared.store)

import users.app as appmod  # noqa: E402
import users.config as config  # noqa: E402
import users.repository as repo  # noqa: E402
from users.security import hash_password, verify_password  # noqa: E402

# ---------------------------------------------------------------------
# Base simulada: cuentas y roles
# ---------------------------------------------------------------------
AHORA = datetime.now(timezone.utc)
ROLES = {
    1: {"id": 1, "name": "admin", "description": "Administrador", "is_admin": True,
        "permissions": ["*"], "user_count": 1},
    2: {"id": 2, "name": "user", "description": "Cliente", "is_admin": False,
        "permissions": [], "user_count": 1},
    3: {"id": 3, "name": "staff", "description": "Personal", "is_admin": True,
        "permissions": ["users:read", "books:write", "orders:write"], "user_count": 0},
}
CUENTAS = {}
SIGUIENTE = {"id": 1}


def nueva_cuenta(email, role_id, *, activa=True, verificado=True, password="Secreto123"):
    uid = SIGUIENTE["id"]
    SIGUIENTE["id"] += 1
    CUENTAS[uid] = {
        "id": uid, "first_name": "Nombre", "last_name_paternal": "Paterno",
        "last_name_maternal": None, "full_name": "Nombre Paterno",
        "email": email, "role": ROLES[role_id]["name"], "role_id": role_id,
        "email_verified": verificado, "is_active": activa,
        "created_at": AHORA, "updated_at": AHORA, "last_login_at": None,
        "password_hash": hash_password(password),
    }
    return uid


ADMIN_ID = nueva_cuenta("admin@ejemplo.mx", 1)
CLIENTE_ID = nueva_cuenta("cliente@ejemplo.mx", 2)


def _fila(uid):
    return dict(CUENTAS[uid]) if uid in CUENTAS else None


repo.get_by_id = lambda uid: _fila(int(uid))
repo.get_by_email = lambda email: next(
    (dict(c) for c in CUENTAS.values() if c["email"].lower() == email.lower()), None)
repo.get_credentials = lambda uid: ({"id": int(uid),
                                     "password_hash": CUENTAS[int(uid)]["password_hash"]}
                                    if int(uid) in CUENTAS else None)
repo.email_taken = lambda email, exclude_id=None: any(
    c["email"].lower() == email.lower() and c["id"] != exclude_id
    for c in CUENTAS.values())


def fake_list_users(filters, sort="id", order="asc", limit=50, offset=0):
    filas = [dict(c) for c in CUENTAS.values()]
    if filters.get("role"):
        filas = [f for f in filas
                 if f["role"] == filters["role"] or str(f["role_id"]) == filters["role"]]
    if filters.get("active") is not None:
        filas = [f for f in filas if f["is_active"] is filters["active"]]
    filas.sort(key=lambda f: f["id"], reverse=(str(order).lower() == "desc"))
    return filas[offset:offset + limit], len(filas)


def fake_create_user(*, first, paternal, maternal, full_name, email,
                     password_hash, role_id=2, email_verified=False, is_active=True):
    uid = SIGUIENTE["id"]
    SIGUIENTE["id"] += 1
    CUENTAS[uid] = {"id": uid, "first_name": first, "last_name_paternal": paternal,
                    "last_name_maternal": maternal, "full_name": full_name,
                    "email": email, "role": ROLES[role_id]["name"], "role_id": role_id,
                    "email_verified": email_verified, "is_active": is_active,
                    "created_at": AHORA, "updated_at": AHORA, "last_login_at": None,
                    "password_hash": password_hash}
    return dict(CUENTAS[uid])


def fake_update_user(uid, changes):
    uid = int(uid)
    if uid not in CUENTAS:
        return None
    mapa = {"first": "first_name", "paternal": "last_name_paternal",
            "maternal": "last_name_maternal", "full_name": "full_name",
            "email": "email", "password_hash": "password_hash",
            "role_id": "role_id", "email_verified": "email_verified",
            "is_active": "is_active"}
    for clave, valor in changes.items():
        if clave in mapa:
            CUENTAS[uid][mapa[clave]] = valor
    # El disparador trg_users_sync_role mantiene role al dia: se simula.
    CUENTAS[uid]["role"] = ROLES[CUENTAS[uid]["role_id"]]["name"]
    return dict(CUENTAS[uid])


repo.list_users = fake_list_users
repo.create_user = fake_create_user
repo.update_user = fake_update_user
repo.set_active = lambda uid, active: fake_update_user(uid, {"is_active": bool(active)})
repo.count_active_admins = lambda exclude_id=None: sum(
    1 for c in CUENTAS.values()
    if c["role"] == "admin" and c["is_active"] and c["id"] != exclude_id)
repo.list_roles = lambda: [dict(r) for r in ROLES.values()]
repo.get_role = lambda rid: (dict(ROLES[int(rid)]) if int(rid) in ROLES else None)
repo.get_role_by_name = lambda name: next(
    (dict(r) for r in ROLES.values() if r["name"].lower() == name.lower()), None)


def fake_create_role(name, description="", is_admin=False):
    rid = max(ROLES) + 1
    ROLES[rid] = {"id": rid, "name": name, "description": description,
                  "is_admin": is_admin, "permissions": [], "user_count": 0}
    return rid


repo.create_role = fake_create_role


def fake_set_permissions(role_id, permissions):
    ROLES[int(role_id)]["permissions"] = sorted(set(permissions))


repo.set_role_permissions = fake_set_permissions

# El resolutor de permisos lee library.role_permissions; aqui sale de ROLES.
shared.resolver.permissions_of = lambda role_id: frozenset(
    ROLES.get(int(role_id), {}).get("permissions", []))
# /health no debe intentar conectar con PostgreSQL.
shared.database.health = lambda: (True, {"status": "ok", "database": "library_db",
                                         "user": "library_user", "schema": "library",
                                         "server": "PostgreSQL 16"})

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


def token_de(uid):
    cuenta = CUENTAS[uid]
    tok, _ = shared.codec.issue_access_token(
        user_id=uid, email=cuenta["email"], role=cuenta["role"],
        role_id=cuenta["role_id"], sid=f"sid-{uid}")
    return tok


def auth(uid):
    return {"Authorization": f"Bearer {token_de(uid)}"}


def abrir_sesion(uid):
    """Simula lo que haria login: sesion + refresh + indice del usuario."""
    sid = f"sid-{uid}"
    tok, claims = shared.codec.issue_access_token(
        user_id=uid, email=CUENTAS[uid]["email"], role=CUENTAS[uid]["role"],
        role_id=CUENTAS[uid]["role_id"], sid=sid)
    shared.store.save_session(sid, {"sid": sid, "user_id": uid,
                                    "access_jti": claims["jti"],
                                    "refresh_hash": f"hash-{uid}"}, 28800)
    shared.store.strict_set(shared.store.refresh_key(f"hash-{uid}", hashed=True),
                            {"sid": sid}, 28800)
    shared.store.track_session(uid, sid, 28800)
    return tok, claims["jti"]


# =====================================================================
print("1. Ninguna lectura es publica")
for ruta in ("/users", "/users/1", "/roles", "/roles/1"):
    r = client.get(f"{ruta}?format=json")
    check(f"GET {ruta} sin token -> 401",
          r.status_code == 401 and r.get_json()["error"]["code"] == "unauthorized",
          f"{r.status_code}")
r = client.get("/health?format=json")
check("GET /health si es publico", r.status_code == 200)
r = client.get("/metrics?format=json")
check("GET /metrics si es publico", r.status_code == 200)

print("2. Autorizacion de grano fino")
r = client.get("/users?format=json", headers=auth(ADMIN_ID))
check("admin lista cuentas", r.status_code == 200
      and r.get_json()["total"] == len(CUENTAS), r.get_data(as_text=True)[:140])
r = client.get("/users?format=json", headers=auth(CLIENTE_ID))
check("cliente NO lista cuentas -> 403", r.status_code == 403
      and r.get_json()["error"]["code"] == "forbidden", str(r.status_code))
r = client.get(f"/users/{CLIENTE_ID}?format=json", headers=auth(CLIENTE_ID))
check("cliente SI ve su propia cuenta", r.status_code == 200
      and r.get_json()["id"] == CLIENTE_ID, r.get_data(as_text=True)[:140])
r = client.get(f"/users/{ADMIN_ID}?format=json", headers=auth(CLIENTE_ID))
check("cliente NO ve la cuenta de otro -> 403", r.status_code == 403, str(r.status_code))
r = client.get(f"/users/{CLIENTE_ID}?format=json", headers=auth(ADMIN_ID))
check("admin ve cualquier cuenta", r.status_code == 200)
r = client.get("/users/9999?format=json", headers=auth(ADMIN_ID))
check("cuenta inexistente -> 404", r.status_code == 404, str(r.status_code))

print("3. password_hash nunca sale en una respuesta")
r = client.get(f"/users/{CLIENTE_ID}?format=json", headers=auth(ADMIN_ID))
cuerpo = r.get_data(as_text=True)
check("el JSON no trae password_hash",
      "password" not in cuerpo.lower() and "$2b$" not in cuerpo, cuerpo[:160])
r = client.get(f"/users/{CLIENTE_ID}", headers=auth(ADMIN_ID))
cuerpo = r.get_data(as_text=True)
check("el XML tampoco, y es XML",
      "password" not in cuerpo.lower() and cuerpo.startswith("<?xml"), cuerpo[:120])
r = client.get("/users?format=json", headers=auth(ADMIN_ID))
check("el listado tampoco", "password" not in r.get_data(as_text=True).lower())

print("4. Alta de cuentas")
alta = {"nombre": "Ada", "apellidoPaterno": "Lovelace", "apellidoMaterno": "Byron",
        "email": "ada@ejemplo.mx", "password": "Secreto123"}
r = client.post("/users?format=json", json=alta, headers=auth(CLIENTE_ID))
check("cliente no puede dar de alta -> 403", r.status_code == 403, str(r.status_code))
r = client.post("/users?format=json", json=alta, headers=auth(ADMIN_ID))
nueva = r.get_json()
check("admin da de alta -> 201", r.status_code == 201 and nueva["email"] == "ada@ejemplo.mx",
      r.get_data(as_text=True)[:200])
ADA_ID = nueva["id"]
check("nace como cliente (roleId 2) y sin verificar",
      nueva["roleId"] == 2 and nueva["emailVerified"] is False, str(nueva))
check("la contrasena se guardo como hash bcrypt",
      CUENTAS[ADA_ID]["password_hash"].startswith("$2")
      and CUENTAS[ADA_ID]["password_hash"] != "Secreto123")
check("full_name se compuso", nueva["fullName"] == "Ada Lovelace Byron", str(nueva))
check("Location apunta al recurso",
      r.headers.get("Location") == f"/users/{ADA_ID}", str(r.headers.get("Location")))
r = client.post("/users?format=json", json=alta, headers=auth(ADMIN_ID))
check("correo duplicado -> 409", r.status_code == 409, str(r.status_code))
r = client.post("/users?format=json", json={"nombre": "X"}, headers=auth(ADMIN_ID))
check("alta incompleta -> 400 con detalles", r.status_code == 400
      and len(r.get_json()["error"]["details"]) >= 2, r.get_data(as_text=True)[:200])
r = client.post("/users?format=json",
                json={**alta, "email": "otra@ejemplo.mx", "password": "123"},
                headers=auth(ADMIN_ID))
check("contrasena corta -> 400", r.status_code == 400, str(r.status_code))
r = client.post("/users?format=json",
                json={**alta, "email": "rol@ejemplo.mx", "role": "no-existe"},
                headers=auth(ADMIN_ID))
check("rol inexistente -> 400", r.status_code == 400, r.get_data(as_text=True)[:140])
r = client.post("/users?format=json",
                json={**alta, "email": "staff@ejemplo.mx", "role": "staff",
                      "emailVerified": True},
                headers=auth(ADMIN_ID))
check("admin puede fijar rol y marcar verificado",
      r.status_code == 201 and r.get_json()["roleId"] == 3
      and r.get_json()["emailVerified"] is True, r.get_data(as_text=True)[:200])
STAFF_ID = r.get_json()["id"]

print("5. Cambio parcial")
r = client.patch(f"/users/{ADA_ID}?format=json", json={"nombre": "Augusta"},
                 headers=auth(ADA_ID))
check("el propio usuario cambia su nombre", r.status_code == 200
      and r.get_json()["nombre"] == "Augusta", r.get_data(as_text=True)[:160])
check("full_name se recompuso",
      r.get_json()["fullName"] == "Augusta Lovelace Byron", str(r.get_json()))
r = client.patch(f"/users/{ADA_ID}?format=json", json={"isActive": False},
                 headers=auth(ADA_ID))
check("el propio usuario NO puede desactivarse por aqui -> 403",
      r.status_code == 403, r.get_data(as_text=True)[:160])
r = client.patch(f"/users/{ADA_ID}?format=json", json={"roleId": 1},
                 headers=auth(ADMIN_ID))
check("el rol no se cambia por PATCH -> 400 que indica la ruta",
      r.status_code == 400 and "role" in r.get_data(as_text=True),
      r.get_data(as_text=True)[:200])
r = client.patch(f"/users/{ADA_ID}?format=json", json={"password": "x"},
                 headers=auth(ADMIN_ID))
check("la contrasena no se cambia por PATCH -> 400", r.status_code == 400)
r = client.patch(f"/users/{ADA_ID}?format=json", json={}, headers=auth(ADA_ID))
check("PATCH vacio -> 400", r.status_code == 400)

print("6. Contrasena: exige la actual si es la propia cuenta")
tok_ada, jti_ada = abrir_sesion(ADA_ID)
r = client.patch(f"/users/{ADA_ID}/password?format=json",
                 json={"password": "NuevaClave456"},
                 headers={"Authorization": f"Bearer {tok_ada}"})
check("sin currentPassword -> 400", r.status_code == 400,
      r.get_data(as_text=True)[:160])
r = client.patch(f"/users/{ADA_ID}/password?format=json",
                 json={"password": "NuevaClave456", "currentPassword": "mal"},
                 headers={"Authorization": f"Bearer {tok_ada}"})
check("currentPassword incorrecta -> 401", r.status_code == 401,
      r.get_data(as_text=True)[:160])
r = client.patch(f"/users/{ADA_ID}/password?format=json",
                 json={"password": "NuevaClave456", "currentPassword": "Secreto123"},
                 headers={"Authorization": f"Bearer {tok_ada}"})
check("con la actual correcta -> 200", r.status_code == 200,
      r.get_data(as_text=True)[:200])
check("la contrasena nueva quedo guardada como hash",
      verify_password("NuevaClave456", CUENTAS[ADA_ID]["password_hash"]))
check("cambiar la contrasena cerro las sesiones",
      r.get_json()["sessionsClosed"] == 1 and FAKE.exists(f"session:sid-{ADA_ID}") == 0,
      str(r.get_json()))
check("y revoco el token anterior", FAKE.exists(f"jwt:revoked:{jti_ada}") == 1)
check("la respuesta no repite la contrasena",
      "NuevaClave456" not in r.get_data(as_text=True))
tok_ada2, _ = abrir_sesion(ADA_ID)
r = client.patch(f"/users/{ADA_ID}/password?format=json",
                 json={"password": "OtraClave789"}, headers=auth(ADMIN_ID))
check("un admin la restablece sin conocer la anterior", r.status_code == 200,
      r.get_data(as_text=True)[:160])

print("7. Correo: queda sin verificar")
tok_staff, jti_staff = abrir_sesion(STAFF_ID)
r = client.patch(f"/users/{STAFF_ID}/email?format=json",
                 json={"email": "nuevo@ejemplo.mx"}, headers=auth(ADMIN_ID))
cuerpo = r.get_json()
check("cambio de correo -> 200", r.status_code == 200
      and cuerpo["email"] == "nuevo@ejemplo.mx", r.get_data(as_text=True)[:200])
check("el correo nuevo queda SIN verificar",
      cuerpo["emailVerified"] is False, str(cuerpo))
check("y avisa de que hay que verificarlo", "verificar" in (cuerpo.get("note") or ""),
      str(cuerpo.get("note")))
check("cambiar el correo cerro las sesiones", cuerpo["sessionsClosed"] == 1
      and FAKE.exists(f"jwt:revoked:{jti_staff}") == 1, str(cuerpo))
r = client.patch(f"/users/{STAFF_ID}/email?format=json",
                 json={"email": "cliente@ejemplo.mx"}, headers=auth(ADMIN_ID))
check("correo de otra cuenta -> 409", r.status_code == 409, str(r.status_code))
r = client.patch(f"/users/{STAFF_ID}/email?format=json",
                 json={"email": "nuevo@ejemplo.mx"}, headers=auth(ADMIN_ID))
check("el mismo correo que ya tiene -> 400", r.status_code == 400, str(r.status_code))
r = client.patch(f"/users/{CLIENTE_ID}/email?format=json",
                 json={"email": "yo@ejemplo.mx", "verified": True},
                 headers=auth(CLIENTE_ID))
check("un cliente no puede marcar su correo como verificado -> 403",
      r.status_code == 403, r.get_data(as_text=True)[:160])

print("8. Cambio de rol: revoca y invalida el cache de permisos")
tok_cliente, jti_cliente = abrir_sesion(CLIENTE_ID)
shared.store.cache_set(shared.store.key("roles", "perms", 3), ["books:write"], 300)
check("habia cache de permisos del rol 3",
      FAKE.exists("roles:perms:3") == 1, str(FAKE.keys_matching("roles:*")))
r = client.put(f"/users/{CLIENTE_ID}/role?format=json", json={"role": "staff"},
               headers=auth(ADMIN_ID))
cuerpo = r.get_json()
check("cambio de rol -> 200", r.status_code == 200 and cuerpo["roleId"] == 3,
      r.get_data(as_text=True)[:200])
check("informa el rol anterior", cuerpo["previousRoleId"] == 2, str(cuerpo))
check("revoco el token con el rol viejo",
      FAKE.exists(f"jwt:revoked:{jti_cliente}") == 1 and cuerpo["sessionsClosed"] == 1,
      str(cuerpo))
check("invalido el cache de permisos", FAKE.exists("roles:perms:3") == 0,
      str(FAKE.keys_matching("roles:*")))
r = client.put(f"/users/{CLIENTE_ID}/role?format=json", json={"roleId": 3},
               headers=auth(ADMIN_ID))
check("fijar el mismo rol no hace nada", r.status_code == 200
      and r.get_json()["updated"] is False, r.get_data(as_text=True)[:160])
r = client.put(f"/users/{ADA_ID}/role?format=json", json={"roleId": 1},
               headers=auth(STAFF_ID))
check("staff (sin users:roles) no cambia roles -> 403", r.status_code == 403,
      str(r.status_code))

print("9. Baja logica y proteccion del ultimo administrador")
r = client.delete(f"/users/{ADA_ID}?format=json", headers=auth(ADMIN_ID))
cuerpo = r.get_json()
check("baja -> 200 y is_active false", r.status_code == 200
      and cuerpo["isActive"] is False, r.get_data(as_text=True)[:200])
check("la fila se conserva (baja logica)", ADA_ID in CUENTAS
      and CUENTAS[ADA_ID]["is_active"] is False)
check("lo dice en la respuesta", "logica" in (cuerpo.get("note") or ""),
      str(cuerpo.get("note")))
r = client.delete(f"/users/{ADA_ID}?format=json", headers=auth(ADMIN_ID))
check("repetir la baja es idempotente", r.status_code == 200
      and r.get_json().get("alreadyInactive") is True, r.get_data(as_text=True)[:160])
check("solo queda un admin activo", repo.count_active_admins() == 1)
r = client.delete(f"/users/{ADMIN_ID}?format=json", headers=auth(ADMIN_ID))
check("no se puede desactivar al ultimo admin -> 409", r.status_code == 409
      and "administrador" in r.get_json()["error"]["message"],
      r.get_data(as_text=True)[:200])
r = client.put(f"/users/{ADMIN_ID}/role?format=json", json={"roleId": 2},
               headers=auth(ADMIN_ID))
check("ni degradarlo -> 409", r.status_code == 409, r.get_data(as_text=True)[:160])

print("10. Roles y permisos")
r = client.get("/roles?format=json", headers=auth(ADMIN_ID))
cuerpo = r.get_json()
check("catalogo de roles", r.status_code == 200 and len(cuerpo["roles"]) >= 3,
      r.get_data(as_text=True)[:160])
check("publica el vocabulario de permisos",
      "users:write" in cuerpo["vocabulary"] and "orders:status" in cuerpo["vocabulary"],
      str(cuerpo.get("vocabulary")))
r = client.post("/roles?format=json",
                json={"name": "almacen", "description": "Almacen",
                      "permissions": ["orders:status"]},
                headers=auth(ADMIN_ID))
check("crear rol -> 201", r.status_code == 201
      and r.get_json()["permissions"] == ["orders:status"],
      r.get_data(as_text=True)[:200])
NUEVO_ROL = r.get_json()["id"]
r = client.post("/roles?format=json", json={"name": "almacen"}, headers=auth(ADMIN_ID))
check("rol duplicado -> 409", r.status_code == 409, str(r.status_code))
r = client.post("/roles?format=json", json={"name": "Con Espacios"},
                headers=auth(ADMIN_ID))
check("nombre de rol invalido -> 400", r.status_code == 400, str(r.status_code))
r = client.put(f"/roles/{NUEVO_ROL}/permissions?format=json",
               json={"permissions": ["orders:read", "payments:read"]},
               headers=auth(ADMIN_ID))
check("reemplazar permisos -> 200 (reemplaza, no anade)",
      r.status_code == 200
      and r.get_json()["permissions"] == ["orders:read", "payments:read"],
      r.get_data(as_text=True)[:200])
r = client.put(f"/roles/{NUEVO_ROL}/permissions?format=json",
               json={"permissions": ["no-es-un-permiso"]}, headers=auth(ADMIN_ID))
check("permiso fuera del vocabulario -> 400", r.status_code == 400
      and "vocabulario" in r.get_data(as_text=True).lower(),
      r.get_data(as_text=True)[:200])
r = client.put("/roles/1/permissions?format=json", json={"permissions": ["users:read"]},
               headers=auth(ADMIN_ID))
check("no se le puede quitar '*' al rol admin -> 409", r.status_code == 409,
      r.get_data(as_text=True)[:200])

print("11. XML y JSON del mismo recurso")
r = client.get("/roles", headers=auth(ADMIN_ID))
check("roles en XML por omision", r.status_code == 200
      and r.get_data(as_text=True).startswith("<?xml")
      and "<role>" in r.get_data(as_text=True), r.get_data(as_text=True)[:200])
r = client.post("/users", data="<user><nombre>Xml</nombre></user>",
                content_type="application/xml", headers=auth(ADMIN_ID))
check("cuerpo XML se interpreta (y falta lo demas -> 400 en XML)",
      r.status_code == 400 and "<error" in r.get_data(as_text=True),
      r.get_data(as_text=True)[:160])

print("12. Fallo seguro con Redis caido")
redis_testing.break_store(shared.store)
r = client.get("/users?format=json", headers=auth(ADMIN_ID))
check("sin poder comprobar la revocacion -> 503", r.status_code == 503
      and r.get_json()["error"]["code"] == "redis_unavailable",
      f"{r.status_code} {r.get_data(as_text=True)[:140]}")
r = client.get("/health?format=json")
check("health lo reporta -> 503", r.status_code == 503
      and r.get_json()["redis"]["status"] == "error", str(r.get_json().get("redis")))
check("y no filtra la clave de Redis", "prueba" not in r.get_data(as_text=True))
redis_testing.install(shared.store, FAKE)
r = client.get("/users?format=json", headers=auth(ADMIN_ID))
check("cuando Redis vuelve, funciona de nuevo", r.status_code == 200)

print(f"\nResultado: {PASSED} OK, {FAILED} fallos")
sys.exit(1 if FAILED else 0)
