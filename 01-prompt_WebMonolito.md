1. Desarrolla una aplicación web monolítica en Node.js en /apps/web_monolito/  que gestione una
librería en línea mediante acceso directo a PostgreSQL. La solución deberá renderizar HTML del lado del servidor, administrar
usuarios registrados, implementar CRUD del modelo normalizado (en
todas las tablas), manejar imágenes y conservar definiciones de
conceptos asociadas a cada libro.
2. Restricción arquitectónica: no se desarrollarán APIs REST, GraphQL,
SOAP ni otros servicios. No se utilizará JSON o XML como formato de
intercambio de datos. El archivo package.json existe únicamente porque
npm lo requiere para administrar el proyecto Node.js
3. Partiendo la base que todo libro tiene de ISBN, título, autor, año de publicación, género, precio, stock, formato, imágenes y conceptos definidos por libro, identifica dependencias funcionales y multivaluadas. 
4. Un libro puede tener varios autores. 
5. Un libro puede pertenecer a varios géneros. 
6. Un libro puede definir muchos conceptos y un mismo concepto puede aparecer en distintos libros con definiciones diferentes. 
7. Un libro puede tener varias imágenes. 
8. Formato y categoría son catálogos independientes. 
9. Debe existir como máximo un administrador
10. Utiliza la macro-arquitectura monolítica para el desarrollo del sistema
11. Utiliza el patrón de diseño MVC para la UI
12. Utiliza el enfoque de organización de código por módulos
13. Utiliza el esquema de base de datos para postgresql data/schema.sql
14. Crea un archivo READE.md con las instrucciones de despliegue en Linux Centos 10 stream, asumiento que tengo instalado el DBMS de Postgresql con el usuario:library_user password: 777 y base de datps library_db