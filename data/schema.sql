-- =====================================================================
-- library/db/schema.sql
-- Base de datos: library_db (PostgreSQL)
-- Arquitectura: Monolítica / MVC / Organización por módulos
--
-- Dependencias funcionales identificadas:
--   ISBN -> título, año_publicación, precio, stock, formato_id, categoria_id
--   autor_id -> nombre_autor
--   genero_id -> nombre_genero
--   concepto_id -> nombre_concepto
--   (libro_id, concepto_id) -> definición   (dependencia FD sobre clave compuesta)
--   usuario_id -> nombre, email, password_hash, rol
--
-- Dependencias multivaluadas (MVD) -> requieren tablas independientes en 4FN:
--   libro ->> autor            (un libro, muchos autores)
--   libro ->> genero           (un libro, muchos géneros)
--   libro ->> imagen           (un libro, muchas imágenes)
--   libro ->> (concepto, definición)  (un libro define muchos conceptos,
--                                       cada par libro-concepto tiene su propia definición)
--
-- Formato y categoría son catálogos independientes (1:N hacia libro, sin MVD entre sí).
-- =====================================================================

CREATE SCHEMA IF NOT EXISTS library;
SET search_path TO library;

CREATE EXTENSION IF NOT EXISTS pgcrypto; -- para gen_random_uuid() si se requiere

-- ---------------------------------------------------------------------
-- ENUMS
-- ---------------------------------------------------------------------
CREATE TYPE user_role AS ENUM ('admin', 'user');

-- ---------------------------------------------------------------------
-- MÓDULO: USUARIOS
-- ---------------------------------------------------------------------
CREATE TABLE users (
    id              SERIAL PRIMARY KEY,
    full_name       VARCHAR(150)    NOT NULL,
    email           VARCHAR(150)    NOT NULL UNIQUE,
    password_hash   VARCHAR(255)    NOT NULL,
    role            user_role       NOT NULL DEFAULT 'user',
    is_active       BOOLEAN         NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ     NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ     NOT NULL DEFAULT now()
);

-- Regla de negocio: máximo un administrador en todo el sistema.
CREATE UNIQUE INDEX ux_users_single_admin
    ON users ((role))
    WHERE role = 'admin';

-- ---------------------------------------------------------------------
-- MÓDULO: CATÁLOGOS INDEPENDIENTES (formato / categoría)
-- ---------------------------------------------------------------------
CREATE TABLE formats (
    id      SERIAL PRIMARY KEY,
    name    VARCHAR(50) NOT NULL UNIQUE   -- Ej: Físico, Digital, Audiolibro
);

CREATE TABLE categories (
    id      SERIAL PRIMARY KEY,
    name    VARCHAR(80) NOT NULL UNIQUE   -- Ej: Ficción, Técnico, Infantil
);

-- ---------------------------------------------------------------------
-- MÓDULO: LIBROS
-- ---------------------------------------------------------------------
CREATE TABLE books (
    id                  SERIAL PRIMARY KEY,
    isbn                VARCHAR(20)     NOT NULL UNIQUE,
    title               VARCHAR(255)    NOT NULL,
    publication_year    SMALLINT        NOT NULL CHECK (publication_year > 0),
    price               NUMERIC(10,2)   NOT NULL CHECK (price >= 0),
    stock               INTEGER         NOT NULL DEFAULT 0 CHECK (stock >= 0),
    format_id           INTEGER         NOT NULL REFERENCES formats(id)    ON UPDATE CASCADE ON DELETE RESTRICT,
    category_id         INTEGER         NOT NULL REFERENCES categories(id) ON UPDATE CASCADE ON DELETE RESTRICT,
    created_at          TIMESTAMPTZ     NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ     NOT NULL DEFAULT now()
);

CREATE INDEX ix_books_title ON books (title);

-- ---------------------------------------------------------------------
-- MÓDULO: AUTORES (M:N con libros)
-- ---------------------------------------------------------------------
CREATE TABLE authors (
    id      SERIAL PRIMARY KEY,
    name    VARCHAR(150) NOT NULL UNIQUE
);

CREATE TABLE book_authors (
    book_id     INTEGER NOT NULL REFERENCES books(id)   ON DELETE CASCADE,
    author_id   INTEGER NOT NULL REFERENCES authors(id) ON DELETE CASCADE,
    PRIMARY KEY (book_id, author_id)
);

-- ---------------------------------------------------------------------
-- MÓDULO: GÉNEROS (M:N con libros)
-- ---------------------------------------------------------------------
CREATE TABLE genres (
    id      SERIAL PRIMARY KEY,
    name    VARCHAR(80) NOT NULL UNIQUE
);

CREATE TABLE book_genres (
    book_id     INTEGER NOT NULL REFERENCES books(id)  ON DELETE CASCADE,
    genre_id    INTEGER NOT NULL REFERENCES genres(id) ON DELETE CASCADE,
    PRIMARY KEY (book_id, genre_id)
);

-- ---------------------------------------------------------------------
-- MÓDULO: CONCEPTOS (M:N con libros + atributo definición por par)
-- ---------------------------------------------------------------------
CREATE TABLE concepts (
    id      SERIAL PRIMARY KEY,
    name    VARCHAR(150) NOT NULL UNIQUE
);

CREATE TABLE book_concepts (
    book_id     INTEGER         NOT NULL REFERENCES books(id)    ON DELETE CASCADE,
    concept_id  INTEGER         NOT NULL REFERENCES concepts(id) ON DELETE CASCADE,
    definition  TEXT            NOT NULL,
    PRIMARY KEY (book_id, concept_id)
);

-- ---------------------------------------------------------------------
-- MÓDULO: IMÁGENES (1:N con libros)
-- ---------------------------------------------------------------------
CREATE TABLE book_images (
    id          SERIAL PRIMARY KEY,
    book_id     INTEGER         NOT NULL REFERENCES books(id) ON DELETE CASCADE,
    url         VARCHAR(500)    NOT NULL,
    is_cover    BOOLEAN         NOT NULL DEFAULT FALSE,
    created_at  TIMESTAMPTZ     NOT NULL DEFAULT now()
);

-- Máximo una portada (is_cover = true) por libro.
CREATE UNIQUE INDEX ux_book_images_one_cover
    ON book_images (book_id)
    WHERE is_cover = TRUE;

-- ---------------------------------------------------------------------
-- TRIGGERS: updated_at automático
-- ---------------------------------------------------------------------
CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_books_updated_at
    BEFORE UPDATE ON books
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER trg_users_updated_at
    BEFORE UPDATE ON users
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();
