# Capturas

Tomadas el 2026-10-07 contra los seis microservicios corriendo en local
(PostgreSQL y Redis reales, con los datos de `data/seed.sql` más un par de
pedidos y pagos de ejemplo). No son de la VM.

## Microservicios (Swagger UI en `/docs`)

| Servicio | Puerto | Captura |
|---|---|---|
| login | 5000 | `ms_login_docs.png` |
| books | 5001 | `ms_books_docs.png` |
| users | 5002 | `ms_users_docs.png` |
| authors | 5003 | `ms_authors_docs.png` |
| pedidos | 5004 | `ms_pedidos_docs.png` |
| pagos | 5005 | `ms_pagos_docs.png` |

## App de escritorio Electron

`app_electron_catalogo.png`, `app_electron_detalle.png`,
`app_electron_login.png`, `app_electron_pedidos.png`.

## App de escritorio Python (Tkinter)

`app_python_catalogo.png` (tarjetas), `app_python_tabla.png`,
`app_python_pedidos.png` (carrito) y `app_python_mis_pedidos.png`.

Las portadas aparecen como marcador porque las imágenes del catálogo son
URLs externas y el entorno de captura no tiene Internet.
