package mx.udem.library.desktop.ui;

import javafx.geometry.Insets;
import javafx.geometry.Pos;
import javafx.scene.control.Button;
import javafx.scene.control.Label;
import javafx.scene.control.Tab;
import javafx.scene.control.TabPane;
import javafx.scene.control.Tooltip;
import javafx.scene.layout.BorderPane;
import javafx.scene.layout.HBox;
import javafx.scene.layout.Priority;
import javafx.scene.layout.Region;
import javafx.scene.layout.VBox;
import javafx.scene.shape.Circle;
import mx.udem.library.desktop.Contexto;
import mx.udem.library.desktop.config.Service;
import mx.udem.library.desktop.model.UserProfile;
import mx.udem.library.desktop.service.HealthService;

import java.util.EnumMap;
import java.util.Map;

/**
 * La ventana principal: barra de identidad, semaforos y las cuatro
 * secciones de la aplicacion.
 *
 * LOS SEMAFOROS TIENEN TRES COLORES Y NO DOS. El amarillo significa
 * "lee pero no escribe": es lo que pasa cuando Redis esta caido, porque
 * los servicios no pueden comprobar si un token fue revocado y rechazan
 * toda escritura, mientras el catalogo publico se sigue leyendo. Pintar
 * eso de verde seria mentir y de rojo exagerar, y en los dos casos el
 * usuario no entenderia por que puede mirar libros pero no comprar.
 */
public final class MainView extends BorderPane {

    private final Contexto contexto;
    private final Runnable alSalir;

    private final Label nombreUsuario = new Label();
    private final Label rolUsuario = new Label();
    private final Map<Service, Circle> luces = new EnumMap<>(Service.class);
    private final Label contadorCesta = new Label();

    private final CatalogView catalogo;
    private final CartView cesta;
    private final OrdersView compras;
    private final TrackingView rastreo;
    private final TabPane pestanas = new TabPane();

    public MainView(Contexto contexto, Runnable alSalir) {
        this.contexto = contexto;
        this.alSalir = alSalir;

        this.rastreo = new TrackingView(contexto);
        this.compras = new OrdersView(contexto, this::irARastreo);
        this.cesta = new CartView(contexto, codigo -> {
            compras.cargar();
            irARastreo(codigo);
        });
        this.catalogo = new CatalogView(contexto);

        setTop(barraSuperior());
        setCenter(construirPestanas());

        contexto.cesta().addListener(c -> Tareas.enHiloDeInterfaz(this::actualizarContador));
        actualizarContador();
        cargarPerfil();
        comprobarSalud();
    }

    private Region barraSuperior() {
        Label marca = new Label("Libreria en Linea");
        marca.getStyleClass().add("marca");

        nombreUsuario.getStyleClass().add("usuario");
        rolUsuario.getStyleClass().add("pie");

        HBox semaforos = new HBox(10);
        semaforos.setAlignment(Pos.CENTER);
        for (Service servicio : Service.values()) {
            Circle luz = new Circle(5);
            luz.getStyleClass().addAll("luz", "luz-desconocida");
            luces.put(servicio, luz);
            Label etiqueta = new Label(servicio.id());
            etiqueta.getStyleClass().add("pie");
            HBox grupo = new HBox(4, luz, etiqueta);
            grupo.setAlignment(Pos.CENTER);
            semaforos.getChildren().add(grupo);
        }

        Button refrescarSalud = new Button("Comprobar servicios");
        refrescarSalud.setOnAction(evento -> comprobarSalud());

        Button ajustes = new Button("Ajustes");
        ajustes.setOnAction(evento -> {
            if (Boolean.TRUE.equals(new AjustesDialog(contexto).showAndWait().orElse(false))) {
                comprobarSalud();
                catalogo.cargar();
            }
        });

        Button salir = new Button("Cerrar sesion");
        salir.setOnAction(evento -> cerrarSesion());

        Region separador = new Region();
        HBox.setHgrow(separador, Priority.ALWAYS);

        VBox identidad = new VBox(1, nombreUsuario, rolUsuario);
        identidad.setAlignment(Pos.CENTER_LEFT);

        HBox barra = new HBox(16, marca, separador, semaforos, refrescarSalud,
                identidad, ajustes, salir);
        barra.setAlignment(Pos.CENTER_LEFT);
        barra.setPadding(new Insets(12, 16, 12, 16));
        barra.getStyleClass().add("barra-superior");
        return barra;
    }

    private Region construirPestanas() {
        Tab tabCatalogo = new Tab("Catalogo", catalogo);
        Tab tabCesta = new Tab("Cesta", cesta);
        Tab tabCompras = new Tab("Mis compras", compras);
        Tab tabRastreo = new Tab("Rastreo", rastreo);

        pestanas.getTabs().addAll(tabCatalogo, tabCesta, tabCompras, tabRastreo);
        pestanas.setTabClosingPolicy(TabPane.TabClosingPolicy.UNAVAILABLE);

        // Al volver a "Mis compras" se recarga: si acabas de comprar,
        // esperas ver tu pedido ahi sin tener que pulsar nada.
        pestanas.getSelectionModel().selectedItemProperty().addListener((obs, antes, ahora) -> {
            if (ahora == tabCompras) {
                compras.cargar();
            }
        });
        contadorCesta.getStyleClass().add("contador");
        tabCesta.setGraphic(contadorCesta);
        return pestanas;
    }

    private void actualizarContador() {
        int piezas = contexto.cesta().totalEjemplares();
        contadorCesta.setText(piezas == 0 ? "" : Integer.toString(piezas));
        contadorCesta.setVisible(piezas > 0);
    }

    private void irARastreo(String codigo) {
        pestanas.getSelectionModel().select(3);
        rastreo.rastrear(codigo);
    }

    /**
     * El nombre del usuario sale del servicio de usuarios, no del token.
     *
     * El JWT ya trae el correo y el rol, pero el perfil completo es del
     * servicio users (5002) y el enunciado pide consultarlo. Si falla,
     * se cae al nombre que trajo el login: la aplicacion no se queda sin
     * identificar al usuario por una peticion que no respondio.
     */
    private void cargarPerfil() {
        nombreUsuario.setText(contexto.tokens().nombreCompleto());
        rolUsuario.setText("rol: " + contexto.tokens().rol());

        int id = contexto.tokens().userId();
        if (id <= 0) {
            return;
        }
        Tareas.enSegundoPlano(
                () -> contexto.usuarios().perfil(id),
                (UserProfile perfil) -> {
                    nombreUsuario.setText(perfil.nombreVisible());
                    rolUsuario.setText("rol: " + perfil.role() + " · " + perfil.email());
                    Tooltip.install(nombreUsuario, new Tooltip(
                            "id " + perfil.id() + "\n" + perfil.email()
                            + "\ncorreo verificado: " + (perfil.emailVerified() ? "si" : "no")
                            + "\nultimo acceso: " + perfil.lastLoginAt()));
                },
                error -> rolUsuario.setText("rol: " + contexto.tokens().rol()
                        + " · no se pudo leer el perfil"));
    }

    private void comprobarSalud() {
        for (Service servicio : Service.values()) {
            Circle luz = luces.get(servicio);
            luz.getStyleClass().setAll("luz", "luz-desconocida");
            Tareas.enSegundoPlano(
                    () -> contexto.salud().comprobar(servicio, contexto.cliente(servicio)),
                    resultado -> pintar(luz, resultado),
                    error -> {
                        luz.getStyleClass().setAll("luz", "luz-caido");
                        Tooltip.install(luz, new Tooltip(servicio.id() + ": " + Mensajes.de(error)));
                    });
        }
    }

    private void pintar(Circle luz, HealthService.Resultado resultado) {
        String clase = switch (resultado.estado()) {
            case ARRIBA -> "luz-arriba";
            case DEGRADADO -> "luz-degradado";
            case CAIDO -> "luz-caido";
        };
        luz.getStyleClass().setAll("luz", clase);
        Tooltip.install(luz, new Tooltip(resultado.servicio().id() + ": " + resultado.detalle()));
    }

    private void cerrarSesion() {
        if (!Tareas.confirmar("Cerrar sesion",
                "Se cerrara tu sesion y se vaciara la cesta.")) {
            return;
        }
        rastreo.liberar();
        contexto.cesta().vaciar();
        // El logout se manda al servidor para que REVOQUE el token: sin
        // eso, el token seguiria valiendo en los seis servicios hasta
        // que caducara por su cuenta.
        Tareas.enSegundoPlano(
                () -> {
                    contexto.login().cerrarSesion();
                    return null;
                },
                nada -> alSalir.run(),
                error -> alSalir.run());
    }

    public void liberar() {
        rastreo.liberar();
    }
}
