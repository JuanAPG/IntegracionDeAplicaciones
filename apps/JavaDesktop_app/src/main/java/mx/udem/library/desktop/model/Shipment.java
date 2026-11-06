package mx.udem.library.desktop.model;

import com.fasterxml.jackson.databind.JsonNode;

/**
 * El rastreo PUBLICO de un envio: GET /envios/&lt;numero&gt; (5004).
 *
 * Es la unica ruta sin token de todo el servicio de pedidos, y es
 * publica a proposito para que una paqueteria pueda consultarla. Por eso
 * devuelve exactamente estos ocho campos y ninguno mas: ni dueno, ni
 * correo, ni importes, ni que libros lleva. El servicio los construye
 * uno por uno, de modo que anadir una columna a la vista no los publica
 * por accidente.
 *
 * `carrier`, `trackingCode`, `shippedAt` y `deliveredAt` son null
 * mientras el pedido no se haya enviado.
 */
public record Shipment(String orderNumber, String status, String carrier,
                       String trackingCode, String placedAt, String shippedAt,
                       String deliveredAt, int itemCount) {

    public static Shipment de(JsonNode nodo) {
        return new Shipment(
                nodo.path("orderNumber").asText(""),
                nodo.path("status").asText(""),
                nodo.path("carrier").asText(null),
                nodo.path("trackingCode").asText(null),
                nodo.path("placedAt").asText(null),
                nodo.path("shippedAt").asText(null),
                nodo.path("deliveredAt").asText(null),
                nodo.path("itemCount").asInt(0));
    }
}
