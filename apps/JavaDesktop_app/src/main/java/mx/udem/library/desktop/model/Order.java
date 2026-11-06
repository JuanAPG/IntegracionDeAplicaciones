package mx.udem.library.desktop.model;

import com.fasterxml.jackson.databind.JsonNode;

import java.util.ArrayList;
import java.util.List;

/**
 * Un pedido del servicio de pedidos (5004).
 *
 * OJO CON EL LISTADO: `GET /pedidos` NO trae `lines`, solo `lineCount` e
 * `itemCount`. Las lineas llegan con el detalle, `GET /pedidos/&lt;id&gt;`.
 * Aqui `lines` queda vacia en ese caso, que es fiel a lo que hay.
 *
 * ESTADOS Y TRANSICIONES, impuestos por un disparador de PostgreSQL y no
 * por la aplicacion:
 *     pendiente -> pagado | cancelado
 *     pagado    -> enviado | cancelado
 *     enviado   -> entregado
 *     entregado, cancelado -> finales
 * Intentar otra cosa da 409. Y el paso a `pagado` NO lo hace el cliente:
 * lo dispara la base cuando los pagos aplicados cubren el total.
 */
public record Order(
        int id,
        String orderNumber,
        String status,
        String currency,
        double subtotal,
        double shippingCost,
        double total,
        double paidAmount,
        int lineCount,
        int itemCount,
        String placedAt,
        String carrier,
        String trackingCode,
        List<OrderLine> lines) {

    public static Order de(JsonNode nodo) {
        List<OrderLine> lineas = new ArrayList<>();
        JsonNode arreglo = nodo.get("lines");
        if (arreglo != null && arreglo.isArray()) {
            arreglo.forEach(elemento -> lineas.add(OrderLine.de(elemento)));
        }
        JsonNode envio = nodo.path("shipping");
        return new Order(
                nodo.path("id").asInt(0),
                nodo.path("orderNumber").asText(""),
                nodo.path("status").asText(""),
                nodo.path("currency").asText("MXN"),
                nodo.path("subtotal").asDouble(0),
                nodo.path("shippingCost").asDouble(0),
                nodo.path("total").asDouble(0),
                nodo.path("paidAmount").asDouble(0),
                nodo.path("lineCount").asInt(lineas.size()),
                nodo.path("itemCount").asInt(0),
                nodo.path("placedAt").asText(""),
                envio.path("carrier").asText(null),
                envio.path("trackingCode").asText(null),
                List.copyOf(lineas));
    }

    public boolean estaPagado() {
        return "pagado".equals(status) || "enviado".equals(status) || "entregado".equals(status);
    }

    public String totalFormateado() {
        return String.format("$%,.2f %s", total, currency);
    }

    /**
     * El codigo de rastreo de ESTA aplicacion, derivado del numero real
     * del pedido: PED-000042 -> LIB-MTY-&lt;ano&gt;-000042.
     *
     * POR QUE SE DERIVA Y NO SE LEE DEL SERVICIO. El campo `trackingCode`
     * del servicio de pedidos solo lo puede escribir quien tenga el
     * permiso `orders:status`, que un cliente normal NO tiene (es 403
     * incluso sobre su propio pedido). De modo que para un usuario
     * corriente ese campo es siempre null. En vez de inventar un endpoint
     * o pedir permisos de staff, el seguimiento se ancla al identificador
     * REAL del pedido, que es lo que el enunciado permite expresamente
     * cuando el servicio no ofrece seguimiento.
     */
    public String codigoRastreo() {
        String sufijo = orderNumber == null ? "" : orderNumber.replaceAll("[^0-9]", "");
        String anio = placedAt != null && placedAt.length() >= 4 ? placedAt.substring(0, 4) : "2026";
        return "LIB-MTY-" + anio + "-" + (sufijo.isEmpty() ? "000000" : sufijo);
    }
}
