package mx.udem.library.desktop.ui;

import javafx.geometry.Insets;
import javafx.geometry.Pos;
import javafx.scene.control.Button;
import javafx.scene.control.Label;
import javafx.scene.control.ProgressIndicator;
import javafx.scene.control.ScrollPane;
import javafx.scene.control.Spinner;
import javafx.scene.control.TextField;
import javafx.scene.image.ImageView;
import javafx.scene.layout.BorderPane;
import javafx.scene.layout.FlowPane;
import javafx.scene.layout.HBox;
import javafx.scene.layout.Priority;
import javafx.scene.layout.Region;
import javafx.scene.layout.VBox;
import mx.udem.library.desktop.Contexto;
import mx.udem.library.desktop.model.Book;
import mx.udem.library.desktop.service.BooksService;

/**
 * El catalogo de libros (Modulo 2).
 *
 * LOS DATOS SALEN DE books (5001) Y authors (5003), nunca de la base.
 * El catalogo es PUBLICO: estas lecturas van sin token a proposito.
 *
 * SOBRE LA DESCRIPCION DEL LIBRO. El enunciado pide ensenar una
 * descripcion, pero el servicio NO tiene campo de sinopsis -- se
 * comprobo contra el esquema de la base y contra el serializador. Lo
 * unico descriptivo que existe son las definiciones de los conceptos
 * asociados al libro, y eso es lo que se ensena, diciendo de donde
 * viene. Inventar un texto o dejar el hueco en blanco habrian sido las
 * dos peores opciones.
 */
public final class CatalogView extends BorderPane {

    private static final int POR_PAGINA = 24;

    private final Contexto contexto;
    private final FlowPane rejilla = new FlowPane(16, 16);
    private final TextField busqueda = new TextField();
    private final Label resumen = new Label();
    private final ProgressIndicator girando = new ProgressIndicator();
    private final Button anterior = new Button("< Anteriores");
    private final Button siguiente = new Button("Siguientes >");

    private int desplazamiento = 0;
    private int total = 0;

    public CatalogView(Contexto contexto) {
        this.contexto = contexto;
        setPadding(new Insets(16));
        setTop(barraSuperior());
        setCenter(areaRejilla());
        setBottom(barraInferior());
        cargar();
    }

    private Region barraSuperior() {
        busqueda.setPromptText("Buscar por titulo, autor o ISBN");
        busqueda.setPrefWidth(340);
        busqueda.setOnAction(evento -> {
            desplazamiento = 0;
            cargar();
        });

        Button buscar = new Button("Buscar");
        buscar.getStyleClass().add("boton-principal");
        buscar.setOnAction(evento -> {
            desplazamiento = 0;
            cargar();
        });

        Button limpiar = new Button("Ver todo");
        limpiar.setOnAction(evento -> {
            busqueda.clear();
            desplazamiento = 0;
            cargar();
        });

        girando.setVisible(false);
        girando.setMaxSize(20, 20);

        Region separador = new Region();
        HBox.setHgrow(separador, Priority.ALWAYS);

        HBox barra = new HBox(10, busqueda, buscar, limpiar, girando, separador, resumen);
        barra.setAlignment(Pos.CENTER_LEFT);
        barra.setPadding(new Insets(0, 0, 14, 0));
        resumen.getStyleClass().add("subtitulo");
        return barra;
    }

    private Region areaRejilla() {
        rejilla.setPadding(new Insets(4));
        rejilla.setAlignment(Pos.TOP_LEFT);
        ScrollPane scroll = new ScrollPane(rejilla);
        scroll.setFitToWidth(true);
        scroll.getStyleClass().add("scroll-limpio");
        return scroll;
    }

    private Region barraInferior() {
        anterior.setOnAction(evento -> {
            desplazamiento = Math.max(0, desplazamiento - POR_PAGINA);
            cargar();
        });
        siguiente.setOnAction(evento -> {
            desplazamiento += POR_PAGINA;
            cargar();
        });
        HBox barra = new HBox(10, anterior, siguiente);
        barra.setAlignment(Pos.CENTER);
        barra.setPadding(new Insets(14, 0, 0, 0));
        return barra;
    }

    public void cargar() {
        girando.setVisible(true);
        rejilla.getChildren().clear();
        String texto = busqueda.getText();

        Tareas.enSegundoPlano(
                () -> contexto.libros().buscarPorTexto(texto, POR_PAGINA, desplazamiento),
                resultado -> {
                    girando.setVisible(false);
                    pintar(resultado);
                },
                error -> {
                    girando.setVisible(false);
                    resumen.setText("No se pudo cargar el catalogo.");
                    rejilla.getChildren().add(tarjetaDeError(Mensajes.de(error)));
                });
    }

    private void pintar(BooksService.Resultado resultado) {
        total = resultado.total();
        rejilla.getChildren().clear();
        resultado.libros().forEach(libro -> rejilla.getChildren().add(tarjeta(libro)));

        int desde = resultado.libros().isEmpty() ? 0 : desplazamiento + 1;
        int hasta = desplazamiento + resultado.libros().size();
        resumen.setText(total == 0 ? "Sin resultados" : desde + "-" + hasta + " de " + total);

        anterior.setDisable(desplazamiento == 0);
        siguiente.setDisable(hasta >= total);

        if (resultado.libros().isEmpty()) {
            Label vacio = new Label("Ningun libro coincide con la busqueda.");
            vacio.getStyleClass().add("subtitulo");
            rejilla.getChildren().add(vacio);
        }
    }

    private Region tarjetaDeError(String texto) {
        Label etiqueta = new Label(texto);
        etiqueta.setWrapText(true);
        etiqueta.setMaxWidth(520);
        etiqueta.getStyleClass().add("mensaje-error");
        VBox caja = new VBox(etiqueta);
        caja.setPadding(new Insets(20));
        return caja;
    }

    /** Una tarjeta de libro: portada, titulo, autores, precio y existencias. */
    private Region tarjeta(Book libro) {
        ImageView portada = new ImageView();
        Imagenes.cargarEn(portada, libro.portada().map(img -> img.url()).orElse(null), 150, 215);

        Label titulo = new Label(libro.title());
        titulo.getStyleClass().add("titulo-tarjeta");
        titulo.setWrapText(true);
        titulo.setMaxWidth(160);

        Label autores = new Label(libro.autoresEnLinea());
        autores.getStyleClass().add("subtitulo");
        autores.setWrapText(true);
        autores.setMaxWidth(160);

        Label precio = new Label(libro.precioFormateado());
        precio.getStyleClass().add("precio");

        Label existencias = new Label(libro.hayExistencias()
                ? "Disponibles: " + libro.stock()
                : "Sin existencias");
        existencias.getStyleClass().add(libro.hayExistencias() ? "disponible" : "agotado");

        Button detalle = new Button("Ver detalle");
        detalle.setMaxWidth(Double.MAX_VALUE);
        detalle.setOnAction(evento -> new BookDetailDialog(contexto, libro).showAndWait());

        Spinner<Integer> cantidad = new Spinner<>(1, Math.max(1, Math.min(100, libro.stock())), 1);
        cantidad.setPrefWidth(70);
        cantidad.setDisable(!libro.hayExistencias());

        Button agregar = new Button("Agregar");
        agregar.getStyleClass().add("boton-principal");
        agregar.setDisable(!libro.hayExistencias());
        agregar.setOnAction(evento -> {
            contexto.cesta().agregar(libro, cantidad.getValue());
            agregar.setText("Agregado");
            // Vuelve a su texto para que se pueda anadir otra vez sin
            // que parezca que el boton se quedo pulsado.
            javafx.animation.PauseTransition espera =
                    new javafx.animation.PauseTransition(javafx.util.Duration.seconds(1.2));
            espera.setOnFinished(fin -> agregar.setText("Agregar"));
            espera.play();
        });

        HBox compra = new HBox(6, cantidad, agregar);
        HBox.setHgrow(agregar, Priority.ALWAYS);
        agregar.setMaxWidth(Double.MAX_VALUE);

        VBox tarjeta = new VBox(8, portada, titulo, autores, precio, existencias, detalle, compra);
        tarjeta.getStyleClass().add("tarjeta-libro");
        tarjeta.setPadding(new Insets(12));
        tarjeta.setPrefWidth(186);
        tarjeta.setAlignment(Pos.TOP_LEFT);
        return tarjeta;
    }
}
