"""
apps/services/login/login/security.py
Hash seguro de contrasenas con bcrypt.

Se usa bcrypt (y no otro esquema) para seguir siendo compatible con los
hashes bcryptjs que ya guarda el monolito en users.password_hash: cualquier
hash que empiece por $2a$/$2b$ se verifica igual, venga del monolito o de
este microservicio. La contrasena en claro nunca se almacena.
"""
import bcrypt

import config


def hash_password(plain):
    rounds = max(4, min(int(config.BCRYPT_ROUNDS), 31))
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt(rounds=rounds)).decode("utf-8")


def verify_password(plain, stored_hash):
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), stored_hash.encode("utf-8"))
    except (ValueError, TypeError):
        return False
