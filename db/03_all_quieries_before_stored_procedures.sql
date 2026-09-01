-- =====================================================================
-- db/03_all_quieries_before_stored_procedures.sql
--
-- INVENTARIO DE CONSULTAS DE LA APLICACION, TAL Y COMO ESTABAN ESCRITAS
-- EN LA CAPA DE MODELO ANTES DE MOVER NADA A LA BASE DE DATOS.
--
-- ---------------------------------------------------------------------
-- ESTE ARCHIVO NO SE EJECUTA.
-- No crea ni modifica nada. El instalador (scripts/setup-db.js) lo salta
-- deliberadamente. Es la FOTOGRAFIA DEL PUNTO DE PARTIDA: sirve para
-- comparar, para justificar por que ciertas consultas se convirtieron en
-- funciones o en vistas y para poder revertir la decision si hiciera
-- falta.
--
-- Si quiere ejecutar alguna, hagalo a mano sustituyendo $1, $2... por
-- valores concretos.
--
-- ---------------------------------------------------------------------
-- QUE PASO CON CADA UNA (resumen; el detalle esta junto a cada consulta)
--
--   [VISTA]     absorbida por db/06_views.sql
--   [FUNCION]   absorbida por db/04_stored_procedures.sql
--   [IGUAL]     sigue en la capa de modelo, sin cambios
--
--   Total inventariado: 38 consultas
--     [IGUAL]   28     consultas de una sola tabla o de un solo JOIN;
--                      subirlas a la base no aporta nada y las alejaria
--                      del sitio donde se leen.
--     [VISTA]     6     lecturas del catalogo con agregacion repetida.
--     [FUNCION]   4     escrituras que tocan varias tablas y deben ser
--                      atomicas.
--
-- ---------------------------------------------------------------------
-- NOTA SOBRE LOS PARAMETROS
-- Todas las consultas usan marcadores $1, $2... y NUNCA concatenacion de
-- texto. El unico fragmento que no puede parametrizarse es el ORDER BY,
-- porque es un identificador y no un valor; se resuelve con lista blanca
-- en la aplicacion (objeto ORDERS de books.model.js), no interpolando lo
-- que llegue en la URL.
-- =====================================================================


-- #####################################################################
-- 1. MODULO CATALOGO / LIBROS   (src/modules/books/books.model.js)
-- #####################################################################

-- ---------------------------------------------------------------------
-- 1.1  Listado del catalogo con filtros, orden y paginacion    [VISTA]
--
-- Esta era la consulta mas cara de mantener: tres subconsultas
-- correlacionadas de agregacion mas dos de conteo, y el WHERE compuesto
-- a mano segun los filtros activos. Aparecia entera en list() y su
-- gemela recortada en count(), con el riesgo de que ambas se separaran.
--
-- AHORA: SELECT ... FROM library.v_books_catalog con el mismo WHERE
-- dinamico. La agregacion se escribe una sola vez, en la vista.
-- ---------------------------------------------------------------------
SELECT b.id, b.isbn, b.title, b.publication_year, b.price, b.stock,
       f.name AS format_name, c.name AS category_name,
       COALESCE((SELECT string_agg(a.name, ', ' ORDER BY a.name)
                   FROM book_authors ba JOIN authors a ON a.id = ba.author_id
                  WHERE ba.book_id = b.id), '') AS authors,
       COALESCE((SELECT string_agg(g.name, ', ' ORDER BY g.name)
                   FROM book_genres bg JOIN genres g ON g.id = bg.genre_id
                  WHERE bg.book_id = b.id), '') AS genres,
       (SELECT i.url FROM book_images i
         WHERE i.book_id = b.id
         ORDER BY i.is_cover DESC, i.id ASC LIMIT 1) AS cover_url,
       (SELECT COUNT(*) FROM book_concepts bc WHERE bc.book_id = b.id)::int AS concepts_count,
       (SELECT COUNT(*) FROM book_images  bi WHERE bi.book_id = b.id)::int AS images_count
  FROM books b
  JOIN formats f    ON f.id = b.format_id
  JOIN categories c ON c.id = b.category_id
 WHERE (b.title ILIKE $1 OR b.isbn ILIKE $1
        OR EXISTS (SELECT 1 FROM book_authors ba JOIN authors a ON a.id = ba.author_id
                    WHERE ba.book_id = b.id AND a.name ILIKE $1))
   AND EXISTS (SELECT 1 FROM book_genres  bg WHERE bg.book_id = b.id AND bg.genre_id  = $2)
   AND EXISTS (SELECT 1 FROM book_authors ba WHERE ba.book_id = b.id AND ba.author_id = $3)
   AND b.format_id   = $4
   AND b.category_id = $5
   AND b.stock > 0
 ORDER BY b.created_at DESC, b.id DESC     -- <- elegido por lista blanca
 LIMIT $6 OFFSET $7;

-- ---------------------------------------------------------------------
-- 1.2  Total de resultados para la paginacion                  [VISTA]
-- ---------------------------------------------------------------------
SELECT COUNT(*)::int AS total FROM books b /* + el mismo WHERE de 1.1 */;

-- ---------------------------------------------------------------------
-- 1.3  Un libro por identificador                              [IGUAL]
-- ---------------------------------------------------------------------
SELECT b.*, f.name AS format_name, c.name AS category_name
  FROM books b
  JOIN formats f    ON f.id = b.format_id
  JOIN categories c ON c.id = b.category_id
 WHERE b.id = $1;

-- ---------------------------------------------------------------------
-- 1.4  Un libro por ISBN (control de duplicados en el alta)    [IGUAL]
-- ---------------------------------------------------------------------
SELECT id, isbn, title FROM books WHERE isbn = $1;

-- ---------------------------------------------------------------------
-- 1.5  Autores de un libro                                     [IGUAL]
-- ---------------------------------------------------------------------
SELECT a.id, a.name
  FROM book_authors ba JOIN authors a ON a.id = ba.author_id
 WHERE ba.book_id = $1
 ORDER BY a.name;

-- ---------------------------------------------------------------------
-- 1.6  Generos de un libro                                     [IGUAL]
-- ---------------------------------------------------------------------
SELECT g.id, g.name
  FROM book_genres bg JOIN genres g ON g.id = bg.genre_id
 WHERE bg.book_id = $1
 ORDER BY g.name;

-- ---------------------------------------------------------------------
-- 1.7  Conceptos de un libro CON SU DEFINICION                 [IGUAL]
--      (libro_id, concepto_id) -> definicion
-- ---------------------------------------------------------------------
SELECT c.id AS concept_id, c.name, bc.definition
  FROM book_concepts bc JOIN concepts c ON c.id = bc.concept_id
 WHERE bc.book_id = $1
 ORDER BY c.name;

-- ---------------------------------------------------------------------
-- 1.8  Imagenes de un libro                                    [IGUAL]
-- ---------------------------------------------------------------------
SELECT id, book_id, url, is_cover, created_at
  FROM book_images
 WHERE book_id = $1
 ORDER BY is_cover DESC, id ASC;

-- ---------------------------------------------------------------------
-- 1.9  ALTA de libro                                         [FUNCION]
--
-- Iba dentro de db.transaction() en JavaScript, seguida de 1.13.
-- Entre el INSERT y las relaciones habia 3 + N viajes de red, y la
-- atomicidad dependia de que el codigo llamara a COMMIT correctamente.
--
-- AHORA: SELECT library.sp_create_book($1..$9)  -> un unico viaje.
-- ---------------------------------------------------------------------
INSERT INTO books (isbn, title, publication_year, price, stock, format_id, category_id)
VALUES ($1, $2, $3, $4, $5, $6, $7)
RETURNING id;

-- ---------------------------------------------------------------------
-- 1.10 EDICION de libro                                      [FUNCION]
--      AHORA: SELECT library.sp_update_book($1..$10)
-- ---------------------------------------------------------------------
UPDATE books
   SET isbn = $2, title = $3, publication_year = $4, price = $5,
       stock = $6, format_id = $7, category_id = $8
 WHERE id = $1;

-- ---------------------------------------------------------------------
-- 1.11 BAJA de libro                                           [IGUAL]
--      La cascada del esquema borra autores, generos, conceptos e
--      imagenes. No hace falta funcion: es una sola sentencia.
-- ---------------------------------------------------------------------
DELETE FROM books WHERE id = $1 RETURNING id, title;

-- ---------------------------------------------------------------------
-- 1.12 Definicion de un concepto para un libro               [FUNCION]
--      AHORA: SELECT library.sp_upsert_book_concept($1, $2, $3)
-- ---------------------------------------------------------------------
INSERT INTO book_concepts (book_id, concept_id, definition)
VALUES ($1, $2, $3)
ON CONFLICT (book_id, concept_id) DO UPDATE SET definition = EXCLUDED.definition
RETURNING book_id, concept_id;

-- ---------------------------------------------------------------------
-- 1.13 Reescritura de relaciones multivaluadas               [FUNCION]
--      Se ejecutaba en bucle desde JavaScript: un DELETE y luego un
--      INSERT por cada autor y por cada genero.
--      AHORA: dentro de library.sp_replace_book_relations(), con
--      unnest() sobre un arreglo y una sola sentencia por tabla.
-- ---------------------------------------------------------------------
DELETE FROM book_authors WHERE book_id = $1;
INSERT INTO book_authors (book_id, author_id) VALUES ($1, $2) ON CONFLICT DO NOTHING;
DELETE FROM book_genres  WHERE book_id = $1;
INSERT INTO book_genres  (book_id, genre_id)  VALUES ($1, $2) ON CONFLICT DO NOTHING;
DELETE FROM book_concepts WHERE book_id = $1 AND concept_id <> ALL($2::int[]);

-- ---------------------------------------------------------------------
-- 1.14 Retirar un concepto de un libro                         [IGUAL]
-- ---------------------------------------------------------------------
DELETE FROM book_concepts WHERE book_id = $1 AND concept_id = $2 RETURNING concept_id;

-- ---------------------------------------------------------------------
-- 1.15 Alta de imagen                                          [IGUAL]
--      Existe library.sp_add_book_image() equivalente, pero la
--      aplicacion conserva esta version: la degradacion de la portada
--      anterior solo ocurre cuando el usuario marca la casilla, y el
--      disparador trg_book_images_first_cover ya cubre el caso de la
--      primera imagen.
-- ---------------------------------------------------------------------
UPDATE book_images SET is_cover = FALSE WHERE book_id = $1;
INSERT INTO book_images (book_id, url, is_cover)
VALUES ($1, $2, $3) RETURNING id, url, is_cover;

-- ---------------------------------------------------------------------
-- 1.16 Cambio de portada                                     [FUNCION]
--      Dos sentencias que DEBEN ir juntas: si se ejecuta solo la
--      segunda, el indice unico parcial ux_book_images_one_cover
--      rechaza la operacion con el codigo 23505.
--      AHORA: SELECT library.sp_set_cover($1, $2)
-- ---------------------------------------------------------------------
UPDATE book_images SET is_cover = FALSE WHERE book_id = $1;
UPDATE book_images SET is_cover = TRUE  WHERE id = $1 AND book_id = $2 RETURNING id;

-- ---------------------------------------------------------------------
-- 1.17 Baja de imagen                                          [IGUAL]
-- ---------------------------------------------------------------------
DELETE FROM book_images WHERE id = $1 RETURNING id, book_id, url;


-- #####################################################################
-- 2. FABRICA CRUD DE CATALOGOS   (src/core/crud/lookupModel.js)
--    Una sola implementacion parametrizada sirve a formats, categories,
--    genres, authors y concepts.
-- #####################################################################

-- ---------------------------------------------------------------------
-- 2.1  Listado con busqueda y paginacion                       [IGUAL]
-- ---------------------------------------------------------------------
SELECT id, name FROM formats WHERE name ILIKE $1 ORDER BY name LIMIT $2 OFFSET $3;

-- ---------------------------------------------------------------------
-- 2.2  Conteo para la paginacion                               [IGUAL]
-- ---------------------------------------------------------------------
SELECT COUNT(*)::int AS total FROM formats WHERE name ILIKE $1;

-- ---------------------------------------------------------------------
-- 2.3  Todos los elementos (para los desplegables del formulario) [IGUAL]
-- ---------------------------------------------------------------------
SELECT id, name FROM formats ORDER BY name;

-- ---------------------------------------------------------------------
-- 2.4 a 2.7  Alta, lectura, edicion y baja                     [IGUAL]
-- ---------------------------------------------------------------------
INSERT INTO formats (name) VALUES ($1) RETURNING id, name;
SELECT id, name FROM formats WHERE id = $1;
UPDATE formats SET name = $2 WHERE id = $1 RETURNING id, name;
DELETE FROM formats WHERE id = $1 RETURNING id, name;

-- ---------------------------------------------------------------------
-- 2.8  Uso del elemento antes de permitir el borrado         [FUNCION]
--
-- Habia CINCO variantes de esta consulta, una por entidad, generadas por
-- la fabrica a partir del nombre de la columna. Funcionaba, pero era el
-- unico sitio del sistema donde un nombre de tabla viajaba dentro de una
-- cadena SQL construida en JavaScript.
--
-- AHORA: SELECT library.fn_usage_count($1, $2), que resuelve la entidad
-- con un CASE sobre una lista cerrada. Un nombre desconocido devuelve -1
-- y no ejecuta ninguna consulta.
-- ---------------------------------------------------------------------
SELECT COUNT(*)::int AS total FROM books        WHERE format_id  = $1;
SELECT COUNT(*)::int AS total FROM books        WHERE category_id = $1;
SELECT COUNT(*)::int AS total FROM book_authors  WHERE author_id  = $1;
SELECT COUNT(*)::int AS total FROM book_genres   WHERE genre_id   = $1;
SELECT COUNT(*)::int AS total FROM book_concepts WHERE concept_id = $1;

-- ---------------------------------------------------------------------
-- 2.9  Buscar por nombre exacto (alta desde el formulario de libro) [IGUAL]
--      Permite escribir "Autor A, Autor B" y crear los que no existan.
-- ---------------------------------------------------------------------
SELECT id, name FROM authors WHERE lower(name) = lower($1);


-- #####################################################################
-- 3. MODULO USUARIOS Y AUTENTICACION
--    (src/modules/users/users.model.js)
-- #####################################################################

-- 3.1  Buscar por correo (inicio de sesion y control de duplicados) [IGUAL]
SELECT id, full_name, email, password_hash, role, is_active FROM users WHERE email = $1;

-- 3.2  Buscar por identificador                                     [IGUAL]
SELECT id, full_name, email, role, is_active, created_at, updated_at FROM users WHERE id = $1;

-- 3.3  Solo el hash (verificacion de la contrasena actual)          [IGUAL]
SELECT password_hash FROM users WHERE id = $1;

-- 3.4  Listado con busqueda por texto y filtro por rol              [IGUAL]
SELECT id, full_name, email, role, is_active, created_at
  FROM users
 WHERE (full_name ILIKE $1 OR email ILIKE $1) AND role = $2
 ORDER BY id LIMIT $3 OFFSET $4;

-- 3.5  Cuantos administradores hay (excluyendo uno)                 [IGUAL]
--      Sostiene la regla "como maximo un administrador" en la interfaz.
--      La GARANTIA no esta aqui, sino en el indice unico parcial
--      ux_users_single_admin: una comprobacion en el controlador tiene
--      una condicion de carrera y el indice no.
SELECT COUNT(*)::int AS total FROM users WHERE role = 'admin' AND id <> $1;

-- 3.6  Alta de usuario  (el hash llega ya calculado con bcrypt)     [IGUAL]
INSERT INTO users (full_name, email, password_hash, role, is_active)
VALUES ($1, $2, $3, $4, $5)
RETURNING id, full_name, email, role, is_active;

-- 3.7  Edicion de usuario                                           [IGUAL]
UPDATE users SET full_name = $2, email = $3, role = $4, is_active = $5
 WHERE id = $1
RETURNING id, full_name, email, role, is_active;

-- 3.8  Edicion del perfil propio (no toca rol ni estado)            [IGUAL]
UPDATE users SET full_name = $2, email = $3 WHERE id = $1
RETURNING id, full_name, email, role;

-- 3.9  Cambio de contrasena                                         [IGUAL]
UPDATE users SET password_hash = $2 WHERE id = $1;

-- 3.10 Baja de usuario                                              [IGUAL]
DELETE FROM users WHERE id = $1 RETURNING id, full_name;


-- #####################################################################
-- 4. PORTADA PUBLICA   (src/modules/catalog/catalog.controller.js)
-- #####################################################################

-- ---------------------------------------------------------------------
-- 4.1  Cifras agregadas de la portada                          [VISTA]
--
-- Eran cuatro consultas lanzadas en paralelo con Promise.all desde el
-- controlador. Cuatro conexiones del pool para pintar cuatro numeros.
--
-- AHORA: SELECT * FROM library.v_catalog_stats  -> una sola fila.
-- ---------------------------------------------------------------------
SELECT COUNT(*)::int FROM books;
SELECT COUNT(*)::int FROM authors;
SELECT COUNT(*)::int FROM genres;
SELECT COUNT(*)::int FROM concepts;


-- #####################################################################
-- 5. INSTALADOR   (scripts/setup-db.js)
-- #####################################################################

-- 5.1  ?Existe ya el esquema?                                       [IGUAL]
SELECT 1 AS found FROM information_schema.schemata WHERE schema_name = $1;

-- 5.2  ?Existe ya un administrador?                                 [IGUAL]
SELECT id, email FROM library.users WHERE role = 'admin';

-- 5.3  Alta del administrador inicial                               [IGUAL]
INSERT INTO library.users (full_name, email, password_hash, role)
VALUES ($1, $2, $3, 'admin');

-- =====================================================================
-- FIN DEL INVENTARIO
-- =====================================================================
