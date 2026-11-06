package mx.udem.library.desktop.ui;

import javafx.scene.control.DialogPane;

/**
 * Detalles de presentacion compartidos.
 *
 * POR QUE HACE FALTA aplicarEstilos. Un dialogo de JavaFX vive en su
 * PROPIA ventana y en su propia escena, y por tanto NO hereda la hoja de
 * estilos de la ventana principal: sale con el tema claro de fabrica, con
 * letras oscuras, aunque el resto de la aplicacion sea oscura. Hay que
 * ponersela a cada uno. Si se anade un dialogo nuevo y se olvida esta
 * llamada, se nota al instante porque sale blanco.
 */
public final class Ui {

    private Ui() {
    }

    public static void aplicarEstilos(DialogPane panel) {
        if (panel == null) {
            return;
        }
        var hoja = Ui.class.getResource("/estilos.css");
        if (hoja != null && !panel.getStylesheets().contains(hoja.toExternalForm())) {
            panel.getStylesheets().add(hoja.toExternalForm());
        }
    }
}
