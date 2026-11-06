package mx.udem.library.desktop.model;

import com.fasterxml.jackson.databind.JsonNode;

/**
 * Una linea de pedido ya creada.
 *
 * `unitPrice` es el precio CONGELADO en el momento de la compra. El
 * cliente no lo envia nunca: lo fija el procedimiento almacenado leyendo
 * el catalogo. Si el libro sube de precio manana, este pedido no cambia.
 */
public record OrderLine(int id, int bookId, String isbn, String title,
                        int quantity, double unitPrice, double lineTotal) {

    public static OrderLine de(JsonNode nodo) {
        return new OrderLine(
                nodo.path("id").asInt(0),
                nodo.path("bookId").asInt(0),
                nodo.path("isbn").asText(""),
                nodo.path("title").asText(""),
                nodo.path("quantity").asInt(0),
                nodo.path("unitPrice").asDouble(0),
                nodo.path("lineTotal").asDouble(0));
    }
}
