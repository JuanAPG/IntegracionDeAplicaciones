package mx.udem.library.desktop.ui;

import mx.udem.library.desktop.net.ApiException;

/** Traduce un fallo a una frase util. */
public final class Mensajes {

    private Mensajes() {
    }

    public static String de(Throwable error) {
        Throwable actual = error;
        while (actual != null) {
            if (actual instanceof ApiException api) {
                return api.mensajeParaUsuario();
            }
            actual = actual.getCause();
        }
        if (error == null) {
            return "Fallo desconocido.";
        }
        return error.getMessage() == null ? error.getClass().getSimpleName() : error.getMessage();
    }
}
