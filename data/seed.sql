-- =====================================================================
-- library/data/seed.sql
-- DATOS INICIALES (INSERTS) de la base de datos library_db.
--
-- El archivo data/schema.sql contiene UNICAMENTE la estructura (DDL).
-- Todos los INSERT viven en este archivo para poder recargar los datos
-- sin volver a crear el esquema.
--
-- Ejecucion:
--   npm run db:setup   -> esquema + estos inserts + administrador
--   npm run db:seed    -> solo estos inserts + administrador
--
-- El script es IDEMPOTENTE: puede ejecutarse varias veces sin duplicar
-- filas (ON CONFLICT DO NOTHING / NOT EXISTS).
--
-- El usuario administrador NO se inserta aqui: lo crea scripts/setup-db.js
-- porque la contrasena debe almacenarse cifrada con bcrypt.
--
-- ---------------------------------------------------------------------
-- DESPLIEGUE EN LA NUBE: por que las tablas van calificadas
--
-- Todas las tablas se escriben como library.<tabla>, no como <tabla>.
-- Asi el archivo NO depende del search_path y se puede ejecutar en
-- cualquier consola o cliente:
--
--   * Consolas SQL que ejecutan cada sentencia en una sesion distinta
--     (el SET se perderia entre una sentencia y la siguiente).
--   * Conexiones detras de PgBouncer en modo transaction pooling, donde
--     un SET fuera de transaccion no sobrevive.
--   * Proveedores que no propagan el parametro de arranque "options"
--     -c search_path=... que usa el pool de la aplicacion.
--
-- Consecuencia practica: el SET de abajo es redundante. Se conserva por
-- comodidad al trabajar en psql, pero SI SU CONSOLA LO RECHAZA PUEDE
-- IGNORARLO SIN RIESGO: los INSERT ya no lo necesitan.
--
-- Requisito previo: data/schema.sql debe haberse aplicado antes, porque
-- es quien crea el esquema "library".
-- ---------------------------------------------------------------------
-- =====================================================================
SET search_path TO library, public;

-- #####################################################################
-- #                                                                   #
-- #                >>> INICIO DE LOS INSERTS <<<                      #
-- #                                                                   #
-- #  Orden de carga (respeta las llaves foraneas):                    #
-- #    1. Catalogos: formats, categories, genres, authors, concepts   #
-- #    2. books                                                       #
-- #    3. book_authors   (libro ->> autor)                            #
-- #    4. book_genres    (libro ->> genero)                           #
-- #    5. book_concepts  ((libro, concepto) -> definicion)            #
-- #    6. book_images    (libro ->> imagen)                           #
-- #    7. users          (usuarios de demostracion, rol 'user')       #
-- #                                                                   #
-- #####################################################################


-- =====================================================================
-- 1. CATALOGOS INDEPENDIENTES
-- =====================================================================

-- ---------- formats: formato_id -> nombre_formato ----------
INSERT INTO library.formats (name) VALUES
  ('Fisico'), ('Digital'), ('Audiolibro'), ('Pasta dura')
ON CONFLICT (name) DO NOTHING;

-- ---------- categories: categoria_id -> nombre_categoria ----------
INSERT INTO library.categories (name) VALUES
  ('Tecnico'), ('Ficcion'), ('Infantil'), ('Divulgacion'), ('Academico')
ON CONFLICT (name) DO NOTHING;

-- ---------- genres: genero_id -> nombre_genero ----------
INSERT INTO library.genres (name) VALUES
  ('Bases de datos'), ('Ingenieria de software'), ('Ciencia ficcion'),
  ('Novela'), ('Ensayo'), ('Historia'), ('Matematicas'),
  ('Algoritmos'), ('Arquitectura de software'), ('Divulgacion cientifica'),
  ('Fisica'), ('Literatura infantil')
ON CONFLICT (name) DO NOTHING;

-- ---------- authors: autor_id -> nombre_autor ----------
INSERT INTO library.authors (name) VALUES
  ('Ramez Elmasri'), ('Shamkant Navathe'), ('Martin Fowler'), ('Kent Beck'),
  ('Isaac Asimov'), ('Gabriel Garcia Marquez'), ('Donald Knuth'),
  ('Robert C. Martin'), ('Erich Gamma'), ('Richard Helm'), ('Ralph Johnson'),
  ('John Vlissides'), ('Thomas H. Cormen'), ('Charles E. Leiserson'),
  ('Ronald L. Rivest'), ('Clifford Stein'), ('Yuval Noah Harari'),
  ('Frank Herbert'), ('Antoine de Saint-Exupery'), ('Stephen Hawking')
ON CONFLICT (name) DO NOTHING;

-- ---------- concepts: concepto_id -> nombre_concepto ----------
INSERT INTO library.concepts (name) VALUES
  ('Normalizacion'), ('Dependencia funcional'), ('Dependencia multivaluada'),
  ('Transaccion'), ('Refactorizacion'), ('Deuda tecnica'), ('Robotica'),
  ('Patron de diseno'), ('Complejidad algoritmica'), ('Codigo limpio'),
  ('Principio SOLID'), ('Arquitectura limpia'), ('Realismo magico'),
  ('Agujero negro'), ('Ecologia planetaria'), ('Revolucion cognitiva')
ON CONFLICT (name) DO NOTHING;


-- =====================================================================
-- 2. LIBROS
--    FD: ISBN -> titulo, ano, precio, stock, formato_id, categoria_id
--    Los catalogos se resuelven por nombre para no depender de los
--    valores concretos que asigne cada SERIAL.
-- =====================================================================
INSERT INTO library.books (isbn, title, publication_year, price, stock, format_id, category_id)
VALUES
  ('978-0133970777', 'Fundamentos de Sistemas de Bases de Datos', 2016, 1250.00, 12,
     (SELECT id FROM library.formats WHERE name = 'Pasta dura'),
     (SELECT id FROM library.categories WHERE name = 'Academico')),
  ('978-0134757599', 'Refactoring: Improving the Design of Existing Code', 2018, 980.50, 7,
     (SELECT id FROM library.formats WHERE name = 'Fisico'),
     (SELECT id FROM library.categories WHERE name = 'Tecnico')),
  ('978-0553293357', 'Fundacion', 1951, 320.00, 25,
     (SELECT id FROM library.formats WHERE name = 'Digital'),
     (SELECT id FROM library.categories WHERE name = 'Ficcion')),
  ('978-0307474728', 'Cien Anos de Soledad', 1967, 410.00, 0,
     (SELECT id FROM library.formats WHERE name = 'Fisico'),
     (SELECT id FROM library.categories WHERE name = 'Ficcion')),
  ('978-0201896831', 'The Art of Computer Programming, Vol. 1', 1997, 2100.00, 3,
     (SELECT id FROM library.formats WHERE name = 'Pasta dura'),
     (SELECT id FROM library.categories WHERE name = 'Academico')),
  ('978-0132350884', 'Clean Code: A Handbook of Agile Software Craftsmanship', 2008, 890.00, 15,
     (SELECT id FROM library.formats WHERE name = 'Fisico'),
     (SELECT id FROM library.categories WHERE name = 'Tecnico')),
  ('978-0134494166', 'Clean Architecture: A Craftsman''s Guide to Software Structure', 2017, 760.00, 9,
     (SELECT id FROM library.formats WHERE name = 'Digital'),
     (SELECT id FROM library.categories WHERE name = 'Tecnico')),
  ('978-0201633610', 'Design Patterns: Elements of Reusable Object-Oriented Software', 1994, 1180.00, 6,
     (SELECT id FROM library.formats WHERE name = 'Pasta dura'),
     (SELECT id FROM library.categories WHERE name = 'Academico')),
  ('978-0262033848', 'Introduction to Algorithms', 2009, 1990.00, 4,
     (SELECT id FROM library.formats WHERE name = 'Pasta dura'),
     (SELECT id FROM library.categories WHERE name = 'Academico')),
  ('978-0062316097', 'Sapiens: De Animales a Dioses', 2014, 540.00, 20,
     (SELECT id FROM library.formats WHERE name = 'Digital'),
     (SELECT id FROM library.categories WHERE name = 'Divulgacion')),
  ('978-0553380163', 'Breve Historia del Tiempo', 1988, 380.00, 11,
     (SELECT id FROM library.formats WHERE name = 'Audiolibro'),
     (SELECT id FROM library.categories WHERE name = 'Divulgacion')),
  ('978-0441013593', 'Dune', 1965, 450.00, 18,
     (SELECT id FROM library.formats WHERE name = 'Fisico'),
     (SELECT id FROM library.categories WHERE name = 'Ficcion')),
  ('978-0156012195', 'El Principito', 1943, 210.00, 30,
     (SELECT id FROM library.formats WHERE name = 'Pasta dura'),
     (SELECT id FROM library.categories WHERE name = 'Infantil'))
ON CONFLICT (isbn) DO NOTHING;


-- =====================================================================
-- 3. libro ->> autor   (MVD resuelta en book_authors)
-- =====================================================================
INSERT INTO library.book_authors (book_id, author_id)
SELECT b.id, a.id FROM library.books b, library.authors a
 WHERE (b.isbn, a.name) IN (
   ('978-0133970777', 'Ramez Elmasri'),
   ('978-0133970777', 'Shamkant Navathe'),
   ('978-0134757599', 'Martin Fowler'),
   ('978-0134757599', 'Kent Beck'),
   ('978-0553293357', 'Isaac Asimov'),
   ('978-0307474728', 'Gabriel Garcia Marquez'),
   ('978-0201896831', 'Donald Knuth'),
   ('978-0132350884', 'Robert C. Martin'),
   ('978-0134494166', 'Robert C. Martin'),
   ('978-0201633610', 'Erich Gamma'),
   ('978-0201633610', 'Richard Helm'),
   ('978-0201633610', 'Ralph Johnson'),
   ('978-0201633610', 'John Vlissides'),
   ('978-0262033848', 'Thomas H. Cormen'),
   ('978-0262033848', 'Charles E. Leiserson'),
   ('978-0262033848', 'Ronald L. Rivest'),
   ('978-0262033848', 'Clifford Stein'),
   ('978-0062316097', 'Yuval Noah Harari'),
   ('978-0553380163', 'Stephen Hawking'),
   ('978-0441013593', 'Frank Herbert'),
   ('978-0156012195', 'Antoine de Saint-Exupery'))
ON CONFLICT DO NOTHING;


-- =====================================================================
-- 4. libro ->> genero   (MVD resuelta en book_genres)
-- =====================================================================
INSERT INTO library.book_genres (book_id, genre_id)
SELECT b.id, g.id FROM library.books b, library.genres g
 WHERE (b.isbn, g.name) IN (
   ('978-0133970777', 'Bases de datos'),
   ('978-0133970777', 'Ingenieria de software'),
   ('978-0134757599', 'Ingenieria de software'),
   ('978-0553293357', 'Ciencia ficcion'),
   ('978-0553293357', 'Novela'),
   ('978-0307474728', 'Novela'),
   ('978-0201896831', 'Matematicas'),
   ('978-0201896831', 'Algoritmos'),
   ('978-0132350884', 'Ingenieria de software'),
   ('978-0134494166', 'Ingenieria de software'),
   ('978-0134494166', 'Arquitectura de software'),
   ('978-0201633610', 'Ingenieria de software'),
   ('978-0201633610', 'Arquitectura de software'),
   ('978-0262033848', 'Algoritmos'),
   ('978-0262033848', 'Matematicas'),
   ('978-0062316097', 'Historia'),
   ('978-0062316097', 'Ensayo'),
   ('978-0553380163', 'Divulgacion cientifica'),
   ('978-0553380163', 'Fisica'),
   ('978-0441013593', 'Ciencia ficcion'),
   ('978-0441013593', 'Novela'),
   ('978-0156012195', 'Literatura infantil'),
   ('978-0156012195', 'Novela'))
ON CONFLICT DO NOTHING;


-- =====================================================================
-- 5. (libro, concepto) -> definicion   (book_concepts)
--    La definicion depende de la clave compuesta completa: el mismo
--    concepto ("Normalizacion", "Refactorizacion", "Patron de diseno")
--    recibe definiciones distintas segun el libro que lo explica.
-- =====================================================================
INSERT INTO library.book_concepts (book_id, concept_id, definition)
SELECT b.id, c.id, v.definition
  FROM (VALUES
    ('978-0133970777', 'Normalizacion',
     'Proceso de descomposicion de relaciones para eliminar redundancia y anomalias de actualizacion, aplicando 1FN a 5FN.'),
    ('978-0133970777', 'Dependencia funcional',
     'Restriccion X -> Y que indica que el valor de X determina de forma unica el valor de Y en toda la relacion.'),
    ('978-0133970777', 'Dependencia multivaluada',
     'Restriccion X ->> Y presente cuando un atributo determina un conjunto de valores independiente del resto de atributos; se resuelve en 4FN.'),
    ('978-0133970777', 'Transaccion',
     'Unidad logica de trabajo que cumple las propiedades ACID: atomicidad, consistencia, aislamiento y durabilidad.'),
    ('978-0134757599', 'Refactorizacion',
     'Cambio en la estructura interna del codigo que no altera su comportamiento observable y mejora su diseno.'),
    ('978-0134757599', 'Deuda tecnica',
     'Costo futuro acumulado por decisiones de diseno que priorizan la entrega inmediata sobre la calidad del codigo.'),
    ('978-0134757599', 'Normalizacion',
     'En el contexto del codigo, dar forma uniforme a estructuras duplicadas para poder extraerlas a una sola abstraccion.'),
    ('978-0553293357', 'Robotica',
     'Disciplina que estudia maquinas autonomas; en la obra se rige por las tres leyes formuladas por el autor.'),
    ('978-0132350884', 'Codigo limpio',
     'Codigo que se lee como prosa: nombres reveladores, funciones cortas con un solo proposito y ausencia de duplicacion.'),
    ('978-0132350884', 'Refactorizacion',
     'Regla del boy scout: dejar cada modulo un poco mas limpio de como se encontro, en pequenos pasos continuos.'),
    ('978-0132350884', 'Deuda tecnica',
     'Desorden acumulado que reduce la velocidad del equipo hasta que reescribir parece mas barato que mantener.'),
    ('978-0134494166', 'Arquitectura limpia',
     'Organizacion en capas concentricas donde las reglas de negocio no dependen de la interfaz, la base de datos ni los frameworks.'),
    ('978-0134494166', 'Principio SOLID',
     'Cinco principios de diseno orientado a objetos: responsabilidad unica, abierto/cerrado, sustitucion de Liskov, segregacion de interfaces e inversion de dependencias.'),
    ('978-0134494166', 'Patron de diseno',
     'Frontera arquitectonica que aisla los detalles tecnicos mediante interfaces controladas por la capa de negocio.'),
    ('978-0201633610', 'Patron de diseno',
     'Solucion reutilizable a un problema recurrente de diseno, descrita por su contexto, su estructura y sus consecuencias.'),
    ('978-0201633610', 'Principio SOLID',
     'Programar contra interfaces y favorecer la composicion sobre la herencia, base conceptual de los patrones del catalogo.'),
    ('978-0262033848', 'Complejidad algoritmica',
     'Medida asintotica del crecimiento del tiempo o el espacio que consume un algoritmo en funcion del tamano de la entrada.'),
    ('978-0201896831', 'Complejidad algoritmica',
     'Analisis exacto del numero de operaciones elementales de un algoritmo, con constantes y no solo con notacion asintotica.'),
    ('978-0307474728', 'Realismo magico',
     'Narrativa que presenta lo extraordinario como parte natural de la vida cotidiana, sin que los personajes lo cuestionen.'),
    ('978-0062316097', 'Revolucion cognitiva',
     'Aparicion del lenguaje ficcional hace unos 70,000 anos, que permitio a Homo sapiens cooperar en grupos muy grandes.'),
    ('978-0553380163', 'Agujero negro',
     'Region del espacio-tiempo con una curvatura tal que nada, ni siquiera la luz, puede escapar de su horizonte de sucesos.'),
    ('978-0441013593', 'Ecologia planetaria',
     'Estudio del equilibrio entre especie, agua y clima de un planeta; en Arrakis define la economia, la religion y la politica.')
  ) AS v(isbn, concept, definition)
  JOIN library.books b    ON b.isbn = v.isbn
  JOIN library.concepts c ON c.name = v.concept
ON CONFLICT (book_id, concept_id) DO NOTHING;


-- =====================================================================
-- 6. libro ->> imagen   (book_images)
--    Portadas de demostracion servidas por Open Library. Las imagenes
--    que suba el administrador desde la aplicacion se guardan en
--    src/public/uploads y se registran con una ruta que empieza en
--    "/uploads/", de modo que estas URL externas nunca se borran del
--    disco al eliminar una imagen (ver core/middlewares/upload.js).
--
--    Restriccion del esquema: como maximo una portada (is_cover = TRUE)
--    por libro (indice unico parcial ux_book_images_one_cover).
--
--    Sin unicidad natural sobre (book_id, url), la idempotencia se
--    resuelve con NOT EXISTS en lugar de ON CONFLICT.
--
--    Sobre una base ya en uso, un libro puede tener ya su portada subida
--    desde la aplicacion. Por eso is_cover se degrada a FALSE cuando el
--    libro ya tiene portada: la imagen de demostracion se agrega a la
--    galeria sin violar ux_book_images_one_cover ni pisar la portada real.
-- =====================================================================
INSERT INTO library.book_images (book_id, url, is_cover)
SELECT b.id,
       v.url,
       v.is_cover AND NOT EXISTS (
         SELECT 1 FROM library.book_images c WHERE c.book_id = b.id AND c.is_cover
       )
  FROM (VALUES
    ('978-0133970777', 'https://covers.openlibrary.org/b/isbn/9780133970777-L.jpg', TRUE),
    ('978-0133970777', 'https://covers.openlibrary.org/b/isbn/9780133970777-M.jpg', FALSE),
    ('978-0134757599', 'https://covers.openlibrary.org/b/isbn/9780134757599-L.jpg', TRUE),
    ('978-0553293357', 'https://covers.openlibrary.org/b/isbn/9780553293357-L.jpg', TRUE),
    ('978-0307474728', 'https://covers.openlibrary.org/b/isbn/9780307474728-L.jpg', TRUE),
    ('978-0307474728', 'https://covers.openlibrary.org/b/isbn/9780307474728-M.jpg', FALSE),
    ('978-0201896831', 'https://covers.openlibrary.org/b/isbn/9780201896831-L.jpg', TRUE),
    ('978-0132350884', 'https://covers.openlibrary.org/b/isbn/9780132350884-L.jpg', TRUE),
    ('978-0134494166', 'https://covers.openlibrary.org/b/isbn/9780134494166-L.jpg', TRUE),
    ('978-0201633610', 'https://covers.openlibrary.org/b/isbn/9780201633610-L.jpg', TRUE),
    ('978-0262033848', 'https://covers.openlibrary.org/b/isbn/9780262033848-L.jpg', TRUE),
    ('978-0062316097', 'https://covers.openlibrary.org/b/isbn/9780062316097-L.jpg', TRUE),
    ('978-0553380163', 'https://covers.openlibrary.org/b/isbn/9780553380163-L.jpg', TRUE),
    ('978-0441013593', 'https://covers.openlibrary.org/b/isbn/9780441013593-L.jpg', TRUE),
    ('978-0441013593', 'https://covers.openlibrary.org/b/isbn/9780441013593-M.jpg', FALSE),
    ('978-0156012195', 'https://covers.openlibrary.org/b/isbn/9780156012195-L.jpg', TRUE)
  ) AS v(isbn, url, is_cover)
  JOIN library.books b ON b.isbn = v.isbn
 WHERE NOT EXISTS (
   SELECT 1 FROM library.book_images i WHERE i.book_id = b.id AND i.url = v.url
 );


-- =====================================================================
-- 7. USUARIOS DE DEMOSTRACION
--    FD: usuario_id -> nombre, email, password_hash, rol
--
--    Solo se insertan cuentas con rol 'user': el esquema admite un unico
--    administrador (indice unico parcial ux_users_single_admin) y lo crea
--    scripts/setup-db.js con la contrasena de .env.
--
--    Contrasena de todas estas cuentas: Demo123!
--    Los hash son bcrypt reales (10 rondas), por lo que sirven para
--    iniciar sesion desde /auth/login. Elimine estas cuentas antes de
--    usar la aplicacion fuera de un entorno de pruebas.
-- =====================================================================
INSERT INTO library.users (full_name, email, password_hash, role, is_active) VALUES
  ('Laura Mendez',  'laura.mendez@example.com',
   '$2a$10$i7oQBu2iPn1gGMnx8ElaBudkFGSlRqlvj7TfRYKCmpN.D6P10w0ca', 'user', TRUE),
  ('Carlos Rivas',  'carlos.rivas@example.com',
   '$2a$10$CNK16l0Uw8bWKLc2hTQbruhgIVRh7m4kq/U1QOYxrUAWMYeuBW7WK', 'user', TRUE),
  ('Ana Torres',    'ana.torres@example.com',
   '$2a$10$BvSWHJmFX5ZT7hdi6dLFc.ZJsZmzyFEDxzDvJ8TtRVOFXDToMlhCS', 'user', TRUE),
  ('Diego Salas',   'diego.salas@example.com',
   '$2a$10$tv1SFyb6Uz.bkJ2z06Mb6OnHJoNgF29/2hh1XoyctBd8JjQydl0pC', 'user', TRUE),
  ('Maria Luna',    'maria.luna@example.com',
   '$2a$10$/nRLn/Fe3YsUtVrtIss0uufHUr8yu9SM47wdfBzk066gUsTLSqGVW', 'user', FALSE)
ON CONFLICT (email) DO NOTHING;

-- #####################################################################
-- #                   >>> FIN DE LOS INSERTS <<<                      #
-- #####################################################################
