"""Paleta minimalista estilo biblioteca + tema ttk."""

BG = "#F5F1E8"        # pergamino
SURFACE = "#FFFFFF"   # tarjetas
SIDEBAR = "#2B2620"   # nogal (header)
INK = "#2B2620"       # texto
INK_ON_DARK = "#F5F1E8"
MUTED = "#8A8177"     # texto secundario
BORDER = "#E3DCCB"    # bordes suaves
ACCENT = "#1B4D3E"    # verde bosque (primario)
ACCENT_HOVER = "#143C31"
BRASS = "#B98A2F"     # dorado biblioteca (detalles)
DANGER = "#A63D2F"
OK = "#1E7E34"
DOWN = "#C0392B"

FONT_TITLE = ("Helvetica", 16, "bold")
FONT_SUB = ("Helvetica", 10)
FONT_BODY = ("Helvetica", 10)
FONT_SMALL = ("Helvetica", 9)


def apply(root):
    from tkinter import ttk
    s = ttk.Style(root)
    try:
        s.theme_use("clam")
    except Exception:
        pass
    s.configure(".", background=BG, foreground=INK, font=FONT_BODY)
    s.configure("TFrame", background=BG)
    s.configure("Card.TFrame", background=SURFACE)
    s.configure("Dark.TFrame", background=SIDEBAR)
    s.configure("TLabel", background=BG, foreground=INK)
    s.configure("Card.TLabel", background=SURFACE, foreground=INK)
    s.configure("Dark.TLabel", background=SIDEBAR, foreground=INK_ON_DARK)
    s.configure("Muted.TLabel", background=BG, foreground=MUTED, font=FONT_SMALL)
    s.configure("Title.TLabel", background=SIDEBAR, foreground=INK_ON_DARK, font=FONT_TITLE)
    s.configure("Sub.TLabel", background=SIDEBAR, foreground="#CFC6B4", font=FONT_SUB)
    s.configure("TButton", background=SURFACE, foreground=INK, borderwidth=1,
                relief="solid", padding=(12, 7))
    s.map("TButton", background=[("active", "#EFE8D6")])
    s.configure("Accent.TButton", background=ACCENT, foreground="white", borderwidth=0,
                padding=(14, 8))
    s.map("Accent.TButton", background=[("active", ACCENT_HOVER)])
    s.configure("Ghost.TButton", background=SIDEBAR, foreground=INK_ON_DARK,
                borderwidth=1, relief="solid", padding=(12, 7))
    s.configure("TEntry", fieldbackground=SURFACE, borderwidth=1, relief="solid",
                padding=6)
    s.configure("Treeview", background=SURFACE, fieldbackground=SURFACE,
                foreground=INK, rowheight=26, borderwidth=1, relief="solid")
    s.configure("Treeview.Heading", background="#ECE5D3", foreground=INK,
                relief="flat", padding=6, font=("Helvetica", 10, "bold"))
    s.configure("TNotebook", background=BG, borderwidth=0)
    s.configure("TNotebook.Tab", background="#E7DFCC", foreground=INK,
                padding=(14, 8))
    s.map("TNotebook.Tab", background=[("selected", SURFACE)])
    return s
