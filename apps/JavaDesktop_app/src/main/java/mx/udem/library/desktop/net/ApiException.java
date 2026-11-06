package mx.udem.library.desktop.net;

import java.util.List;

/**
 * Un fallo al hablar con un microservicio, ya traducido a algo que se le
 * puede ensenar a una persona.
 *
 * LOS SEIS SERVICIOS DEVUELVEN EL MISMO SOBRE DE ERROR:
 * <pre>
 * {"error": {"status": 403, "code": "forbidden",
 *            "message": "...", "details": ["Permiso requerido: ..."]}}
 * </pre>
 * Esta clase lo conserva entero -- codigo, mensaje y detalles -- porque
 * los detalles son justo lo accionable: en un 409 por falta de existencias
 * dicen que libro, cuantos hay y cuantos se piden.
 *
 * UN FALLO DE RED TAMBIEN ES UN ApiException, con {@code status == 0}. La
 * interfaz necesita algo que mostrar tanto si el servidor contesto 500
 * como si el cable esta desconectado; dejar escapar una IOException cruda
 * obliga a cada pantalla a lidiar con dos mundos distintos.
 */
public class ApiException extends RuntimeException {

    private final int status;
    private final String code;
    private final List<String> details;

    public ApiException(int status, String code, String mensaje, List<String> details) {
        super(mensaje);
        this.status = status;
        this.code = code == null ? "" : code;
        this.details = details == null ? List.of() : List.copyOf(details);
    }

    public static ApiException deRed(String mensaje, Throwable causa) {
        ApiException exc = new ApiException(0, "network_error", mensaje, List.of());
        if (causa != null) {
            exc.initCause(causa);
        }
        return exc;
    }

    public int status() {
        return status;
    }

    public String code() {
        return code;
    }

    public List<String> details() {
        return details;
    }

    public boolean esDeRed() {
        return status == 0;
    }

    /** 401: el token falta, caduco o fue revocado. */
    public boolean esNoAutorizado() {
        return status == 401;
    }

    /** 403: el token es bueno pero el rol no alcanza. */
    public boolean esProhibido() {
        return status == 403;
    }

    /**
     * Mensaje para la persona que usa la aplicacion.
     *
     * Dice QUE HACER, no que fallo. Los textos de 401, 403 y 503 son los
     * mismos que ya usan el cliente de Tkinter y el de Electron, a
     * proposito: los tres clientes del proyecto deben decir lo mismo ante
     * el mismo problema, o el usuario cree que son fallos distintos.
     */
    public String mensajeParaUsuario() {
        String base = switch (status) {
            case 0 -> "No se pudo contactar al servicio. Revisa tu conexion y la IP "
                    + "de la instancia en Ajustes.";
            case 401 -> "Tu sesion caduco o se cerro desde otro sitio. Vuelve a iniciar sesion.";
            case 403 -> "Tu cuenta no tiene permiso para esto.";
            case 404 -> getMessage() == null || getMessage().isBlank()
                    ? "No se encontro lo que buscabas." : getMessage();
            case 409 -> getMessage();
            case 503 -> "El servicio no esta disponible ahora mismo "
                    + "(base de datos o Redis caidos).";
            default -> getMessage() == null || getMessage().isBlank()
                    ? "Error " + status : getMessage();
        };
        if (details.isEmpty()) {
            return base;
        }
        // Hasta tres detalles: mas que eso es un muro de texto en un dialogo.
        return base + "\n" + String.join("\n", details.subList(0, Math.min(3, details.size())));
    }

    @Override
    public String toString() {
        return "ApiException[status=" + status + ", code=" + code + ", mensaje=" + getMessage() + "]";
    }
}
