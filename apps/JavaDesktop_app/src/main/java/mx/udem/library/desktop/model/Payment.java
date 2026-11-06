package mx.udem.library.desktop.model;

import com.fasterxml.jackson.databind.JsonNode;

/**
 * Un pago registrado en el servicio de pagos (5005).
 *
 * `reference` es la cadena legible (PAG-000011); `id` es el entero. No
 * hay ningun campo llamado `paymentReference`.
 *
 * `idempotentReplay` viene a true cuando se reenvio la misma
 * `idempotencyKey`: el servicio devuelve el pago original con 200 en vez
 * de cobrar otra vez. La aplicacion lo dice en claro, porque un usuario
 * que ve "pago registrado" dos veces tiene derecho a preguntarse si le
 * cobraron dos veces.
 */
public record Payment(
        int id,
        String reference,
        String status,
        double amount,
        String currency,
        String methodName,
        int orderId,
        String orderNumber,
        String orderStatus,
        boolean idempotentReplay) {

    public static Payment de(JsonNode nodo) {
        JsonNode metodo = nodo.path("method");
        JsonNode pedido = nodo.path("order");
        return new Payment(
                nodo.path("id").asInt(0),
                nodo.path("reference").asText(""),
                nodo.path("status").asText(""),
                nodo.path("amount").asDouble(0),
                nodo.path("currency").asText("MXN"),
                metodo.path("name").asText(""),
                pedido.path("id").asInt(0),
                pedido.path("number").asText(""),
                pedido.path("status").asText(""),
                nodo.path("idempotentReplay").asBoolean(false));
    }

    /** El pago quedo efectivamente cobrado. */
    public boolean estaAplicado() {
        return "aplicado".equals(status);
    }

    public String importeFormateado() {
        return String.format("$%,.2f %s", amount, currency);
    }
}
