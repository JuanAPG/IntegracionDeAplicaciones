-- =====================================================================
-- data/roles_migration.sql
-- MIGRACION del catalogo de ROLES y PERMISOS.
-- data/schema.sql queda intacto: una migracion por archivo, junto al
-- esquema inicial (misma convencion que data/login_migration.sql).
--
-- POR QUE
--   El JWT debe llevar user_id y role_id, y las operaciones
--   administrativas deben comprobar que el usuario tenga un rol
--   autorizado. Hasta ahora el rol era un ENUM ('admin','user') en la
--   propia cuenta: no habia role_id al que apuntar ni forma de decir
--   QUE puede hacer cada rol.
--
-- DISENO
--   * library.roles           catalogo de roles (1 admin, 2 user, 3 staff)
--   * library.role_permissions  rol ->> permiso es una dependencia
--     MULTIVALUADA (un rol tiene muchos permisos, un permiso lo tienen
--     muchos roles): en 4FN va en su propia tabla, igual que
--     book_authors o book_genres. NO se guarda como lista en una columna.
--   * users.role_id FK -> roles(id). La columna ENUM `role` SE CONSERVA
--     y se sincroniza por disparador en ambos sentidos, exactamente como
--     se hizo con full_name en login_migration.sql, para no romper el
--     monolito ni los procedimientos que escriben `role`.
--   * Se ELIMINA ux_users_single_admin: con un catalogo de roles
--     administrable, la regla "un solo administrador" impedia que el
--     microservicio de usuarios hiciera su trabajo.
--
-- Aplicacion en la instancia (idempotente, puede correrse dos veces):
--   psql -U library_user -d library_db -f data/roles_migration.sql
-- =====================================================================

SET search_path TO library, public;

-- ---------------------------------------------------------------------
-- 0. El ENUM aprende el rol nuevo
-- ---------------------------------------------------------------------
-- `role` sigue siendo ENUM por compatibilidad; para que pueda reflejar
-- un rol intermedio hay que anadir la etiqueta. ADD VALUE IF NOT EXISTS
-- hace la sentencia repetible.
ALTER TYPE library.user_role ADD VALUE IF NOT EXISTS 'staff';

-- ---------------------------------------------------------------------
-- 1. Catalogo de roles
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS library.roles (
    id          SERIAL PRIMARY KEY,
    name        VARCHAR(40)  NOT NULL UNIQUE,
    description VARCHAR(200) NOT NULL DEFAULT '',
    -- Marca de conveniencia para los informes; la autorizacion real se
    -- decide por los permisos de role_permissions, no por este campo.
    is_admin    BOOLEAN      NOT NULL DEFAULT FALSE,
    created_at  TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ  NOT NULL DEFAULT now()
);

-- Los ids son fijos y conocidos: el JWT los transporta en role_id y los
-- seis microservicios los interpretan igual.
INSERT INTO library.roles (id, name, description, is_admin) VALUES
    (1, 'admin', 'Administrador: acceso total a los seis microservicios', TRUE),
    (2, 'user',  'Cliente: opera unicamente sobre sus propios pedidos y pagos', FALSE),
    (3, 'staff', 'Personal de la libreria: catalogo, pedidos y pagos, sin administrar cuentas', TRUE)
ON CONFLICT (id) DO UPDATE
    SET name = EXCLUDED.name,
        description = EXCLUDED.description,
        is_admin = EXCLUDED.is_admin,
        updated_at = now();

-- La secuencia debe quedar por encima de los ids sembrados a mano, o el
-- primer rol que cree el microservicio de usuarios choca con la PK.
SELECT setval(pg_get_serial_sequence('library.roles', 'id'),
              GREATEST((SELECT max(id) FROM library.roles), 1));

-- ---------------------------------------------------------------------
-- 2. Permisos por rol  (MVD rol ->> permiso, tabla propia en 4FN)
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS library.role_permissions (
    role_id     INTEGER     NOT NULL REFERENCES library.roles(id)
                            ON UPDATE CASCADE ON DELETE CASCADE,
    permission  VARCHAR(40) NOT NULL,
    granted_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (role_id, permission)
);

CREATE INDEX IF NOT EXISTS ix_role_permissions_permission
    ON library.role_permissions (permission);

-- Vocabulario de permisos (el mismo que declara
-- packages/library_common/library_common/roles.py):
--   users:read  users:write  users:roles
--   books:write
--   authors:write
--   orders:read  orders:write  orders:status
--   payments:read  payments:write
-- "*" es comodin y solo lo tiene admin.
--
-- El rol `user` NO aparece aqui a proposito: un cliente no necesita
-- ningun permiso especial para operar sobre LO SUYO. Cada servicio
-- compara el user_id del token con el dueno del recurso; los permisos
-- de esta tabla son exclusivamente para lo ADMINISTRATIVO (ver o tocar
-- lo de otros).
INSERT INTO library.role_permissions (role_id, permission) VALUES
    (1, '*'),
    (3, 'users:read'),
    (3, 'books:write'),
    (3, 'authors:write'),
    (3, 'orders:read'),
    (3, 'orders:write'),
    (3, 'orders:status'),
    (3, 'payments:read'),
    (3, 'payments:write')
ON CONFLICT (role_id, permission) DO NOTHING;

-- ---------------------------------------------------------------------
-- 3. users.role_id  +  sincronizacion con el ENUM `role`
-- ---------------------------------------------------------------------
ALTER TABLE library.users
    ADD COLUMN IF NOT EXISTS role_id INTEGER REFERENCES library.roles(id)
        ON UPDATE CASCADE ON DELETE RESTRICT;

-- Relleno a partir del ENUM que ya tenia cada cuenta.
UPDATE library.users AS u
   SET role_id = r.id
  FROM library.roles AS r
 WHERE r.name = u.role::text
   AND u.role_id IS NULL;

-- Cualquier cuenta sin rol reconocible queda como cliente.
UPDATE library.users SET role_id = 2 WHERE role_id IS NULL;

ALTER TABLE library.users
    ALTER COLUMN role_id SET NOT NULL,
    ALTER COLUMN role_id SET DEFAULT 2;

CREATE INDEX IF NOT EXISTS ix_users_role_id ON library.users (role_id);

-- Sincroniza role <-> role_id en AMBAS direcciones:
--   * si viene role_id (microservicios nuevos), se deriva el nombre;
--   * si viene solo role (monolito, sp_register_user), se deriva el id.
-- Si el rol existe en el catalogo pero NO como etiqueta del ENUM, se
-- respeta role_id y la columna ENUM se deja como estaba: el catalogo
-- puede crecer sin tener que alterar el tipo cada vez.
CREATE OR REPLACE FUNCTION library.trg_users_sync_role()
RETURNS TRIGGER AS $$
DECLARE
    v_name TEXT;
    v_id   INTEGER;
BEGIN
    IF NEW.role_id IS NOT NULL
       AND (TG_OP = 'INSERT' OR NEW.role_id IS DISTINCT FROM OLD.role_id) THEN
        SELECT name INTO v_name FROM library.roles WHERE id = NEW.role_id;
        IF v_name IS NULL THEN
            RAISE EXCEPTION 'El rol % no existe en library.roles', NEW.role_id;
        END IF;
        IF EXISTS (SELECT 1 FROM pg_enum e
                     JOIN pg_type t ON t.oid = e.enumtypid
                    WHERE t.typname = 'user_role' AND e.enumlabel = v_name) THEN
            NEW.role := v_name::library.user_role;
        END IF;
    ELSIF TG_OP = 'INSERT' OR NEW.role IS DISTINCT FROM OLD.role THEN
        SELECT id INTO v_id FROM library.roles WHERE name = NEW.role::text;
        IF v_id IS NOT NULL THEN
            NEW.role_id := v_id;
        END IF;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_users_sync_role ON library.users;
CREATE TRIGGER trg_users_sync_role
    BEFORE INSERT OR UPDATE OF role, role_id ON library.users
    FOR EACH ROW EXECUTE FUNCTION library.trg_users_sync_role();

-- ---------------------------------------------------------------------
-- 4. Fuera la regla de "un solo administrador"
-- ---------------------------------------------------------------------
-- El indice parcial ux_users_single_admin impedia que existiera un
-- segundo admin, de modo que el microservicio de usuarios no podia
-- administrar roles de verdad. La regla se retira a proposito.
DROP INDEX IF EXISTS library.ux_users_single_admin;

-- El disparador fn_protect_last_admin (db/05_triggers.sql) sigue
-- vigente si esta instalado: evita quedarse SIN ningun administrador,
-- que es la proteccion que de verdad importa.

-- ---------------------------------------------------------------------
-- 5. Vista de apoyo
-- ---------------------------------------------------------------------
CREATE OR REPLACE VIEW library.v_role_permissions AS
SELECT r.id            AS role_id,
       r.name          AS role_name,
       r.is_admin,
       count(rp.permission)                       AS permission_count,
       coalesce(array_agg(rp.permission ORDER BY rp.permission)
                FILTER (WHERE rp.permission IS NOT NULL), '{}') AS permissions
  FROM library.roles r
  LEFT JOIN library.role_permissions rp ON rp.role_id = r.id
 GROUP BY r.id, r.name, r.is_admin
 ORDER BY r.id;

-- ---------------------------------------------------------------------
-- 6. Comprobacion
-- ---------------------------------------------------------------------
--   SELECT * FROM library.v_role_permissions;
--   SELECT id, email, role, role_id FROM library.users ORDER BY id LIMIT 10;
