"""Entrada de la app de escritorio. Corre local, consume la VM."""
import tkinter as tk

import config_store
from books_client import BooksClient
from health_monitor import HealthMonitor
from login_client import LoginClient
from ui_books import LibraryApp


def make_login(cfg):
    login_url, _books, timeout, _poll = config_store.endpoints(cfg)
    c = LoginClient(login_url, timeout)
    saved = cfg.get("session") or {}
    c.restore_cookies(saved.get("cookies") or {})
    c.set_token(saved.get("token"))
    return c


def make_books(cfg, token=None):
    _login, books_url, timeout, _poll = config_store.endpoints(cfg)
    b = BooksClient(books_url, timeout)
    b.set_token(token if token is not None
                else (cfg.get("session") or {}).get("token"))
    return b


def main():
    cfg = config_store.load()
    login_client = make_login(cfg)
    books_client = make_books(cfg)

    def save_session(email, user, cookies, token=None):
        nonlocal cfg
        cfg = config_store.save_session(cfg, email, user, cookies, token=token)
        books_client.set_token(token)
        return cfg

    # Instancia real
    root = LibraryApp(cfg, save_session, login_client, books_client,
                      make_login, make_books, monitor=None)
    _login, _books, _timeout, poll = config_store.endpoints(cfg)
    mon = HealthMonitor(login_client, books_client, poll, root.health_update)
    root.monitor = mon
    mon.start()
    root.mainloop()
    mon.stop()


if __name__ == "__main__":
    main()
