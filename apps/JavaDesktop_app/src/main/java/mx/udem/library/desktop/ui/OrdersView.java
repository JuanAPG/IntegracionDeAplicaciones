package mx.udem.library.desktop.ui;

import javafx.beans.property.SimpleStringProperty;
import javafx.collections.FXCollections;
import javafx.geometry.Insets;
import javafx.geometry.Pos;
import javafx.scene.control.Button;
import javafx.scene.control.Label;
import javafx.scene.control.ProgressIndicator;
import javafx.scene.control.TableColumn;
import javafx.scene.control.TableView;
import javafx.scene.control.TextArea;
import javafx.scene.layout.BorderPane;
import javafx.scene.layout.HBox;
import javafx.scene.layout.Priority;
import javafx.scene.layout.Region;
import javafx.scene.layout.VBox;
import mx.udem.library.desktop.Contexto;
import mx.udem.library.desktop.model.Order;
import mx.udem.library.desktop.model.OrderLine;
import mx.udem.library.desktop.model.Payment;

import java.util.List;
import java.util.function.Consumer;
import java.util.stream.Collectors;

/**
 * Mis compras (Modulo 5).
 *
 * LOS DATOS COMERCIALES SALEN DE pedidos (5004) Y pagos (5005), y se
 * ensena el estado que devuelven, sin interpretarlo. Si un pago quedo
 * `autorizado` y el pedido sigue `pendiente`, eso es lo que se ve: el
 * enunciado pide expresamente no inventar estados de pago exitoso.
 *
 * EL LISTADO NO TRAE LAS LINEAS -- el servicio solo las incluye en el
 * detalle -- de modo que al seleccionar un pedido se pide su ficha
 * completa. Es una peticion mas, pero es el contrato real.
 */
public final class OrdersView extends BorderPane {

    private final Contexto contexto;
    private final Consumer<String> alRastrear;

    private final TableView<Order> tabla = new TableView<>();
    private final TextArea detalle = new TextArea();
    private final ProgressIndicator girando = new ProgressIndicator();
    private final Button rastrear = new Button("Rastrear este pedido");

    public OrdersView(Contexto contexto, Consumer<String> alRastrear) {
        this.contexto = contexto;
        this.alRastrear = alRastrear;
        setPadding(new Insets(16));

        Label titulo = new Label("Mis compras");
        titulo.getStyleClass().add("titulo-grande");

        Button recargar = new Button("Actualizar");
        recargar.setOnAction(evento -> cargar());
        girando.setVisible(false);
        girando.setMaxSize(20, 20);

        Region separador = new Region();
        HBox.setHgrow(separador, Priority.ALWAYS);
        HBox cabecera = new HBox(12, titulo, girando, separador, recargar);
        cabecera.setAlignment(Pos.CENTER_LEFT);
        cabecera.setPadding(new Insets(0, 0, 12, 0));
        setTop(cabecera);

        construirTabla();
        detalle.setEditable(false);
        detalle.setPrefRowCount(12);
        detalle.getStyleClass().add("bitacora");
        detalle.setPromptText("Selecciona un pedido para ver sus libros, su importe "
                + "y el estado de su pago.");

        rastrear.getStyleClass().add("boton-principal");
        rastrear.setDisable(true);
        rastrear.setOnAction(evento -> {
            Order seleccionado = tabla.getSelectionModel().getSelectedItem();
            if (seleccionado != null) {
                alRastrear.accept(seleccionado.codigoRastreo());
            }
        });

        VBox inferior = new VBox(10, detalle, new HBox(10, rastrear));
        inferior.setPadding(new Insets(12, 0, 0, 0));

        setCenter(tabla);
        setBottom(inferior);
        cargar();
    }

    private void construirTabla() {
        TableColumn<Order, String> colNumero = new TableColumn<>("Pedido");
        colNumero.setCellValueFactory(d -> new SimpleStringProperty(d.getValue().orderNumber()));
        colNumero.setPrefWidth(130);

        TableColumn<Order, String> colFecha = new TableColumn<>("Fecha");
        colFecha.setCellValueFactory(d -> new SimpleStringProperty(
                fecha(d.getValue().placedAt())));
        colFecha.setPrefWidth(150);

        TableColumn<Order, String> colEstado = new TableColumn<>("Estado");
        colEstado.setCellValueFactory(d -> new SimpleStringProperty(d.getValue().status()));
        colEstado.setPrefWidth(110);

        TableColumn<Order, String> colPiezas = new TableColumn<>("Articulos");
        colPiezas.setCellValueFactory(d -> new SimpleStringProperty(
                d.getValue().itemCount() + " en " + d.getValue().lineCount() + " titulos"));
        colPiezas.setPrefWidth(140);

        TableColumn<Order, String> colTotal = new TableColumn<>("Total");
        colTotal.setCellValueFactory(d -> new SimpleStringProperty(d.getValue().totalFormateado()));
        colTotal.setPrefWidth(130);

        TableColumn<Order, String> colRastreo = new TableColumn<>("Codigo de rastreo");
        colRastreo.setCellValueFactory(d -> new SimpleStringProperty(d.getValue().codigoRastreo()));
        colRastreo.setPrefWidth(190);

        tabla.getColumns().addAll(colNumero, colFecha, colEstado, colPiezas, colTotal, colRastreo);
        tabla.setPlaceholder(new Label("Todavia no tienes compras."));
        tabla.setColumnResizePolicy(TableView.CONSTRAINED_RESIZE_POLICY_FLEX_LAST_COLUMN);
        tabla.getSelectionModel().selectedItemProperty().addListener(
                (obs, antes, ahora) -> {
                    rastrear.setDisable(ahora == null);
                    if (ahora != null) {
                        cargarDetalle(ahora);
                    }
                });
    }

    public void cargar() {
        girando.setVisible(true);
        Tareas.enSegundoPlano(
                () -> contexto.pedidos().mios(50),
                pedidos -> {
                    girando.setVisible(false);
                    tabla.setItems(FXCollections.observableArrayList(pedidos));
                },
                error -> {
                    girando.setVisible(false);
                    detalle.setText("No se pudieron cargar tus pedidos:\n" + Mensajes.de(error));
                });
    }

    /**
     * Ficha completa: las lineas vienen del servicio de pedidos y los
     * pagos del de pagos. Dos microservicios para una sola pantalla.
     */
    private void cargarDetalle(Order resumen) {
        detalle.setText("Consultando el pedido " + resumen.orderNumber() + "...");
        Tareas.enSegundoPlano(
                () -> {
                    Order completo = contexto.pedidos().detalle(resumen.id());
                    List<Payment> pagos;
                    try {
                        pagos = contexto.pagos().dePedido(resumen.id());
                    } catch (RuntimeException exc) {
                        pagos = List.of();
                    }
                    return texto(completo, pagos);
                },
                detalle::setText,
                error -> detalle.setText("No se pudo cargar el detalle:\n" + Mensajes.de(error)));
    }

    private String texto(Order pedido, List<Payment> pagos) {
        StringBuilder sb = new StringBuilder();
        sb.append("Pedido ").append(pedido.orderNumber())
          .append("   ·   estado: ").append(pedido.status())
          .append("   ·   ").append(fecha(pedido.placedAt())).append("\n")
          .append("Codigo de rastreo: ").append(pedido.codigoRastreo()).append("\n\n");

        sb.append("Libros\n");
        for (OrderLine linea : pedido.lines()) {
            sb.append(String.format("  %-44s  x%-3d  $%,10.2f%n",
                    recortar(linea.title(), 44), linea.quantity(), linea.lineTotal()));
        }
        if (pedido.lines().isEmpty()) {
            sb.append("  (el servicio no devolvio las lineas de este pedido)\n");
        }

        sb.append(String.format("%nSubtotal  $%,.2f%nEnvio     $%,.2f%nTotal     $%,.2f %s%n",
                pedido.subtotal(), pedido.shippingCost(), pedido.total(), pedido.currency()));

        sb.append("\nPagos\n");
        if (pagos.isEmpty()) {
            sb.append("  Sin pagos registrados.\n");
        } else {
            for (Payment pago : pagos) {
                sb.append(String.format("  %s  %s  %s  (%s)%n",
                        pago.reference(), pago.importeFormateado(), pago.status(), pago.methodName()));
            }
            boolean algunoAplicado = pagos.stream().anyMatch(Payment::estaAplicado);
            if (!algunoAplicado) {
                sb.append("  Ningun pago esta APLICADO todavia, de modo que el pedido "
                        + "no figura como pagado.\n");
            }
        }
        return sb.toString();
    }

    private static String recortar(String texto, int largo) {
        if (texto == null) {
            return "";
        }
        return texto.length() <= largo ? texto : texto.substring(0, largo - 1) + "…";
    }

    private static String fecha(String iso) {
        if (iso == null || iso.length() < 16) {
            return iso == null ? "" : iso;
        }
        return iso.substring(0, 10) + " " + iso.substring(11, 16);
    }
}
