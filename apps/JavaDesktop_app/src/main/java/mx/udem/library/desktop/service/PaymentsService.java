package mx.udem.library.desktop.service;

import com.fasterxml.jackson.databind.JsonNode;
import mx.udem.library.desktop.model.Balance;
import mx.udem.library.desktop.model.Payment;
import mx.udem.library.desktop.model.PaymentMethod;
import mx.udem.library.desktop.net.ApiClient;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * Microservicio de pagos (5005).
 *
 * ESTA APLICACION NO ENVIA NI PIDE DATOS DE TARJETA. El servicio rechaza
 * con 400 cualquier cuerpo que traiga `cardNumber`, `cvv`, `pan`,
 * `titular` y una decena mas de claves parecidas, y hace bien: un
 * servicio que no guarda instrumentos de pago no puede filtrarlos. Lo
 * unico que se manda es un codigo de autorizacion simulado y, como mucho,
 * los cuatro ultimos digitos, que no identifican una tarjeta.
 *
 * LA CLAVE DE IDEMPOTENCIA SE GENERA UNA VEZ POR INTENTO DE COBRO, no
 * por clic. Asi, si alguien pulsa dos veces o la red reintenta, el
 * servicio devuelve el MISMO pago con `idempotentReplay: true` en lugar
 * de cobrar dos veces.
 *
 * OJO CON EL PUERTO DE /saldo: la ruta es `/pedidos/&lt;id&gt;/saldo` pero vive
 * aqui, en pagos (5005), no en el servicio de pedidos.
 */
public final class PaymentsService {

    private final ApiClient api;

    public PaymentsService(ApiClient api) {
        this.api = api;
    }

    /** Metodos de pago disponibles. Exige token, aunque no un permiso. */
    public List<PaymentMethod> metodos() {
        JsonNode respuesta = api.get("/metodos", true);
        List<PaymentMethod> metodos = new ArrayList<>();
        JsonNode arreglo = respuesta.get("methods");
        if (arreglo != null && arreglo.isArray()) {
            arreglo.forEach(nodo -> metodos.add(PaymentMethod.de(nodo)));
        }
        return List.copyOf(metodos);
    }

    /**
     * Cuanto falta por cobrar de un pedido. Conviene consultarlo ANTES de
     * cobrar y usar `balance` como importe: el servicio rechaza con 409
     * un pago que exceda el saldo comprometido.
     */
    public Balance saldo(int orderId) {
        return Balance.de(api.get("/pedidos/" + orderId + "/saldo", true));
    }

    /**
     * Registra el pago de un pedido.
     *
     * El estado con el que nace depende del metodo: `efectivo` no exige
     * autorizacion y nace `aplicado`, lo que hace que el disparador de la
     * base pase el pedido a `pagado` en la misma transaccion. Los metodos
     * que si la exigen nacen `autorizado` y alguien con permiso tiene que
     * aplicarlos despues. Esta aplicacion NO finge que un pago autorizado
     * esta cobrado: ensena el estado que devolvio el servicio.
     */
    public Payment pagar(int orderId, double importe, String metodo,
                         String codigoAutorizacion, String ultimos4,
                         String claveIdempotencia) {
        Map<String, Object> cuerpo = new LinkedHashMap<>();
        cuerpo.put("orderId", orderId);
        cuerpo.put("amount", importe);
        cuerpo.put("method", metodo);
        cuerpo.put("idempotencyKey", claveIdempotencia);
        if (codigoAutorizacion != null && !codigoAutorizacion.isBlank()) {
            cuerpo.put("authorizationCode", codigoAutorizacion.trim());
        }
        if (ultimos4 != null && ultimos4.matches("\\d{4}")) {
            cuerpo.put("cardLast4", ultimos4);
        }
        cuerpo.put("notes", "Cobro simulado desde el cliente de escritorio Java");
        return Payment.de(api.post("/pagos", cuerpo, true));
    }

    /** Los pagos de los pedidos del usuario del token. */
    public List<Payment> mios(int limit) {
        JsonNode respuesta = api.get("/pagos", Map.of("limit", Integer.toString(limit)), true);
        List<Payment> pagos = new ArrayList<>();
        JsonNode arreglo = respuesta.get("payments");
        if (arreglo != null && arreglo.isArray()) {
            arreglo.forEach(nodo -> pagos.add(Payment.de(nodo)));
        }
        return List.copyOf(pagos);
    }

    public List<Payment> dePedido(int orderId) {
        JsonNode respuesta = api.get("/pagos",
                Map.of("orderId", Integer.toString(orderId), "limit", "50"), true);
        List<Payment> pagos = new ArrayList<>();
        JsonNode arreglo = respuesta.get("payments");
        if (arreglo != null && arreglo.isArray()) {
            arreglo.forEach(nodo -> pagos.add(Payment.de(nodo)));
        }
        return List.copyOf(pagos);
    }
}
