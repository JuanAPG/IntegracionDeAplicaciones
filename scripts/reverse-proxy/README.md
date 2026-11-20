# Evidencias del gateway

[La captura de la terminal](../../evidencias/reverse-proxy/captura-pruebas.png) muestra una terminal real con pruebas de PythonTK y Electron contra Nginx local y el registro de una ejecución anterior de la prueba Java contra ese mismo entorno. `registro-pruebas.txt` contiene la salida completa de la ejecución previa. Los upstreams fueron simulados: devuelven el puerto, el método y la ruta recibida. No se conectó a la VM y no se ha probado un login real, una base de datos ni una interfaz gráfica de las tres aplicaciones. Estas evidencias comprueban el direccionamiento probado, no sustituyen capturas del funcionamiento real en la VM.

Las pruebas usan la plantilla `docs/nginx/library.conf`, cambiando solo el puerto de escucha en una copia temporal y agregando servidores HTTP simulados. `prueba_gateway.py`, `prueba_gateway.js` y `PruebaGateway.java` ejecutan código de los clientes. Se verificaron rutas de catálogo, login, roles, autores, envío y saldo de pagos; el saldo llega al puerto 5005. El catálogo/login de Electron y login/refresh de Python se verificaron como construcción de URL, no como peticiones de autenticación. Las demás líneas muestran peticiones HTTP reales a Nginx y respuestas simuladas. El Java se compiló para JDK 21 con JavaFX 21.0.8. Las pruebas de regresión existentes dieron 32/32 en Python y 24/24 en Electron; `nginx -t` pasó previamente en nginx:stable-alpine.

## Para repetir contra simuladores

Con Docker, Python 3 con `requests`, Node 18+, JDK 21 y Maven instalados, desde la raíz del repositorio, ejecutar `bash scripts/reverse-proxy/verificar.sh`. El script usa el puerto local 18081, compila Java con Maven y elimina solo su propio contenedor al terminar. Necesita descargar imágenes y dependencias la primera vez. Las pruebas de las aplicaciones pueden ejecutarse por separado con `cd apps/Python_app && python test_app_smoke.py` y `cd apps/Electron-app && npm ci && npm test`.

## Evidencia pendiente de la VM

Después de que el responsable instale la configuración y ajuste dominio/puerto, capturar cada aplicación funcionando con datos reales, verificar login con una cuenta de prueba y comparar rutas públicas con sus servicios, sin incluir contraseñas ni tokens. Los indicadores `/health` son restringidos a localhost en esta plantilla; desde un equipo externo se muestran como estado desconocido, no como servicio caído. El script local no demuestra el despliegue ni reemplaza esas comprobaciones.
