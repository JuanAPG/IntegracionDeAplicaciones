-- =====================================================================
-- db/04_stored_procedures.sql
-- FUNCIONES Y PROCEDIMIENTOS ALMACENADOS.
--
-- Requisito previo: db/01_schema.sql y db/06_views.sql
--   (fn_search_books devuelve SETOF library.v_books_catalog, de modo que
--    las vistas deben existir antes. Orden de carga usado por el
--    instalador: 01 -> 06 -> 04 -> 05 -> 02.)
--
-- ---------------------------------------------------------------------
-- CRITERIO: que se sube a la base de datos y que se queda en la aplicacion
--
-- Aqui viven solo las operaciones que tocan VARIAS TABLAS Y DEBEN SER
-- ATOMICAS. Antes estaban en la capa de modelo como transacciones de
-- JavaScript (db.transaction + varias consultas por viaje de red).
-- Moverlas a la base de datos consigue tres cosas:
--
--   1. La atomicidad la garantiza el motor, no el orden en que el codigo
--      recuerde llamar a BEGIN y COMMIT.
--   2. Un alta de libro con sus autores y generos pasa de N+3 viajes de
--      red a UNO solo.
--   3. La regla queda disponible para cualquier cliente de la base, no
--      solo para esta aplicacion.
--
-- Lo que NO se sube: la logica de presentacion, la validacion de formato
-- de los campos (que debe seguir ocurriendo en el servidor de aplicacion
-- para poder devolver mensajes al usuario) y el hash de contrasenas, que
-- se calcula con bcrypt en Node.
--
-- Todas las funciones son SECURITY INVOKER (el valor por defecto): se
-- ejecutan con los privilegios de quien llama, no con los del creador.
-- SECURITY DEFINER seria una escalada de privilegios innecesaria aqui.
-- =====================================================================

SET search_path TO library, public;


-- ---------------------------------------------------------------------
-- sp_replace_book_relations
-- Reescribe las relaciones multivaluadas de un libro. Auxiliar de las
-- dos funciones siguientes; no la llama la aplicacion directamente.
-- ---------------------------------------------------------------------
CREATE OR REPLACE FUNCTION library.sp_replace_book_relations(
    p_book_id    INTEGER,
    p_author_ids INTEGER[],
    p_genre_ids  INTEGER[]
) RETURNS VOID
LANGUAGE plpgsql AS $$
BEGIN
    DELETE FROM library.book_authors WHERE book_id = p_book_id;
    IF p_author_ids IS NOT NULL AND array_length(p_author_ids, 1) > 0 THEN
        INSERT INTO library.book_authors (book_id, author_id)
        SELECT DISTINCT p_book_id, a.author_id
          FROM unnest(p_author_ids) AS a(author_id)
         WHERE EXISTS (SELECT 1 FROM library.authors x WHERE x.id = a.author_id)
        ON CONFLICT DO NOTHING;
    END IF;

    DELETE FROM library.book_genres WHERE book_id = p_book_id;
    IF p_genre_ids IS NOT NULL AND array_length(p_genre_ids, 1) > 0 THEN
        INSERT INTO library.book_genres (book_id, genre_id)
        SELECT DISTINCT p_book_id, g.genre_id
          FROM unnest(p_genre_ids) AS g(genre_id)
         WHERE EXISTS (SELECT 1 FROM library.genres x WHERE x.id = g.genre_id)
        ON CONFLICT DO NOTHING;
    END IF;
END;
$$;


-- ---------------------------------------------------------------------
-- sp_create_book
-- Alta de un libro con sus autores y generos en UNA sola operacion
-- atomica. Devuelve el identificador generado.
--
-- Sustituye a: books.model.create() + replaceRelations()
-- ---------------------------------------------------------------------
CREATE OR REPLACE FUNCTION library.sp_create_book(
    p_isbn        VARCHAR,
    p_title       VARCHAR,
    p_year        SMALLINT,
    p_price       NUMERIC,
    p_stock       INTEGER,
    p_format_id   INTEGER,
    p_category_id INTEGER,
    p_author_ids  INTEGER[] DEFAULT '{}',
    p_genre_ids   INTEGER[] DEFAULT '{}'
) RETURNS INTEGER
LANGUAGE plpgsql AS $$
DECLARE
    v_book_id INTEGER;
BEGIN
    INSERT INTO library.books (isbn, title, publication_year, price, stock, format_id, category_id)
    VALUES (p_isbn, p_title, p_year, p_price, p_stock, p_format_id, p_category_id)
    RETURNING id INTO v_book_id;

    PERFORM library.sp_replace_book_relations(v_book_id, p_author_ids, p_genre_ids);
    RETURN v_book_id;
END;
$$;


-- ---------------------------------------------------------------------
-- sp_update_book
-- Actualiza los datos escalares y reescribe autores y generos.
-- Devuelve FALSE si el libro no existe (la aplicacion lo traduce a un
-- mensaje, no a un error).
--
-- Las definiciones de conceptos NO se tocan aqui: tienen sus propios
-- formularios y su propia funcion (sp_upsert_book_concept).
--
-- Sustituye a: books.model.update() + replaceRelations()
-- ---------------------------------------------------------------------
CREATE OR REPLACE FUNCTION library.sp_update_book(
    p_id          INTEGER,
    p_isbn        VARCHAR,
    p_title       VARCHAR,
    p_year        SMALLINT,
    p_price       NUMERIC,
    p_stock       INTEGER,
    p_format_id   INTEGER,
    p_category_id INTEGER,
    p_author_ids  INTEGER[] DEFAULT '{}',
    p_genre_ids   INTEGER[] DEFAULT '{}'
) RETURNS BOOLEAN
LANGUAGE plpgsql AS $$
DECLARE
    v_rows INTEGER;
BEGIN
    UPDATE library.books
       SET isbn = p_isbn, title = p_title, publication_year = p_year,
           price = p_price, stock = p_stock,
           format_id = p_format_id, category_id = p_category_id
     WHERE id = p_id;

    GET DIAGNOSTICS v_rows = ROW_COUNT;
    IF v_rows = 0 THEN
        RETURN FALSE;
    END IF;

    PERFORM library.sp_replace_book_relations(p_id, p_author_ids, p_genre_ids);
    RETURN TRUE;
END;
$$;


-- ---------------------------------------------------------------------
-- sp_upsert_book_concept
-- Alta o actualizacion de la definicion que un libro concreto da a un
-- concepto. Es la operacion central del modelo:
--     (libro_id, concepto_id) -> definicion
-- La clave primaria compuesta impide duplicar el par; ON CONFLICT
-- convierte el segundo intento en una actualizacion.
-- ---------------------------------------------------------------------
CREATE OR REPLACE FUNCTION library.sp_upsert_book_concept(
    p_book_id    INTEGER,
    p_concept_id INTEGER,
    p_definition TEXT
) RETURNS VOID
LANGUAGE sql AS $$
    INSERT INTO library.book_concepts (book_id, concept_id, definition)
    VALUES (p_book_id, p_concept_id, p_definition)
    ON CONFLICT (book_id, concept_id)
    DO UPDATE SET definition = EXCLUDED.definition;
$$;


-- ---------------------------------------------------------------------
-- sp_set_cover
-- Marca una imagen como portada del libro. Debe degradar primero la
-- portada anterior: el indice unico parcial ux_book_images_one_cover
-- rechazaria dos portadas simultaneas, de modo que las dos sentencias
-- tienen que ir juntas y en este orden.
-- Devuelve el id de la imagen promovida, o NULL si no pertenece al libro.
-- ---------------------------------------------------------------------
CREATE OR REPLACE FUNCTION library.sp_set_cover(
    p_book_id  INTEGER,
    p_image_id INTEGER
) RETURNS INTEGER
LANGUAGE plpgsql AS $$
DECLARE
    v_id INTEGER;
BEGIN
    UPDATE library.book_images SET is_cover = FALSE
     WHERE book_id = p_book_id AND is_cover = TRUE;

    UPDATE library.book_images SET is_cover = TRUE
     WHERE id = p_image_id AND book_id = p_book_id
    RETURNING id INTO v_id;

    RETURN v_id;   -- NULL si la imagen no existe o es de otro libro
END;
$$;


-- ---------------------------------------------------------------------
-- sp_add_book_image
-- Anade una imagen. Si se pide como portada, degrada la anterior en la
-- misma operacion atomica.
-- ---------------------------------------------------------------------
CREATE OR REPLACE FUNCTION library.sp_add_book_image(
    p_book_id  INTEGER,
    p_url      VARCHAR,
    p_is_cover BOOLEAN DEFAULT FALSE
) RETURNS TABLE (id INTEGER, url VARCHAR, is_cover BOOLEAN)
LANGUAGE plpgsql AS $$
-- Las columnas de salida de RETURNS TABLE crean variables llamadas id, url e
-- is_cover que CHOCAN con las columnas del mismo nombre de book_images. Sin
-- esta directiva, "WHERE is_cover = TRUE" es ambiguo y la funcion falla en
-- ejecucion, no al crearse: el error solo aparece cuando p_is_cover es TRUE.
#variable_conflict use_column
BEGIN
    IF p_is_cover THEN
        UPDATE library.book_images SET is_cover = FALSE
         WHERE library.book_images.book_id = p_book_id
           AND library.book_images.is_cover = TRUE;
    END IF;

    RETURN QUERY
    INSERT INTO library.book_images (book_id, url, is_cover)
    VALUES (p_book_id, p_url, p_is_cover)
    RETURNING library.book_images.id,
              library.book_images.url,
              library.book_images.is_cover;
END;
$$;


-- ---------------------------------------------------------------------
-- fn_usage_count
-- Cuantos libros usan un elemento de catalogo. La fabrica CRUD de
-- core/crud/ la consulta antes de permitir un borrado, para poder dar un
-- mensaje util en lugar de dejar que estalle la clave foranea.
--
-- El nombre de la entidad se resuelve con CASE sobre una lista cerrada:
-- NO se construye SQL dinamico con el texto recibido. Un valor
-- desconocido devuelve -1, nunca ejecuta nada.
-- ---------------------------------------------------------------------
CREATE OR REPLACE FUNCTION library.fn_usage_count(
    p_entity TEXT,
    p_id     INTEGER
) RETURNS INTEGER
LANGUAGE plpgsql STABLE AS $$
DECLARE
    v_total INTEGER;
BEGIN
    CASE p_entity
        WHEN 'authors'    THEN SELECT count(*) INTO v_total FROM library.book_authors  WHERE author_id  = p_id;
        WHEN 'genres'     THEN SELECT count(*) INTO v_total FROM library.book_genres   WHERE genre_id   = p_id;
        WHEN 'concepts'   THEN SELECT count(*) INTO v_total FROM library.book_concepts WHERE concept_id = p_id;
        WHEN 'formats'    THEN SELECT count(*) INTO v_total FROM library.books         WHERE format_id  = p_id;
        WHEN 'categories' THEN SELECT count(*) INTO v_total FROM library.books         WHERE category_id = p_id;
        ELSE RETURN -1;   -- entidad no reconocida: no se ejecuta ninguna consulta
    END CASE;
    RETURN COALESCE(v_total, 0);
END;
$$;


-- ---------------------------------------------------------------------
-- sp_create_user
-- Alta de usuario. El hash bcrypt SE CALCULA EN LA APLICACION y llega ya
-- cifrado: la base nunca ve la contrasena en claro.
--
-- Definida pero NO conectada a la aplicacion: el modulo de usuarios
-- funciona con una sola sentencia y no gana nada moviendola aqui. Se
-- deja como referencia del contrato.
-- ---------------------------------------------------------------------
CREATE OR REPLACE FUNCTION library.sp_create_user(
    p_full_name     VARCHAR,
    p_email         VARCHAR,
    p_password_hash VARCHAR,
    p_role          library.user_role DEFAULT 'user',
    p_is_active     BOOLEAN DEFAULT TRUE
) RETURNS INTEGER
LANGUAGE sql AS $$
    INSERT INTO library.users (full_name, email, password_hash, role, is_active)
    VALUES (p_full_name, p_email, p_password_hash, p_role, p_is_active)
    RETURNING id;
$$;


-- ---------------------------------------------------------------------
-- fn_search_books
-- Busqueda con todos los filtros del catalogo resueltos en la base.
-- NULL en un parametro significa "no filtrar por este campo".
--
-- Definida pero NO conectada: la aplicacion sigue componiendo el WHERE
-- en books.model.js sobre la vista v_books_catalog, porque el orden
-- (ORDER BY) tiene que elegirse con lista blanca en la capa de
-- aplicacion y partirlo en dos sitios seria peor que dejarlo en uno.
-- Se incluye para mostrar el contrato equivalente del lado del servidor.
-- ---------------------------------------------------------------------
CREATE OR REPLACE FUNCTION library.fn_search_books(
    p_search      TEXT    DEFAULT NULL,
    p_genre_id    INTEGER DEFAULT NULL,
    p_author_id   INTEGER DEFAULT NULL,
    p_format_id   INTEGER DEFAULT NULL,
    p_category_id INTEGER DEFAULT NULL,
    p_only_stock  BOOLEAN DEFAULT FALSE,
    p_limit       INTEGER DEFAULT 12,
    p_offset      INTEGER DEFAULT 0
) RETURNS SETOF library.v_books_catalog
LANGUAGE sql STABLE AS $$
    SELECT *
      FROM library.v_books_catalog v
     WHERE (p_search      IS NULL OR p_search = ''
            OR v.title   ILIKE '%' || p_search || '%'
            OR v.isbn    ILIKE '%' || p_search || '%'
            OR v.authors ILIKE '%' || p_search || '%')
       AND (p_genre_id    IS NULL OR p_genre_id    = ANY (v.genre_ids))
       AND (p_author_id   IS NULL OR p_author_id   = ANY (v.author_ids))
       AND (p_format_id   IS NULL OR v.format_id   = p_format_id)
       AND (p_category_id IS NULL OR v.category_id = p_category_id)
       AND (NOT p_only_stock OR v.stock > 0)
     ORDER BY v.created_at DESC, v.id DESC
     LIMIT p_limit OFFSET p_offset;
$$;
