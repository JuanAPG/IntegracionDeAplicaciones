# App escritorio Tkinter — Biblioteca (`Python_app`)

Corre **local** en tu computadora y consume los microservicios de la **VM**:

- login `http://34.51.14.158:5000` · books `http://34.51.14.158:5001`
- locales: `http://localhost:5000` · `http://localhost:5001` (pantalla ⚙)

## Flujo

1. La app abre directo en **libros**: ver y buscar es libre (invitado).
2. **Nuevo / Editar / Eliminar** revalidan la sesión contra el servidor y,
   si no hay sesión vigente, abren el diálogo de autenticación.
3. Botón arriba a la derecha: `Iniciar sesión` ⇄ `email · Salir`; hay
   pantalla **Perfil** con los datos del lector.
4. Semáforos verde (up) / amarillo (degradado: accesible pero DB u otra
   dependencia mal) / rojo (down), con fecha-hora de última comprobación.
5. `⚙` abre la configuración: modificar, **probar**, guardar, persistir y
   restaurar valores.

## Correr

```bash
cd apps/Python_app
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt   # requests + Pillow (portadas)
python3 app.py
```

## Registro y verificación (sendmail de la VM)

- El registro pide nombre, apellidos, correo y contraseña; el servidor
  envía el token por sendmail (vigencia 48 h, un solo uso).
- Pestaña **Verificar cuenta**: pega el token (`GET /verify?token=`).
- Sin verificar, el login responde `403 email_not_verified` y la app lo
  dice en claro (detecta cuentas aún no autenticables).

## Sesión

- Se guarda localmente (`config.json`: email, usuario, cookies, token JWT,
  fechas); **nunca** el password. Al rearrancar se valida con `GET /session`:
  si expiró, aviso controlado + regreso al diálogo de autenticación.
- El login devuelve además un JWT (`token`, `tokenType: Bearer`, 1 h) que la
  app adjunta como `Authorization: Bearer` en cada escritura de libros
  (`POST/PUT/PATCH/DELETE` → 401 sin él, 403 si expiró). El JWT vence antes
  que la cookie (8 h): al expirar se pide login de nuevo.
- Aviso amarillo cuando falta poco para el vencimiento estimado (8 h).

## Libros (siempre JSON: `?output=json`)

- Vistas **Tarjetas** (portadas con Pillow + caché; placeholder “Sin
  portada”; visor ◀ ▶ para varias imágenes) y **Tabla**.
- Filtros: texto general, ISBN, título, año, precio mín/máx.
- Detalle por `GET /books/isbn/{isbn}` con conceptos y definiciones.
- Editar ofrece **PATCH** (solo atributos cambiados) y **PUT** (reemplazo
  completo, con advertencia de que las colecciones omitidas se vacían).
- Eliminar pide confirmación previa.
- Errores comprensibles: ISBN duplicado (409), libro inexistente (404),
  credenciales incorrectas (401), servicio no disponible, sesión expirada.
  Nunca un traceback como respuesta.
