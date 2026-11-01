#!/usr/bin/env bash
# locust_tests/armar_resultados.sh
# Sustituye en RESULTADOS.md, entre los marcadores, las tablas que
# extraer_metricas.py saca de los CSV de una tanda. Idempotente.
#
#   ./armar_resultados.sh              # tanda por omision (2026-11-01)
#   RONDA=2026-10-30 ./armar_resultados.sh
#
# Las tablas NO se escriben a mano en ningun momento: salen de los CSV
# que dejo Locust, de modo que el informe y la evidencia no pueden
# discrepar.
set -eu
cd "$(dirname "$0")"
RONDA="${RONDA:-2026-11-01}" python3 - <<'PY'
import os
import subprocess

ronda = os.environ["RONDA"]
ini, fin = f"<!--TABLAS {ronda}-->", f"<!--FIN TABLAS {ronda}-->"
doc = open("RESULTADOS.md").read()
if ini not in doc or fin not in doc:
    raise SystemExit(f"RESULTADOS.md no tiene los marcadores {ini} / {fin}")

tablas = subprocess.run(["python3", "extraer_metricas.py"],
                        capture_output=True, text=True, check=True,
                        env={**os.environ, "RONDA": ronda}).stdout

antes, resto = doc.split(ini, 1)
_, despues = resto.split(fin, 1)
open("RESULTADOS.md", "w").write(
    f"{antes}{ini}\n\n{tablas.strip()}\n\n{fin}{despues}")
print(f"RESULTADOS.md: tablas de la tanda {ronda} actualizadas")
PY
