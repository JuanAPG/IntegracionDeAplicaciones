"""Ventana principal: libros primero; el CRUD exige sesion validada (auth gate)."""
import threading
import tkinter as tk
from tkinter import messagebox, ttk

import theme
from books_client import books_from_payload, detail_text, row_of
from health_monitor import DEGRADED, DOWN, UP
from images_cache import HAS_PIL, fetch_thumbnail, placeholder_image
from ui_dialogs import AuthDialog, BookDialog, ImageViewer, SettingsDialog


def _run(fn):
    threading.Thread(target=fn, daemon=True).start()


STATE_COLOR = {UP: theme.OK, DEGRADED: "#C8931A", DOWN: theme.DOWN}
STATE_LABEL = {UP: "up", DEGRADED: "degradado", DOWN: "down"}

# Los seis microservicios, en el orden en que se pintan los semáforos.
SERVICIOS_SEMAFORO = (
    ("login", "Login"), ("books", "Libros"), ("users", "Usuarios"),
    ("authors", "Autores"), ("pedidos", "Pedidos"), ("pagos", "Pagos"),
)


class LibraryApp(tk.Tk):
    def __init__(self, config, save_config, backend, rebuild, monitor):
        """
        backend  objeto con los SEIS clientes y el TokenBox compartido
                 (ver app.py). Se recibe entero en vez de cliente por
                 cliente: al cambiar la IP de la VM se reemplaza de una
                 sola vez y no quedan referencias viejas por ahi.
        rebuild  fn(config) -> Backend nuevo, para Ajustes.
        """
        super().__init__()
        self.config = config
        self.save_config = save_config
        self.backend = backend
        self.rebuild = rebuild
        self.login_client = backend.login
        self.books_client = backend.books
        self.tokens = backend.tokens
        self.monitor = monitor
        self.user = (config.get("session") or {}).get("user")
        self.books_cache = []
        self.view_mode = tk.StringVar(value="cards")
        self.card_photos = {}
        self._placeholder = None

        self.title("Biblioteca")
        self.geometry("1120x700")
        self.minsize(980, 620)
        theme.apply(self)
        self.configure(background=theme.BG)

        self._header()
        self._session_banner()
        self._searchbar()
        self._content()
        self._footer()
        self._refresh_auth_ui()
        self._load_books()
        if self.monitor is not None:
            # el monitor llama con (service, state, text, stamp)
            self.monitor.start()
        self._restore_session()
        self.after(60_000, self._session_watchdog)

    # ---- layout ----
    def _header(self):
        bar = ttk.Frame(self, style="Dark.TFrame", padding=(18, 12))
        bar.pack(fill="x")
        left = ttk.Frame(bar, style="Dark.TFrame")
        left.pack(side="left")
        ttk.Label(left, text="❦  Biblioteca", style="Title.TLabel").pack(anchor="w")
        ttk.Label(left, text="Catálogo en la VM · sesión guardada en este equipo",
                  style="Sub.TLabel").pack(anchor="w")
        right = ttk.Frame(bar, style="Dark.TFrame")
        right.pack(side="right")
        # Un semáforo por microservicio. En dos filas de tres para que
        # quepan sin empujar los botones fuera de la ventana.
        sem = ttk.Frame(right, style="Dark.TFrame")
        sem.pack(side="left", padx=(0, 14))
        self.dots = {}
        self.dot_labels = {}
        for indice, (clave, etiqueta) in enumerate(SERVICIOS_SEMAFORO):
            fila, columna = divmod(indice, 3)
            celda = ttk.Frame(sem, style="Dark.TFrame")
            celda.grid(row=fila, column=columna, sticky="w", padx=(0, 10))
            lienzo = tk.Canvas(celda, width=10, height=10, highlightthickness=0,
                               background=theme.SIDEBAR)
            lienzo.pack(side="left", padx=(0, 4))
            self._dot(lienzo, "#8A8177")
            self.dots[clave] = lienzo
            texto = ttk.Label(celda, text=f"{etiqueta} …", style="Dark.TLabel",
                              font=("Helvetica", 8))
            texto.pack(side="left")
            self.dot_labels[clave] = texto

        self.btn_auth = ttk.Button(right, text="Iniciar sesión", style="Ghost.TButton",
                                   command=self._auth_button)
        self.btn_auth.pack(side="left", padx=(0, 8))
        self.btn_orders = ttk.Button(right, text="Pedidos y pagos",
                                     style="Ghost.TButton",
                                     command=self._open_orders)
        self.btn_orders.pack(side="left", padx=(0, 8))
        self.btn_profile = ttk.Button(right, text="Perfil", style="Ghost.TButton",
                                      command=self._open_profile)
        self.btn_profile.pack(side="left", padx=(0, 8))
        ttk.Button(right, text="⚙", width=3, style="Ghost.TButton",
                   command=self._open_settings).pack(side="left")

    def _dot(self, canvas, color):
        canvas.delete("all")
        canvas.create_oval(1, 1, 11, 11, fill=color, outline="")

    def _session_banner(self):
        self.banner = ttk.Label(self, text="", background="#F2C94C",
                                foreground="#3A2E00", padding=(18, 6),
                                font=("Helvetica", 9, "bold"))
        # oculto hasta que haya aviso

    def _show_banner(self, text):
        self.banner.configure(text=text)
        self.banner.pack(fill="x")

    def _hide_banner(self):
        self.banner.pack_forget()

    def _searchbar(self):
        bar = ttk.Frame(self, padding=(18, 12, 18, 0))
        bar.pack(fill="x")
        ttk.Label(bar, text="Buscar").pack(side="left", padx=(0, 8))
        self.e_q = ttk.Entry(bar, width=22)
        self.e_q.pack(side="left", padx=(0, 6))
        self.e_q.bind("<Return>", lambda _e: self._load_books())
        self.f_isbn = self._filter(bar, "ISBN", 14)
        self.f_title = self._filter(bar, "Título", 16)
        self.f_year = self._filter(bar, "Año", 6)
        self.f_pmin = self._filter(bar, "Precio mín", 8)
        self.f_pmax = self._filter(bar, "Precio máx", 8)
        ttk.Button(bar, text="Buscar", command=self._load_books).pack(side="left", padx=(6, 4))
        ttk.Button(bar, text="Limpiar", command=self._clear_filters).pack(side="left")
        self.lbl_hint = ttk.Label(bar, text="", style="Muted.TLabel")
        self.lbl_hint.pack(side="right")

    def _filter(self, parent, label, width):
        ttk.Label(parent, text=label, font=("Helvetica", 9)).pack(side="left", padx=(2, 2))
        e = ttk.Entry(parent, width=width)
        e.pack(side="left", padx=(0, 4))
        e.bind("<Return>", lambda _e: self._load_books())
        return e

    def _clear_filters(self):
        for e in (self.e_q, self.f_isbn, self.f_title, self.f_year, self.f_pmin, self.f_pmax):
            e.delete(0, "end")
        self._load_books()

    def _content(self):
        mid = ttk.Frame(self, padding=(18, 10))
        mid.pack(fill="both", expand=True)
        toolbar = ttk.Frame(mid)
        toolbar.pack(fill="x", pady=(0, 6))
        ttk.Radiobutton(toolbar, text="Tarjetas", value="cards",
                        variable=self.view_mode, command=self._switch_view).pack(side="left")
        ttk.Radiobutton(toolbar, text="Tabla", value="table",
                        variable=self.view_mode, command=self._switch_view).pack(side="left", padx=(8, 0))
        ttk.Button(toolbar, text="Detalle (por ISBN)", command=self._open_detail).pack(side="right")
        ttk.Button(toolbar, text="Imágenes", command=self._open_images).pack(side="right", padx=(0, 6))

        self.view_cards = ttk.Frame(mid)
        self.view_table = ttk.Frame(mid)
        self._build_table(self.view_table)
        self._build_cards(self.view_cards)
        self._switch_view()

        self.detail = tk.Text(mid, height=8, wrap="word", relief="solid",
                              borderwidth=1, font=("Helvetica", 9),
                              background="white", foreground=theme.INK)
        self.detail.pack(fill="x", pady=(8, 0))
        self.detail.insert("1.0", "Selecciona un libro para ver el detalle (se consulta por ISBN).")
        self.detail.configure(state="disabled")

    # ---- tabla ----
    def _build_table(self, parent):
        cols = ("id", "isbn", "title", "year", "price", "stock", "format", "category")
        self.tree = ttk.Treeview(parent, columns=cols, show="headings", height=10)
        heads = {"id": ("ID", 50), "isbn": ("ISBN", 140), "title": ("Título", 280),
                 "year": ("Año", 60), "price": ("Precio", 80), "stock": ("Stock", 60),
                 "format": ("Formato", 110), "category": ("Categoría", 120)}
        for c, (h, w) in heads.items():
            self.tree.heading(c, text=h)
            self.tree.column(c, width=w, anchor="w" if c == "title" else "center")
        vsb = ttk.Scrollbar(parent, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")
        self.tree.bind("<<TreeviewSelect>>", lambda _e: self._show_detail())
        self.tree.bind("<Double-1>", lambda _e: self._open_detail())

    # ---- tarjetas ----
    def _build_cards(self, parent):
        self.cards_canvas = tk.Canvas(parent, highlightthickness=0, background=theme.BG)
        vsb = ttk.Scrollbar(parent, orient="vertical", command=self.cards_canvas.yview)
        self.cards_canvas.configure(yscrollcommand=vsb.set)
        self.cards_canvas.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")
        self.cards_inner = ttk.Frame(self.cards_canvas)
        self.cards_canvas.create_window((0, 0), window=self.cards_inner, anchor="nw")
        self.cards_inner.bind("<Configure>",
                              lambda _e: self.cards_canvas.configure(
                                  scrollregion=self.cards_canvas.bbox("all")))

    def _switch_view(self):
        if self.view_mode.get() == "cards":
            self.view_table.pack_forget()
            self.view_cards.pack(fill="both", expand=True)
        else:
            self.view_cards.pack_forget()
            self.view_table.pack(fill="both", expand=True)

    def _rebuild_cards(self):
        for w in self.cards_inner.winfo_children():
            w.destroy()
        self.card_photos = {}
        if not HAS_PIL:
            ttk.Label(self.cards_inner,
                      text="Instala Pillow para ver portadas (pip install -r requirements.txt).",
                      style="Muted.TLabel").grid(row=0, column=0, sticky="w", pady=8)
        if self._placeholder is None:
            self._placeholder = placeholder_image()
        for i, b in enumerate(self.books_cache):
            card = ttk.Frame(self.cards_inner, style="Card.TFrame", padding=10,
                             borderwidth=1, relief="solid")
            card.grid(row=i // 3, column=i % 3, padx=6, pady=6, sticky="nsew")
            for c in range(3):
                self.cards_inner.columnconfigure(c, weight=1)
            img_lbl = ttk.Label(card, style="Card.TLabel", anchor="center")
            img_lbl.pack()
            if self._placeholder is not None:
                img_lbl.configure(image=self._placeholder)
            title = str(b.get("title", ""))[:42]
            ttk.Label(card, text=title, style="Card.TLabel",
                      font=("Helvetica", 10, "bold"), wraplength=170).pack(pady=(6, 0))
            ttk.Label(card, text=f"ISBN {b.get('isbn','')} · {b.get('publicationYear','')}",
                      style="Card.TLabel", font=("Helvetica", 8)).pack()
            ttk.Label(card, text=f"${b.get('price','')} · stock {b.get('stock','')}",
                      style="Card.TLabel", font=("Helvetica", 9, "bold")).pack()
            card.bind("<Button-1>", lambda _e, b=b: self._select_book(b))
            for child in card.winfo_children():
                child.bind("<Button-1>", lambda _e, b=b: self._select_book(b))
            images = b.get("images", []) or []
            url = images[0].get("url", "") if images else ""
            if url:
                self._load_card_cover(img_lbl, b.get("id"), url)

    def _load_card_cover(self, label, book_id, url):
        def work():
            def done(photo):
                def apply():
                    try:
                        if photo is not None:
                            self.card_photos[book_id] = photo
                            label.configure(image=photo)
                    except tk.TclError:
                        pass
                try:
                    self.after(0, apply)
                except Exception:
                    pass
            fetch_thumbnail(url, done)
        _run(work)

    def _select_book(self, book):
        self._highlight(book)
        self._show_detail(book=book)

    def _highlight(self, book):
        for item in self.tree.get_children():
            vals = self.tree.item(item, "values")
            if vals and str(vals[0]) == str(book.get("id", "")):
                self.tree.selection_set(item)
                self.tree.see(item)
                break

    def _footer(self):
        bar = ttk.Frame(self, padding=(18, 0, 18, 14))
        bar.pack(fill="x")
        ttk.Button(bar, text="↻  Recargar", command=self._load_books).pack(side="left")
        ttk.Button(bar, text="+  Nuevo", style="Accent.TButton",
                   command=self._create).pack(side="left", padx=(8, 0))
        ttk.Button(bar, text="✎  Editar (PATCH/PUT)", command=self._edit).pack(side="left", padx=(8, 0))
        ttk.Button(bar, text="🗑  Eliminar", command=self._delete).pack(side="left", padx=(8, 0))
        self.status = ttk.Label(bar, text="Listo.", style="Muted.TLabel")
        self.status.pack(side="right")

    # ---- sesion ----
    def is_authed(self):
        return bool(self.user)

    def _refresh_auth_ui(self):
        if self.user:
            email = self.user.get("email") or (self.config.get("session") or {}).get("email") or "lector"
            self.btn_auth.configure(text=f"{email} · Salir")
            self.btn_profile.state(["!disabled"])
            self.lbl_hint.configure(text="Sesión activa — puedes gestionar libros.")
        else:
            self.btn_auth.configure(text="Iniciar sesión")
            self.btn_profile.state(["disabled"])
            self.lbl_hint.configure(text="Modo invitado — el CRUD pide iniciar sesión.")
        self._update_expiry_banner()

    def _update_expiry_banner(self):
        import config_store
        state, minutes = config_store.session_expiry_info(self.config.get("session") or {})
        if state == "expired" and self.is_authed():
            self._show_banner("Tu sesión probablemente expiró — se validará con el servidor.")
        elif state == "expiring_soon" and self.is_authed():
            self._show_banner(f"Tu sesión vence en ~{minutes} min — guarda tu trabajo.")
        else:
            self._hide_banner()

    def _session_watchdog(self):
        """Cada minuto: aviso de expiración y revalidación contra el servidor."""
        self._update_expiry_banner()
        if self.is_authed():
            import config_store
            state, _m = config_store.session_expiry_info(self.config.get("session") or {})
            if state == "expired":
                self._server_revalidate()
        self.after(60_000, self._session_watchdog)

    def _server_revalidate(self):
        def work():
            ok, _msg, _user = self.login_client.get_session()
            if not ok:
                self.after(0, self._session_expired)
        _run(work)

    def _session_expired(self):
        self.user = None
        self.tokens.clear()
        self.config = self.save_config(None, None, {}, None)
        self._refresh_auth_ui()
        messagebox.showwarning(
            "Sesión expirada",
            "El servidor indica que la sesión ya no es válida. "
            "Vuelve a iniciar sesión para seguir gestionando libros.",
            parent=self)
        AuthDialog(self, self.login_client, self._on_authenticated)

    def _auth_button(self):
        if self.is_authed():
            if messagebox.askyesno("Cerrar sesión", "¿Cerrar la sesión de este equipo?"):
                _run(self._do_logout)
        else:
            AuthDialog(self, self.login_client, self._on_authenticated)

    def _open_profile(self):
        u = self.user or {}
        email = u.get("email") or (self.config.get("session") or {}).get("email") or "—"
        top = tk.Toplevel(self)
        top.title("Perfil del lector")
        top.geometry("380x360")
        top.resizable(False, False)
        top.transient(self)
        theme.apply(top)
        f = ttk.Frame(top, padding=20)
        f.pack(fill="both", expand=True)
        ttk.Label(f, text="Perfil del lector", font=("Helvetica", 13, "bold")).pack(anchor="w", pady=(0, 10))
        rows = [("Nombre", f"{u.get('nombre','') or ''} {u.get('apellidoPaterno','') or ''}".strip() or "—"),
                ("Nombre completo", u.get("fullName") or "—"),
                ("Correo", email),
                ("Rol", u.get("role") or "—"),
                ("Verificado", "sí" if u.get("emailVerified") else "no"),
                ("Creada", (u.get("createdAt") or "—")[:19]),
                ("Último acceso", (u.get("lastLoginAt") or "—")[:19])]
        for label, value in rows:
            row = ttk.Frame(f)
            row.pack(fill="x", pady=2)
            ttk.Label(row, text=label + ":", width=16, font=("Helvetica", 9, "bold")).pack(side="left")
            ttk.Label(row, text=str(value), wraplength=200).pack(side="left")
        ttk.Button(f, text="Cerrar sesión", command=lambda: (top.destroy(), self._auth_button())).pack(
            fill="x", pady=(14, 0))

    def _on_authenticated(self, email, user):
        self.user = user or {"email": email}
        # El TokenBox ya tiene los dos tokens (lo llenó LoginClient.login);
        # aquí solo se persisten junto con la cookie.
        self.config = self.save_config(
            email, self.user, self.login_client.snapshot_cookies(),
            token=self.tokens.access, refresh_token=self.tokens.refresh)
        self._refresh_auth_ui()
        rol = self.tokens.role or (user or {}).get("role") or "user"
        self.status.configure(text=f"Sesión iniciada como {email} (rol {rol}).")

    def _do_logout(self):
        try:
            self.login_client.logout()
        except Exception:
            pass
        self.user = None
        self.tokens.clear()
        self.config = self.save_config(None, None, {}, None)
        self.after(0, self._refresh_auth_ui)
        self.after(0, lambda: self.status.configure(text="Sesión cerrada en este equipo."))

    def _restore_session(self):
        saved = (self.config.get("session") or {}).get("cookies")
        if not saved:
            return
        self.status.configure(text="Validando sesión guardada con el servidor…")
        def work():
            ok, _msg, user = self.login_client.get_session()
            def done():
                if ok:
                    self.user = user or {}
                    self._refresh_auth_ui()
                    self.status.configure(text="Sesión restaurada y vigente.")
                else:
                    self.user = None
                    self.tokens.clear()
                    self.config = self.save_config(None, None, {}, None)
                    self._refresh_auth_ui()
                    self.status.configure(text="La sesión guardada expiró.")
                    messagebox.showwarning(
                        "Sesión expirada",
                        "Tu sesión anterior ya no es válida. "
                        "Inicia sesión de nuevo para gestionar libros.",
                        parent=self)
            self.after(0, done)
        _run(work)

    def _require_auth(self, action):
        """Gate con revalidación en servidor: action() solo corre con sesión vigente."""
        if not self.is_authed():
            messagebox.showinfo("Solo lectores registrados",
                                "Regístrate o inicia sesión para crear, editar o eliminar libros.\n\nVer y buscar sigue libre.",
                                parent=self)
            AuthDialog(self, self.login_client, self._on_authenticated)
            return
        if self.login_client.token_expired() or self.login_client.token_expiring_soon():
            # El token de acceso dura 30 min, pero ahora hay refresh: en
            # vez de mandar al usuario a iniciar sesión, se renueva. Solo
            # si la renovación falla (refresh caducado, sesión cerrada
            # desde otro sitio o cuenta desactivada) se pide login.
            if not self.login_client.refresh():
                self._session_expired()
                return
            self.config = self.save_config(
                (self.config.get("session") or {}).get("email"), self.user,
                self.login_client.snapshot_cookies(),
                token=self.tokens.access, refresh_token=self.tokens.refresh)
        self.status.configure(text="Validando sesión con el servidor…")
        def work():
            ok, _msg, user = self.login_client.get_session()
            def done():
                if ok:
                    if user:
                        self.user = user
                        self._refresh_auth_ui()
                    action()
                else:
                    self._session_expired()
            try:
                self.after(0, done)
            except Exception:
                pass
        _run(work)

    # ---- semaforos ----
    def health_update(self, service, state, text, stamp):
        """Pinta el semáforo de un servicio. Lo llama el HealthMonitor."""
        def apply():
            lienzo = self.dots.get(service)
            if lienzo is None:
                return
            etiqueta = dict(SERVICIOS_SEMAFORO).get(service, service)
            self._dot(lienzo, STATE_COLOR.get(state, theme.DOWN))
            self.dot_labels[service].configure(
                text=f"{etiqueta} {STATE_LABEL.get(state, state)} · {stamp}")
            if state == DEGRADED:
                self.status.configure(text=f"{etiqueta} degradado: {text[:110]}")
            elif state == DOWN:
                self.status.configure(text=f"{etiqueta} no disponible: {text[:110]}")
        try:
            self.after(0, apply)
        except Exception:
            pass

    def _open_orders(self):
        """Abre la ventana de pedidos y pagos."""
        from ui_orders import OrdersWindow

        OrdersWindow(self, self.backend.pedidos, self.backend.pagos,
                     self.backend.books, self.tokens,
                     on_stock_changed=self._load_books)

    # ---- datos ----
    def _load_books(self):
        params = {"q": self.e_q.get().strip(), "isbn": self.f_isbn.get().strip(),
                  "title": self.f_title.get().strip(), "year": self.f_year.get().strip(),
                  "price_min": self.f_pmin.get().strip(), "price_max": self.f_pmax.get().strip()}
        self.status.configure(text="Cargando libros de la VM (JSON)…")
        def work():
            try:
                if any(params.values()):
                    ok, msg, data = self.books_client.search(**params)
                else:
                    ok, msg, data = self.books_client.list_books(limit=100)
            except Exception as exc:  # noqa: BLE001 - nunca traceback al usuario
                ok, msg, data = False, f"No se pudo completar la consulta: {exc}", None
            self.after(0, lambda: self._books_done(ok, msg, data))
        _run(work)

    def _books_done(self, ok, msg, data):
        if not ok:
            self.status.configure(text=msg)
            messagebox.showerror("Libros", msg, parent=self)
            return
        books = books_from_payload(data)
        self.books_cache = books
        for i in self.tree.get_children():
            self.tree.delete(i)
        for b in books:
            r = row_of(b)
            self.tree.insert("", "end", values=r[:8])
        self._rebuild_cards()
        self.status.configure(text=f"{len(books)} libro(s) desde la VM (JSON).")

    def _selected(self):
        sel = self.tree.selection()
        if not sel:
            if self.books_cache and len(self.books_cache) == 1:
                return self.books_cache[0]
            messagebox.showinfo("Elige un libro", "Selecciona una tarjeta o fila de la tabla.",
                                parent=self)
            return None
        idx = self.tree.index(sel[0])
        if 0 <= idx < len(self.books_cache):
            return self.books_cache[idx]
        return None

    def _show_detail(self, book=None):
        b = book or self._selected_silent()
        if not b:
            return
        self.detail.configure(state="normal")
        self.detail.delete("1.0", "end")
        self.detail.insert("1.0", detail_text(b))
        self.detail.configure(state="disabled")
        # refresco por ISBN para demostrar el endpoint dedicado
        isbn = b.get("isbn", "")
        if isbn:
            def work():
                try:
                    ok, _msg, data = self.books_client.get_by_isbn(isbn)
                except Exception:
                    return
                if ok and isinstance(data, dict) and data.get("book"):
                    fresh = data["book"]
                    def apply():
                        for i, old in enumerate(self.books_cache):
                            if str(old.get("id")) == str(fresh.get("id")):
                                self.books_cache[i] = fresh
                                break
                        self.detail.configure(state="normal")
                        self.detail.delete("1.0", "end")
                        self.detail.insert("1.0", detail_text(fresh))
                        self.detail.configure(state="disabled")
                    try:
                        self.after(0, apply)
                    except Exception:
                        pass
            _run(work)

    def _open_detail(self):
        b = self._selected() or self._selected_silent()
        if not b:
            return
        isbn = b.get("isbn", "")
        self.status.configure(text=f"Consultando detalle por ISBN {isbn}…")
        def work():
            try:
                ok, msg, data = self.books_client.get_by_isbn(isbn)
            except Exception as exc:  # noqa: BLE001
                ok, msg, data = False, f"No se pudo consultar el detalle: {exc}", None
            self.after(0, lambda: self._detail_done(ok, msg, data, b))
        _run(work)

    def _detail_done(self, ok, msg, data, fallback):
        if not ok:
            messagebox.showerror("Detalle", msg, parent=self)
            self.status.configure(text=msg)
            return
        book = data.get("book", fallback) if isinstance(data, dict) else fallback
        top = tk.Toplevel(self)
        top.title(f"{book.get('title','')} — {book.get('isbn','')}")
        top.geometry("560x620")
        top.transient(self)
        theme.apply(top)
        f = ttk.Frame(top, padding=18)
        f.pack(fill="both", expand=True)
        ttk.Label(f, text=str(book.get("title", "")), font=("Helvetica", 14, "bold"),
                  wraplength=500).pack(anchor="w")
        ttk.Label(f, text=f"ISBN {book.get('isbn','')} · id {book.get('id','')}",
                  style="Muted.TLabel").pack(anchor="w", pady=(0, 8))
        cover = ttk.Label(f, background="white", relief="solid", anchor="center")
        cover.pack(pady=4)
        ph = placeholder_image()
        images = book.get("images", []) or []
        first_url = images[0].get("url", "") if images else ""
        if first_url:
            cover.configure(text="cargando portada…")
            def work():
                def done(photo):
                    def apply():
                        if photo is not None:
                            cover.configure(image=photo, text="")
                            cover.image = photo
                        elif ph is not None:
                            cover.configure(image=ph, text="")
                            cover.image = ph
                        else:
                            cover.configure(text="Sin portada")
                    try:
                        self.after(0, apply)
                    except Exception:
                        pass
                fetch_thumbnail(first_url, done)
            _run(work)
        elif ph is not None:
            cover.configure(image=ph)
            cover.image = ph
        else:
            cover.configure(text="Este libro no tiene imagen")
        txt = tk.Text(f, height=16, wrap="word", relief="solid", borderwidth=1,
                      font=("Helvetica", 9))
        txt.pack(fill="both", expand=True, pady=8)
        txt.insert("1.0", detail_text(book))
        txt.configure(state="disabled")
        btns = ttk.Frame(f)
        btns.pack(fill="x")
        n_img = len(images)
        ttk.Button(btns, text=f"Ver imágenes ({n_img})",
                   command=lambda: ImageViewer(self, str(book.get("title", "")), images)).pack(
                       side="left", padx=(0, 6))
        ttk.Button(btns, text="Cerrar", command=top.destroy).pack(side="left")
        self.status.configure(text=f"Detalle de ISBN {book.get('isbn','')} con conceptos.")

    def _open_images(self):
        b = self._selected() or self._selected_silent()
        if not b:
            return
        ImageViewer(self, str(b.get("title", "")), b.get("images", []) or [])

    def _selected_silent(self):
        sel = self.tree.selection()
        if not sel:
            return None
        idx = self.tree.index(sel[0])
        if 0 <= idx < len(self.books_cache):
            return self.books_cache[idx]
        return None

    # ---- CRUD ----
    def _catalog_names(self, name):
        try:
            ok, _msg, items = self.books_client.catalog(name)
        except Exception:
            return []
        names = []
        for it in items or []:
            if isinstance(it, dict):
                names.append(it.get("name", ""))
            elif isinstance(it, str):
                names.append(it)
        return [n for n in names if n]

    def _create(self):
        self._require_auth(self._create_after_gate)

    def _create_after_gate(self):
        def work():
            fmts = self._catalog_names("formats")
            cats = self._catalog_names("categories")
            try:
                self.after(0, lambda: self._create_dialog(fmts, cats))
            except Exception:
                pass
        _run(work)

    def _create_dialog(self, fmts, cats):
        dlg = BookDialog(self, book=None, formats=fmts, categories=cats)
        self.wait_window(dlg)
        if not dlg.result:
            return
        _method, payload = dlg.result
        self.status.configure(text="Creando libro…")
        def work():
            try:
                ok, msg, _data = self.books_client.create(payload)
            except Exception as exc:  # noqa: BLE001
                ok, msg, _data = False, f"No se pudo crear: {exc}", None
            self.after(0, lambda: (self._load_books(),
                                   messagebox.showinfo("Libro creado",
                                                       "Operación correcta: el libro quedó registrado.",
                                                       parent=self) if ok
                                   else messagebox.showerror("No se pudo crear", msg, parent=self)))
        _run(work)

    def _edit(self):
        book = self._selected() or self._selected_silent()
        if not book:
            messagebox.showinfo("Elige un libro", "Selecciona una tarjeta o fila de la tabla.",
                                parent=self)
            return
        self._require_auth(lambda: self._edit_after_gate(book))

    def _edit_after_gate(self, book):
        def work():
            fmts = self._catalog_names("formats")
            cats = self._catalog_names("categories")
            try:
                self.after(0, lambda: self._edit_dialog(book, fmts, cats))
            except Exception:
                pass
        _run(work)

    def _edit_dialog(self, book, fmts, cats):
        dlg = BookDialog(self, book=book, formats=fmts, categories=cats)
        self.wait_window(dlg)
        if not dlg.result:
            return
        method, payload = dlg.result
        if method == "PUT":
            self.status.configure(text=f"Reemplazo completo (PUT) del libro {book.get('id')}…")
        else:
            changed = ", ".join(payload.keys())
            self.status.configure(text=f"Actualización parcial (PATCH: {changed})…")
        def work():
            try:
                if method == "PUT":
                    ok, msg, _data = self.books_client.put(book.get("id"), payload)
                else:
                    ok, msg, _data = self.books_client.patch(book.get("id"), payload)
            except Exception as exc:  # noqa: BLE001
                ok, msg, _data = False, f"No se pudo editar: {exc}", None
            def done():
                self._load_books()
                if ok:
                    what = ("Reemplazo completo (PUT): el libro quedó tal como lo enviaste."
                            if method == "PUT" else
                            f"Actualización parcial (PATCH): solo cambió {', '.join(payload.keys())}.")
                    messagebox.showinfo("Libro actualizado", what, parent=self)
                else:
                    messagebox.showerror("No se pudo editar", msg, parent=self)
            self.after(0, done)
        _run(work)

    def _delete(self):
        book = self._selected() or self._selected_silent()
        if not book:
            messagebox.showinfo("Elige un libro", "Selecciona una tarjeta o fila de la tabla.",
                                parent=self)
            return
        self._require_auth(lambda: self._delete_after_gate(book))

    def _delete_after_gate(self, book):
        if not messagebox.askyesno("Confirmar eliminación",
                                   f"¿Eliminar «{book.get('title','')}»\nISBN {book.get('isbn','')} "
                                   f"(id {book.get('id')})?\n\nEsta acción no se puede deshacer.",
                                   parent=self):
            return
        self.status.configure(text="Eliminando…")
        def work():
            try:
                ok, msg = self.books_client.delete(book.get("id"))
            except Exception as exc:  # noqa: BLE001
                ok, msg = False, f"No se pudo eliminar: {exc}"
            self.after(0, lambda: (self._load_books(),
                                   messagebox.showinfo("Eliminado", msg, parent=self) if ok
                                   else messagebox.showerror("No se pudo eliminar", msg, parent=self)))
        _run(work)

    def _open_settings(self):
        def on_save(cfg):
            import config_store as store
            store.save(cfg)
            self.config = cfg
            # Se rehacen los SEIS clientes de una vez: así no queda
            # ninguno apuntando a la IP anterior.
            self.backend = self.rebuild(cfg)
            self.login_client = self.backend.login
            self.books_client = self.backend.books
            self.tokens = self.backend.tokens
            if self.monitor is not None:
                self.monitor.replace_clients(self.backend.health_clients())
                try:
                    _timeout, poll = store.timings(cfg)
                except Exception:
                    poll = 15
                self.monitor.poll = poll
                self.monitor.check_now()
            self._load_books()

        SettingsDialog(self, self.config, on_save, self.rebuild)
