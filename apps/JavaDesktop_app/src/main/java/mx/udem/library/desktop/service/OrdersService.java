package mx.udem.library.desktop.service;

import com.fasterxml.jackson.databind.JsonNode;
import mx.udem.library.desktop.cart.Cart;
import mx.udem.library.desktop.model.Order;
import mx.udem.library.desktop.model.Shipment;
import mx.udem.library.desktop.net.ApiClient;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * Microservicio de pedidos (5004).
 *
 * EL PRECIO NO SE ENVIA NUNCA AL CREAR UN PEDIDO. Solo van el id del
 * libro y la cantidad; el procedimiento almacenado congela el precio
 * leyendolo del catalogo dentro de la misma transaccion en que reserva
 * las existencias. Mandar el precio desde el cliente permitiria comprar
 * a un precio elegido por el cliente, que es justo lo que no debe poder
 * hacerse.
 *
 * EL LISTADO NO TRAE LAS LINEAS. `GET /pedidos` devuelve `lineCount` e
 * `itemCount` pero no `lines`; para ver que libros lleva un pedido hay
 * que pedir el detalle.
 */
public final class OrdersService {

    private final ApiClient api;

    public OrdersService(ApiClient api) {
        this.api = api;
    }

    /**
     * Crea el pedido a partir de la cesta.
     *
     * Devuelve el pedido ya creado, con su numero real (PED-000042) y su
     * total calculado por el servidor. Si no alcanzan las existencias el
     * servicio responde 409 diciendo de que libro se trata, cuantos hay y
     * cuantos se piden: ese detalle llega intacto en la excepcion.
     */
    public Order crear(Cart cesta, String direccionEnvio, double costoEnvio, String notas) {
        List<Map<String, Object>> lineas = new ArrayList<>();
        cesta.lineas().forEach(linea -> lineas.add(Map.of(
                "bookId", linea.libro().id(),
                "quantity", linea.cantidad())));

        Map<String, Object> cuerpo = new LinkedHashMap<>();
        cuerpo.put("lines", lineas);
        if (direccionEnvio != null && !direccionEnvio.isBlank()) {
            cuerpo.put("shippingAddress", direccionEnvio.trim());
        }
        if (costoEnvio > 0) {
            cuerpo.put("shippingCost", costoEnvio);
        }
        if (notas != null && !notas.isBlank()) {
            cuerpo.put("notes", notas.trim());
        }
        // `userId` NO se manda: sin el, el servicio crea el pedido para
        // el dueno del token. Mandarlo exigiria el permiso orders:write.
        return Order.de(api.post("/pedidos", cuerpo, true));
    }

    /** Los pedidos del usuario del token. Sin lineas (ver la nota de arriba). */
    public List<Order> mios(int limit) {
        JsonNode respuesta = api.get("/pedidos",
                Map.of("limit", Integer.toString(limit), "sort", "placed", "order", "desc"), true);
        List<Order> pedidos = new ArrayList<>();
        JsonNode arreglo = respuesta.get("orders");
        if (arreglo != null && arreglo.isArray()) {
            arreglo.forEach(nodo -> pedidos.add(Order.de(nodo)));
        }
        return List.copyOf(pedidos);
    }

    /** Detalle con las lineas. El dueno pasa sin permiso; un ajeno es 403. */
    public Order detalle(int id) {
        return Order.de(api.get("/pedidos/" + id, true));
    }

    public Order porNumero(String numero) {
        return Order.de(api.get("/pedidos/numero/" + numero.trim().toUpperCase(), true));
    }

    /**
     * Rastreo publico del envio.
     *
     * Se pide SIN token a proposito: es la unica ruta publica del
     * servicio, pensada para que un tercero (la paqueteria) pueda
     * consultarla. El numero se normaliza a mayusculas porque el servicio
     * lo hace y asi la cache acierta.
     */
    public Shipment envio(String numeroPedido) {
        return Shipment.de(api.get("/envios/" + numeroPedido.trim().toUpperCase(), false));
    }

    /** Bitacora de cambios de estado del pedido. */
    public List<Map<String, String>> historial(int id) {
        JsonNode respuesta = api.get("/pedidos/" + id + "/historial", true);
        List<Map<String, String>> eventos = new ArrayList<>();
        JsonNode arreglo = respuesta.get("history");
        if (arreglo != null && arreglo.isArray()) {
            arreglo.forEach(nodo -> eventos.add(Map.of(
                    "de", nodo.path("fromStatus").asText(""),
                    "a", nodo.path("toStatus").asText(""),
                    "nota", nodo.path("note").asText(""),
                    "cuando", nodo.path("changedAt").asText(""))));
        }
        return List.copyOf(eventos);
    }
}
