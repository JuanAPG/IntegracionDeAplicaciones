package mx.udem.library.desktop.ui;

import javafx.geometry.Insets;
import javafx.geometry.Pos;
import javafx.scene.control.Button;
import javafx.scene.control.Hyperlink;
import javafx.scene.control.Label;
import javafx.scene.control.PasswordField;
import javafx.scene.control.ProgressIndicator;
import javafx.scene.control.TextField;
import javafx.scene.layout.BorderPane;
import javafx.scene.layout.HBox;
import javafx.scene.layout.Priority;
import javafx.scene.layout.Region;
import javafx.scene.layout.VBox;
import mx.udem.library.desktop.Contexto;

/**
 * Pantalla de inicio de sesion (Modulo 1).
 *
 * LA CONTRASENA NO SE GUARDA EN NINGUN SITIO. Se toma del campo, viaja
 * en el cuerpo de la peticion y se olvida. Lo que queda despues es el
 * token de acceso y el de refresco, que el servidor puede revocar.
 */
public final class LoginView extends BorderPane {

    private final Contexto contexto;
    private final Runnable alEntrar;

    private final TextField campoCorreo = new TextField();
    private final PasswordField campoClave = new PasswordField();
    private final Label mensaje = new Label();
    private final Button botonEntrar = new Button("Iniciar sesion");
    private final ProgressIndicator girando = new ProgressIndicator();

    public LoginView(Contexto contexto, Runnable alEntrar) {
        this.contexto = contexto;
        this.alEntrar = alEntrar;
        getStyleClass().add("fondo");
        setCenter(construir());
    }

    private Region construir() {
        Label titulo = new Label("Libreria en Linea");
        titulo.getStyleClass().add("titulo-grande");
        Label subtitulo = new Label("Cliente de escritorio · Java + JavaFX");
        subtitulo.getStyleClass().add("subtitulo");

        campoCorreo.setPromptText("correo electronico");
        campoClave.setPromptText("contrasena");
        campoCorreo.setPrefWidth(320);
        campoClave.setPrefWidth(320);

        botonEntrar.getStyleClass().add("boton-principal");
        botonEntrar.setDefaultButton(true);
        botonEntrar.setMaxWidth(Double.MAX_VALUE);
        botonEntrar.setOnAction(evento -> entrar());

        girando.setVisible(false);
        girando.setMaxSize(22, 22);

        mensaje.getStyleClass().add("mensaje-error");
        mensaje.setWrapText(true);
        mensaje.setMaxWidth(320);

        Hyperlink ajustes = new Hyperlink("Ajustes de conexion");
        ajustes.setOnAction(evento -> new AjustesDialog(contexto).showAndWait());

        Label pie = new Label("Las operaciones protegidas usan JWT (Authorization: Bearer).\n"
                + "Esta aplicacion nunca guarda tu contrasena.");
        pie.getStyleClass().add("pie");
        pie.setWrapText(true);
        pie.setMaxWidth(320);

        VBox tarjeta = new VBox(12, titulo, subtitulo, new Region(),
                campoCorreo, campoClave,
                new HBox(8, botonEntrar), mensaje,
                new HBox(8, ajustes), pie);
        tarjeta.getStyleClass().add("tarjeta");
        tarjeta.setAlignment(Pos.CENTER_LEFT);
        tarjeta.setPadding(new Insets(32));
        tarjeta.setMaxSize(400, Region.USE_PREF_SIZE);

        HBox fila = (HBox) tarjeta.getChildren().get(5);
        HBox.setHgrow(botonEntrar, Priority.ALWAYS);
        fila.getChildren().add(girando);
        fila.setAlignment(Pos.CENTER_LEFT);

        VBox centro = new VBox(tarjeta);
        centro.setAlignment(Pos.CENTER);
        return centro;
    }

    private void entrar() {
        String correo = campoCorreo.getText() == null ? "" : campoCorreo.getText().trim();
        String clave = campoClave.getText() == null ? "" : campoClave.getText();
        if (correo.isBlank() || clave.isBlank()) {
            mensaje.setText("Escribe tu correo y tu contrasena.");
            return;
        }
        mensaje.setText("");
        ocupado(true);

        Tareas.enSegundoPlano(
                () -> {
                    contexto.login().iniciarSesion(correo, clave);
                    return contexto.tokens().nombreCompleto();
                },
                nombre -> {
                    ocupado(false);
                    // La contrasena se borra del campo en cuanto deja de
                    // hacer falta: no tiene por que seguir en memoria de
                    // la interfaz.
                    campoClave.clear();
                    alEntrar.run();
                },
                error -> {
                    ocupado(false);
                    mensaje.setText(Mensajes.de(error));
                });
    }

    private void ocupado(boolean si) {
        botonEntrar.setDisable(si);
        campoCorreo.setDisable(si);
        campoClave.setDisable(si);
        girando.setVisible(si);
    }
}
