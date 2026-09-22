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
    saved = (cfg.get("session") or {}).get("cookies") or {}
    c.restore_cookies(saved)
    return c


def make_books(cfg):
    _login, books_url, timeout, _poll = config_store.endpoints(cfg)
    return BooksClient(books_url, timeout)


def main():
    cfg = config_store.load()
    login_client = make_login(cfg)
    books_client = make_books(cfg)

    def save_session(email, user, cookies):
        nonlocal cfg
        cfg = config_store.save_session(cfg, email, user, cookies)
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
