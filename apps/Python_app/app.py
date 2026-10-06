"""apps/Python_app/app.py
Entrada de la app de escritorio. Corre local, consume la VM.

Arma las piezas y las conecta:

  TokenBox       un solo juego de tokens (acceso 30 min + refresh 8 h)
                 compartido por los seis clientes. Cuando LoginClient
                 renueva, los demás usan el token nuevo sin enterarse, y
                 el JSON local se actualiza solo.
  Clientes       login, books, users, authors, pedidos, pagos.
  HealthMonitor  semáforos de los seis servicios.
  LibraryApp     la ventana del catálogo, desde la que se abre la de
                 pedidos y pagos.
"""
import tkinter as tk

import config_store
from api_client import TokenBox
from books_client import BooksClient
from health_monitor import HealthMonitor
from login_client import LoginClient
from services_client import AuthorsClient, PagosClient, PedidosClient, UsersClient
from ui_books import LibraryApp


class Backend:
    """
    Los seis clientes y el token compartido, en un solo objeto.

    Se rehace entero cuando cambian los endpoints (Ajustes ⚙), de modo
    que no hay que ir actualizando seis referencias por separado.
    """

    def __init__(self, config, on_tokens_changed=None):
        self.config = config
        urls = config_store.service_urls(config)
        timeout, self.poll = config_store.timings(config)
        self.timeout = timeout

        self.tokens = TokenBox(on_change=on_tokens_changed)
        self.login = LoginClient(urls["login"], timeout, tokens=self.tokens)

        # refresher: lo usan todos los clientes para renovar el token
        # antes de que caduque y para reintentar una vez tras un 401.
        refresher = self.login.refresh

        self.books = BooksClient(urls["books"], timeout, tokens=self.tokens,
                                 refresher=refresher)
        self.users = UsersClient(urls["users"], self.tokens, timeout, refresher)
        self.authors = AuthorsClient(urls["authors"], self.tokens, timeout, refresher)
        self.pedidos = PedidosClient(urls["pedidos"], self.tokens, timeout, refresher)
        self.pagos = PagosClient(urls["pagos"], self.tokens, timeout, refresher)

    def restore(self, session):
        """Recupera la sesión guardada: cookie + los dos tokens."""
        self.login.restore_cookies((session or {}).get("cookies") or {})
        self.tokens.set((session or {}).get("token"),
                        (session or {}).get("refresh_token"))

    def health_clients(self):
        return {"login": self.login, "books": self.books, "users": self.users,
                "authors": self.authors, "pedidos": self.pedidos,
                "pagos": self.pagos}


def main():
    cfg = config_store.load()
    estado = {"cfg": cfg}

    def guardar_tokens(access, refresh):
        """Cada renovación de token se persiste: al reabrir la app, la
        sesión sigue viva sin volver a escribir la contraseña."""
        estado["cfg"] = config_store.save_tokens(estado["cfg"], access, refresh)

    backend = Backend(cfg, on_tokens_changed=guardar_tokens)
    backend.restore(cfg.get("session"))

    def save_session(email, user, cookies, token=None, refresh_token=None):
        estado["cfg"] = config_store.save_session(
            estado["cfg"], email, user, cookies, token=token,
            refresh_token=refresh_token)
        return estado["cfg"]

    def rebuild(nuevo_cfg):
        """Rehace los clientes tras cambiar los endpoints en Ajustes."""
        estado["cfg"] = nuevo_cfg
        nuevo = Backend(nuevo_cfg, on_tokens_changed=guardar_tokens)
        nuevo.restore(nuevo_cfg.get("session"))
        return nuevo

    root = LibraryApp(estado["cfg"], save_session, backend, rebuild, monitor=None)
    monitor = HealthMonitor(backend.health_clients(), backend.poll,
                            root.health_update)
    root.monitor = monitor
    monitor.start()
    root.mainloop()
    monitor.stop()


if __name__ == "__main__":
    main()
