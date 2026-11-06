package mx.udem.library.desktop.ui;

import com.fasterxml.jackson.databind.JsonNode;
import javafx.geometry.Insets;
import javafx.geometry.Pos;
import javafx.scene.control.Button;
import javafx.scene.control.Label;
import javafx.scene.control.TextField;
import javafx.scene.layout.BorderPane;
import javafx.scene.layout.HBox;
import javafx.scene.layout.Priority;
import javafx.scene.layout.Region;
import javafx.scene.web.WebEngine;
import javafx.scene.web.WebView;
import mx.udem.library.desktop.Contexto;
import mx.udem.library.desktop.net.TrackingSocket;

import java.net.URL;

/**
 * Seguimiento de la entrega en un mapa (Modulo 6).
 *
 * COMO ENCAJAN LAS PIEZAS
 *
 *   servidor de rastreo (Flask + Flask-Sock)
 *        |  WebSocket, JSON, una posicion por segundo
 *        v
 *   TrackingSocket  (cliente WebSocket EN JAVA, con el Bearer en la
 *        |           cabecera del handshake)
 *        v
 *   esta pantalla   (recibe el JSON y lo entrega a la pagina)
 *        |  webEngine.executeScript("LIB.posicion({...})")
 *        v
 *   WebView con Leaflet + OpenStreetMap
 *
 * POR QUE EL WEBSOCKET ESTA EN JAVA Y NO EN LA PAGINA. Ademas de que el
 * enunciado lo pide, el WebSocket de un navegador no permite poner
 * cabeceras en el handshake: el token tendria que ir en la URL, donde
 * acaba en los registros del servidor. Desde Java va como
 * Authorization: Bearer, igual que el resto de la aplicacion.
 *
 * EL MAPA NO SE RECARGA NUNCA. Se carga una vez y despues solo se le
 * empujan posiciones; mover un marcador no es recargar una pagina.
 */
public final class TrackingView extends BorderPane {

    private final Contexto contexto;
    private final WebView navegador = new WebView();
    private final WebEngine motor = navegador.getEngine();

    private final TextField campoCodigo = new TextField();
    private final Label estadoConexion = new Label("Sin rastreo activo");
    private final Button conectar = new Button("Rastrear pedido");
    private final Button desconectar = new Button("Detener");

    private TrackingSocket socket;
    private boolean paginaLista = false;
    private String codigoPendiente;

    public TrackingView(Contexto contexto) {
        this.contexto = contexto;
        setPadding(new Insets(16));
        setTop(barra());
        setCenter(navegador);
        cargarPagina();
    }

    private Region barra() {
        Label titulo = new Label("Seguimiento de entrega");
        titulo.getStyleClass().add("titulo-grande");

        campoCodigo.setPromptText("LIB-MTY-2026-000042");
        campoCodigo.setPrefWidth(230);
        campoCodigo.setOnAction(evento -> iniciar());

        conectar.getStyleClass().add("boton-principal");
        conectar.setOnAction(evento -> iniciar());

        desconectar.setDisable(true);
        desconectar.setOnAction(evento -> detener());

        estadoConexion.getStyleClass().add("subtitulo");

        Region separador = new Region();
        HBox.setHgrow(separador, Priority.ALWAYS);

        HBox fila = new HBox(10, new Label("Codigo:"), campoCodigo, conectar,
                desconectar, separador, estadoConexion);
        fila.setAlignment(Pos.CENTER_LEFT);

        Label nota = new Label(
                "El codigo se deriva del numero real del pedido (PED-000042 -> "
                + "LIB-MTY-2026-000042). El servidor de rastreo comprueba con el "
                + "servicio de pedidos que el pedido sea tuyo antes de ensenar nada.");
        nota.getStyleClass().add("pie");
        nota.setWrapText(true);

        javafx.scene.layout.VBox caja = new javafx.scene.layout.VBox(8, titulo, fila, nota);
        caja.setPadding(new Insets(0, 0, 12, 0));
        return caja;
    }

    private void cargarPagina() {
        /*
         * IDENTIFICARSE ANTE OPENSTREETMAP. Su politica de uso de
         * mosaicos exige un User-Agent que diga quien eres; a los
         * clientes genericos los limita o los bloquea, y el resultado
         * son cuadros grises en el mapa. El WebView manda por omision
         * un UA de WebKit sin identificar la aplicacion, asi que se le
         * pone uno propio. No es cosmetica: es la condicion para poder
         * usar sus mosaicos.
         */
        motor.setUserAgent("LibreriaEnLineaDesktop/1.0 "
                + "(cliente de escritorio JavaFX; practica academica UDEM) "
                + motor.getUserAgent());

        URL pagina = getClass().getResource("/map/mapa.html");
        if (pagina == null) {
            estadoConexion.setText("No se encontro la pagina del mapa en los recursos.");
            return;
        }
        motor.getLoadWorker().stateProperty().addListener((obs, antes, ahora) -> {
            if (ahora == javafx.concurrent.Worker.State.SUCCEEDED) {
                paginaLista = true;
                // Leaflet calcula el tamano al cargar; dentro de un
                // WebView que todavia no tiene medidas sale un mapa de
                // cero pixeles. Esto lo obliga a recalcular.
                ejecutar("LIB.redimensionar()");
                if (codigoPendiente != null) {
                    String codigo = codigoPendiente;
                    codigoPendiente = null;
                    abrirSocket(codigo);
                }
            } else if (ahora == javafx.concurrent.Worker.State.FAILED) {
                estadoConexion.setText("No se pudo cargar el mapa.");
            }
        });
        motor.load(pagina.toExternalForm());

        // El WebView cambia de tamano con la ventana; Leaflet necesita
        // enterarse o deja franjas grises donde no ha pedido mosaicos.
        navegador.widthProperty().addListener((obs, antes, ahora) -> ejecutar("LIB.redimensionar()"));
        navegador.heightProperty().addListener((obs, antes, ahora) -> ejecutar("LIB.redimensionar()"));
    }

    /** Lo llaman las otras pantallas al pulsar "rastrear". */
    public void rastrear(String codigo) {
        campoCodigo.setText(codigo);
        iniciar();
    }

    private void iniciar() {
        String codigo = campoCodigo.getText() == null ? "" : campoCodigo.getText().trim().toUpperCase();
        if (codigo.isBlank()) {
            Tareas.aviso("Falta el codigo",
                    "Escribe el codigo de rastreo, o seleccionalo desde Mis compras.");
            return;
        }
        campoCodigo.setText(codigo);
        if (!paginaLista) {
            codigoPendiente = codigo;
            estadoConexion.setText("Preparando el mapa...");
            return;
        }
        abrirSocket(codigo);
    }

    private void abrirSocket(String codigo) {
        detener();
        socket = new TrackingSocket(
                contexto.config(), contexto.tokens(),
                this::alLlegarMensaje,
                (evento, texto) -> Tareas.enHiloDeInterfaz(() -> {
                    estadoConexion.setText(texto);
                    boolean vivo = evento == TrackingSocket.Evento.CONECTADO
                            || evento == TrackingSocket.Evento.CONECTANDO;
                    conectar.setDisable(vivo);
                    desconectar.setDisable(!vivo);
                    if (evento == TrackingSocket.Evento.RECHAZADO
                            || evento == TrackingSocket.Evento.ERROR) {
                        ejecutar("LIB.error(" + json(texto) + ")");
                    }
                }));
        socket.conectar(codigo);
    }

    private void detener() {
        if (socket != null) {
            socket.cerrar();
            socket = null;
        }
        conectar.setDisable(false);
        desconectar.setDisable(true);
    }

    /**
     * Cada mensaje del servidor se reenvia a la pagina.
     *
     * executeScript DEBE correr en el hilo de JavaFX: el WebEngine no es
     * seguro para hilos y llamarlo desde el hilo del WebSocket produce
     * fallos que no apuntan a su causa.
     */
    private void alLlegarMensaje(JsonNode mensaje) {
        String tipo = mensaje.path("type").asText("");
        String carga = mensaje.toString();
        Tareas.enHiloDeInterfaz(() -> {
            switch (tipo) {
                case "snapshot" -> ejecutar("LIB.snapshot(" + carga + ")");
                case "posicion" -> ejecutar("LIB.posicion(" + carga + ")");
                case "estado" -> {
                    ejecutar("LIB.estado(" + carga + ")");
                    estadoConexion.setText("Estado: " + mensaje.path("status").asText(""));
                }
                case "error" -> {
                    String motivo = mensaje.path("reason").asText("rastreo rechazado");
                    estadoConexion.setText(motivo);
                    ejecutar("LIB.error(" + json(motivo) + ")");
                }
                default -> { /* un tipo nuevo del servidor no debe romper al cliente */ }
            }
        });
    }

    private void ejecutar(String guion) {
        try {
            motor.executeScript(guion);
        } catch (RuntimeException exc) {
            // Si la pagina aun no cargo o cambio, no vale la pena tumbar
            // la aplicacion por no poder mover un marcador.
            System.err.println("[mapa] no se pudo ejecutar: " + exc.getMessage());
        }
    }

    private static String json(String texto) {
        return "\"" + texto.replace("\\", "\\\\").replace("\"", "\\\"")
                .replace("\n", " ") + "\"";
    }

    /** Al cerrar la aplicacion o cambiar de usuario. */
    public void liberar() {
        detener();
    }
}
