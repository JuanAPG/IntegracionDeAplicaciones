package mx.udem.library.desktop.model;

import com.fasterxml.jackson.databind.JsonNode;

import java.util.ArrayList;
import java.util.List;
import java.util.Optional;
import java.util.stream.Collectors;

/**
 * Un libro del catalogo, tal como lo emite el servicio de libros.
 *
 * Los nombres de los campos son los del servicio, sin renombrar: si
 * manana cambia el contrato, el compilador no ayuda, pero al menos el
 * mapeo esta en un solo sitio y se lee contra la documentacion sin
 * traducir nada mentalmente.
 */
public record Book(
        int id,
        String isbn,
        String title,
        int publicationYear,
        double price,
        String currency,
        int stock,
        Ref format,
        Ref category,
        List<Ref> authors,
        List<Ref> genres,
        List<Concept> concepts,
        List<BookImage> images) {

    public static Book de(JsonNode nodo) {
        return new Book(
                nodo.path("id").asInt(0),
                nodo.path("isbn").asText(""),
                nodo.path("title").asText(""),
                nodo.path("publicationYear").asInt(0),
                nodo.path("price").asDouble(0),
                nodo.path("currency").asText("MXN"),
                nodo.path("stock").asInt(0),
                Ref.de(nodo.get("format")),
                Ref.de(nodo.get("category")),
                lista(nodo.get("authors"), Ref::de),
                lista(nodo.get("genres"), Ref::de),
                lista(nodo.get("concepts"), Concept::de),
                lista(nodo.get("images"), BookImage::de));
    }

    private static <T> List<T> lista(JsonNode arreglo,
                                     java.util.function.Function<JsonNode, T> mapeo) {
        List<T> salida = new ArrayList<>();
        if (arreglo != null && arreglo.isArray()) {
            arreglo.forEach(elemento -> salida.add(mapeo.apply(elemento)));
        }
        return List.copyOf(salida);
    }

    /** Los autores en una linea, para la tarjeta del catalogo. */
    public String autoresEnLinea() {
        if (authors.isEmpty()) {
            return "Autor no registrado";
        }
        return authors.stream().map(Ref::name).collect(Collectors.joining(", "));
    }

    public String generosEnLinea() {
        return genres.stream().map(Ref::name).collect(Collectors.joining(", "));
    }

    /**
     * La portada: el elemento marcado con isCover.
     *
     * El SQL del servicio ya ordena las imagenes poniendo la portada
     * primero, pero se filtra por isCover de todos modos en vez de
     * confiar en el orden: depender del ORDER BY de otro componente es
     * una dependencia invisible que se rompe en silencio.
     */
    public Optional<BookImage> portada() {
        return images.stream()
                .filter(BookImage::isCover)
                .filter(BookImage::esDescargable)
                .findFirst()
                .or(() -> images.stream().filter(BookImage::esDescargable).findFirst());
    }

    /**
     * Texto descriptivo. Ver la nota de {@link Concept}: el catalogo no
     * tiene sinopsis, de modo que se construye con las definiciones de
     * los conceptos, que es el unico texto real disponible.
     */
    public String descripcion() {
        if (concepts.isEmpty()) {
            return "Este libro no tiene una descripcion registrada en el catalogo.";
        }
        return concepts.stream()
                .filter(concepto -> concepto.definition() != null && !concepto.definition().isBlank())
                .map(concepto -> concepto.name() + ": " + concepto.definition())
                .collect(Collectors.joining("\n\n"));
    }

    public boolean hayExistencias() {
        return stock > 0;
    }

    public String precioFormateado() {
        return String.format("$%,.2f %s", price, currency);
    }
}
