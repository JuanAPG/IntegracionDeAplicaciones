package mx.udem.library.desktop.net;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import mx.udem.library.desktop.auth.TokenStore;
import mx.udem.library.desktop.config.Config;
import mx.udem.library.desktop.config.Service;

import java.io.IOException;
import java.net.URI;
import java.net.URLEncoder;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.function.BooleanSupplier;

/**
 * El unico sitio desde el que esta aplicacion habla con los
 * microservicios.
 *
 * NO HAY NI UNA CONEXION A POSTGRESQL EN TODO EL PROYECTO, y es un
 * requisito de la arquitectura, no una casualidad: las operaciones de
 * negocio viven en los servicios, que son los que conocen las reglas
 * (congelar el precio, reservar existencias, decidir cuando un pedido
 * pasa a pagado). Un cliente con acceso directo a la base se saltaria
 * todas esas reglas sin enterarse.
 *
 * USA EL CLIENTE HTTP DEL JDK. Desde Java 11 el propio {@code java.net.http}
 * basta: HTTP/1.1 y 2, tiempos limite, y cuerpos como cadena. Una
 * dependencia menos que auditar.
 *
 * LAS TRES COSAS QUE HACE Y QUE NO SE VEN:
 *
 * 1. Pone el parametro de representacion de CADA servicio. En books es
 *    {@code ?output=json} porque alli {@code format} es ademas un filtro
 *    del catalogo; en los otros cinco es {@code ?format=json}. Ademas
 *    manda {@code Accept: application/json}, que los servicios respetan
 *    como segunda prioridad. Los dos, no uno: la version desplegada en la
 *    instancia ignora la cabecera.
 *
 * 2. Renueva el token ANTES de que caduque, no despues de comerse un 401.
 *    El servidor publica en {@code renewBefore} cuantos segundos de
 *    margen quiere; se respeta ese numero en lugar de inventarse uno.
 *
 * 3. Ante un 401, renueva y reintenta EXACTAMENTE UNA VEZ. Ni cero (el
 *    usuario veria un error espurio al cruzar la frontera de los 30
 *    minutos) ni dos (un token revocado de verdad produciria un bucle de
 *    renovaciones contra el servidor).
 */
public final class ApiClient {

    private static final ObjectMapper MAPPER = new ObjectMapper();

    private final Config config;
    private final Service servicio;
    private final TokenStore tokens;
    private final HttpClient http;

    /**
     * Como renovar la sesion. Lo inyecta la aplicacion despues de crear
     * el cliente de login, porque el cliente de login es a su vez un
     * ApiClient: sin este gancho habria una dependencia circular.
     * Devuelve true si consiguio un token nuevo.
     */
    private BooleanSupplier renovador = () -> false;

    public ApiClient(Config config, Service servicio, TokenStore tokens) {
        this.config = config;
        this.servicio = servicio;
        this.tokens = tokens;
        this.http = HttpClient.newBuilder()
                .connectTimeout(Duration.ofSeconds(Math.min(10, config.timeoutSegundos())))
                .followRedirects(HttpClient.Redirect.NORMAL)
                .build();
    }

    public void setRenovador(BooleanSupplier renovador) {
        this.renovador = renovador == null ? () -> false : renovador;
    }

    public Service servicio() {
        return servicio;
    }

    // -----------------------------------------------------------------
    // Verbos
    // -----------------------------------------------------------------

    public JsonNode get(String ruta, Map<String, String> consulta, boolean conToken) {
        return ejecutar("GET", ruta, consulta, null, conToken);
    }

    public JsonNode get(String ruta, boolean conToken) {
        return get(ruta, Map.of(), conToken);
    }

    public JsonNode post(String ruta, Object cuerpo, boolean conToken) {
        return ejecutar("POST", ruta, Map.of(), cuerpo, conToken);
    }

    public JsonNode put(String ruta, Object cuerpo, boolean conToken) {
        return ejecutar("PUT", ruta, Map.of(), cuerpo, conToken);
    }

    public JsonNode patch(String ruta, Object cuerpo, boolean conToken) {
        return ejecutar("PATCH", ruta, Map.of(), cuerpo, conToken);
    }

    public JsonNode delete(String ruta, Object cuerpo, boolean conToken) {
        return ejecutar("DELETE", ruta, Map.of(), cuerpo, conToken);
    }

    // -----------------------------------------------------------------
    // El motor
    // -----------------------------------------------------------------

    private JsonNode ejecutar(String metodo, String ruta, Map<String, String> consulta,
                              Object cuerpo, boolean conToken) {
        if (conToken && tokens.haySesion() && tokens.convieneRenovar()) {
            // Renovacion proactiva: barata, y evita que una operacion de
            // negocio falle a mitad por un token que caduco entre el
            // clic y la peticion.
            renovador.getAsBoolean();
        }

        HttpResponse<String> respuesta = enviar(metodo, ruta, consulta, cuerpo, conToken);

        if (respuesta.statusCode() == 401 && conToken && tokens.haySesion()) {
            if (renovador.getAsBoolean()) {
                respuesta = enviar(metodo, ruta, consulta, cuerpo, true);
            }
        }
        return interpretar(respuesta);
    }

    private HttpResponse<String> enviar(String metodo, String ruta, Map<String, String> consulta,
                                        Object cuerpo, boolean conToken) {
        URI uri = construirUri(ruta, consulta);
        HttpRequest.Builder peticion = HttpRequest.newBuilder(uri)
                .timeout(Duration.ofSeconds(config.timeoutSegundos()))
                .header("Accept", "application/json");

        if (conToken) {
            String token = tokens.accessToken();
            if (token != null && !token.isBlank()) {
                // El formato es literalmente este. El servicio no acepta
                // el token por query string, y hace bien: las URL acaban
                // en registros y en el historial del navegador.
                peticion.header("Authorization", "Bearer " + token);
            }
        }

        HttpRequest.BodyPublisher publicador = HttpRequest.BodyPublishers.noBody();
        if (cuerpo != null) {
            try {
                String json = MAPPER.writeValueAsString(cuerpo);
                publicador = HttpRequest.BodyPublishers.ofString(json, StandardCharsets.UTF_8);
                peticion.header("Content-Type", "application/json; charset=utf-8");
            } catch (Exception exc) {
                throw new ApiException(0, "client_error",
                        "No se pudo serializar el cuerpo de la peticion.", List.of());
            }
        }
        peticion.method(metodo, publicador);

        try {
            return http.send(peticion.build(), HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));
        } catch (IOException exc) {
            throw ApiException.deRed("No se pudo contactar a " + servicio.id()
                    + " en " + uri.getHost() + ":" + uri.getPort() + ".", exc);
        } catch (InterruptedException exc) {
            Thread.currentThread().interrupt();
            throw ApiException.deRed("La peticion a " + servicio.id() + " fue interrumpida.", exc);
        }
    }

    private URI construirUri(String ruta, Map<String, String> consulta) {
        Map<String, String> parametros = new LinkedHashMap<>(consulta);
        // El parametro de representacion va SIEMPRE y lo pone el cliente,
        // no cada llamada: olvidarlo en una sola peticion devuelve XML y
        // revienta el parseo con un error que no apunta a la causa.
        parametros.putIfAbsent(servicio.formatParam(), "json");

        StringBuilder url = new StringBuilder(config.base(servicio).toString());
        url.append(ruta.startsWith("/") ? ruta : "/" + ruta);

        boolean primero = true;
        for (Map.Entry<String, String> par : parametros.entrySet()) {
            if (par.getValue() == null || par.getValue().isBlank()) {
                continue;
            }
            url.append(primero ? '?' : '&');
            primero = false;
            url.append(URLEncoder.encode(par.getKey(), StandardCharsets.UTF_8))
               .append('=')
               .append(URLEncoder.encode(par.getValue(), StandardCharsets.UTF_8));
        }
        return URI.create(url.toString());
    }

    /**
     * Convierte la respuesta en un arbol JSON o en una ApiException con
     * el sobre de error ya desempaquetado.
     */
    private JsonNode interpretar(HttpResponse<String> respuesta) {
        int estado = respuesta.statusCode();
        String texto = respuesta.body() == null ? "" : respuesta.body();

        if (estado >= 200 && estado < 300) {
            if (texto.isBlank()) {
                return MAPPER.createObjectNode();
            }
            try {
                return MAPPER.readTree(texto);
            } catch (Exception exc) {
                // Un 200 que no es JSON suele significar que falto el
                // parametro de representacion y llego XML.
                throw new ApiException(estado, "bad_payload",
                        "El servicio " + servicio.id() + " respondio algo que no es JSON. "
                        + "Primeros caracteres: " + recorte(texto), List.of());
            }
        }
        throw construirError(estado, texto);
    }

    private ApiException construirError(int estado, String texto) {
        String codigo = "http_error";
        String mensaje = "Error " + estado + " en " + servicio.id() + ".";
        List<String> detalles = new ArrayList<>();

        try {
            JsonNode raiz = MAPPER.readTree(texto);
            JsonNode error = raiz.get("error");
            if (error != null && error.isObject()) {
                codigo = error.path("code").asText(codigo);
                mensaje = error.path("message").asText(mensaje);
                JsonNode lista = error.get("details");
                if (lista != null && lista.isArray()) {
                    lista.forEach(detalle -> detalles.add(detalle.asText()));
                }
            }
        } catch (Exception ignorado) {
            // El cuerpo no es JSON. Con un 503 sin cuerpo pasa, y
            // distinguirlo importa: 503 CON cuerpo es un servicio vivo
            // pero degradado; 503 sin cuerpo es un servicio caido.
            if (!texto.isBlank()) {
                mensaje = recorte(texto);
            }
        }
        return new ApiException(estado, codigo, mensaje, detalles);
    }

    private static String recorte(String texto) {
        String limpio = texto.strip().replaceAll("\\s+", " ");
        return limpio.length() <= 160 ? limpio : limpio.substring(0, 160) + "...";
    }

    public static ObjectMapper mapper() {
        return MAPPER;
    }
}
