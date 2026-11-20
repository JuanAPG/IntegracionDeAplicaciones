"""Prueba HTTP local con Nginx y upstreams simulados; no conecta a la VM."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'apps' / 'Python_app'))
from api_client import TokenBox
from books_client import BooksClient
from services_client import AuthorsClient, PagosClient, PedidosClient, UsersClient
from gateway_url import service_url

base = 'http://127.0.0.1:18081/api/'
token = TokenBox()
cases = [
    (BooksClient(base + 'books', tokens=token), '/books/15', 5001, '/books/15?output=json'),
    (UsersClient(base + 'users', token), '/roles', 5002, '/roles?format=json'),
    (AuthorsClient(base + 'authors', token), '/authors/3/books', 5003, '/authors/3/books?format=json'),
    (PedidosClient(base + 'pedidos', token), '/envios/ABC', 5004, '/envios/ABC?format=json'),
    (PagosClient(base + 'pagos', token), '/pedidos/15/saldo', 5005, '/pedidos/15/saldo?format=json'),
]
assert service_url(base + 'login', '/login') == base + 'login'
assert service_url(base + 'login', '/refresh') == base + 'login/refresh'
print('PythonTK: login y refresh -> rutas públicas correctas')
for client, path, port, uri in cases:
    ok, data, error = client.request('GET', path, auth=False)
    assert ok, error
    assert data['port'] == port and data['uri'] == uri, (port, data)
    print(f"PythonTK: {path} -> :{port}{uri} OK")
