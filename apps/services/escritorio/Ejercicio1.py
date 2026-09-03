import re
import socket
import getpass
import tkinter as tk
from tkinter import messagebox, scrolledtext, ttk

import soap_client

MODELOS_SERVICIO = ("IaaS", "PaaS", "SaaS", "FaaS", "N/A")

PATRONES = [
    ("IaaS", "IaaS (Infrastructure as a Service)",
     r"\b(servidor|maquina virtual|vm|infraestructura|almacenamiento|red|cpu|disco|aws ec2|azure vm)\b"),
    ("PaaS", "PaaS (Platform as a Service)",
     r"\b(plataforma|desarrollo|deploy|desplegar|runtime|contenedor|docker|kubernetes|heroku|google app engine)\b"),
    ("SaaS", "SaaS (Software as a Service)",
     r"\b(software|aplicacion|correo|gmail|office 365|microsoft 365|salesforce|crm|erp|navegador)\b"),
    ("FaaS", "FaaS (Function as a Service)",
     r"\b(funcion|funciones|evento|serverless|lambda|azure functions|cloud functions|ejecutar codigo)\b"),
]

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

# Con que se identifica este cliente de escritorio ante clientes_servidos
# (encabezado SOAP opcional ClienteInfo, ver soap_endpoint.py). No es una
# credencial: solo dice "que tipo de app y que instancia hizo la llamada".
TIPO_CLIENTE = "Python-Tkinter-Clasificador"
IDENTIFICADOR_CLIENTE = f"{getpass.getuser()}@{socket.gethostname()}"


def clasificar_texto(texto):
    """Heuristica local por palabras clave. Devuelve (codigo_modelo, etiqueta_larga)."""
    texto = texto.lower()
    for codigo, etiqueta, patron in PATRONES:
        if re.search(patron, texto):
            return codigo, etiqueta
    return None, "No identificado"


class Ejercicio1(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Clasificador de Servicios Cloud Computing")
        self.geometry("700x600")
        self.resizable(False, False)

        notebook = ttk.Notebook(self)
        notebook.pack(fill="both", expand=True)

        tab_local = tk.Frame(notebook)
        tab_soap = tk.Frame(notebook)
        notebook.add(tab_local, text="Clasificacion local")
        notebook.add(tab_soap, text="Clasificacion SOAP")

        self._crear_tab_local(tab_local)
        self._crear_tab_soap(tab_soap)

    # ===================================================================
    # Modo local: heuristica sin red, sin base de datos (comportamiento
    # original del ejercicio, intacto).
    # ===================================================================
    def _crear_tab_local(self, parent):
        panel_datos = tk.Frame(parent, padx=10, pady=10)
        panel_datos.pack(fill="x")

        tk.Label(panel_datos, text="Nombre:").grid(row=0, column=0, sticky="w", padx=5, pady=5)
        self.txt_nombre = tk.Entry(panel_datos)
        self.txt_nombre.grid(row=0, column=1, sticky="ew", padx=5, pady=5)

        tk.Label(panel_datos, text="Apellido:").grid(row=1, column=0, sticky="w", padx=5, pady=5)
        self.txt_apellido = tk.Entry(panel_datos)
        self.txt_apellido.grid(row=1, column=1, sticky="ew", padx=5, pady=5)

        panel_datos.columnconfigure(1, weight=1)

        frame_desc = tk.LabelFrame(parent, text="Escriba una descripcion del servicio Cloud",
                                   padx=5, pady=5)
        frame_desc.pack(fill="both", expand=True, padx=10, pady=5)

        self.txt_descripcion = scrolledtext.ScrolledText(frame_desc, wrap="word", height=10)
        self.txt_descripcion.pack(fill="both", expand=True)

        panel_inferior = tk.Frame(parent, padx=10, pady=10)
        panel_inferior.pack(fill="x")

        tk.Button(panel_inferior, text="Clasificar", command=self._clasificar_local).pack(fill="x")

        self.lbl_resultado = tk.Label(panel_inferior, text="Resultado: ",
                                      font=("Arial", 14, "bold"), fg="blue",
                                      justify="left", anchor="w")
        self.lbl_resultado.pack(fill="x", pady=(10, 0))

    def _clasificar_local(self):
        nombre = self.txt_nombre.get().strip()
        apellido = self.txt_apellido.get().strip()
        texto = self.txt_descripcion.get("1.0", tk.END).strip()

        if not nombre or not apellido or not texto:
            messagebox.showwarning("Aviso", "Complete todos los campos.")
            return

        _, etiqueta = clasificar_texto(texto)
        self.lbl_resultado.config(text=f"Usuario: {nombre} {apellido}\nClasificacion: {etiqueta}")

    # ===================================================================
    # Modo SOAP: la GUI NUNCA importa psycopg2 ni conoce host/puerto/
    # usuario de PostgreSQL. Todo pasa por soap_client.py, que solo habla
    # HTTP/XML con la URL configurada aqui abajo.
    # ===================================================================
    def _crear_tab_soap(self, parent):
        outer = tk.Frame(parent, padx=10, pady=10)
        outer.pack(fill="both", expand=True)

        # --- Identidad + servidor -----------------------------------
        panel_datos = tk.LabelFrame(outer, text="Datos del clasificador", padx=8, pady=8)
        panel_datos.pack(fill="x")

        tk.Label(panel_datos, text="Nombre:").grid(row=0, column=0, sticky="w", padx=5, pady=3)
        self.soap_nombre = tk.Entry(panel_datos)
        self.soap_nombre.grid(row=0, column=1, sticky="ew", padx=5, pady=3)

        tk.Label(panel_datos, text="Apellidos:").grid(row=1, column=0, sticky="w", padx=5, pady=3)
        self.soap_apellidos = tk.Entry(panel_datos)
        self.soap_apellidos.grid(row=1, column=1, sticky="ew", padx=5, pady=3)

        tk.Label(panel_datos, text="Correo:").grid(row=2, column=0, sticky="w", padx=5, pady=3)
        self.soap_correo = tk.Entry(panel_datos)
        self.soap_correo.grid(row=2, column=1, sticky="ew", padx=5, pady=3)

        tk.Label(panel_datos, text="URL del servicio SOAP:").grid(row=3, column=0, sticky="w", padx=5, pady=3)
        self.soap_url = tk.Entry(panel_datos)
        self.soap_url.insert(0, "http://localhost:5001/soap/clasificacion")
        self.soap_url.grid(row=3, column=1, sticky="ew", padx=5, pady=3)

        panel_datos.columnconfigure(1, weight=1)

        # --- Conceptos pendientes ------------------------------------
        panel_pendientes = tk.LabelFrame(outer, text="Conceptos pendientes de clasificar", padx=8, pady=8)
        panel_pendientes.pack(fill="both", expand=True, pady=(8, 0))

        tk.Button(panel_pendientes, text="Cargar conceptos pendientes",
                 command=self._cargar_pendientes).pack(anchor="w")

        self.lista_pendientes = tk.Listbox(panel_pendientes, height=6)
        self.lista_pendientes.pack(fill="both", expand=True, pady=(6, 0))
        self._pendientes = []  # paralelo a self.lista_pendientes: dicts con la fila completa

        # --- Sugerencia de modelo + registro --------------------------
        panel_clasificar = tk.LabelFrame(outer, text="Clasificacion", padx=8, pady=8)
        panel_clasificar.pack(fill="x", pady=(8, 0))

        tk.Label(panel_clasificar, text="Descripcion (opcional, para sugerir el modelo):").pack(anchor="w")
        self.soap_descripcion = tk.Text(panel_clasificar, height=3, wrap="word")
        self.soap_descripcion.pack(fill="x", pady=(2, 6))

        fila_modelo = tk.Frame(panel_clasificar)
        fila_modelo.pack(fill="x")
        tk.Button(fila_modelo, text="Sugerir modelo",
                 command=self._sugerir_modelo).pack(side="left")
        tk.Label(fila_modelo, text="Modelo de servicio:").pack(side="left", padx=(15, 5))
        self.combo_modelo = ttk.Combobox(fila_modelo, values=MODELOS_SERVICIO,
                                         state="readonly", width=10)
        self.combo_modelo.pack(side="left")

        tk.Button(panel_clasificar, text="Registrar clasificacion (SOAP)",
                 command=self._registrar_clasificacion, bg="#2e7d32", fg="white"
                 ).pack(fill="x", pady=(10, 0))

        # --- Resultado + progreso -------------------------------------
        self.soap_resultado = tk.Label(outer, text="", font=("Arial", 11, "bold"),
                                       fg="blue", justify="left", anchor="w", wraplength=650)
        self.soap_resultado.pack(fill="x", pady=(10, 0))

        panel_progreso = tk.Frame(outer)
        panel_progreso.pack(fill="x", pady=(4, 0))
        tk.Button(panel_progreso, text="Actualizar progreso",
                 command=self._actualizar_progreso).pack(side="left")
        self.lbl_progreso = tk.Label(panel_progreso, text="Progreso: --")
        self.lbl_progreso.pack(side="left", padx=(10, 0))

    # ---- validaciones comunes -----------------------------------------
    def _datos_identidad(self):
        nombre = self.soap_nombre.get().strip()
        apellidos = self.soap_apellidos.get().strip()
        correo = self.soap_correo.get().strip()
        url = self.soap_url.get().strip()

        if not nombre or not apellidos or not correo:
            messagebox.showwarning("Aviso", "Complete nombre, apellidos y correo.")
            return None
        if not EMAIL_RE.match(correo):
            messagebox.showwarning("Aviso", "El correo no tiene un formato valido.")
            return None
        if not url:
            messagebox.showwarning("Aviso", "Indique la URL del servicio SOAP.")
            return None
        return nombre, apellidos, correo, url

    def _header_cliente(self):
        return {"tipo_cliente": TIPO_CLIENTE, "identificador": IDENTIFICADOR_CLIENTE}

    # ---- acciones -------------------------------------------------------
    def _cargar_pendientes(self):
        datos = self._datos_identidad()
        if not datos:
            return
        _, _, correo, url = datos

        try:
            pendientes = soap_client.obtener_conceptos_pendientes(
                url, correo, limite=10, header=self._header_cliente())
        except soap_client.SoapFaultError as fault:
            self._mostrar_fault(fault)
            return
        except soap_client.SoapTransportError as exc:
            self._mostrar_error_transporte(exc)
            return

        self._pendientes = pendientes
        self.lista_pendientes.delete(0, tk.END)
        if not pendientes:
            self.lista_pendientes.insert(tk.END, "(sin conceptos pendientes)")
            return
        for item in pendientes:
            texto = (f"{item['nombre_concepto']}  —  {item['titulo_libro']} "
                     f"({item['nombre_categoria']})")
            self.lista_pendientes.insert(tk.END, texto)

    def _sugerir_modelo(self):
        texto = self.soap_descripcion.get("1.0", tk.END).strip()
        if not texto:
            messagebox.showinfo("Sugerencia", "Escriba una descripcion para sugerir un modelo.")
            return
        codigo, etiqueta = clasificar_texto(texto)
        if codigo is None:
            messagebox.showinfo("Sugerencia", "No se identifico un modelo a partir del texto; "
                                              "elija uno manualmente.")
            return
        self.combo_modelo.set(codigo)
        messagebox.showinfo("Sugerencia", f"Modelo sugerido: {etiqueta}")

    def _registrar_clasificacion(self):
        datos = self._datos_identidad()
        if not datos:
            return
        _, _, correo, url = datos

        seleccion = self.lista_pendientes.curselection()
        if not seleccion or not self._pendientes:
            messagebox.showwarning("Aviso", "Cargue los conceptos pendientes y seleccione uno.")
            return
        concepto = self._pendientes[seleccion[0]]

        modelo = self.combo_modelo.get().strip()
        if modelo not in MODELOS_SERVICIO:
            messagebox.showwarning("Aviso", "Seleccione un modelo de servicio valido.")
            return

        try:
            mensaje = soap_client.registrar_clasificacion(
                url, correo, concepto["referencia_libro"], concepto["referencia_concepto"],
                modelo, header=self._header_cliente())
        except soap_client.SoapFaultError as fault:
            self._mostrar_fault(fault)
            return
        except soap_client.SoapTransportError as exc:
            self._mostrar_error_transporte(exc)
            return

        self.soap_resultado.config(fg="#2e7d32", text=f"Exito: {mensaje}")
        self._cargar_pendientes()      # el concepto recien clasificado ya no debe salir
        self._actualizar_progreso()

    def _actualizar_progreso(self):
        datos = self._datos_identidad()
        if not datos:
            return
        _, _, correo, url = datos

        try:
            clasificados, pendientes = soap_client.obtener_progreso_usuario(
                url, correo, header=self._header_cliente())
        except soap_client.SoapFaultError as fault:
            self._mostrar_fault(fault)
            return
        except soap_client.SoapTransportError as exc:
            self._mostrar_error_transporte(exc)
            return

        self.lbl_progreso.config(text=f"Progreso: {clasificados} clasificados, {pendientes} pendientes")

    # ---- presentacion de errores: nunca XML ni detalle tecnico --------
    _CATEGORIA_TITULO = {
        "CLIENTE": "Datos no encontrados",
        "VALIDACION": "Error de validacion",
        "CONFLICTO": "Clasificacion duplicada",
        "SERVIDOR": "Error del servidor",
    }

    def _mostrar_fault(self, fault):
        titulo = self._CATEGORIA_TITULO.get(fault.categoria, "Error del servicio")
        self.soap_resultado.config(fg="#c62828", text=f"{titulo}: {fault.mensaje}")
        messagebox.showerror(titulo, fault.mensaje)

    def _mostrar_error_transporte(self, exc):
        mensaje = str(exc)
        self.soap_resultado.config(fg="#c62828", text=f"No se pudo contactar al servicio: {mensaje}")
        messagebox.showerror("Sin conexion con el servicio SOAP", mensaje)


if __name__ == "__main__":
    app = Ejercicio1()
    app.mainloop()
