package mx.udem.library.desktop.ui;

import javafx.scene.image.Image;
import javafx.scene.image.ImageView;

import java.io.IOException;
import java.io.InputStream;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.time.Duration;
import java.util.HexFormat;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

/**
 * Las portadas de los libros.
 *
 * TRES COSAS QUE SE APRENDIERON POR LAS MALAS EN LOS OTROS CLIENTES DEL
 * PROYECTO, y que aqui estan desde el principio:
 *
 * 1. CACHE EN DISCO con el nombre derivado de la URL. Un catalogo de 30
 *    libros son 30 descargas a openlibrary.org cada vez que se abre la
 *    aplicacion; con cache, solo la primera vez.
 *
 * 2. TOPE DE TAMANO. Una portada son decenas de kilobytes; si una URL
 *    devuelve 40 MB, algo va mal y no hay que meterlo en memoria.
 *
 * 3. UN 302 CON CERO BYTES NO DISPARA NINGUN ERROR. El servidor de
 *    imagenes responde "correctamente" con un cuerpo vacio, la descarga
 *    termina sin excepcion y lo que se obtiene es una imagen que no
 *    decodifica. Por eso no basta con capturar fallos: hay que
 *    comprobar que la imagen resultante tiene ancho de verdad.
 */
public final class Imagenes {

    private static final Path CACHE = Path.of(System.getProperty("java.io.tmpdir"), "libreria-portadas");
    private static final long MAX_BYTES = 3L * 1024 * 1024;
    private static final Map<String, Image> EN_MEMORIA = new ConcurrentHashMap<>();

    private static final HttpClient HTTP = HttpClient.newBuilder()
            .connectTimeout(Duration.ofSeconds(8))
            .followRedirects(HttpClient.Redirect.NORMAL)
            .build();

    private static Image placeholder;

    private Imagenes() {
    }

    /**
     * Pone la portada en el ImageView, descargandola en segundo plano.
     * Mientras llega -- o si no llega -- se ve la imagen generica.
     */
    public static void cargarEn(ImageView destino, String url, double ancho, double alto) {
        destino.setFitWidth(ancho);
        destino.setFitHeight(alto);
        destino.setPreserveRatio(true);
        destino.setSmooth(true);
        destino.setImage(generica());

        if (url == null || url.isBlank() || !(url.startsWith("http://") || url.startsWith("https://"))) {
            return;
        }
        Image enMemoria = EN_MEMORIA.get(url);
        if (enMemoria != null) {
            destino.setImage(enMemoria);
            return;
        }
        Tareas.enSegundoPlano(
                () -> descargar(url),
                imagen -> {
                    if (imagen != null) {
                        EN_MEMORIA.put(url, imagen);
                        destino.setImage(imagen);
                    }
                },
                error -> { /* se queda la generica: una portada ausente no es un fallo */ });
    }

    private static Image descargar(String url) {
        try {
            Path archivo = CACHE.resolve(huella(url) + ".img");
            if (Files.isReadable(archivo) && Files.size(archivo) > 0) {
                try (InputStream in = Files.newInputStream(archivo)) {
                    Image imagen = new Image(in);
                    if (!imagen.isError() && imagen.getWidth() > 0) {
                        return imagen;
                    }
                }
            }

            HttpRequest peticion = HttpRequest.newBuilder(URI.create(url))
                    .timeout(Duration.ofSeconds(12))
                    // Algunos servidores de imagenes rechazan a los
                    // clientes sin User-Agent reconocible.
                    .header("User-Agent", "LibreriaEnLinea-Desktop/1.0")
                    .GET()
                    .build();
            HttpResponse<byte[]> respuesta = HTTP.send(peticion, HttpResponse.BodyHandlers.ofByteArray());
            byte[] bytes = respuesta.body();

            if (respuesta.statusCode() != 200 || bytes == null || bytes.length == 0
                    || bytes.length > MAX_BYTES) {
                return null;
            }
            Image imagen = new Image(new java.io.ByteArrayInputStream(bytes));
            // La comprobacion del 302 vacio: la descarga "funciono" pero
            // lo que llego no es una imagen.
            if (imagen.isError() || imagen.getWidth() <= 0) {
                return null;
            }
            Files.createDirectories(CACHE);
            Files.write(archivo, bytes);
            return imagen;
        } catch (IOException | InterruptedException | RuntimeException exc) {
            return null;
        }
    }

    private static String huella(String url) {
        try {
            MessageDigest sha = MessageDigest.getInstance("SHA-256");
            return HexFormat.of().formatHex(sha.digest(url.getBytes())).substring(0, 32);
        } catch (Exception exc) {
            return Integer.toHexString(url.hashCode());
        }
    }

    /** "Portada no disponible", generada una vez y reutilizada. */
    public static synchronized Image generica() {
        if (placeholder == null) {
            // Se dibuja con un SVG embebido en un data: URI en lugar de
            // llevar un PNG en los recursos: una dependencia binaria
            // menos y se ve nitido a cualquier tamano.
            String svg = """
                    <svg xmlns="http://www.w3.org/2000/svg" width="200" height="300">
                      <rect width="200" height="300" rx="10" fill="#1e293b"/>
                      <rect x="12" y="12" width="176" height="276" rx="6"
                            fill="none" stroke="#334155" stroke-width="2"/>
                      <text x="100" y="140" text-anchor="middle" font-size="46" fill="#475569">?</text>
                      <text x="100" y="186" text-anchor="middle" font-size="13"
                            fill="#64748b" font-family="sans-serif">Portada</text>
                      <text x="100" y="206" text-anchor="middle" font-size="13"
                            fill="#64748b" font-family="sans-serif">no disponible</text>
                    </svg>""";
            String datos = "data:image/svg+xml;base64,"
                    + java.util.Base64.getEncoder().encodeToString(svg.getBytes());
            placeholder = new Image(datos);
        }
        return placeholder;
    }
}
