package mx.udem.library.desktop.config;

/**
 * Los siete destinos que consume esta aplicacion.
 *
 * EL MAPA DE PUERTOS SE COMPROBO, NO SE COPIO DEL ENUNCIADO. El enunciado
 * de la practica lista "pagos 5002, pedidos 5003, users 5004, autores
 * 5005", pero la instancia responde al reves y no es una suposicion: el
 * {@code GET /health} de cada servicio declara su propio nombre
 * ({@code {"service":"users"}} en el 5002, {@code "orders"} en el 5004...).
 * Se usa el mapa REAL; {@link mx.udem.library.desktop.service.HealthService}
 * lo vuelve a verificar al arrancar y avisa si algun puerto cambia de
 * identidad.
 *
 * EL PARAMETRO DE FORMATO NO ES EL MISMO EN TODOS. En el servicio de
 * libros, {@code format} es ADEMAS un filtro del catalogo (Fisico,
 * Digital, Audiolibro...), de modo que alli la representacion se pide con
 * {@code ?output=json}. En los otros cinco se pide con {@code ?format=json}.
 * Por eso cada servicio lleva su parametro aqui y no en cada llamada: es
 * el tipo de detalle que se olvida en una de veinte peticiones.
 */
public enum Service {

    LOGIN("login", 5000, "format"),
    BOOKS("books", 5001, "output"),
    USERS("users", 5002, "format"),
    AUTHORS("authors", 5003, "format"),
    PEDIDOS("pedidos", 5004, "format"),
    PAGOS("pagos", 5005, "format"),

    /**
     * Servidor de rastreo (Flask + Flask-Sock). No es uno de los seis
     * microservicios del monorepo: es el componente que esta aplicacion
     * anade para el seguimiento en tiempo real. Corre aparte y solo habla
     * WebSocket y HTTP estatico (la pagina del mapa).
     */
    TRACKING("tracking", 5900, "format");

    private final String id;
    private final int defaultPort;
    private final String formatParam;

    Service(String id, int defaultPort, String formatParam) {
        this.id = id;
        this.defaultPort = defaultPort;
        this.formatParam = formatParam;
    }

    /** Nombre corto, el que se usa como clave en config.properties. */
    public String id() {
        return id;
    }

    public int defaultPort() {
        return defaultPort;
    }

    /** {@code "output"} para books, {@code "format"} para el resto. */
    public String formatParam() {
        return formatParam;
    }

    /**
     * Lo que el servicio declara en su {@code /health}. Sirve para
     * comprobar que el puerto al que apuntamos es el que creemos.
     * El servicio de pedidos se identifica como "orders" y el de pagos
     * como "payments": son los nombres de la version desplegada.
     */
    public String healthName() {
        return switch (this) {
            case PEDIDOS -> "orders";
            case PAGOS -> "payments";
            default -> id;
        };
    }
}
