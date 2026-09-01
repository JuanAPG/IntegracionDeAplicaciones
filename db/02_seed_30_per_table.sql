-- =====================================================================
-- db/02_seed_30_per_table.sql
-- DATOS DE DEMOSTRACION: 30 filas en cada tabla de entidad.
--
-- Requisito previo: db/01_schema.sql (y, si se quiere que los datos
-- pasen por los disparadores, tambien db/05_triggers.sql).
--
-- ---------------------------------------------------------------------
-- VOLUMEN POR TABLA
--
--   formats        30    categories     30    genres         30
--   authors        30    concepts       30    books          30
--   users          30    (1 administrador + 29 cuentas de demostracion)
--
--   book_authors   37    book_genres    50    book_concepts  49
--   book_images    36
--
-- Las cuatro ultimas son tablas de UNION que resuelven las dependencias
-- multivaluadas. Llevan MAS de 30 filas a proposito: con exactamente 30
-- pares y 30 libros, cada libro tendria como maximo un autor y un genero,
-- y el modelo dejaria de demostrar precisamente lo que justifica el
-- diseno en 4FN. El minimo de 30 se respeta en todas ellas.
--
-- ---------------------------------------------------------------------
-- IDEMPOTENTE: puede ejecutarse tantas veces como se quiera sin duplicar
-- una sola fila (ON CONFLICT DO NOTHING sobre las claves naturales).
--
-- CALIFICACION DE ESQUEMA: todas las tablas se escriben library.<tabla>.
-- Asi el archivo no depende del search_path y funciona en consolas que
-- abren una sesion por sentencia y detras de PgBouncer en modo
-- transaction pooling, donde un SET suelto no sobrevive. El SET de abajo
-- es por comodidad en psql: SI SU CONSOLA LO RECHAZA, IGNORELO.
--
-- ---------------------------------------------------------------------
-- AVISO DE SEGURIDAD
-- Las 29 cuentas de demostracion comparten la contrasena  Demo123!
-- y el administrador usa  Admin123!  . Ambos son hashes bcrypt reales de
-- contrasenas PUBLICAS: sirven para probar, nunca para producir.
-- ELIMINE ESTAS CUENTAS ANTES DE EXPONER EL SISTEMA A INTERNET.
-- =====================================================================
SET search_path TO library, public;


-- =====================================================================
-- 1. CATALOGOS INDEPENDIENTES  (formato_id -> nombre, categoria_id -> nombre)
-- =====================================================================
INSERT INTO library.formats (name) VALUES
  ('Rustica'),
  ('Pasta dura'),
  ('Pasta blanda'),
  ('Bolsillo'),
  ('Pasta dura ilustrada'),
  ('Edicion de lujo'),
  ('Edicion anotada'),
  ('Edicion conmemorativa'),
  ('Edicion bilingue'),
  ('Facsimil'),
  ('Digital EPUB'),
  ('Digital PDF'),
  ('Digital MOBI'),
  ('Digital AZW3'),
  ('Digital interactivo'),
  ('Audiolibro MP3'),
  ('Audiolibro CD'),
  ('Audiolibro streaming'),
  ('Braille'),
  ('Letra grande'),
  ('Espiral'),
  ('Fasciculo'),
  ('Grapa'),
  ('Novela grafica'),
  ('Manga'),
  ('Caja recopilatoria'),
  ('Impresion bajo demanda'),
  ('Cuaderno de trabajo'),
  ('Mapa desplegable'),
  ('Microfilm')
ON CONFLICT (name) DO NOTHING;

INSERT INTO library.categories (name) VALUES
  ('Tecnico'),
  ('Academico'),
  ('Ficcion'),
  ('No ficcion'),
  ('Infantil'),
  ('Juvenil'),
  ('Divulgacion'),
  ('Referencia'),
  ('Autoayuda'),
  ('Negocios'),
  ('Arte y diseno'),
  ('Historia'),
  ('Biografia'),
  ('Ciencia'),
  ('Matematicas'),
  ('Filosofia'),
  ('Psicologia'),
  ('Salud'),
  ('Cocina'),
  ('Viajes'),
  ('Deportes'),
  ('Religion'),
  ('Politica'),
  ('Economia'),
  ('Derecho'),
  ('Educacion'),
  ('Idiomas'),
  ('Poesia'),
  ('Teatro'),
  ('Comic')
ON CONFLICT (name) DO NOTHING;

INSERT INTO library.genres (name) VALUES
  ('Bases de datos'),
  ('Ingenieria de software'),
  ('Arquitectura de software'),
  ('Programacion'),
  ('Algoritmos'),
  ('Redes'),
  ('Seguridad informatica'),
  ('Inteligencia artificial'),
  ('Sistemas operativos'),
  ('Estructuras de datos'),
  ('Metodologias agiles'),
  ('Gestion de proyectos'),
  ('Diseno de interfaces'),
  ('Ciencia ficcion'),
  ('Fantasia'),
  ('Novela'),
  ('Ensayo'),
  ('Cuento'),
  ('Misterio'),
  ('Terror'),
  ('Romance'),
  ('Aventura'),
  ('Distopia'),
  ('Realismo magico'),
  ('Cronica'),
  ('Biografia'),
  ('Historia'),
  ('Divulgacion cientifica'),
  ('Matematicas'),
  ('Poesia')
ON CONFLICT (name) DO NOTHING;

INSERT INTO library.authors (name) VALUES
  ('Ramez Elmasri'),
  ('Shamkant Navathe'),
  ('Martin Fowler'),
  ('Robert C. Martin'),
  ('Erich Gamma'),
  ('Richard Helm'),
  ('Ralph Johnson'),
  ('John Vlissides'),
  ('Andrew Hunt'),
  ('David Thomas'),
  ('Thomas H. Cormen'),
  ('Charles E. Leiserson'),
  ('Donald Knuth'),
  ('Eric Evans'),
  ('Michael Feathers'),
  ('Kent Beck'),
  ('Frederick P. Brooks Jr.'),
  ('Steve McConnell'),
  ('Andrew S. Tanenbaum'),
  ('Joshua Bloch'),
  ('Brian W. Kernighan'),
  ('Bjarne Stroustrup'),
  ('Martin Kleppmann'),
  ('Marijn Haverbeke'),
  ('Isaac Asimov'),
  ('Gabriel Garcia Marquez'),
  ('Frank Herbert'),
  ('Antoine de Saint-Exupery'),
  ('Jorge Luis Borges'),
  ('Yuval Noah Harari')
ON CONFLICT (name) DO NOTHING;

INSERT INTO library.concepts (name) VALUES
  ('Normalizacion'),
  ('Dependencia funcional'),
  ('Dependencia multivaluada'),
  ('Cuarta forma normal'),
  ('Clave primaria'),
  ('Clave foranea'),
  ('Indice'),
  ('Transaccion'),
  ('Concurrencia'),
  ('Interbloqueo'),
  ('Patron de diseno'),
  ('Principio SOLID'),
  ('Refactorizacion'),
  ('Deuda tecnica'),
  ('Acoplamiento'),
  ('Cohesion'),
  ('Abstraccion'),
  ('Encapsulamiento'),
  ('Polimorfismo'),
  ('Inyeccion de dependencias'),
  ('Arquitectura limpia'),
  ('Prueba unitaria'),
  ('Integracion continua'),
  ('Complejidad algoritmica'),
  ('Recursividad'),
  ('Tabla hash'),
  ('Arbol binario'),
  ('Idempotencia'),
  ('Realismo magico'),
  ('Robotica')
ON CONFLICT (name) DO NOTHING;

-- =====================================================================
-- 2. LIBROS  (ISBN -> titulo, ano, precio, stock, formato, categoria)
-- Formato y categoria se resuelven POR NOMBRE y no por identificador:
-- asi el archivo no depende de los valores que asigne cada SERIAL y
-- sigue siendo valido si el catalogo se recarga en otro orden.
-- =====================================================================
INSERT INTO library.books (isbn, title, publication_year, price, stock, format_id, category_id)
SELECT v.isbn, v.title, v.publication_year, v.price, v.stock, f.id, c.id
  FROM (VALUES
    ('978-0133970777', 'Fundamentos de Sistemas de Bases de Datos', 2016::smallint, 1250.00::numeric, 12, 'Pasta dura', 'Academico'),
    ('978-0134757599', 'Refactoring: Improving the Design of Existing Code', 2018::smallint, 980.50::numeric, 7, 'Rustica', 'Tecnico'),
    ('978-0132350884', 'Clean Code: A Handbook of Agile Software Craftsmanship', 2008::smallint, 890.00::numeric, 15, 'Rustica', 'Tecnico'),
    ('978-0134494166', 'Clean Architecture: A Craftsman''s Guide to Software Structure', 2017::smallint, 950.00::numeric, 9, 'Rustica', 'Tecnico'),
    ('978-0201633610', 'Design Patterns: Elements of Reusable Object-Oriented Software', 1994::smallint, 1120.00::numeric, 6, 'Pasta dura', 'Tecnico'),
    ('978-0201616224', 'The Pragmatic Programmer: From Journeyman to Master', 1999::smallint, 870.00::numeric, 11, 'Rustica', 'Tecnico'),
    ('978-0262033848', 'Introduction to Algorithms', 2009::smallint, 1580.00::numeric, 5, 'Pasta dura', 'Academico'),
    ('978-0201896831', 'The Art of Computer Programming, Volume 1', 1997::smallint, 1750.00::numeric, 3, 'Edicion de lujo', 'Academico'),
    ('978-0321125217', 'Domain-Driven Design: Tackling Complexity in the Heart of Software', 2003::smallint, 1090.00::numeric, 8, 'Pasta dura', 'Tecnico'),
    ('978-0131177055', 'Working Effectively with Legacy Code', 2004::smallint, 940.00::numeric, 10, 'Rustica', 'Tecnico'),
    ('978-0321146533', 'Test Driven Development: By Example', 2002::smallint, 760.00::numeric, 13, 'Rustica', 'Tecnico'),
    ('978-0201835953', 'The Mythical Man-Month: Essays on Software Engineering', 1995::smallint, 690.00::numeric, 14, 'Edicion conmemorativa', 'Negocios'),
    ('978-0735619678', 'Code Complete: A Practical Handbook of Software Construction', 2004::smallint, 1210.00::numeric, 7, 'Pasta dura', 'Tecnico'),
    ('978-0132126953', 'Computer Networks', 2010::smallint, 1340.00::numeric, 4, 'Pasta dura', 'Academico'),
    ('978-0134685991', 'Effective Java', 2018::smallint, 1020.00::numeric, 9, 'Rustica', 'Tecnico'),
    ('978-0131103627', 'The C Programming Language', 1988::smallint, 640.00::numeric, 18, 'Rustica', 'Academico'),
    ('978-0321563842', 'The C++ Programming Language', 2013::smallint, 1450.00::numeric, 5, 'Pasta dura', 'Academico'),
    ('978-1449373320', 'Designing Data-Intensive Applications', 2017::smallint, 1290.00::numeric, 11, 'Rustica', 'Tecnico'),
    ('978-1593279509', 'Eloquent JavaScript', 2018::smallint, 590.00::numeric, 20, 'Digital EPUB', 'Tecnico'),
    ('978-0134092669', 'Modern Operating Systems', 2014::smallint, 1380.00::numeric, 6, 'Pasta dura', 'Academico'),
    ('978-0553293357', 'Fundacion', 1951::smallint, 320.00::numeric, 25, 'Digital EPUB', 'Ficcion'),
    ('978-0307474728', 'Cien Anos de Soledad', 1967::smallint, 410.00::numeric, 0, 'Rustica', 'Ficcion'),
    ('978-0441013593', 'Dune', 1965::smallint, 450.00::numeric, 16, 'Bolsillo', 'Ficcion'),
    ('978-0156012195', 'El Principito', 1943::smallint, 210.00::numeric, 30, 'Pasta dura ilustrada', 'Infantil'),
    ('978-0060883287', 'El Amor en los Tiempos del Colera', 1985::smallint, 380.00::numeric, 8, 'Rustica', 'Ficcion'),
    ('978-0143039433', 'El Aleph', 1949::smallint, 295.00::numeric, 14, 'Bolsillo', 'Ficcion'),
    ('978-0062316097', 'Sapiens: De Animales a Dioses', 2011::smallint, 520.00::numeric, 22, 'Rustica', 'Divulgacion'),
    ('978-0553380163', 'Yo, Robot', 1950::smallint, 340.00::numeric, 17, 'Audiolibro MP3', 'Ficcion'),
    ('978-0345391803', 'El Fin de la Eternidad', 1955::smallint, 365.00::numeric, 6, 'Bolsillo', 'Ficcion'),
    ('978-8420674247', 'Ficciones', 1944::smallint, 310.00::numeric, 13, 'Edicion anotada', 'Ficcion')
       ) AS v(isbn, title, publication_year, price, stock, format_name, category_name)
  JOIN library.formats    f ON f.name = v.format_name
  JOIN library.categories c ON c.name = v.category_name
ON CONFLICT (isbn) DO NOTHING;

-- =====================================================================
-- 3. MVD  libro ->> autor   (book_authors)
-- =====================================================================
INSERT INTO library.book_authors (book_id, author_id)
SELECT b.id, a.id
  FROM (VALUES
    ('978-0133970777', 'Ramez Elmasri'),
    ('978-0133970777', 'Shamkant Navathe'),
    ('978-0134757599', 'Martin Fowler'),
    ('978-0134757599', 'Kent Beck'),
    ('978-0132350884', 'Robert C. Martin'),
    ('978-0134494166', 'Robert C. Martin'),
    ('978-0201633610', 'Erich Gamma'),
    ('978-0201633610', 'Richard Helm'),
    ('978-0201633610', 'Ralph Johnson'),
    ('978-0201633610', 'John Vlissides'),
    ('978-0201616224', 'Andrew Hunt'),
    ('978-0201616224', 'David Thomas'),
    ('978-0262033848', 'Thomas H. Cormen'),
    ('978-0262033848', 'Charles E. Leiserson'),
    ('978-0201896831', 'Donald Knuth'),
    ('978-0321125217', 'Eric Evans'),
    ('978-0131177055', 'Michael Feathers'),
    ('978-0321146533', 'Kent Beck'),
    ('978-0201835953', 'Frederick P. Brooks Jr.'),
    ('978-0735619678', 'Steve McConnell'),
    ('978-0132126953', 'Andrew S. Tanenbaum'),
    ('978-0134685991', 'Joshua Bloch'),
    ('978-0131103627', 'Brian W. Kernighan'),
    ('978-0321563842', 'Bjarne Stroustrup'),
    ('978-1449373320', 'Martin Kleppmann'),
    ('978-1593279509', 'Marijn Haverbeke'),
    ('978-0134092669', 'Andrew S. Tanenbaum'),
    ('978-0553293357', 'Isaac Asimov'),
    ('978-0307474728', 'Gabriel Garcia Marquez'),
    ('978-0441013593', 'Frank Herbert'),
    ('978-0156012195', 'Antoine de Saint-Exupery'),
    ('978-0060883287', 'Gabriel Garcia Marquez'),
    ('978-0143039433', 'Jorge Luis Borges'),
    ('978-0062316097', 'Yuval Noah Harari'),
    ('978-0553380163', 'Isaac Asimov'),
    ('978-0345391803', 'Isaac Asimov'),
    ('978-8420674247', 'Jorge Luis Borges')
       ) AS v(isbn, author_name)
  JOIN library.books   b ON b.isbn = v.isbn
  JOIN library.authors a ON a.name = v.author_name
ON CONFLICT (book_id, author_id) DO NOTHING;

-- =====================================================================
-- 4. MVD  libro ->> genero   (book_genres)
-- =====================================================================
INSERT INTO library.book_genres (book_id, genre_id)
SELECT b.id, g.id
  FROM (VALUES
    ('978-0133970777', 'Bases de datos'),
    ('978-0133970777', 'Ingenieria de software'),
    ('978-0134757599', 'Ingenieria de software'),
    ('978-0134757599', 'Arquitectura de software'),
    ('978-0132350884', 'Ingenieria de software'),
    ('978-0132350884', 'Programacion'),
    ('978-0134494166', 'Arquitectura de software'),
    ('978-0134494166', 'Ingenieria de software'),
    ('978-0201633610', 'Arquitectura de software'),
    ('978-0201633610', 'Programacion'),
    ('978-0201616224', 'Ingenieria de software'),
    ('978-0201616224', 'Metodologias agiles'),
    ('978-0262033848', 'Algoritmos'),
    ('978-0262033848', 'Estructuras de datos'),
    ('978-0262033848', 'Matematicas'),
    ('978-0201896831', 'Algoritmos'),
    ('978-0201896831', 'Matematicas'),
    ('978-0321125217', 'Arquitectura de software'),
    ('978-0131177055', 'Ingenieria de software'),
    ('978-0321146533', 'Metodologias agiles'),
    ('978-0321146533', 'Ingenieria de software'),
    ('978-0201835953', 'Gestion de proyectos'),
    ('978-0201835953', 'Ensayo'),
    ('978-0735619678', 'Ingenieria de software'),
    ('978-0132126953', 'Redes'),
    ('978-0132126953', 'Seguridad informatica'),
    ('978-0134685991', 'Programacion'),
    ('978-0131103627', 'Programacion'),
    ('978-0321563842', 'Programacion'),
    ('978-1449373320', 'Bases de datos'),
    ('978-1449373320', 'Arquitectura de software'),
    ('978-1593279509', 'Programacion'),
    ('978-1593279509', 'Diseno de interfaces'),
    ('978-0134092669', 'Sistemas operativos'),
    ('978-0553293357', 'Ciencia ficcion'),
    ('978-0553293357', 'Novela'),
    ('978-0307474728', 'Novela'),
    ('978-0307474728', 'Realismo magico'),
    ('978-0441013593', 'Ciencia ficcion'),
    ('978-0441013593', 'Aventura'),
    ('978-0156012195', 'Cuento'),
    ('978-0060883287', 'Novela'),
    ('978-0060883287', 'Romance'),
    ('978-0143039433', 'Cuento'),
    ('978-0062316097', 'Divulgacion cientifica'),
    ('978-0062316097', 'Historia'),
    ('978-0553380163', 'Ciencia ficcion'),
    ('978-0345391803', 'Ciencia ficcion'),
    ('978-8420674247', 'Cuento'),
    ('978-8420674247', 'Ensayo')
       ) AS v(isbn, genre_name)
  JOIN library.books  b ON b.isbn = v.isbn
  JOIN library.genres g ON g.name = v.genre_name
ON CONFLICT (book_id, genre_id) DO NOTHING;

-- =====================================================================
-- 5. FD SOBRE CLAVE COMPUESTA  (libro, concepto) -> definicion
-- Este es el punto central del modelo. Observe que 'Refactorizacion',
-- 'Patron de diseno', 'Principio SOLID', 'Complejidad algoritmica',
-- 'Deuda tecnica', 'Concurrencia', 'Robotica' y 'Realismo magico'
-- aparecen en VARIOS libros con definiciones DISTINTAS. Si la definicion
-- viviera en la tabla concepts, estos datos serian irrepresentables.
-- =====================================================================
INSERT INTO library.book_concepts (book_id, concept_id, definition)
SELECT b.id, c.id, v.definition
  FROM (VALUES
    ('978-0133970777', 'Normalizacion',
       'Proceso de descomponer relaciones para eliminar redundancia y anomalias de insercion, borrado y actualizacion, avanzando por formas normales sucesivas.'),
    ('978-0133970777', 'Dependencia funcional',
       'Restriccion X -> Y segun la cual cada valor de X determina un unico valor de Y en toda instancia valida de la relacion.'),
    ('978-0133970777', 'Dependencia multivaluada',
       'Restriccion X ->> Y en la que un valor de X determina un CONJUNTO de valores de Y independiente del resto de atributos.'),
    ('978-0133970777', 'Cuarta forma normal',
       'Una relacion esta en 4FN si esta en Boyce-Codd y no contiene dependencias multivaluadas no triviales sobre atributos que no sean superclave.'),
    ('978-0133970777', 'Clave foranea',
       'Atributo que referencia la clave primaria de otra relacion y cuya integridad referencial hace cumplir el motor.'),
    ('978-0133970777', 'Indice',
       'Estructura auxiliar, habitualmente un arbol B+, que acelera la busqueda a costa de espacio y de un coste anadido en cada escritura.'),
    ('978-0133970777', 'Transaccion',
       'Unidad atomica de trabajo que cumple las propiedades ACID: o se aplican todos sus efectos o ninguno.'),
    ('978-0134757599', 'Refactorizacion',
       'Cambio en la estructura interna del codigo que no altera su comportamiento observable, aplicado en pasos pequenos y respaldado por pruebas.'),
    ('978-0134757599', 'Deuda tecnica',
       'Coste futuro que se asume al elegir una solucion rapida en lugar de la correcta; se paga con intereses en cada cambio posterior.'),
    ('978-0134757599', 'Patron de diseno',
       'Refactorizacion de destino: una estructura conocida hacia la que conviene mover el codigo cuando el olor detectado lo justifica.'),
    ('978-0134757599', 'Acoplamiento',
       'Grado en que un modulo conoce los detalles internos de otro; reducirlo es el objetivo de la mayoria de las refactorizaciones.'),
    ('978-0132350884', 'Refactorizacion',
       'Disciplina de dejar el codigo mas limpio de como se encontro, aplicada de forma continua y no como una fase separada del proyecto.'),
    ('978-0132350884', 'Cohesion',
       'Medida de cuanto se relacionan entre si las responsabilidades de una clase: alta cohesion significa que todas sus variables las usan casi todos sus metodos.'),
    ('978-0132350884', 'Deuda tecnica',
       'Desorden que se acumula cuando se antepone la entrega a la limpieza; su sintoma es que la productividad del equipo cae con el tiempo.'),
    ('978-0134494166', 'Principio SOLID',
       'Cinco principios de diseno orientado a objetos: responsabilidad unica, abierto/cerrado, sustitucion de Liskov, segregacion de interfaces e inversion de dependencias.'),
    ('978-0134494166', 'Arquitectura limpia',
       'Organizacion en capas concentricas donde las dependencias apuntan siempre hacia dentro y las reglas de negocio no conocen los detalles de entrega ni de persistencia.'),
    ('978-0134494166', 'Inyeccion de dependencias',
       'Tecnica por la que un componente recibe sus colaboradores desde fuera en lugar de construirlos, lo que permite invertir la direccion de las dependencias.'),
    ('978-0134494166', 'Abstraccion',
       'Frontera estable que separa la politica de negocio del detalle volatil; en esta arquitectura toda dependencia debe apuntar hacia la abstraccion.'),
    ('978-0201633610', 'Patron de diseno',
       'Solucion reutilizable a un problema recurrente de diseno, descrita por su nombre, su contexto, su solucion y sus consecuencias.'),
    ('978-0201633610', 'Principio SOLID',
       'Programar contra interfaces y favorecer la composicion sobre la herencia, base conceptual de los patrones del catalogo.'),
    ('978-0201633610', 'Polimorfismo',
       'Capacidad de invocar la misma operacion sobre objetos de clases distintas y obtener el comportamiento propio de cada una.'),
    ('978-0201633610', 'Encapsulamiento',
       'Ocultacion del detalle que varia detras de una interfaz estable; es el criterio con el que se decide que encapsular en cada patron.'),
    ('978-0201616224', 'Deuda tecnica',
       'Ventanas rotas: cada defecto que se deja sin arreglar autoriza el siguiente y acelera la degradacion del sistema.'),
    ('978-0201616224', 'Idempotencia',
       'Propiedad de una operacion que produce el mismo resultado se ejecute una o varias veces; imprescindible en automatizacion y despliegue.'),
    ('978-0262033848', 'Complejidad algoritmica',
       'Descripcion asintotica del crecimiento del coste de un algoritmo en funcion del tamano de la entrada, expresada con la notacion O grande.'),
    ('978-0262033848', 'Recursividad',
       'Tecnica en la que un procedimiento se define en terminos de si mismo sobre un subproblema menor, con un caso base que garantiza la terminacion.'),
    ('978-0262033848', 'Tabla hash',
       'Estructura que aplica una funcion de dispersion a la clave para obtener acceso en tiempo constante promedio, con resolucion de colisiones.'),
    ('978-0262033848', 'Arbol binario',
       'Estructura jerarquica en la que cada nodo tiene como maximo dos hijos; equilibrada, ofrece busqueda logaritmica.'),
    ('978-0201896831', 'Complejidad algoritmica',
       'Analisis exacto del numero de operaciones elementales de un algoritmo, no solo de su orden asintotico.'),
    ('978-0201896831', 'Recursividad',
       'Herramienta de definicion y de demostracion: los algoritmos recursivos se analizan por induccion sobre el tamano del problema.'),
    ('978-0321125217', 'Abstraccion',
       'Modelo del dominio compartido entre expertos y desarrolladores, expresado en un lenguaje ubicuo comun.'),
    ('978-0321125217', 'Acoplamiento',
       'Relacion entre contextos delimitados, que se gestiona con mapas de contexto en lugar de con un modelo unico para toda la organizacion.'),
    ('978-0131177055', 'Prueba unitaria',
       'Prueba rapida y aislada que se escribe primero para poder modificar codigo heredado con una red de seguridad.'),
    ('978-0131177055', 'Acoplamiento',
       'Motivo por el que el codigo heredado no se puede probar: romper las costuras es el primer paso para cubrirlo con pruebas.'),
    ('978-0321146533', 'Prueba unitaria',
       'Pieza central del ciclo rojo-verde-refactor: primero se escribe la prueba que falla, despues el codigo minimo que la hace pasar.'),
    ('978-0321146533', 'Refactorizacion',
       'Tercer paso del ciclo: una vez la prueba pasa, se mejora el diseno sin cambiar el comportamiento.'),
    ('978-0735619678', 'Prueba unitaria',
       'Una de las varias tecnicas de construccion, complementaria a la revision por pares y a las aserciones.'),
    ('978-0735619678', 'Abstraccion',
       'Principal herramienta contra la complejidad: gestionar la complejidad esencial es el imperativo tecnico del software.'),
    ('978-0132126953', 'Concurrencia',
       'Ejecucion simultanea de procesos que compiten por el medio, resuelta con protocolos de acceso multiple y control de errores.'),
    ('978-1449373320', 'Transaccion',
       'Agrupacion de lecturas y escrituras que el sistema trata como una unidad, con niveles de aislamiento que definen que anomalias se permiten.'),
    ('978-1449373320', 'Concurrencia',
       'Origen de las anomalias de lectura sucia, lectura no repetible y escritura perdida en sistemas distribuidos.'),
    ('978-1449373320', 'Idempotencia',
       'Requisito para poder reintentar una peticion con seguridad cuando la red no confirma si la primera llego.'),
    ('978-1449373320', 'Indice',
       'Estructura secundaria cuyo coste de mantenimiento en escritura debe compararse siempre con la ganancia en lectura.'),
    ('978-0134092669', 'Interbloqueo',
       'Situacion en la que un conjunto de procesos se espera mutuamente y ninguno puede avanzar; se previene, se evita o se detecta.'),
    ('978-0134092669', 'Concurrencia',
       'Ejecucion intercalada de procesos sobre uno o varios nucleos, coordinada por el planificador del sistema operativo.'),
    ('978-0553293357', 'Robotica',
       'Disciplina que gobierna el comportamiento de las maquinas inteligentes mediante leyes explicitas y jerarquicas.'),
    ('978-0553380163', 'Robotica',
       'Las tres leyes que ningun robot positronico puede violar, y las paradojas que surgen cuando entran en conflicto.'),
    ('978-0307474728', 'Realismo magico',
       'Narrativa en la que lo extraordinario se cuenta con la misma naturalidad que lo cotidiano, sin que los personajes se sorprendan.'),
    ('978-8420674247', 'Realismo magico',
       'Construccion de laberintos conceptuales donde lo fantastico se presenta como una consecuencia logica y erudita.')
       ) AS v(isbn, concept_name, definition)
  JOIN library.books    b ON b.isbn = v.isbn
  JOIN library.concepts c ON c.name = v.concept_name
ON CONFLICT (book_id, concept_id) DO NOTHING;

-- =====================================================================
-- 6. MVD  libro ->> imagen   (book_images)
-- Como maximo una portada por libro: lo garantiza el indice unico
-- parcial ux_book_images_one_cover, no la aplicacion.
-- =====================================================================
-- 6.a  PORTADAS: una por libro.
--
-- Va en una sentencia PROPIA, separada de las imagenes adicionales, y el
-- motivo es el disparador trg_book_images_first_cover: las filas que
-- inserta un mismo comando NO son visibles para las consultas que ese
-- mismo comando ejecuta. Si portadas y adicionales fueran un solo INSERT,
-- el disparador creeria que cada libro sigue sin imagenes y marcaria
-- TODAS como portada, chocando con ux_book_images_one_cover.
INSERT INTO library.book_images (book_id, url, is_cover)
SELECT b.id, v.url, v.is_cover
  FROM (VALUES
    ('978-0133970777',
       'https://covers.openlibrary.org/b/isbn/9780133970777-L.jpg', TRUE),
    ('978-0134757599',
       'https://covers.openlibrary.org/b/isbn/9780134757599-L.jpg', TRUE),
    ('978-0132350884',
       'https://covers.openlibrary.org/b/isbn/9780132350884-L.jpg', TRUE),
    ('978-0134494166',
       'https://covers.openlibrary.org/b/isbn/9780134494166-L.jpg', TRUE),
    ('978-0201633610',
       'https://covers.openlibrary.org/b/isbn/9780201633610-L.jpg', TRUE),
    ('978-0201616224',
       'https://covers.openlibrary.org/b/isbn/9780201616224-L.jpg', TRUE),
    ('978-0262033848',
       'https://covers.openlibrary.org/b/isbn/9780262033848-L.jpg', TRUE),
    ('978-0201896831',
       'https://covers.openlibrary.org/b/isbn/9780201896831-L.jpg', TRUE),
    ('978-0321125217',
       'https://covers.openlibrary.org/b/isbn/9780321125217-L.jpg', TRUE),
    ('978-0131177055',
       'https://covers.openlibrary.org/b/isbn/9780131177055-L.jpg', TRUE),
    ('978-0321146533',
       'https://covers.openlibrary.org/b/isbn/9780321146533-L.jpg', TRUE),
    ('978-0201835953',
       'https://covers.openlibrary.org/b/isbn/9780201835953-L.jpg', TRUE),
    ('978-0735619678',
       'https://covers.openlibrary.org/b/isbn/9780735619678-L.jpg', TRUE),
    ('978-0132126953',
       'https://covers.openlibrary.org/b/isbn/9780132126953-L.jpg', TRUE),
    ('978-0134685991',
       'https://covers.openlibrary.org/b/isbn/9780134685991-L.jpg', TRUE),
    ('978-0131103627',
       'https://covers.openlibrary.org/b/isbn/9780131103627-L.jpg', TRUE),
    ('978-0321563842',
       'https://covers.openlibrary.org/b/isbn/9780321563842-L.jpg', TRUE),
    ('978-1449373320',
       'https://covers.openlibrary.org/b/isbn/9781449373320-L.jpg', TRUE),
    ('978-1593279509',
       'https://covers.openlibrary.org/b/isbn/9781593279509-L.jpg', TRUE),
    ('978-0134092669',
       'https://covers.openlibrary.org/b/isbn/9780134092669-L.jpg', TRUE),
    ('978-0553293357',
       'https://covers.openlibrary.org/b/isbn/9780553293357-L.jpg', TRUE),
    ('978-0307474728',
       'https://covers.openlibrary.org/b/isbn/9780307474728-L.jpg', TRUE),
    ('978-0441013593',
       'https://covers.openlibrary.org/b/isbn/9780441013593-L.jpg', TRUE),
    ('978-0156012195',
       'https://covers.openlibrary.org/b/isbn/9780156012195-L.jpg', TRUE),
    ('978-0060883287',
       'https://covers.openlibrary.org/b/isbn/9780060883287-L.jpg', TRUE),
    ('978-0143039433',
       'https://covers.openlibrary.org/b/isbn/9780143039433-L.jpg', TRUE),
    ('978-0062316097',
       'https://covers.openlibrary.org/b/isbn/9780062316097-L.jpg', TRUE),
    ('978-0553380163',
       'https://covers.openlibrary.org/b/isbn/9780553380163-L.jpg', TRUE),
    ('978-0345391803',
       'https://covers.openlibrary.org/b/isbn/9780345391803-L.jpg', TRUE),
    ('978-8420674247',
       'https://covers.openlibrary.org/b/isbn/9788420674247-L.jpg', TRUE)
       ) AS v(isbn, url, is_cover)
  JOIN library.books b ON b.isbn = v.isbn
 WHERE NOT EXISTS (SELECT 1 FROM library.book_images x
                    WHERE x.book_id = b.id AND x.url = v.url);

-- 6.b  IMAGENES ADICIONALES (no portada) de algunos libros.
INSERT INTO library.book_images (book_id, url, is_cover)
SELECT b.id, v.url, v.is_cover
  FROM (VALUES
    ('978-0133970777',
       'https://covers.openlibrary.org/b/isbn/9780133970777-M.jpg', FALSE),
    ('978-0201633610',
       'https://covers.openlibrary.org/b/isbn/9780201633610-M.jpg', FALSE),
    ('978-0132350884',
       'https://covers.openlibrary.org/b/isbn/9780132350884-M.jpg', FALSE),
    ('978-0441013593',
       'https://covers.openlibrary.org/b/isbn/9780441013593-M.jpg', FALSE),
    ('978-0307474728',
       'https://covers.openlibrary.org/b/isbn/9780307474728-M.jpg', FALSE),
    ('978-0156012195',
       'https://covers.openlibrary.org/b/isbn/9780156012195-M.jpg', FALSE)
       ) AS v(isbn, url, is_cover)
  JOIN library.books b ON b.isbn = v.isbn
 WHERE NOT EXISTS (SELECT 1 FROM library.book_images x
                    WHERE x.book_id = b.id AND x.url = v.url);

-- =====================================================================
-- 7. USUARIOS  (usuario_id -> nombre, email, password_hash, rol)
-- 1 administrador + 29 cuentas de demostracion = 30 filas.
-- La cuenta de Maria Luna esta DESACTIVADA a proposito, para poder
-- probar que un usuario inactivo no puede iniciar sesion.
-- Solo puede haber un administrador: lo impone ux_users_single_admin.
-- =====================================================================
INSERT INTO library.users (full_name, email, password_hash, role, is_active) VALUES
  ('Administrador', 'admin@library.local',
     '$2a$10$z.cmpOvjUaY5nRphPcM5i.Mm3OTZ8rDEnBvCElmFVfVsU8WPWOxQW', 'admin', TRUE),
  ('Laura Mendez', 'laura.mendez@example.com',
     '$2a$10$bkxSiP00iAAR0j.pCQ95Y.N0oKit2z1JemPWLZ8DrXmMzLhKKvG26', 'user', TRUE),
  ('Carlos Rivas', 'carlos.rivas@example.com',
     '$2a$10$bkxSiP00iAAR0j.pCQ95Y.N0oKit2z1JemPWLZ8DrXmMzLhKKvG26', 'user', TRUE),
  ('Ana Torres', 'ana.torres@example.com',
     '$2a$10$bkxSiP00iAAR0j.pCQ95Y.N0oKit2z1JemPWLZ8DrXmMzLhKKvG26', 'user', TRUE),
  ('Diego Salas', 'diego.salas@example.com',
     '$2a$10$bkxSiP00iAAR0j.pCQ95Y.N0oKit2z1JemPWLZ8DrXmMzLhKKvG26', 'user', TRUE),
  ('Maria Luna', 'maria.luna@example.com',
     '$2a$10$bkxSiP00iAAR0j.pCQ95Y.N0oKit2z1JemPWLZ8DrXmMzLhKKvG26', 'user', FALSE),
  ('Jorge Pena', 'jorge.pena@example.com',
     '$2a$10$bkxSiP00iAAR0j.pCQ95Y.N0oKit2z1JemPWLZ8DrXmMzLhKKvG26', 'user', TRUE),
  ('Sofia Cruz', 'sofia.cruz@example.com',
     '$2a$10$bkxSiP00iAAR0j.pCQ95Y.N0oKit2z1JemPWLZ8DrXmMzLhKKvG26', 'user', TRUE),
  ('Miguel Alvarez', 'miguel.alvarez@example.com',
     '$2a$10$bkxSiP00iAAR0j.pCQ95Y.N0oKit2z1JemPWLZ8DrXmMzLhKKvG26', 'user', TRUE),
  ('Valeria Ortiz', 'valeria.ortiz@example.com',
     '$2a$10$bkxSiP00iAAR0j.pCQ95Y.N0oKit2z1JemPWLZ8DrXmMzLhKKvG26', 'user', TRUE),
  ('Andres Gomez', 'andres.gomez@example.com',
     '$2a$10$bkxSiP00iAAR0j.pCQ95Y.N0oKit2z1JemPWLZ8DrXmMzLhKKvG26', 'user', TRUE),
  ('Paula Ramirez', 'paula.ramirez@example.com',
     '$2a$10$bkxSiP00iAAR0j.pCQ95Y.N0oKit2z1JemPWLZ8DrXmMzLhKKvG26', 'user', TRUE),
  ('Hector Nunez', 'hector.nunez@example.com',
     '$2a$10$bkxSiP00iAAR0j.pCQ95Y.N0oKit2z1JemPWLZ8DrXmMzLhKKvG26', 'user', TRUE),
  ('Camila Vega', 'camila.vega@example.com',
     '$2a$10$bkxSiP00iAAR0j.pCQ95Y.N0oKit2z1JemPWLZ8DrXmMzLhKKvG26', 'user', TRUE),
  ('Ruben Castro', 'ruben.castro@example.com',
     '$2a$10$bkxSiP00iAAR0j.pCQ95Y.N0oKit2z1JemPWLZ8DrXmMzLhKKvG26', 'user', TRUE),
  ('Daniela Soto', 'daniela.soto@example.com',
     '$2a$10$bkxSiP00iAAR0j.pCQ95Y.N0oKit2z1JemPWLZ8DrXmMzLhKKvG26', 'user', TRUE),
  ('Emilio Rojas', 'emilio.rojas@example.com',
     '$2a$10$bkxSiP00iAAR0j.pCQ95Y.N0oKit2z1JemPWLZ8DrXmMzLhKKvG26', 'user', TRUE),
  ('Natalia Ibarra', 'natalia.ibarra@example.com',
     '$2a$10$bkxSiP00iAAR0j.pCQ95Y.N0oKit2z1JemPWLZ8DrXmMzLhKKvG26', 'user', TRUE),
  ('Oscar Delgado', 'oscar.delgado@example.com',
     '$2a$10$bkxSiP00iAAR0j.pCQ95Y.N0oKit2z1JemPWLZ8DrXmMzLhKKvG26', 'user', TRUE),
  ('Renata Fuentes', 'renata.fuentes@example.com',
     '$2a$10$bkxSiP00iAAR0j.pCQ95Y.N0oKit2z1JemPWLZ8DrXmMzLhKKvG26', 'user', TRUE),
  ('Ivan Molina', 'ivan.molina@example.com',
     '$2a$10$bkxSiP00iAAR0j.pCQ95Y.N0oKit2z1JemPWLZ8DrXmMzLhKKvG26', 'user', TRUE),
  ('Gabriela Ponce', 'gabriela.ponce@example.com',
     '$2a$10$bkxSiP00iAAR0j.pCQ95Y.N0oKit2z1JemPWLZ8DrXmMzLhKKvG26', 'user', TRUE),
  ('Sergio Aguilar', 'sergio.aguilar@example.com',
     '$2a$10$bkxSiP00iAAR0j.pCQ95Y.N0oKit2z1JemPWLZ8DrXmMzLhKKvG26', 'user', TRUE),
  ('Lucia Farias', 'lucia.farias@example.com',
     '$2a$10$bkxSiP00iAAR0j.pCQ95Y.N0oKit2z1JemPWLZ8DrXmMzLhKKvG26', 'user', TRUE),
  ('Tomas Rendon', 'tomas.rendon@example.com',
     '$2a$10$bkxSiP00iAAR0j.pCQ95Y.N0oKit2z1JemPWLZ8DrXmMzLhKKvG26', 'user', TRUE),
  ('Elena Bustos', 'elena.bustos@example.com',
     '$2a$10$bkxSiP00iAAR0j.pCQ95Y.N0oKit2z1JemPWLZ8DrXmMzLhKKvG26', 'user', TRUE),
  ('Pablo Cardenas', 'pablo.cardenas@example.com',
     '$2a$10$bkxSiP00iAAR0j.pCQ95Y.N0oKit2z1JemPWLZ8DrXmMzLhKKvG26', 'user', TRUE),
  ('Ines Villalobos', 'ines.villalobos@example.com',
     '$2a$10$bkxSiP00iAAR0j.pCQ95Y.N0oKit2z1JemPWLZ8DrXmMzLhKKvG26', 'user', TRUE),
  ('Rodrigo Escobar', 'rodrigo.escobar@example.com',
     '$2a$10$bkxSiP00iAAR0j.pCQ95Y.N0oKit2z1JemPWLZ8DrXmMzLhKKvG26', 'user', TRUE),
  ('Marta Quintero', 'marta.quintero@example.com',
     '$2a$10$bkxSiP00iAAR0j.pCQ95Y.N0oKit2z1JemPWLZ8DrXmMzLhKKvG26', 'user', TRUE)
ON CONFLICT (email) DO NOTHING;

-- =====================================================================
-- COMPROBACION RAPIDA
-- Ejecute esto despues de cargar para confirmar el volumen esperado:
--
--   SELECT 'formats' t, count(*) FROM library.formats
--   UNION ALL SELECT 'categories',    count(*) FROM library.categories
--   UNION ALL SELECT 'genres',        count(*) FROM library.genres
--   UNION ALL SELECT 'authors',       count(*) FROM library.authors
--   UNION ALL SELECT 'concepts',      count(*) FROM library.concepts
--   UNION ALL SELECT 'books',         count(*) FROM library.books
--   UNION ALL SELECT 'users',         count(*) FROM library.users
--   UNION ALL SELECT 'book_authors',  count(*) FROM library.book_authors
--   UNION ALL SELECT 'book_genres',   count(*) FROM library.book_genres
--   UNION ALL SELECT 'book_concepts', count(*) FROM library.book_concepts
--   UNION ALL SELECT 'book_images',   count(*) FROM library.book_images;
-- =====================================================================
