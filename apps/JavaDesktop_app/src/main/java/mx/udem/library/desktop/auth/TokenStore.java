package mx.udem.library.desktop.auth;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;

import java.nio.charset.StandardCharsets;
import java.time.Instant;
import java.util.Base64;
import java.util.Optional;
import java.util.function.Consumer;

/**
 * La sesion: el token de acceso, el de refresco y lo que se sabe del
 * usuario. UNO solo, compartido por los seis clientes de servicio.
 *
 * POR QUE UNO SOLO. Cuando el cliente de pedidos renueva el token, el de
 * libros y el de pagos tienen que enterarse sin que nadie se los diga. Si
 * cada cliente guardara su copia, bastaria con que uno renovara para que
 * los otros cinco siguieran mandando un token ya revocado -- y la
 * revocacion es inmediata, porque el `jti` viejo entra en la lista de
 * Redis en cuanto se usa el refresh.
 *
 * LOS CLAIMS SE LEEN SIN VERIFICAR LA FIRMA, Y ES CORRECTO. Aqui solo se
 * decodifica el Base64URL del cuerpo del JWT para saber cuando caduca y
 * que rol tiene, y eso sirve UNICAMENTE para decidir cuando renovar y que
 * botones ensenar. La autorizacion de verdad la aplica cada microservicio
 * al verificar la firma con el secreto compartido. Por eso esta clase no
 * necesita ninguna libreria de JWT: meter una en un cliente invita a
 * creer que el cliente decide algo sobre seguridad, y no decide nada.
 *
 * LA CONTRASENA NUNCA ENTRA AQUI. Ni se guarda, ni se recuerda para
 * reintentar. Lo que se conserva son dos credenciales que el servidor
 * puede revocar en cualquier momento.
 */
public final class TokenStore {

    private static final ObjectMapper MAPPER = new ObjectMapper();

    private String accessToken;
    private String refreshToken;
    private Instant expiraEn;
    /** Segundos antes de `exp` en los que conviene renovar. Lo publica el servidor. */
    private int renovarAntes = 300;

    private int userId;
    private String email = "";
    private String nombreCompleto = "";
    private String rol = "";

    private Consumer<TokenStore> alCambiar = store -> { };

    public synchronized void setListener(Consumer<TokenStore> listener) {
        this.alCambiar = listener == null ? store -> { } : listener;
    }

    /**
     * Guarda lo que devolvieron {@code /login} o {@code /refresh}. Los dos
     * responden con la MISMA forma, de ahi que haya un solo metodo.
     *
     * Ojo con {@code refreshToken}: es de UN SOLO USO con rotacion. Cada
     * renovacion trae uno nuevo y el anterior queda inservible, de modo
     * que guardar el nuevo no es opcional.
     */
    public synchronized void actualizar(JsonNode respuesta) {
        this.accessToken = texto(respuesta, "token");
        this.refreshToken = texto(respuesta, "refreshToken");
        if (respuesta.hasNonNull("renewBefore")) {
            this.renovarAntes = respuesta.get("renewBefore").asInt(300);
        }

        JsonNode usuario = respuesta.get("user");
        if (usuario != null && usuario.isObject()) {
            this.userId = usuario.path("id").asInt(this.userId);
            this.email = usuario.path("email").asText(this.email);
            this.nombreCompleto = usuario.path("fullName").asText(this.nombreCompleto);
            this.rol = usuario.path("role").asText(this.rol);
        }

        // `exp` del propio token manda sobre `expiresIn`: es la verdad que
        // van a comprobar los microservicios al verificar la firma.
        this.expiraEn = leerExpiracion(this.accessToken)
                .orElseGet(() -> Instant.now().plusSeconds(respuesta.path("expiresIn").asLong(1800)));

        JsonNode claims = claims(this.accessToken).orElse(null);
        if (claims != null) {
            if (claims.hasNonNull("user_id")) {
                this.userId = claims.get("user_id").asInt(this.userId);
            }
            if (claims.hasNonNull("role")) {
                this.rol = claims.get("role").asText(this.rol);
            }
            if (claims.hasNonNull("email")) {
                this.email = claims.get("email").asText(this.email);
            }
        }
        alCambiar.accept(this);
    }

    public synchronized void limpiar() {
        accessToken = null;
        refreshToken = null;
        expiraEn = null;
        userId = 0;
        email = "";
        nombreCompleto = "";
        rol = "";
        alCambiar.accept(this);
    }

    public synchronized boolean haySesion() {
        return accessToken != null && !accessToken.isBlank();
    }

    public synchronized String accessToken() {
        return accessToken;
    }

    public synchronized String refreshToken() {
        return refreshToken;
    }

    public synchronized int userId() {
        return userId;
    }

    public synchronized String email() {
        return email;
    }

    public synchronized String nombreCompleto() {
        return nombreCompleto == null || nombreCompleto.isBlank() ? email : nombreCompleto;
    }

    public synchronized String rol() {
        return rol;
    }

    public synchronized Instant expiraEn() {
        return expiraEn;
    }

    /**
     * Verdadero cuando falta poco para que caduque.
     *
     * Se renueva ANTES del 401, no con el 401: gastar una peticion fallida
     * para enterarse de algo que el propio token ya dice es trabajo de mas
     * y, sobre todo, es una operacion de negocio que falla a mitad.
     */
    public synchronized boolean convieneRenovar() {
        if (accessToken == null || expiraEn == null) {
            return false;
        }
        return Instant.now().isAfter(expiraEn.minusSeconds(renovarAntes));
    }

    public synchronized boolean estaCaducado() {
        return expiraEn != null && Instant.now().isAfter(expiraEn);
    }

    /** Cuerpo del JWT sin verificar la firma. Solo para la interfaz. */
    public static Optional<JsonNode> claims(String jwt) {
        if (jwt == null) {
            return Optional.empty();
        }
        String[] partes = jwt.split("\\.");
        if (partes.length < 2) {
            return Optional.empty();
        }
        try {
            byte[] cuerpo = Base64.getUrlDecoder().decode(rellenar(partes[1]));
            return Optional.of(MAPPER.readTree(new String(cuerpo, StandardCharsets.UTF_8)));
        } catch (Exception exc) {
            return Optional.empty();
        }
    }

    private static Optional<Instant> leerExpiracion(String jwt) {
        return claims(jwt)
                .filter(node -> node.hasNonNull("exp"))
                .map(node -> Instant.ofEpochSecond(node.get("exp").asLong()));
    }

    /** Base64URL sin relleno: hay que devolverle los '=' antes de decodificar. */
    private static String rellenar(String base64url) {
        int faltan = (4 - base64url.length() % 4) % 4;
        return base64url + "=".repeat(faltan);
    }

    private static String texto(JsonNode nodo, String campo) {
        JsonNode valor = nodo.get(campo);
        return valor == null || valor.isNull() ? null : valor.asText();
    }
}
