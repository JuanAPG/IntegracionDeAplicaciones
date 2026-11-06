package mx.udem.library.desktop.service;

import com.fasterxml.jackson.databind.JsonNode;
import mx.udem.library.desktop.model.Book;
import mx.udem.library.desktop.net.ApiClient;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * Microservicio de libros (5001).
 *
 * EL CATALOGO ES PUBLICO: estas lecturas van SIN token a proposito. No
 * es una omision; mandar credenciales donde no hacen falta solo amplia
 * la superficie por la que se pueden filtrar.
 *
 * LA TRAMPA DEL PARAMETRO `format`. En este servicio -- y solo en este --
 * `format` es tambien un filtro del catalogo (Fisico, Digital,
 * Audiolibro). La representacion se pide con `output`, que no tiene esa
 * ambiguedad, y asi `format` queda libre para filtrar de verdad. El
 * ApiClient ya lo sabe por el enum Service; aqui solo hay que recordar no
 * usar `format` para otra cosa.
 */
public final class BooksService {

    private final ApiClient api;

    public BooksService(ApiClient api) {
        this.api = api;
    }

    /** Catalogo completo, paginado. */
    public Resultado listar(int limit, int offset) {
        return buscar(Map.of(), limit, offset);
    }

    /**
     * Busqueda por titulo. El filtro `q` del servicio busca en titulo,
     * ISBN y autor a la vez, que es lo que espera quien escribe en una
     * caja de busqueda.
     */
    public Resultado buscarPorTexto(String texto, int limit, int offset) {
        if (texto == null || texto.isBlank()) {
            return listar(limit, offset);
        }
        return buscar(Map.of("q", texto.trim()), limit, offset);
    }

    public Resultado buscar(Map<String, String> filtros, int limit, int offset) {
        Map<String, String> consulta = new LinkedHashMap<>(filtros);
        consulta.put("limit", Integer.toString(limit));
        consulta.put("offset", Integer.toString(offset));

        JsonNode respuesta = api.get("/books", consulta, false);
        List<Book> libros = new ArrayList<>();
        JsonNode arreglo = respuesta.get("books");
        if (arreglo != null && arreglo.isArray()) {
            arreglo.forEach(nodo -> libros.add(Book.de(nodo)));
        }
        return new Resultado(List.copyOf(libros),
                respuesta.path("total").asInt(libros.size()),
                respuesta.path("limit").asInt(limit),
                respuesta.path("offset").asInt(offset));
    }

    /**
     * Ficha de un libro por su id.
     *
     * La respuesta viene ENVUELTA en la clave `book`, al contrario que el
     * listado, que trae la coleccion en `books`.
     */
    public Book porId(int id) {
        return Book.de(api.get("/books/" + id, false).path("book"));
    }

    public Book porIsbn(String isbn) {
        return Book.de(api.get("/books/isbn/" + isbn, false).path("book"));
    }

    /** Una pagina del catalogo con el total que hay detras. */
    public record Resultado(List<Book> libros, int total, int limit, int offset) {
        public boolean hayMas() {
            return offset + libros.size() < total;
        }
    }
}
