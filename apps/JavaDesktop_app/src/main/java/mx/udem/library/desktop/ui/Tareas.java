package mx.udem.library.desktop.ui;

import javafx.application.Platform;
import javafx.concurrent.Task;
import javafx.scene.control.Alert;
import javafx.scene.control.ButtonType;
import mx.udem.library.desktop.net.ApiException;

import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.function.Consumer;
import java.util.function.Supplier;

/**
 * Ejecutar trabajo de red fuera del hilo de la interfaz.
 *
 * POR QUE IMPORTA TANTO. JavaFX pinta en un solo hilo. Si una peticion
 * HTTP se hace en ese hilo, la ventana se congela mientras dura -- y con
 * un servidor en la nube eso es entre 100 ms y el tiempo limite de 20
 * segundos. Una aplicacion que se queda blanca cada vez que pulsas un
 * boton parece rota aunque funcione.
 *
 * La regla, sin excepciones: lo que toca la red va en {@code enSegundoPlano};
 * lo que toca la interfaz va en el bloque de exito o de fallo, que esta
 * clase ya ejecuta en el hilo de JavaFX.
 */
public final class Tareas {

    // Hilos demonio: si quedara alguno vivo, la aplicacion no cerraria
    // al cerrar la ventana y el proceso seguiria en segundo plano.
    private static final ExecutorService POOL = Executors.newFixedThreadPool(4, hilo -> {
        Thread t = new Thread(hilo, "red-libreria");
        t.setDaemon(true);
        return t;
    });

    private Tareas() {
    }

    public static <T> void enSegundoPlano(Supplier<T> trabajo,
                                          Consumer<T> alTerminar,
                                          Consumer<Throwable> alFallar) {
        Task<T> tarea = new Task<>() {
            @Override
            protected T call() {
                return trabajo.get();
            }
        };
        tarea.setOnSucceeded(evento -> alTerminar.accept(tarea.getValue()));
        tarea.setOnFailed(evento -> {
            Throwable error = tarea.getException();
            if (alFallar != null) {
                alFallar.accept(error);
            } else {
                error(error);
            }
        });
        POOL.execute(tarea);
    }

    public static void enHiloDeInterfaz(Runnable accion) {
        if (Platform.isFxApplicationThread()) {
            accion.run();
        } else {
            Platform.runLater(accion);
        }
    }

    public static void cerrar() {
        POOL.shutdownNow();
    }

    // -----------------------------------------------------------------
    // Dialogos
    // -----------------------------------------------------------------

    /**
     * Ensena un fallo.
     *
     * Si es un ApiException usa su mensaje para la persona, que dice QUE
     * HACER ("vuelve a iniciar sesion") en vez de que fallo
     * ("401 Unauthorized"). Los detalles del servicio van debajo: en un
     * 409 por falta de existencias son justo lo util.
     */
    public static void error(Throwable error) {
        String mensaje;
        if (error instanceof ApiException api) {
            mensaje = api.mensajeParaUsuario();
        } else if (error != null && error.getCause() instanceof ApiException api) {
            mensaje = api.mensajeParaUsuario();
        } else if (error != null) {
            mensaje = error.getMessage() == null
                    ? error.getClass().getSimpleName() : error.getMessage();
        } else {
            mensaje = "Fallo desconocido.";
        }
        final String texto = mensaje;
        enHiloDeInterfaz(() -> {
            Alert alerta = new Alert(Alert.AlertType.ERROR, texto, ButtonType.OK);
            Ui.aplicarEstilos(alerta.getDialogPane());
            alerta.setHeaderText(null);
            alerta.setTitle("No se pudo completar");
            alerta.getDialogPane().setMinWidth(420);
            alerta.showAndWait();
        });
    }

    public static void aviso(String titulo, String texto) {
        enHiloDeInterfaz(() -> {
            Alert alerta = new Alert(Alert.AlertType.INFORMATION, texto, ButtonType.OK);
            Ui.aplicarEstilos(alerta.getDialogPane());
            alerta.setHeaderText(titulo);
            alerta.setTitle(titulo);
            alerta.getDialogPane().setMinWidth(420);
            alerta.showAndWait();
        });
    }

    public static boolean confirmar(String titulo, String texto) {
        Alert alerta = new Alert(Alert.AlertType.CONFIRMATION, texto, ButtonType.CANCEL, ButtonType.OK);
        Ui.aplicarEstilos(alerta.getDialogPane());
        alerta.setHeaderText(titulo);
        alerta.setTitle(titulo);
        alerta.getDialogPane().setMinWidth(420);
        return alerta.showAndWait().filter(b -> b == ButtonType.OK).isPresent();
    }
}
