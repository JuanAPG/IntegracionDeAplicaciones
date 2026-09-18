"""
test/test_login_mocked.py
Pruebas del microservicio SIN PostgreSQL ni sendmail: se simulan el
repositorio y el envio de correo, y se ejercitan todos los endpoints en
XML (omision) y JSON (?format=json) con el test_client de Flask.

Uso (en la VM o aqui con un .venv):
    python test/test_login_mocked.py
"""
import os
import sys
from datetime import datetime, timedelta, timezone

os.environ.setdefault("SECRET_KEY", "secreto-de-pruebas")

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "login"))

import app as appmod  # noqa: E402
import db as dbmod  # noqa: E402
import tokens as token_box  # noqa: E402
import users_repository as repo  # noqa: E402

SENT = []
USERS = {}
TOKENS = {}
NEXT_ID = {"v": 1}


def _row(uid):
    u = USERS[uid]
    return dict(u)


# ---- simulacion del repositorio -------------------------------------
def fake_email_taken(email):
    return any(u["email"].lower() == email.lower() for u in USERS.values())


def fake_create_user(first, paternal, maternal, full_name, email, password_hash):
    uid = NEXT_ID["v"]
    NEXT_ID["v"] += 1
    now = datetime.now(timezone.utc)
    USERS[uid] = {"id": uid, "first_name": first, "last_name_paternal": paternal,
                  "last_name_maternal": maternal or None, "full_name": full_name,
                  "email": email, "role": "user", "email_verified": False,
                  "is_active": True, "created_at": now, "updated_at": now,
                  "last_login_at": None, "password_hash": password_hash}
    return _row(uid)


def fake_status(email):
    for u in USERS.values():
        if u["email"].lower() == email.lower():
            return {"registered": True, "verified": u["email_verified"],
                    "active": u["is_active"], "previouslyVerified": u["email_verified"]}
    return {"registered": False, "verified": False, "active": False,
            "previouslyVerified": False}


def fake_create_token(user_id, token_hash, expires_at):
    TOKENS[token_hash] = {"user_id": user_id, "expires_at": expires_at, "used": False}


def fake_consume(token_hash):
    t = TOKENS.get(token_hash)
    now = datetime.now(timezone.utc)
    if t is None or t["used"] or t["expires_at"] <= now:
        return None
    t["used"] = True
    USERS[t["user_id"]]["email_verified"] = True
    return _row(t["user_id"])


def fake_token_state(token_hash):
    t = TOKENS.get(token_hash)
    if t is None:
        return None
    return {"used_at": datetime.now(timezone.utc) if t["used"] else None,
            "expires_at": t["expires_at"]}


def fake_get_by_email(email):
    for u in USERS.values():
        if u["email"].lower() == email.lower():
            return dict(u)
    return None


def fake_get_by_id(uid):
    return dict(USERS[uid]) if uid in USERS else None


def fake_send(to_email, full_name, verify_url):
    SENT.append({"to": to_email, "url": verify_url})
    return True


repo.email_taken = fake_email_taken
repo.create_user = fake_create_user
repo.verification_status = fake_status
repo.create_verification_token = fake_create_token
repo.consume_verification_token = fake_consume
repo.token_state = fake_token_state
repo.get_by_email = fake_get_by_email
repo.get_by_id = fake_get_by_id
repo.set_last_login = lambda uid: None
appmod.mail_sender.send_verification_email = fake_send
dbmod.ping = lambda: {"db": "library_db", "usr": "library_user",
                      "version": "PostgreSQL 16 on test"}

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


def body_text(resp):
    return resp.get_data(as_text=True)


print("1. Servicio y formatos")
r = client.get("/")
check("indice XML por omision", r.status_code == 200 and "<service" in body_text(r), body_text(r)[:120])
r = client.get("/?format=json")
check("indice JSON", r.status_code == 200 and r.get_json()["service"] == "library-login-service")
r = client.get("/health?format=json")
check("health ok", r.status_code == 200 and r.get_json()["status"] == "ok")

print("2. Validacion previa del correo")
r = client.get("/validate-email?email=no-es-correo&format=json")
check("sintaxis invalida", r.get_json()["valid"] is False)
r = client.get("/validate-email?email=ada@ejemplo.mx&format=json")
check("correo nuevo disponible", r.get_json()["available"] is True)
r = client.get("/validate-email?email=ada@ejemplo.mx")
check("validacion en XML", "<validation" in body_text(r))

print("3. Registro")
r = client.post("/register?format=json", json={"email": "x@y.zz"})
check("registro incompleto 400", r.status_code == 400)
r = client.post("/register?format=json", json={
    "nombre": "Ada", "apellidoPaterno": "Lovelace", "apellidoMaterno": "Byron",
    "email": "ada@ejemplo.mx", "password": "Secreto123"})
check("registro 201 JSON", r.status_code == 201 and r.get_json()["created"] is True, body_text(r)[:200])
check("correo enviado por sendmail (simulado)", len(SENT) == 1 and SENT[0]["to"] == "ada@ejemplo.mx")
check("hash bcrypt, no texto plano",
      USERS[1]["password_hash"] != "Secreto123" and USERS[1]["password_hash"].startswith("$2"))
check("nombre normalizado", USERS[1]["first_name"] == "Ada"
      and USERS[1]["last_name_paternal"] == "Lovelace"
      and USERS[1]["last_name_maternal"] == "Byron"
      and USERS[1]["full_name"] == "Ada Lovelace Byron")
r = client.post("/register", data="<register><nombre>B</nombre></register>",
                content_type="application/xml")
check("registro XML por omision responde XML", r.status_code in (201, 400)
      and "xml" in (r.content_type or ""), f"{r.status_code} {r.content_type}")
r = client.post("/register?format=json", json={
    "nombre": "Ada", "apellidoPaterno": "Lovelace", "email": "ada@ejemplo.mx",
    "password": "Secreto123"})
check("duplicado 409", r.status_code == 409 and "error" in r.get_json())
r = client.post("/register?format=json", json={
    "nombre": "Ada", "apellidoPaterno": "Lovelace", "email": "ADA@EJEMPLO.MX",
    "password": "Secreto123"})
check("unicidad insensible a mayusculas", r.status_code == 409)

print("4. Verificacion del correo")
token_url = SENT[0]["url"]
raw_token = token_url.split("token=")[1]
r = client.get(f"/verify?token={raw_token}&format=json")
check("token valido verifica", r.status_code == 200
      and r.get_json()["user"]["emailVerified"] is True, body_text(r)[:200])
r = client.get(f"/verify?token={raw_token}&format=json")
check("token reutilizado 410", r.status_code == 410)
r = client.get("/verify?token=inexistente&format=json")
check("token falso 404", r.status_code == 404)
raw2, digest2, _ = token_box.issue_token()
TOKENS[digest2] = {"user_id": 1,
                   "expires_at": datetime.now(timezone.utc) - timedelta(minutes=1),
                   "used": False}
r = client.get(f"/verify?token={raw2}&format=json")
check("token expirado 410", r.status_code == 410)
r = client.get("/verify?format=json")
check("token ausente 400", r.status_code == 400)
raw3, digest3, exp3 = token_box.issue_token()
TOKENS[digest3] = {"user_id": 1, "expires_at": exp3, "used": False}
r = client.post("/verify?format=json", json={"token": raw3})
check("verify por POST con JSON", r.status_code == 200
      and r.get_json()["verified"] is True)
def _race(*a):
    raise Exception('duplicate key value violates unique constraint "users_email_key"')
repo.create_user = _race
r = client.post("/register?format=json", json={
    "nombre": "Race", "apellidoPaterno": "Condicion", "email": "race@ejemplo.mx",
    "password": "Secreto123"})
check("carrera de duplicado 409", r.status_code == 409)
repo.create_user = fake_create_user

print("5. Login / sesion / logout")
client.post("/register?format=json", json={
    "nombre": "Sin", "apellidoPaterno": "Verificar", "email": "sin@ejemplo.mx",
    "password": "Secreto123"})
r = client.post("/login?format=json",
                json={"email": "sin@ejemplo.mx", "password": "Secreto123"})
check("sin verificar 403 email_not_verified",
      r.status_code == 403 and r.get_json()["error"]["code"] == "email_not_verified")
r = client.post("/login?format=json",
                json={"email": "ada@ejemplo.mx", "password": "OtraClave"})
check("clave mala 401", r.status_code == 401)
r = client.post("/login?format=json",
                json={"email": "nadie@ejemplo.mx", "password": "Secreto123"})
check("desconocido 401 sin enumerar", r.status_code == 401)
r = client.post("/login?format=json",
                json={"email": "ada@ejemplo.mx", "password": "Secreto123"})
check("login 200", r.status_code == 200 and r.get_json()["authenticated"] is True,
      body_text(r)[:200])
r = client.get("/session?format=json")
check("sesion autenticada", r.get_json().get("authenticated") is True
      and r.get_json()["user"]["email"] == "ada@ejemplo.mx", body_text(r)[:200])
r = client.get("/session")
check("sesion en XML por omision", "<session" in body_text(r))
anon = appmod.app.test_client()
r = anon.get("/session?format=json")
check("sin cookie no autenticado", r.status_code == 200
      and r.get_json()["authenticated"] is False)
r = client.post("/logout?format=json")
check("logout", r.get_json()["authenticated"] is False)
r = client.get("/session?format=json")
check("sesion cerrada", r.get_json()["authenticated"] is False)

print("6. Forma de los errores en XML")
r = client.post("/login", json={"email": "x", "password": "y"})
check("error XML con <error", r.status_code == 400 and "<error" in body_text(r))

print("7. Caida de la base")


def _boom():
    raise Exception("caida simulada")


dbmod.ping = _boom
r = client.get("/health?format=json")
check("health 503 sin PG", r.status_code == 503 and r.get_json()["status"] == "error")

print(f"\nResultado: {PASSED} OK, {FAILED} fallos")
sys.exit(1 if FAILED else 0)
