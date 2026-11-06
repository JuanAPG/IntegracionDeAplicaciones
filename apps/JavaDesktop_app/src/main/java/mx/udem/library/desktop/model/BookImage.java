package mx.udem.library.desktop.model;

import com.fasterxml.jackson.databind.JsonNode;

/**
 * Una imagen de un libro.
 *
 * `url` es la cadena LITERAL que guarda la base: el servicio no la
 * transforma ni la completa. En los datos sembrados son URL absolutas de
 * openlibrary.org, pero el esquema admite cualquier cosa, incluida una
 * ruta relativa. Por eso {@link #esDescargable()} comprueba el esquema
 * antes de que nadie intente bajarla.
 */
public record BookImage(int id, String url, boolean isCover) {

    public static BookImage de(JsonNode nodo) {
        return new BookImage(
                nodo.path("id").asInt(0),
                nodo.path("url").asText(""),
                nodo.path("isCover").asBoolean(false));
    }

    public boolean esDescargable() {
        return url != null && (url.startsWith("http://") || url.startsWith("https://"));
    }
}
