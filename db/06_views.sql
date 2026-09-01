-- =====================================================================
-- db/06_views.sql
-- VISTAS.
--
-- Requisito previo: db/01_schema.sql
-- Orden de carga usado por el instalador: 01 -> 06 -> 04 -> 05 -> 02
-- (las vistas van antes que las funciones porque fn_search_books
--  devuelve SETOF library.v_books_catalog).
--
-- ---------------------------------------------------------------------
-- CRITERIO
--
-- El modelo esta normalizado hasta 4FN, que es lo correcto para ESCRIBIR:
-- ningun dato repetido, ninguna anomalia de actualizacion. Pero casi toda
-- LECTURA de esta aplicacion necesita lo contrario: el libro con sus
-- autores y generos ya reunidos en una linea.
--
-- Esa reunion se escribia antes a mano en books.model.js: dos
-- subconsultas de agregacion, una de portada y dos de conteo, repetidas
-- en list() y a punto de repetirse en cada consulta nueva. Las vistas la
-- escriben UNA vez. El modelo normalizado sigue siendo la verdad; la
-- vista es la forma comoda de leerlo.
--
-- Vistas conectadas a la aplicacion:  v_books_catalog, v_catalog_stats
-- Vistas de apoyo y diagnostico:      las demas (no las usa la app)
-- =====================================================================

SET search_path TO library, public;


-- =====================================================================
-- v_books_catalog   [LA USA LA APLICACION]
--
-- Modelo de lectura del catalogo. Reune el libro con sus catalogos, sus
-- autores y generos agregados (como texto para mostrar y como arreglo de
-- identificadores para filtrar), su portada y sus conteos.
--
-- Los arreglos author_ids / genre_ids permiten filtrar con
--     WHERE $1 = ANY(genre_ids)
-- en lugar de un EXISTS con subconsulta por cada filtro.
-- =====================================================================
CREATE OR REPLACE VIEW library.v_books_catalog AS
SELECT b.id,
       b.isbn,
       b.title,
       b.publication_year,
       b.price,
       b.stock,
       b.format_id,
       b.category_id,
       b.created_at,
       b.updated_at,
       f.name AS format_name,
       c.name AS category_name,
       COALESCE(a.names, '')       AS authors,
       COALESCE(g.names, '')       AS genres,
       COALESCE(a.ids, '{}'::int[]) AS author_ids,
       COALESCE(g.ids, '{}'::int[]) AS genre_ids,
       cov.url                     AS cover_url,
       COALESCE(bc.total, 0)       AS concepts_count,
       COALESCE(bi.total, 0)       AS images_count
  FROM library.books b
  JOIN library.formats    f ON f.id = b.format_id
  JOIN library.categories c ON c.id = b.category_id
  LEFT JOIN LATERAL (
        SELECT string_agg(au.name, ', ' ORDER BY au.name) AS names,
               array_agg(au.id ORDER BY au.id)            AS ids
          FROM library.book_authors ba
          JOIN library.authors au ON au.id = ba.author_id
         WHERE ba.book_id = b.id
  ) a ON TRUE
  LEFT JOIN LATERAL (
        SELECT string_agg(ge.name, ', ' ORDER BY ge.name) AS names,
               array_agg(ge.id ORDER BY ge.id)            AS ids
          FROM library.book_genres bg
          JOIN library.genres ge ON ge.id = bg.genre_id
         WHERE bg.book_id = b.id
  ) g ON TRUE
  LEFT JOIN LATERAL (
        SELECT i.url
          FROM library.book_images i
         WHERE i.book_id = b.id
         ORDER BY i.is_cover DESC, i.id ASC
         LIMIT 1
  ) cov ON TRUE
  LEFT JOIN LATERAL (
        SELECT count(*)::int AS total FROM library.book_concepts x WHERE x.book_id = b.id
  ) bc ON TRUE
  LEFT JOIN LATERAL (
        SELECT count(*)::int AS total FROM library.book_images x WHERE x.book_id = b.id
  ) bi ON TRUE;


-- =====================================================================
-- v_catalog_stats   [LA USA LA APLICACION]
--
-- Cifras de la portada publica. Antes eran cuatro consultas lanzadas en
-- paralelo desde el controlador; ahora es una sola fila.
-- =====================================================================
CREATE OR REPLACE VIEW library.v_catalog_stats AS
SELECT (SELECT count(*)::int FROM library.books)         AS books,
       (SELECT count(*)::int FROM library.authors)       AS authors,
       (SELECT count(*)::int FROM library.genres)        AS genres,
       (SELECT count(*)::int FROM library.concepts)      AS concepts,
       (SELECT count(*)::int FROM library.book_images)   AS images,
       (SELECT count(*)::int FROM library.book_concepts) AS definitions,
       (SELECT count(*)::int FROM library.users WHERE is_active) AS active_users;


-- =====================================================================
-- v_book_concepts
--
-- La relacion central del modelo, ya legible: cada fila es la definicion
-- que UN libro concreto da a UN concepto. Util para revisar de un vistazo
-- que un mismo concepto tiene textos distintos segun el libro.
--
--   SELECT concept_name, book_title, left(definition, 60)
--     FROM library.v_book_concepts
--    WHERE concept_name = 'Refactorizacion';
-- =====================================================================
CREATE OR REPLACE VIEW library.v_book_concepts AS
SELECT bc.book_id,
       b.title   AS book_title,
       b.isbn,
       bc.concept_id,
       c.name    AS concept_name,
       bc.definition
  FROM library.book_concepts bc
  JOIN library.books    b ON b.id = bc.book_id
  JOIN library.concepts c ON c.id = bc.concept_id;


-- =====================================================================
-- v_shared_concepts
--
-- Conceptos definidos por mas de un libro, con cuantas definiciones
-- DISTINTAS tienen. Es la evidencia del diseno en una consulta: si la
-- definicion viviera en la tabla concepts, esta vista devolveria siempre
-- distinct_definitions = 1 y no habria nada que modelar.
-- =====================================================================
CREATE OR REPLACE VIEW library.v_shared_concepts AS
SELECT c.id   AS concept_id,
       c.name AS concept_name,
       count(*)::int                       AS books,
       count(DISTINCT bc.definition)::int  AS distinct_definitions
  FROM library.concepts c
  JOIN library.book_concepts bc ON bc.concept_id = c.id
 GROUP BY c.id, c.name
HAVING count(*) > 1;


-- =====================================================================
-- v_catalog_usage
--
-- Cuantos libros usa cada elemento de catalogo, en una sola relacion.
-- Sirve para la pantalla de administracion de catalogos y para saber que
-- se puede borrar sin chocar con una clave foranea.
-- =====================================================================
CREATE OR REPLACE VIEW library.v_catalog_usage AS
SELECT 'formats'::text AS entity, f.id, f.name,
       (SELECT count(*)::int FROM library.books x WHERE x.format_id = f.id) AS usage_count
  FROM library.formats f
UNION ALL
SELECT 'categories', c.id, c.name,
       (SELECT count(*)::int FROM library.books x WHERE x.category_id = c.id)
  FROM library.categories c
UNION ALL
SELECT 'authors', a.id, a.name,
       (SELECT count(*)::int FROM library.book_authors x WHERE x.author_id = a.id)
  FROM library.authors a
UNION ALL
SELECT 'genres', g.id, g.name,
       (SELECT count(*)::int FROM library.book_genres x WHERE x.genre_id = g.id)
  FROM library.genres g
UNION ALL
SELECT 'concepts', k.id, k.name,
       (SELECT count(*)::int FROM library.book_concepts x WHERE x.concept_id = k.id)
  FROM library.concepts k;


-- =====================================================================
-- v_books_without_cover
--
-- Control de calidad del catalogo: libros sin ninguna imagen, o con
-- imagenes pero sin portada. Con el disparador
-- trg_book_images_first_cover el segundo caso ya no deberia ocurrir;
-- esta vista existe justamente para comprobarlo.
-- =====================================================================
CREATE OR REPLACE VIEW library.v_books_without_cover AS
SELECT b.id, b.isbn, b.title,
       (SELECT count(*)::int FROM library.book_images i WHERE i.book_id = b.id) AS images
  FROM library.books b
 WHERE NOT EXISTS (SELECT 1 FROM library.book_images i
                    WHERE i.book_id = b.id AND i.is_cover);


-- =====================================================================
-- v_audit_recent
--
-- Ultimos 200 cambios registrados por trg_books_audit, con el titulo
-- actual del libro cuando todavia existe.
-- =====================================================================
CREATE OR REPLACE VIEW library.v_audit_recent AS
SELECT l.id, l.table_name, l.operation, l.record_id,
       b.title AS current_title,
       l.changed_by, l.changed_at, l.details
  FROM library.audit_log l
  LEFT JOIN library.books b ON b.id = l.record_id AND l.table_name = 'books'
 ORDER BY l.changed_at DESC, l.id DESC
 LIMIT 200;
