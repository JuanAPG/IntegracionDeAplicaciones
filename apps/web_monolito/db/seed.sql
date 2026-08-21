-- =====================================================================
-- Datos iniciales de demostracion (idempotente).
-- Se ejecuta con: npm run db:seed
-- El usuario administrador NO se crea aqui: lo crea scripts/setup-db.js
-- porque la contrasena debe almacenarse cifrada con bcrypt.
-- =====================================================================
SET search_path TO library, public;

-- ---------- Catalogos independientes ----------
INSERT INTO formats (name) VALUES
  ('Fisico'), ('Digital'), ('Audiolibro'), ('Pasta dura')
ON CONFLICT (name) DO NOTHING;

INSERT INTO categories (name) VALUES
  ('Tecnico'), ('Ficcion'), ('Infantil'), ('Divulgacion'), ('Academico')
ON CONFLICT (name) DO NOTHING;

INSERT INTO genres (name) VALUES
  ('Bases de datos'), ('Ingenieria de software'), ('Ciencia ficcion'),
  ('Novela'), ('Ensayo'), ('Historia'), ('Matematicas')
ON CONFLICT (name) DO NOTHING;

INSERT INTO authors (name) VALUES
  ('Ramez Elmasri'), ('Shamkant Navathe'), ('Martin Fowler'), ('Kent Beck'),
  ('Isaac Asimov'), ('Gabriel Garcia Marquez'), ('Donald Knuth')
ON CONFLICT (name) DO NOTHING;

INSERT INTO concepts (name) VALUES
  ('Normalizacion'), ('Dependencia funcional'), ('Dependencia multivaluada'),
  ('Transaccion'), ('Refactorizacion'), ('Deuda tecnica'), ('Robotica')
ON CONFLICT (name) DO NOTHING;

-- ---------- Libros ----------
INSERT INTO books (isbn, title, publication_year, price, stock, format_id, category_id)
VALUES
  ('978-0133970777', 'Fundamentos de Sistemas de Bases de Datos', 2016, 1250.00, 12,
     (SELECT id FROM formats WHERE name = 'Pasta dura'),
     (SELECT id FROM categories WHERE name = 'Academico')),
  ('978-0134757599', 'Refactoring: Improving the Design of Existing Code', 2018, 980.50, 7,
     (SELECT id FROM formats WHERE name = 'Fisico'),
     (SELECT id FROM categories WHERE name = 'Tecnico')),
  ('978-0553293357', 'Fundacion', 1951, 320.00, 25,
     (SELECT id FROM formats WHERE name = 'Digital'),
     (SELECT id FROM categories WHERE name = 'Ficcion')),
  ('978-0307474728', 'Cien Anos de Soledad', 1967, 410.00, 0,
     (SELECT id FROM formats WHERE name = 'Fisico'),
     (SELECT id FROM categories WHERE name = 'Ficcion')),
  ('978-0201896831', 'The Art of Computer Programming, Vol. 1', 1997, 2100.00, 3,
     (SELECT id FROM formats WHERE name = 'Pasta dura'),
     (SELECT id FROM categories WHERE name = 'Academico'))
ON CONFLICT (isbn) DO NOTHING;

-- ---------- libro ->> autor ----------
INSERT INTO book_authors (book_id, author_id)
SELECT b.id, a.id FROM books b, authors a
 WHERE (b.isbn, a.name) IN (
   ('978-0133970777', 'Ramez Elmasri'),
   ('978-0133970777', 'Shamkant Navathe'),
   ('978-0134757599', 'Martin Fowler'),
   ('978-0134757599', 'Kent Beck'),
   ('978-0553293357', 'Isaac Asimov'),
   ('978-0307474728', 'Gabriel Garcia Marquez'),
   ('978-0201896831', 'Donald Knuth'))
ON CONFLICT DO NOTHING;

-- ---------- libro ->> genero ----------
INSERT INTO book_genres (book_id, genre_id)
SELECT b.id, g.id FROM books b, genres g
 WHERE (b.isbn, g.name) IN (
   ('978-0133970777', 'Bases de datos'),
   ('978-0133970777', 'Ingenieria de software'),
   ('978-0134757599', 'Ingenieria de software'),
   ('978-0553293357', 'Ciencia ficcion'),
   ('978-0553293357', 'Novela'),
   ('978-0307474728', 'Novela'),
   ('978-0201896831', 'Matematicas'))
ON CONFLICT DO NOTHING;

-- ---------- (libro, concepto) -> definicion ----------
-- El mismo concepto "Normalizacion" recibe definiciones distintas segun el libro.
INSERT INTO book_concepts (book_id, concept_id, definition)
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
     'Disciplina que estudia maquinas autonomas; en la obra se rige por las tres leyes formuladas por el autor.')
  ) AS v(isbn, concept, definition)
  JOIN books b    ON b.isbn = v.isbn
  JOIN concepts c ON c.name = v.concept
ON CONFLICT (book_id, concept_id) DO NOTHING;
