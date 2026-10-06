"""
apps/Python_app/ui_orders.py
Ventana de PEDIDOS Y PAGOS.

Tres pestañas:
  Carrito    arma un pedido con libros del catálogo y lo envía.
             El precio no se manda: lo congela el servidor desde la base.
  Pedidos    los del usuario (o todos, si su rol tiene orders:read),
             con detalle, bitácora, cancelación, cambio de estado y
             cobro.
  Envío      el rastreo PÚBLICO por número de pedido. Funciona SIN
             sesión, porque es el endpoint pensado para que un tercero
             (la paquetería) maneje su logística.

Los botones que exigen un rol se desactivan cuando el token no lo tiene,
pero eso es solo comodidad: la autorización de verdad la aplica cada
microservicio, que responde 403 si el rol no alcanza.
"""
import threading
import tkinter as tk
from tkinter import messagebox, ttk

ESTADOS_PEDIDO = ("pendiente", "pagado", "enviado", "entregado", "cancelado")


def _run(fn):
    """Lanza el trabajo de red fuera del hilo de la interfaz."""
    threading.Thread(target=fn, daemon=True).start()


def _money(value, currency="MXN"):
    try:
        return f"{float(value):,.2f} {currency}"
    except (TypeError, ValueError):
        return "—"


class OrdersWindow(tk.Toplevel):
    def __init__(self, parent, pedidos_client, pagos_client, books_client,
                 tokens, on_stock_changed=None):
        super().__init__(parent)
        self.title("Pedidos y pagos")
        self.geometry("980x620")
        self.minsize(860, 540)
        self.transient(parent)

        self.pedidos = pedidos_client
        self.pagos = pagos_client
        self.books = books_client
        self.tokens = tokens
        self.on_stock_changed = on_stock_changed

        self.carrito = {}          # book_id -> {"title", "price", "qty", "stock"}
        self.catalogo = []
        self.pedidos_cache = []
        self.metodos = []

        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True, padx=12, pady=12)
        self.tab_carrito = ttk.Frame(nb, padding=10)
        self.tab_pedidos = ttk.Frame(nb, padding=10)
        self.tab_envio = ttk.Frame(nb, padding=10)
        nb.add(self.tab_carrito, text="Carrito")
        nb.add(self.tab_pedidos, text="Mis pedidos")
        nb.add(self.tab_envio, text="Rastrear envío")

        self._build_carrito()
        self._build_pedidos()
        self._build_envio()

        self.status = ttk.Label(self, text="", padding=(14, 6))
        self.status.pack(fill="x")

        self._cargar_catalogo()
        self._cargar_pedidos()
        self._cargar_metodos()

    # -----------------------------------------------------------------
    def _say(self, text, error=False):
        def apply():
            self.status.configure(text=text,
                                  foreground="#B3261E" if error else "#1B5E20")
        self.after(0, apply)

    def _puede(self, *permisos):
        """Pista local: admin lo puede todo; staff, lo operativo."""
        rol = (self.tokens.role or "").lower()
        if rol == "admin":
            return True
        if rol == "staff":
            return all(p.startswith(("orders:", "payments:", "books:"))
                       for p in permisos)
        return False

    # =================================================================
    # Carrito
    # =================================================================
    def _build_carrito(self):
        izq = ttk.Frame(self.tab_carrito)
        izq.pack(side="left", fill="both", expand=True)
        ttk.Label(izq, text="Catálogo", font=("Helvetica", 11, "bold")).pack(anchor="w")

        buscar = ttk.Frame(izq)
        buscar.pack(fill="x", pady=(4, 6))
        self.e_buscar = ttk.Entry(buscar)
        self.e_buscar.pack(side="left", fill="x", expand=True)
        self.e_buscar.bind("<Return>", lambda _e: self._cargar_catalogo())
        ttk.Button(buscar, text="Buscar",
                   command=self._cargar_catalogo).pack(side="left", padx=(6, 0))

        cols = ("id", "titulo", "precio", "stock")
        self.tv_catalogo = ttk.Treeview(izq, columns=cols, show="headings", height=14)
        for col, texto, ancho in (("id", "Id", 50), ("titulo", "Título", 240),
                                  ("precio", "Precio", 90), ("stock", "Stock", 60)):
            self.tv_catalogo.heading(col, text=texto)
            self.tv_catalogo.column(col, width=ancho,
                                    anchor="e" if col in ("precio", "stock", "id") else "w")
        self.tv_catalogo.pack(fill="both", expand=True)
        self.tv_catalogo.bind("<Double-1>", lambda _e: self._agregar_al_carrito())

        acciones = ttk.Frame(izq)
        acciones.pack(fill="x", pady=(6, 0))
        ttk.Label(acciones, text="Cantidad").pack(side="left")
        self.sp_cantidad = ttk.Spinbox(acciones, from_=1, to=100, width=5)
        self.sp_cantidad.set(1)
        self.sp_cantidad.pack(side="left", padx=(4, 8))
        ttk.Button(acciones, text="Agregar al carrito ▸",
                   command=self._agregar_al_carrito).pack(side="left")

        der = ttk.Frame(self.tab_carrito, padding=(12, 0, 0, 0))
        der.pack(side="left", fill="both", expand=True)
        ttk.Label(der, text="Carrito", font=("Helvetica", 11, "bold")).pack(anchor="w")

        cols = ("id", "titulo", "cant", "importe")
        self.tv_carrito = ttk.Treeview(der, columns=cols, show="headings", height=10)
        for col, texto, ancho in (("id", "Id", 50), ("titulo", "Título", 200),
                                  ("cant", "Cant.", 60), ("importe", "Importe", 100)):
            self.tv_carrito.heading(col, text=texto)
            self.tv_carrito.column(col, width=ancho,
                                   anchor="e" if col != "titulo" else "w")
        self.tv_carrito.pack(fill="both", expand=True, pady=(4, 6))

        quitar = ttk.Frame(der)
        quitar.pack(fill="x")
        ttk.Button(quitar, text="Quitar del carrito",
                   command=self._quitar_del_carrito).pack(side="left")
        ttk.Button(quitar, text="Vaciar",
                   command=self._vaciar_carrito).pack(side="left", padx=(6, 0))

        datos = ttk.Frame(der)
        datos.pack(fill="x", pady=(10, 0))
        ttk.Label(datos, text="Dirección de envío").grid(row=0, column=0, sticky="w")
        self.e_direccion = ttk.Entry(datos, width=34)
        self.e_direccion.grid(row=0, column=1, sticky="ew", padx=(6, 0))
        ttk.Label(datos, text="Costo de envío").grid(row=1, column=0, sticky="w", pady=(4, 0))
        self.e_envio = ttk.Entry(datos, width=10)
        self.e_envio.insert(0, "0")
        self.e_envio.grid(row=1, column=1, sticky="w", padx=(6, 0), pady=(4, 0))
        datos.columnconfigure(1, weight=1)

        self.lbl_total = ttk.Label(der, text="Total estimado: —",
                                   font=("Helvetica", 10, "bold"))
        self.lbl_total.pack(anchor="e", pady=(10, 4))
        ttk.Button(der, text="Crear pedido",
                   command=self._crear_pedido).pack(anchor="e")
        ttk.Label(der, text="El precio lo congela el servidor desde el catálogo;\n"
                            "el total definitivo lo calcula él.",
                  foreground="#6B6B6B", justify="right").pack(anchor="e", pady=(4, 0))

    def _cargar_catalogo(self):
        termino = self.e_buscar.get().strip()

        def work():
            if termino:
                ok, msg, data = self.books.search(q=termino)
            else:
                ok, msg, data = self.books.list_books(limit=100)
            if not ok:
                self._say(msg, error=True)
                return
            from books_client import books_from_payload
            self.catalogo = books_from_payload(data)
            self.after(0, self._pintar_catalogo)
            self._say(f"{len(self.catalogo)} libro(s) en el catálogo.")

        _run(work)

    def _pintar_catalogo(self):
        self.tv_catalogo.delete(*self.tv_catalogo.get_children())
        for libro in self.catalogo:
            self.tv_catalogo.insert(
                "", "end", iid=str(libro.get("id")),
                values=(libro.get("id"), libro.get("title", ""),
                        _money(libro.get("price"), libro.get("currency", "")),
                        libro.get("stock", 0)))

    def _libro_seleccionado(self):
        sel = self.tv_catalogo.selection()
        if not sel:
            messagebox.showinfo("Elige un libro",
                                "Selecciona un libro del catálogo.", parent=self)
            return None
        book_id = int(sel[0])
        return next((b for b in self.catalogo if int(b.get("id", 0)) == book_id), None)

    def _agregar_al_carrito(self):
        libro = self._libro_seleccionado()
        if libro is None:
            return
        try:
            cantidad = int(self.sp_cantidad.get())
        except (TypeError, ValueError):
            cantidad = 1
        if cantidad < 1:
            return
        stock = int(libro.get("stock") or 0)
        book_id = int(libro["id"])
        actual = self.carrito.get(book_id, {}).get("qty", 0)
        if actual + cantidad > stock:
            messagebox.showwarning(
                "Stock insuficiente",
                f"«{libro.get('title')}» tiene {stock} unidad(es) disponibles "
                f"y ya llevas {actual} en el carrito.\n\n"
                "El servidor lo volverá a comprobar al crear el pedido: esta "
                "advertencia es solo para evitarte el viaje.",
                parent=self)
            return
        entrada = self.carrito.setdefault(
            book_id, {"title": libro.get("title", ""),
                      "price": float(libro.get("price") or 0),
                      "qty": 0, "stock": stock})
        entrada["qty"] += cantidad
        self._pintar_carrito()

    def _quitar_del_carrito(self):
        sel = self.tv_carrito.selection()
        if not sel:
            return
        self.carrito.pop(int(sel[0]), None)
        self._pintar_carrito()

    def _vaciar_carrito(self):
        self.carrito.clear()
        self._pintar_carrito()

    def _pintar_carrito(self):
        self.tv_carrito.delete(*self.tv_carrito.get_children())
        total = 0.0
        for book_id, item in sorted(self.carrito.items()):
            importe = item["qty"] * item["price"]
            total += importe
            self.tv_carrito.insert("", "end", iid=str(book_id),
                                   values=(book_id, item["title"], item["qty"],
                                           _money(importe)))
        try:
            total += float(self.e_envio.get() or 0)
        except (TypeError, ValueError):
            pass
        self.lbl_total.configure(text=f"Total estimado: {_money(total)}")

    def _crear_pedido(self):
        if not self.carrito:
            messagebox.showinfo("Carrito vacío",
                                "Agrega al menos un libro.", parent=self)
            return
        if not self.tokens.access:
            messagebox.showwarning("Sin sesión",
                                   "Inicia sesión para crear un pedido.",
                                   parent=self)
            return
        lineas = [(book_id, item["qty"]) for book_id, item in self.carrito.items()]
        try:
            envio = float(self.e_envio.get() or 0)
        except (TypeError, ValueError):
            envio = 0
        direccion = self.e_direccion.get().strip()

        def work():
            ok, data, error = self.pedidos.create(
                lineas, shipping_cost=envio, address=direccion)
            if not ok:
                self._say(error.message, error=True)
                self.after(0, lambda: messagebox.showerror(
                    "No se pudo crear el pedido", error.message, parent=self))
                return
            self.carrito.clear()
            self.after(0, self._pintar_carrito)
            self._say(f"Pedido {data.get('orderNumber')} creado por "
                      f"{_money(data.get('total'), data.get('currency', ''))}.")
            self._cargar_pedidos()
            self._cargar_catalogo()      # el stock cambió
            if self.on_stock_changed:
                self.after(0, self.on_stock_changed)

        _run(work)

    # =================================================================
    # Mis pedidos
    # =================================================================
    def _build_pedidos(self):
        barra = ttk.Frame(self.tab_pedidos)
        barra.pack(fill="x")
        ttk.Label(barra, text="Estado").pack(side="left")
        self.cb_estado = ttk.Combobox(barra, width=14, state="readonly",
                                      values=("(todos)",) + ESTADOS_PEDIDO)
        self.cb_estado.set("(todos)")
        self.cb_estado.pack(side="left", padx=(4, 10))
        self.var_todos = tk.BooleanVar(value=False)
        self.chk_todos = ttk.Checkbutton(
            barra, text="Ver los de todos (requiere orders:read)",
            variable=self.var_todos, command=self._cargar_pedidos)
        self.chk_todos.pack(side="left")
        if not self._puede("orders:read"):
            self.chk_todos.state(["disabled"])
        ttk.Button(barra, text="Actualizar",
                   command=self._cargar_pedidos).pack(side="right")
        self.cb_estado.bind("<<ComboboxSelected>>", lambda _e: self._cargar_pedidos())

        cols = ("numero", "estado", "piezas", "total", "pagado", "fecha")
        self.tv_pedidos = ttk.Treeview(self.tab_pedidos, columns=cols,
                                       show="headings", height=12)
        for col, texto, ancho in (("numero", "Número", 110), ("estado", "Estado", 90),
                                  ("piezas", "Piezas", 60), ("total", "Total", 110),
                                  ("pagado", "Cobrado", 110), ("fecha", "Fecha", 150)):
            self.tv_pedidos.heading(col, text=texto)
            self.tv_pedidos.column(col, width=ancho,
                                   anchor="w" if col in ("numero", "estado", "fecha") else "e")
        self.tv_pedidos.pack(fill="both", expand=True, pady=(8, 6))
        self.tv_pedidos.bind("<Double-1>", lambda _e: self._ver_detalle())

        acciones = ttk.Frame(self.tab_pedidos)
        acciones.pack(fill="x")
        ttk.Button(acciones, text="Detalle y bitácora",
                   command=self._ver_detalle).pack(side="left")
        ttk.Button(acciones, text="Pagar…",
                   command=self._pagar).pack(side="left", padx=(6, 0))
        ttk.Button(acciones, text="Cancelar pedido",
                   command=self._cancelar).pack(side="left", padx=(6, 0))
        self.btn_estado = ttk.Button(acciones, text="Cambiar estado…",
                                     command=self._cambiar_estado)
        self.btn_estado.pack(side="left", padx=(6, 0))
        if not self._puede("orders:status"):
            self.btn_estado.state(["disabled"])

    def _cargar_pedidos(self):
        estado = self.cb_estado.get()
        estado = "" if estado == "(todos)" else estado
        todos = bool(self.var_todos.get())

        def work():
            ok, data, error = self.pedidos.list_orders(status=estado, todos=todos)
            if not ok:
                self._say(error.message, error=True)
                return
            self.pedidos_cache = data.get("orders", [])
            self.after(0, self._pintar_pedidos)
            self._say(f"{data.get('total', 0)} pedido(s).")

        _run(work)

    def _pintar_pedidos(self):
        self.tv_pedidos.delete(*self.tv_pedidos.get_children())
        for pedido in self.pedidos_cache:
            moneda = pedido.get("currency", "")
            self.tv_pedidos.insert(
                "", "end", iid=str(pedido.get("id")),
                values=(pedido.get("orderNumber", ""), pedido.get("status", ""),
                        pedido.get("itemCount", 0),
                        _money(pedido.get("total"), moneda),
                        _money(pedido.get("paidAmount"), moneda),
                        (pedido.get("placedAt") or "")[:19].replace("T", " ")))

    def _pedido_seleccionado(self):
        sel = self.tv_pedidos.selection()
        if not sel:
            messagebox.showinfo("Elige un pedido",
                                "Selecciona un pedido de la lista.", parent=self)
            return None
        order_id = int(sel[0])
        return next((p for p in self.pedidos_cache
                     if int(p.get("id", 0)) == order_id), None)

    def _ver_detalle(self):
        pedido = self._pedido_seleccionado()
        if pedido is None:
            return
        order_id = int(pedido["id"])

        def work():
            ok, data, error = self.pedidos.get_order(order_id)
            if not ok:
                self._say(error.message, error=True)
                return
            ok_h, hist, _error = self.pedidos.history(order_id)
            self.after(0, lambda: self._mostrar_detalle(
                data, hist.get("history", []) if ok_h else []))

        _run(work)

    def _mostrar_detalle(self, pedido, historial):
        win = tk.Toplevel(self)
        win.title(f"Pedido {pedido.get('orderNumber')}")
        win.geometry("620x520")
        texto = tk.Text(win, wrap="word", padx=12, pady=12)
        texto.pack(fill="both", expand=True)
        moneda = pedido.get("currency", "")
        lineas = [
            f"Pedido {pedido.get('orderNumber')}  ·  estado: {pedido.get('status')}",
            f"Cliente: {pedido.get('user', {}).get('name') or '—'} "
            f"({pedido.get('user', {}).get('email') or '—'})",
            "",
            f"Subtotal: {_money(pedido.get('subtotal'), moneda)}",
            f"Envío:    {_money(pedido.get('shippingCost'), moneda)}",
            f"Total:    {_money(pedido.get('total'), moneda)}",
            f"Cobrado:  {_money(pedido.get('paidAmount'), moneda)}",
            "",
            "Líneas:",
        ]
        for linea in pedido.get("lines", []):
            lineas.append(
                f"  • {linea.get('quantity')} × {linea.get('title')} "
                f"(ISBN {linea.get('isbn')}) — "
                f"{_money(linea.get('unitPrice'), moneda)} c/u = "
                f"{_money(linea.get('lineTotal'), moneda)}")
        envio = pedido.get("shipping") or {}
        if envio.get("carrier") or envio.get("trackingCode"):
            lineas += ["", f"Paquetería: {envio.get('carrier') or '—'}",
                       f"Guía: {envio.get('trackingCode') or '—'}"]
        if historial:
            lineas += ["", "Bitácora de estados:"]
            for paso in historial:
                lineas.append(
                    f"  {(paso.get('changedAt') or '')[:19].replace('T', ' ')}  "
                    f"{paso.get('fromStatus') or '(alta)'} → {paso.get('toStatus')}"
                    + (f"  · {paso.get('note')}" if paso.get("note") else ""))
        texto.insert("1.0", "\n".join(lineas))
        texto.configure(state="disabled")
        ttk.Button(win, text="Cerrar", command=win.destroy).pack(pady=8)

    def _cancelar(self):
        pedido = self._pedido_seleccionado()
        if pedido is None:
            return
        if not messagebox.askyesno(
                "Cancelar pedido",
                f"¿Cancelar {pedido.get('orderNumber')}?\n\n"
                "Las unidades reservadas vuelven al catálogo.", parent=self):
            return
        order_id = int(pedido["id"])

        def work():
            ok, data, error = self.pedidos.cancel(order_id, "cancelado desde la app")
            if not ok:
                self._say(error.message, error=True)
                self.after(0, lambda: messagebox.showerror(
                    "No se pudo cancelar", error.message, parent=self))
                return
            self._say(f"Pedido {data.get('orderNumber')} cancelado; stock devuelto.")
            self._cargar_pedidos()
            self._cargar_catalogo()
            if self.on_stock_changed:
                self.after(0, self.on_stock_changed)

        _run(work)

    def _cambiar_estado(self):
        pedido = self._pedido_seleccionado()
        if pedido is None:
            return
        EstadoDialog(self, self.pedidos, pedido, self._tras_cambiar_estado)

    def _tras_cambiar_estado(self, mensaje):
        self._say(mensaje)
        self._cargar_pedidos()

    # =================================================================
    # Pagos
    # =================================================================
    def _cargar_metodos(self):
        def work():
            ok, data, _error = self.pagos.methods()
            if ok:
                self.metodos = data.get("methods", [])

        _run(work)

    def _pagar(self):
        pedido = self._pedido_seleccionado()
        if pedido is None:
            return
        if pedido.get("status") == "cancelado":
            messagebox.showinfo("Pedido cancelado",
                                "Un pedido cancelado no se puede pagar.",
                                parent=self)
            return
        PagoDialog(self, self.pagos, pedido, self.metodos, self._tras_pagar)

    def _tras_pagar(self, mensaje):
        self._say(mensaje)
        self._cargar_pedidos()

    # =================================================================
    # Rastreo público
    # =================================================================
    def _build_envio(self):
        ttk.Label(self.tab_envio,
                  text="Rastreo de envío",
                  font=("Helvetica", 12, "bold")).pack(anchor="w")
        ttk.Label(self.tab_envio,
                  text="Consulta PÚBLICA: no necesita sesión. Es el mismo endpoint "
                       "que usaría una paquetería para seguir el paquete, y por eso "
                       "solo devuelve el estado del envío —ni cliente, ni importes, "
                       "ni qué libros lleva.",
                  wraplength=860, foreground="#6B6B6B",
                  justify="left").pack(anchor="w", pady=(4, 12))

        fila = ttk.Frame(self.tab_envio)
        fila.pack(fill="x")
        ttk.Label(fila, text="Número de pedido").pack(side="left")
        self.e_numero = ttk.Entry(fila, width=18)
        self.e_numero.pack(side="left", padx=(6, 6))
        self.e_numero.insert(0, "PED-")
        self.e_numero.bind("<Return>", lambda _e: self._rastrear())
        ttk.Button(fila, text="Consultar", command=self._rastrear).pack(side="left")

        self.txt_envio = tk.Text(self.tab_envio, height=14, wrap="word",
                                 padx=12, pady=12, state="disabled")
        self.txt_envio.pack(fill="both", expand=True, pady=(12, 0))

    def _rastrear(self):
        numero = self.e_numero.get().strip().upper()
        if not numero or numero == "PED-":
            messagebox.showinfo("Falta el número",
                                "Escribe un número de pedido, por ejemplo "
                                "PED-000123.", parent=self)
            return

        def work():
            ok, data, error = self.pedidos.track(numero)
            if not ok:
                self.after(0, lambda: self._pintar_envio(
                    f"No se pudo consultar {numero}.\n\n{error.message}"))
                return
            lineas = [
                f"Pedido {data.get('orderNumber')}",
                f"Estado del envío: {data.get('status')}",
                f"Paquetería: {data.get('carrier') or '—'}",
                f"Guía: {data.get('trackingCode') or '—'}",
                f"Piezas: {data.get('itemCount')}",
                "",
                f"Realizado: {(data.get('placedAt') or '—')[:19].replace('T', ' ')}",
                f"Enviado:   {(data.get('shippedAt') or '—')[:19].replace('T', ' ')}",
                f"Entregado: {(data.get('deliveredAt') or '—')[:19].replace('T', ' ')}",
            ]
            self.after(0, lambda: self._pintar_envio("\n".join(lineas)))

        _run(work)

    def _pintar_envio(self, texto):
        self.txt_envio.configure(state="normal")
        self.txt_envio.delete("1.0", "end")
        self.txt_envio.insert("1.0", texto)
        self.txt_envio.configure(state="disabled")


# =====================================================================
class PagoDialog(tk.Toplevel):
    """Registra un pago contra un pedido."""

    def __init__(self, parent, pagos_client, pedido, metodos, on_done):
        super().__init__(parent)
        self.title(f"Pagar {pedido.get('orderNumber')}")
        self.geometry("460x360")
        self.transient(parent)
        self.grab_set()
        self.pagos = pagos_client
        self.pedido = pedido
        self.on_done = on_done
        # Clave de idempotencia fija para ESTE diálogo: si el usuario
        # pulsa dos veces, el servidor devuelve el mismo pago en vez de
        # cobrar otra vez.
        from login_client import LoginClient
        self.idempotency_key = LoginClient.new_idempotency_key()

        marco = ttk.Frame(self, padding=14)
        marco.pack(fill="both", expand=True)
        moneda = pedido.get("currency", "")
        ttk.Label(marco, text=f"Pedido {pedido.get('orderNumber')}",
                  font=("Helvetica", 11, "bold")).pack(anchor="w")
        ttk.Label(marco, text=f"Total {_money(pedido.get('total'), moneda)} · "
                              f"cobrado {_money(pedido.get('paidAmount'), moneda)}"
                  ).pack(anchor="w", pady=(2, 10))

        self.lbl_saldo = ttk.Label(marco, text="Consultando saldo…",
                                   foreground="#6B6B6B")
        self.lbl_saldo.pack(anchor="w", pady=(0, 10))

        fila = ttk.Frame(marco)
        fila.pack(fill="x")
        ttk.Label(fila, text="Importe").grid(row=0, column=0, sticky="w")
        self.e_importe = ttk.Entry(fila, width=14)
        self.e_importe.grid(row=0, column=1, sticky="w", padx=(6, 0))
        ttk.Label(fila, text="Método").grid(row=1, column=0, sticky="w", pady=(6, 0))
        nombres = [m["name"] for m in metodos] or ["efectivo", "tarjeta"]
        self.cb_metodo = ttk.Combobox(fila, values=nombres, state="readonly", width=16)
        self.cb_metodo.set(nombres[0])
        self.cb_metodo.grid(row=1, column=1, sticky="w", padx=(6, 0), pady=(6, 0))
        ttk.Label(fila, text="Código de autorización").grid(row=2, column=0,
                                                            sticky="w", pady=(6, 0))
        self.e_codigo = ttk.Entry(fila, width=20)
        self.e_codigo.grid(row=2, column=1, sticky="w", padx=(6, 0), pady=(6, 0))
        ttk.Label(fila, text="Últimos 4 dígitos").grid(row=3, column=0,
                                                       sticky="w", pady=(6, 0))
        self.e_last4 = ttk.Entry(fila, width=8)
        self.e_last4.grid(row=3, column=1, sticky="w", padx=(6, 0), pady=(6, 0))

        ttk.Label(marco,
                  text="Esta aplicación NO envía números de tarjeta: el servicio "
                       "rechaza cualquier campo de ese tipo. Solo viaja la "
                       "referencia de la pasarela y, si acaso, los cuatro "
                       "últimos dígitos.",
                  wraplength=410, foreground="#6B6B6B",
                  justify="left").pack(anchor="w", pady=(12, 8))

        self.lbl_msg = ttk.Label(marco, text="", foreground="#B3261E",
                                 wraplength=410, justify="left")
        self.lbl_msg.pack(anchor="w")

        botones = ttk.Frame(marco)
        botones.pack(fill="x", pady=(10, 0))
        ttk.Button(botones, text="Cancelar", command=self.destroy).pack(side="right")
        self.btn_pagar = ttk.Button(botones, text="Registrar pago",
                                    command=self._pagar)
        self.btn_pagar.pack(side="right", padx=(0, 8))

        self._cargar_saldo()

    def _cargar_saldo(self):
        order_id = int(self.pedido["id"])

        def work():
            ok, data, error = self.pagos.balance(order_id)
            if not ok:
                self.after(0, lambda: self.lbl_saldo.configure(
                    text=f"No se pudo leer el saldo: {error.message}"))
                return
            falta = data.get("balance")
            self.after(0, lambda: self._pintar_saldo(data, falta))

        _run(work)

    def _pintar_saldo(self, saldo, falta):
        moneda = self.pedido.get("currency", "")
        self.lbl_saldo.configure(
            text=f"Cobrado {_money(saldo.get('paid'), moneda)} · "
                 f"comprometido {_money(saldo.get('committed'), moneda)} · "
                 f"falta {_money(falta, moneda)}")
        if not self.e_importe.get() and falta:
            self.e_importe.insert(0, f"{float(falta):.2f}")

    def _pagar(self):
        try:
            importe = float(self.e_importe.get())
        except (TypeError, ValueError):
            self.lbl_msg.configure(text="El importe debe ser un número.")
            return
        if importe <= 0:
            self.lbl_msg.configure(text="El importe debe ser mayor que cero.")
            return
        self.btn_pagar.state(["disabled"])
        self.lbl_msg.configure(text="Registrando…", foreground="#6B6B6B")
        datos = {
            "order_id": int(self.pedido["id"]),
            "amount": importe,
            "method": self.cb_metodo.get(),
            "idempotency_key": self.idempotency_key,
            "authorization_code": self.e_codigo.get().strip(),
            "card_last4": self.e_last4.get().strip(),
        }

        def work():
            ok, data, error = self.pagos.register(**datos)
            if not ok:
                self.after(0, lambda: (
                    self.lbl_msg.configure(text=error.message, foreground="#B3261E"),
                    self.btn_pagar.state(["!disabled"])))
                return
            estado = data.get("status")
            repetido = " (ya existía: no se cobró dos veces)" \
                if data.get("idempotentReplay") else ""
            self.after(0, lambda: (
                self.on_done(f"Pago {data.get('reference')} registrado "
                             f"({estado}){repetido}."),
                self.destroy()))

        _run(work)


# =====================================================================
class EstadoDialog(tk.Toplevel):
    """Mueve el estado de un pedido. Exige el permiso orders:status."""

    def __init__(self, parent, pedidos_client, pedido, on_done):
        super().__init__(parent)
        self.title(f"Estado de {pedido.get('orderNumber')}")
        self.geometry("440x300")
        self.transient(parent)
        self.grab_set()
        self.pedidos = pedidos_client
        self.pedido = pedido
        self.on_done = on_done

        marco = ttk.Frame(self, padding=14)
        marco.pack(fill="both", expand=True)
        actual = pedido.get("status")
        ttk.Label(marco, text=f"Estado actual: {actual}",
                  font=("Helvetica", 11, "bold")).pack(anchor="w")

        # Solo se ofrecen las transiciones que la base va a aceptar.
        posibles = {"pendiente": ["pagado", "cancelado"],
                    "pagado": ["enviado", "cancelado"],
                    "enviado": ["entregado"],
                    "entregado": [], "cancelado": []}.get(actual, [])
        ttk.Label(marco, text="Transiciones permitidas desde aquí:",
                  foreground="#6B6B6B").pack(anchor="w", pady=(6, 2))

        if not posibles:
            ttk.Label(marco, text="Ninguna: es un estado final.",
                      foreground="#B3261E").pack(anchor="w")
            ttk.Button(marco, text="Cerrar", command=self.destroy).pack(pady=12)
            return

        self.cb_destino = ttk.Combobox(marco, values=posibles, state="readonly")
        self.cb_destino.set(posibles[0])
        self.cb_destino.pack(anchor="w", pady=(0, 10))

        fila = ttk.Frame(marco)
        fila.pack(fill="x")
        ttk.Label(fila, text="Paquetería").grid(row=0, column=0, sticky="w")
        self.e_carrier = ttk.Entry(fila, width=22)
        self.e_carrier.grid(row=0, column=1, sticky="w", padx=(6, 0))
        ttk.Label(fila, text="Código de guía").grid(row=1, column=0, sticky="w",
                                                    pady=(6, 0))
        self.e_guia = ttk.Entry(fila, width=22)
        self.e_guia.grid(row=1, column=1, sticky="w", padx=(6, 0), pady=(6, 0))

        ttk.Label(marco,
                  text="Al marcar «enviado», la paquetería y la guía son lo que "
                       "después lee cualquiera en el rastreo público.",
                  wraplength=390, foreground="#6B6B6B",
                  justify="left").pack(anchor="w", pady=(10, 8))

        self.lbl_msg = ttk.Label(marco, text="", foreground="#B3261E",
                                 wraplength=390, justify="left")
        self.lbl_msg.pack(anchor="w")

        botones = ttk.Frame(marco)
        botones.pack(fill="x", pady=(8, 0))
        ttk.Button(botones, text="Cancelar", command=self.destroy).pack(side="right")
        ttk.Button(botones, text="Aplicar",
                   command=self._aplicar).pack(side="right", padx=(0, 8))

    def _aplicar(self):
        destino = self.cb_destino.get()
        order_id = int(self.pedido["id"])
        carrier = self.e_carrier.get().strip()
        guia = self.e_guia.get().strip()

        def work():
            ok, data, error = self.pedidos.change_status(
                order_id, destino, carrier=carrier, tracking=guia)
            if not ok:
                self.after(0, lambda: self.lbl_msg.configure(text=error.message))
                return
            aviso = data.get("warning")
            mensaje = (f"{self.pedido.get('orderNumber')}: "
                       f"{data.get('previousStatus')} → {data.get('status')}.")
            if aviso:
                mensaje += f" {aviso}"
            self.after(0, lambda: (self.on_done(mensaje), self.destroy()))

        _run(work)
