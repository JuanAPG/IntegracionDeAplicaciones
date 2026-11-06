# Evidencias

| Archivo | Qué muestra | Cuándo |
|---|---|---|
| `01_login_javafx.png` | La aplicación JavaFX arrancada, pantalla de inicio de sesión | 2026-11-05 |
| `02_mapa_rastreo_monterrey.jpg` | El mapa de Leaflet + OpenStreetMap con la ruta real Parque Fundidora → UDEM, el vehículo en movimiento, la estela recorrida y los cinco estados de entrega | 2026-11-05 |

## Lo verificado por consola

```
$ curl http://localhost:5900/health
{"service":"tracking","status":"ok","requireAuth":false,
 "deliveries":0,"subscribers":0,"timeFactor":10.0}

$ (cliente WebSocket real contra ws://localhost:5900/ws?code=LIB-MTY-2026-000043)
SNAPSHOT destino=Estadio BBVA ruta=77 pts estado=Pedido confirmado
  ESTADO -> Preparando pedido
  ESTADO -> Pedido enviado
  ESTADO -> En ruta de entrega
  posicion 25.68213,-100.28688 rumbo=5.3  5.0% En ruta de entrega
total de posiciones recibidas: 23

$ (máquina de estados hasta el final de la ruta)
   1s -> Pedido confirmado      0.0%
   5s -> Preparando pedido      0.0%
  14s -> Pedido enviado         0.0%
  17s -> En ruta de entrega     4.9%
  60s -> En ruta de entrega    75.7%
  90s -> Entregado            100.0%

$ (rutas distintas por código, deterministas)
LIB-MTY-2026-000042 -> UDEM          236 puntos, 16.5 km
LIB-MTY-2026-000043 -> Estadio BBVA   77 puntos,  5.9 km
LIB-MTY-2026-000001 -> Escobedo      230 puntos, 16.8 km
```

## Lo que falta evidenciar, y por qué

Login real, catálogo, cesta, compra y "Mis compras" contra la instancia de GCP.
Los siete componentes de la VM dejaron de responder el 2026-10-30 a las 15:51 y
siguen caídos: la máquina está viva (ICMP y SSH responden) pero ningún proceso
escucha en los puertos 3000 y 5000-5005.

**No se sustituyeron por datos simulados.** El enunciado prohíbe simular
respuestas REST cuando existe un microservicio real, y una captura de datos
inventados no evidencia nada. En cuanto los servicios vuelvan, estas pantallas
se capturan sin tocar una línea de código.
