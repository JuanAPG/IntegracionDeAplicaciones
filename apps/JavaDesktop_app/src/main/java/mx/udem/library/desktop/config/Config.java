package mx.udem.library.desktop.config;

import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.URI;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.util.EnumMap;
import java.util.Map;
import java.util.Properties;

/**
 * Donde vive cada servicio y como se cambia sin recompilar.
 *
 * LA IP DE LA INSTANCIA ES EFIMERA: cambia cada vez que se reinicia la
 * maquina de GCP. Por eso existe {@link #applyHost(String)}: se escribe
 * la IP UNA vez y los siete destinos se reapuntan conservando su puerto.
 * Los dos clientes que ya existen en el monorepo (el de Tkinter y el de
 * Electron) tienen ese mismo atajo, y por la misma razon.
 *
 * DONDE SE GUARDA. En {@code ~/.library-desktop/config.properties}, FUERA
 * del arbol del repositorio. No es manía: el {@code config.json} del
 * cliente de Tkinter acabo commiteado con una cookie de sesion viva
 * dentro. Lo que no esta en el repositorio no se sube por accidente.
 *
 * QUE NO SE GUARDA NUNCA: la contrasena. Ni aqui ni en ningun otro sitio
 * de esta aplicacion. La sesion se guarda como token de acceso y de
 * refresco, que el servidor puede revocar; una contrasena, no.
 */
public final class Config {

    private static final String IP_POR_OMISION = "34.51.89.203";
    private static final Path DIRECTORIO = Path.of(System.getProperty("user.home"), ".library-desktop");
    private static final Path ARCHIVO = DIRECTORIO.resolve("config.properties");

    private final Map<Service, URI> bases = new EnumMap<>(Service.class);
    private int timeoutSegundos = 20;

    private Config() {
    }

    /**
     * Carga la configuracion: primero los valores de fabrica, encima el
     * archivo del usuario si existe, y encima la variable de entorno
     * {@code LIBRARY_VM_IP} si esta puesta.
     *
     * Un archivo corrupto NO impide arrancar: se registra y se sigue con
     * los valores de fabrica. Una aplicacion de escritorio que no abre
     * porque su configuracion tiene una coma de mas es inservible.
     */
    public static Config cargar() {
        Config config = new Config();
        config.bases.put(Service.TRACKING, hostDeRastreoPorOmision());
        config.aplicarHostInterno(IP_POR_OMISION);

        Properties props = new Properties();
        if (Files.isReadable(ARCHIVO)) {
            try (InputStream in = Files.newInputStream(ARCHIVO)) {
                props.load(in);
            } catch (IOException | IllegalArgumentException exc) {
                System.err.println("[config] no se pudo leer " + ARCHIVO
                        + " (" + exc.getMessage() + "); se usan los valores de fabrica");
            }
        }

        for (Service servicio : Service.values()) {
            String valor = props.getProperty("url." + servicio.id());
            if (valor != null && !valor.isBlank()) {
                try {
                    config.bases.put(servicio, new URI(valor.trim()));
                } catch (Exception exc) {
                    System.err.println("[config] url." + servicio.id() + " invalida: " + valor);
                }
            }
        }

        String timeout = props.getProperty("timeout.segundos");
        if (timeout != null) {
            try {
                config.timeoutSegundos = Math.max(1, Integer.parseInt(timeout.trim()));
            } catch (NumberFormatException ignored) {
                // se queda el valor por omision
            }
        }

        String ipEntorno = System.getenv("LIBRARY_VM_IP");
        if (ipEntorno != null && !ipEntorno.isBlank()) {
            config.aplicarHostInterno(ipEntorno.trim());
        }
        return config;
    }

    /**
     * Reapunta los siete destinos a una IP nueva conservando los puertos.
     * Es la operacion que mas se usa, porque la IP de GCP cambia sola.
     */
    public void applyHost(String host) {
        aplicarHostInterno(host);
    }

    /**
     * EL SERVIDOR DE RASTREO NO VIVE EN LA INSTANCIA. Es el unico de los
     * siete destinos que corre en el equipo del usuario, junto a la
     * aplicacion: no es uno de los seis microservicios del monorepo, es
     * el componente que esta aplicacion anade. Por eso reapuntar la IP
     * de GCP NO debe arrastrarlo -- si lo hiciera, el rastreo buscaria
     * un puerto 5900 en la VM que no existe.
     *
     * Para ponerlo en otra maquina se edita su URL una por una en
     * Ajustes, o la variable TRACKING_URL.
     */
    private void aplicarHostInterno(String host) {
        for (Service servicio : Service.values()) {
            if (servicio == Service.TRACKING) {
                continue;
            }
            bases.put(servicio, URI.create("http://" + host + ":" + servicio.defaultPort()));
        }
        bases.putIfAbsent(Service.TRACKING, hostDeRastreoPorOmision());
    }

    private static URI hostDeRastreoPorOmision() {
        String desdeEntorno = System.getenv("TRACKING_URL");
        if (desdeEntorno != null && !desdeEntorno.isBlank()) {
            try {
                return new URI(desdeEntorno.trim());
            } catch (Exception exc) {
                System.err.println("[config] TRACKING_URL invalida: " + desdeEntorno);
            }
        }
        return URI.create("http://localhost:" + Service.TRACKING.defaultPort());
    }

    public URI base(Service servicio) {
        return bases.get(servicio);
    }

    public void setBase(Service servicio, URI uri) {
        bases.put(servicio, uri);
    }

    public int timeoutSegundos() {
        return timeoutSegundos;
    }

    public void setTimeoutSegundos(int segundos) {
        this.timeoutSegundos = Math.max(1, segundos);
    }

    /**
     * URL del WebSocket de rastreo, derivada del destino TRACKING.
     * {@code http://host:5900} se convierte en {@code ws://host:5900/ws}.
     */
    public URI websocketRastreo() {
        URI base = bases.get(Service.TRACKING);
        String esquema = "https".equalsIgnoreCase(base.getScheme()) ? "wss" : "ws";
        return URI.create(esquema + "://" + base.getAuthority() + "/ws");
    }

    /**
     * Guarda la configuracion de forma ATOMICA: se escribe en un archivo
     * temporal y se renombra encima. Si la aplicacion muere a mitad de la
     * escritura, el archivo anterior sigue intacto en lugar de quedar
     * truncado. Es la misma precaucion que toma el cliente de Tkinter.
     */
    public void guardar() throws IOException {
        Files.createDirectories(DIRECTORIO);
        Properties props = new Properties();
        for (Service servicio : Service.values()) {
            props.setProperty("url." + servicio.id(), bases.get(servicio).toString());
        }
        props.setProperty("timeout.segundos", Integer.toString(timeoutSegundos));

        Path temporal = Files.createTempFile(DIRECTORIO, "config", ".tmp");
        try (OutputStream out = Files.newOutputStream(temporal)) {
            props.store(out, "Libreria en Linea - cliente de escritorio. NO contiene contrasenas.");
        }
        Files.move(temporal, ARCHIVO, StandardCopyOption.REPLACE_EXISTING,
                StandardCopyOption.ATOMIC_MOVE);
    }

    public static Path rutaArchivo() {
        return ARCHIVO;
    }
}
