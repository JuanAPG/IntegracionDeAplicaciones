desarrolla una base de datos en Postgreal, tomando en consideración que más adelante se desarollará un sistema web completo que administre usuarios registrados, implementar CRUD del modelo normalizado (en todas las tablas), manejar imágenes y conservar definiciones de conceptos asociadas a cada libro.

Partiendo de ISBN, título, autor, año de publicación, género, precio, stock, formato, imágenes y conceptos definidos por libro, identifica dependencias funcionales y multivaluadas. · Un libro puede tener varios autores. · Un libro puede pertenecer a varios géneros. · Un libro puede definir muchos conceptos y un mismo concepto puede aparecer en distintos libros con definiciones diferentes. · Un libro puede tener varias imágenes. · Formato y categoría son catálogos independientes. · Debe existir como máximo un administrador

Utiliza la macro-arquitectura monolítica para el desarrollo del sistema

Utiliza el patrón de diseño MVC para la UI

Utiliza el enfoque de organización de código por módulos

Crea el diseño de la base de daos desde un archivo .sql dentro del directorio library/db