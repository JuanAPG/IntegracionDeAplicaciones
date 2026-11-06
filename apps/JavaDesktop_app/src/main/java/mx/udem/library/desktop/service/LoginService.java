package mx.udem.library.desktop.service;

import com.fasterxml.jackson.databind.JsonNode;
import mx.udem.library.desktop.auth.TokenStore;
import mx.udem.library.desktop.net.ApiClient;
import mx.udem.library.desktop.net.ApiException;

import java.util.Map;

/**
 * Microservicio de autenticacion (5000).
 *
 * EL CAMPO DEL TOKEN SE LLAMA `token`. No `accessToken` ni
 * `access_token`: se verifico contra el serializador del servicio. Es el
 * tipo de detalle que cuesta una tarde si se asume.
 *
 * HAY QUE PEDIR JSON SI O SI EN /login Y /refresh. El servicio NO publica
 * los tokens en su representacion XML, y lo hace a proposito: los XML
 * acaban en archivos y registros intermedios con demasiada facilidad. Si
 * esta aplicacion olvidara el parametro de formato, recibiria un 200
 * perfectamente valido sin token dentro. El ApiClient lo pone siempre.
 */
public final class LoginService {

    private final ApiClient api;
    private final TokenStore tokens;

    public LoginService(ApiClient api, TokenStore tokens) {
        this.api = api;
        this.tokens = tokens;
    }

    /**
     * Inicia sesion. La contrasena viaja en el cuerpo y NO se guarda en
     * ningun sitio: ni en disco, ni en un campo, ni para reintentar.
     */
    public void iniciarSesion(String email, String password) {
        JsonNode respuesta = api.post("/login",
                Map.of("email", email, "password", password), false);
        tokens.actualizar(respuesta);
    }

    /**
     * Renueva el token de acceso con el de refresco.
     *
     * EL REFRESH ES DE UN SOLO USO CON ROTACION: la respuesta trae uno
     * nuevo y el anterior queda inservible en el acto, de modo que
     * guardar el nuevo es obligatorio (lo hace {@code tokens.actualizar}).
     *
     * Devuelve true si hay token nuevo. Distingue dos fallos que parecen
     * el mismo y no lo son:
     *   - el servidor dice que no (401): la sesion murio, se limpia;
     *   - no se pudo ni preguntar (red): la sesion puede seguir viva, NO
     *     se limpia. Tirar una sesion buena porque el wifi parpadeo es un
     *     error que ya cometieron y corrigieron los otros dos clientes
     *     del proyecto.
     */
    public boolean renovar() {
        String refresco = tokens.refreshToken();
        if (refresco == null || refresco.isBlank()) {
            return false;
        }
        try {
            JsonNode respuesta = api.post("/refresh", Map.of("refreshToken", refresco), false);
            tokens.actualizar(respuesta);
            return tokens.haySesion();
        } catch (ApiException exc) {
            if (exc.esDeRed()) {
                return false;
            }
            tokens.limpiar();
            return false;
        }
    }

    /**
     * Cierra la sesion.
     *
     * Manda el Bearer, no solo borra lo local: eso es lo que hace que el
     * servidor meta el `jti` en la lista de revocacion de Redis y el
     * token deje de valer en los SEIS servicios al instante. Un logout
     * que solo borra en el cliente deja un token vivo 30 minutos.
     *
     * Si la llamada falla, se limpia igualmente: desde el punto de vista
     * de quien pulso "salir", la sesion tiene que terminar.
     */
    public void cerrarSesion() {
        try {
            api.post("/logout", Map.of(), true);
        } catch (ApiException ignorado) {
            // Se limpia de todos modos.
        } finally {
            tokens.limpiar();
        }
    }

    /**
     * Comprueba contra el servidor si la sesion sigue viva. Ademas
     * RENUEVA la ventana deslizante de 8 horas de la sesion en Redis.
     */
    public boolean sesionVigente() {
        try {
            JsonNode respuesta = api.get("/session", true);
            return respuesta.path("authenticated").asBoolean(false);
        } catch (ApiException exc) {
            return false;
        }
    }
}
