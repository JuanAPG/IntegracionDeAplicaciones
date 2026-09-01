-- =====================================================================
-- db/05_triggers.sql
-- DISPARADORES.
--
-- Requisito previo: db/01_schema.sql
-- Orden de carga usado por el instalador: 01 -> 06 -> 04 -> 05 -> 02
-- (los disparadores se crean ANTES de cargar los datos para que el seed
--  pase por ellos y quede normalizado y auditado como cualquier alta).
--
-- ---------------------------------------------------------------------
-- CRITERIO: que merece un disparador y que no
--
-- Un disparador es codigo invisible: se ejecuta sin que nadie lo llame.
-- Eso lo hace excelente para INVARIANTES que deben cumplirse pase lo que
-- pase, y peligroso para logica de negocio, que conviene poder leer en
-- el sitio donde se invoca. Aqui solo hay invariantes.
--
-- Lo que NO se hizo a proposito:
--   * NO hay un disparador que degrade la portada anterior al marcar una
--     nueva. Seria comodo, pero convertiria en silenciosa una operacion
--     que hoy falla de forma ruidosa y comprobable (indice unico parcial
--     ux_book_images_one_cover, codigo 23505). Degradar es una DECISION,
--     y las decisiones se toman en una funcion que se llama a proposito:
--     sp_set_cover / sp_add_book_image en db/04_stored_procedures.sql.
--   * NO hay disparadores de validacion de precio, stock o ano: eso ya
--     lo hacen las restricciones CHECK, que son declarativas, mas baratas
--     y el planificador las entiende.
-- =====================================================================

SET search_path TO library, public;


-- =====================================================================
-- 1. updated_at automatico
--    Sin esto, la columna updated_at depende de que cada UPDATE de la
--    aplicacion se acuerde de tocarla. Un dia alguien no se acuerda.
-- =====================================================================
CREATE OR REPLACE FUNCTION library.fn_set_updated_at()
RETURNS TRIGGER
LANGUAGE plpgsql AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_books_updated_at ON library.books;
CREATE TRIGGER trg_books_updated_at
    BEFORE UPDATE ON library.books
    FOR EACH ROW EXECUTE FUNCTION library.fn_set_updated_at();

DROP TRIGGER IF EXISTS trg_users_updated_at ON library.users;
CREATE TRIGGER trg_users_updated_at
    BEFORE UPDATE ON library.users
    FOR EACH ROW EXECUTE FUNCTION library.fn_set_updated_at();


-- =====================================================================
-- 2. Normalizacion de los datos del libro
--    El ISBN es una clave natural con UNIQUE. Si un operador escribe
--    "978-0132350884 " con un espacio final, o en minusculas, la base
--    aceptaria un DUPLICADO LOGICO que el indice unico no detecta.
--    Normalizar en el disparador cierra ese hueco para cualquier cliente,
--    no solo para esta aplicacion.
-- =====================================================================
CREATE OR REPLACE FUNCTION library.fn_normalize_book()
RETURNS TRIGGER
LANGUAGE plpgsql AS $$
BEGIN
    NEW.isbn  := upper(btrim(NEW.isbn));
    NEW.title := btrim(NEW.title);
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_books_normalize ON library.books;
CREATE TRIGGER trg_books_normalize
    BEFORE INSERT OR UPDATE ON library.books
    FOR EACH ROW EXECUTE FUNCTION library.fn_normalize_book();


-- =====================================================================
-- 3. La primera imagen de un libro es siempre su portada
--    Un libro con imagenes pero sin portada obliga a todas las consultas
--    de listado a inventarse un criterio de desempate. Este disparador
--    hace que ese estado no pueda existir.
--
--    Solo PROMUEVE cuando no hay ninguna imagen; nunca degrada la portada
--    existente. Marcar una segunda portada a mano sigue fallando con
--    23505, que es exactamente lo que se quiere.
-- =====================================================================
CREATE OR REPLACE FUNCTION library.fn_first_image_is_cover()
RETURNS TRIGGER
LANGUAGE plpgsql AS $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM library.book_images WHERE book_id = NEW.book_id) THEN
        NEW.is_cover := TRUE;
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_book_images_first_cover ON library.book_images;
CREATE TRIGGER trg_book_images_first_cover
    BEFORE INSERT ON library.book_images
    FOR EACH ROW EXECUTE FUNCTION library.fn_first_image_is_cover();


-- =====================================================================
-- 4. Proteccion del ultimo administrador
--    El indice ux_users_single_admin impide que haya MAS de uno. Este
--    disparador impide el problema simetrico: quedarse con NINGUNO.
--
--    Un sistema sin administrador no se puede recuperar desde la propia
--    interfaz: haria falta entrar por psql. La aplicacion ya comprueba
--    esto en users.controller, pero esa comprobacion vive en un solo
--    formulario; el disparador cubre tambien el acceso directo por SQL,
--    un script de mantenimiento o un modulo futuro.
-- =====================================================================
CREATE OR REPLACE FUNCTION library.fn_protect_last_admin()
RETURNS TRIGGER
LANGUAGE plpgsql AS $$
DECLARE
    v_otros INTEGER;
BEGIN
    -- Solo interesa cuando la fila afectada ES el administrador
    IF OLD.role <> 'admin' THEN
        IF TG_OP = 'DELETE' THEN RETURN OLD; ELSE RETURN NEW; END IF;
    END IF;

    -- Si sigue siendo administrador activo, la operacion es inofensiva
    IF TG_OP = 'UPDATE' AND NEW.role = 'admin' AND NEW.is_active THEN
        RETURN NEW;
    END IF;

    SELECT count(*) INTO v_otros
      FROM library.users
     WHERE role = 'admin' AND is_active AND id <> OLD.id;

    IF v_otros = 0 THEN
        RAISE EXCEPTION
            'No se puede dejar el sistema sin administrador activo (usuario %).', OLD.id
            USING ERRCODE = 'raise_exception';
    END IF;

    IF TG_OP = 'DELETE' THEN RETURN OLD; ELSE RETURN NEW; END IF;
END;
$$;

DROP TRIGGER IF EXISTS trg_users_protect_admin ON library.users;
CREATE TRIGGER trg_users_protect_admin
    BEFORE UPDATE OR DELETE ON library.users
    FOR EACH ROW EXECUTE FUNCTION library.fn_protect_last_admin();


-- =====================================================================
-- 5. Bitacora de cambios sobre libros
--    Escribe en library.audit_log quien cambio que y cuando. Es el unico
--    disparador que no protege un invariante: existe porque el catalogo
--    es el activo del negocio y un borrado accidental debe poder
--    rastrearse. La tabla se declara en db/01_schema.sql.
--
--    Registra el id y un resumen legible, NUNCA la fila completa: una
--    bitacora que copia todo crece sin control y termina desactivandose.
-- =====================================================================
CREATE OR REPLACE FUNCTION library.fn_audit_books()
RETURNS TRIGGER
LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        INSERT INTO library.audit_log (table_name, operation, record_id, details)
        VALUES ('books', 'INSERT', NEW.id, format('%s (ISBN %s)', NEW.title, NEW.isbn));
        RETURN NEW;

    ELSIF TG_OP = 'UPDATE' THEN
        -- Solo se registra si cambio algo relevante para el negocio
        IF (OLD.isbn, OLD.title, OLD.price, OLD.stock) IS DISTINCT FROM
           (NEW.isbn, NEW.title, NEW.price, NEW.stock) THEN
            INSERT INTO library.audit_log (table_name, operation, record_id, details)
            VALUES ('books', 'UPDATE', NEW.id,
                    format('precio %s -> %s | stock %s -> %s | titulo %s',
                           OLD.price, NEW.price, OLD.stock, NEW.stock, NEW.title));
        END IF;
        RETURN NEW;

    ELSE
        INSERT INTO library.audit_log (table_name, operation, record_id, details)
        VALUES ('books', 'DELETE', OLD.id, format('%s (ISBN %s)', OLD.title, OLD.isbn));
        RETURN OLD;
    END IF;
END;
$$;

DROP TRIGGER IF EXISTS trg_books_audit ON library.books;
CREATE TRIGGER trg_books_audit
    AFTER INSERT OR UPDATE OR DELETE ON library.books
    FOR EACH ROW EXECUTE FUNCTION library.fn_audit_books();


-- =====================================================================
-- RESUMEN
--
--   trg_books_updated_at         BEFORE UPDATE     books
--   trg_users_updated_at         BEFORE UPDATE     users
--   trg_books_normalize          BEFORE INS/UPD    books
--   trg_book_images_first_cover  BEFORE INSERT     book_images
--   trg_users_protect_admin      BEFORE UPD/DEL    users
--   trg_books_audit              AFTER  INS/UPD/DEL books
--
-- Comprobacion:
--   SELECT tgname, relname FROM pg_trigger t
--     JOIN pg_class c ON c.oid = t.tgrelid
--    WHERE NOT tgisinternal AND relnamespace = 'library'::regnamespace;
-- =====================================================================
