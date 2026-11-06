package mx.udem.library.desktop.net;

import com.fasterxml.jackson.databind.JsonNode;
import mx.udem.library.desktop.auth.TokenStore;
import mx.udem.library.desktop.config.Config;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.WebSocket;
import java.time.Duration;
import java.util.concurrent.CompletionStage;
import java.util.function.Consumer;

/**
 * El cliente WebSocket del rastreo. VIVE EN JAVA, no en la pagina.
 *
 * POR QUE AQUI Y NO EN EL JAVASCRIPT DEL MAPA. Por dos razones, y la
 * segunda es la de peso:
 *
 *  1. El enunciado pide que la conexion WebSocket este integrada en la
 *     aplicacion Java, no que la pagina embebida se conecte por su
 *     cuenta.
 *  2. El WebSocket de un navegador NO permite poner cabeceras en el
 *     handshake. Desde JavaScript, el token tendria que viajar en la
 *     URL -- donde acaba en registros del servidor y en el historial --
 *     o no viajar. Desde Java se manda como
 *     {@code Authorization: Bearer}, igual que en el resto de la
 *     aplicacion.
 *
 * El flujo queda: este cliente recibe el JSON, y la pantalla del mapa se
 * lo entrega a la pagina llamando a {@code window.LIB}.
 *
 * DETALLE QUE ROMPE A MUCHOS CLIENTES: {@link WebSocket.Listener#onText}
 * puede entregar un mensaje PARTIDO en varios trozos; el parametro
 * {@code last} dice si este es el ultimo. Un cliente que intente
 * analizar cada trozo como JSON funciona en pruebas y falla con
 * mensajes grandes -- y el `snapshot` de una ruta de 236 puntos es
 * grande. Por eso aqui se acumulan los trozos hasta que llega el
 * ultimo.
 */
public final class TrackingSocket implements AutoCloseable {

    /** Lo que le pasa a la conexion, para que la interfaz lo cuente. */
    public enum Evento { CONECTANDO, CONECTADO, CERRADO, RECHAZADO, ERROR }

    private final Config config;
    private final TokenStore tokens;
    private final HttpClient http;

    private final Consumer<JsonNode> alRecibir;
    private final java.util.function.BiConsumer<Evento, String> alCambiarEstado;

    private volatile WebSocket socket;
    private final StringBuilder acumulador = new StringBuilder();

    public TrackingSocket(Config config, TokenStore tokens,
                          Consumer<JsonNode> alRecibir,
                          java.util.function.BiConsumer<Evento, String> alCambiarEstado) {
        this.config = config;
        this.tokens = tokens;
        this.alRecibir = alRecibir;
        this.alCambiarEstado = alCambiarEstado;
        this.http = HttpClient.newBuilder()
                .connectTimeout(Duration.ofSeconds(10))
                .build();
    }

    /** Abre el seguimiento de un codigo. Cierra el anterior si lo habia. */
    public void conectar(String codigoRastreo) {
        cerrar();
        acumulador.setLength(0);

        URI uri = URI.create(config.websocketRastreo() + "?code="
                + java.net.URLEncoder.encode(codigoRastreo, java.nio.charset.StandardCharsets.UTF_8));
        alCambiarEstado.accept(Evento.CONECTANDO, "Conectando con el servidor de rastreo...");

        WebSocket.Builder constructor = http.newWebSocketBuilder()
                .connectTimeout(Duration.ofSeconds(10));

        String token = tokens.accessToken();
        if (token != null && !token.isBlank()) {
            // La cabecera, no la URL. Ver el comentario de la clase.
            constructor.header("Authorization", "Bearer " + token);
        }

        constructor.buildAsync(uri, new Oyente())
                .whenComplete((ws, error) -> {
                    if (error != null) {
                        alCambiarEstado.accept(Evento.ERROR,
                                "No se pudo abrir el rastreo: " + causaLegible(error));
                    } else {
                        socket = ws;
                        alCambiarEstado.accept(Evento.CONECTADO, "Rastreo en vivo.");
                    }
                });
    }

    @Override
    public void close() {
        cerrar();
    }

    public void cerrar() {
        WebSocket actual = socket;
        socket = null;
        if (actual != null) {
            try {
                actual.sendClose(WebSocket.NORMAL_CLOSURE, "cerrado por el usuario");
            } catch (Exception ignorado) {
                actual.abort();
            }
        }
    }

    public boolean estaConectado() {
        WebSocket actual = socket;
        return actual != null && !actual.isInputClosed();
    }

    private static String causaLegible(Throwable error) {
        Throwable raiz = error;
        while (raiz.getCause() != null) {
            raiz = raiz.getCause();
        }
        String mensaje = raiz.getMessage();
        return mensaje == null || mensaje.isBlank() ? raiz.getClass().getSimpleName() : mensaje;
    }

    /** El oyente de la conexion. Sus metodos corren en hilos del cliente HTTP. */
    private final class Oyente implements WebSocket.Listener {

        @Override
        public void onOpen(WebSocket ws) {
            ws.request(1);
        }

        @Override
        public CompletionStage<?> onText(WebSocket ws, CharSequence datos, boolean ultimo) {
            acumulador.append(datos);
            if (ultimo) {
                String mensaje = acumulador.toString();
                acumulador.setLength(0);
                try {
                    JsonNode nodo = ApiClient.mapper().readTree(mensaje);
                    alRecibir.accept(nodo);
                } catch (Exception exc) {
                    alCambiarEstado.accept(Evento.ERROR,
                            "Mensaje de rastreo ilegible: " + exc.getMessage());
                }
            }
            ws.request(1);
            return null;
        }

        @Override
        public CompletionStage<?> onClose(WebSocket ws, int codigo, String motivo) {
            socket = null;
            // 1008 es "violacion de politica": el servidor entendio la
            // peticion y la rechazo. Distinguirlo de un corte de red
            // importa, porque la accion del usuario es distinta: ahi no
            // sirve reintentar.
            if (codigo == 1008) {
                alCambiarEstado.accept(Evento.RECHAZADO,
                        "El servidor no autorizo este rastreo" + (motivo.isBlank() ? "." : ": " + motivo));
            } else {
                alCambiarEstado.accept(Evento.CERRADO,
                        "Rastreo cerrado" + (motivo.isBlank() ? "." : ": " + motivo));
            }
            return null;
        }

        @Override
        public void onError(WebSocket ws, Throwable error) {
            socket = null;
            alCambiarEstado.accept(Evento.ERROR, "Fallo del rastreo: " + causaLegible(error));
        }
    }
}
