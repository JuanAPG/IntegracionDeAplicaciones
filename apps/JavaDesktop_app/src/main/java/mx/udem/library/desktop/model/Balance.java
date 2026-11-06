package mx.udem.library.desktop.model;

import com.fasterxml.jackson.databind.JsonNode;

/**
 * El saldo de un pedido: GET /pedidos/&lt;id&gt;/saldo.
 *
 * OJO CON EL PUERTO: esta ruta vive en PAGOS (5005), no en pedidos
 * (5004), aunque la ruta empiece por /pedidos. Es el error de direccion
 * mas facil de cometer con este contrato.
 *
 *   paid      = suma de los pagos en estado `aplicado`
 *   committed = suma de los `autorizado` + `pendiente` (comprometido pero
 *               todavia no cobrado)
 *   balance   = total - paid
 * El servicio rechaza con 409 un pago que haga `committed + amount` mayor
 * que el total, de modo que conviene prerrellenar el importe con
 * `balance` en lugar de con el total.
 */
public record Balance(int orderId, String orderNumber, String orderStatus,
                      String currency, double total, double paid,
                      double committed, double balance) {

    public static Balance de(JsonNode nodo) {
        return new Balance(
                nodo.path("orderId").asInt(0),
                nodo.path("orderNumber").asText(""),
                nodo.path("orderStatus").asText(""),
                nodo.path("currency").asText("MXN"),
                nodo.path("total").asDouble(0),
                nodo.path("paid").asDouble(0),
                nodo.path("committed").asDouble(0),
                nodo.path("balance").asDouble(0));
    }

    public boolean estaLiquidado() {
        return balance <= 0.004;
    }
}
