// Prueba HTTP local: Nginx y upstreams simulados; no conecta a la VM.
import java.net.URI;
import mx.udem.library.desktop.config.Config;
import mx.udem.library.desktop.config.Service;
import mx.udem.library.desktop.net.ApiClient;
import mx.udem.library.desktop.auth.TokenStore;

public class PruebaGateway {
    public static void main(String[] args) {
        var config = Config.cargar();
        var tokens = new TokenStore();
        check(config, tokens, Service.LOGIN, "/login", 5000, "/login?format=json");
        check(config, tokens, Service.BOOKS, "/books/15", 5001, "/books/15?output=json");
        check(config, tokens, Service.USERS, "/roles", 5002, "/roles?format=json");
        check(config, tokens, Service.AUTHORS, "/authors/3/books", 5003, "/authors/3/books?format=json");
        check(config, tokens, Service.PEDIDOS, "/envios/ABC", 5004, "/envios/ABC?format=json");
        check(config, tokens, Service.PAGOS, "/pedidos/15/saldo", 5005, "/pedidos/15/saldo?format=json");
    }
    static void check(Config config, TokenStore tokens, Service service, String path, int port, String uri) {
        config.setBase(service, URI.create("http://127.0.0.1:18081/api/" + service.id()));
        var result = new ApiClient(config, service, tokens).get(path, false);
        if (result.path("port").asInt() != port || !result.path("uri").asText().equals(uri)) {
            throw new AssertionError("Destino inesperado: " + result);
        }
        System.out.println("Java: " + path + " -> :" + port + uri + " OK");
    }
}
