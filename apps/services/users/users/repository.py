"""
apps/services/users/users/repository.py
Todo el SQL del microservicio de usuarios.

PostgreSQL es la fuente principal: cuentas (library.users), catalogo de
roles (library.roles) y permisos por rol (library.role_permissions, ver
data/roles_migration.sql).

Reglas que se respetan aqui
  * password_hash vive en la propia cuenta; no hay tabla de contrasenas
    y nunca se devuelve en una respuesta.
  * Los nombres viven normalizados (first_name, last_name_paternal,
    last_name_maternal); full_name lo sincroniza un disparador para no
    romper el monolito.
  * role y role_id se sincronizan entre si por disparador: basta escribir
    role_id.
  * La baja de una cuenta es LOGICA (is_active = false). No se borra:
    library.orders la referencia con ON DELETE RESTRICT y un pedido
    historico no puede quedarse sin dueno.
  * Todas las consultas usan parametros (%s). Nunca se concatena un valor
    del usuario dentro del SQL.
"""
from .shared import database

PUBLIC_COLUMNS = (
    "u.id, u.first_name, u.last_name_paternal, u.last_name_maternal, "
    "u.full_name, u.email, u.role, u.role_id, u.email_verified, u.is_active, "
    "u.created_at, u.updated_at, u.last_login_at"
)

# Campos por los que se puede ordenar un listado. Es una LISTA BLANCA: el
# nombre de una columna no puede ir como parametro, de modo que la unica
# forma segura de admitir ?sort= es comprobarlo contra este conjunto.
SORTABLE = {"id": "u.id", "email": "u.email", "name": "u.full_name",
            "role": "u.role_id", "created": "u.created_at",
            "lastLogin": "u.last_login_at"}


def public_user(row):
    """Fila de users -> diccionario JSON en camelCase, SIN password_hash."""
    if row is None:
        return None
    return {
        "id": row["id"],
        "nombre": row.get("first_name"),
        "apellidoPaterno": row.get("last_name_paternal"),
        "apellidoMaterno": row.get("last_name_maternal"),
        "fullName": row.get("full_name"),
        "email": row["email"],
        "role": row.get("role"),
        "roleId": row.get("role_id"),
        "emailVerified": bool(row.get("email_verified")),
        "isActive": bool(row.get("is_active", True)),
        "createdAt": row.get("created_at").isoformat() if row.get("created_at") else None,
        "updatedAt": row.get("updated_at").isoformat() if row.get("updated_at") else None,
        "lastLoginAt": row.get("last_login_at").isoformat() if row.get("last_login_at") else None,
    }


# ---------------------------------------------------------------------
# Lectura de cuentas
# ---------------------------------------------------------------------
def get_by_id(user_id):
    with database.cursor() as cur:
        cur.execute(f"SELECT {PUBLIC_COLUMNS} FROM users u WHERE u.id = %s", (user_id,))
        return cur.fetchone()


def get_by_email(email):
    with database.cursor() as cur:
        cur.execute(f"SELECT {PUBLIC_COLUMNS} FROM users u "
                    "WHERE lower(u.email) = lower(%s)", (email,))
        return cur.fetchone()


def get_credentials(user_id):
    """Solo para comprobar la contrasena actual antes de cambiarla."""
    with database.cursor() as cur:
        cur.execute("SELECT id, password_hash FROM users WHERE id = %s", (user_id,))
        return cur.fetchone()


def email_taken(email, exclude_id=None):
    with database.cursor() as cur:
        if exclude_id is None:
            cur.execute("SELECT 1 FROM users WHERE lower(email) = lower(%s)", (email,))
        else:
            cur.execute("SELECT 1 FROM users WHERE lower(email) = lower(%s) AND id <> %s",
                        (email, exclude_id))
        return cur.fetchone() is not None


def list_users(filters, sort="id", order="asc", limit=50, offset=0):
    """
    Listado administrativo con filtros, orden y paginacion.

    Devuelve (filas, total). El total se calcula con los mismos filtros
    pero sin paginar, para que el cliente pueda paginar de verdad.
    """
    where = []
    params = []

    if filters.get("q"):
        where.append("(u.full_name ILIKE %s OR u.email ILIKE %s)")
        patron = f"%{filters['q']}%"
        params.extend([patron, patron])
    if filters.get("email"):
        where.append("u.email ILIKE %s")
        params.append(f"%{filters['email']}%")
    if filters.get("role"):
        # Admite el nombre del rol o su id.
        where.append("(u.role::text = %s OR u.role_id::text = %s)")
        params.extend([filters["role"], filters["role"]])
    if filters.get("active") is not None:
        where.append("u.is_active = %s")
        params.append(filters["active"])
    if filters.get("verified") is not None:
        where.append("u.email_verified = %s")
        params.append(filters["verified"])

    clause = (" WHERE " + " AND ".join(where)) if where else ""
    column = SORTABLE.get(sort, "u.id")
    direction = "DESC" if str(order).lower() == "desc" else "ASC"

    with database.cursor() as cur:
        cur.execute(f"SELECT count(*) AS total FROM users u{clause}", params)
        total = cur.fetchone()["total"]
        cur.execute(
            f"SELECT {PUBLIC_COLUMNS} FROM users u{clause} "
            f"ORDER BY {column} {direction}, u.id ASC LIMIT %s OFFSET %s",
            params + [limit, offset])
        return cur.fetchall(), total


# ---------------------------------------------------------------------
# Escritura de cuentas
# ---------------------------------------------------------------------
def create_user(*, first, paternal, maternal, full_name, email, password_hash,
                role_id=2, email_verified=False, is_active=True):
    """
    Alta administrativa. role y role_id los sincroniza el disparador
    trg_users_sync_role, de modo que basta con escribir role_id.
    """
    with database.cursor(commit=True) as cur:
        cur.execute(
            "INSERT INTO users (first_name, last_name_paternal, last_name_maternal, "
            "full_name, email, password_hash, role_id, email_verified, is_active) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id",
            (first, paternal, maternal or None, full_name, email, password_hash,
             role_id, email_verified, is_active))
        new_id = cur.fetchone()["id"]
    return get_by_id(new_id)


def update_user(user_id, changes):
    """
    Actualiza solo los campos presentes en `changes`.

    Las claves se traducen a columnas por una LISTA BLANCA: nada que
    venga del cliente llega a formar parte del SQL.
    """
    columns = {
        "first": "first_name",
        "paternal": "last_name_paternal",
        "maternal": "last_name_maternal",
        "full_name": "full_name",
        "email": "email",
        "password_hash": "password_hash",
        "role_id": "role_id",
        "email_verified": "email_verified",
        "is_active": "is_active",
    }
    sets = []
    params = []
    for key, value in changes.items():
        column = columns.get(key)
        if column is None:
            continue
        sets.append(f"{column} = %s")
        params.append(value)
    if not sets:
        return get_by_id(user_id)

    with database.cursor(commit=True) as cur:
        cur.execute(f"UPDATE users SET {', '.join(sets)} WHERE id = %s RETURNING id",
                    params + [user_id])
        if cur.fetchone() is None:
            return None
    return get_by_id(user_id)


def set_active(user_id, active):
    """Baja/alta LOGICA de la cuenta."""
    return update_user(user_id, {"is_active": bool(active)})


def count_active_admins(exclude_id=None):
    """
    Cuantos administradores activos quedan.

    Se consulta antes de desactivar a un admin o de quitarle el rol: el
    sistema puede tener varios administradores, pero no puede quedarse
    sin ninguno.
    """
    with database.cursor() as cur:
        if exclude_id is None:
            cur.execute("SELECT count(*) AS n FROM users u JOIN roles r ON r.id = u.role_id "
                        "WHERE r.name = 'admin' AND u.is_active")
        else:
            cur.execute("SELECT count(*) AS n FROM users u JOIN roles r ON r.id = u.role_id "
                        "WHERE r.name = 'admin' AND u.is_active AND u.id <> %s",
                        (exclude_id,))
        return cur.fetchone()["n"]


# ---------------------------------------------------------------------
# Roles y permisos
# ---------------------------------------------------------------------
def list_roles():
    with database.cursor() as cur:
        cur.execute(
            "SELECT r.id, r.name, r.description, r.is_admin, "
            "       coalesce(array_agg(rp.permission ORDER BY rp.permission) "
            "                FILTER (WHERE rp.permission IS NOT NULL), '{}') AS permissions, "
            "       (SELECT count(*) FROM users u WHERE u.role_id = r.id) AS user_count "
            "  FROM roles r LEFT JOIN role_permissions rp ON rp.role_id = r.id "
            " GROUP BY r.id, r.name, r.description, r.is_admin ORDER BY r.id")
        return cur.fetchall()


def get_role(role_id):
    with database.cursor() as cur:
        cur.execute(
            "SELECT r.id, r.name, r.description, r.is_admin, "
            "       coalesce(array_agg(rp.permission ORDER BY rp.permission) "
            "                FILTER (WHERE rp.permission IS NOT NULL), '{}') AS permissions, "
            "       (SELECT count(*) FROM users u WHERE u.role_id = r.id) AS user_count "
            "  FROM roles r LEFT JOIN role_permissions rp ON rp.role_id = r.id "
            " WHERE r.id = %s GROUP BY r.id, r.name, r.description, r.is_admin",
            (role_id,))
        return cur.fetchone()


def get_role_by_name(name):
    with database.cursor() as cur:
        cur.execute("SELECT id, name, description, is_admin FROM roles "
                    "WHERE lower(name) = lower(%s)", (name,))
        return cur.fetchone()


def create_role(name, description="", is_admin=False):
    with database.cursor(commit=True) as cur:
        cur.execute("INSERT INTO roles (name, description, is_admin) "
                    "VALUES (%s, %s, %s) RETURNING id",
                    (name, description, is_admin))
        return cur.fetchone()["id"]


def set_role_permissions(role_id, permissions):
    """
    Reemplaza la lista de permisos del rol (borra las que no vienen,
    inserta las nuevas) en UNA transaccion.
    """
    with database.cursor(commit=True) as cur:
        cur.execute("DELETE FROM role_permissions WHERE role_id = %s", (role_id,))
        for permission in sorted(set(permissions)):
            cur.execute("INSERT INTO role_permissions (role_id, permission) "
                        "VALUES (%s, %s) ON CONFLICT DO NOTHING",
                        (role_id, permission))


def role_to_dict(row):
    if row is None:
        return None
    return {
        "id": row["id"],
        "name": row["name"],
        "description": row.get("description") or "",
        "isAdmin": bool(row.get("is_admin")),
        "permissions": list(row.get("permissions") or []),
        "userCount": row.get("user_count"),
    }
