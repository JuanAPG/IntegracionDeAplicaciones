-- =====================================================================
-- data/login_migration.sql
-- MIGRACION del microservicio de autenticacion (apps/services/login).
-- data/schema.sql queda intacto: todos los cambios de esta entrega viven
-- aqui, junto al esquema inicial, una migracion por archivo.
--
-- Diseno (1FN/2FN: usuario_id -> nombre, apellido_paterno,
-- apellido_materno, email, password_hash, rol):
--   * El nombre deja de ser un campo libre (full_name) y pasa a tres
--     columnas atomicas. full_name SE CONSERVA y se sincroniza por
--     disparador para no romper el monolito ni los procedimientos que
--     escriben full_name (db/04_stored_procedures.sql).
--   * password_hash sigue en la propia cuenta: NO se duplica ni se crea
--     tabla de contrasenas.
--   * email_verified + email_verification_tokens: el token viaja por
--     sendmail local (nunca POP/IMAP); en la base solo vive su hash.
--   * verified_emails: registro INTERNO de correos ya verificados
--     previamente (evita revalidar y reenviar a quien ya se verifico).
--
-- Aplicacion en la instancia (idempotente, puede correrse dos veces):
--   psql -U library_user -d library_db -f data/login_migration.sql
-- =====================================================================

SET search_path TO library, public;

-- ---------------------------------------------------------------------
-- 1. Nombre normalizado + estado de verificacion en users
-- ---------------------------------------------------------------------
ALTER TABLE library.users
    ADD COLUMN IF NOT EXISTS first_name          VARCHAR(80),
    ADD COLUMN IF NOT EXISTS last_name_paternal  VARCHAR(80),
    ADD COLUMN IF NOT EXISTS last_name_maternal  VARCHAR(80),
    ADD COLUMN IF NOT EXISTS email_verified      BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS last_login_at       TIMESTAMPTZ;

-- Rellena las partes a partir del full_name existente (mejor esfuerzo):
-- primer token -> nombre, segundo -> apellido paterno, resto -> materno.
UPDATE library.users AS u
   SET first_name = s.p[1],
       last_name_paternal = s.p[2],
       last_name_maternal = NULLIF(array_to_string(s.p[3:array_length(s.p, 1)], ' '), '')
  FROM (SELECT id, regexp_split_to_array(btrim(full_name), '\s+') AS p
          FROM library.users) AS s
 WHERE u.id = s.id
   AND u.first_name IS NULL;

-- Sincroniza full_name <-> partes en ambas direcciones:
--   * si vienen partes (login), full_name se compone;
--   * si solo viene full_name (monolito, sp_register_user), se parte.
CREATE OR REPLACE FUNCTION library.trg_users_sync_names()
RETURNS TRIGGER AS $$
DECLARE
    v_parts TEXT[];
BEGIN
    IF NEW.first_name IS NOT NULL
       OR NEW.last_name_paternal IS NOT NULL
       OR NEW.last_name_maternal IS NOT NULL THEN
        NEW.full_name := NULLIF(concat_ws(' ',
            NULLIF(btrim(COALESCE(NEW.first_name, '')), ''),
            NULLIF(btrim(COALESCE(NEW.last_name_paternal, '')), ''),
            NULLIF(btrim(COALESCE(NEW.last_name_maternal, '')), '')), '');
    ELSIF NEW.full_name IS NOT NULL THEN
        v_parts := regexp_split_to_array(btrim(NEW.full_name), '\s+');
        NEW.first_name := v_parts[1];
        NEW.last_name_paternal := v_parts[2];
        NEW.last_name_maternal :=
            NULLIF(array_to_string(v_parts[3:array_length(v_parts, 1)], ' '), '');
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_users_sync_names ON library.users;
CREATE TRIGGER trg_users_sync_names
    BEFORE INSERT OR UPDATE OF first_name, last_name_paternal,
        last_name_maternal, full_name ON library.users
    FOR EACH ROW EXECUTE FUNCTION library.trg_users_sync_names();

-- ---------------------------------------------------------------------
-- 2. Tokens de verificacion (solo el hash; el claro solo viaja en el correo)
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS library.email_verification_tokens (
    id          BIGSERIAL PRIMARY KEY,
    user_id     INTEGER       NOT NULL REFERENCES library.users(id) ON DELETE CASCADE,
    token_hash  TEXT          NOT NULL UNIQUE,
    expires_at  TIMESTAMPTZ   NOT NULL,
    used_at     TIMESTAMPTZ,
    created_at  TIMESTAMPTZ   NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_evt_user
    ON library.email_verification_tokens (user_id);

-- ---------------------------------------------------------------------
-- 3. Registro interno de correos ya verificados previamente
-- ---------------------------------------------------------------------
-- El email se guarda en minusculas; el servicio siempre escribe y lee
-- con lower(), de modo que la PK basta sin depender de citext.
CREATE TABLE IF NOT EXISTS library.verified_emails (
    email       VARCHAR(150)  NOT NULL PRIMARY KEY,
    user_id     INTEGER       REFERENCES library.users(id) ON DELETE SET NULL,
    source      VARCHAR(20)   NOT NULL DEFAULT 'token'
                CHECK (source IN ('token', 'migration')),
    verified_at TIMESTAMPTZ   NOT NULL DEFAULT now()
);

-- Las cuentas que ya existian (admin, seed, monolito) se consideran
-- verificadas por el proceso confiable que las creo: asi el administrador
-- no queda bloqueado y el registro interno nace con ellas.
UPDATE library.users SET email_verified = TRUE WHERE email_verified = FALSE;

INSERT INTO library.verified_emails (email, user_id, source)
SELECT lower(email), id, 'migration' FROM library.users
ON CONFLICT (email) DO NOTHING;
