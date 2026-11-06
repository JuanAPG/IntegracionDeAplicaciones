package mx.udem.library.desktop.ui;

import javafx.beans.property.SimpleObjectProperty;
import javafx.beans.property.SimpleStringProperty;
import javafx.collections.FXCollections;
import javafx.geometry.Insets;
import javafx.geometry.Pos;
import javafx.scene.control.Button;
import javafx.scene.control.Label;
import javafx.scene.control.Spinner;
import javafx.scene.control.TableCell;
import javafx.scene.control.TableColumn;
import javafx.scene.control.TableView;
import javafx.scene.layout.BorderPane;
import javafx.scene.layout.HBox;
import javafx.scene.layout.Priority;
import javafx.scene.layout.Region;
import javafx.scene.layout.VBox;
import mx.udem.library.desktop.Contexto;
import mx.udem.library.desktop.cart.Cart;

import java.util.function.Consumer;

/**
 * La cesta de compras (Modulo 3).
 *
 * LOS IMPORTES DE ESTA PANTALLA SON UNA ESTIMACION. El total de verdad
 * lo calcula el servicio de pedidos con los precios que congela del
 * catalogo en el momento de la compra. Se dice en pantalla, porque un
 * usuario que ve 1 918.00 aqui y 1 950.00 en la confirmacion tiene
 * derecho a saber por que.
 */
public final class CartView extends BorderPane {

    private final Contexto contexto;
    private final TableView<Cart.Linea> tabla = new TableView<>();
    private final Label subtotal = new Label();
    private final Label ejemplares = new Label();
    private final Button comprar = new Button("Confirmar compra");

    public CartView(Contexto contexto, Consumer<String> alComprar) {
        this.contexto = contexto;
        setPadding(new Insets(16));

        Label titulo = new Label("Tu cesta");
        titulo.getStyleClass().add("titulo-grande");
        setTop(new VBox(4, titulo, ejemplares));
        BorderPane.setMargin(getTop(), new Insets(0, 0, 12, 0));

        construirTabla();
        setCenter(tabla);
        setBottom(pie(alComprar));

        contexto.cesta().addListener(cesta -> Tareas.enHiloDeInterfaz(this::refrescar));
        refrescar();
    }

    private void construirTabla() {
        TableColumn<Cart.Linea, String> colTitulo = new TableColumn<>("Libro");
        colTitulo.setCellValueFactory(dato ->
                new SimpleStringProperty(dato.getValue().libro().title()));
        colTitulo.setPrefWidth(300);

        TableColumn<Cart.Linea, String> colAutor = new TableColumn<>("Autor");
        colAutor.setCellValueFactory(dato ->
                new SimpleStringProperty(dato.getValue().libro().autoresEnLinea()));
        colAutor.setPrefWidth(190);

        TableColumn<Cart.Linea, String> colPrecio = new TableColumn<>("Precio");
        colPrecio.setCellValueFactory(dato ->
                new SimpleStringProperty(dato.getValue().libro().precioFormateado()));
        colPrecio.setPrefWidth(120);

        TableColumn<Cart.Linea, Cart.Linea> colCantidad = new TableColumn<>("Cantidad");
        colCantidad.setCellValueFactory(dato -> new SimpleObjectProperty<>(dato.getValue()));
        colCantidad.setPrefWidth(110);
        colCantidad.setCellFactory(columna -> new TableCell<>() {
            @Override
            protected void updateItem(Cart.Linea linea, boolean vacia) {
                super.updateItem(linea, vacia);
                if (vacia || linea == null) {
                    setGraphic(null);
                    return;
                }
                int tope = Math.max(1, Math.min(100, linea.libro().stock()));
                Spinner<Integer> control = new Spinner<>(1, tope, linea.cantidad());
                control.setPrefWidth(90);
                control.valueProperty().addListener((obs, antes, ahora) -> {
                    if (ahora != null && ahora != linea.cantidad()) {
                        contexto.cesta().establecerCantidad(linea.libro().id(), ahora);
                    }
                });
                setGraphic(control);
            }
        });

        TableColumn<Cart.Linea, String> colSubtotal = new TableColumn<>("Subtotal");
        colSubtotal.setCellValueFactory(dato -> new SimpleStringProperty(
                String.format("$%,.2f", dato.getValue().subtotal())));
        colSubtotal.setPrefWidth(120);

        TableColumn<Cart.Linea, Cart.Linea> colQuitar = new TableColumn<>("");
        colQuitar.setCellValueFactory(dato -> new SimpleObjectProperty<>(dato.getValue()));
        colQuitar.setPrefWidth(90);
        colQuitar.setCellFactory(columna -> new TableCell<>() {
            @Override
            protected void updateItem(Cart.Linea linea, boolean vacia) {
                super.updateItem(linea, vacia);
                if (vacia || linea == null) {
                    setGraphic(null);
                    return;
                }
                Button quitar = new Button("Quitar");
                quitar.setOnAction(evento -> contexto.cesta().quitar(linea.libro().id()));
                setGraphic(quitar);
            }
        });

        tabla.getColumns().addAll(colTitulo, colAutor, colPrecio, colCantidad, colSubtotal, colQuitar);
        tabla.setPlaceholder(new Label("Tu cesta esta vacia. Agrega libros desde el catalogo."));
        tabla.setColumnResizePolicy(TableView.CONSTRAINED_RESIZE_POLICY_FLEX_LAST_COLUMN);
    }

    private Region pie(Consumer<String> alComprar) {
        subtotal.getStyleClass().add("precio-total");

        Label nota = new Label("""
                El importe definitivo lo calcula el servicio de pedidos con los precios \
                congelados del catalogo. Antes de confirmar se vuelven a comprobar precios \
                y existencias.""");
        nota.getStyleClass().add("pie");
        nota.setWrapText(true);
        nota.setMaxWidth(520);

        Button vaciar = new Button("Vaciar cesta");
        vaciar.setOnAction(evento -> {
            if (!contexto.cesta().estaVacia()
                    && Tareas.confirmar("Vaciar la cesta", "Se quitaran todos los libros.")) {
                contexto.cesta().vaciar();
            }
        });

        comprar.getStyleClass().add("boton-principal");
        comprar.setOnAction(evento -> new CheckoutDialog(contexto, alComprar).showAndWait());

        Region separador = new Region();
        HBox.setHgrow(separador, Priority.ALWAYS);

        HBox fila = new HBox(12, nota, separador, subtotal, vaciar, comprar);
        fila.setAlignment(Pos.CENTER_RIGHT);
        fila.setPadding(new Insets(14, 0, 0, 0));
        return fila;
    }

    private void refrescar() {
        tabla.setItems(FXCollections.observableArrayList(contexto.cesta().lineas()));
        subtotal.setText(String.format("Subtotal: $%,.2f MXN", contexto.cesta().subtotal()));
        int piezas = contexto.cesta().totalEjemplares();
        ejemplares.setText(piezas == 0
                ? "Sin articulos"
                : piezas + (piezas == 1 ? " ejemplar" : " ejemplares")
                  + " · " + contexto.cesta().lineas().size() + " titulos");
        ejemplares.getStyleClass().setAll("subtitulo");
        comprar.setDisable(contexto.cesta().estaVacia());
    }
}
