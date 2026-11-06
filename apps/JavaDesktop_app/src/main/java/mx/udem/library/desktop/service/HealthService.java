package mx.udem.library.desktop.service;

import com.fasterxml.jackson.databind.JsonNode;
import mx.udem.library.desktop.config.Config;
import mx.udem.library.desktop.config.Service;
import mx.udem.library.desktop.net.ApiClient;
import mx.udem.library.desktop.net.ApiException;

/**
 * El semaforo de cada servicio.
 *
 * TRES ESTADOS, NO DOS, y el amarillo es la razon de ser del semaforo:
 * con Redis caido, el catalogo y los autores se siguen leyendo (la cache
 * es opcional en las lecturas) pero NINGUNA escritura funciona, porque
 * no se puede comprobar si un token fue revocado y el proyecto prefiere
 * rechazar antes que honrar una credencial posiblemente retirada.
 * Pintar eso en verde seria mentir y en rojo exagerar.
 *
 * TAMBIEN COMPRUEBA LA IDENTIDAD DEL PUERTO. Cada servicio declara su
 * nombre en `/health`, y el mapa de puertos del enunciado de la practica
 * esta invertido respecto a lo desplegado. Si el 5002 contesta "payments"
 * en lugar de "users", esta aplicacion lo dice en vez de enviar los datos
 * al servicio equivocado.
 */
public final class HealthService {

    public enum Estado { ARRIBA, DEGRADADO, CAIDO }

    public record Resultado(Service servicio, Estado estado, String detalle) { }

    private final Config config;

    public HealthService(Config config) {
        this.config = config;
    }

    public Resultado comprobar(Service servicio, ApiClient api) {
        try {
            JsonNode salud = api.get("/health", false);
            String estadoServicio = salud.path("status").asText("");
            String identidad = salud.path("service").asText("");

            if (!identidad.isBlank() && !identidad.equals(servicio.healthName())) {
                return new Resultado(servicio, Estado.DEGRADADO,
                        "El puerto " + config.base(servicio).getPort() + " dice ser '"
                        + identidad + "' y no '" + servicio.healthName()
                        + "'. Revisa el mapa de puertos en Ajustes.");
            }
            if ("degraded".equals(estadoServicio)) {
                return new Resultado(servicio, Estado.DEGRADADO,
                        "Funciona para leer, pero las escrituras fallaran (Redis caido).");
            }
            if ("ok".equals(estadoServicio)) {
                return new Resultado(servicio, Estado.ARRIBA, "Disponible.");
            }
            return new Resultado(servicio, Estado.DEGRADADO, "Estado: " + estadoServicio);

        } catch (ApiException exc) {
            // Un 503 CON cuerpo es un servicio vivo pero degradado; un
            // 503 sin cuerpo, o un fallo de red, es un servicio caido.
            if (exc.status() == 503 && !exc.getMessage().isBlank()) {
                return new Resultado(servicio, Estado.DEGRADADO, exc.getMessage());
            }
            return new Resultado(servicio, Estado.CAIDO, exc.mensajeParaUsuario());
        }
    }
}
