# API Gateway de Library: propuesta para revisión

Basado en `e4cd1d0471a4fe03e512fbd48e96a86746bb987c`. No se ha accedido a la VM ni instalado o validado allí. El archivo `library.conf` es una plantilla: sustituir `library.example.test` por el nombre real y confirmar el puerto efectivo del monolito antes de usarla. El README y `.env.example` de `apps/web_monolito` indican 3000, pero no prueban el despliegue; no hay evidencia de que 5173 esté activo. Conservar cualquier bloque o servicio existente hasta comprobarlo. Usar el Host indicado en las pruebas; el servidor no declara `default_server`, por lo que una petición por IP u otro Host podría seleccionar otro bloque.

La propuesta supone `API_PREFIX` vacío en Books, Users, Authors, Pedidos y Pagos (valor predeterminado del código y `.env.example`) y `SOAP_ENDPOINT_PATH=/soap/clasificacion`; comprobar los valores efectivos de Gunicorn sin revelar secretos. Si difieren, ajustar las rutas internas, no cambiar puertos ni variables a ciegas. La ruta `/api/login` llega a `/login`; las demás rutas de Login usan el espacio `/api/login/`. Las expresiones de recursos conservan método, cuerpo, cabeceras y parámetros; `rewrite ... break` modifica únicamente la ruta, y `proxy_pass` sin URI no vuelve a reemplazarla. `Authorization` y Cookie pasan por defecto. Nginx no valida JWT. Se reservan los nombres auxiliares bajo cada servicio, y se envían 404 de API desconocida en vez de al monolito. El método y la barra final siguen la semántica de Flask: por ejemplo `/api/books/` no equivale necesariamente a `/api/books`. Las aplicaciones deben usar la ruta sin barra cuando así la define Flask.

| Ruta pública | Destino interno en 127.0.0.1 | Observación |
|---|---|---|
| `/api/login` | `:5000/login` | POST |
| `/api/login/{validate-email,register,verify,refresh,logout,session}` | `:5000/{igual}` | Métodos según Login; `/verify` GET/POST |
| `/api/books[/…]` | `:5001/books[/…]` | CRUD, search, isbn |
| `/api/books/{formats,categories,genres,authors,concepts,cloud-concepts}` | `:5001/{igual}` | Catálogos reales de Books; `authors` es distinto al servicio Authors |
| `/api/books/cache/invalidate` | `:5001/cache/invalidate` | POST protegido por el servicio |
| `/api/books/soap/clasificacion` | `:5001/soap/clasificacion` | POST SOAP; depende del valor efectivo de SOAP_ENDPOINT_PATH |
| `/api/users[/…]` | `:5002/users[/…]` | CRUD y subrutas |
| `/api/users/roles[/…]` | `:5002/roles[/…]` | Roles |
| `/api/authors[/…]` | `:5003/authors[/…]` | CRUD y libros del autor |
| `/api/pedidos[/…]` | `:5004/pedidos[/…]` | CRUD, historial, estado |
| `/api/pedidos/envios/<numero>` | `:5004/envios/<numero>` | Seguimiento público definido por Pedidos |
| `/api/pagos[/…]` | `:5005/pagos[/…]` | CRUD disponible según código |
| `/api/pagos/metodos` | `:5005/metodos` | Métodos de pago |
| `/api/pagos/pedidos/<id>/saldo` | `:5005/pedidos/<id>/saldo` | La regla específica evita enviar el saldo a Pedidos |
| `/api/<servicio>/health` | `:puerto/health` | Solo localhost; seis reglas exactas |
| `/` y otras rutas fuera de `/api` | `:3000` | Monolito, sujeto a verificación |

Los seis servicios definen `/docs/`, `/docs/static`, `/openapi.json` y `/metrics`. No se publican en esta plantilla. Para conservar acceso administrativo usar un túnel SSH o consultar localmente el puerto del servicio; Swagger necesita sus rutas originales, recursos estáticos y URLs de OpenAPI, por lo que no basta con un proxy de `/docs/` bajo un prefijo. El WSDL es un archivo del repositorio, no se identificó una ruta Flask que lo sirva. La configuración antigua puede exponer otras URLs directas: inventariarlas antes de sustituirla, incluida cualquier dependencia externa de Swagger o SOAP. El login genera enlaces de verificación con `MAIL_VERIFY_BASE_URL` o `request.host_url`, agregando `/verify`; comprobar y planear `MAIL_VERIFY_BASE_URL=https://DOMINIO/api/login` para que el enlace público sea correcto, sin cambiar automáticamente la configuración del servicio. Verificar también cookies, CORS, contenido absoluto, redirecciones y URLs generadas de cada aplicación en la VM; este proxy no reescribe cuerpos ni resuelve todas esas dependencias automáticamente.

## Inspección antes de instalar

Ejecutar en la VM, con autorización y sin publicar la salida sensible:

```bash
sudo nginx -T
sudo systemctl status nginx --no-pager
sudo ss -lntp | grep -E ':(80|443|3000|5173|500[0-5])\b'
sudo systemctl list-units --type=service --all | grep -Ei 'library|gunicorn|nginx'
curl -si http://127.0.0.1:3000/library
curl -si http://127.0.0.1:5173/
sudo getsebool httpd_can_network_connect
```

Comprobar en `nginx -T` todos los `listen`, `server_name`, rutas, certificados y includes. Integrar las `location` en el bloque existente si ya atiende el mismo nombre y puerto; no dejar servidores duplicados compitiendo por el mismo nombre ni borrar `default.conf`. Comprobar localmente los endpoints directos y variables efectivas de cada servicio (incluidas `API_PREFIX`, `SOAP_ENDPOINT_PATH`, `MAIL_VERIFY_BASE_URL`) mediante las unidades y sus archivos de entorno, evitando exponer secretos. Verificar que la aplicación de 3000 es efectivamente el monolito y que la configuración previa no tiene funcionalidades necesarias que falten aquí. Si TLS termina en otro proxy, ajustar `X-Forwarded-Proto` y direcciones de cliente solo desde proxies confiables: `$scheme` describe la conexión recibida por este Nginx, y no confiar ciegamente en cabeceras externas.

## Instalación en Fedora (solo después de aprobación)

Copiar la plantilla revisada a `/tmp/library.conf`, editar `server_name`, y si es necesario el puerto verificado. `nginx -T` debe revisarse antes; el respaldo queda fuera de `conf.d` para que Nginx no lo incluya. Los siguientes comandos detienen la secuencia si hay fallo y revierten el archivo si la prueba falla; no cambian ni eliminan otros archivos. Requieren instalar el paquete de política SELinux si no existe. Hacerlo desde una sesión con recuperación disponible.

```bash
set -e
sudo install -d -m 700 /etc/nginx/backup
backup="/etc/nginx/backup/library.conf.$(date +%Y%m%d%H%M%S)"
if sudo test -e /etc/nginx/conf.d/library.conf; then
  sudo cp -a /etc/nginx/conf.d/library.conf "$backup"
else
  backup=""
fi
sudo install -m 644 /tmp/library.conf /etc/nginx/conf.d/library.conf
sudo restorecon -v /etc/nginx/conf.d/library.conf
if sudo nginx -t; then
  sudo systemctl reload nginx
else
  if [ -n "$backup" ]; then
    sudo cp -a "$backup" /etc/nginx/conf.d/library.conf
    sudo restorecon -v /etc/nginx/conf.d/library.conf
  else
    sudo rm -f /etc/nginx/conf.d/library.conf
  fi
  echo 'Prueba fallida: archivo anterior restaurado; Nginx no recargado.' >&2
  exit 1
fi
```

Si SELinux impide conexiones salientes de Nginx, confirmar primero con `getsebool httpd_can_network_connect` y registros AVC (`sudo ausearch -m AVC -ts recent`); si se confirma y se aprueba el cambio, `sudo setsebool -P httpd_can_network_connect 1`. Esto habilita conexiones de red para el dominio httpd en general. No desactivar SELinux. Si falla la recarga pese a `nginx -t`, investigar `systemctl status nginx` y restaurar manualmente el respaldo, volver a probar y recargar.

## Pruebas reales para ejecutar después del despliegue

No se han ejecutado contra la VM. Desde ella, sustituir el Host por el configurado. Examinar cuerpo y código: 200 de raíz no demuestra funcionalidad; 401/403 en rutas protegidas sin token puede ser correcto, 502 indica upstream o SELinux, 404 inesperado puede indicar una ruta/prefijo o bloque equivocado, y 503 puede indicar dependencia caída. Las respuestas de salud pueden indicar fallos de PostgreSQL/Redis. Para salud, verificar también desde una máquina externa que la ruta da 403.

```bash
HOST=library.example.test
BASE=http://127.0.0.1
for svc in login books users authors pedidos pagos; do
  echo "===== $svc ====="
  curl -si -H "Host: $HOST" "$BASE/api/$svc/health?format=json"
done
curl -si -H "Host: $HOST" "$BASE/api/books?output=json&limit=2"
curl -si -H "Host: $HOST" "$BASE/api/authors?format=json&limit=2"
curl -si -H "Host: $HOST" "$BASE/api/users?format=json&limit=2"
curl -si -H "Host: $HOST" "$BASE/api/pedidos?format=json&limit=2"
curl -si -H "Host: $HOST" "$BASE/api/pagos/metodos?format=json"
curl -si -H "Host: $HOST" "$BASE/api/pagos/pedidos/1/saldo?format=json"
```

Para autenticación real usar HTTPS una vez habilitado, una cuenta verificada de prueba y un pedido propio existente. El siguiente ejemplo pide la contraseña sin eco, evita guardarla en argumentos o historial, y deja un archivo temporal con permisos restrictivos para el cuerpo; borrar el archivo y las variables tras la prueba. En la VM se puede usar el nombre DNS real o `--resolve` para TLS. El estado 200 depende de credenciales, rol, datos y servicios; 401/403 sin token no es prueba de éxito funcional.

```bash
BASE=https://library.example.test
umask 077
read -r -p 'Correo de prueba: ' TEST_EMAIL
read -r -s -p 'Contraseña: ' TEST_PASSWORD; echo
export TEST_EMAIL TEST_PASSWORD
payload=$(mktemp)
python3 -c 'import json,os,sys; json.dump({"email":os.environ["TEST_EMAIL"],"password":os.environ["TEST_PASSWORD"]},sys.stdout)' > "$payload"
unset TEST_PASSWORD
response=$(curl -fsS -H 'Content-Type: application/json' --data-binary "@$payload" "$BASE/api/login?format=json")
rm -f "$payload"
TOKEN=$(printf '%s' "$response" | python3 -c 'import json,sys; print(json.load(sys.stdin)["token"])')
unset response TEST_EMAIL
curl -si -H "Authorization: Bearer $TOKEN" "$BASE/api/login/session?format=json"
curl -si -H "Authorization: Bearer $TOKEN" "$BASE/api/users?format=json&limit=2"
curl -si -H "Authorization: Bearer $TOKEN" "$BASE/api/pedidos?format=json&limit=2"
curl -si -H "Authorization: Bearer $TOKEN" "$BASE/api/pagos/metodos?format=json"
# Sustituir 1 por un pedido propio existente.
curl -si -H "Authorization: Bearer $TOKEN" "$BASE/api/pagos/pedidos/1/saldo?format=json"
unset TOKEN
```

El token aparece en los argumentos de curl mientras corre: usar una cuenta de prueba en una máquina confiable. Para comprobar preservación de métodos y cuerpo usar datos de prueba controlados y las operaciones reales documentadas en cada servicio; POST/PUT/PATCH/DELETE pueden modificar datos, no ejecutarlos indiscriminadamente. Comparar respuestas directas al puerto y a través de Nginx con los mismos parámetros y credenciales.

## Inventario de clientes a migrar posteriormente

- `apps/Python_app/config_store.py`, `ui_dialogs.py`: seis bases directas `http://host:5000`…`:5005`, guardadas también en configuración local; el botón por host reconstruye puertos. `login_client.py`, `books_client.py`, `services_client.py` y `api_client.py` concatenan rutas completas y `/health`.
- `apps/Electron-app/src/js/config.js`: catálogo `:5001` + `/books`, otras cinco bases por puerto o valores persistidos en localStorage. `auth.js` y `services.js` agregan rutas completas; revisar UI, valores persistidos y derivación automática.
- `apps/JavaDesktop_app/src/main/java/mx/udem/library/desktop/config/{Config,Service}.java`, `net/ApiClient.java`, `service/*`: seis bases por puerto y concatenación de rutas, configuración persistente y salud. Tracking (`:5900`, `/ws`) es un servicio distinto y no está incluido en esta propuesta.
- `apps/services/escritorio/Ejercicio1.py` y `auth_client.py`: cliente adicional de Login y URL SOAP configurable; revisar si se usan en el despliegue.
- `apps/web_monolito`: usa PostgreSQL directamente (`src/config/database.js`); no se encontraron llamadas a estas seis APIs en `src`. Confirmar configuración de despliegue y consumidores externos antes de concluir que no requiere migración.

No basta cambiar todas las bases a `/api/<servicio>`: por ejemplo, añadir `/books` a `/api/books` duplica el nombre; Login igualmente duplica `/login`. Ajustar la construcción de cada ruta, incluyendo salud, `/roles`, `/envios`, `/metodos` y el saldo de Pagos. Actualizar URLs guardadas y probar sesión, renovación de token y CORS. No se modifica código de clientes en esta entrega.

## Seguridad

Configurar HTTPS con certificado válido y redirección HTTP en bloques revisados, y activar `SESSION_COOKIE_SECURE` en Login solo cuando HTTPS esté operativo de extremo a extremo para el cliente. Mantener Gunicorn, PostgreSQL y Redis en loopback o red privada; tras migrar y verificar todos los consumidores, restringir 5000–5005 y el puerto del monolito tanto en firewalld como en las reglas de ingreso de Google Cloud, evitando bloquear conexiones legítimas. Permitir públicamente solo 80/443 según necesidad; limitar SSH a orígenes autorizados. Mantener métricas, Swagger y administración privados. Revisar exposición de `/cache/invalidate` y autorización del servicio antes de publicarla. No confiar en un `X-Forwarded-For` aportado por el cliente para decisiones de seguridad sin configurar proxies confiables.

## Validación realizada en el entorno de preparación

`nginx -t` pasó en `nginx:stable-alpine` con esta plantilla. Con upstreams simulados se comprobaron las rutas de los seis servicios, complementos de Books, roles, envíos, saldo de Pagos, fallback del monolito y el 404 de API desconocida; las pruebas verificaron además el método, la query y la cabecera Authorization en ejemplos representativos. No sustituyen la prueba en Fedora, la configuración completa de esa VM, las respuestas de Flask, cuerpos, cookies, autenticación real ni las dependencias.
