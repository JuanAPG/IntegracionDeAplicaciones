package mx.udem.library.desktop.model;

import com.fasterxml.jackson.databind.JsonNode;

import java.util.ArrayList;
import java.util.List;

/**
 * Un autor del servicio de autores (5003).
 *
 * El listado trae solo id, nombre y cuantas obras; el detalle anade un
 * RESUMEN de los libros, con seis campos y nada mas. Esa escasez es
 * deliberada del servicio: la ficha completa de un libro vive en el
 * servicio de libros, y duplicarla aqui obligaria a mantener dos
 * verdades.
 */
public record Author(int id, String name, int bookCount, List<BookSummary> books) {

    public static Author de(JsonNode nodo) {
        List<BookSummary> libros = new ArrayList<>();
        JsonNode arreglo = nodo.get("books");
        if (arreglo != null && arreglo.isArray()) {
            arreglo.forEach(elemento -> libros.add(BookSummary.de(elemento)));
        }
        return new Author(
                nodo.path("id").asInt(0),
                nodo.path("name").asText(""),
                nodo.path("bookCount").asInt(libros.size()),
                List.copyOf(libros));
    }

    /** Resumen de obra que devuelve el servicio de autores. */
    public record BookSummary(int id, String isbn, String title,
                              int publicationYear, double price, int stock) {

        public static BookSummary de(JsonNode nodo) {
            return new BookSummary(
                    nodo.path("id").asInt(0),
                    nodo.path("isbn").asText(""),
                    nodo.path("title").asText(""),
                    nodo.path("publicationYear").asInt(0),
                    nodo.path("price").asDouble(0),
                    nodo.path("stock").asInt(0));
        }
    }
}
