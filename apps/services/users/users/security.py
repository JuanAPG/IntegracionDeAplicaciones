"""
apps/services/users/users/security.py
Hash de contrasenas con bcrypt.

Se usa bcrypt, y no otro esquema, para que los hashes sean compatibles
con los que ya guardan el monolito (bcryptjs) y el microservicio de
login: cualquier hash que empiece por $2a$/$2b$ se verifica igual, lo
haya escrito quien lo haya escrito.

La contrasena en claro NUNCA se almacena ni se registra en el log.
"""
import bcrypt

from library_common import env

ROUNDS = env.get_int("BCRYPT_ROUNDS", 12)


def hash_password(plain):
    rounds = max(4, min(int(ROUNDS), 31))
    return bcrypt.hashpw(plain.encode("utf-8"),
                         bcrypt.gensalt(rounds=rounds)).decode("utf-8")


def verify_password(plain, stored_hash):
    try:
        return bcrypt.checkpw(plain.encode("utf-8"),
                              (stored_hash or "").encode("utf-8"))
    except (ValueError, TypeError):
        return False
