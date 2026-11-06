package mx.udem.library.desktop;

import mx.udem.library.desktop.auth.TokenStore;
import mx.udem.library.desktop.cart.Cart;
import mx.udem.library.desktop.config.Config;
import mx.udem.library.desktop.config.Service;
import mx.udem.library.desktop.net.ApiClient;
import mx.udem.library.desktop.service.AuthorsService;
import mx.udem.library.desktop.service.BooksService;
import mx.udem.library.desktop.service.HealthService;
import mx.udem.library.desktop.service.LoginService;
import mx.udem.library.desktop.service.OrdersService;
import mx.udem.library.desktop.service.PaymentsService;
import mx.udem.library.desktop.service.UsersService;

import java.util.EnumMap;
import java.util.Map;

/**
 * Todo lo que la aplicacion necesita, construido una sola vez.
 *
 * UN SOLO TokenStore PARA LOS SEIS CLIENTES: cuando uno renueva el
 * token, los demas lo tienen al instante. Con una copia por cliente,
 * bastaria con que uno renovara para que los otros cinco siguieran
 * mandando un token ya revocado.
 *
 * EL GANCHO DE RENOVACION se conecta aqui y no en el constructor de
 * ApiClient porque hay una dependencia circular: el cliente necesita
 * saber renovar, y quien sabe renovar es el servicio de login, que a su
 * vez es un cliente.
 */
public final class Contexto {

    private final Config config;
    private final TokenStore tokens = new TokenStore();
    private final Map<Service, ApiClient> clientes = new EnumMap<>(Service.class);
    private final Cart cesta = new Cart();

    private final LoginService login;
    private final UsersService usuarios;
    private final BooksService libros;
    private final AuthorsService autores;
    private final OrdersService pedidos;
    private final PaymentsService pagos;
    private final HealthService salud;

    public Contexto(Config config) {
        this.config = config;
        for (Service servicio : Service.values()) {
            clientes.put(servicio, new ApiClient(config, servicio, tokens));
        }
        this.login = new LoginService(clientes.get(Service.LOGIN), tokens);
        this.usuarios = new UsersService(clientes.get(Service.USERS));
        this.libros = new BooksService(clientes.get(Service.BOOKS));
        this.autores = new AuthorsService(clientes.get(Service.AUTHORS));
        this.pedidos = new OrdersService(clientes.get(Service.PEDIDOS));
        this.pagos = new PaymentsService(clientes.get(Service.PAGOS));
        this.salud = new HealthService(config);

        // Todos los clientes renuevan por la misma via.
        clientes.values().forEach(cliente -> cliente.setRenovador(login::renovar));
    }

    public Config config() {
        return config;
    }

    public TokenStore tokens() {
        return tokens;
    }

    public Cart cesta() {
        return cesta;
    }

    public ApiClient cliente(Service servicio) {
        return clientes.get(servicio);
    }

    public LoginService login() {
        return login;
    }

    public UsersService usuarios() {
        return usuarios;
    }

    public BooksService libros() {
        return libros;
    }

    public AuthorsService autores() {
        return autores;
    }

    public OrdersService pedidos() {
        return pedidos;
    }

    public PaymentsService pagos() {
        return pagos;
    }

    public HealthService salud() {
        return salud;
    }
}
