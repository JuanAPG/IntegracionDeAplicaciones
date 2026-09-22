"""Dialogos: auth (login/registro/verificacion), editor PUT/PATCH,
visor de imagenes y configuracion de endpoints."""
import re
import threading
import tkinter as tk
from tkinter import messagebox, ttk

import theme
from images_cache import HAS_PIL, fetch_thumbnail, placeholder_image

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _run(fn):
    t = threading.Thread(target=fn, daemon=True)
    t.start()
    return t


def _spin(parent, text="Procesando..."):
    top = tk.Toplevel(parent)
    top.title("")
    top.transient(parent)
    top.grab_set()
    top.resizable(False, False)
    frm = ttk.Frame(top, padding=18, style="Card.TFrame")
    frm.pack(fill="both", expand=True)
    ttk.Label(frm, text=text, style="Card.TLabel").pack()
    pb = ttk.Progressbar(frm, mode="indeterminate", length=180)
    pb.pack(pady=(10, 0))
    pb.start(12)
    return top


class AuthDialog(tk.Toplevel):
    """Modal con tabs Iniciar sesion / Registrarse / Verificar cuenta."""

    def __init__(self, parent, login_client, on_authenticated):
        super().__init__(parent)
        self.login_client = login_client
        self.on_authenticated = on_authenticated  # fn(email, user)
        self.title("Accede a la biblioteca")
        self.geometry("440x560")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()
        theme.apply(self)
        self.configure(background=theme.BG)

        ttk.Label(self, text="Tu cuenta de lector",
                  font=("Helvetica", 14, "bold")).pack(pady=(16, 2))
        ttk.Label(self, text="Inicia sesión o regístrate para gestionar libros.",
                  style="Muted.TLabel").pack(pady=(0, 10))

        self.nb = ttk.Notebook(self)
        self.nb.pack(fill="both", expand=True, padx=16, pady=6)
        self._tab_login(self.nb)
        self._tab_register(self.nb)
        self._tab_verify(self.nb)

    # ---- login ----
    def _tab_login(self, nb):
        f = ttk.Frame(nb, padding=16)
        nb.add(f, text="Iniciar sesión")
        ttk.Label(f, text="Correo").pack(anchor="w")
        self.e_email = ttk.Entry(f, width=40)
        self.e_email.pack(fill="x", pady=(2, 10))
        ttk.Label(f, text="Contraseña").pack(anchor="w")
        self.e_pass = ttk.Entry(f, width=40, show="•")
        self.e_pass.pack(fill="x", pady=(2, 14))
        ttk.Button(f, text="Entrar", style="Accent.TButton",
                   command=self._do_login).pack(fill="x")
        ttk.Label(f, text="¿Cuenta nueva sin verificar? Usa la pestaña Verificar cuenta.",
                  style="Muted.TLabel", wraplength=360).pack(pady=(10, 0))
        self.e_email.focus_set()
        self.bind("<Return>", lambda _e: self._do_login())

    def _do_login(self):
        email = self.e_email.get().strip()
        pwd = self.e_pass.get()
        if not EMAIL_RE.match(email):
            messagebox.showwarning("Revisa el correo", "El correo no tiene un formato válido.",
                                   parent=self)
            return
        if not pwd:
            messagebox.showwarning("Falta contraseña", "Escribe tu contraseña.", parent=self)
            return
        spin = _spin(self, "Verificando credenciales...")
        def work():
            ok, msg, user, _code = self.login_client.login(email, pwd)
            self.after(0, lambda: (spin.destroy(), self._login_done(ok, msg, email, user)))
        _run(work)

    def _login_done(self, ok, msg, email, user):
        if ok:
            self.on_authenticated(email, user or {})
            messagebox.showinfo("Bienvenido", "Sesión iniciada. Ya puedes gestionar libros.",
                                parent=self.master)
            self.destroy()
        else:
            messagebox.showerror("No se pudo entrar", msg, parent=self)

    # ---- registro ----
    def _tab_register(self, nb):
        f = ttk.Frame(nb, padding=16)
        nb.add(f, text="Registrarse")
        self.r_nombre = self._field(f, "Nombre")
        self.r_pat = self._field(f, "Apellido paterno")
        self.r_mat = self._field(f, "Apellido materno (opcional)")
        self.r_email = self._field(f, "Correo")
        ttk.Label(f, text="Contraseña (mínimo 6 caracteres)").pack(anchor="w")
        self.r_pass = ttk.Entry(f, show="•")
        self.r_pass.pack(fill="x", pady=(2, 12))
        ttk.Button(f, text="Crear cuenta", style="Accent.TButton",
                   command=self._do_register).pack(fill="x")
        ttk.Label(f, text="El servidor envía un token por sendmail (vigencia 48 h). "
                          "Sin verificarlo no podrás entrar.",
                  style="Muted.TLabel", wraplength=360).pack(pady=(8, 0))

    def _field(self, parent, label):
        ttk.Label(parent, text=label).pack(anchor="w")
        e = ttk.Entry(parent)
        e.pack(fill="x", pady=(2, 8))
        return e

    def _do_register(self):
        nombre = self.r_nombre.get().strip()
        pat = self.r_pat.get().strip()
        mat = self.r_mat.get().strip()
        email = self.r_email.get().strip()
        pwd = self.r_pass.get()
        if not nombre or not pat:
            messagebox.showwarning("Faltan datos", "Nombre y apellido paterno son obligatorios.",
                                   parent=self)
            return
        if not EMAIL_RE.match(email):
            messagebox.showwarning("Revisa el correo", "El correo no tiene un formato válido.",
                                   parent=self)
            return
        if len(pwd) < 6:
            messagebox.showwarning("Contraseña corta", "Mínimo 6 caracteres.", parent=self)
            return
        spin = _spin(self, "Creando tu cuenta...")
        def work():
            ok, msg, _data, _code = self.login_client.register(
                nombre, pat, email, pwd, mat)
            def done():
                spin.destroy()
                if ok:
                    messagebox.showinfo(
                        "Registro exitoso",
                        msg + "\n\nCuando llegue el correo, pega el token en "
                             "la pestaña Verificar cuenta.",
                        parent=self)
                    self.e_email.delete(0, "end")
                    self.e_email.insert(0, email)
                    self.nb.select(2)
                else:
                    messagebox.showerror("No se pudo registrar", msg, parent=self)
            self.after(0, done)
        _run(work)

    # ---- verificación ----
    def _tab_verify(self, nb):
        f = ttk.Frame(nb, padding=16)
        nb.add(f, text="Verificar cuenta")
        ttk.Label(f, text="Token del correo").pack(anchor="w")
        self.v_token = ttk.Entry(f, width=40)
        self.v_token.pack(fill="x", pady=(2, 12))
        ttk.Button(f, text="Verificar correo", style="Accent.TButton",
                   command=self._do_verify).pack(fill="x")
        ttk.Label(f, text="El token es de un solo uso y expira en 48 h. "
                          "Si expiró, regístrate de nuevo para recibir otro.",
                  style="Muted.TLabel", wraplength=360).pack(pady=(8, 0))

    def _do_verify(self):
        token = self.v_token.get().strip()
        if not token:
            messagebox.showwarning("Falta el token", "Pega el token que llegó a tu correo.",
                                   parent=self)
            return
        spin = _spin(self, "Verificando token...")
        def work():
            ok, msg, _user = self.login_client.verify(token)
            def done():
                spin.destroy()
                if ok:
                    messagebox.showinfo("Cuenta verificada", msg, parent=self)
                    self.nb.select(0)
                else:
                    messagebox.showerror("No se pudo verificar", msg, parent=self)
            self.after(0, done)
        _run(work)


class SettingsDialog(tk.Toplevel):
    """Modificar, probar, guardar, persistir y restaurar endpoints."""

    def __init__(self, parent, config, on_save, login_factory, books_factory):
        import config_store
        self._store = config_store
        super().__init__(parent)
        self.config = config
        self.on_save = on_save
        self.login_factory = login_factory
        self.books_factory = books_factory
        self.title("Conexión con microservicios")
        self.geometry("500x520")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()
        theme.apply(self)
        f = ttk.Frame(self, padding=18)
        f.pack(fill="both", expand=True)
        ttk.Label(f, text="Conexión", font=("Helvetica", 13, "bold")).pack(anchor="w")
        ttk.Label(f, text="La base vive en la VM; aquí solo cambian las direcciones.",
                  style="Muted.TLabel").pack(anchor="w", pady=(0, 12))
        ep = config.get("endpoints", {})
        self.e_login = self._row(f, "Login (:5000)", ep.get("login_base_url", ""))
        self.e_books = self._row(f, "Books (:5001)", ep.get("books_base_url", ""))
        self.e_timeout = self._row(f, "Timeout segundos", str(ep.get("timeout", 8)))
        self.e_poll = self._row(f, "Chequeo semáforo cada (seg)", str(ep.get("poll", 15)))
        self.lbl_test = ttk.Label(f, text="Sin probar.", style="Muted.TLabel")
        self.lbl_test.pack(anchor="w", pady=(6, 0))
        btns = ttk.Frame(f)
        btns.pack(fill="x", pady=(10, 0))
        ttk.Button(btns, text="Probar", command=self._test).pack(side="left", padx=(0, 6))
        ttk.Button(btns, text="Restaurar valores", command=self._defaults).pack(side="left")
        ttk.Button(f, text="Guardar", style="Accent.TButton",
                   command=self._save).pack(fill="x", pady=(12, 0))

    def _row(self, parent, label, value):
        ttk.Label(parent, text=label).pack(anchor="w")
        e = ttk.Entry(parent)
        e.insert(0, value)
        e.pack(fill="x", pady=(2, 8))
        return e

    def _draft(self):
        try:
            timeout = max(int(self.e_timeout.get().strip() or 8), 2)
        except ValueError:
            timeout = 8
        try:
            poll = max(int(self.e_poll.get().strip() or 15), 5)
        except ValueError:
            poll = 15
        return {"login_base_url": self.e_login.get().strip().rstrip("/"),
                "books_base_url": self.e_books.get().strip().rstrip("/"),
                "timeout": timeout, "poll": poll}

    def _test(self):
        draft = self._draft()
        self.lbl_test.configure(text="Probando…")
        def work():
            lc = self.login_factory({"endpoints": draft, "session": {}})
            bc = self.books_factory({"endpoints": draft, "session": {}})
            lok, lmsg, _ = lc.health()
            bok, bmsg, _ = bc.health()
            def done():
                self.lbl_test.configure(
                    text=f"Login: {'up' if lok else 'FALLA — ' + lmsg[:80]}   ·   "
                         f"Books: {'up' if bok else 'FALLA — ' + bmsg[:80]}")
            self.after(0, done)
        _run(work)

    def _defaults(self):
        d = self._store.DEFAULTS["endpoints"]
        for entry, key in ((self.e_login, "login_base_url"), (self.e_books, "books_base_url"),
                           (self.e_timeout, "timeout"), (self.e_poll, "poll")):
            entry.delete(0, "end")
            entry.insert(0, str(d[key]))
        self.lbl_test.configure(text="Valores predeterminados (sin guardar aún).")

    def _save(self):
        self.config["endpoints"] = self._draft()
        self.on_save(self.config)
        self.destroy()


class ImageViewer(tk.Toplevel):
    """Consulta las imágenes del libro (navegación ◀ ▶)."""

    def __init__(self, parent, title, images):
        super().__init__(parent)
        self.images = images or []
        self.idx = 0
        self.title(f"Imágenes — {title}")
        self.geometry("360x420")
        self.resizable(False, False)
        self.transient(parent)
        theme.apply(self)
        f = ttk.Frame(self, padding=14)
        f.pack(fill="both", expand=True)
        self.lbl_img = ttk.Label(f, background="white", relief="solid",
                                 anchor="center", width=24)
        self.lbl_img.pack(pady=(0, 8))
        self.lbl_count = ttk.Label(f, text="", style="Muted.TLabel")
        self.lbl_count.pack()
        self.lbl_url = ttk.Label(f, text="", style="Muted.TLabel", wraplength=320)
        self.lbl_url.pack(pady=(4, 8))
        nav = ttk.Frame(f)
        nav.pack()
        ttk.Button(nav, text="◀", width=4, command=lambda: self._go(-1)).pack(side="left", padx=4)
        ttk.Button(nav, text="▶", width=4, command=lambda: self._go(1)).pack(side="left", padx=4)
        self._show()

    def _go(self, step):
        if self.images:
            self.idx = (self.idx + step) % len(self.images)
            self._show()

    def _show(self):
        if not self.images:
            ph = placeholder_image()
            if ph is not None:
                self.lbl_img.configure(image=ph)
                self.lbl_img.image = ph
            else:
                self.lbl_img.configure(text="Sin imagen")
            self.lbl_count.configure(text="Este libro no tiene imágenes.")
            self.lbl_url.configure(text="")
            return
        item = self.images[self.idx]
        url = item.get("url", "")
        cover = " · portada" if item.get("isCover") else ""
        self.lbl_count.configure(text=f"Imagen {self.idx + 1} de {len(self.images)}{cover}")
        self.lbl_url.configure(text=url)
        self.lbl_img.configure(text="cargando…", image="")
        def work():
            def done(photo):
                def apply():
                    if photo is not None:
                        self.lbl_img.configure(image=photo, text="")
                        self.lbl_img.image = photo
                    else:
                        ph = placeholder_image(text="No se pudo cargar")
                        if ph is not None:
                            self.lbl_img.configure(image=ph, text="")
                            self.lbl_img.image = ph
                        else:
                            self.lbl_img.configure(text="No se pudo cargar")
                try:
                    self.after(0, apply)
                except Exception:
                    pass
            fetch_thumbnail(url, done)
        _run(work)


class BookDialog(tk.Toplevel):
    """Crear (POST) o editar. En edición ofrece PATCH parcial y PUT completo."""

    def __init__(self, parent, book=None, formats=(), categories=()):
        super().__init__(parent)
        self.book = book or {}
        self.is_edit = book is not None
        self.result = None   # (method, payload)
        self.title("Editar libro" if self.is_edit else "Nuevo libro")
        self.geometry("540x700")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()
        theme.apply(self)

        outer = ttk.Frame(self, padding=14)
        outer.pack(fill="both", expand=True)
        canvas = tk.Canvas(outer, highlightthickness=0, background=theme.BG)
        vsb = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=vsb.set)
        canvas.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")
        f = ttk.Frame(canvas, padding=10)
        canvas.create_window((0, 0), window=f, anchor="nw")
        f.bind("<Configure>", lambda _e: canvas.configure(scrollregion=canvas.bbox("all")))

        head = "Editar libro — elige parcial o reemplazo" if self.is_edit else "Nuevo libro"
        ttk.Label(f, text=head, font=("Helvetica", 13, "bold")).pack(anchor="w", pady=(0, 10))
        self.entries = {}
        b = self.book
        self._row(f, "isbn", "ISBN*", str(b.get("isbn", "")))
        self._row(f, "title", "Título*", str(b.get("title", "")))
        self._row(f, "year", "Año publicación*",
                  str(b.get("publicationYear", "") if b.get("publicationYear") is not None else ""))
        self._row(f, "price", "Precio*",
                  str(b.get("price", "") if b.get("price") is not None else ""))
        self._row(f, "stock", "Stock", str(b.get("stock", 0) if b.get("stock") is not None else 0))
        self._combo(f, "format", "Formato* (id o nombre)", _name(b.get("format")), list(formats))
        self._combo(f, "category", "Categoría* (id o nombre)", _name(b.get("category")),
                    list(categories))
        self._row(f, "authors", "Autores (separados por coma)",
                  ", ".join(a.get("name", "") for a in b.get("authors", []) or []))
        self._row(f, "genres", "Géneros (separados por coma)",
                  ", ".join(g.get("name", "") for g in b.get("genres", []) or []))
        ttk.Label(f, text="Conceptos (una línea por concepto: nombre :: definición)").pack(anchor="w")
        self.txt_concepts = tk.Text(f, height=4, width=58, relief="solid", borderwidth=1)
        self.txt_concepts.pack(fill="x", pady=(2, 8))
        for c in b.get("concepts", []) or []:
            self.txt_concepts.insert("end", f"{c.get('name','')} :: {c.get('definition','')}\n")
        self._row(f, "images", "Imágenes URLs (coma; la 1ª es portada)",
                  ", ".join(i.get("url", "") for i in b.get("images", []) or []))

        if self.is_edit:
            ttk.Button(f, text="Guardar parcial (PATCH) — solo lo cambiado",
                       style="Accent.TButton", command=lambda: self._ok("PATCH")).pack(fill="x", pady=(12, 0))
            ttk.Button(f, text="Reemplazar todo (PUT) — objeto completo",
                       command=lambda: self._ok("PUT")).pack(fill="x", pady=(6, 0))
        else:
            ttk.Button(f, text="Crear libro", style="Accent.TButton",
                       command=lambda: self._ok("POST")).pack(fill="x", pady=(12, 0))
        ttk.Button(f, text="Cancelar", command=self.destroy).pack(fill="x", pady=(6, 0))

    def _row(self, parent, key, label, value):
        ttk.Label(parent, text=label).pack(anchor="w")
        e = ttk.Entry(parent)
        e.insert(0, value)
        e.pack(fill="x", pady=(2, 8))
        self.entries[key] = e

    def _combo(self, parent, key, label, value, values):
        ttk.Label(parent, text=label).pack(anchor="w")
        e = ttk.Combobox(parent, values=values)
        e.set(value)
        e.pack(fill="x", pady=(2, 8))
        self.entries[key] = e

    def _val(self, key):
        return self.entries[key].get().strip()

    def _concepts(self):
        out = []
        for line in self.txt_concepts.get("1.0", "end").splitlines():
            line = line.strip()
            if not line:
                continue
            if "::" in line:
                name, definition = line.split("::", 1)
            else:
                name, definition = line, ""
            name, definition = name.strip(), definition.strip()
            if name:
                out.append({"name": name, "definition": definition or "—"})
        return out

    def _full_payload(self):
        payload = {"isbn": self._val("isbn"), "title": self._val("title"),
                   "publication_year": int(self._val("year")), "price": float(self._val("price")),
                   "stock": int(self._val("stock") or 0),
                   "format": self._val("format"), "category": self._val("category")}
        authors = [a.strip() for a in self._val("authors").split(",") if a.strip()]
        genres = [g.strip() for g in self._val("genres").split(",") if g.strip()]
        concepts = self._concepts()
        images = [u.strip() for u in self._val("images").split(",") if u.strip()]
        if authors:
            payload["authors"] = authors
        if genres:
            payload["genres"] = genres
        if concepts:
            payload["concepts"] = concepts
        if images:
            payload["images"] = [{"url": u, "isCover": i == 0} for i, u in enumerate(images)]
        return payload

    def _original(self):
        b = self.book
        return {
            "isbn": str(b.get("isbn", "")), "title": str(b.get("title", "")),
            "publication_year": b.get("publicationYear"), "price": b.get("price"),
            "stock": b.get("stock"), "format": _name(b.get("format")),
            "category": _name(b.get("category")),
            "authors": sorted(a.get("name", "") for a in b.get("authors", []) or []),
            "genres": sorted(g.get("name", "") for g in b.get("genres", []) or []),
        }

    def _ok(self, method):
        if not self._val("isbn") or not self._val("title") or not self._val("year") \
                or not self._val("price") or not self._val("format") or not self._val("category"):
            messagebox.showwarning("Faltan datos", "Completa los campos marcados con *.",
                                   parent=self)
            return
        try:
            int(self._val("year")); float(self._val("price")); int(self._val("stock") or 0)
        except ValueError:
            messagebox.showwarning("Números inválidos",
                                   "Año, precio y stock deben ser numéricos.", parent=self)
            return
        if method == "PATCH" and self.is_edit:
            full = self._full_payload()
            orig = self._original()
            diff = {}
            for key in ("isbn", "title", "publication_year", "price", "stock",
                        "format", "category"):
                new, old = full.get(key), orig.get(key)
                try:
                    same = float(new) == float(old)
                except (TypeError, ValueError):
                    same = str(new) == str(old)
                if not same:
                    diff[key] = new
            for key in ("authors", "genres"):
                if sorted(full.get(key, [])) != (orig.get(key) or []):
                    diff[key] = full.get(key, [])
            new_concepts = sorted((c["name"], c["definition"]) for c in full.get("concepts", []))
            old_concepts = sorted((c.get("name", ""), c.get("definition", ""))
                                  for c in self.book.get("concepts", []) or [])
            if new_concepts != old_concepts:
                diff["concepts"] = full.get("concepts", [])
            new_imgs = [u.strip() for u in self._val("images").split(",") if u.strip()]
            old_imgs = [i.get("url", "") for i in self.book.get("images", []) or []]
            if new_imgs != old_imgs:
                diff["images"] = ([{"url": u, "isCover": i == 0} for i, u in enumerate(new_imgs)]
                                  if new_imgs else [])
            if not diff:
                messagebox.showinfo("Sin cambios", "No modificaste ningún atributo.", parent=self)
                return
            self.result = ("PATCH", diff)
            self.destroy()
            return
        if method == "PUT" and self.is_edit:
            if not messagebox.askyesno(
                    "Reemplazo completo (PUT)",
                    "PUT sustituye el libro entero: las colecciones que no listes "
                    "(autores, géneros, conceptos, imágenes) quedarán vacías.\n\n¿Continuar?",
                    parent=self):
                return
            self.result = ("PUT", self._full_payload())
            self.destroy()
            return
        self.result = ("POST", self._full_payload())
        self.destroy()


def _name(value):
    if isinstance(value, dict):
        return value.get("name") or ""
    return value or ""
