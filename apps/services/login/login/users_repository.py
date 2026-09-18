"""
apps/services/login/login/users_repository.py
Todo el SQL del microservicio: lectura, registro y verificacion.

La tabla users conserva password_hash en la propia cuenta (no hay tabla
de contrasenas). Los nombres viven normalizados en first_name,
last_name_paternal y last_name_maternal; full_name se mantiene
sincronizado por disparador para no romper el monolito (ver
data/login_migration.sql).
"""
import db

PUBLIC_COLUMNS = (
    "id, first_name, last_name_paternal, last_name_maternal, full_name, "
    "email, role, email_verified, is_active, created_at, updated_at, last_login_at"
)


def public_user(row):
    """Fila de users -> diccionario JSON en camelCase."""
    if row is None:
        return None
    return {
        "id": row["id"],
        "nombre": row.get("first_name"),
        "apellidoPaterno": row.get("last_name_paternal"),
        "apellidoMaterno": row.get("last_name_maternal"),
        "fullName": row.get("full_name"),
        "email": row["email"],
        "role": row["role"],
        "emailVerified": bool(row.get("email_verified")),
        "isActive": bool(row.get("is_active", True)),
        "createdAt": row.get("created_at").isoformat() if row.get("created_at") else None,
        "lastLoginAt": row.get("last_login_at").isoformat() if row.get("last_login_at") else None,
    }


def get_by_email(email):
    with db.cursor() as cur:
        cur.execute(
            f"SELECT {PUBLIC_COLUMNS}, password_hash FROM users "
            "WHERE lower(email) = lower(%s)",
            (email,))
        return cur.fetchone()


def get_by_id(user_id):
    with db.cursor() as cur:
        cur.execute(f"SELECT {PUBLIC_COLUMNS} FROM users WHERE id = %s", (user_id,))
        return cur.fetchone()


def email_taken(email):
    with db.cursor() as cur:
        cur.execute("SELECT 1 FROM users WHERE lower(email) = lower(%s)", (email,))
        return cur.fetchone() is not None


def create_user(first, paternal, maternal, full_name, email, password_hash):
    with db.cursor(commit=True) as cur:
        cur.execute(
            f"INSERT INTO users (first_name, last_name_paternal, last_name_maternal, "
            "full_name, email, password_hash, role, is_active) "
            "VALUES (%s, %s, %s, %s, %s, %s, 'user', TRUE) "
            f"RETURNING {PUBLIC_COLUMNS}",
            (first, paternal, maternal or None, full_name, email, password_hash))
        return cur.fetchone()


def set_last_login(user_id):
    with db.cursor(commit=True) as cur:
        cur.execute("UPDATE users SET last_login_at = now() WHERE id = %s", (user_id,))


def create_verification_token(user_id, token_hash, expires_at):
    with db.cursor(commit=True) as cur:
        cur.execute(
            "DELETE FROM email_verification_tokens "
            "WHERE user_id = %s AND used_at IS NULL",
            (user_id,))
        cur.execute(
            "INSERT INTO email_verification_tokens (user_id, token_hash, expires_at) "
            "VALUES (%s, %s, %s)",
            (user_id, token_hash, expires_at))


def consume_verification_token(token_hash):
    """
    Canjea un token: lo marca usado, activa email_verified y deja constancia
    en el registro interno de correos verificados. Devuelve la fila del
    usuario o None si el token no existe, expiro o ya se uso.
    """
    with db.cursor(commit=True) as cur:
        cur.execute(
            "UPDATE email_verification_tokens SET used_at = now() "
            "WHERE token_hash = %s AND used_at IS NULL AND expires_at > now() "
            "RETURNING user_id",
            (token_hash,))
        hit = cur.fetchone()
        if hit is None:
            return None
        cur.execute(
            f"UPDATE users SET email_verified = TRUE WHERE id = %s "
            f"RETURNING {PUBLIC_COLUMNS}",
            (hit["user_id"],))
        user = cur.fetchone()
        cur.execute(
            "INSERT INTO verified_emails (email, user_id, source) "
            "VALUES (lower(%s), %s, 'token') "
            "ON CONFLICT (email) DO UPDATE SET verified_at = now(), "
            "user_id = EXCLUDED.user_id",
            (user["email"], user["id"]))
        return user


def token_state(token_hash):
    """Distingue token inexistente / expirado / usado (mensajes precisos)."""
    with db.cursor() as cur:
        cur.execute(
            "SELECT used_at, expires_at FROM email_verification_tokens "
            "WHERE token_hash = %s",
            (token_hash,))
        return cur.fetchone()


def verification_status(email):
    """
    Validacion interna del correo: combina la cuenta (si existe) con el
    registro de correos ya verificados previamente.
    """
    with db.cursor() as cur:
        cur.execute(
            "SELECT id, email_verified, is_active FROM users "
            "WHERE lower(email) = lower(%s)",
            (email,))
        account = cur.fetchone()
        cur.execute("SELECT 1 FROM verified_emails WHERE email = lower(%s)", (email,))
        previously = cur.fetchone() is not None
    return {
        "registered": account is not None,
        "verified": bool(account and account["email_verified"]),
        "active": bool(account and account["is_active"]),
        "previouslyVerified": previously,
    }
