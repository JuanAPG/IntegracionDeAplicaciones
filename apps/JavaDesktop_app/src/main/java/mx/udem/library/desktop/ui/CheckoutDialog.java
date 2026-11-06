package mx.udem.library.desktop.ui;

import javafx.geometry.Insets;
import javafx.scene.control.ButtonBar;
import javafx.scene.control.ButtonType;
import javafx.scene.control.ChoiceBox;
import javafx.scene.control.Dialog;
import javafx.scene.control.Label;
import javafx.scene.control.ProgressIndicator;
import javafx.scene.control.TextArea;
import javafx.scene.control.TextField;
import javafx.scene.layout.GridPane;
import javafx.scene.layout.HBox;
import javafx.scene.layout.VBox;
import mx.udem.library.desktop.Contexto;
import mx.udem.library.desktop.cart.Cart;
import mx.udem.library.desktop.model.Balance;
import mx.udem.library.desktop.model.Order;
import mx.udem.library.desktop.model.Payment;
import mx.udem.library.desktop.model.PaymentMethod;

import java.security.SecureRandom;
import java.util.Base64;
import java.util.List;
import java.util.function.Consumer;

/**
 * Simulacion de compra (Modulo 4): pedido + pago, con servicios reales.
 *
 * EL FLUJO, Y POR QUE CADA PASO ES NECESARIO
 *
 *  1. Revalidar la cesta contra el catalogo. Cortesia, no autoridad: el
 *     servicio lo volvera a comprobar de forma atomica. Evita que el
 *     usuario llegue al final para descubrir que un libro se agoto.
 *  2. POST /pedidos  -> crea el pedido y devuelve su numero REAL
 *     (PED-000042) y su total, calculado por el servidor. El cliente NO
 *     manda precios: los congela el procedimiento almacenado.
 *  3. GET /pedidos/<id>/saldo (en PAGOS, 5005) -> cuanto hay que cobrar.
 *     Se usa ese importe y no el total: el servicio rechaza con 409 un
 *     pago que exceda el saldo comprometido.
 *  4. POST /pagos -> registra el cobro.
 *  5. Se ensena el estado REAL que devolvio el servicio. Si el pago
 *     quedo `autorizado` y no `aplicado`, se dice: no se finge un pago
 *     exitoso.
 *
 * NO SE PIDEN NI SE ENVIAN DATOS DE TARJETA. El servicio rechaza con 400
 * cualquier cuerpo que traiga numero de tarjeta, CVV o titular. Lo unico
 * que viaja es un codigo de autorizacion simulado.
 *
 * LA CLAVE DE IDEMPOTENCIA SE GENERA UNA VEZ AL ABRIR EL DIALOGO, no en
 * cada clic: asi un doble clic o un reintento de red devuelven el MISMO
 * pago en lugar de cobrar dos veces.
 */
public final class CheckoutDialog extends Dialog<Void> {

    private static final SecureRandom ALEATORIO = new SecureRandom();

    private final Contexto contexto;
    private final Consumer<String> alTerminar;
    private final String claveIdempotencia = nuevaClave();

    private final TextField direccion = new TextField();
    private final TextField costoEnvio = new TextField("120.00");
    private final ChoiceBox<PaymentMethod> metodo = new ChoiceBox<>();
    private final TextArea bitacora = new TextArea();
    private final ProgressIndicator girando = new ProgressIndicator();
    private final Label aviso = new Label();

    private final ButtonType botonComprar =
            new ButtonType("Comprar", ButtonBar.ButtonData.OK_DONE);

    public CheckoutDialog(Contexto contexto, Consumer<String> alTerminar) {
        this.contexto = contexto;
        this.alTerminar = alTerminar;

        setTitle("Confirmar compra");
        setHeaderText("Revisa tu pedido antes de confirmar");
        getDialogPane().setPrefWidth(620);
        getDialogPane().getButtonTypes().addAll(botonComprar, ButtonType.CLOSE);

        direccion.setPromptText("Calle, numero, colonia, Monterrey, N.L.");
        direccion.setText("Av. Lazaro Cardenas 1000, Monterrey, N.L.");
        direccion.setPrefColumnCount(34);

        metodo.setDisable(true);
        bitacora.setEditable(false);
        bitacora.setPrefRowCount(9);
        bitacora.getStyleClass().add("bitacora");
        girando.setVisible(false);
        girando.setMaxSize(20, 20);
        aviso.setWrapText(true);
        aviso.getStyleClass().add("pie");

        Cart cesta = contexto.cesta();
        Label resumen = new Label(String.format(
                "%d titulos · %d ejemplares · subtotal estimado $%,.2f MXN",
                cesta.lineas().size(), cesta.totalEjemplares(), cesta.subtotal()));
        resumen.getStyleClass().add("subtitulo");

        GridPane rejilla = new GridPane();
        rejilla.setHgap(10);
        rejilla.setVgap(9);
        rejilla.add(new Label("Direccion de envio:"), 0, 0);
        rejilla.add(direccion, 1, 0);
        rejilla.add(new Label("Costo de envio:"), 0, 1);
        rejilla.add(costoEnvio, 1, 1);
        rejilla.add(new Label("Metodo de pago:"), 0, 2);
        rejilla.add(new HBox(8, metodo, girando), 1, 2);

        Label notaTarjeta = new Label(
                "Esta aplicacion NO pide ni envia datos de tarjeta: el servicio de "
                + "pagos rechaza cualquier campo de ese tipo. El cobro es simulado "
                + "y se registra con un codigo de autorizacion ficticio.");
        notaTarjeta.getStyleClass().add("pie");
        notaTarjeta.setWrapText(true);
        notaTarjeta.setMaxWidth(560);

        VBox contenido = new VBox(12, resumen, rejilla, notaTarjeta, aviso, bitacora);
        contenido.setPadding(new Insets(14));
        Ui.aplicarEstilos(getDialogPane());
        getDialogPane().setContent(contenido);

        cargarMetodos();

        // El boton no cierra el dialogo: consume el evento y hace el
        // flujo dentro, para poder ensenar el progreso paso a paso.
        getDialogPane().lookupButton(botonComprar).addEventFilter(
                javafx.event.ActionEvent.ACTION, evento -> {
                    evento.consume();
                    comprar();
                });
    }

    private void cargarMetodos() {
        girando.setVisible(true);
        Tareas.enSegundoPlano(
                () -> contexto.pagos().metodos(),
                (List<PaymentMethod> metodos) -> {
                    girando.setVisible(false);
                    metodos.stream().filter(PaymentMethod::isActive).forEach(metodo.getItems()::add);
                    if (!metodo.getItems().isEmpty()) {
                        // Se preselecciona el que NO exige autorizacion
                        // (efectivo): es el unico con el que la compra
                        // queda liquidada en el acto, que es lo que hace
                        // util la demostracion.
                        metodo.getSelectionModel().select(
                                metodo.getItems().stream()
                                        .filter(m -> !m.requiresAuthorization())
                                        .findFirst()
                                        .orElse(metodo.getItems().get(0)));
                        metodo.setDisable(false);
                        actualizarAviso();
                    }
                    metodo.setOnAction(evento -> actualizarAviso());
                },
                error -> {
                    girando.setVisible(false);
                    aviso.setText("No se pudieron cargar los metodos de pago: "
                            + Mensajes.de(error));
                });
    }

    private void actualizarAviso() {
        PaymentMethod elegido = metodo.getValue();
        if (elegido == null) {
            return;
        }
        aviso.setText(elegido.requiresAuthorization()
                ? "\"" + elegido.name() + "\" exige autorizacion: el pago nacera como "
                  + "AUTORIZADO y el pedido seguira pendiente hasta que alguien con "
                  + "permiso lo aplique. Es el comportamiento real del servicio."
                : "\"" + elegido.name() + "\" no exige autorizacion: el pago nacera "
                  + "APLICADO y el pedido pasara a pagado en la misma transaccion.");
    }

    private void comprar() {
        PaymentMethod elegido = metodo.getValue();
        if (elegido == null) {
            Tareas.aviso("Falta el metodo", "Elige un metodo de pago.");
            return;
        }
        double envio;
        try {
            envio = Double.parseDouble(costoEnvio.getText().trim());
        } catch (NumberFormatException exc) {
            Tareas.aviso("Costo de envio", "Escribe un numero, por ejemplo 120.00");
            return;
        }

        getDialogPane().lookupButton(botonComprar).setDisable(true);
        girando.setVisible(true);
        bitacora.clear();
        anotar("1/4  Revalidando la cesta contra el catalogo...");

        Tareas.enSegundoPlano(
                () -> ejecutarCompra(envio, elegido),
                resultado -> {
                    girando.setVisible(false);
                    anotar("");
                    anotar(resultado.resumen());
                    if (resultado.pedido() != null) {
                        contexto.cesta().vaciar();
                        alTerminar.accept(resultado.pedido().codigoRastreo());
                    }
                },
                error -> {
                    girando.setVisible(false);
                    getDialogPane().lookupButton(botonComprar).setDisable(false);
                    anotar("");
                    anotar("No se completo: " + Mensajes.de(error));
                });
    }

    /** Todo el flujo de compra. Corre fuera del hilo de la interfaz. */
    private Resultado ejecutarCompra(double envio, PaymentMethod elegido) {
        List<Cart.Aviso> avisos = contexto.cesta().revalidar(id -> contexto.libros().porId(id));
        avisos.forEach(a -> anotar("     aviso: " + a.texto()));
        if (contexto.cesta().estaVacia()) {
            throw new IllegalStateException(
                    "La cesta quedo vacia tras revalidarla contra el catalogo.");
        }

        anotar("2/4  Creando el pedido en el servicio de pedidos...");
        Order pedido = contexto.pedidos().crear(
                contexto.cesta(), direccion.getText(), envio,
                "Pedido creado desde el cliente de escritorio Java");
        anotar("     pedido " + pedido.orderNumber() + " creado. Total: "
                + pedido.totalFormateado() + " · estado: " + pedido.status());

        anotar("3/4  Consultando el saldo en el servicio de pagos...");
        Balance saldo = contexto.pagos().saldo(pedido.id());
        anotar(String.format("     total %.2f · pagado %.2f · por cobrar %.2f",
                saldo.total(), saldo.paid(), saldo.balance()));

        anotar("4/4  Registrando el pago...");
        String autorizacion = elegido.requiresAuthorization()
                ? "SIM-" + Long.toHexString(ALEATORIO.nextLong() & 0xFFFFFFFFL).toUpperCase()
                : null;
        Payment pago = contexto.pagos().pagar(
                pedido.id(), saldo.balance(), elegido.name(),
                autorizacion, null, claveIdempotencia);

        StringBuilder resumen = new StringBuilder();
        resumen.append("Compra registrada.\n")
               .append("Pedido:  ").append(pedido.orderNumber()).append("  (")
               .append(pedido.totalFormateado()).append(")\n")
               .append("Pago:    ").append(pago.reference()).append("  ")
               .append(pago.importeFormateado()).append("  estado: ").append(pago.status());
        if (pago.idempotentReplay()) {
            resumen.append("\n(ya existia con la misma clave de idempotencia: NO se cobro dos veces)");
        }
        resumen.append("\nCodigo de rastreo: ").append(pedido.codigoRastreo());
        if (!pago.estaAplicado()) {
            resumen.append("\n\nEl pago quedo en estado '").append(pago.status())
                   .append("'. El pedido no figura como pagado hasta que se aplique: ")
                   .append("asi lo decide el servicio, y esta aplicacion no lo disimula.");
        }
        return new Resultado(pedido, pago, resumen.toString());
    }

    private void anotar(String linea) {
        Tareas.enHiloDeInterfaz(() -> bitacora.appendText(linea + "\n"));
    }

    private static String nuevaClave() {
        byte[] bytes = new byte[16];
        ALEATORIO.nextBytes(bytes);
        return "java-desktop-" + Base64.getUrlEncoder().withoutPadding().encodeToString(bytes);
    }

    private record Resultado(Order pedido, Payment pago, String resumen) { }
}
