#!/usr/bin/env python3
"""
locust_tests/extraer_metricas.py
Lee los CSV que deja Locust en evidencias/ y arma las tablas de
RESULTADOS.md. No calcula nada por su cuenta: toma los valores tal como
los escribio Locust (columnas "95%", "Requests/s", "Request Count",
"Failure Count") para que la tabla y la evidencia no puedan discrepar.
"""
import csv
import glob
import os
import sys

P95_UMBRAL = 1000.0
ERROR_UMBRAL = 5.0
PERFILES = ["smoke", "load", "stress", "spike", "soak", "quiebre"]


def lee(perfil):
    ruta = f"evidencias/{perfil}_stats.csv"
    if not os.path.exists(ruta):
        return None
    filas = list(csv.DictReader(open(ruta)))
    return {f["Name"]: f for f in filas}


def num(fila, clave, por_omision=0.0):
    try:
        return float(fila[clave])
    except (TypeError, ValueError, KeyError):
        return por_omision


def veredicto(p95, err, exitosas=None):
    # 100 % de fallos no es "degradado": es que el destino no respondio.
    # Dar un veredicto de umbral ahi seria presentar como medicion algo
    # que no se pudo medir.
    if exitosas == 0:
        return "NO VALIDO (destino caido)"
    return "DEGRADADO" if (p95 > P95_UMBRAL or err > ERROR_UMBRAL) else "cumplido"


# Lo que cada perfil PIDE (va en el locustfile, en ETAPAS). La duracion y
# el numero de usuarios que se imprimen abajo NO salen de aqui sino del
# historial que escribio Locust: esto es solo la etiqueta legible.
USUARIOS = {
    "smoke": "1",
    "load": "5",
    "stress": "2->20",
    "spike": "2->15->2",
    "soak": "3",
    "quiebre": "1->20 (+1/12 s)",
}


def historial(perfil):
    """Duracion y concurrencia REALES de la corrida, leidas del historial.

    No se declaran: se miden. La diferencia importa en el perfil de
    quiebre, cuya corrida duro 13 minutos en vez de los 4 previstos por
    el defecto ya corregido del locustfile.
    """
    ruta = f"evidencias/{perfil}_stats_history.csv"
    if not os.path.exists(ruta):
        return None, None
    marcas, usuarios = [], []
    for fila in csv.DictReader(open(ruta)):
        if fila.get("Name") != "Aggregated":
            continue
        try:
            marcas.append(int(fila["Timestamp"]))
            usuarios.append(int(fila["User Count"]))
        except (TypeError, ValueError, KeyError):
            continue
    if not marcas:
        return None, None
    return max(marcas) - min(marcas), max(usuarios)


def duracion(segundos):
    if segundos is None:
        return "—"
    if segundos < 120:
        return f"{segundos} s"
    return f"{segundos // 60} min {segundos % 60:02d} s"


def sistema(nombre):
    if nombre.startswith("[monolito]"):
        return "monolito"
    if nombre.startswith("["):
        return nombre.split("]")[0][1:]
    return None


def main():
    print("## Tabla global por perfil\n")
    print("| Perfil | Usuarios | Duracion | Peticiones | RPS | p95 (ms) | Errores | Umbral |")
    print("|---|---|---|---|---|---|---|---|")
    for perfil in PERFILES:
        datos = lee(perfil)
        if not datos or "Aggregated" not in datos:
            print(f"| {perfil} | {USUARIOS.get(perfil, '—')} | — | — | — | — | — "
                  f"| NO EJECUTADO |")
            continue
        t = datos["Aggregated"]
        n = num(t, "Request Count")
        fallos = num(t, "Failure Count")
        err = (fallos / n * 100) if n else 0.0
        p95 = num(t, "95%")
        segundos, pico = historial(perfil)
        print(f"| {perfil} | {USUARIOS.get(perfil, '—')} (pico medido {pico}) "
              f"| {duracion(segundos)} | {int(n)} | {num(t, 'Requests/s'):.2f} "
              f"| {p95:.0f} | {err:.2f} % | {veredicto(p95, err, n - fallos)} |")

    print("\n## Tabla por destino y perfil\n")
    print("| Perfil | Destino | Usuarios | Duracion | Peticiones | RPS | "
          "p95 (ms) | Errores | Umbral |")
    print("|---|---|---|---|---|---|---|---|---|")
    for perfil in PERFILES:
        datos = lee(perfil)
        if not datos:
            continue
        agregado = {}
        for nombre, fila in datos.items():
            s = sistema(nombre)
            if not s:
                continue
            a = agregado.setdefault(s, {"n": 0.0, "f": 0.0, "p95": 0.0, "rps": 0.0})
            a["n"] += num(fila, "Request Count")
            a["f"] += num(fila, "Failure Count")
            a["rps"] += num(fila, "Requests/s")
            a["p95"] = max(a["p95"], num(fila, "95%"))
        segundos, pico = historial(perfil)
        for s in sorted(agregado):
            a = agregado[s]
            err = (a["f"] / a["n"] * 100) if a["n"] else 0.0
            print(f"| {perfil} | {s} | {USUARIOS.get(perfil, '—')} "
                  f"| {duracion(segundos)} | {int(a['n'])} | {a['rps']:.2f} "
                  f"| {a['p95']:.0f} (peor ruta) | {err:.2f} % "
                  f"| {veredicto(a['p95'], err, a['n'] - a['f'])} |")

    print("\n## El par comparable: catalogo\n")
    print("| Perfil | [monolito] /library/libros p95 | [books] /books?format=json p95 |")
    print("|---|---|---|")
    for perfil in PERFILES:
        datos = lee(perfil)
        if not datos:
            continue
        m = next((f for n, f in datos.items() if "library/libros (catalogo" in n), None)
        b = next((f for n, f in datos.items() if "books?format=json" in n), None)
        print(f"| {perfil} | {num(m, '95%'):.0f} ms |" if m else f"| {perfil} | — |",
              f" {num(b, '95%'):.0f} ms |" if b else " — |")


if __name__ == "__main__":
    sys.exit(main())
