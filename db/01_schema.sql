-- =====================================================================
-- db/01_schema.sql
-- ESTRUCTURA (DDL) de la base de datos library_db.
--
-- Contiene UNICAMENTE tablas, tipos, restricciones e indices. Los demas
-- objetos viven en archivos propios para poder recrearlos por separado:
--
--   db/02_seed_30_per_table.sql   datos
--   db/04_stored_procedures.sql   funciones y procedimientos
--   db/05_triggers.sql            disparadores
--   db/06_views.sql               vistas
--
-- Requisito previo: db/00_create_database.sql (rol, base y extensiones).
--
-- ---------------------------------------------------------------------
-- DEPENDENCIAS FUNCIONALES (FD)
--   ISBN        -> titulo, ano_publicacion, precio, stock, formato, categoria
--   autor_id    -> nombre_autor
--   genero_id   -> nombre_genero
--   concepto_id -> nombre_concepto
--   usuario_id  -> nombre, email, password_hash, rol
--   (libro_id, concepto_id) -> definicion      <- FD sobre CLAVE COMPUESTA
--
-- DEPENDENCIAS MULTIVALUADAS (MVD) -> tabla propia cada una (4FN)
--   libro ->> autor       (book_authors)
--   libro ->> genero      (book_genres)
--   libro ->> imagen      (book_images)
--
-- El caso (libro, concepto) -> definicion NO es una MVD pura: la
-- definicion depende de la clave compuesta completa. Por eso vive como
-- atributo de la tabla de union y no en la tabla concepts.
--
-- ---------------------------------------------------------------------
-- Todas las referencias van calificadas con "library." para no depender
-- del search_path: consolas que abren una sesion por sentencia y pooler
-- en modo transaction pooling pierden un SET suelto.
-- =====================================================================

CREATE SCHEMA IF NOT EXISTS library;
SET search_path TO library, public;   -- comodidad en psql; redundante por lo anterior


-- =====================================================================
-- TIPOS
-- =====================================================================
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type t
                     JOIN pg_namespace n ON n.oid = t.typnamespace
                    WHERE t.typname = 'user_role' AND n.nspname = 'library') THEN
        CREATE TYPE library.user_role AS ENUM ('admin', 'user');
    END IF;
END
$$;


-- =====================================================================
-- MODULO: USUARIOS
-- =====================================================================
CREATE TABLE IF NOT EXISTS library.users (
    id              SERIAL PRIMARY KEY,
    full_name       VARCHAR(150)       NOT NULL,
    email           VARCHAR(150)       NOT NULL UNIQUE,
    password_hash   VARCHAR(255)       NOT NULL,
    role            library.user_role  NOT NULL DEFAULT 'user',
    is_active       BOOLEAN            NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ        NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ        NOT NULL DEFAULT now()
);

-- Regla de negocio: COMO MAXIMO UN ADMINISTRADOR en todo el sistema.
-- Es una restriccion condicional: UNIQUE normal no la expresa. El indice
-- unico parcial la hace imposible de violar, incluso con dos peticiones
-- concurrentes, cosa que una comprobacion en el controlador no logra.
CREATE UNIQUE INDEX IF NOT EXISTS ux_users_single_admin
    ON library.users ((role))
    WHERE role = 'admin';

CREATE INDEX IF NOT EXISTS ix_users_email ON library.users (email);


-- =====================================================================
-- MODULO: CATALOGOS INDEPENDIENTES (1:N hacia libro)
-- =====================================================================
CREATE TABLE IF NOT EXISTS library.formats (
    id      SERIAL PRIMARY KEY,
    name    VARCHAR(50) NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS library.categories (
    id      SERIAL PRIMARY KEY,
    name    VARCHAR(80) NOT NULL UNIQUE
);


-- =====================================================================
-- MODULO: LIBROS  (entidad central)
-- =====================================================================
CREATE TABLE IF NOT EXISTS library.books (
    id                  SERIAL PRIMARY KEY,
    isbn                VARCHAR(20)     NOT NULL UNIQUE,
    title               VARCHAR(255)    NOT NULL,
    publication_year    SMALLINT        NOT NULL CHECK (publication_year > 0),
    price               NUMERIC(10,2)   NOT NULL CHECK (price >= 0),
    stock               INTEGER         NOT NULL DEFAULT 0 CHECK (stock >= 0),
    format_id           INTEGER         NOT NULL REFERENCES library.formats(id)
                                        ON UPDATE CASCADE ON DELETE RESTRICT,
    category_id         INTEGER         NOT NULL REFERENCES library.categories(id)
                                        ON UPDATE CASCADE ON DELETE RESTRICT,
    created_at          TIMESTAMPTZ     NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ     NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_books_title       ON library.books (title);
CREATE INDEX IF NOT EXISTS ix_books_format      ON library.books (format_id);
CREATE INDEX IF NOT EXISTS ix_books_category    ON library.books (category_id);
CREATE INDEX IF NOT EXISTS ix_books_created_at  ON library.books (created_at DESC, id DESC);


-- =====================================================================
-- MVD: libro ->> autor
-- =====================================================================
CREATE TABLE IF NOT EXISTS library.authors (
    id      SERIAL PRIMARY KEY,
    name    VARCHAR(150) NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS library.book_authors (
    book_id     INTEGER NOT NULL REFERENCES library.books(id)   ON DELETE CASCADE,
    author_id   INTEGER NOT NULL REFERENCES library.authors(id) ON DELETE CASCADE,
    PRIMARY KEY (book_id, author_id)
);

CREATE INDEX IF NOT EXISTS ix_book_authors_author ON library.book_authors (author_id);


-- =====================================================================
-- MVD: libro ->> genero
-- =====================================================================
CREATE TABLE IF NOT EXISTS library.genres (
    id      SERIAL PRIMARY KEY,
    name    VARCHAR(80) NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS library.book_genres (
    book_id     INTEGER NOT NULL REFERENCES library.books(id)  ON DELETE CASCADE,
    genre_id    INTEGER NOT NULL REFERENCES library.genres(id) ON DELETE CASCADE,
    PRIMARY KEY (book_id, genre_id)
);

CREATE INDEX IF NOT EXISTS ix_book_genres_genre ON library.book_genres (genre_id);


-- =====================================================================
-- FD sobre clave compuesta: (libro, concepto) -> definicion
--
-- El nombre del concepto es unico y vive en concepts; la DEFINICION es
-- distinta en cada libro que lo explica y por eso es un atributo de la
-- tabla de union, no de concepts. Colocarla en concepts seria un error
-- de 2FN y haria imposible representar los datos reales.
-- =====================================================================
CREATE TABLE IF NOT EXISTS library.concepts (
    id      SERIAL PRIMARY KEY,
    name    VARCHAR(150) NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS library.book_concepts (
    book_id     INTEGER NOT NULL REFERENCES library.books(id)    ON DELETE CASCADE,
    concept_id  INTEGER NOT NULL REFERENCES library.concepts(id) ON DELETE CASCADE,
    definition  TEXT    NOT NULL CHECK (length(btrim(definition)) > 0),
    PRIMARY KEY (book_id, concept_id)
);

CREATE INDEX IF NOT EXISTS ix_book_concepts_concept ON library.book_concepts (concept_id);


-- =====================================================================
-- MVD: libro ->> imagen
-- =====================================================================
CREATE TABLE IF NOT EXISTS library.book_images (
    id          SERIAL PRIMARY KEY,
    book_id     INTEGER         NOT NULL REFERENCES library.books(id) ON DELETE CASCADE,
    url         VARCHAR(500)    NOT NULL,
    is_cover    BOOLEAN         NOT NULL DEFAULT FALSE,
    created_at  TIMESTAMPTZ     NOT NULL DEFAULT now()
);

-- Segunda restriccion condicional: COMO MAXIMO UNA PORTADA por libro.
CREATE UNIQUE INDEX IF NOT EXISTS ux_book_images_one_cover
    ON library.book_images (book_id)
    WHERE is_cover = TRUE;

CREATE INDEX IF NOT EXISTS ix_book_images_book ON library.book_images (book_id);


-- =====================================================================
-- BITACORA DE CAMBIOS
-- La escribe el disparador trg_books_audit (db/05_triggers.sql). Se
-- declara aqui porque es estructura; el disparador que la alimenta es
-- comportamiento y vive en su propio archivo.
-- =====================================================================
CREATE TABLE IF NOT EXISTS library.audit_log (
    id          BIGSERIAL PRIMARY KEY,
    table_name  VARCHAR(60)  NOT NULL,
    operation   VARCHAR(10)  NOT NULL CHECK (operation IN ('INSERT','UPDATE','DELETE')),
    record_id   INTEGER,
    changed_by  TEXT         NOT NULL DEFAULT current_user,
    changed_at  TIMESTAMPTZ  NOT NULL DEFAULT now(),
    details     TEXT
);

CREATE INDEX IF NOT EXISTS ix_audit_log_table ON library.audit_log (table_name, changed_at DESC);
