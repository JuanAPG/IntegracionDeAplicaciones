1. Escribe un microservicio en flask (No usar blueprints) con una conexión a la base de datos de postgres para generar endpoints y realizar las operaciones CRUD de libros. Depositalo en /soap

2. Usa como referenci el esquema de base de datos que esta en data/squema.sql y el diseño del XML definido en /apps/services/soap/library.xml

3. El microservicio debe demostrar todos los libros, un libro, buscar por atributos, modificar un libro, borrar un libro y actualizar un libro.

4. Toma en consideración CORS ya que este servicio será accedido mediante clientes fuera de dominio.

5. Considera los siguientes datos de PostgreSQL: db: library_db, usuario: library_user y password: 777. Uda las variables de entorno .env para no exponer las credenciales. Si es necesario, camvia el .env que tenemos de example al real, puedes consultar los demas prompts para analizar