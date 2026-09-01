-- =====================================================================
-- db/00_create_database.sql
-- Creacion del rol, de la base de datos y de las extensiones.
--
-- ESTE ARCHIVO SE EJECUTA COMO SUPERUSUARIO Y FUERA DE library_db.
-- Es el unico de la serie que requiere privilegios de administrador del
-- servidor; el resto (01..06) los ejecuta ya library_user dentro de la
-- base recien creada.
--
--   psql -U postgres -f db/00_create_database.sql
--
-- CREATE DATABASE no puede ejecutarse dentro de una transaccion, de modo
-- que este archivo se mantiene deliberadamente separado del esquema.
-- Los bloques DO ... IF NOT EXISTS lo hacen repetible.
-- =====================================================================

-- ---------------------------------------------------------------------
-- 1. Rol de la aplicacion
--    La contrasena la fija el enunciado de la practica. En un despliegue
--    real debe venir de una variable de entorno y ser larga y aleatoria.
-- ---------------------------------------------------------------------
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'library_user') THEN
        CREATE ROLE library_user LOGIN PASSWORD '777';
        RAISE NOTICE 'Rol library_user creado.';
    ELSE
        RAISE NOTICE 'El rol library_user ya existe; no se modifica.';
    END IF;
END
$$;

-- ---------------------------------------------------------------------
-- 2. Base de datos
--    gexec ejecuta la sentencia generada solo si la base no existe.
--    Se usa este truco porque CREATE DATABASE no admite IF NOT EXISTS
--    ni puede ir dentro de un bloque DO.
-- ---------------------------------------------------------------------
SELECT 'CREATE DATABASE library_db OWNER library_user ENCODING ''UTF8'''
 WHERE NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = 'library_db')
\gexec

-- ---------------------------------------------------------------------
-- 3. Privilegios y extensiones dentro de library_db
--    CREATE EXTENSION exige superusuario, por eso vive aqui y no en
--    01_schema.sql: asi el archivo del esquema puede ejecutarlo el
--    propio library_user sin errores de permisos.
-- ---------------------------------------------------------------------
\connect library_db

GRANT CREATE, CONNECT ON DATABASE library_db TO library_user;

CREATE EXTENSION IF NOT EXISTS pgcrypto;   -- gen_random_uuid(), digest()
CREATE EXTENSION IF NOT EXISTS unaccent;   -- busqueda insensible a acentos (opcional)

-- ---------------------------------------------------------------------
-- 4. Nota sobre minimo privilegio
--    library_user es propietario del esquema, por lo que puede ejecutar
--    DROP TABLE. Para un despliegue expuesto a Internet, separar el rol
--    de migracion del rol de la aplicacion:
--
--      CREATE ROLE library_app LOGIN PASSWORD '<clave-larga>';
--      GRANT USAGE ON SCHEMA library TO library_app;
--      GRANT SELECT, INSERT, UPDATE, DELETE
--            ON ALL TABLES IN SCHEMA library TO library_app;
--      GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA library TO library_app;
--
--    y conectar la aplicacion con library_app, que no puede alterar la
--    estructura. Detalle completo en apps/SEGURIDAD.txt, punto 9.
-- ---------------------------------------------------------------------
