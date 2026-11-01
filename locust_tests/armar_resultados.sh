#!/usr/bin/env bash
# Inserta en RESULTADOS.md el inventario de rutas y las tablas que
# extraer_metricas.py saca de los CSV. Idempotente: se puede repetir.
set -eu
cd "$(dirname "$0")"
python3 - <<'PY'
import subprocess
doc = open("RESULTADOS.md").read()
tablas = subprocess.run(["python3", "extraer_metricas.py"],
                        capture_output=True, text=True, check=True).stdout
rutas = open("RUTAS.md").read() if __import__("os").path.exists("RUTAS.md") else ""
marca = "<!--TABLAS-->"
if marca in doc:
    doc = doc.replace(marca, rutas + "\n" + tablas)
else:
    ini = doc.index("## Rutas identificadas")
    fin = doc.index("## Desviaciones respecto al enunciado")
    doc = doc[:ini] + rutas + "\n" + tablas + "\n" + doc[fin:]
open("RESULTADOS.md", "w").write(doc)
print("RESULTADOS.md actualizado")
PY
