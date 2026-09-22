# Bitácora de integración — App escritorio Tkinter (`apps/Python_app`)

**Servicios:** login `http://34.51.125.230:5000` · books `http://34.51.125.230:5001`
**App:** corre local (`python3 app.py`), base de datos en la VM.
**Formato:** login usa `?format=json`, books usa `?output=json`.

| Prueba | Acción realizada | Endpoint | Resultado HTTP | Resultado observado |
|---|---|---|---|---|
| 01 | Registro de usuario nuevo (nombre, apellidos, correo, password) | `POST /register?format=json` | 201 | “Registro exitoso. Revisa tu correo…”. Respuesta trae `emailVerification.required:true`, `sent:true`, `expiresAt` (+48 h). |
| 02 | Login correcto con cuenta verificada | `POST /login?format=json` | 200 | “Sesión iniciada”. `authenticated:true`, header muestra `email · Salir`, hint “Sesión activa”. |
| 03 | Intento de login incorrecto (clave errónea) | `POST /login?format=json` | 401 | “Usuario no encontrado o credenciales inválidas.” Sin traceback, la sesión no se crea. |
| 04 | Panel principal al abrir la app | `GET /books?output=json&limit=100` (carga inicial) | 200 | Ventana Biblioteca con 14 libros en tarjetas y tabla; estado “14 libro(s) desde la VM (JSON)”. |
| 05 | Estado de ambos microservicios | `GET /health` (login y books) | 200 / 200 | Semáforos verdes “Login up · HH:MM:SS” y “Books up · HH:MM:SS”. Amarillo si degradado, rojo si caído. |
| 06 | Perfil del usuario autenticado | `GET /session?format=json` | 200 | Diálogo Perfil: nombre, correo, rol, verificado, creada y último acceso. |
| 07 | Catálogo de libros | `GET /books?output=json` | 200 | Lista 14 libros (id, ISBN, título, año, precio, stock, formato, categoría). |
| 08 | Búsqueda o filtrado (título + precio máx) | `GET /books/search?title=sistemas&price_max=1300&output=json` | 200 | Solo libros coincidentes; con filtros vacíos vuelve el catálogo completo. |
| 09 | Detalle de un libro | `GET /books/isbn/978-0133970777?output=json` | 200 | Ficha con autores, géneros, conceptos con definición e imágenes; botón “Ver imágenes (N)”. |
| 10 | Registro de un nuevo libro | `POST /books?output=json` | 201 | “Libro creado / Operación correcta”. Libro `PRUEBA INTEGRACION - 611380` creado con id 20. |
| 11 | Modificación completa mediante PUT | `PUT /books/20?output=json` (objeto entero) | 200 | “Reemplazo completo (PUT): el libro quedó tal como lo enviaste.” Precio 613.00 y stock 7 aplicados. |
| 12 | Modificación parcial mediante PATCH | `PATCH /books/20?output=json` con `{"price": 612.00}` | 200 | “Actualización parcial (PATCH): solo cambió price.” Resto intacto (PUT≠PATCH). |
| 13 | Eliminación de un libro | `DELETE /books/20?output=json` | 200 | “Libro eliminado.” Desaparece de tarjetas y tabla. |
| 14 | Confirmación previa a la eliminación | (diálogo UI, sin endpoint) | — | `askyesno` con título/ISBN; “No” cancela sin llamar al servicio. |
| 15 | Error por ISBN duplicado | `POST /books?output=json` (ISBN existente) | 409 | “ISBN duplicado — ya existe un libro con ese ISBN…” No se crea nada. |
| 16 | Consulta de ISBN inexistente | `GET /books/isbn/000-0000000000?output=json` | 404 | “No existe ningún libro con ISBN …”. Diálogo de error, sin traceback. |
| 17 | Microservicio de libros detenido | `GET /books`, `GET /health` (sin servidor) | Sin conexión (timeout/rechazo) | “Servicio no disponible — sin conexión con …”. Semáforo Books rojo + hora. |
| 18 | Recuperación tras reiniciar el servicio | `GET /health?output=json` + `GET /books` | 200 | Semáforo vuelve a verde, “↻ Recargar” trae el catálogo sin reiniciar la app. |
| 19 | Pantalla de configuración | (diálogo ⚙; botón Probar → `GET /health` ambos) | 200 / 200 | “Login: up · Books: up”. Guardar persiste `config.json`; Restaurar devuelve los valores de la VM. |
| 20 | Funcionamiento con servicios locales | `GET /health` en `http://localhost:5000` y `:5001` | 200 / 200 | Tras cambiar URLs en ⚙ y Guardar, semáforos en verde contra servicios locales. |

## Notas
- PUT sustituye el libro entero (colecciones omitidas quedan vacías, con advertencia previa); PATCH solo toca lo enviado.
- Ningún error muestra traceback: todos los mensajes son texto comprensible con la URL que falló.
