Para lo siguiente, recuerda que el correo debera validarse mediante un servicio como sendmail, que estara alojado en la instancia, no usar un pop. Recuerda que tienes que tener la validacion interna del email, para los correos ya verificados previamente.

Desarrollar un microservicio independiente de autenticación y gestión básica de usuarios para la plataforma de librería en línea existente. El servicio deberá desarrollarse con Python, Flask, Psycopg 3 y PostgreSQL, utilizar la base de datos actual del proyecto y exponer sus respuestas tanto en XML como en JSON.

Requerimientos funcionales: El microservicio deberá implementar las siguientes operaciones:

Método - Endpoint - Función

POST /register Registrar un nuevo usuario

POST /login Autenticar al usuario e iniciar sesión

POST /logout Cerrar la sesión

GET /session Consultar si existe una sesión autenticada

GET /health Verificar el estado del microservicio y PostgreSQL



Todos los endpoints deberán soportar:  ?format=xml  y ?format=json, si no se especifica el parámetro format, XML será el formato predeterminado., por ejemplo: POST /login     POST /login?format=xml deberán responder XML, mientras que:  POST /login?format=json deberá responder JSON. El registro deberá solicitar:

- nombre
- apellido paterno
- apellido materno
- email
- password
 (En la base de datos no esta organizado de esta manera, hay que reestructurar)

El correo deberá validarse antes de registrarse y deberá ser único. La contraseña nunca deberá almacenarse en texto plano. El sistema almacenará únicamente un hash seguro de la contraseña.

La autenticación deberá verificar las credenciales contra PostgreSQL y, cuando sean correctas, crear una sesión del lado de Flask que permita identificar al usuario en solicitudes posteriores.

El correo deberá validarse antes de registrarse y deberá ser único. La contraseña nunca deberá almacenarse en texto plano. El sistema almacenará únicamente un hash seguro de la contraseña.

La autenticación deberá verificar las credenciales contra PostgreSQL y, cuando sean correctas, crear una sesión del lado de Flask que permita identificar al usuario en solicitudes posteriores.

1. Crea el microservicio en el directorio apps/services/login
2. Modifica e integra las tablas necesarias a la base de datos library
3. Despliega el microservicio en el puerto 5000
4. Utiliza Swagger para documentar los endpoints en XML y JSON
5. Valida que todos los endpoint funcionen correctamente

Recuerda, no necesitamos almacenar la contraseña dos veces ni crear una tabla exclusivamente para passwords. password_hash pertenece naturalmente a la cuenta de usuario. 

Considera la reestructuracion de la base de datos para que caiga en lo necesario, y que este normalizado. la base de datos esta en data/squema.sql