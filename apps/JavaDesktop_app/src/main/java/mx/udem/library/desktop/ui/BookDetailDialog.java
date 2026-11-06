package mx.udem.library.desktop.ui;

import javafx.geometry.Insets;
import javafx.scene.control.ButtonType;
import javafx.scene.control.Dialog;
import javafx.scene.control.Label;
import javafx.scene.control.ScrollPane;
import javafx.scene.control.Spinner;
import javafx.scene.image.ImageView;
import javafx.scene.layout.HBox;
import javafx.scene.layout.Region;
import javafx.scene.layout.VBox;
import mx.udem.library.desktop.Contexto;
import mx.udem.library.desktop.model.Author;
import mx.udem.library.desktop.model.Book;
import mx.udem.library.desktop.model.Ref;

import java.util.stream.Collectors;

/**
 * Ficha de un libro, con la informacion de sus autores.
 *
 * Los autores llegan del catalogo solo como (id, nombre); la ficha del
 * autor -- cuantas obras tiene y cuales -- vive en OTRO microservicio
 * (authors, 5003), de modo que se pide aparte y en segundo plano. Es
 * un ejemplo claro de lo que significa integrar: una pantalla, dos
 * servicios independientes.
 */
public final class BookDetailDialog extends Dialog<Void> {

    public BookDetailDialog(Contexto contexto, Book libro) {
        setTitle(libro.title());
        setHeaderText(null);
        getDialogPane().getButtonTypes().add(ButtonType.CLOSE);
        getDialogPane().setPrefWidth(720);

        ImageView portada = new ImageView();
        Imagenes.cargarEn(portada, libro.portada().map(img -> img.url()).orElse(null), 200, 290);

        Label titulo = new Label(libro.title());
        titulo.getStyleClass().add("titulo-grande");
        titulo.setWrapText(true);

        Label autores = new Label(libro.autoresEnLinea());
        autores.getStyleClass().add("subtitulo");

        Label ficha = new Label(String.format(
                "ISBN %s · %d · %s · %s%nFormato: %s · Categoria: %s%nGeneros: %s",
                libro.isbn(), libro.publicationYear(), libro.precioFormateado(),
                libro.hayExistencias() ? "Disponibles: " + libro.stock() : "Sin existencias",
                libro.format() == null ? "—" : libro.format().name(),
                libro.category() == null ? "—" : libro.category().name(),
                libro.generosEnLinea().isBlank() ? "—" : libro.generosEnLinea()));
        ficha.setWrapText(true);

        Label tituloDescripcion = new Label("Descripcion");
        tituloDescripcion.getStyleClass().add("titulo-seccion");

        Label descripcion = new Label(libro.descripcion());
        descripcion.setWrapText(true);
        descripcion.setMaxWidth(440);

        Label notaDescripcion = new Label(
                "El catalogo no almacena una sinopsis: este texto son las "
                + "definiciones de los conceptos asociados al libro, que es la "
                + "unica informacion descriptiva que publica el servicio.");
        notaDescripcion.getStyleClass().add("pie");
        notaDescripcion.setWrapText(true);
        notaDescripcion.setMaxWidth(440);

        Label tituloAutores = new Label("Sobre los autores");
        tituloAutores.getStyleClass().add("titulo-seccion");
        VBox cajaAutores = new VBox(6);
        cargarAutores(contexto, libro, cajaAutores);

        Spinner<Integer> cantidad = new Spinner<>(1, Math.max(1, Math.min(100, libro.stock())), 1);
        cantidad.setPrefWidth(80);
        cantidad.setDisable(!libro.hayExistencias());

        javafx.scene.control.Button agregar = new javafx.scene.control.Button("Agregar a la cesta");
        agregar.getStyleClass().add("boton-principal");
        agregar.setDisable(!libro.hayExistencias());
        agregar.setOnAction(evento -> {
            contexto.cesta().agregar(libro, cantidad.getValue());
            agregar.setText("Agregado a la cesta");
            agregar.setDisable(true);
        });

        VBox derecha = new VBox(10, titulo, autores, ficha,
                tituloDescripcion, descripcion, notaDescripcion,
                tituloAutores, cajaAutores,
                new HBox(8, cantidad, agregar));
        derecha.setPrefWidth(450);

        HBox contenido = new HBox(20, new VBox(portada), derecha);
        contenido.setPadding(new Insets(16));

        ScrollPane scroll = new ScrollPane(contenido);
        scroll.setFitToWidth(true);
        scroll.setPrefHeight(540);
        Ui.aplicarEstilos(getDialogPane());
        getDialogPane().setContent(scroll);
    }

    private void cargarAutores(Contexto contexto, Book libro, VBox destino) {
        if (libro.authors().isEmpty()) {
            destino.getChildren().add(etiquetaTenue("Este libro no tiene autores registrados."));
            return;
        }
        destino.getChildren().add(etiquetaTenue("Consultando el servicio de autores..."));

        Tareas.enSegundoPlano(
                () -> libro.authors().stream()
                        .map(Ref::ref)
                        .filter(id -> id > 0)
                        .map(id -> {
                            try {
                                return contexto.autores().porId(id);
                            } catch (RuntimeException exc) {
                                return null;
                            }
                        })
                        .filter(autor -> autor != null)
                        .collect(Collectors.toList()),
                autores -> {
                    destino.getChildren().clear();
                    if (autores.isEmpty()) {
                        destino.getChildren().add(etiquetaTenue(
                                "No se pudo consultar la ficha de los autores."));
                        return;
                    }
                    for (Author autor : autores) {
                        Label nombre = new Label(autor.name() + " · " + autor.bookCount()
                                + (autor.bookCount() == 1 ? " obra" : " obras") + " en el catalogo");
                        nombre.getStyleClass().add("titulo-tarjeta");
                        destino.getChildren().add(nombre);

                        String otras = autor.books().stream()
                                .filter(obra -> obra.id() != libro.id())
                                .map(Author.BookSummary::title)
                                .limit(4)
                                .collect(Collectors.joining(" · "));
                        if (!otras.isBlank()) {
                            destino.getChildren().add(etiquetaTenue("Tambien: " + otras));
                        }
                    }
                },
                error -> {
                    destino.getChildren().clear();
                    destino.getChildren().add(etiquetaTenue(
                            "No se pudo consultar el servicio de autores: " + Mensajes.de(error)));
                });
    }

    private static Label etiquetaTenue(String texto) {
        Label etiqueta = new Label(texto);
        etiqueta.getStyleClass().add("subtitulo");
        etiqueta.setWrapText(true);
        etiqueta.setMaxWidth(440);
        return etiqueta;
    }
}
