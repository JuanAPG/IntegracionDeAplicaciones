"""
apps/Python_app/services_client.py
Clientes de los microservicios nuevos: usuarios, autores, pedidos y pagos.

Todos heredan de ApiClient, de modo que comparten el encabezado Bearer,
la renovacion automatica del token a los 30 minutos y la traduccion de
errores. Aqui solo vive lo propio de cada API.
"""
from api_client import ApiClient


class UsersClient(ApiClient):
    """Cuentas, roles, correos y contrasenas. NINGUNA lectura es publica."""

    SERVICE = "Usuarios"

    def list_users(self, q="", role="", active=None, limit=50, offset=0):
        params = {"limit": limit, "offset": offset}
        if q:
            params["q"] = q
        if role:
            params["role"] = role
        if active is not None:
            params["active"] = "true" if active else "false"
        return self.get("/users", params, fallback="No se pudieron listar las cuentas")

    def get_user(self, user_id):
        return self.get(f"/users/{user_id}", fallback="No se pudo leer la cuenta")

    def create_user(self, payload):
        return self.post("/users", payload, fallback="No se pudo crear la cuenta")

    def update_names(self, user_id, payload):
        return self.patch(f"/users/{user_id}", payload,
                          fallback="No se pudo actualizar la cuenta")

    def change_password(self, user_id, nueva, actual=None):
        body = {"password": nueva}
        if actual:
            body["currentPassword"] = actual
        return self.patch(f"/users/{user_id}/password", body,
                          fallback="No se pudo cambiar la contrasena")

    def change_email(self, user_id, email, verified=None):
        body = {"email": email}
        if verified is not None:
            body["verified"] = bool(verified)
        return self.patch(f"/users/{user_id}/email", body,
                          fallback="No se pudo cambiar el correo")

    def change_role(self, user_id, role_id=None, role=None):
        body = {"roleId": role_id} if role_id is not None else {"role": role}
        return self.put(f"/users/{user_id}/role", body,
                        fallback="No se pudo cambiar el rol")

    def deactivate(self, user_id):
        return self.delete(f"/users/{user_id}",
                           fallback="No se pudo desactivar la cuenta")

    def list_roles(self):
        return self.get("/roles", fallback="No se pudieron listar los roles")


class AuthorsClient(ApiClient):
    """Autores y su relacion con los libros. Las lecturas son publicas."""

    SERVICE = "Autores"

    def list_authors(self, q="", has_books=None, limit=50, offset=0):
        params = {"limit": limit, "offset": offset, "sort": "name"}
        if q:
            params["q"] = q
        if has_books is not None:
            params["has_books"] = "true" if has_books else "false"
        return self.get("/authors", params, auth=False,
                        fallback="No se pudieron listar los autores")

    def get_author(self, author_id):
        return self.get(f"/authors/{author_id}", auth=False,
                        fallback="No se pudo leer el autor")

    def books_of(self, author_id):
        return self.get(f"/authors/{author_id}/books", auth=False,
                        fallback="No se pudieron listar las obras")

    def create_author(self, name, books=None):
        body = {"name": name}
        if books:
            body["books"] = list(books)
        return self.post("/authors", body, fallback="No se pudo crear el autor")

    def rename(self, author_id, name):
        return self.put(f"/authors/{author_id}", {"name": name},
                        fallback="No se pudo renombrar el autor")

    def set_books(self, author_id, book_ids):
        return self.put(f"/authors/{author_id}/books", {"books": list(book_ids)},
                        fallback="No se pudieron fijar las obras")

    def link_book(self, author_id, book_id):
        return self.post(f"/authors/{author_id}/books/{book_id}",
                         fallback="No se pudo vincular la obra")

    def unlink_book(self, author_id, book_id):
        return self.delete(f"/authors/{author_id}/books/{book_id}",
                           fallback="No se pudo desvincular la obra")

    def delete_author(self, author_id, force=False):
        params = {"force": "true"} if force else None
        return self.delete(f"/authors/{author_id}", params=params,
                           fallback="No se pudo borrar el autor")


class PedidosClient(ApiClient):
    """
    Pedidos, lineas y estados.

    El rastreo de envio (track) es la UNICA llamada que no manda token:
    el endpoint es publico para que lo pueda usar una paqueteria.
    """

    SERVICE = "Pedidos"

    def create(self, lines, shipping_cost=0, address="", notes="", user_id=None):
        body = {"lines": [{"bookId": int(b), "quantity": int(q)} for b, q in lines]}
        if shipping_cost:
            body["shippingCost"] = float(shipping_cost)
        if address:
            body["shippingAddress"] = address
        if notes:
            body["notes"] = notes
        if user_id is not None:
            body["userId"] = int(user_id)
        return self.post("/pedidos", body, fallback="No se pudo crear el pedido")

    def list_orders(self, status="", todos=False, user_id=None, limit=50, offset=0):
        params = {"limit": limit, "offset": offset}
        if status:
            params["status"] = status
        if todos:
            params["all"] = "true"
        if user_id is not None:
            params["userId"] = int(user_id)
        return self.get("/pedidos", params,
                        fallback="No se pudieron listar los pedidos")

    def get_order(self, order_id):
        return self.get(f"/pedidos/{order_id}", fallback="No se pudo leer el pedido")

    def history(self, order_id):
        return self.get(f"/pedidos/{order_id}/historial",
                        fallback="No se pudo leer la bitacora")

    def adjust(self, order_id, lines):
        body = {"lines": [{"bookId": int(b), "quantity": int(q)} for b, q in lines]}
        return self.patch(f"/pedidos/{order_id}/lineas", body,
                          fallback="No se pudo ajustar el pedido")

    def cancel(self, order_id, reason=""):
        return self.delete(f"/pedidos/{order_id}",
                           body={"reason": reason} if reason else None,
                           fallback="No se pudo cancelar el pedido")

    def change_status(self, order_id, status, carrier="", tracking="", note=""):
        body = {"status": status}
        if carrier:
            body["carrier"] = carrier
        if tracking:
            body["trackingCode"] = tracking
        if note:
            body["note"] = note
        return self.put(f"/pedidos/{order_id}/estado", body,
                        fallback="No se pudo cambiar el estado")

    def track(self, order_number):
        """
        Rastreo PUBLICO: sin token.

        Devuelve solo el estatus de envio. Se llama con auth=False a
        proposito: asi funciona igual sin sesion, que es justo para lo
        que existe el endpoint.
        """
        numero = (order_number or "").strip().upper()
        if not numero:
            return False, None, None
        return self.get(f"/envios/{numero}", auth=False,
                        fallback="No se pudo consultar el envio")


class PagosClient(ApiClient):
    """Pagos. Aqui NADA es publico: todo exige token."""

    SERVICE = "Pagos"

    def methods(self):
        return self.get("/metodos", fallback="No se pudieron listar los metodos")

    def register(self, order_id, amount, method=None, method_id=None,
                 idempotency_key=None, authorization_code=None, card_last4=None,
                 notes=""):
        body = {"orderId": int(order_id), "amount": float(amount)}
        if method_id is not None:
            body["methodId"] = int(method_id)
        elif method:
            body["method"] = method
        if idempotency_key:
            body["idempotencyKey"] = idempotency_key
        if authorization_code:
            body["authorizationCode"] = authorization_code
        if card_last4:
            body["cardLast4"] = card_last4
        if notes:
            body["notes"] = notes
        return self.post("/pagos", body, fallback="No se pudo registrar el pago")

    def list_payments(self, order_id=None, status="", todos=False,
                      limit=50, offset=0):
        params = {"limit": limit, "offset": offset}
        if order_id is not None:
            params["orderId"] = int(order_id)
        if status:
            params["status"] = status
        if todos:
            params["all"] = "true"
        return self.get("/pagos", params,
                        fallback="No se pudieron listar los pagos")

    def get_payment(self, payment_id):
        return self.get(f"/pagos/{payment_id}", fallback="No se pudo leer el pago")

    def balance(self, order_id):
        return self.get(f"/pedidos/{order_id}/saldo",
                        fallback="No se pudo consultar el saldo")

    def apply(self, payment_id, authorization_code=""):
        body = {"authorizationCode": authorization_code} if authorization_code else None
        return self.post(f"/pagos/{payment_id}/aplicar", body,
                         fallback="No se pudo aplicar el pago")

    def reject(self, payment_id, note=""):
        return self.post(f"/pagos/{payment_id}/rechazar",
                         {"note": note} if note else None,
                         fallback="No se pudo rechazar el pago")

    def refund(self, payment_id, note=""):
        return self.post(f"/pagos/{payment_id}/reembolsar",
                         {"note": note} if note else None,
                         fallback="No se pudo reembolsar el pago")
