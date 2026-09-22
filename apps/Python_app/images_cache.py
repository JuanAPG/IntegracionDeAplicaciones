"""Portadas de libros: descarga con caché local + placeholder si no hay imagen.

Sin Pillow instalado, el módulo sigue importándose y la UI muestra el
placeholder textual (la dependencia es opcional en tiempo de ejecución,
obligatoria en requirements.txt).
"""
import hashlib
import os
import tempfile
import threading
import urllib.request

try:
    from PIL import Image, ImageDraw, ImageFont, ImageTk
    HAS_PIL = True
except ImportError:  # noqa: BLE001
    HAS_PIL = False
    Image = ImageDraw = ImageFont = ImageTk = None

CACHE_DIR = os.path.join(tempfile.gettempdir(), "biblioteca_covers")
THUMB = (160, 220)
PLACEHOLDER_COLOR = (232, 224, 205)
PLACEHOLDER_INK = (90, 80, 64)

try:
    os.makedirs(CACHE_DIR, exist_ok=True)
except OSError:
    pass


def _cache_path(url):
    digest = hashlib.sha256(url.encode("utf-8")).hexdigest()
    return os.path.join(CACHE_DIR, digest + ".thumb.png")


def placeholder_image(width=160, height=220, text="Sin portada"):
    """Placeholder generado sin red; None si no hay Pillow."""
    if not HAS_PIL:
        return None
    img = Image.new("RGB", (width, height), PLACEHOLDER_COLOR)
    draw = ImageDraw.Draw(img)
    draw.rectangle([6, 6, width - 7, height - 7], outline=PLACEHOLDER_INK, width=2)
    # líneas que simulan lomo/texto
    for i, y in enumerate(range(60, height - 40, 14)):
        w = width - 40 - (i % 3) * 18
        draw.line([(20, y), (20 + w, y)], fill=PLACEHOLDER_INK, width=2)
    # título centrado arriba
    try:
        font = ImageFont.load_default()
        bbox = draw.textbbox((0, 0), text, font=font)
        draw.text(((width - (bbox[2] - bbox[0])) / 2, 24), text,
                  fill=PLACEHOLDER_INK, font=font)
    except Exception:
        pass
    return ImageTk.PhotoImage(img)


def fetch_thumbnail(url, callback, size=THUMB, timeout=10):
    """Descarga en hilo; callback(photo_or_None) se ejecuta en ese hilo
    (la UI debe reenviar con after). Usa caché en disco."""
    def work():
        photo = None
        if HAS_PIL and url:
            path = _cache_path(url)
            try:
                if os.path.exists(path):
                    img = Image.open(path)
                else:
                    req = urllib.request.Request(
                        url, headers={"User-Agent": "Biblioteca-Tk/1.0"})
                    with urllib.request.urlopen(req, timeout=timeout) as resp:
                        data = resp.read(3 * 1024 * 1024)
                    with open(path, "wb") as fh:
                        fh.write(data)
                    img = Image.open(path)
                img = img.convert("RGB")
                img.thumbnail(size, Image.LANCZOS)
                # centrar en lienzo fijo
                canvas = Image.new("RGB", size, (245, 241, 232))
                canvas.paste(img, ((size[0] - img.size[0]) // 2,
                                   (size[1] - img.size[1]) // 2))
                photo = ImageTk.PhotoImage(canvas)
            except Exception:  # noqa: BLE001 - red o formato: placeholder
                photo = None
        try:
            callback(photo)
        except Exception:
            pass
    threading.Thread(target=work, daemon=True).start()
