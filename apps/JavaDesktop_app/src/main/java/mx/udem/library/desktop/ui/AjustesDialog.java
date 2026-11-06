package mx.udem.library.desktop.ui;

import javafx.geometry.Insets;
import javafx.scene.control.ButtonBar;
import javafx.scene.control.ButtonType;
import javafx.scene.control.Dialog;
import javafx.scene.control.Label;
import javafx.scene.control.TextField;
import javafx.scene.layout.GridPane;
import javafx.scene.layout.VBox;
import mx.udem.library.desktop.Contexto;
import mx.udem.library.desktop.config.Service;

import java.net.URI;

/**
 * Ajustes de conexion.
 *
 * LA IP DE LA INSTANCIA DE GCP CAMBIA CADA VEZ QUE SE REINICIA. Por eso
 * lo primero del dialogo es un solo campo que reapunta los SIETE
 * destinos conservando sus puertos: es la operacion que de verdad se usa.
 * Debajo quedan las URL una por una por si algun servicio vive en otra
 * maquina.
 */
public final class AjustesDialog extends Dialog<Boolean> {

    public AjustesDialog(Contexto contexto) {
        setTitle("Ajustes de conexion");
        setHeaderText("Donde viven los servicios");

        TextField campoIp = new TextField();
        campoIp.setPromptText("por ejemplo 34.51.65.207");
        campoIp.setText(contexto.config().base(Service.BOOKS).getHost());

        GridPane rejilla = new GridPane();
        rejilla.setHgap(10);
        rejilla.setVgap(8);
        rejilla.setPadding(new Insets(14));

        rejilla.add(new Label("IP de la instancia:"), 0, 0);
        rejilla.add(campoIp, 1, 0);
        rejilla.add(new Label("Aplica a los siete puertos."), 1, 1);

        TextField[] campos = new TextField[Service.values().length];
        int fila = 2;
        for (Service servicio : Service.values()) {
            TextField campo = new TextField(contexto.config().base(servicio).toString());
            campo.setPrefColumnCount(30);
            campos[servicio.ordinal()] = campo;
            rejilla.add(new Label(servicio.id() + " (" + servicio.defaultPort() + "):"), 0, fila);
            rejilla.add(campo, 1, fila);
            fila++;
        }

        campoIp.textProperty().addListener((obs, antes, ahora) -> {
            if (ahora == null || ahora.isBlank()) {
                return;
            }
            for (Service servicio : Service.values()) {
                campos[servicio.ordinal()].setText(
                        "http://" + ahora.trim() + ":" + servicio.defaultPort());
            }
        });

        Label nota = new Label("""
                El mapa de puertos se comprueba con /health: cada servicio dice
                su propio nombre. Si un puerto contesta con otra identidad, la
                aplicacion lo avisa en los semaforos en lugar de mandar los
                datos al servicio equivocado.""");
        nota.setWrapText(true);
        nota.getStyleClass().add("pie");

        VBox contenido = new VBox(10, rejilla, nota);
        contenido.setPadding(new Insets(6));
        Ui.aplicarEstilos(getDialogPane());
        getDialogPane().setContent(contenido);
        getDialogPane().getButtonTypes().addAll(
                new ButtonType("Guardar", ButtonBar.ButtonData.OK_DONE), ButtonType.CANCEL);

        setResultConverter(boton -> {
            if (boton == null || boton.getButtonData() != ButtonBar.ButtonData.OK_DONE) {
                return false;
            }
            for (Service servicio : Service.values()) {
                String valor = campos[servicio.ordinal()].getText();
                if (valor != null && !valor.isBlank()) {
                    try {
                        contexto.config().setBase(servicio, new URI(valor.trim()));
                    } catch (Exception exc) {
                        Tareas.aviso("URL invalida", valor + " no es una URL valida.");
                        return false;
                    }
                }
            }
            try {
                contexto.config().guardar();
            } catch (Exception exc) {
                Tareas.aviso("No se pudo guardar",
                        "Los cambios valen para esta sesion, pero no se pudieron "
                        + "escribir en disco: " + exc.getMessage());
            }
            return true;
        });
    }
}
