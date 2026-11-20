# Library: monorepositorio

Proyecto de integración de aplicaciones con monolito, clientes de escritorio, servicios y base de datos. Los principales componentes son:

| Componente | Ubicación |
|---|---|
| Monolito web | `apps/web_monolito/` |
| Escritorio Electron | `apps/Electron-app/` |
| Escritorio Python/Tkinter | `apps/Python_app/` |
| Escritorio JavaFX y servidor de rastreo independiente | `apps/JavaDesktop_app/` |
| Libros, catálogos y SOAP | `library_soap_service/` |
| Login, usuarios, autores, pedidos y pagos | `apps/services/` |
| Código Python compartido | `packages/library_common/` |
| Esquema, migraciones y datos | `data/` y `db/` |
| Nginx y guía de clientes | `docs/nginx/` |
| Captura de integración local | `evidencias/reverse-proxy/` |
| Scripts y registro de la prueba local | `scripts/reverse-proxy/` |

Los seis clientes de servicios de las aplicaciones de escritorio admiten el gateway. Antes de ejecutarlos, configurar el origen real como se explica en `docs/nginx/CLIENTES.md`; los valores guardados previamente pueden seguir apuntando a puertos directos. Cada aplicación y servicio tiene instrucciones y dependencias en su propia carpeta.

`docs/nginx/library.conf` es una plantilla revisada, no una copia verificada de la VM. Hay que ajustar el nombre del servidor, confirmar el puerto del monolito y ejecutar las validaciones indicadas en `docs/nginx/README.md` antes de instalarla. La captura incluida muestra Nginx local con servicios simulados; la integración con la VM, las credenciales reales y las capturas de las interfaces siguen pendientes de validación en el despliegue.
