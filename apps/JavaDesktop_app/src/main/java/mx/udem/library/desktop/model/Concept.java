package mx.udem.library.desktop.model;

import com.fasterxml.jackson.databind.JsonNode;

/**
 * Un concepto asociado a un libro, con su definicion.
 *
 * IMPORTA MAS DE LO QUE PARECE: el catalogo NO tiene campo de sinopsis ni
 * de descripcion -- se comprobo contra `data/schema.sql` y contra el
 * serializador del servicio, y la tabla `books` solo guarda isbn, titulo,
 * ano, precio, existencias, formato y categoria. La definicion de los
 * conceptos es el unico texto descriptivo real del catalogo, de modo que
 * es lo que esta aplicacion ensena como descripcion del libro, diciendo
 * de donde sale en vez de fingir que el servicio tiene una sinopsis.
 */
public record Concept(int ref, String name, String definition) {

    public static Concept de(JsonNode nodo) {
        return new Concept(
                nodo.path("ref").asInt(0),
                nodo.path("name").asText(""),
                nodo.path("definition").asText(""));
    }
}
