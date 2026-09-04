"""
apps/services/escritorio/mock_soap_server.py
Servidor SOAP local de PRUEBA, sin PostgreSQL, Flask ni psycopg2, para
poder correr y demostrar la GUI (Ejercicio1_local_demo.py) en una
maquina donde el modulo SOAP real no esta instalado -- por ejemplo tu
laptop, cuando el servicio de verdad solo vive en la VM y aqui no
tienes PostgreSQL.

No es una reimplementacion aparte: importa el modulo REAL
library_soap_service/soap/soap_endpoint.py sin tocarlo, para que el
parseo de sobres, el armado de respuestas y la taxonomia de SOAP Fault
sean EXACTAMENTE los mismos que en produccion. Lo unico que cambia es
la capa de datos: se sustituye clasificacion_repository (PostgreSQL)
por mock_repository (memoria), y se stubbean config/db para no
requerir python-dotenv ni psycopg2 instalados localmente.

Uso:
    python3 mock_soap_server.py [puerto]      # puerto por omision: 5001

Luego, en la GUI (pestana "Clasificacion SOAP"), usa:
    http://localhost:5001/soap/clasificacion

NUNCA usar este servidor como reemplazo del modulo SOAP real: no
persiste nada (los datos se pierden al cerrarlo), no es seguro para
mas de un cliente a la vez, y su credencial WS-Security
(admin_demo / demo-2026, ver mock_repository.py) es solo de prueba.
"""
import os
import sys
import types
from http.server import BaseHTTPRequestHandler, HTTPServer

_HERE = os.path.dirname(os.path.abspath(__file__))
_SOAP_DIR = os.path.normpath(os.path.join(_HERE, "..", "..", "..",
                                          "library_soap_service", "soap"))
sys.path.insert(0, _HERE)
sys.path.insert(0, _SOAP_DIR)

# ---------------------------------------------------------------------
# Stubs: soap_endpoint.py importa "config" y "db" del modulo real. Se
# reemplazan ANTES de importarlo para no arrastrar python-dotenv
# (config.py) ni psycopg2 (db.py), que no estan instalados en una
# laptop sin el entorno del microservicio. Solo se ponen los atributos
# que soap_endpoint.py realmente usa.
# ---------------------------------------------------------------------
_config_stub = types.ModuleType("config")
_config_stub.CLASIFICACION_NAMESPACE = "urn:library:clasificacion:1.0"
_config_stub.CLASIFICACION_DEFAULT_LIMIT = 10
_config_stub.CLASIFICACION_MAX_LIMIT = 100
_config_stub.DEBUG = True
sys.modules["config"] = _config_stub

_db_stub = types.ModuleType("db")
_db_stub.DatabaseUnavailable = type("DatabaseUnavailable", (RuntimeError,), {})
sys.modules["db"] = _db_stub

# clasificacion_repository -> mock_repository, ANTES de importar
# soap_endpoint (que hace "import clasificacion_repository as repo").
import mock_repository
sys.modules["clasificacion_repository"] = mock_repository

import soap_endpoint  # noqa: E402 (tiene que ir despues de los stubs de arriba)


class _Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        if self.path != "/soap/clasificacion":
            self.send_response(404)
            self.end_headers()
            return
        length = int(self.headers.get("Content-Length", 0))
        raw_body = self.rfile.read(length)
        xml_bytes, status = soap_endpoint.handle_request(raw_body)
        self.send_response(status)
        self.send_header("Content-Type", "text/xml; charset=utf-8")
        self.send_header("Content-Length", str(len(xml_bytes)))
        self.end_headers()
        self.wfile.write(xml_bytes)

    def log_message(self, fmt, *args):
        print("[mock-soap]", fmt % args)


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 5001
    server = HTTPServer(("127.0.0.1", port), _Handler)
    print(f"Mock SOAP local (sin PostgreSQL) -> http://127.0.0.1:{port}/soap/clasificacion")
    print("Catalogo semilla:")
    for isbn, titulo, categoria, concepto in mock_repository.CATALOGO:
        print(f"  - {concepto}  ({titulo} / {categoria})")
    print("Credencial WS-Security de PRUEBA (ObtenerEstadisticasPorModelo): "
         "admin_demo / demo-2026 -- NO usar en produccion.")
    print("Ctrl+C para detener. Los datos se pierden al cerrar (a proposito: cada corrida es limpia).")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nDetenido.")


if __name__ == "__main__":
    main()
