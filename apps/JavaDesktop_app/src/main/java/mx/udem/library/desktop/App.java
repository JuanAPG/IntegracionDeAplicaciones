package mx.udem.library.desktop;

import javafx.application.Application;
import javafx.scene.Scene;
import javafx.scene.layout.StackPane;
import javafx.stage.Stage;
import mx.udem.library.desktop.config.Config;
import mx.udem.library.desktop.ui.LoginView;
import mx.udem.library.desktop.ui.MainView;
import mx.udem.library.desktop.ui.Tareas;

/**
 * Cliente de escritorio de la Libreria en Linea.
 *
 * Aplicacion JavaFX que consume los seis microservicios del monorepo por
 * REST/JSON con autenticacion JWT, y el servidor de rastreo por
 * WebSocket. No habla con PostgreSQL: todas las operaciones de negocio
 * pasan por los servicios.
 *
 * Arranque:
 *     mvn -s maven-settings.xml clean javafx:run
 */
public final class App extends Application {

    private final StackPane raiz = new StackPane();
    private Contexto contexto;
    private MainView principal;

    @Override
    public void start(Stage ventana) {
        contexto = new Contexto(Config.cargar());

        Scene escena = new Scene(raiz, 1280, 820);
        escena.getStylesheets().add(
                getClass().getResource("/estilos.css").toExternalForm());

        mostrarLogin();

        ventana.setScene(escena);
        ventana.setTitle("Libreria en Linea · cliente de escritorio");
        ventana.setMinWidth(1040);
        ventana.setMinHeight(700);
        ventana.show();
    }

    private void mostrarLogin() {
        if (principal != null) {
            principal.liberar();
            principal = null;
        }
        raiz.getChildren().setAll(new LoginView(contexto, this::mostrarPrincipal));
    }

    private void mostrarPrincipal() {
        principal = new MainView(contexto, this::mostrarLogin);
        raiz.getChildren().setAll(principal);
    }

    @Override
    public void stop() {
        if (principal != null) {
            principal.liberar();
        }
        Tareas.cerrar();
    }

    public static void main(String[] args) {
        launch(args);
    }
}
