package mx.udem.library.desktop.service;

import com.fasterxml.jackson.databind.JsonNode;
import mx.udem.library.desktop.model.Author;
import mx.udem.library.desktop.net.ApiClient;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;

/**
 * Microservicio de autores (5003).
 *
 * Lecturas publicas y cacheadas. CUIDADO con una sutileza: estas rutas
 * usan `@optional_token`, lo que significa que si se manda una cabecera
 * Authorization se verifica de verdad y un token caducado produce 401
 * AUNQUE la ruta sea publica. Por eso aqui se pide siempre sin token: es
 * mas robusto que mandar uno que podria estar vencido.
 */
public final class AuthorsService {

    private final ApiClient api;

    public AuthorsService(ApiClient api) {
        this.api = api;
    }

    public List<Author> listar(String busqueda, int limit) {
        Map<String, String> consulta = busqueda == null || busqueda.isBlank()
                ? Map.of("limit", Integer.toString(limit))
                : Map.of("q", busqueda.trim(), "limit", Integer.toString(limit));

        JsonNode respuesta = api.get("/authors", consulta, false);
        List<Author> autores = new ArrayList<>();
        JsonNode arreglo = respuesta.get("authors");
        if (arreglo != null && arreglo.isArray()) {
            arreglo.forEach(nodo -> autores.add(Author.de(nodo)));
        }
        return List.copyOf(autores);
    }

    /** Ficha del autor con el resumen de sus obras. Sin envoltorio. */
    public Author porId(int id) {
        return Author.de(api.get("/authors/" + id, false));
    }
}
