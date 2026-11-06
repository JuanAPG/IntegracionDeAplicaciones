package mx.udem.library.desktop.model;

import com.fasterxml.jackson.databind.JsonNode;

/**
 * Un metodo de pago de GET /metodos (5005).
 *
 * `requiresAuthorization` decide el estado con el que NACE el pago, y por
 * tanto si la compra queda liquidada de inmediato:
 *   - false (efectivo)  -> el pago nace `aplicado` y el disparador de la
 *                          base pasa el pedido a `pagado` en el acto.
 *   - true  (tarjeta...) -> nace `autorizado` si se manda un codigo de
 *                          autorizacion, y queda pendiente de que alguien
 *                          con permiso lo aplique.
 * Esa diferencia es la razon por la que esta aplicacion ensena el aviso
 * correspondiente en la pantalla de pago: el usuario tiene que entender
 * por que su pedido quedo pagado o no.
 */
public record PaymentMethod(int id, String name, String description,
                            boolean requiresAuthorization, boolean isActive) {

    public static PaymentMethod de(JsonNode nodo) {
        return new PaymentMethod(
                nodo.path("id").asInt(0),
                nodo.path("name").asText(""),
                nodo.path("description").asText(""),
                nodo.path("requiresAuthorization").asBoolean(false),
                nodo.path("isActive").asBoolean(true));
    }

    @Override
    public String toString() {
        return name;
    }
}
