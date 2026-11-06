package mx.udem.library.desktop.model;

import com.fasterxml.jackson.databind.JsonNode;

/**
 * Una referencia a un catalogo: formato, categoria, autor o genero.
 *
 * Los servicios usan la clave "ref" para el identificador en estas
 * colecciones (y "id" en las imagenes, que es la irregularidad que mas
 * despista del contrato). Se respeta tal cual viene.
 */
public record Ref(int ref, String name) {

    public static Ref de(JsonNode nodo) {
        if (nodo == null || nodo.isNull()) {
            return null;
        }
        return new Ref(nodo.path("ref").asInt(0), nodo.path("name").asText(""));
    }

    @Override
    public String toString() {
        return name;
    }
}
